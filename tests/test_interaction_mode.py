"""test_interaction_mode.py —— 交互模式（TG/微信/QQ）三件套 + 专属配色联动。

覆盖：
- MODE_CONFIG 映射（send / read_mark / layout / skin）
- 发送键绑定分支（qq=Ctrl+Enter 发送；tg/wechat=Enter 发送）
- 消息回执显隐（qq 传 read_mark=None 隐藏）
- 会话列表布局密度（LAYOUTS 三档）
- 模式切换写 prefs 并联动换肤（_set_mode → _apply_mode_skin）
"""
import tkinter as tk
from types import SimpleNamespace

import pytest

from client import MODE_CONFIG, ChatWindow
from widgets.msg_list import MsgList
from widgets.session_list import SessionList

FONT = ("PingFang SC", 12)


@pytest.fixture(scope="module")
def root():
    try:
        r = tk.Tk()
    except tk.TclError as exc:          # 无显示环境（headless CI）跳过
        pytest.skip(f"无可用 Tk 显示环境: {exc}")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
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


def test_mode_config_shape():
    """三种模式都具备 send/read_mark/layout/skin 四键且取值符合预期。"""
    modes = {"tg", "wechat", "qq"}
    assert set(MODE_CONFIG) == modes
    for m in modes:
        cfg = MODE_CONFIG[m]
        assert {"send", "read_mark", "layout", "skin"} <= set(cfg)
    assert MODE_CONFIG["tg"]["send"] == "enter"
    assert MODE_CONFIG["wechat"]["send"] == "enter"
    assert MODE_CONFIG["qq"]["send"] == "ctrl_enter"
    assert bool(MODE_CONFIG["tg"]["read_mark"])
    assert bool(MODE_CONFIG["wechat"]["read_mark"])
    assert MODE_CONFIG["qq"]["read_mark"] is None
    assert MODE_CONFIG["tg"]["layout"] == "tg"
    assert MODE_CONFIG["wechat"]["layout"] == "wechat"
    assert MODE_CONFIG["qq"]["layout"] == "qq"
    assert MODE_CONFIG["tg"]["skin"] == "apple"
    assert MODE_CONFIG["wechat"]["skin"] == "wechat"
    assert MODE_CONFIG["qq"]["skin"] == "qq"


def test_bind_send_key_branches():
    """发送键绑定：qq 模式 Return=换行/Ctrl+Return=发送；tg 模式 Shift+Return=换行。"""
    rec_tg, rec_qq = {}, {}
    entry_tg = SimpleNamespace(bind=lambda seq, fn: rec_tg.__setitem__(seq, fn))
    entry_qq = SimpleNamespace(bind=lambda seq, fn: rec_qq.__setitem__(seq, fn))
    def make_app(cfg):
        return SimpleNamespace(_mode_cfg=cfg, _on_entry_return="SEND",
                               _on_entry_newline="NEWLINE")
    ChatWindow._bind_send_key(make_app(MODE_CONFIG["tg"]), entry_tg)
    ChatWindow._bind_send_key(make_app(MODE_CONFIG["qq"]), entry_qq)
    assert {"<Return>", "<Shift-Return>"} <= set(rec_tg)
    assert "<Control-Return>" not in rec_tg
    assert {"<Return>", "<Control-Return>"} <= set(rec_qq)
    assert "<Shift-Return>" not in rec_qq


def test_read_mark_hidden_in_qq(root):
    """QQ 模式（read_mark=None）：自己的已读消息行头不含 read_mark 段。"""
    def mark(prefix, rm):
        m = MsgList(root, FONT, read_mark=rm)
        m.set_me_uid(2)
        m.append({"uid": 2, "nick": "我", "channel": "public",
                  "ts": __import__("time").time(), "text": "读了吗", "seq": 12})
        m.set_reads({"1": 12})
        segs = m._heading_segs(m._rows[0], False, True)
        m.destroy()
        return segs
    segs_qq = mark("qq", None)
    assert all(k != "read_mark" for _t, k in segs_qq)
    segs_tg = mark("tg", "✓已读  ")          # tg/wechat 显示回执
    assert any(k == "read_mark" for _t, k in segs_tg)


def test_session_layout_params():
    """会话列表三档布局密度：tg56 / wechat64 / qq50，qq 角标更高。"""
    assert SessionList.LAYOUTS["tg"]["ROW_H"] == 56
    assert SessionList.LAYOUTS["wechat"]["ROW_H"] == 64
    assert SessionList.LAYOUTS["qq"]["ROW_H"] == 50
    assert SessionList.LAYOUTS["qq"]["BADGE_H"] == 20


def test_set_mode_writes_prefs_and_skins():
    """切换交互模式：写 prefs + 更新 mode_cfg + 触发 _apply_mode_skin（换肤联动）。"""
    recorded = {}
    class Stub:
        def __init__(self):
            self._prefs = type("P", (), {
                "set": lambda _self, k, v: recorded.__setitem__(k, v)})()
            self.skins = []
        def _apply_mode_skin(self):
            if getattr(self, "_mode_cfg", {}).get("skin"):
                self.skins.append(self._mode_cfg["skin"])
    app = Stub()
    ChatWindow._set_mode(app, "qq")
    assert recorded == {"interaction_mode": "qq"}
    assert app._mode_cfg is MODE_CONFIG["qq"]        # 由 _set_mode 赋值
    assert app.skins == ["qq"]