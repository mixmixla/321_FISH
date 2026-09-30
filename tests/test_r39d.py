# -*- coding: utf-8 -*-
"""R39D 体验三件回归：图片灯箱 / 滚动伪惯性+气泡淡入 / 合并转发。

Lightbox 纯数学（无 Tk）：
- clamp_zoom 钳制 [0.2, 8.0]；fit_scale 收进视口（只缩不放，坏输入回退 1.0）
- zoom_anchor 不变量：锚点所指图像内容点在缩放前后屏幕位置不动

滚动伪惯性（Tk）：
- _wheel 只推进目标位并调度插值帧，不直接跳格；连发滚轮只保留一个定时器
- _smooth_tick 逐帧逼近，收敛后贴齐目标并清态；_cancel_smooth 清定时器与目标
- 程序性滚动（load / prepend / scroll_to_end / append 钉底）打断在途惯性

气泡淡入（Tk）：
- 开启后 own 新消息进入 _fading；他人消息/系统行不进入；关开关即清空
- _bubble_fill 淡入期返回渐混色，结束后返回纯色

合并转发 forward_pack（Tk + 集成）：
- _Row 解析 fp 段，正文占位 [合并转发] N 条消息；渲染行高为正、重绘不崩
- _ellipsis 按像素截断；双击合并转发卡路由到 on_fwd_open（不走引用回复）
- client_core.send_chat(fwd_seqs=/fwd_from=) 只提交源会话+源 seq 入帧（R64 口径）
- 服务器按真实历史聚合（白名单字段、条数截 30、单条文本截 200、空 items 丢弃），
  客户端自带 fp 一律忽略，源会话越权（他人私聊）拒绝
"""
import socket
import threading
import time
import types
from dataclasses import replace

import pytest

from client_core import ClientCore
from config import CFG
from server import Hub, serve as serve_tcp
from widgets.lightbox import Lightbox, ZOOM_MAX, ZOOM_MIN
from widgets.msg_list import MsgList, _Row

FONT = ("Microsoft YaHei UI", 9)


# ================= Lightbox 纯数学（无 Tk） =================

def test_lightbox_clamp_zoom():
    assert Lightbox.clamp_zoom(0.01) == ZOOM_MIN
    assert Lightbox.clamp_zoom(99.0) == ZOOM_MAX
    assert Lightbox.clamp_zoom(1.5) == 1.5


def test_lightbox_fit_scale():
    assert Lightbox.fit_scale(2000, 1000, 400, 400) == 0.2     # 等比收进
    assert Lightbox.fit_scale(100, 50, 400, 400) == 1.0        # 小图不放大
    assert Lightbox.fit_scale(0, 100, 400, 400) == 1.0         # 坏输入回退
    assert Lightbox.fit_scale(100, 100, 0, 400) == 1.0


def test_lightbox_zoom_anchor_invariant():
    """锚点 (px,py) 指向的图像内容点缩放前后屏幕位置不动。"""
    ox, oy = 30.0, -20.0                       # 当前偏移（zoom_old = 1）
    px, py = 200.0, 150.0                      # 指针（锚点）
    ratio = 1.5
    nx, ny = Lightbox.zoom_anchor(ox, oy, px, py, ratio)
    img_pt = (px - ox, py - oy)                # 锚点处的图像内容坐标
    assert (ox + img_pt[0], oy + img_pt[1]) == (px, py)          # 旧帧落在锚点
    assert (nx + img_pt[0] * ratio, ny + img_pt[1] * ratio) == \
        pytest.approx((px, py))                # 新帧（zoom_new=ratio）仍在锚点


# ================= Tk 环境 =================

@pytest.fixture(scope="module")
def root():
    try:
        import tkinter as tk
        r = tk.Tk()
    except Exception as exc:            # 无显示环境（headless CI）跳过
        pytest.skip(f"无可用 Tk 显示环境: {exc}")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except Exception:
        pass


@pytest.fixture()
def ml(root):
    ml = MsgList(root, FONT)
    ml.configure(width=400, height=400)
    ml.pack(fill="both", expand=True)
    root.update_idletasks()
    root.update()
    yield ml
    ml.destroy()


def _msg(seq, uid=1, text=None):
    return {"t": "chat", "channel": "public", "seq": seq, "uid": uid,
            "nick": "甲" if uid == 1 else "乙",
            "text": text or f"消息 {seq}", "ts": time.time() - (1000 - seq)}


# ================= 滚动伪惯性 =================

def test_wheel_sets_target_and_schedules(ml):
    ml.load([_msg(i) for i in range(1, 50)], me_uid=1)
    ml.update()
    ml._cancel_smooth()
    ml._wheel(120)                              # 上滚一格
    assert ml._scroll_target is not None        # 目标位已推进
    assert ml._smooth_job is not None           # 插值帧已调度
    t1 = ml._scroll_target
    ml._wheel(120)                              # 连发：目标继续推进，定时器不重复
    assert ml._scroll_target < t1
    ml._cancel_smooth()
    assert ml._scroll_target is None and ml._smooth_job is None


def test_smooth_tick_eases_then_snaps(ml):
    calls = []
    ml.yview = lambda: (0.0, 0.0)               # stub：视口停在 0
    ml.yview_moveto = lambda f: calls.append(f)
    ml._set_stick_from_view = lambda: None
    ml._maybe_load_top = lambda: None
    ml._render = lambda: None
    ml._scroll_target = 0.5
    ml._smooth_frames = 0
    ml._smooth_tick()                           # 第 1 帧：向目标逼近
    assert calls and calls[0] == pytest.approx(0.5 * ml.SMOOTH_EASE)
    assert ml._smooth_job is not None           # 未收敛 → 继续调度
    ml._cancel_smooth()
    # 收敛：视口已到目标 → 贴齐并清态
    calls.clear()
    ml.yview = lambda: (0.5, 0.5)
    ml._scroll_target = 0.5
    ml._smooth_frames = 0
    ml._smooth_tick()
    assert calls[-1] == 0.5
    assert ml._scroll_target is None and ml._smooth_job is None


def test_smooth_tick_frame_cap(ml):
    """顶/底钳制下 diff 不收敛：帧数上限兜底退出。"""
    ml.yview = lambda: (0.0, 0.0)
    ml.yview_moveto = lambda f: None
    ml._set_stick_from_view = lambda: None
    ml._maybe_load_top = lambda: None
    ml._render = lambda: None
    ml._scroll_target = 0.9                     # 视口恒 0，diff 恒大
    ml._smooth_frames = ml.SMOOTH_MAX_FRAMES - 1
    ml._smooth_tick()                           # 最后一帧
    assert ml._scroll_target is None            # 上限退出，目标贴齐
    assert ml._smooth_job is None


def test_programmatic_scroll_cancels_smooth(ml):
    ml.load([_msg(i) for i in range(1, 30)], me_uid=1)
    ml.update()
    ml._wheel(-120)
    assert ml._smooth_job is not None
    ml.load([_msg(1)], me_uid=1)                # 切会话
    assert ml._smooth_job is None and ml._scroll_target is None
    ml._wheel(-120)
    ml.scroll_to_end()
    assert ml._smooth_job is None
    ml._wheel(-120)
    ml.prepend([_msg(i) for i in range(-10, 0)])  # 翻页
    assert ml._smooth_job is None


# ================= 气泡淡入 =================

def test_fade_tracks_own_rows_only(ml):
    ml.set_fade_enabled(True)
    ml.load([_msg(1, uid=2)], me_uid=1)         # 他人历史消息不触发
    assert ml._fading == {}
    ml.append(_msg(2, uid=2))                   # 他人实时消息（行 1）
    assert ml._fading == {}
    ml.append(_msg(3, uid=1))                   # 我的实时消息（行 2）
    assert 2 in ml._fading                      # 行下标 2 进入淡入
    ml.append({"ts": time.time(), "text": "系统行"})     # 系统行（append_sys 路径）
    assert all(i < ml.count for i in ml._fading)
    ml.set_fade_enabled(False)
    assert ml._fading == {}                     # 关开关即清空


def test_bubble_fill_fade_colors(ml):
    ml.set_me_uid(1)
    ml.set_fade_enabled(True)
    ml.append(_msg(1, uid=1))
    base = ml._pal["bubble_out"]
    bg = ml._pal["bg"]
    assert ml._bubble_fill(0, True) != base     # 淡入期：渐混色 ≠ 纯色
    assert ml._bubble_fill(0, True) != bg
    ml._fading[0] = time.time() - 10            # 起始时间推到过期
    assert ml._bubble_fill(0, True) == base     # 结束后回到纯色
    ml._fading.clear()
    assert ml._bubble_fill(0, True) == base
    ml._fading[0] = time.time()
    assert ml._bubble_fill(0, False) == ml._pal["bubble_in"]   # 他人气泡不受影响


# ================= 合并转发 forward_pack =================

def _fp_msg(seq=10, n=3):
    return {"t": "chat", "channel": "public", "seq": seq, "uid": 2, "nick": "乙",
            "ts": time.time(),
            "fp": {"n": n, "items": [
                {"nick": "甲", "ts": time.time() - 60, "text": f"第{i}条"}
                for i in range(1, n + 1)]}}


def test_row_parses_fp_and_body(ml):
    row = _Row(_fp_msg())
    assert row.fwd_pack is not None and row.fwd_pack["n"] == 3
    assert "[合并转发] 3 条消息" in row.body
    plain = _Row({"uid": 1, "nick": "甲", "text": "普通", "ts": 1.0})
    assert plain.fwd_pack is None
    sysrow = _Row({"ts": 1.0, "text": "sys"}, is_system=True)
    assert sysrow.fwd_pack is None              # 系统行不解析 fp
    bad = _Row({"uid": 1, "nick": "甲", "ts": 1.0, "fp": "脏数据"})
    assert bad.fwd_pack is None                 # 非 dict 忽略


def test_fp_row_estimate_and_render(ml):
    ml.load([_msg(1), _fp_msg(2), _msg(3)], me_uid=1)
    ml.update()
    assert ml._heights[1] is not None and ml._heights[1] > 0
    # 估算与绘制同源：fp 卡估算 = 实测（_estimate 有专用 fp 分支）
    assert ml._heights[1] == ml._estimate(1, ml._rows[1])
    h_fp = ml._heights[1]
    cum = ml._cum[-1]
    ml._render()                                # 重绘不崩
    assert ml._heights[1] == h_fp               # fp 行高稳定（无反馈回路）
    # 普通文本行存在既有 ≤PAD_TOP(3px) 估算差（绘制后自校正）；fp 行同源零差
    assert abs(ml._cum[-1] - cum) <= 3 * ml.count
    # 大包（n>3）：预览封顶 3 行，估算与绘制行数同源
    ml.append(_fp_msg(5, n=12))
    ml.update()
    assert ml._heights[-1] == h_fp              # n=3 与 n=12 同高（预览封顶）


def test_ellipsis_truncates_to_pixel_width(ml):
    short = "短文本"
    assert ml._ellipsis(short, 1000) == short   # 宽度足够 → 原样
    long_t = "很长的测试文本" * 50
    out = ml._ellipsis(long_t, 40)
    assert out.endswith("…")
    assert ml._meas(out) <= 40                  # 截断后不超预算
    assert ml._ellipsis("", 40) == ""


def test_double_click_fp_row_routes_to_fwd_open(ml):
    opened = []
    quoted = []
    ml._on_fwd_open = opened.append
    ml._on_row_double = quoted.append
    ml.load([_fp_msg(1), _msg(2)], me_uid=1)
    ml.update()
    ml.canvasy = lambda y: y    # stub：withdrawn 窗口画布仅 1px 高，canvasy 会加滚动偏移致越界
    h = ml._heights[0]
    ev = types.SimpleNamespace(x=100, y=int(h / 2))
    ml._on_double_click(ev)                     # 双击合并转发卡
    assert opened == [0] and quoted == []       # 走展开，不走引用回复
    ev2 = types.SimpleNamespace(x=100, y=int(ml._heights[0] + ml._heights[1] / 2))
    ml._on_double_click(ev2)                    # 双击普通行
    assert quoted == [1] and opened == [0]      # 走引用回复（且仅一次）


def test_clientcore_send_chat_fwd_frame(tmp_path):
    core = ClientCore(host="127.0.0.1", port=1, nick="t",
                      history_dir=str(tmp_path / "h"))
    frames = []
    core._send_frame = lambda header, body=b"": frames.append(header) or True
    assert core.send_chat("", channel="group", to=9, fwd_seqs=[11, 12],
                          fwd_from={"type": "public"}) is True
    assert frames[0]["fwd_seqs"] == [11, 12]
    assert frames[0]["fwd_from"] == {"type": "public"}
    assert "text" not in frames[0] and "fp" not in frames[0]
    core._history.close()


# ================= 服务器 fp 聚合（集成，R64 口径） =================

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Cli:
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
                hb, b = self.chan.recv_frame()
                with self._lock:
                    self.events.append((hb, b))
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


@pytest.fixture()
def hub(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"))
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    time.sleep(0.2)
    yield h, port, stop
    stop.set()
    time.sleep(0.2)


def _seed_public(cli_send, watcher, n=40, prefix="源"):
    """往公共频道灌 n 条消息，返回其真实 seq 列表（按发送顺序）。"""
    seqs = []
    for i in range(n):
        cli_send({"t": "chat", "channel": "public", "text": f"{prefix}{i}"})
    for _ in range(n):
        h, _b = watcher.wait("chat",
                             pred=lambda x: str(x.get("text", "")).startswith(prefix))
        assert h is not None
        seqs.append(h["seq"])
    return seqs


def test_server_fwd_aggregates_real_history(hub):
    """合并转发：条目由服务器按源 seq 从真实历史聚合（白名单字段 + 条数上限）。"""
    _h, port, _stop = hub
    a, b = _Cli(port, "甲"), _Cli(port, "乙")
    assert a.hello() and b.hello()
    seqs = _seed_public(a.send, b, 40)
    a.send({"t": "chat", "channel": "public",
            "fwd_seqs": list(reversed(seqs)),       # 倒序提交 → 顺序即提交序
            "fwd_from": {"type": "public"}})
    got = b.wait("chat", pred=lambda h: "fp" in h)
    assert got is not None
    fp = got[0]["fp"]
    assert fp["n"] == 30                            # 条数截断到上限
    assert len(fp["items"]) == 30
    it = fp["items"][0]
    assert set(it.keys()) <= {"nick", "text", "ts"}  # 白名单字段
    assert it["nick"] == "甲"                        # 昵称取自服务器历史
    assert it["text"] == "源39"                      # 正文取自服务器历史
    a.close()
    b.close()


def test_server_fwd_single_text_cap(hub):
    _h, port, _stop = hub
    a, b = _Cli(port, "甲"), _Cli(port, "乙")
    assert a.hello() and b.hello()
    a.send({"t": "chat", "channel": "public", "text": "超" * 500})
    h, _ = b.wait("chat", pred=lambda x: x.get("text"))
    assert h is not None
    a.send({"t": "chat", "channel": "public", "fwd_seqs": [h["seq"]],
            "fwd_from": {"type": "public"}})
    got = b.wait("chat", pred=lambda h: "fp" in h)
    assert got is not None
    it = got[0]["fp"]["items"][0]
    assert len(it["text"]) == 200                   # 单条文本截到 200
    a.close()
    b.close()


def test_server_fwd_ignores_client_fp_payload(hub):
    """客户端自带 fp 条目 → 一律忽略（无可聚合源 seq 则拒发）。"""
    _h, port, _stop = hub
    a, b = _Cli(port, "甲"), _Cli(port, "乙")
    assert a.hello() and b.hello()
    forged = {"n": 1, "items": [{"nick": "领导", "text": "伪造内容"}]}
    a.send({"t": "chat", "channel": "public", "fp": forged})
    err = a.wait("error", timeout=2.0)
    assert err is not None and err[0].get("code") == "empty"
    # 带正文的伪造 fp：正文照发，伪造卡被剥除
    a.send({"t": "chat", "channel": "public", "text": "正常文本", "fp": forged})
    got = b.wait("chat", pred=lambda h: h.get("text") == "正常文本")
    assert got is not None and "fp" not in got[0]
    a.close()
    b.close()


def test_server_fwd_cannot_reach_foreign_private(hub):
    """源 seq 落在他人私聊 → 源会话权限校验拦住，条目为空并拒发。"""
    _h, port, _stop = hub
    a, b, c = _Cli(port, "甲"), _Cli(port, "乙"), _Cli(port, "丙")
    assert a.hello() and b.hello() and c.hello()
    b.send({"t": "chat", "channel": "private", "to": c.uid, "text": "乙丙私聊机密"})
    got = c.wait("chat", pred=lambda h: h.get("text"))
    assert got is not None
    secret_seq = got[0]["seq"]
    a.send({"t": "chat", "channel": "public",
            "fwd_seqs": [secret_seq],
            "fwd_from": {"type": "private", "uid": c.uid}})
    err = a.wait("error", timeout=2.0)
    assert err is not None and err[0].get("code") == "empty"
    a.close()
    b.close()
    c.close()
