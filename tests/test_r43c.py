# -*- coding: utf-8 -*-
"""R43C 高分屏 DPI 适配回归：进程级声明降级链 / 真实 DPI 缩放校正。

- apply_early：禁用/非 Windows 直接 False；Windows 上三级 API 降级不抛错；
- fix_scaling：按系统 DPI 显式钉 tk scaling 并返回 dpi/96 因子；
  非 Windows 恒 96 → 因子 1.0 零影响。
"""
import pytest

import dpi
from dpi import apply_early, fix_scaling, _system_dpi


def test_apply_early_disabled(monkeypatch):
    monkeypatch.setattr(dpi.os, "name", "nt")
    assert apply_early(False) is False               # prefs 关闭 → 不声明


def test_apply_early_non_windows(monkeypatch):
    monkeypatch.setattr(dpi.os, "name", "posix")
    assert apply_early(True) is False                # 非 Windows 静默跳过


def test_system_dpi_non_windows_is_96(monkeypatch):
    monkeypatch.setattr(dpi.os, "name", "posix")
    assert _system_dpi() == 96.0


def test_system_dpi_windows_finite():
    if dpi.os.name != "nt":
        pytest.skip("仅 Windows 有真实系统 DPI")
    d = _system_dpi()
    assert d >= 96.0                                 # 声明后不会返回虚拟化 96 以下


def test_fix_scaling_pins_and_returns_factor(monkeypatch):
    class _Recorder:
        def __init__(self):
            self.calls = []

        def call(self, *args):
            self.calls.append(args)

    class _FakeRoot:
        def __init__(self):
            self.tk = _Recorder()

    monkeypatch.setattr(dpi.os, "name", "nt")
    monkeypatch.setattr(dpi, "_system_dpi", lambda: 144.0)
    fake = _FakeRoot()
    scale = fix_scaling(fake)
    assert fake.tk.calls == [("tk", "scaling", 2.0)]   # 144/72
    assert scale == pytest.approx(1.5)                 # 144/96


def test_fix_scaling_non_windows_noop(monkeypatch):
    class _Recorder:
        def __init__(self):
            self.calls = []

        def call(self, *args):
            self.calls.append(args)

    class _FakeRoot:
        def __init__(self):
            self.tk = _Recorder()

    monkeypatch.setattr(dpi.os, "name", "posix")
    monkeypatch.setattr(dpi, "_system_dpi", lambda: 96.0)   # posix 实现恒返 96
    fake = _FakeRoot()
    assert fix_scaling(fake) == 1.0
    assert fake.tk.calls == []                         # 非 Windows 不动 scaling
