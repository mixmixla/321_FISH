# -*- coding: utf-8 -*-
"""R43A1 弹窗动效：Toplevel 统一淡入。

与 R39D② 滚动缓动/气泡淡入同思路：Tkinter 无合成器，动效一律 after
插值（30ms 帧距 ≈33fps）。设计期曾计划「滑入」，实测与各对话框创建后
自居中的 geometry 二次定位互相打架（后定位会覆盖动画坐标），裁剪为
纯淡入——失败静默恢复可见，动效绝不影响窗口可用性。

用法：创建 Toplevel、设好 title 后调用 ui_fx.fade_in(dlg)。
注意：overrideredirect 窗口（气泡提示/@补全）与 ghost 挖空窗不要调用。
"""
import tkinter as tk

_STEP_MS = 30          # 帧间隔
_DEFAULT_MS = 120      # 淡入总时长
_UI_SOUND = False      # 反馈音全局开关（默认关，客户端 set_sound 门控）


def fade_in(win, ms: int = _DEFAULT_MS) -> None:
    """窗口淡入 0→1。alpha 不受支持的 WM 上原样显示（一次性探测）。"""
    try:
        win.attributes("-alpha", 0.0)      # 映射前隐身（兼作支持性探测）
    except Exception:
        return                             # 无 alpha 支持 → 直接显示
    steps = max(1, int(ms) // _STEP_MS)

    def _tick(i: int = 0) -> None:
        try:
            if not win.winfo_exists():
                return
            a = (i + 1) / steps
            win.attributes("-alpha", 1.0 if a >= 1.0 else a)
            if a < 1.0:
                win.after(_STEP_MS, _tick, i + 1)
        except Exception:
            try:
                win.attributes("-alpha", 1.0)
            except Exception:
                pass

    _tick()


def press_feedback(btn, pressed_bg: str | None = None,
                   anim_ms: int = 90) -> None:
    """R43A2 按钮按压反馈（带过渡动画）。

    - relief=raised 的普通按钮：按下凹陷、松开/离开恢复；
    - flat 工具按钮：传 pressed_bg 时按下以 hex_lerp 过渡到底色、
      松开/离开过渡还原（toggle 徽标类按钮不要调用，避免按压态与
      开关态混淆）。

    过渡用 after 插值（hex_lerp+ease_out），异常静默回退到瞬变，
    绝不影响按钮可用性（对齐 popup 淡入范式）。
    """
    def _bg_exit(btn_):
        j = getattr(btn_, "_pf_ajob", None)
        if j:
            try:
                btn_.after_cancel(j)
            except Exception:
                pass
            btn_._pf_ajob = None

    def _down(_ev):
        try:
            if str(btn["state"]) == "disabled":
                return
            r = str(btn["relief"])
            if pressed_bg and r == "flat":
                base = btn["bg"]
                btn._pf_base = base             # 记录原色（供渐变回退）
                btn._pf_bg = pressed_bg
                _bg_exit(btn)
                steps = max(1, int(anim_ms) // _STEP_MS)

                def _anim(i: int = 0):
                    if not btn.winfo_exists():
                        return
                    c = hex_lerp(base, pressed_bg, ease_out((i + 1) / steps))
                    if c is not None:
                        btn["bg"] = c
                    if i + 1 < steps:
                        btn._pf_ajob = btn.after(_STEP_MS, _anim, i + 1)
                    else:
                        btn._pf_ajob = None
                _anim()
            elif r != "flat":
                btn._pf_relief = r                # Python 属性记原 relief
                btn["relief"] = "sunken"
        except Exception:
            pass

    def _up(_ev):
        try:
            r = getattr(btn, "_pf_relief", None)
            if r is not None:
                btn._pf_relief = None
                btn["relief"] = r
        except Exception:
            pass
        try:
            base = getattr(btn, "_pf_base", None)
            pressed = getattr(btn, "_pf_bg", None)
            if base is not None and pressed is not None:
                _bg_exit(btn)
                steps = max(1, int(anim_ms) // _STEP_MS)

                def _back(i: int = 0):
                    if not btn.winfo_exists():
                        return
                    c = hex_lerp(pressed, base, ease_out((i + 1) / steps))
                    if c is not None:
                        btn["bg"] = c
                    if i + 1 < steps:
                        btn._pf_ajob = btn.after(_STEP_MS, _back, i + 1)
                    else:
                        btn._pf_ajob = None
                        btn._pf_base = None
                        btn._pf_bg = None
                _back()
        except Exception:
            pass

    try:
        btn.bind("<ButtonPress-1>", _down, add="+")
        btn.bind("<ButtonRelease-1>", _up, add="+")
        btn.bind("<Leave>", _up, add="+")
    except Exception:
        pass


# ============================================================
# 高级微交互：三态动效 + 缓动工具（全套界面通用）
# ============================================================
def ease_out(t: float) -> float:
    """ease-out cubic：0→1，渐出。动效插值用。"""
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def hex_lerp(c1: str, c2: str, t: float) -> str:
    """两个 #rrggbb 颜色按 t∈[0,1] 线性插值，返回新 hex（hover 渐变/发光用）。"""
    try:
        x = [int(c1[1 + i * 2:3 + i * 2], 16) for i in range(3)]
        y = [int(c2[1 + i * 2:3 + i * 2], 16) for i in range(3)]
        out = "".join("%02x" % round(x[i] + (y[i] - x[i]) * t) for i in range(3))
        return "#" + out
    except Exception:
        return c1


def btn3(btn, *, base=None, hover=None, pressed=None) -> None:
    """按钮三态动效：常态→hover（变色+提升+光标手）→按压（按色+凹陷）→释放回弹到 hover。

    点击时先瞬时压深、释放后按当前指针位置复原；光标统一成手型。传给很广的
    tk.Button / 扁平 Label 按钮都可。无色参时取按钮当前底色与派生色。"""
    base = base or (btn.cget("bg") if btn.cget("bg") else "#ffffff")
    hover = hover or hex_lerp(base, "#8a6f55", 0.25)   # 默认琥珀加深
    pressed = pressed or hex_lerp(base, "#8a6f55", 0.45)
    try:
        btn.configure(cursor="hand2")
    except Exception:
        pass

    def _ent(_e):
        try:
            if str(btn["state"]) == "disabled":
                return
            if not hasattr(btn, "_b3_base"):
                btn._b3_base = str(btn["bg"])
            btn["bg"] = hover
            btn["relief"] = "raised"
            btn["bd"] = 1
        except Exception:
            pass

    def _lea(_e):
        try:
            if hasattr(btn, "_b3_base"):
                btn["bg"] = btn._b3_base
            btn["relief"] = "flat"
            btn["bd"] = 0
        except Exception:
            pass

    def _prs(_e):
        try:
            btn["bg"] = pressed
            btn["relief"] = "sunken"
            btn["bd"] = 1
        except Exception:
            pass

    def _rls(_e):
        try:
            btn["bg"] = hover
            btn["relief"] = "raised"
            btn["bd"] = 1
        except Exception:
            pass

    try:
        btn.bind("<Enter>", _ent, add="+")
        btn.bind("<Leave>", _lea, add="+")
        btn.bind("<ButtonPress-1>", _prs, add="+")
        btn.bind("<ButtonRelease-1>", _rls, add="+")
    except Exception:
        pass


def click(enabled: bool = True, force: bool = False) -> None:
    """轻量界面反馈音（可选）。默认读全局 _UI_SOUND（由客户端 set_sound 门控）。

    只用于「完成一次操作」的确认感（发送消息/弹窗确定等），不做铺天盖地的
    按键音，避免在办公摸鱼场景暴露。非 Windows 或系统无声卡时静默。"""
    if not (force or (enabled and _UI_SOUND)):
        return
    try:
        import winsound
        winsound.MessageBeep(0x00000040)   # MB_ICONINFORMATION：短清脆提示音
    except Exception:
        pass


def set_sound(on: bool) -> None:
    """全局开关反馈音（客户端启动/设置时调用）。"""
    global _UI_SOUND
    _UI_SOUND = bool(on)
