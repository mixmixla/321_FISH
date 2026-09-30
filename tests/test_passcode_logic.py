# -*- coding: utf-8 -*-
"""test_passcode_logic.py —— PasscodeBox / LockOverlay 判定逻辑（R8/R10，不建 Tk）。"""
import auth
from widgets.passcode import PasscodeBox
from widgets.lock_screen import LockOverlay


def _decide(code, guard, check):
    return PasscodeBox._decide(None, code, guard, check)


def _lock_decide(code, guard, check):
    return LockOverlay._decide(None, code, guard, check)


def test_correct():
    g = auth.FloodGuard()
    assert _decide("p", g, lambda c: c == "p") == ("ok", None)
    assert g.allowed()          # 成功不清除计数所需 dt，但 ok() 清零


def test_wrong_fails_and_guard():
    g = auth.FloodGuard(max_attempts=2, window=5)
    assert _decide("x", g, lambda c: False)[0] == "err"
    assert _decide("x", g, lambda c: False)[0] == "err"
    assert not g.allowed()      # 达阈值锁定
    assert _decide("x", g, lambda c: False)[0] == "err" and "频繁" in _decide("x", g, lambda c: False)[1]


def test_empty_rejected():
    g = auth.FloodGuard()
    assert _decide("   ", g, lambda c: True)[0] == "err"


def test_flood_blocked_even_correct():
    g = auth.FloodGuard(max_attempts=1, window=5)
    _decide("x", g, lambda c: False)
    assert not g.allowed()
    assert _decide("right", g, lambda c: True)[0] == "err"  # 锁定期间连正确码也拒


# ---------- R10 LockOverlay（运行时锁屏）判定同范式 ----------
def test_lock_correct():
    g = auth.FloodGuard()
    assert _lock_decide("p", g, lambda c: c == "p") == ("ok", None)


def test_lock_wrong_and_empty():
    g = auth.FloodGuard(max_attempts=2, window=5)
    _lock_decide("x", g, lambda c: False)          # 第1次错
    _lock_decide("x", g, lambda c: False)          # 第2次错 → 达阈值
    assert not g.allowed()
    assert "频繁" in _lock_decide("x", g, lambda c: False)[1]
    assert _lock_decide("   ", g, lambda c: True)[0] == "err"  # 限频锁定连空/正确码也拒
    assert _lock_decide("right", g, lambda c: True)[0] == "err"