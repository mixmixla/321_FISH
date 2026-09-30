# -*- coding: utf-8 -*-
"""R37 加密云历史回归：

单元（cloud_history / LocalHistory）：
- pack/unpack 往返（含中文）；错口令拒解；篡改拒收
- merge 去重（缺失补齐、重复跳过）；频道文件名反解
- LocalHistory.export_all（内存∪磁盘）与 merge_in（只补缺，落盘重写）

集成（经服务器）：
- 甲聊天 → 上传 → 服务器落盘 .bin 与 audit 均不含明文
- 同昵称重登（同 uid，模拟换设备）→ 拉取解密 → 本地空历史补齐
- 错口令恢复失败；无备份提示；服务器重启后 blob 仍在
"""
import os
import socket
import threading
import time
from dataclasses import replace

import pytest

import cloud_history as ch
from cloud_history import CloudHistoryError
from client_core import ClientCore, LocalHistory
from config import CFG
from server import Hub, serve as serve_tcp


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def hub(tmp_path):
    wdir = str(tmp_path / "web")
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"), web_files_dir=wdir)
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    time.sleep(0.2)
    yield h, port, stop, tmp_path
    stop.set()
    time.sleep(0.2)


class Collector:
    __test__ = False

    def __init__(self, core: ClientCore) -> None:
        self.events = []
        self._lock = threading.Lock()
        core._on_event = self._on

    def _on(self, ev: dict) -> None:
        with self._lock:
            self.events.append(ev)

    def wait(self, t: str, timeout: float = 5.0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for i, e in enumerate(self.events):
                    if e.get("t") == t and (pred is None or pred(e)):
                        del self.events[i]
                        return e
            time.sleep(0.01)
        return None


def _spawn(port: int, nick: str, tmp_path, sub: str = ""):
    core = ClientCore(host="127.0.0.1", port=port, nick=nick,
                      history_dir=str(tmp_path / f"hist_{nick}{sub}"))
    col = Collector(core)
    core.start()
    w = col.wait("welcome")
    assert w is not None, f"{nick} 未收到 welcome"
    return core, col


# ---------- 单元 ----------

def test_pack_unpack_roundtrip_and_wrong_password():
    channels = {"public": [{"t": "chat", "text": "机密中文消息", "uid": 1, "ts": 1.5}],
                "private:1:2": [{"t": "chat", "text": "私聊", "uid": 2, "ts": 2}]}
    blob = ch.pack(channels, uid=7, nick="甲", password="口令123")
    assert blob.startswith(ch.MAGIC)
    data = ch.unpack(blob, "口令123")
    assert data["uid"] == 7 and data["nick"] == "甲"
    assert data["channels"]["public"][0]["text"] == "机密中文消息"
    with pytest.raises(CloudHistoryError):
        ch.unpack(blob, "错口令")
    bad = bytearray(blob)
    bad[-1] ^= 0xFF
    with pytest.raises(CloudHistoryError):
        ch.unpack(bytes(bad), "口令123")
    with pytest.raises(CloudHistoryError):
        ch.unpack(b"not-a-blob", "口令123")


def test_merge_dedup_and_fill():
    existing = [{"t": "chat", "ts": 1.0, "uid": 1, "text": "a"}]
    incoming = [
        {"t": "chat", "ts": 1.0, "uid": 1, "text": "a"},     # 重复：跳过
        {"t": "chat", "ts": 2.0, "uid": 1, "text": "b"},     # 缺失：补
        {"t": "chat", "ts": "3.5", "uid": 2, "text": "c"},   # 字符串 ts 也判重
    ]
    out = ch.merge(existing, incoming)
    assert [m["text"] for m in out] == ["a", "b", "c"]
    out2 = ch.merge(list(out), list(incoming))               # 再合并不重复
    assert len(out2) == 3


def test_key_from_filename():
    f = LocalHistory._key_from_filename
    assert f("public") == "public"
    assert f("private_1_2") == "private:1:2"
    assert f("e2ee_2_9") == "e2ee:2:9"
    assert f("group_5") == "group:5"
    assert f("") is None
    assert f("unknown_shape") is None                        # 未知形态跳过


def test_export_all_and_merge_in(tmp_path):
    h = LocalHistory(str(tmp_path / "lh"))
    h.add("public", {"t": "chat", "ts": 1.0, "uid": 1, "text": "公聊1"})
    h.add("private:1:2", {"t": "chat", "ts": 2.0, "uid": 2, "text": "私聊1"})
    h.close()
    h2 = LocalHistory(str(tmp_path / "lh"))                  # 模拟重启：纯磁盘
    exported = h2.export_all()
    assert set(exported.keys()) == {"public", "private:1:2"}
    assert exported["public"][0]["text"] == "公聊1"

    # 另一设备历史：合并 → 只补缺
    h3 = LocalHistory(str(tmp_path / "lh"))
    h3.merge_in({"public": [
        {"t": "chat", "ts": 1.0, "uid": 1, "text": "公聊1"},  # 已有
        {"t": "chat", "ts": 3.0, "uid": 1, "text": "公聊2"},  # 新增
    ], "group:4": [{"t": "chat", "ts": 4.0, "uid": 3, "text": "群聊1"}]})
    assert h3.load_disk("public")[-1]["text"] == "公聊2"
    assert len(h3.load_disk("public")) == 2
    assert h3.load_disk("group:4")[0]["text"] == "群聊1"
    h3.close()


# ---------- 集成 ----------

def test_cloud_upload_restore_flow(hub, tmp_path):
    h, port, _stop, _tp = hub
    a, ca = _spawn(port, "甲", tmp_path)
    try:
        # 产生本地历史（公聊 + 密聊）
        a._store_chat({"t": "chat", "channel": "public", "uid": a.uid,
                       "nick": "甲", "text": "云备份暗号XYZ", "seq": 11, "ts": 1.0})
        a._store_chat({"t": "chat", "channel": "e2ee", "uid": a.uid, "to": 2,
                       "nick": "甲", "text": "密聊暗号QWE", "seq": 12, "ts": 2.0})

        ok, msg = a.cloud_upload("口令abc")
        assert ok, msg

        # 服务器落盘 .bin 与 audit 均不含明文
        bin_path = os.path.join(str(tmp_path / "web"), "cloud", f"{a.uid}.bin")
        assert os.path.isfile(bin_path)
        with open(bin_path, "rb") as f:
            raw = f.read()
        assert "云备份暗号XYZ".encode() not in raw
        assert "密聊暗号QWE".encode() not in raw
        audit_dir = str(tmp_path / "audit")
        audit_raw = "".join(
            open(os.path.join(audit_dir, fn), "r", encoding="utf-8",
                 errors="ignore").read()
            for fn in os.listdir(audit_dir))
        assert "云备份暗号XYZ" not in audit_raw

        # 同昵称重登（同 uid）+ 全新历史目录 → 拉取解密恢复
        a.stop()
        time.sleep(0.3)
        b, cb = _spawn(port, "甲", tmp_path, sub="_newdev")
        assert b.uid == a.uid, "同昵称重登应复用 uid"
        assert b._history.load_disk("public") == []
        ok2, msg2 = b.cloud_restore("口令abc")
        assert ok2, msg2
        pub = b._history.load_disk("public")
        assert any(m.get("text") == "云备份暗号XYZ" for m in pub)
        e2 = b._history.load_disk(f"e2ee:{min(a.uid, 2)}:{max(a.uid, 2)}")
        assert any(m.get("text") == "密聊暗号QWE" for m in e2)
        # 再次恢复不重复（去重）
        ok3, msg3 = b.cloud_restore("口令abc")
        assert ok3 and "0 条" in msg3, msg3
        assert len(b._history.load_disk("public")) == len(pub)
        b.stop()
    finally:
        try:
            a.stop()
        except Exception:
            pass


def test_cloud_wrong_password_and_empty(hub, tmp_path):
    h, port, _stop, _tp = hub
    a, _ca = _spawn(port, "乙", tmp_path)
    b, _cb = _spawn(port, "丙", tmp_path)
    try:
        ok, _ = a.cloud_upload("正确口令")
        assert ok
        # 错口令 → 拒解
        a._store_chat({"t": "chat", "channel": "public", "uid": a.uid,
                       "nick": "乙", "text": "some", "seq": 1, "ts": 1.0})
        ok2, msg2 = a.cloud_restore("错误口令")
        assert not ok2 and "解密失败" in msg2, msg2
        # 丙从未上传 → 云端无备份
        ok3, msg3 = b.cloud_restore("任意口令")
        assert not ok3 and "没有" in msg3, msg3
    finally:
        a.stop()
        b.stop()


def test_cloud_server_restart_keeps_blob(hub, tmp_path):
    h, port, stop, _tp = hub
    a, _ca = _spawn(port, "丁", tmp_path)
    try:
        a._store_chat({"t": "chat", "channel": "public", "uid": a.uid,
                       "nick": "丁", "text": "重启暗号", "seq": 1, "ts": 1.0})
        ok, _ = a.cloud_upload("口令xyz")
        assert ok
        assert h.cloud.get(a.uid) is not None
    finally:
        a.stop()
    stop.set()
    time.sleep(0.3)

    # 重启服务器（同 web_files_dir）→ blob 从磁盘恢复
    wdir = str(tmp_path / "web")
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"), web_files_dir=wdir)
    h2 = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    assert a.uid in h2.cloud, "重启后密文 blob 未从磁盘恢复"
    blob = h2.cloud[a.uid]["blob"]
    assert "重启暗号".encode() not in blob           # 服务器仍是密文
    data = ch.unpack(blob, "口令xyz")
    assert data["channels"]["public"][0]["text"] == "重启暗号"
