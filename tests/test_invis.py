# -*- coding: utf-8 -*-
"""R56 隐身上线回归：服务器权威持久，对非管理员/非本人隐藏。

- 关闭隐身：所有人（含普通用户）都能在名单里看到我；
- 开启隐身：普通用户名单隐藏我，本人名单仍可见，管理员名单仍可见；
- INV_SET 无权限要求（任何已登录用户可开），回帧 invis_ack 反馈 on；
- 隐身持久：known 落盘，重连 welcome 的 invisible 字段带回。
"""
import time
import socket
import threading
from dataclasses import replace

import pytest

from config import CFG
from protocol import MsgType
from test_r53 import _Sess  # 真实 hello 登录


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def hub(tmp_path):
    from server import Hub, serve as serve_tcp
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"))
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    time.sleep(0.2)
    yield h, port, stop
    stop.set()
    time.sleep(0.1)


def _names(entries) -> set:
    return {e["uid"] for e in entries}


def test_invis_hides_from_normal_users(hub):
    h, _w, _ = hub
    stamp = str(int(time.time() % 100000))
    a = _Sess(h, "甲A" + stamp)          # 隐身者
    b = _Sess(h, "乙B" + stamp)          # 普通用户
    adm = _Sess(h, "L57", "L57")         # 管理员
    assert a.uid and b.uid and adm.is_admin

    # 未隐身：普通用户 b 能看到甲（甲在线的会话名单位含 a.uid）
    rb = {u["uid"] for u in h._roster(b.uid)}
    assert a.uid in rb

    # 开启隐身
    h.dispatch(a, {"t": MsgType.INV_SET.value, "on": True})
    assert h._is_invisible(a.uid) is True
    # 回帧确认
    assert a.last_frame("invis_ack") == {"t": "invis_ack", "on": True}

    # 普通用户 b 的名单不再含甲
    rb2 = {u["uid"] for u in h._roster(b.uid)}
    assert a.uid not in rb2
    rb2k = {u["uid"] for u in h._known_list(b.uid)}
    assert a.uid not in rb2k

    # 本人名单仍可见
    ra = {u["uid"] for u in h._roster(a.uid)}
    assert a.uid in ra

    # 管理员名单仍可见
    radm = {u["uid"] for u in h._roster(adm.uid)}
    assert a.uid in radm

    # 关闭隐身 → 恢复可见
    h.dispatch(a, {"t": MsgType.INV_SET.value, "on": False})
    assert a.last_frame("invis_ack") == {"t": "invis_ack", "on": False}
    rb3 = {u["uid"] for u in h._roster(b.uid)}
    assert a.uid in rb3


def test_invis_yields_welcome_flag(hub):
    """welcome 携带 invisible 初始态 + 重连持久（_attach 不丢隐身）。"""
    h, _w, _ = hub
    stamp = str(int(time.time() % 100000))
    a = _Sess(h, "丙C" + stamp)
    # 开启隐身后断开（模拟掉线/重连）
    h.dispatch(a, {"t": MsgType.INV_SET.value, "on": True})
    with h.lock:
        del h.sessions[a.uid]               # 不是注销，nick_to_uid 保留 → 重连复用 uid
    b = _Sess(h, "丙C" + stamp)             # 同名重连
    assert b.uid == a.uid                   # 复用原 uid
    w = b.last_frame("welcome")
    assert w is not None
    assert w.get("invisible") is True
    assert h._is_invisible(a.uid) is True


def test_admin_force_invis(hub):
    """R56B：管理员强制显身/隐身（非管理员被拒；roster 携带 invisible 标记）。"""
    h, _w, _ = hub
    stamp = str(int(time.time()) % 100000)
    a = _Sess(h, "丁D" + stamp)          # 普通用户
    b = _Sess(h, "戊E" + stamp)          # 普通用户
    adm = _Sess(h, "L57", "L57")         # 管理员

    # 非管理员调用 → forbid，状态不变
    h.dispatch(a, {"t": MsgType.ADMIN_INVIS_SET.value,
                   "uid": b.uid, "on": True})
    assert any(f.get("code") == "forbid" for f in a.errors())
    assert h._is_invisible(b.uid) is False

    # 管理员强制 b 隐身 → 生效，b 本人收到 invis_ack
    h.dispatch(adm, {"t": MsgType.ADMIN_INVIS_SET.value,
                     "uid": b.uid, "on": True})
    assert h._is_invisible(b.uid) is True
    assert b.last_frame("invis_ack") == {"t": "invis_ack", "on": True}
    # 审计落盘
    rows = h.audit.recent(limit=50, type_prefix="admin")
    assert any(r.get("type") == "admin_force_invis" and
               r.get("target") == b.uid and r.get("on") is True for r in rows)

    # 普通用户 a 名单隐藏 b；管理员名单可见且带 invisible 标记
    assert b.uid not in {u["uid"] for u in h._roster(a.uid)}
    radm = {u["uid"]: u for u in h._roster(adm.uid)}
    assert b.uid in radm and radm[b.uid]["invisible"] is True

    # 管理员强制恢复显身
    h.dispatch(adm, {"t": MsgType.ADMIN_INVIS_SET.value,
                     "uid": b.uid, "on": False})
    assert h._is_invisible(b.uid) is False
    assert b.uid in {u["uid"] for u in h._roster(a.uid)}


def test_group_member_roster_marks_invisible(hub):
    """R57：群成员花名册（group_state 广播 + group_detail）携带 invisible 标记，
    供管理员识别，也供普通成员按开关可选隐藏隐身上线者。"""
    from test_admin_groups import make_group
    h, _w, _ = hub
    stamp = str(int(time.time() % 100000))
    nick = "隐甲" + stamp
    a = _Sess(h, nick)                        # 隐身者（群成员，在线）
    make_group(h, 51, "联动群", owner=a.uid, nick=nick,
               members={a.uid: nick, 6: "乙"})
    h.dispatch(a, {"t": MsgType.INV_SET.value, "on": True})   # 开启隐身

    # 广播给成员的 group_state 花名册带标记（桌面端 core.group_members 消费）
    h._send_group_state(51)
    gs = a.last_frame("group_state")
    assert gs is not None
    m2 = next(x for x in gs["members"] if x["uid"] == a.uid)
    assert m2["invisible"] is True

    # group_detail（普通成员/管理员同构视图也带标记，供可选隐藏）
    detail = h.group_detail(51, 6)
    assert detail is not None
    m = next(x for x in detail["members"] if x["uid"] == a.uid)
    assert m["invisible"] is True

    # 离线 known 名单：非管理员视角仍强制隐藏隐身者（联动核查，不泄露）
    assert a.uid not in {u["uid"] for u in h._known_list(6)}