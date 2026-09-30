# -*- coding: utf-8 -*-
"""R69 升级包测试：A1 多套伪装皮肤 + A3 摸鱼报告（纯函数）。"""
import tkinter as tk

import pytest

from config import BOSS_SKINS, BOSS_SKIN_LABELS, BOSS_SKIN_TITLES
from prefs import fish_add_day, fish_summary


# ---------- A1：多套伪装皮肤 ----------
@pytest.fixture(scope="module")
def root():
    try:
        r = tk.Tk()
    except tk.TclError:                       # pragma: no cover - 无显示环境
        pytest.skip("no display")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except Exception:
        pass


def test_boss_skins_registered():
    """五套皮肤都要有中文标签与标题池。"""
    assert BOSS_SKINS == ("excel", "vscode", "terminal", "ppt", "mail")
    for sk in BOSS_SKINS:
        assert BOSS_SKIN_LABELS.get(sk)
        assert BOSS_SKIN_TITLES.get(sk)


def test_boss_window_builds_every_skin(root):
    """每套皮肤都能构建出内容区（不抛异常），且标题取自该皮肤标题池。"""
    from boss import BossWindow
    b = BossWindow(root, skin="excel")
    try:
        assert b.skin == "excel"
        for sk in BOSS_SKINS:
            b.set_skin(sk)
            assert b.skin == sk
            assert b.win.title() in BOSS_SKIN_TITLES[sk]
            assert b._tick_fn is not None
        b.close()
    finally:
        try:
            b.close()
        except Exception:
            pass


def test_boss_window_cycle_wraps_and_reports(root):
    """cycle() 依次轮换并在末尾回到首套；回调收到新皮肤键。"""
    from boss import BossWindow
    seen = []
    b = BossWindow(root, skin="excel", on_cycle=seen.append)
    try:
        order = [b.cycle() for _ in range(len(BOSS_SKINS))]
        assert order == list(BOSS_SKINS[1:]) + [BOSS_SKINS[0]]
        assert seen == order
    finally:
        b.close()


def test_boss_window_bad_skin_falls_back(root):
    """非法皮肤名回落首套，不抛异常。"""
    from boss import BossWindow
    b = BossWindow(root, skin="not-a-skin")
    try:
        assert b.skin == BOSS_SKINS[0]
        b.set_skin("still-bad")
        assert b.skin == BOSS_SKINS[0]
    finally:
        b.close()


# ---------- A3：摸鱼报告（纯函数） ----------
def test_fish_add_day_accumulates_same_day():
    d = fish_add_day({}, "2026-09-26", sec=10.0, games=1, msgs=2)
    d = fish_add_day(d, "2026-09-26", sec=5.5, games=1, msgs=3)
    assert d["2026-09-26"] == {"sec": 15.5, "games": 2, "msgs": 5}


def test_fish_add_day_does_not_mutate_input():
    src = {}
    fish_add_day(src, "2026-09-26", sec=1.0)
    assert src == {}


def test_fish_add_day_tolerates_bad_records():
    d = fish_add_day({"2026-09-26": "garbage"}, "2026-09-26", sec=3.0, msgs=1)
    assert d["2026-09-26"]["sec"] == 3.0
    assert d["2026-09-26"]["msgs"] == 1


def test_fish_add_day_trims_to_keep_window():
    days = {f"2026-08-{i:02d}": {"sec": 1.0, "games": 0, "msgs": 0}
            for i in range(1, 10)}
    days = fish_add_day(days, "2026-09-26", sec=2.0, keep=5)
    assert len(days) == 5
    assert "2026-09-26" in days               # 最新一天必然保留
    assert "2026-08-01" not in days            # 最旧一天被裁掉


def test_fish_summary_today_and_week():
    days = {
        "2026-09-20": {"sec": 60.0, "games": 1, "msgs": 10},
        "2026-09-25": {"sec": 120.0, "games": 2, "msgs": 20},
        "2026-09-26": {"sec": 30.0, "games": 1, "msgs": 5},
    }
    rep = fish_summary(days, "2026-09-26", window=7)
    assert rep["today"] == {"sec": 30.0, "games": 1, "msgs": 5}
    assert rep["week"] == {"sec": 210.0, "games": 4, "msgs": 35}
    assert rep["week_days"] == 3


def test_fish_summary_empty_is_zero():
    rep = fish_summary({}, "2026-09-26", window=7)
    assert rep["today"] == {"sec": 0, "games": 0, "msgs": 0}
    assert rep["week"] == {"sec": 0, "games": 0, "msgs": 0}
    assert rep["week_days"] == 0


def test_fish_summary_window_limits_days():
    days = {f"2026-09-{i:02d}": {"sec": 10.0, "games": 0, "msgs": 0}
            for i in range(1, 11)}
    rep = fish_summary(days, "2026-09-10", window=3)
    assert rep["week_days"] == 3
    assert rep["week"]["sec"] == 30.0


# ---------- C10：用户资料卡（桌面消息头像点击接线） ----------
def test_msg_avatar_binds_profile_callback(root):
    """R69C10：点他人消息头像 → on_profile(uid)；头像 item 带 r69c10_ 标签。"""
    from widgets.msg_list import MsgList
    seen = []
    ml = MsgList(root, ("TkDefaultFont", 10), on_profile=seen.append)
    ml.configure(width=400, height=300)
    ml.pack(fill="both", expand=True)
    root.deiconify()                 # 事件投递要求窗口已映射（withdraw 下会被丢弃）
    root.update_idletasks()
    root.update()
    try:
        ml.set_me_uid(2)
        ml.append({"uid": 7, "nick": "资料甲", "channel": "public",
                   "ts": 1.0, "text": "你好"})
        ml._delete_items()
        y = 0
        for i, row in enumerate(ml._rows):
            y += ml._draw_row(i, row, y, 400)
        ml.configure(scrollregion=(0, 0, 400, y))    # 视口回到顶部，头像才可命中
        ml.yview_moveto(0.0)
        root.update()
        oval = next(it for it in ml._item_ids if ml.type(it) == "oval")
        tags = [t for t in ml.gettags(oval) if t.startswith("r69c10_")]
        assert tags, "头像未打上资料卡标签"
        assert ml.tag_bind(tags[0], "<Button-1>"), "头像未绑定 Button-1"
        x0, y0, x1, y1 = ml.bbox(oval)
        off = ml.canvasy(0)
        ml.event_generate("<Button-1>", x=int((x0 + x1) / 2),
                          y=int((y0 + y1) / 2 - off))
        root.update()
        assert seen == [7]
    finally:
        ml.destroy()
        root.withdraw()


def test_msg_avatar_without_callback_still_renders(root):
    """未传 on_profile 时照常画头像且不打标签（如实降级）。"""
    from widgets.msg_list import MsgList
    ml = MsgList(root, ("TkDefaultFont", 10))
    ml.configure(width=400, height=300)
    ml.pack(fill="both", expand=True)
    root.update_idletasks()
    root.update()
    try:
        ml.append({"uid": 7, "nick": "资料甲", "channel": "public",
                   "ts": 1.0, "text": "你好"})
        ml._delete_items()
        y = 0
        for i, row in enumerate(ml._rows):
            y += ml._draw_row(i, row, y, 400)
        ovals = [it for it in ml._item_ids if ml.type(it) == "oval"]
        assert ovals
        assert not any(ml.gettags(it) and
                       any(t.startswith("r69c10_") for t in ml.gettags(it))
                       for it in ovals)
    finally:
        ml.destroy()


# ---------- C11：标为未读 + 稍后处理清单 ----------
def test_prefs_unread_mark_roundtrip(tmp_path):
    """prefs 标为未读：toggle/set 幂等 + 落盘后可重载。"""
    from prefs import Prefs
    p = tmp_path / "prefs.json"
    pf = Prefs(str(p))
    assert pf.unread_marks() == []
    assert pf.toggle_unread_mark("group:7") is True
    assert pf.is_unread_mark("group:7")
    assert pf.toggle_unread_mark("group:7") is False
    assert not pf.is_unread_mark("group:7")
    assert pf.set_unread_mark("private:1:2", True) is True
    assert pf.set_unread_mark("private:1:2", True) is True     # 重复设置不重复入列
    assert pf.unread_marks().count("private:1:2") == 1
    again = Prefs(str(p))                                       # 模拟重启
    assert again.unread_marks() == ["private:1:2"]


def test_session_list_mark_unread_dot(root):
    """R69C11：标记会话在名称前画 accent 圆点；有数字角标时不重复画。"""
    from widgets.session_list import SessionList
    sl = SessionList(root, ("TkDefaultFont", 10))
    sl.configure(width=260, height=120)
    sl.pack(fill="both", expand=True)
    root.update_idletasks()
    root.update()
    accent = sl._pal["accent"]
    try:
        sl.set_items([{"key": "private:1:2", "name": "甲",
                       "mark_unread": True, "unread": 0, "ts": 0}])
        root.update()
        dots = [it for it in sl.find_all()
                if sl.type(it) == "oval" and sl.itemcget(it, "fill") == accent]
        assert len(dots) == 1, "未画/多画了未读标记圆点"
        assert abs(sl.bbox(dots[0])[0] - (sl._TEXT_L + 2)) < 2
        sl.set_items([{"key": "private:1:2", "name": "甲",
                       "mark_unread": True, "unread": 3, "ts": 0}])
        root.update()
        dots2 = [it for it in sl.find_all()
                 if sl.type(it) == "oval" and sl.itemcget(it, "fill") == accent]
        assert not dots2, "已有数字角标时不该再画蓝点"
        sl.set_items([{"key": "private:1:2", "name": "甲",
                       "mark_unread": False, "unread": 0, "ts": 0}])
        root.update()
        dots3 = [it for it in sl.find_all()
                 if sl.type(it) == "oval" and sl.itemcget(it, "fill") == accent]
        assert not dots3
    finally:
        sl.destroy()


def test_snooze_panel_lists_and_clears(root):
    """R69C11：稍后处理面板列出标记项；「已处理」回调清除对应 key。"""
    from widgets.stars_panel import SnoozePanel
    cleared = []
    marks = [{"key": "group:7", "label": "研发群(5)", "preview": "下午对齐"},
             {"key": "private:1:2", "label": "老王", "preview": "在吗"}]
    panel = SnoozePanel(root, marks, lambda k: None, on_clear=cleared.append)
    root.update_idletasks()
    try:
        assert panel.listbox.size() == 2
        assert "研发群(5)" in panel.listbox.get(0)
        panel.listbox.selection_set(0)
        panel._on_clear_sel()
        assert cleared == ["group:7"]
        assert panel.listbox.size() == 1
        assert "老王" in panel.listbox.get(0)
    finally:
        panel.destroy()


def test_web_page_has_unread_marks_wiring():
    """R69C11 网页端：本地标记 + 圆点 + 稍后处理面板接线齐全。"""
    from web import PAGE
    for token in ("function loadMarks()", "function saveMarks()", "function isMarked(",
                  "function toggleMark(", "function unmarkConvo(",
                  "function renderMarkPanel()", "function toggleMarkPanel()",
                  "function markLabel(", "function gotoConvKey(",
                  "id=\"marksec\"", ".umark{", ".mkbtn{",
                  "state.marks=loadMarks();",
                  "unmarkConvo(convKey(c.type,"):
        assert token in PAGE, "网页端缺少 C11 接线：" + token


def test_web_page_mark_dot_only_without_badge():
    """会话行：有数字未读角标时不再重复画蓝点（对齐桌面）。"""
    from web import PAGE
    assert "(n?\"\":markDot(key))" in PAGE


# ---------- C12：群成员按状态分组 + B8：群文件按类型过滤 ----------
def _client_src():
    import os
    import client as _c
    return open(os.path.join(os.path.dirname(os.path.abspath(_c.__file__)),
                             "client.py"), encoding="utf-8").read()


def test_gf_kind_classifies_by_extension():
    """B8：群文件扩展名归类（图片/文档/压缩包/其他，大小写不敏感）。"""
    from client import gf_kind
    assert gf_kind("截图.PNG") == "image"
    assert gf_kind("a.jpeg") == "image"
    assert gf_kind("需求.docx") == "doc"
    assert gf_kind("report.pdf") == "doc"
    assert gf_kind("包.zip") == "archive"
    assert gf_kind("x.7z") == "archive"
    assert gf_kind("无扩展名") == "other"
    assert gf_kind("") == "other"


def test_group_members_by_status_wiring():
    """C12 桌面：状态分组顺序/标题常量 + 分组开关 + 实时状态判定齐全。"""
    import client as _c
    assert _c.MEMBER_STATUS_ORDER == ("online", "away", "busy", "offline")
    assert _c.MEMBER_STATUS_LABEL["offline"] == "离线"
    src = _client_src()
    assert "by_status = tk.BooleanVar(value=True)" in src
    assert "按在线状态分组" in src
    assert "MEMBER_STATUS_LABEL.get(s, s)" in src
    assert "def _status_of(m)" in src


def test_group_files_search_filter_wiring():
    """B8 桌面：群文件库搜索框 + 类型按钮 + 共享过滤填充方法。"""
    src = _client_src()
    assert "def _gf_fill(self, lb, records: list) -> list:" in src
    assert "GF_KIND_LABELS" in src
    assert "qv.trace_add(\"write\", _on_q)" in src
    assert "dlg[\"raw\"] = records" in src


def test_web_page_group_members_by_status():
    """C12 网页：群成员面板按状态分组（开关 + 分组标题）。"""
    from web import PAGE
    for token in ("function toggleMemGroup()", "state.memByStatus",
                  "memByStatus:true", "关闭分组 ○", "memStatus(m)===s",
                  "按状态分组 ●"):
        assert token in PAGE, "网页端缺少 C12 接线：" + token


# ---------- B5：群图片墙 / 相册 ----------
def test_image_wall_grid_and_hit_test(root):
    """B5：九宫格铺满路径；格子命中反解正确，间隙/越界返回 -1。"""
    from types import SimpleNamespace
    from widgets.image_wall import ImageWall
    picked = []
    paths = ["/tmp/a.png", "/tmp/b.png", "/tmp/c.png", "/tmp/d.png", "/tmp/e.png"]
    wall = ImageWall(root, paths, thumb_of=lambda p: None,
                     on_pick=picked.append, cols=2, cell=100, gap=8)
    try:
        for i in range(len(paths)):
            assert wall.canvas.find_withtag("iwc%d" % i), f"第 {i} 格未绘制"
        assert not wall.canvas.find_withtag("iwc5")        # 没有第 6 格
        cx, cy = wall._slot(3)                             # 第二行第 2 列
        ev = SimpleNamespace(x=int(cx + 50), y=int(cy + 50))
        assert wall._hit(ev) == 3
        wall._on_click(ev)
        assert picked == [3]
        gap_ev = SimpleNamespace(x=int(cx + 102), y=int(cy + 50))   # 落在列间隙
        assert wall._hit(gap_ev) == -1
        far_ev = SimpleNamespace(x=int(cx + 50), y=9999)
        assert wall._hit(far_ev) == -1
    finally:
        wall.destroy()


def test_image_wall_downsamples_oversized_thumb(root):
    """B5：缩略图大于格子时用整数倍 subsample 收进格子（不溢出、自持引用）。"""
    from widgets.image_wall import ImageWall
    big = tk.PhotoImage(width=240, height=150)
    wall = ImageWall(root, ["/tmp/big.png"], thumb_of=lambda p: big,
                     cols=2, cell=130, gap=8)
    try:
        got = wall._fit(0)
        assert got is not None
        assert max(got.width(), got.height()) <= 130 - 6
        assert wall._photos[0] is got                  # 降采样产物常驻防 GC
    finally:
        wall.destroy()


def test_image_wall_polls_until_thumbs_ready(root):
    """B5：缩略图未就绪画占位并轮询；到位后就地换格并停止轮询。"""
    from widgets.image_wall import ImageWall
    store = {}
    wall = ImageWall(root, ["/tmp/a.png", "/tmp/b.png"],
                     thumb_of=store.get, cols=2, cell=100, gap=8)
    try:
        assert wall._pending() == [0, 1]
        assert wall.canvas.find_withtag("iwc0")
        assert wall._job is not None                   # 已有轮询排程
        store["/tmp/a.png"] = tk.PhotoImage(width=80, height=60)
        wall._tick()
        assert wall._pending() == [1]
        assert wall.canvas.find_withtag("iwc0")
        store["/tmp/b.png"] = tk.PhotoImage(width=60, height=80)
        wall._tick()
        assert wall._pending() == []
        assert wall._job is None                       # 全部就绪 → 停轮询
    finally:
        store.clear()
        wall.destroy()


def test_group_album_wiring():
    """B5 桌面：群菜单入口 + 视图门控 + 复用灯箱/缩略图缓存。"""
    src = _client_src()
    assert "from widgets.image_wall import ImageWall" in src
    assert "label=\"🖼 图片墙\"" in src
    assert "def _group_album_dialog(self, gid: int) -> None:" in src
    assert "def _open_album_image(self, paths: list, idx: int) -> None:" in src
    assert "if self.view != (\"group\", gid):" in src       # 仅当前会话可开
    assert "self.msg_list.image_rows()" in src
    assert "thumb_of=self.msg_list._img_photo.get" in src


def test_web_page_image_wall_wiring():
    """B5 网页：图片墙面板 + 聚合已加载图片 + 灯箱多图翻页。"""
    from web import PAGE
    for token in ("function openAlbum()", "function closeAlbum()",
                  "function albumSrcs()", "function lbStep(", "function lightboxList(",
                  "const LB={list:[],i:0}",
                  "#msgs .bub img.mimg", "img class='mimg'",
                  "onclick=\"openAlbum()\"", "lightboxList(srcs,i)",
                  "#lb .lbnav{", "#alb .grid{",
                  "(LB.i+1)+\" / \"+LB.list.length"):
        assert token in PAGE, "网页端缺少 B5 接线：" + token


# ---------- B6+B7：群待办 / 接龙 / 签到 ----------
@pytest.fixture()
def hub(tmp_path):
    """本地 TCP Hub（与 test_c9_group 同构），B6/B7 协议级验证用。"""
    import socket
    import threading
    import time as _t
    from dataclasses import replace as _replace
    from config import CFG as _CFG
    from server import Hub, serve as serve_tcp
    cfg = _replace(_CFG, audit_dir=str(tmp_path / "audit"))
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    _t.sleep(0.1)
    yield h, port, stop
    stop.set()
    _t.sleep(0.2)


def _mk_group(port: int, owner_name="alice", members=("bob",)):
    """建群 + 拉成员；返回 (owner, gid, [owner, *members])。"""
    from test_server import TestClient
    o = TestClient(port, owner_name)
    o.hello()
    o.send({"t": "group_create", "name": "任务群", "public": 1})
    gs = o.wait("group_state", pred=lambda e: e.get("name") == "任务群")
    gid = gs["gid"]
    clients = [o]
    for name in members:
        m = TestClient(port, name)
        m.hello()
        m.send({"t": "group_join", "gid": gid})
        assert m.wait("group_state", pred=lambda e: e.get("gid") == gid)
        clients.append(m)
    return o, gid, clients


def test_task_frames_registered():
    """B6/B7：TASK_* 帧名与 TASK_STATE 广播帧就位。"""
    from protocol import MsgType
    assert MsgType.TASK_ADD.value == "task_add"
    assert MsgType.TASK_DO.value == "task_do"
    assert MsgType.TASK_LIST.value == "task_list"
    assert MsgType.TASK_DEL.value == "task_del"
    assert MsgType.TASK_STATE.value == "task_state"


def test_task_add_do_undo_del_flow(hub):
    """B6/B7：发起→参与→撤销→关闭全链路广播与权威状态。"""
    h, port, _stop = hub
    owner, gid, (o, b) = _mk_group(port)
    o.send({"t": "task_add", "gid": gid, "text": "周五发版", "mode": "relay"})
    st = b.wait("task_state", pred=lambda e: e.get("gid") == gid and e.get("tasks"))
    assert st is not None, "成员未收到 TASK_STATE 广播"
    assert len(st["tasks"]) == 1
    t0 = st["tasks"][0]
    assert t0["text"] == "周五发版" and t0["mode"] == "relay"
    assert t0["uid"] == o.uid and t0["closed"] == 0 and t0["done"] == {}
    assert t0["assignee"] == 0
    assert "发起接龙" in st["text"]
    tid = t0["tid"]
    assert h.tasks[gid][0]["tid"] == tid          # 服务端权威
    # bob 接龙
    b.send({"t": "task_do", "gid": gid, "tid": tid, "on": 1})
    st2 = o.wait("task_state", pred=lambda e: (e.get("tasks") or [{}])[0].get("done"))
    assert str(b.uid) in st2["tasks"][0]["done"]
    assert "接龙" in st2["text"]
    # bob 撤销
    b.send({"t": "task_do", "gid": gid, "tid": tid, "on": 0})
    st3 = o.wait("task_state", pred=lambda e: "撤销接龙" in (e.get("text") or ""))
    assert st3 is not None
    assert not st3["tasks"][0]["done"]
    # 发起人关闭
    o.send({"t": "task_del", "gid": gid, "tid": tid})
    st4 = b.wait("task_state", pred=lambda e: e.get("tasks") == [])
    assert st4 is not None and "关闭了" in st4["text"]
    assert h.tasks.get(gid) == []


def test_task_add_empty_and_bad_mode(hub):
    """B6/B7：空内容被拒（error code=task）；非法 mode 回落 todo。"""
    _h, port, _stop = hub
    owner, gid, _cl = _mk_group(port)
    owner.send({"t": "task_add", "gid": gid, "text": "   ", "mode": "todo"})
    err = owner.wait("error", pred=lambda e: e.get("code") == "task")
    assert err is not None and "内容不能为空" in err.get("text", "")
    owner.send({"t": "task_add", "gid": gid, "text": "合法内容", "mode": "瞎写"})
    st = owner.wait("task_state", pred=lambda e: e.get("tasks"))
    assert st["tasks"][0]["mode"] == "todo"


def test_task_assignee_restricts_others(hub):
    """B6/B7：指派任务仅被指派人可参与；越权回 error code=perm。"""
    _h, port, _stop = hub
    owner, gid, (o, b) = _mk_group(port)
    o.send({"t": "task_add", "gid": gid, "text": "只给 bob", "assignee": b.uid})
    st = b.wait("task_state", pred=lambda e: e.get("tasks"))
    assert st["tasks"][0]["assignee"] == b.uid
    tid = st["tasks"][0]["tid"]
    o.send({"t": "task_do", "gid": gid, "tid": tid, "on": 1})
    err = o.wait("error", pred=lambda e: e.get("code") == "perm")
    assert err is not None and "指派" in err.get("text", "")
    b.send({"t": "task_do", "gid": gid, "tid": tid, "on": 1})
    st2 = o.wait("task_state", pred=lambda e: (e.get("tasks") or [{}])[0].get("done"))
    assert str(b.uid) in st2["tasks"][0]["done"]


def test_task_assignee_outside_group_degrades_to_public(hub):
    """B6/B7：指派对象不在群内 → 退化为公开任务（assignee=0）。"""
    _h, port, _stop = hub
    owner, gid, _cl = _mk_group(port)
    owner.send({"t": "task_add", "gid": gid, "text": "公开化", "assignee": 987654})
    st = owner.wait("task_state", pred=lambda e: e.get("tasks"))
    assert st["tasks"][0]["assignee"] == 0


def test_task_del_permission_and_missing(hub):
    """B6/B7：普通成员不能关他人任务；不存在/已删除的任务回 error code=task。"""
    h, port, _stop = hub
    owner, gid, (o, b) = _mk_group(port)
    o.send({"t": "task_add", "gid": gid, "text": "别乱关", "mode": "todo"})
    st = b.wait("task_state", pred=lambda e: e.get("tasks"))
    tid = st["tasks"][0]["tid"]
    b.send({"t": "task_del", "gid": gid, "tid": tid})
    err = b.wait("error", pred=lambda e: e.get("code") == "perm")
    assert err is not None and "仅发起人" in err.get("text", "")
    assert h.tasks[gid]                            # 未被删除
    o.send({"t": "task_do", "gid": gid, "tid": 999999, "on": 1})
    err2 = o.wait("error", pred=lambda e: e.get("code") == "task")
    assert err2 is not None and "任务不存在" in err2.get("text", "")


def test_task_list_is_unicast_to_requester(hub):
    """B6/B7：TASK_LIST 只回请求者，不打扰群内其他成员。"""
    _h, port, _stop = hub
    owner, gid, (o, b) = _mk_group(port)
    o.send({"t": "task_add", "gid": gid, "text": "拉取用", "mode": "checkin"})
    b.wait("task_state", pred=lambda e: e.get("tasks"))
    b.send({"t": "task_list", "gid": gid})
    got = b.wait("task_state", pred=lambda e: e.get("tasks"))
    assert got is not None and got["tasks"][0]["mode"] == "checkin"
    assert not o.has("task_state", pred=lambda e: not e.get("text"))


def test_task_non_member_rejected(hub):
    """B6/B7：非群成员不能发起/拉取（error code=group）。"""
    _h, port, _stop = hub
    from test_server import TestClient
    owner, gid, _cl = _mk_group(port)
    outsider = TestClient(port, "outsider")
    outsider.hello()
    outsider.send({"t": "task_add", "gid": gid, "text": "混进来", "mode": "todo"})
    err = outsider.wait("error", pred=lambda e: e.get("code") == "group")
    assert err is not None and "不在该群" in err.get("text", "")
    outsider.send({"t": "task_list", "gid": gid})
    err2 = outsider.wait("error", pred=lambda e: e.get("code") == "group")
    assert err2 is not None


def test_task_snapshot_restore_roundtrip(hub, tmp_path):
    """B6/B7：快照落盘 → 新 Hub 恢复后任务与自增号一致（坏条目跳过）。"""
    from server import Hub
    h, port, _stop = hub
    owner, gid, (o, b) = _mk_group(port)
    o.send({"t": "task_add", "gid": gid, "text": "签到打卡", "mode": "checkin"})
    st = b.wait("task_state", pred=lambda e: e.get("tasks"))
    tid = st["tasks"][0]["tid"]
    b.send({"t": "task_do", "gid": gid, "tid": tid, "on": 1})
    o.wait("task_state", pred=lambda e: (e.get("tasks") or [{}])[0].get("done"))

    state = h._snapshot_state()
    assert str(gid) in state["tasks"] and state["task_seq"] == tid
    h2 = Hub(cfg=h.cfg, audit_dir=str(tmp_path / "audit2"))
    h2._restore(state)
    assert h2._task_seq == tid
    rec = h2.tasks[gid][0]
    assert rec["text"] == "签到打卡" and rec["mode"] == "checkin"
    assert rec["uid"] == o.uid and b.uid in rec["done"]
    assert rec["done"][b.uid] > 0
    # 坏条目跳过：缺 tid / 空 text / 非 dict / 非数字 gid
    h3 = Hub(cfg=h.cfg, audit_dir=str(tmp_path / "audit3"))
    h3._restore({"tasks": {"7": [{"text": "无 tid"}, "x", {"tid": 3, "text": ""},
                                   {"tid": 4, "text": "留着", "done": {"bad": "x"}}],
                            "abc": [{"tid": 9, "text": "非法群"}]},
                 "task_seq": 4})
    assert [t["tid"] for t in h3.tasks[7]] == [4]
    assert h3.tasks[7][0]["done"] == {}
    assert 0 not in h3.tasks


def test_task_panel_render_select_and_toggle(root):
    """B6/B7 桌面：面板渲染标记/计数、选中互斥按钮文案、双击参与回调。"""
    from widgets.task_panel import TaskPanel
    added, did, deleted, refreshed = [], [], [], []
    panel = TaskPanel(root, 7, "任务群", 2,
                      name_of=lambda u: {1: "阿甲", 2: "我"}.get(u, f"用户{u}"),
                      on_add=lambda t, m: added.append((t, m)),
                      on_do=lambda tid, on: did.append((tid, on)),
                      on_del=lambda tid: deleted.append(tid),
                      on_refresh=lambda: refreshed.append(1))
    root.update_idletasks()
    try:
        assert refreshed, "打开面板应触发一次清单拉取"
        panel.set_tasks([
            {"tid": 11, "text": "发版", "mode": "todo", "uid": 1, "ts": 0,
             "done": {}, "assignee": 0, "closed": 0},
            {"tid": 12, "text": "接龙吃饭", "mode": "relay", "uid": 1, "ts": 0,
             "done": {"2": 1.0}, "assignee": 2, "closed": 0},
            {"tid": 13, "text": "已关", "mode": "checkin", "uid": 1, "ts": 0,
             "done": {}, "assignee": 0, "closed": 1},
        ])
        assert panel.listbox.size() == 3
        assert panel.listbox.get(0).startswith("☐ [待办] 0 人 · 发版")
        assert panel.listbox.get(1).startswith("☑ [接龙] 1 人 · 接龙吃饭")
        assert panel.listbox.get(2).startswith("✅ [签到] 0 人 · 已关")
        assert "指派 我" in panel.listbox.get(1)
        assert panel._hint.cget("text") == "进行中 2 / 共 3"
        # 选中未参与的待办 → 按钮显示动作文案
        panel.listbox.selection_set(0)
        panel._sync_btn()
        assert panel._do_btn.cget("text") == "✓ 完成"
        panel._do_toggle()
        assert did == [(11, True)]
        # 选中我已参与 → 撤销
        panel.listbox.selection_clear(0, "end")
        panel.listbox.selection_set(1)
        panel._sync_btn()
        assert panel._do_btn.cget("text") == "↩ 撤销"
        panel._do_toggle()
        assert did[-1] == (12, False)
        # 关闭选中
        panel._del_sel()
        assert deleted == [12]
        # 发起：空内容不回调并给提示
        panel._add()
        assert added == [] and panel._hint.cget("text") == "内容不能为空"
        panel._entry.insert(0, "周末团建")
        panel._mode.set("relay")
        panel._add()
        assert added == [("周末团建", "relay")]
        assert panel._entry.get() == ""
        # 空清单不崩
        panel.set_tasks([])
        assert panel.listbox.size() == 0
        panel._sync_btn()
        assert panel._do_btn.cget("text") == "＋ 参与/打卡"
    finally:
        panel.destroy()


def test_task_panel_no_callbacks_is_safe(root):
    """B6/B7 桌面：未接线回调时交互不抛异常（如实降级）。"""
    from widgets.task_panel import TaskPanel
    panel = TaskPanel(root, 3, "群", 1)
    root.update_idletasks()
    try:
        panel.set_tasks([{"tid": 1, "text": "x", "mode": "todo", "uid": 1,
                          "ts": 0, "done": {}, "assignee": 0, "closed": 0}])
        panel.listbox.selection_set(0)
        panel._add()
        panel._do_toggle()
        panel._del_sel()
        panel._refresh()
    finally:
        panel.destroy()


def test_group_tasks_wiring():
    """B6/B7 桌面：菜单入口 + 面板复用 + 帧发送 + 回帧路由齐全。"""
    src = _client_src()
    assert "from widgets.task_panel import TaskPanel" in src
    assert "label=\"🧾 群任务\"" in src
    assert "def _group_tasks_dialog(self, gid: int) -> None:" in src
    assert "def _on_task_state(self, ev: dict) -> None:" in src
    assert "elif t == \"task_state\":" in src
    assert "self.core.send_task_list(gid)" in src
    assert "panel.set_tasks(ev.get(\"tasks\") or [])" in src
    core = open(__import__("client_core").__file__, encoding="utf-8").read()
    assert "MsgType.TASK_STATE.value" in core
    for fn in ("send_task_add", "send_task_do", "send_task_list", "send_task_del"):
        assert f"def {fn}(" in core, "client_core 缺少 " + fn


def test_web_page_tasks_wiring():
    """B6/B7 网页：任务面板 JS + 群任务入口 + SSE 回帧 + Python 侧动作转发。"""
    from web import PAGE
    for token in ("function openTasksPanel()", "function tkAdd()", "function tkDo(",
                  "function tkDel(", "function renderTasks()", "const TK_MODE=",
                  "const TK_DO=", "state.taskGid=", "state.taskGid===d.gid",
                  "tasks:[],taskGid:null,", "#tkpanel{",
                  "onclick='openTasksPanel()'",
                  "groupApi(\"task_list\",{gid:state.taskGid})",
                  "d.t===\"task_state\""):
        assert token in PAGE, "网页端缺少 B6/B7 接线：" + token
    import os
    import web as _w
    src = open(os.path.join(os.path.dirname(os.path.abspath(_w.__file__)),
                            "web.py"), encoding="utf-8").read()
    for token in ("\"task_add\": MsgType.TASK_ADD.value",
                  "\"task_do\": MsgType.TASK_DO.value",
                  "\"task_list\": MsgType.TASK_LIST.value",
                  "\"task_del\": MsgType.TASK_DEL.value",
                  "action == \"task_add\"", "action in (\"task_do\", \"task_del\")",
                  "frame[\"on\"] = 1 if body.get(\"on\", True) else 0",
                  "\"任务号非法\""):
        assert token in src, "web.py 缺少 B6/B7 转发：" + token


# ---------- D13：全局搜索过滤增强 ----------
def _gs():
    import widgets.global_search as gs
    return gs


def test_msg_kind_classification():
    """D13：按附件字段判定消息类型（优先级 poll > file > voice > fp > sticker …）。"""
    gs = _gs()
    assert gs.msg_kind({"text": "普通"}) == "text"
    assert gs.msg_kind({"text": "看这个 http://a.cn/x"}) == "link"
    assert gs.msg_kind({"text": "带图", "file": {"kind": "image", "fid": 1}}) == "image"
    assert gs.msg_kind({"text": "附件", "file": {"kind": "file", "fid": 2}}) == "file"
    assert gs.msg_kind({"text": "投票", "poll": {"q": "去吗"}}) == "poll"
    assert gs.msg_kind({"text": "语音", "voice": True}) == "voice"
    assert gs.msg_kind({"text": "转发", "fp": {"n": 2, "items": []}}) == "fwd"
    assert gs.msg_kind({"text": "[:cat:]"}) == "sticker"
    assert gs.msg_kind({"text": "表情", "sticker": "smile"}) == "sticker"
    assert gs.msg_kind({"text": "卡片", "preview": {"url": "u"}}) == "link"
    assert gs.msg_kind({"text": "富", "rich": [{"t": "b"}]}) == "rich"
    # 优先级：投票压过正文里的链接；图片压过链接预览
    assert gs.msg_kind({"text": "http://a.cn", "poll": {"q": "x"}}) == "poll"
    assert gs.msg_kind({"text": "http://a.cn", "file": {"kind": "image"}}) == "image"
    assert gs.msg_kind(None) == "text"
    for k in gs.MSG_KIND_LABEL:
        assert gs.MSG_KIND_LABEL[k]


def test_filter_hits_sender_kind_time():
    """D13：filter_hits 三个维度独立生效、可叠加，顺序保持（ts 倒序）。"""
    gs = _gs()
    import time as _t
    now = 1_700_000_000.0
    hits = [
        {"uid": 1, "nick": "甲", "kind": "text", "ts": now - 60},
        {"uid": 2, "nick": "乙", "kind": "image", "ts": now - 3600},
        {"uid": 1, "nick": "甲", "kind": "image", "ts": now - 3 * 86400},
        {"uid": 3, "nick": "丙", "kind": "text", "ts": now - 40 * 86400},
    ]
    assert gs.filter_hits(hits) == hits                       # 无参数 = 原样
    assert [h["nick"] for h in gs.filter_hits(hits, sender=1)] == ["甲", "甲"]
    assert [h["nick"] for h in gs.filter_hits(hits, kind="image")] == ["乙", "甲"]
    recent = gs.filter_hits(hits, days=7, now=now)
    assert [h["nick"] for h in recent] == ["甲", "乙", "甲"]
    both = gs.filter_hits(hits, sender=1, kind="image", days=7, now=now)
    assert [h["ts"] for h in both] == [now - 3 * 86400]        # 只剩甲那条旧图
    # 缺 ts 的结果在启用时间过滤时被剔除，但不过滤时保留
    loose = [{"uid": 1, "kind": "text", "ts": None, "nick": "甲"}]
    assert gs.filter_hits(loose) == loose
    assert gs.filter_hits(loose, days=7, now=now) == []
    assert gs.filter_hits([], sender=1) == []


def test_filter_hits_days_1_uses_today_midnight():
    """D13：「今天」＝本地 0 点起（不是「近 24 小时」）。"""
    gs = _gs()
    import time as _t
    lt = _t.localtime()
    midnight = _t.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    now = midnight + 3600
    hits = [{"uid": 1, "kind": "text", "ts": midnight + 10, "nick": "今"},
            {"uid": 1, "kind": "text", "ts": midnight - 10, "nick": "昨"}]
    got = gs.filter_hits(hits, days=1, now=now)
    assert [h["nick"] for h in got] == ["今"]


def test_hit_senders_and_kinds_aggregate():
    """D13：下拉候选聚合去重 + 固定顺序（senders 取 nick，kinds 按 _KIND_ORDER）。"""
    gs = _gs()
    hits = [{"uid": 2, "nick": "乙", "kind": "image"},
            {"uid": 1, "nick": "甲", "kind": "text"},
            {"uid": 2, "nick": "乙", "kind": "text"}]
    assert set(gs.hit_senders(hits)) == {("乙 (#2)", 2), ("甲 (#1)", 1)}
    kinds = [k for _l, k in gs.hit_kinds(hits)]
    assert kinds == ["text", "image"]                          # 按 _KIND_ORDER
    assert [l for l, _k in gs.hit_kinds(hits)] == ["文本", "图片"]
    assert gs.hit_senders([]) == [] and gs.hit_kinds([]) == []
    assert gs.hit_senders([{"kind": "text"}]) == []             # 无 uid 不进候选


def test_index_items_carry_uid_and_kind(tmp_path):
    """D13：索引项新增 uid/kind（纯追加字段），检索与倒序语义不变。"""
    gs = _gs()
    import json
    (tmp_path / "public.jsonl").write_text("\n".join(json.dumps(m, ensure_ascii=False)
                                                     for m in [
        {"seq": 2, "text": "golang 图", "ts": 200, "uid": 7, "nick": "甲",
         "file": {"kind": "image"}},
        {"seq": 1, "text": "golang 文", "ts": 100, "uid": 8, "nick": "乙"},
    ]) + "\n", encoding="utf-8")
    idx = gs.load_index(str(tmp_path))
    hits = idx.search("golang")
    assert [h["ts"] for h in hits] == [200, 100]
    assert hits[0]["uid"] == 7 and hits[0]["kind"] == "image"
    assert hits[1]["kind"] == "text"
    idx.add("public", {"seq": 3, "text": "晚点吃什么", "ts": 300, "uid": 9,
                       "poll": {"q": "x"}})
    assert idx.search("吃什么")[0]["kind"] == "poll"
    idx.add("public", {"seq": 4, "text": "", "ts": 400})        # 无正文仍跳过
    assert len(idx) == 3


def test_global_search_filter_wiring():
    """D13 桌面接线：过滤条 + 原始命中缓存 + 过滤重渲染 + 结果内跳转。"""
    src = open(_gs().__file__, encoding="utf-8").read()
    for token in ("from tkinter import ttk", "def filter_hits(",
                  "def hit_senders(", "def hit_kinds(",
                  "self.sender_cb = ttk.Combobox(", "self.kind_cb = ttk.Combobox(",
                  "self.time_cb = ttk.Combobox(", "def _apply_filters(self) -> None:",
                  "def _refresh_filters(self) -> None:", "self._raw = list(res)",
                  "filter_hits(self._raw, sender=sender, kind=kind, days=days)",
                  "MSG_KIND_LABEL.get(k, k)"):
        assert token in src, "global_search 缺少 D13 接线：" + token
    # 回车跳转后自动前进下一条命中
    assert "self._move(1)" in src.split("def _pick_sel")[1].split("def _pick(")[0]


# ---------- D14：语音连播 ----------
def test_voice_autoplay_desc_wiring():
    """D14：MsgList 暴露 on_voice_end，播完回调；client 侧有开关与连播逻辑。"""
    import os
    import widgets.msg_list as ml
    msrc = open(ml.__file__, encoding="utf-8").read()
    for token in ("on_voice_end=None,", "self._on_voice_end = on_voice_end",
                  "self._on_voice_end(vp[0])"):
        assert token in msrc, "msg_list 缺少 D14 接线：" + token
    csrc = _client_src()
    for token in ("on_voice_end=self._on_voice_end,",
                  "def _on_voice_end(self, idx: int) -> None:",
                  "def _toggle_voice_autoplay(self) -> None:",
                  "self._prefs.get(\"voice_autoplay\")",
                  "self._prefs.set(\"voice_autoplay\", bool(on))",
                  "\"🔁 语音连播\"",
                  "self.msg_list.voice_started(j, getattr(r, \"voice_dur\", 0.0), rate)"):
        assert token in csrc, "client 缺少 D14 接线：" + token
    assert os.path.basename(ml.__file__) == "msg_list.py"


# ---------- D15：屏幕共享 + 画中画 ----------
def test_screen_recorder_matches_cam_interface():
    """D15：ScreenRecorder 与 CamRecorder 同名接口（voice_call 可无差别替换）。"""
    import video_api as va
    for name in ("start", "stop", "is_healthy", "_fail"):
        assert hasattr(va.ScreenRecorder, name), "ScreenRecorder 缺 " + name
    assert callable(va.screen_available)
    # 非 Windows 或未装 Pillow 时为 False（不抛异常）
    assert isinstance(va.screen_available(), bool)


def test_screen_recorder_grab_encodes_png():
    """D15：抓一帧的编码路径可独立验证（注入假 ImageGrab，不需要真屏幕）。"""
    import video_api as va

    class _Img:
        """最小假图：只需 size / convert / resize / tobytes。"""

        def __init__(self, w, h):
            self.size = (w, h)

        def convert(self, _m):
            return self

        def resize(self, size):
            return _Img(size[0], size[1])

        def tobytes(self):
            w, h = self.size
            return bytes([200]) * (w * h * 3)

    class _Grab:
        @staticmethod
        def grab(bbox=None):
            return _Img(1920, 1080)

    got = []
    rec = va.ScreenRecorder(on_frame=got.append)
    rec._grab_once(_Grab)
    assert len(got) == 1 and got[0][:8] == b"\x89PNG\r\n\x1a\n"
    w, h, rows = va.png_decode(got[0])
    assert w == va.VID_W and h == 180 and len(rows) == 180
    assert all(len(r) == va.VID_W * 3 for r in rows)
    assert rec.last_frame_ts > 0               # 抓到帧即刷新时间戳


def test_call_manager_screen_source():
    """D15：set_video(source="screen") 起屏幕采集；video 事件带 source。"""
    import time
    import video_api as va
    from voice_call import CallManager

    class _Core:
        roster = {}
        known = {}

        def _send_frame(self, _f):
            return True

    cm = CallManager(_Core())
    cm.state = "incall"
    cm._peer_vcap = True
    evs = []
    cm._push = lambda kind, **kw: evs.append((kind, kw))
    made = []

    class _FakeScreen:
        def __init__(self, on_frame=None, on_error=None):
            made.append(self)
            self.on_frame = on_frame
            self.on_error = on_error

        def start(self):
            return True

        def stop(self):
            pass

    orig = va.ScreenRecorder
    va.ScreenRecorder = _FakeScreen
    try:
        cm.set_video(True, source="screen")
        for _ in range(200):                   # 采集器在后台线程创建
            if made:
                break
            time.sleep(0.01)
    finally:
        va.ScreenRecorder = orig
    assert made and cm.video_source() == "screen"
    assert cm.is_video_on()
    assert ("video", {"on": True, "source": "screen"}) in evs
    cm.shutdown()                              # 不发声令帧，仅清理状态


def test_call_window_pip_and_share_wiring():
    """D15 桌面接线：共享/画中画按钮 + PiP 窗口生命周期 + 帧推送。"""
    import os
    import widgets.call_window as cw
    src = open(cw.__file__, encoding="utf-8").read()
    for token in ("self.btn_share = tk.Label(", "self.btn_pip = tk.Label(",
                  "def _toggle_share(self, _e=None) -> None:",
                  "def _toggle_pip(self, _e=None) -> None:",
                  "def _push_pip(self) -> None:", "def _close_pip(self) -> None:",
                  "def _video_from_screen(self) -> bool:",
                  "from widgets.pip_window import PipWindow",
                  "self.manager.set_video(True, source=\"screen\")",
                  "self.manager.screen_supported()"):
        assert token in src, "call_window 缺少 D15 接线：" + token
    pip_path = os.path.join(os.path.dirname(os.path.abspath(cw.__file__)),
                            "pip_window.py")
    psrc = open(pip_path, encoding="utf-8").read()
    for token in ("class PipWindow(tk.Toplevel)", "self.overrideredirect(True)",
                  "\"-topmost\", True", "def set_frame(self, png) -> None:",
                  "def close(self) -> None:", "<B1-Motion>", "返回"):
        assert token in psrc, "pip_window 缺少 D15 能力：" + token


def test_voice_call_and_video_api_doc_wiring():
    """D15 采集源分派：voice_call 按 source 选 ScreenRecorder / CamRecorder。"""
    import os
    import voice_call as vc
    src = open(os.path.join(os.path.dirname(os.path.abspath(vc.__file__)),
                            "voice_call.py"), encoding="utf-8").read()
    for token in ("def set_video(self, on: bool, source: str = \"cam\") -> None:",
                  "def screen_supported(self) -> bool:",
                  "def video_source(self) -> str:",
                  "def _cam_start(self, source: str = \"cam\") -> None:",
                  "video_api.ScreenRecorder(on_frame=self._send_video_frame",
                  "self._push(\"video\", on=True, source=source)"):
        assert token in src, "voice_call 缺少 D15 接线：" + token
