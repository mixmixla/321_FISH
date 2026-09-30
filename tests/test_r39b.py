# -*- coding: utf-8 -*-
"""R39B 云同步会话状态回归。

单元（cloud_history）：
- pack 带 conv_states 段往返；旧结构（无段）打包/解包兼容
- merge_conv_states：ts 新者胜、相等/无 ts 保留本地、单边键纳入、坏值跳过

客户端采集/应用（ChatWindow 打桩实例）：
- _collect_conv_states：已读游标/未读/草稿/置顶/归档/静音聚合
- _apply_conv_states：ts 新者胜；已读游标只前进；当前会话未读不动；
  草稿按 ts 覆盖/清除；pin/mute/archive 差异翻转并写 prefs

集成（经服务器）：
- 甲带钩子上传（含状态段）→ 换设备恢复 → 应用钩子收到状态、提示含「会话状态」
- 无钩子（旧客户端语义）上传 → 有钩子恢复 → 不应用状态、不崩
"""
import os
import socket
import threading
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

import cloud_history as ch
from client_core import ClientCore
from client import ChatWindow
from config import CFG
from prefs import Prefs
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


# ---------- 单元：cloud_history ----------

def test_pack_roundtrip_with_conv_states():
    channels = {"public": [{"t": "chat", "text": "hi", "uid": 1, "ts": 1.0}]}
    states = {"private:1:2": {"ts": 99.0, "read": 5, "unread": 0,
                              "draft": "", "pin": True, "muted": False,
                              "archived": False}}
    blob = ch.pack(channels, uid=7, nick="甲", password="p",
                   conv_states=states)
    data = ch.unpack(blob, "p")
    assert data["conv_states"] == states
    assert data["channels"]["public"][0]["text"] == "hi"


def test_old_blob_compat_no_states():
    channels = {"public": [{"t": "chat", "text": "旧结构", "uid": 1, "ts": 1.0}]}
    blob = ch.pack(channels, uid=7, nick="甲", password="p")   # 不带状态段
    data = ch.unpack(blob, "p")
    assert data["conv_states"] == {}                            # 解包视为空
    blob2 = ch.pack(channels, uid=7, nick="甲", password="p",
                    conv_states={})                             # 空段同样不写入
    assert ch.unpack(blob2, "p")["conv_states"] == {}


def test_merge_conv_states_new_wins():
    local = {"a": {"ts": 10.0, "read": 1}, "b": {"ts": 5.0, "read": 2}}
    incoming = {"a": {"ts": 20.0, "read": 9},                # 新 → 胜
                "b": {"ts": 5.0, "read": 8},                 # 相等 → 本地保留
                "c": {"read": 7},                            # 无 ts → 纳入
                "d": "bad",                                  # 非 dict → 跳过
                }
    out = ch.merge_conv_states(local, incoming)
    assert out["a"]["read"] == 9
    assert out["b"]["read"] == 2
    assert out["c"] == {"read": 7}
    assert "d" not in out
    older = {"a": {"ts": 1.0, "read": 0}}
    assert ch.merge_conv_states(out, older)["a"]["read"] == 9   # 旧 → 保留


# ---------- 单元：客户端采集/应用（打桩实例，不建 Tk） ----------

def _stub_app(tmp_path):
    app = ChatWindow.__new__(ChatWindow)
    app.core = SimpleNamespace(uid=1)
    app._prefs = Prefs(str(tmp_path / "prefs.json"))
    app._last_read = {}
    app._unread = {}
    app._drafts = {}
    app._draft_ts = {}
    app._conv_state_ts = {}
    app._refresh_lists = lambda: None
    app._refresh_archived = lambda: None
    app._persist_drafts = lambda: None
    return app


def test_client_collect_conv_states(tmp_path):
    app = _stub_app(tmp_path)
    app._last_read = {"private:1:2": 42}
    app._unread = {("private", 2): 3, ("group", 7): 1}
    app._drafts = {"public": "未发完的"}
    app._draft_ts = {"public": 100.0}
    app._conv_state_ts = {"private:1:2": 200.0}
    app._prefs.toggle_pin("group:7")
    states = app._collect_conv_states()
    assert states["private:1:2"] == {"ts": 200.0, "read": 42, "unread": 3,
                                     "draft": "", "pin": False,
                                     "muted": False, "archived": False}
    assert states["public"]["draft"] == "未发完的"
    assert states["public"]["ts"] == 100.0
    assert states["group:7"]["pin"] is True
    assert states["group:7"]["unread"] == 1


def test_client_apply_conv_states(tmp_path):
    app = _stub_app(tmp_path)
    app._hist_key = lambda: "group:9"          # 当前正在看的会话
    st_new = {"ts": 300.0, "read": 7, "unread": 2, "draft": "云端草稿",
              "pin": True, "muted": True, "archived": False}
    app._apply_conv_states({"public": st_new})
    assert app._last_read["public"] == 7
    assert app._unread[("public", None)] == 2
    assert app._drafts["public"] == "云端草稿"
    assert app._draft_ts["public"] == 300.0
    assert app._prefs.is_pinned("public") and app._prefs.is_muted("public")
    assert not app._prefs.is_archived("public")
    assert app._conv_state_ts["public"] == 300.0

    # 已读游标只前进：更新的 ts 但更小的 read 不回滚
    app._apply_conv_states({"public": {"ts": 400.0, "read": 3, "unread": 0,
                                       "draft": "", "pin": True,
                                       "muted": True, "archived": False}})
    assert app._last_read["public"] == 7
    assert "public" not in app._drafts          # 空草稿 = 清除
    assert ("public", None) not in app._unread  # unread=0 清未读

    # 旧 ts 不覆盖本地新状态
    app._conv_state_ts["public"] = 999.0
    app._apply_conv_states({"public": {"ts": 500.0, "read": 99, "unread": 5,
                                       "draft": "x", "pin": False,
                                       "muted": False, "archived": True}})
    assert app._last_read["public"] == 7
    assert app._prefs.is_pinned("public")

    # 当前会话（group:9）的未读不被云端改写
    app._unread[("group", 9)] = 4
    app._apply_conv_states({"group:9": {"ts": 2000.0, "read": 1, "unread": 0,
                                        "draft": "", "pin": False,
                                        "muted": False, "archived": False}})
    assert app._unread[("group", 9)] == 4


# ---------- 集成：经服务器 ----------

def test_cloud_states_upload_restore_flow(hub, tmp_path):
    _h, port, _stop, _tp = hub
    a, _ca = _spawn(port, "甲", tmp_path)
    try:
        a._store_chat({"t": "chat", "channel": "public", "uid": a.uid,
                       "nick": "甲", "text": "R39B消息", "seq": 11, "ts": 1.0})
        a.set_conv_state_hooks(
            lambda: {"public": {"ts": 123.0, "read": 11, "unread": 0,
                                "draft": "甲的草稿", "pin": True,
                                "muted": False, "archived": False}},
            lambda states: None)
        ok, msg = a.cloud_upload("口令r39b")
        assert ok, msg

        a.stop()
        time.sleep(0.3)
        b, _cb = _spawn(port, "甲", tmp_path, sub="_dev2")
        applied = []
        b.set_conv_state_hooks(lambda: {}, applied.append)
        ok2, msg2 = b.cloud_restore("口令r39b")
        assert ok2, msg2
        assert "会话状态" in msg2, msg2
        assert len(applied) == 1
        assert applied[0]["public"]["draft"] == "甲的草稿"
        assert applied[0]["public"]["read"] == 11
        b.stop()
    finally:
        try:
            a.stop()
        except Exception:
            pass


def test_cloud_states_old_uploader_new_restorer(hub, tmp_path):
    _h, port, _stop, _tp = hub
    a, _ca = _spawn(port, "乙", tmp_path)      # 无钩子 = 旧客户端语义
    try:
        a._store_chat({"t": "chat", "channel": "public", "uid": a.uid,
                       "nick": "乙", "text": "旧打包", "seq": 1, "ts": 1.0})
        ok, msg = a.cloud_upload("口令old")
        assert ok, msg

        a.stop()
        time.sleep(0.3)
        b, _cb = _spawn(port, "乙", tmp_path, sub="_dev2")
        applied = []
        b.set_conv_state_hooks(lambda: {}, applied.append)
        ok2, msg2 = b.cloud_restore("口令old")
        assert ok2, msg2
        assert "会话状态" not in msg2            # 旧 blob 无状态段 → 不应用
        assert applied == []
        assert any(m.get("text") == "旧打包"
                   for m in b._history.load_disk("public"))
        b.stop()
    finally:
        try:
            a.stop()
        except Exception:
            pass
