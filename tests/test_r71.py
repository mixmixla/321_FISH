# -*- coding: utf-8 -*-
"""R71 回归：频道评论区 / 联系人名片 / @handle 别名 / STT 内置化。

覆盖：
- 频道（kind=channel）：非创建者带 thread_root 的评论放行、裸发贴仍 readonly 拒；
  THREAD_FETCH 可取频道评论，非成员被拒（deny）
- 名片：card={uid,nick} 白名单化进 msg["card"]；伪造/多余字段被丢弃；
  非 dict 的 card 被忽略；纯名片消息不触发 empty
- 群慢速：thread_root 回帖豁免慢速，普通发贴仍受档位限制
- @handle：_on_mention_click 的别名 → uid 解析（纯逻辑单测）
- STT：find_model_dir 优先级（prefs > env > _MEIPASS > 用户目录 > 项目目录）
"""
import os
import shutil
import socket
import threading
import time
from dataclasses import replace

import pytest

from config import CFG, MAX_NICK_LEN, STT_MODEL_SUBDIR
from protocol import MsgType
from server import Hub, serve as serve_tcp

import optional


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
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    time.sleep(0.2)
    yield h, port, stop
    stop.set()
    time.sleep(0.2)


class _Cli:
    """原始帧客户端：直发 JSON 头，便于构造名片这类「非正规」负载。"""
    __test__ = False

    def __init__(self, port, nick):
        from crypto import client_handshake
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.chan = client_handshake(self.sock)
        self.nick = nick
        self.uid = None
        self.events = []
        self._lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            while True:
                h, b = self.chan.recv_frame()
                with self._lock:
                    self.events.append((h, b))
        except Exception:
            pass

    def send(self, header, body=b""):
        self.chan.send_frame(header, body)

    def wait(self, t, timeout=3.0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for i, (h, b) in enumerate(self.events):
                    if h.get("t") == t and (pred is None or pred(h)):
                        del self.events[i]
                        return h, b
            time.sleep(0.01)
        return None, None

    def hello(self):
        self.send({"t": "hello", "nick": self.nick})
        h, _ = self.wait("welcome")
        if h:
            self.uid = h["uid"]
        return h

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def _mk_channel(owner, name="📢 公告"):
    """owner 建频道并返回 (gid, 根消息 seq)。"""
    owner.send({"t": "group_create", "name": name, "broadcast": True,
                "public": True})
    gs, _ = owner.wait("group_state", pred=lambda x: x.get("name") == name)
    assert gs, "频道未创建"
    gid = gs["gid"]
    return gid


# ================= 频道评论区 =================

def test_channel_comment_ok_post_blocked(hub):
    """非创建者裸发贴被 readonly 拒；带 thread_root 评论放行。"""
    h, port, _ = hub
    owner, member = _Cli(port, "主播"), _Cli(port, "观众")
    owner.hello(), member.hello()
    gid = _mk_channel(owner)
    assert h.groups[gid]["kind"] == "channel"
    member.send({"t": "group_join", "gid": gid})
    assert member.wait("group_state", pred=lambda x: x.get("gid") == gid)

    # 裸发贴 → readonly（R26B 原语义不破）
    member.send({"t": "chat", "channel": "group", "to": gid, "text": "我要发贴"})
    he, _ = member.wait("error", pred=lambda x: x.get("code") == "readonly")
    assert he and "readonly" == he["code"]

    # 创建者发根贴
    owner.send({"t": "chat", "channel": "group", "to": gid, "text": "正式公告"})
    root, _ = owner.wait("chat", pred=lambda x: x.get("uid") == owner.uid
                         and x.get("text") == "正式公告")
    assert root and root.get("seq")

    # 成员评论（带 thread_root）→ 放行并广播
    member.send({"t": "chat", "channel": "group", "to": gid, "text": "收到",
                 "thread_root": root["seq"]})
    cm, _ = member.wait("chat", pred=lambda x: x.get("thread_root") == root["seq"])
    assert cm and cm.get("uid") == member.uid and cm.get("text") == "收到"
    # 无效 thread_root 仍被 thread 校验拒（豁免只放开只读闸门，不放开校验）
    member.send({"t": "chat", "channel": "group", "to": gid, "text": "越权",
                 "thread_root": 999999})
    he2, _ = member.wait("error", pred=lambda x: x.get("code") == "thread")
    assert he2
    owner.close(), member.close()


def test_channel_thread_fetch_and_permission(hub):
    """频道评论可经 THREAD_FETCH 拉取；非成员被拒（deny）。"""
    h, port, _ = hub
    owner, member, outsider = _Cli(port, "甲"), _Cli(port, "乙"), _Cli(port, "丙")
    owner.hello(), member.hello(), outsider.hello()
    gid = _mk_channel(owner)
    member.send({"t": "group_join", "gid": gid})
    assert member.wait("group_state", pred=lambda x: x.get("gid") == gid)
    owner.send({"t": "chat", "channel": "group", "to": gid, "text": "公告"})
    root, _ = owner.wait("chat", pred=lambda x: x.get("text") == "公告")
    for i in range(2):
        member.send({"t": "chat", "channel": "group", "to": gid,
                     "text": f"评论{i}", "thread_root": root["seq"]})
        assert member.wait("chat", pred=lambda x: x.get("thread_root") == root["seq"])

    member.send({"t": MsgType.THREAD_FETCH.value, "channel": "group",
                 "to": gid, "root_seq": root["seq"]})
    th, _ = member.wait(MsgType.THREAD_HISTORY.value)
    assert th and th.get("root_seq") == root["seq"]
    msgs = th.get("msgs") or []
    assert len(msgs) == 2 and all(m.get("thread_root") == root["seq"] for m in msgs)

    # 非成员拉取频道评论 → deny
    outsider.send({"t": MsgType.THREAD_FETCH.value, "channel": "group",
                   "to": gid, "root_seq": root["seq"]})
    he, _ = outsider.wait("error", pred=lambda x: x.get("code") == "deny")
    assert he
    owner.close(), member.close(), outsider.close()


# ================= 联系人名片（白名单） =================

def test_card_whitelist_and_junk_dropped(hub):
    """纯名片消息合法；只留 uid/nick，伪造/多余字段一律丢弃。"""
    h, port, _ = hub
    a, b = _Cli(port, "甲"), _Cli(port, "乙")
    a.hello(), b.hello()

    # 纯名片（无正文）→ 不被 empty 拒；多余字段被裁剪
    a.send({"t": "chat", "channel": "public",
            "card": {"uid": b.uid, "nick": " 乙 ", "extra": "junk",
                     "__proto__": {"x": 1}}})
    ev, _ = b.wait("chat", pred=lambda x: x.get("card"))
    assert ev, "纯名片消息被拒（empty）"
    assert ev["card"] == {"uid": b.uid, "nick": "乙"}      # 去空格 + 只剩两字段
    assert "text" not in ev

    # uid 为数字字符串 → 归一化为 int
    a.send({"t": "chat", "channel": "public",
            "card": {"uid": str(b.uid), "nick": "乙"}})
    ev2, _ = b.wait("chat", pred=lambda x: x.get("card"))
    assert ev2 and ev2["card"]["uid"] == b.uid

    # 超长昵称 → 截断到 MAX_NICK_LEN
    a.send({"t": "chat", "channel": "public",
            "card": {"uid": b.uid, "nick": "N" * (MAX_NICK_LEN + 20)}})
    ev3, _ = b.wait("chat", pred=lambda x: x.get("card"))
    assert ev3 and len(ev3["card"]["nick"]) == MAX_NICK_LEN

    # 非数字 uid → 整个 card 作废，无正文 → empty
    a.send({"t": "chat", "channel": "public", "card": {"uid": "abc", "nick": "x"}})
    assert a.wait("error", pred=lambda x: x.get("code") == "empty")[0]

    # bool 是 int 子类，须剔除 → 同样 empty
    a.send({"t": "chat", "channel": "public", "card": {"uid": True, "nick": "x"}})
    assert a.wait("error", pred=lambda x: x.get("code") == "empty")[0]

    # 非 dict 的 card 直接忽略（有正文照常发）
    a.send({"t": "chat", "channel": "public", "card": "junk", "text": "普通"})
    ev4, _ = b.wait("chat", pred=lambda x: x.get("text") == "普通")
    assert ev4 and "card" not in ev4

    # 缺 nick → 作废
    a.send({"t": "chat", "channel": "public", "card": {"uid": b.uid}})
    assert a.wait("error", pred=lambda x: x.get("code") == "empty")[0]
    a.close(), b.close()


# ================= 群慢速 × 话题豁免 =================

def test_slow_exempt_for_thread_reply(hub):
    """慢速档位对普通发贴生效，对 thread_root 回帖豁免。"""
    h, port, _ = hub
    owner, member = _Cli(port, "甲"), _Cli(port, "乙")
    owner.hello(), member.hello()
    owner.send({"t": "group_create", "name": "慢速群", "public": True})
    gs, _ = owner.wait("group_state", pred=lambda x: x.get("name") == "慢速群")
    assert gs
    gid = gs["gid"]
    member.send({"t": "group_join", "gid": gid})
    assert member.wait("group_state", pred=lambda x: x.get("gid") == gid)

    owner.send({"t": MsgType.GROUP_SLOW.value, "gid": gid, "seconds": 5})
    assert member.wait("group_state", pred=lambda x: x.get("slow") == 5)

    member.send({"t": "chat", "channel": "group", "to": gid, "text": "第一条"})
    assert member.wait("chat", pred=lambda x: x.get("text") == "第一条")
    member.send({"t": "chat", "channel": "group", "to": gid, "text": "第二条"})
    assert member.wait("error", pred=lambda x: x.get("code") == "slow")

    # owner 发根贴（owner 天然豁免），member 档内回帖 → 豁免放行
    owner.send({"t": "chat", "channel": "group", "to": gid, "text": "根贴"})
    root, _ = owner.wait("chat", pred=lambda x: x.get("text") == "根贴")
    member.send({"t": "chat", "channel": "group", "to": gid, "text": "档内回帖",
                 "thread_root": root["seq"]})
    cm, _ = member.wait("chat", pred=lambda x: x.get("text") == "档内回帖"
                        and x.get("thread_root") == root["seq"])
    assert cm, "话题回帖未豁免慢速"
    owner.close(), member.close()


# ================= @handle 别名解析（纯逻辑） =================

def test_mention_handle_resolution():
    from client import ChatWindow
    switches, cards = [], []
    core = type("C", (), {"uid": 1})()
    core.group_members = {7: [{"nick": "小明", "uid": 5}]}
    s = type("S", (), {"view": ("group", 7), "core": core,
                       "_prefs": {"handles": {"老大": "6", "我": 1}}})()
    s._switch_view = lambda ch, to: switches.append((ch, to))
    s._open_user_card = lambda uid: cards.append(uid)
    clk = ChatWindow._on_mention_click.__get__(s)

    clk("@老大")                       # 别名 → 私聊（字符串 uid 也认）
    assert switches == [("private", 6)]
    s.view = ("public", None)
    clk("@老大")                       # 别名表全局生效（非群会话也跳）
    assert switches == [("private", 6), ("private", 6)]
    clk("@我")                         # 别名指向自己 → 打开个人资料而非私聊
    assert cards == [1] and len(switches) == 2
    clk("@小明")                       # 无别名 + 非群会话 → 不跳
    assert len(switches) == 2

    s.view = ("group", 7)
    clk("@小明")                       # 回到群 → 按成员昵称匹配（R29C 原语义）
    assert switches == [("private", 6), ("private", 6), ("private", 5)]

    s._prefs = {"handles": {"坏": "abc"}}   # 非数字别名作废 → 落回成员匹配（未命中）
    clk("@坏")
    assert len(switches) == 3
    clk("@无人")                       # 未命中 → 不跳
    assert len(switches) == 3


# ================= STT 内置模型定位优先级 =================

def _fake_model(path):
    """造一个「像 vosk 模型」的目录（含 am/final.mdl）。"""
    os.makedirs(os.path.join(str(path), "am"), exist_ok=True)
    with open(os.path.join(str(path), "am", "final.mdl"), "wb") as fh:
        fh.write(b"m")
    return str(path)


def test_find_model_dir_priority(tmp_path, monkeypatch):
    pref = _fake_model(tmp_path / "pref")
    env = _fake_model(tmp_path / "env")
    meipass = tmp_path / "meipass"
    packed = _fake_model(meipass / STT_MODEL_SUBDIR)
    userhome = tmp_path / "userhome"
    _fake_model(userhome / STT_MODEL_SUBDIR)

    monkeypatch.setattr(optional, "_log_dir", lambda: str(userhome))
    monkeypatch.setattr(optional.sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.delattr(optional.sys, "_MEIPASS", raising=False)

    # 1) 仅 env
    monkeypatch.setenv("VOSK_MODEL", env)
    assert optional.find_model_dir() == env
    # 2) prefs 压过 env
    assert optional.find_model_dir(pref_dir=pref) == pref
    # 3) env 压过 _MEIPASS（用户可指向外部模型，绕开 onefile 解包）
    monkeypatch.setattr(optional.sys, "_MEIPASS", str(meipass), raising=False)
    assert optional.find_model_dir() == env
    # 4) 无 env → _MEIPASS 内置模型
    monkeypatch.delenv("VOSK_MODEL", raising=False)
    assert optional.find_model_dir() == packed
    # 5) 无 _MEIPASS → 用户可写目录
    monkeypatch.delattr(optional.sys, "_MEIPASS", raising=False)
    assert optional.find_model_dir() == _fake_model(userhome / STT_MODEL_SUBDIR)
    # 6) 全部落空 → 项目目录（仓库内 models/vosk 为空）→ 空串
    shutil.rmtree(str(userhome / STT_MODEL_SUBDIR))
    assert optional.find_model_dir() == ""