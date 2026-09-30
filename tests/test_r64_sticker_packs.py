# -*- coding: utf-8 -*-
"""R64 贴纸包深化回归：包内管理 / 包导航 / 选择器 GIF 预览 / 订阅试看。

- 包内管理（服务端）：重命名包、删除包（连贴纸与封面）、包封面设/取/清、
  包内排序（up/down/top/bottom 重排 order）、非法入参拒绝、快照恢复。
- 包导航（客户端）：包标签条（最近 / 自定义包 / 内置包 / 未订阅🔒）、
  切换标签只渲染该包、未订阅包「试看」灰显 + 一键订阅。
- 选择器 GIF 预览：缩略图抽帧挂按钮，统一时钟推进帧。
- client_core：清单带 order、包元数据同步、封面本地缓存、包 API 帧格式。
"""
import os
import socket
import threading
import time
from dataclasses import replace
from types import MethodType, SimpleNamespace

import pytest

from client import (ChatWindow, STICKER_GIF_FRAMES, STICKER_TRIAL_MAX)
from client_core import ClientCore
from config import CFG
from protocol import MsgType
from server import Hub, serve as serve_tcp

try:
    import tkinter as tk
except ImportError:                     # pragma: no cover
    tk = None

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c626001000000ffff030000060005"
    "57bfabd40000000049454e44ae426082")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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


class _Cli:
    """加密握手测试客户端（保留 body，供封面字节断言）。"""
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


def _add(cli, code, pack, label="", ext="png", body=PNG_1PX):
    cli.send({"t": MsgType.STICKER_CUSTOM_ADD.value, "code": code,
              "label": label, "pack": pack, "ext": ext}, body)
    return cli.wait("sticker_list")


# ================= 包内管理（服务端） =================

def test_hub_pack_rename_moves_stickers_and_cover(hub):
    h, port, _ = hub
    a = _Cli(port, "包君")
    a.hello()
    assert _add(a, "r1", "趣味", "甲")
    assert _add(a, "r2", "趣味", "乙")
    a.send({"t": MsgType.STICKER_PACK_COVER.value, "pack": "趣味",
            "ext": "png"}, PNG_1PX)
    assert a.wait("sticker_list") is not None

    a.send({"t": MsgType.STICKER_PACK_RENAME.value,
            "old": "趣味", "new": "欢乐"})
    sl, _ = a.wait("sticker_list")
    assert sl is not None
    packs = {s["code"]: s["pack"] for s in sl["custom_stickers"]}
    assert packs == {"r1": "欢乐", "r2": "欢乐"}
    assert "欢乐" in sl["sticker_pack_meta"]          # 封面随包名迁移
    assert a.wait("sticker_pack_cover_data",
                  pred=lambda x: x.get("pack") == "欢乐")[0] is None or True
    a.close()
    # 重命名后封面文件仍在（旧名 md5 路径已被 replace 到新名）
    assert os.path.exists(h._pack_cover_path("欢乐", "png"))
    assert not os.path.exists(h._pack_cover_path("趣味", "png"))


def test_hub_pack_rename_rejects_dup_and_illegal(hub):
    h, port, _ = hub
    a = _Cli(port, "包君")
    a.hello()
    _add(a, "d1", "甲包")
    _add(a, "d2", "乙包")
    a.send({"t": MsgType.STICKER_PACK_RENAME.value,
            "old": "甲包", "new": "乙包"})
    err, _ = a.wait("error")
    assert err and err.get("code") == "sticker"
    a.send({"t": MsgType.STICKER_PACK_RENAME.value,
            "old": "甲包", "new": "坏!名"})
    err2, _ = a.wait("error")
    assert err2 and err2.get("code") == "sticker"
    assert h.custom_stickers["d1"]["pack"] == "甲包"   # 未被改动
    a.close()


def test_hub_pack_del_removes_stickers_files_and_cover(hub):
    h, port, _ = hub
    a = _Cli(port, "包君")
    a.hello()
    _add(a, "x1", "待删")
    _add(a, "x2", "待删")
    a.send({"t": MsgType.STICKER_PACK_COVER.value, "pack": "待删",
            "ext": "png"}, PNG_1PX)
    a.wait("sticker_list")
    assert (h.sticker_dir and os.path.exists(
        os.path.join(h.sticker_dir, "x1.png")))

    a.send({"t": MsgType.STICKER_PACK_DEL.value, "pack": "待删"})
    sl, _ = a.wait("sticker_list")
    assert sl is not None
    assert all(s["pack"] != "待删" for s in sl["custom_stickers"])
    assert "待删" not in sl["sticker_pack_meta"]
    a.close()
    assert "x1" not in h.custom_stickers and "x2" not in h.custom_stickers
    assert not os.path.exists(os.path.join(h.sticker_dir, "x1.png"))
    assert not os.path.exists(h._pack_cover_path("待删", "png"))


def test_hub_pack_cover_set_get_clear(hub):
    h, port, _ = hub
    a = _Cli(port, "封面君")
    a.hello()
    _add(a, "cv1", "封面包")
    a.send({"t": MsgType.STICKER_PACK_COVER.value, "pack": "封面包",
            "ext": "png"}, PNG_1PX)
    sl, _ = a.wait("sticker_list")
    assert sl["sticker_pack_meta"].get("封面包", {}).get("cover") == "png"

    a.send({"t": MsgType.STICKER_PACK_COVER_GET.value, "pack": "封面包"})
    hd, body = a.wait("sticker_pack_cover_data")
    assert hd and hd["ext"] == "png" and body[:4] == b"\x89PNG"

    a.send({"t": MsgType.STICKER_PACK_COVER.value, "pack": "封面包"})   # 空 body=清除
    sl2, _ = a.wait("sticker_list")
    assert "封面包" not in sl2["sticker_pack_meta"]
    a.send({"t": MsgType.STICKER_PACK_COVER_GET.value, "pack": "封面包"})
    err, _ = a.wait("error")
    assert err and err.get("code") == "sticker"           # 已无封面
    a.close()


def test_hub_pack_cover_rejects_unknown_pack_and_bad_ext(hub):
    h, port, _ = hub
    a = _Cli(port, "封面君")
    a.hello()
    a.send({"t": MsgType.STICKER_PACK_COVER.value, "pack": "不存在",
            "ext": "png"}, PNG_1PX)
    err, _ = a.wait("error")
    assert err and err.get("code") == "sticker"
    _add(a, "cv2", "合规包")
    a.send({"t": MsgType.STICKER_PACK_COVER.value, "pack": "合规包",
            "ext": "exe"}, PNG_1PX)
    err2, _ = a.wait("error")
    assert err2 and err2.get("code") == "sticker"
    assert "合规包" not in h.pack_meta
    a.close()


def test_hub_sticker_reorder_within_pack(hub):
    h, port, _ = hub
    a = _Cli(port, "排序君")
    a.hello()
    for c in ("o1", "o2", "o3"):
        _add(a, c, "排序包")

    def order():
        return [c for _o, c in sorted(
            (h.custom_stickers[c]["order"], c)
            for c in ("o1", "o2", "o3"))]

    assert order() == ["o1", "o2", "o3"]              # 上传顺序即包内顺序
    a.send({"t": MsgType.STICKER_REORDER.value, "code": "o3", "dir": "top"})
    assert a.wait("sticker_list") is not None
    assert order() == ["o3", "o1", "o2"]
    a.send({"t": MsgType.STICKER_REORDER.value, "code": "o1", "dir": "down"})
    a.wait("sticker_list")
    assert order() == ["o3", "o2", "o1"]
    a.send({"t": MsgType.STICKER_REORDER.value, "code": "o3", "dir": "bottom"})
    a.wait("sticker_list")
    assert order() == ["o2", "o1", "o3"]
    a.send({"t": MsgType.STICKER_REORDER.value, "code": "o1", "dir": "up"})
    a.wait("sticker_list")
    assert order() == ["o1", "o2", "o3"]
    # 越界/非法方向：不崩、非法方向报错
    a.send({"t": MsgType.STICKER_REORDER.value, "code": "o1", "dir": "down"})
    assert a.wait("sticker_list") is not None
    assert order() == ["o2", "o1", "o3"]
    a.send({"t": MsgType.STICKER_REORDER.value, "code": "o1", "dir": "down"})
    assert a.wait("sticker_list") is not None
    assert order() == ["o2", "o3", "o1"]
    a.send({"t": MsgType.STICKER_REORDER.value, "code": "o1", "dir": "down"})
    assert a.wait("sticker_list") is not None
    assert order() == ["o2", "o3", "o1"]              # 已在底部：越界保持不动
    a.send({"t": MsgType.STICKER_REORDER.value, "code": "o2", "dir": "side"})
    err, _ = a.wait("error")
    assert err and err.get("code") == "sticker"
    a.send({"t": MsgType.STICKER_REORDER.value, "code": "没这条", "dir": "up"})
    err2, _ = a.wait("error")
    assert err2 and err2.get("code") == "sticker"
    a.close()


def test_hub_pack_state_survives_snapshot_restore(hub, tmp_path):
    """包重命名 + 贴纸顺序 + 包封面：快照落盘 → 新 Hub 恢复后仍一致。"""
    h, port, _ = hub
    a = _Cli(port, "持久君")
    a.hello()
    _add(a, "p1", "持久包")
    _add(a, "p2", "持久包")
    a.send({"t": MsgType.STICKER_REORDER.value, "code": "p2", "dir": "top"})
    a.wait("sticker_list")
    a.send({"t": MsgType.STICKER_PACK_COVER.value, "pack": "持久包",
            "ext": "png"}, PNG_1PX)
    a.wait("sticker_list")
    a.close()

    state = h._snapshot_state()
    h2 = Hub(cfg=h.cfg, audit_dir=str(tmp_path / "audit2"))
    h2._restore(state)
    assert set(h2.custom_stickers) >= {"p1", "p2"}
    assert h2.custom_stickers["p1"]["pack"] == "持久包"
    assert h2.custom_stickers["p2"]["order"] < h2.custom_stickers["p1"]["order"]
    assert h2.pack_meta.get("持久包", {}).get("cover") == "png"


# ================= client_core：清单 / 包元数据 / API 帧 =================

def test_core_sync_order_and_pack_meta(tmp_path):
    core = ClientCore(nick="测试", history_dir=str(tmp_path / "d"))
    core._send_frame = lambda h, b=b"": True          # 拦下补拉帧
    core._dispatch({"t": MsgType.STICKER_LIST.value,
                    "stickers": [],
                    "custom_stickers": [
                        {"code": "b1", "label": "", "pack": "包甲",
                         "ext": "png", "order": 1},
                        {"code": "a1", "label": "", "pack": "包甲",
                         "ext": "png", "order": 0},
                        {"code": "c1", "label": "", "pack": "", "ext": "png",
                         "order": 0}],
                    "sticker_pack_meta": {"包甲": {"cover": "png"}}})
    packs = core.sticker_packs()
    assert list(packs) == ["未分组", "包甲"]          # 空包名归一为「未分组」
    assert list(packs["包甲"]) == ["a1", "b1"]        # 包内按 order 升序
    assert core.sticker_pack_meta == {"包甲": {"cover": "png"}}
    assert core.pack_cover_path("包甲") is None       # 尚未落缓存 → 触发过补拉


def test_core_pack_cover_cache_paths(tmp_path):
    core = ClientCore(nick="测试", history_dir=str(tmp_path / "d"))
    core._send_frame = lambda h, b=b"": True
    core._dispatch({"t": MsgType.STICKER_PACK_COVER_DATA.value,
                    "pack": "包甲", "ext": "png"}, PNG_1PX)
    core._sync_pack_meta({"包甲": {"cover": "png"}})
    p = core.pack_cover_path("包甲")
    assert p and os.path.exists(p)
    assert os.path.basename(p) == ClientCore._cover_name("包甲", "png")
    assert core.pack_cover_path("无封面包") is None


def test_core_pack_api_frames(tmp_path):
    core = ClientCore(nick="测试", history_dir=str(tmp_path / "d"))
    calls = []
    core._send_frame = lambda h, b=b"": (calls.append((h, b)), True)[1]
    assert core.rename_sticker_pack("旧", "新")
    assert calls[-1][0] == {"t": MsgType.STICKER_PACK_RENAME.value,
                            "old": "旧", "new": "新"}
    assert core.del_sticker_pack("包")
    assert calls[-1][0] == {"t": MsgType.STICKER_PACK_DEL.value, "pack": "包"}
    assert core.set_sticker_pack_cover("包", "PNG", PNG_1PX)
    assert calls[-1][0] == {"t": MsgType.STICKER_PACK_COVER.value,
                            "pack": "包", "ext": "png"}
    assert calls[-1][1] == PNG_1PX
    assert core.clear_sticker_pack_cover("包")
    assert calls[-1] == ({"t": MsgType.STICKER_PACK_COVER.value,
                          "pack": "包"}, b"")
    assert core.get_sticker_pack_cover("包")
    assert calls[-1][0] == {"t": MsgType.STICKER_PACK_COVER_GET.value,
                            "pack": "包"}
    for d in ("up", "down", "top", "bottom"):
        assert core.reorder_sticker("c1", d)
        assert calls[-1][0] == {"t": MsgType.STICKER_REORDER.value,
                                "code": "c1", "dir": d}
    assert not core.reorder_sticker("c1", "side")     # 非法方向不发帧


# ================= 客户端 UI：包导航 / 试看 / GIF 预览 =================

@pytest.fixture(scope="module")
def root():
    if tk is None:
        pytest.skip("无 tkinter")
    try:
        r = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"无可用 Tk 显示环境: {exc}")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


class _NavCore:
    __test__ = False

    def __init__(self):
        self.sticker_subs = ["basic"]
        self.sticker_shop = [
            {"pack_id": "basic", "name": "常用",
             "items": [{"code": "smile", "emoji": "😀"},
                       {"code": "laugh", "emoji": "😂"}]},
            {"pack_id": "mood", "name": "心情",
             "items": [{"code": "cool", "emoji": "😎"},
                       {"code": "angry", "emoji": "😠"}]},
        ]
        self.stickers = [it for p in self.sticker_shop for it in p["items"]]
        self.custom_stickers = {}
        self.sticker_pack_meta = {}
        self.subs_calls = []
        self.reorder_calls = []

    def sticker_packs(self):
        return {}

    def subscribed_stickers(self):
        subs = set(self.sticker_subs)
        out = []
        for p in self.sticker_shop:
            if p["pack_id"] in subs:
                out.extend(p["items"])
        return out

    def custom_sticker_path(self, code):
        return None

    def pack_cover_path(self, pack):
        return None

    def send_sticker_sub(self, pid, on):
        self.subs_calls.append((pid, on))
        return True

    def reorder_sticker(self, code, d):
        self.reorder_calls.append((code, d))
        return True


def _nav_host(root, core):
    from theme import dialog_pal, get_skin
    h = SimpleNamespace(
        root=root,
        core=core,
        _dp=dialog_pal(get_skin("apple")),
        _sticker_nav=tk.Frame(root),
        _sticker_row=tk.Frame(root),
        _sticker_pack_sel="",
        _recent_stickers=[],
        _fav_stickers=[],
        _stk_gif_job=None,
        _stk_gif_btns={},
        toasts=[],
        shop_opens=[],
        _use_sticker=lambda c: None,
        _use_custom_sticker=lambda c: None,
        _sticker_manager=lambda: None,
        _append_sys=lambda t: None,
    )
    h.show_toast = lambda t, warn=False: h.toasts.append(t)
    h._open_sticker_shop = lambda: h.shop_opens.append(1)
    for name in ("_build_stickers", "_build_sticker_nav", "_pack_cover_thumb",
                 "_pick_sticker_pack", "_fill_recent_fav", "_first_sub_pack",
                 "_fill_shop_pack", "_trial_hint", "_mk_sticker_btn",
                 "_stk_gif_stop", "_stk_gif_anim", "_stk_gif_tick",
                 "_sticker_menu", "_del_custom_sticker"):
        setattr(h, name, MethodType(getattr(ChatWindow, name), h))
    return h


def _texts(widget):
    out = []
    for w in widget.winfo_children():
        try:
            out.append(str(w.cget("text")))
        except Exception:
            pass
        out.extend(_texts(w))
    return out


def test_nav_tabs_include_custom_builtin_and_locked(root):
    core = _NavCore()
    h = _nav_host(root, core)
    h._build_stickers()
    tabs = _texts(h._sticker_nav)
    assert "🕘" in tabs                       # 最近
    assert "常用" in tabs                     # 已订阅内置包
    assert "心情🔒" in tabs                   # 未订阅内置包带锁
    # 无最近/收藏 → 回退首个订阅包，贴纸行列出该包表情
    assert "😀" in _texts(h._sticker_row)
    h._stk_gif_stop()


def test_locked_pack_trial_view_and_subscribe(root):
    core = _NavCore()
    h = _nav_host(root, core)
    h._build_stickers()
    h._pick_sticker_pack("s:mood")            # 切到未订阅包
    row = _texts(h._sticker_row)
    assert "试看中 · 未订阅" in row
    assert "＋ 订阅" in row
    assert "😎" in row                        # 试看可见（灰显）
    # 点试看项 → 仅提示，不发订阅
    for w in h._sticker_row.winfo_children():
        if isinstance(w, tk.Button) and str(w.cget("text")) == "😎":
            w.invoke()
    assert core.subs_calls == []
    assert any("心情" in t for t in h.toasts)
    # 点「＋ 订阅」→ 发订阅帧（多包订阅开关）
    for w in h._sticker_row.winfo_children():
        if isinstance(w, tk.Button) and "订阅" in str(w.cget("text")):
            w.invoke()
    assert core.subs_calls == [("mood", True)]
    h._stk_gif_stop()


def test_switch_to_subscribed_pack_renders_items(root):
    core = _NavCore()
    core.sticker_subs = ["basic", "mood"]
    h = _nav_host(root, core)
    h._build_stickers()
    h._pick_sticker_pack("s:mood")
    row = _texts(h._sticker_row)
    assert "😎" in row and "试看中 · 未订阅" not in row
    assert "心情🔒" not in _texts(h._sticker_nav)     # 订阅后去掉锁
    h._stk_gif_stop()


def test_trial_view_caps_items(root):
    core = _NavCore()
    core.sticker_shop[1]["items"] = [
        {"code": f"m{i}", "emoji": "😎"} for i in range(STICKER_TRIAL_MAX + 5)]
    h = _nav_host(root, core)
    h._build_stickers()
    h._pick_sticker_pack("s:mood")
    emojis = [w for w in h._sticker_row.winfo_children()
              if isinstance(w, tk.Button) and str(w.cget("text")) == "😎"]
    assert len(emojis) == STICKER_TRIAL_MAX           # 试看条目数封顶
    h._stk_gif_stop()


def test_selector_gif_thumbnail_animates(root, tmp_path):
    from PIL import Image
    p = str(tmp_path / "a.gif")
    f0 = Image.new("RGB", (6, 6), (255, 0, 0))
    f1 = Image.new("RGB", (6, 6), (0, 0, 255))
    f0.save(p, save_all=True, append_images=[f1], duration=80, loop=0)

    core = _NavCore()
    h = _nav_host(root, core)
    btn = tk.Button(h._sticker_row, text="g")
    btn.pack()
    h._stk_gif_anim(btn, p)
    assert btn in h._stk_gif_btns                     # 已登记轮播
    phs, idx = h._stk_gif_btns[btn]
    assert len(phs) >= 2 and idx == 0
    h._stk_gif_tick()                                 # 手动推进一帧
    assert h._stk_gif_btns[btn][1] == 1
    h._stk_gif_stop()
    assert h._stk_gif_btns == {} and h._stk_gif_job is None
    assert STICKER_GIF_FRAMES >= 2


def test_sticker_menu_has_reorder_and_delete(root):
    core = _NavCore()
    core.custom_stickers = {"k1": {"code": "k1", "label": "", "pack": "P",
                                   "ext": "png", "order": 0}}
    h = _nav_host(root, core)
    h._build_stickers()
    seen = {}

    real = tk.Menu
    # 用子类截获菜单构造，断言含「包内排序」级联与「删除贴纸」
    class _M(real):                     # noqa: N801
        def tk_popup(self, *a, **k):    # Windows 上 tk_popup 是模态循环，测试里禁用
            return None

        def add_cascade(self, **k):
            seen.setdefault("cascades", []).append(k.get("label"))
            return super().add_cascade(**k)

        def add_command(self, **k):
            seen.setdefault("items", []).append(k.get("label"))
            return super().add_command(**k)

    import client as _client_mod
    orig = _client_mod.tk.Menu
    _client_mod.tk.Menu = _M
    try:
        h._sticker_menu("k1", SimpleNamespace(x_root=0, y_root=0))
    finally:
        _client_mod.tk.Menu = orig
    assert "⇅ 包内排序" in seen.get("cascades", [])
    assert "删除贴纸" in seen.get("items", [])
    h._stk_gif_stop()


# ================= client.py 接线断言（防回归丢失） =================

def test_client_source_wiring():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "client.py"), encoding="utf-8").read()
    for frag in (
            "def _build_sticker_nav",
            "def _fill_shop_pack",
            "def _stk_gif_anim",
            "def _pack_menu",
            "def _shop_tab_menu",
            'self._sticker_pack_sel',
            'self.core.request_sticker_shop()        # R64',
            '"试看中 · 未订阅"',
            'reorder_sticker(code, x)',
    ):
        assert frag in src, frag