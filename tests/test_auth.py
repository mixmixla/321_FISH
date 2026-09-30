# -*- coding: utf-8 -*-
"""test_auth.py —— 本机解锁码哈希与限频（R8）。"""
import auth


def test_salt_unique():
    assert auth.salt() != auth.salt()


def test_make_verify_roundtrip():
    stored = auth.make("secret1")
    assert ":" in stored
    assert auth.verify("secret1", stored)
    assert not auth.verify("wrong", stored)


def test_verify_rejects_empty_and_badformat():
    assert not auth.verify("", "")
    assert not auth.verify("abc", "")
    assert not auth.verify("", "aa:bb")
    assert not auth.verify("abc", "badformat-without-colon")
    assert not auth.verify("abc", "zz:nothex")


def test_verify_differs_per_salt():
    a = auth.make("same")
    b = auth.make("same")
    assert a != b
    assert auth.verify("same", a) and auth.verify("same", b)


def test_flood_guard_locks_then_recovers():
    g = auth.FloodGuard(max_attempts=3, window=1)
    assert g.allowed()
    g.fail(); g.fail()
    assert g.allowed()
    g.fail()
    assert not g.allowed()
    assert g.remaining() > 0
    # 过冷却恢复
    import time
    g._last_try = time.time() - 2
    assert g.allowed()


def test_flood_guard_progressive_wait():
    """对齐 TG passcodeCanTry：第 max_attempts 次失败起，等待随次数递进。"""
    g = auth.FloodGuard(max_attempts=3, window=30)     # 默认阈值 3、封顶 30
    g._last_try = 0.0
    for _ in range(2):
        g.fail()
    g.fail()                                            # 第3次：5s
    assert 4.5 <= g.remaining() <= 5.0
    g.fail()                                            # 第4次：10s
    assert 9.0 <= g.remaining() <= 10.0
    g.fail()                                            # 第5次：15s
    assert 14.0 <= g.remaining() <= 15.0
    # 连错期连正确码也拒（allowed False）
    assert not g.allowed()


def test_flood_guard_ok_resets():
    g = auth.FloodGuard(max_attempts=2, window=30)
    g.fail(); g.ok()
    assert g.allowed()
    g.fail(); g.fail()
    assert not g.allowed()
    g.ok()
    assert g.allowed()