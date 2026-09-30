# -*- coding: utf-8 -*-
"""R25 第一梯队四件套回归：typing 正在输入（A）、在线/最后上线（B）、
收藏夹发给自己（C）、会话文件夹（D，prefs 层）。

e2e 用真 socket + 真 Hub（127.0.0.1 随机端口），与 test_client_core.py 同款夹具；
prefs/限速类用纯单元断言。
"""
import socket
import threading
import time
from dataclasses import replace

import pytest

from config import CFG
from server import Hub, serve as serve_tcp
from client_core import ClientCore
from prefs import Prefs


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def hub(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"))
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False), daemon=True).start()
    time.sleep(0.1)
    yield h, port, stop
    stop.set()
    time.sleep(0.2)


class Collector:
    """on_event 收集器：wait 匹配即移除（与 TestClient.wait 同语义）。"""
    __test__ = False

    def __init__(self, core: ClientCore) -> None:
        self.events = []
        self._lock = threading.Lock()
        core._on_event = self._on

    def _on(self, ev: dict) -> None:
        with self._lock:
            self.events.append(ev)

    def wait(self, t: str, timeout: float = 3.0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for i, e in enumerate(self.events):
                    if e.get("t") == t and (pred is None or pred(e)):
                        del self.events[i]
                        return e
            time.sleep(0.01)
        return None

    def has(self, t: str, pred=None) -> bool:
        with self._lock:
            return any(e.get("t") == t and (pred is None or pred(e))
                       for e in self.events)


def _make_core(port: int, nick: str, tmp_path, **kw):
    kw.setdefault("heartbeat_interval", 0.1)
    kw.setdefault("heartbeat_timeout", 0.8)
    kw.setdefault("reconnect_base", 0.05)
    kw.setdefault("reconnect_max", 0.3)
    hist_dir = kw.pop("history_dir", str(tmp_path / f"hist_{nick}"))
    return ClientCore(host="127.0.0.1", port=port, nick=nick,
                      history_dir=hist_dir, **kw)


def _spawn(port: int, nick: str, tmp_path):
    core = _make_core(port, nick, tmp_path)
    col = Collector(core)
    core.start()
    w = col.wait("welcome")
    assert w is not None, f"{nick} 未收到 welcome"
    return core, col


def _online(col, timeout: float = 3.0):
    return col.wait("state", timeout=timeout,
                    pred=lambda e: e.get("state") == "online")


# ---------- R25A 正在输入 ----------
def test_typing_broadcast_to_recipients_not_sender(hub, tmp_path):
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_typing("public")
        got = bc.wait("typing", pred=lambda e: e.get("nick") == "alice")
        assert got and got["channel"] == "public" and got["uid"] == a.uid
        assert not ac.has("typing")            # 服务器不回传给自己
    finally:
        a.stop(); b.stop()


def test_typing_private_only_peer(hub, tmp_path):
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    c3, cc = _spawn(port, "charlie", tmp_path)
    try:
        assert _online(ac) and _online(bc) and _online(cc)
        assert a.send_typing("private", b.uid)
        got = bc.wait("typing", pred=lambda e: e.get("channel") == "private"
                       and e.get("to") == b.uid)
        assert got and got["uid"] == a.uid
        assert not cc.has("typing")            # 第三方收不到
    finally:
        a.stop(); b.stop(); c3.stop()


def test_typing_server_rate_limit(hub, tmp_path):
    """服务器 1s/人 限速：同一 uid 连续两帧只转发第一帧。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        # 绕过客户端限速直接发原始帧，验证服务器侧限速
        a._send_frame({"t": "typing", "channel": "public"})
        a._send_frame({"t": "typing", "channel": "public"})
        time.sleep(0.3)
        with bc._lock:
            n = sum(1 for e in bc.events if e.get("t") == "typing")
        assert n <= 1                          # 服务器限速：至多一帧
    finally:
        a.stop(); b.stop()


def test_typing_for_ttl_expiry():
    """客户端 typing 表：过期条目惰性清除，typing_for 返回存活昵称。"""
    core = ClientCore(host="127.0.0.1", port=1, nick="t")
    core.uid = 7
    core._on_typing({"t": "typing", "channel": "private", "uid": 3,
                     "to": 7, "nick": "bob", "ts": time.time()})
    assert core.typing_for("private:3:7") == ["bob"]
    # 过期：伪造旧时间戳 → 应清空并返回空
    core.typing["private:3:7"][3]["ts"] = time.time() - 10
    assert core.typing_for("private:3:7") == []
    assert "private:3:7" not in core.typing    # 惰性清除


def test_send_typing_local_rate_limit(tmp_path):
    """客户端 send_typing 本地 1s/人 限速。"""
    core = ClientCore(host="127.0.0.1", port=1, nick="t",
                      history_dir=str(tmp_path / "h"))
    core._send_frame = lambda h, body=b"": True   # 免网络直判
    assert core.send_typing("public") is True
    assert core.send_typing("public") is False    # 1s 内第二帧被限速


# ---------- R25B 在线 / 最后上线 ----------
def test_known_last_online_after_disconnect(hub, tmp_path):
    """断线后服务器 known 记录 last_online，且 roster 广播带全量 known。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        bob_uid = b.uid
        b.stop()                               # bob 下线
        ev = ac.wait("roster", pred=lambda e: bob_uid not in
                     [u["uid"] for u in e.get("online", [])]
                     and bob_uid in [u["uid"] for u in e.get("known", [])])
        assert ev is not None
        known = {u["uid"]: u for u in ev.get("known", [])}
        assert bob_uid in known and known[bob_uid]["last_online"] > 0
        # 客户端 known 实时同步（无需重连）
        assert bob_uid in a.known and a.known[bob_uid]["last_online"] > 0
    finally:
        a.stop(); b.stop()


def test_welcome_known_includes_offline(hub, tmp_path):
    """后到的客户端 welcome 自带 known（含离线用户与最后上线）。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        bob_uid = b.uid
        b.stop()                               # bob 先下线
        time.sleep(0.3)
        c3, cc = _spawn(port, "charlie", tmp_path)
        assert _online(cc)
        assert a.uid in c3.known and c3.known[a.uid]["last_online"] == 0   # 在线用户
        assert bob_uid in c3.known and c3.known[bob_uid]["last_online"] > 0  # 离线最后上线
    finally:
        a.stop(); c3.stop()


# ---------- R25C 收藏夹（发给自己） ----------
def test_saved_message_send_to_self(hub, tmp_path):
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    try:
        assert _online(ac)
        assert a.send_chat("待办：写周报", channel="private", to=a.uid)
        got = ac.wait("chat", pred=lambda e: e.get("channel") == "private"
                      and e.get("to") == a.uid and e.get("text") == "待办：写周报")
        assert got and got["uid"] == a.uid
        # 本地历史落 private:uid:uid
        assert any(m.get("text") == "待办：写周报" for m in a.history("private", a.uid))
    finally:
        a.stop()


def test_saved_isolation_from_other_client(hub, tmp_path):
    """收藏夹历史只在本人 welcome 的 saved 里，他端不可见。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    try:
        assert _online(ac)
        a.send_chat("私藏笔记", channel="private", to=a.uid)
        ac.wait("chat", pred=lambda e: e.get("text") == "私藏笔记")
        b, bc = _spawn(port, "bob", tmp_path)
        assert _online(bc)
        assert not any(m.get("text") == "私藏笔记" for m in b.history("private", b.uid))
        assert not bc.has("chat")
    finally:
        a.stop(); b.stop()


# ---------- R25D 会话文件夹（prefs 层） ----------
def test_folders_roundtrip(tmp_path):
    p = Prefs(str(tmp_path / "prefs.json"))
    p.set_folders([{"name": "工作", "keys": ["private:1:2", "group:3"]},
                   {"name": "生活", "keys": []}])
    p2 = Prefs(str(tmp_path / "prefs.json"))       # 重新加载
    assert p2.folders() == [{"name": "工作", "keys": ["private:1:2", "group:3"]},
                            {"name": "生活", "keys": []}]


def test_folders_bad_data_tolerated(tmp_path):
    p = Prefs(str(tmp_path / "prefs.json"))
    p.set("folders", [{"name": "ok", "keys": ["public"]},
                      "not-dict",
                      {"name": "", "keys": []},
                      {"name": "no-keys"}])
    assert p.folders() == [{"name": "ok", "keys": ["public"]},
                           {"name": "no-keys", "keys": []}]


# ---------- R25 GUI 冒烟（文件夹过滤 + 收藏夹行 + 在线点 + typing 标题） ----------
def test_gui_smoke_r25(hub, tmp_path):
    import tkinter as tk
    try:
        r0 = tk.Tk()
        r0.destroy()
    except tk.TclError as exc:
        pytest.skip(f"无可用 Tk 显示环境: {exc}")
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        from client import ChatWindow
        win = ChatWindow(a, prefs_path=str(tmp_path / "prefs.json"))
        try:
            win.root.update_idletasks()
            win.root.update()
            win._refresh_lists()               # welcome 事件已被收集器消费，手动灌名单
            # 收藏夹（自己）置顶行；bob 在线带绿点
            names = [it.get("name") for it in win.roster_list._items]
            assert names and names[0] == "收藏夹"
            bob_row = next(it for it in win.roster_list._items
                           if it.get("key") == win._pin_key("private", b.uid))
            assert bob_row["status"] == "online"
            # 会话文件夹：建组 → 切换过滤 → 恢复全部
            lo, hi = sorted((a.uid, b.uid))
            key = f"private:{lo}:{hi}"
            win._prefs.set_folders([{"name": "工作", "keys": [key]}])
            win._rebuild_folder_bar()
            win._set_active_folder("工作")
            assert [it.get("key") for it in win.roster_list._items] == [key]
            win._set_active_folder(None)
            assert len(win.roster_list._items) >= 2
            # 对方正在输入 → 标题追加「正在输入…」
            a.typing.setdefault(key, {})[a.uid] = {"nick": "alice", "ts": time.time()}
            win._switch_view("private", b.uid)
            assert "正在输入" in win.chan_label.cget("text")
        finally:
            try:
                win.root.destroy()
            except tk.TclError:
                pass
    finally:
        a.stop(); b.stop()
