# -*- coding: utf-8 -*-
"""Login window foreground helper tests using a fake Win32 user32.

These tests deliberately never create a Tk window or call real Win32 APIs.
They protect the native handle boundary used by widgets.login_box._force_foreground.
"""
import ctypes
from types import SimpleNamespace

import pytest

import widgets.login_box as login_box


class _NativeFunction:
    """Callable fake that accepts ctypes argtypes/restype assignments."""

    def __init__(self, result=1, error=None):
        self.result = result
        self.error = error
        self.calls = []
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        self.calls.append(args)
        if self.error is not None:
            raise self.error
        return self.result


class _FakeUser32:
    def __init__(self, *, ancestor=0x1_0000_0002, is_window=1,
                 set_window_pos=1, set_foreground=1):
        self.GetAncestor = _NativeFunction(ancestor)
        self.IsWindow = _NativeFunction(is_window)
        self.SetWindowPos = _NativeFunction(set_window_pos)
        self.SetForegroundWindow = _NativeFunction(set_foreground)


class _FakeWindow:
    def __init__(self, *, hwnd=0x1_0000_0001, exists=True, viewable=True):
        self.hwnd = hwnd
        self.exists = exists
        self.viewable = viewable
        self.viewable_calls = 0

    def winfo_exists(self):
        return self.exists

    def winfo_viewable(self):
        self.viewable_calls += 1
        return self.viewable

    def winfo_id(self):
        return self.hwnd


def _install_user32(monkeypatch, user32):
    # ctypes.windll is absent on non-Windows hosts; the helper must still be
    # testable with this injected fake without touching a real desktop.
    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(user32=user32),
        raising=False,
    )


def _int_handle(value):
    if isinstance(value, ctypes.c_void_p):
        return value.value
    return int(value)


def _signed_handle(value):
    value = _int_handle(value)
    if value is None:
        return None
    bits = ctypes.sizeof(ctypes.c_void_p) * 8
    if value == (1 << bits) - 1:
        return -1
    return value


def _assert_pointer_type(tp):
    assert tp is not None
    assert ctypes.sizeof(tp) == ctypes.sizeof(ctypes.c_void_p)


def test_force_foreground_uses_root_wrapper_and_preserves_64bit_handle(monkeypatch):
    child_hwnd = 0x1_0000_0001
    root_hwnd = 0x1_0000_0002
    user32 = _FakeUser32(ancestor=root_hwnd)
    _install_user32(monkeypatch, user32)
    win = _FakeWindow(hwnd=child_hwnd)

    assert login_box._force_foreground(win) is True
    assert win.viewable_calls == 1

    assert _signed_handle(user32.GetAncestor.calls[0][0]) == child_hwnd
    assert user32.GetAncestor.calls[0][1] == 2  # GA_ROOT, not owner/parent
    assert _signed_handle(user32.IsWindow.calls[0][0]) == root_hwnd
    pos_args = user32.SetWindowPos.calls[0]
    assert _signed_handle(pos_args[0]) == root_hwnd
    assert _signed_handle(pos_args[1]) == -1  # HWND_TOPMOST
    assert tuple(pos_args[2:6]) == (0, 0, 0, 0)
    assert pos_args[6] == 0x0001 | 0x0002  # SWP_NOSIZE | SWP_NOMOVE
    assert _signed_handle(user32.SetForegroundWindow.calls[0][0]) == root_hwnd

    # Every HWND argument is pointer-sized.  Only GetAncestor returns an
    # HWND; IsWindow/SetWindowPos/SetForegroundWindow return Win32 BOOL.
    _assert_pointer_type(user32.GetAncestor.argtypes[0])
    _assert_pointer_type(user32.GetAncestor.restype)
    _assert_pointer_type(user32.IsWindow.argtypes[0])
    assert user32.IsWindow.restype is not None
    _assert_pointer_type(user32.SetWindowPos.argtypes[0])
    _assert_pointer_type(user32.SetWindowPos.argtypes[1])
    assert user32.SetWindowPos.restype is not None
    _assert_pointer_type(user32.SetForegroundWindow.argtypes[0])
    assert user32.SetForegroundWindow.restype is not None


@pytest.mark.parametrize(
    "window_kwargs, ancestor, is_window",
    [
        ({"exists": False}, 0x1_0000_0002, 1),
        ({"viewable": False}, 0x1_0000_0002, 1),
        ({}, 0, 1),
        ({}, 0x1_0000_0002, 0),
    ],
)
def test_force_foreground_rejects_missing_or_invalid_window(
    monkeypatch, window_kwargs, ancestor, is_window
):
    user32 = _FakeUser32(ancestor=ancestor, is_window=is_window)
    _install_user32(monkeypatch, user32)
    win = _FakeWindow(**window_kwargs)

    assert login_box._force_foreground(win) is False
    assert not user32.SetWindowPos.calls
    assert not user32.SetForegroundWindow.calls


@pytest.mark.parametrize("failure", ["set_window_pos", "set_foreground"])
def test_force_foreground_returns_false_on_native_failure(monkeypatch, failure):
    kwargs = {failure: 0}
    user32 = _FakeUser32(**kwargs)
    _install_user32(monkeypatch, user32)

    assert login_box._force_foreground(_FakeWindow()) is False
    if failure == "set_window_pos":
        assert user32.SetWindowPos.calls
        assert user32.SetForegroundWindow.calls
    else:
        assert user32.SetWindowPos.calls
        assert user32.SetForegroundWindow.calls


def test_force_foreground_returns_false_when_native_raises(monkeypatch):
    user32 = _FakeUser32()
    user32.SetWindowPos.error = OSError("SetWindowPos failed")
    _install_user32(monkeypatch, user32)

    assert login_box._force_foreground(_FakeWindow()) is False
    assert not user32.SetForegroundWindow.calls
