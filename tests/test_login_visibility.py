# -*- coding: utf-8 -*-
"""Login window visibility and modal focus regressions.

These tests exercise the real Tk windows, but replace service discovery with a
small in-memory stub.  The login gate must be usable while its self-owned Tk
root is withdrawn; a withdrawn/override-redirect root must not become the
Windows owner of the visible login Toplevel.
"""
from __future__ import annotations

import threading
import time
import tkinter as tk

import pytest

import widgets.login_box as login_box
from prefs import Prefs


class _FakeDiscovery:
    """No-network DiscoveryClient replacement for modal Tk tests."""

    instances = []

    def __init__(self, *_args, **_kwargs):
        self.stop = threading.Event()
        self.started = False
        self.__class__.instances.append(self)

    def start(self):
        self.started = True

    def candidates(self):
        return []


@pytest.fixture(scope="module")
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"无可用 Tk 显示环境: {error}")
    root.geometry("480x320+80+80")
    root.withdraw()
    yield root
    try:
        for child in list(root.winfo_children()):
            if child.winfo_exists():
                try:
                    child.grab_release()
                except tk.TclError:
                    pass
                child.destroy()
        root.grab_release()
    except tk.TclError:
        pass
    try:
        root.destroy()
    except tk.TclError:
        pass


@pytest.fixture(autouse=True)
def clean_tk_root(tk_root):
    """Keep one Tcl interpreter for the module; reset child windows per test."""
    yield
    try:
        for child in list(tk_root.winfo_children()):
            if child.winfo_exists():
                try:
                    child.grab_release()
                except tk.TclError:
                    pass
                child.destroy()
        tk_root.grab_release()
        tk_root.overrideredirect(False)
        tk_root.withdraw()
        tk_root.update_idletasks()
    except tk.TclError:
        pass


@pytest.fixture(autouse=True)
def no_network_discovery(monkeypatch):
    _FakeDiscovery.instances = []
    monkeypatch.setattr(login_box, "DiscoveryClient", _FakeDiscovery)


def _pump(root, seconds: float) -> None:
    """Run the Tk event queue for a bounded interval without mainloop()."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            root.update()
        except tk.TclError:
            return
        time.sleep(0.01)
    try:
        root.update()
    except tk.TclError:
        pass


def _is_alive(widget) -> bool:
    try:
        return bool(widget.winfo_exists())
    except tk.TclError:
        return False


def _assert_mapped_visible(win) -> None:
    assert win.state() == "normal"
    assert win.winfo_ismapped(), "登录窗没有映射到桌面"
    assert win.winfo_viewable(), "登录窗不可见"
    assert win.winfo_width() > 1 and win.winfo_height() > 1


def _new_hidden_dialog(root, tmp_path, **kwargs):
    root.overrideredirect(True)
    root.withdraw()
    return login_box.LoginDialog(
        root,
        Prefs(str(tmp_path / "prefs.json")),
        default_host="127.0.0.1",
        default_port=9527,
        **kwargs,
    )


def test_withdrawn_overrideredirect_owner_maps_dialog_and_grab(tk_root, tmp_path):
    """The self-owned hidden root must not hide its login Toplevel."""
    box = _new_hidden_dialog(tk_root, tmp_path, owner_hidden=True)
    try:
        _pump(tk_root, 0.15)
        _assert_mapped_visible(box.dlg)
        assert not box.dlg.transient(), (
            "withdrawn self-owned root must not be wm transient owner"
        )
        assert box.dlg.grab_current() is box.dlg
        assert box.dlg.focus_get() is box._nick_ent
    finally:
        if _is_alive(box.dlg):
            box._cancel()
        _pump(tk_root, 0.05)
    assert not _is_alive(box.dlg)
    assert tk_root.grab_current() is None
    assert box._raise_job is None
    assert _FakeDiscovery.instances
    assert all(item.stop.is_set() for item in _FakeDiscovery.instances)


def test_iconic_parent_does_not_become_transient_owner(tk_root, tmp_path):
    """An iconified visible parent must not hide or own the login Toplevel."""
    tk_root.deiconify()
    tk_root.update_idletasks()
    tk_root.update()
    tk_root.iconify()
    _pump(tk_root, 0.08)
    assert tk_root.state() == "iconic"
    box = login_box.LoginDialog(
        tk_root,
        Prefs(str(tmp_path / "iconic-prefs.json")),
        default_host="127.0.0.1",
        default_port=9527,
        owner_hidden=False,
    )
    try:
        _pump(tk_root, 0.15)
        _assert_mapped_visible(box.dlg)
        assert not box.dlg.transient()
    finally:
        if _is_alive(box.dlg):
            box._cancel()
        _pump(tk_root, 0.05)
    assert _is_alive(tk_root), "关闭登录窗不应销毁可见/图标化宿主"
    assert tk_root.grab_current() is None
    assert box._raise_job is None
    assert box._poll_job is None
    assert box._disco is None
    assert _FakeDiscovery.instances
    assert all(item.stop.is_set() for item in _FakeDiscovery.instances)


def test_visible_parent_keeps_transient_relationship(tk_root, tmp_path):
    """A normal visible parent keeps the existing transient modal behavior."""
    tk_root.deiconify()
    tk_root.update_idletasks()
    tk_root.update()
    box = login_box.LoginDialog(
        tk_root,
        Prefs(str(tmp_path / "prefs.json")),
        default_host="127.0.0.1",
        default_port=9527,
        owner_hidden=False,
    )
    try:
        _pump(tk_root, 0.15)
        _assert_mapped_visible(box.dlg)
        assert str(box.dlg.transient()) == str(tk_root)
        assert box.dlg.grab_current() is box.dlg
    finally:
        if _is_alive(box.dlg):
            box._cancel()
        _pump(tk_root, 0.05)
    assert _is_alive(tk_root)
    assert tk_root.grab_current() is None


def test_foreground_retry_does_not_steal_password_focus(tk_root, tmp_path, monkeypatch):
    """The delayed foreground retry runs and leaves an already focused password field."""
    calls = []

    # The repaired implementation exposes the helper at module level.  The
    # fallback setattr keeps this test importable on the pre-fix checkout; the
    # old nested helper then records no calls and fails this regression.
    monkeypatch.setattr(
        login_box,
        "_force_foreground",
        lambda win: calls.append(win),
        raising=False,
    )
    box = _new_hidden_dialog(tk_root, tmp_path, owner_hidden=True)
    try:
        box._pwd_ent.focus_force()
        tk_root.update_idletasks()
        _pump(tk_root, 0.55)
        assert len(calls) >= 2, "缺少创建后和约 400ms 后的前台重试"
        assert box.dlg.focus_get() is box._pwd_ent
    finally:
        if _is_alive(box.dlg):
            box._cancel()
        _pump(tk_root, 0.05)


def test_escape_releases_grab_and_cancels_retry(tk_root, tmp_path, monkeypatch):
    """Escape follows cancel semantics and no delayed job touches a dead dialog."""
    calls = []
    monkeypatch.setattr(
        login_box,
        "_force_foreground",
        lambda win: calls.append(win),
        raising=False,
    )
    box = _new_hidden_dialog(tk_root, tmp_path, owner_hidden=True)
    _pump(tk_root, 0.12)
    assert box.dlg.grab_current() is box.dlg
    box.dlg.event_generate("<Escape>")
    _pump(tk_root, 0.12)
    assert not _is_alive(box.dlg)
    assert tk_root.grab_current() is None
    assert box._poll_job is None
    assert box._disco is None
    assert box._raise_job is None
    assert _FakeDiscovery.instances
    assert all(item.stop.is_set() for item in _FakeDiscovery.instances)
    before = len(calls)
    _pump(tk_root, 0.48)
    assert len(calls) == before


def _run_autoclose_login(monkeypatch, prefs, host, *, submit: bool):
    """Run one real self-owned show_login call and close it from Tk's queue."""
    created = []
    real_cls = login_box.LoginDialog

    class _ProbeDialog(real_cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)
            self._mapped_at_creation = bool(
                self.dlg.winfo_ismapped() and self.dlg.winfo_viewable()
            )
            if submit:
                self._nick_ent.insert(0, "登录测试账号")
                self._pwd_ent.insert(0, "测试密码")
                self.dlg.after(90, self._login)
            else:
                self.dlg.after(90, self._cancel)

    # Reuse the module's real Tcl interpreter.  show_login normally creates a
    # fresh Tk root and destroys it; a second Tk interpreter is unreliable on
    # Python 3.14/Tk 8.6 Windows.  A real withdrawn Toplevel is equivalent as
    # the self-owned Tcl host for this visibility contract.
    monkeypatch.setattr(login_box.tk, "Tk", lambda: host)
    monkeypatch.setattr(login_box, "LoginDialog", _ProbeDialog)
    result = login_box.show_login(
        master=None,
        prefs=prefs,
        default_host="127.0.0.1",
        default_port=9527,
    )
    assert created, "show_login 没有创建真实 LoginDialog"
    return result, created[0]


def test_show_login_self_owned_submit_destroys_hidden_root(
    tk_root, monkeypatch, tmp_path
):
    host = tk.Toplevel(tk_root)
    result, box = _run_autoclose_login(
        monkeypatch,
        Prefs(str(tmp_path / "submit-prefs.json")),
        host,
        submit=True,
    )
    assert result == {
        "nick": "登录测试账号",
        "pwd": "测试密码",
        "host": "127.0.0.1",
        "port": 9527,
        "name": "手动指定",
        "remember": False,
    }
    assert box._mapped_at_creation
    assert not _is_alive(box.dlg)
    assert box._poll_job is None
    assert box._disco is None
    assert box._raise_job is None
    assert not _is_alive(host), "show_login finally 必须销毁自有宿主"
    assert _FakeDiscovery.instances
    assert all(item.stop.is_set() for item in _FakeDiscovery.instances)


def test_show_login_self_owned_cancel_and_relogin_stay_visible(
    tk_root, monkeypatch, tmp_path
):
    prefs = Prefs(str(tmp_path / "cancel-prefs.json"))
    seen = []
    mapped = []
    real_cls = login_box.LoginDialog

    class _ProbeDialog(real_cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            seen.append(self)
            mapped.append(bool(self.dlg.winfo_ismapped() and
                               self.dlg.winfo_viewable()))
            self.dlg.after(90, self._cancel)

    monkeypatch.setattr(login_box, "LoginDialog", _ProbeDialog)
    hosts = []
    for _ in range(2):
        host = tk.Toplevel(tk_root)
        hosts.append(host)
        monkeypatch.setattr(login_box.tk, "Tk", lambda host=host: host)
        assert login_box.show_login(prefs=prefs) is None
    assert len(seen) == 2
    assert mapped == [True, True]
    for box in seen:
        assert not _is_alive(box.dlg)
        assert box._poll_job is None
        assert box._disco is None
        assert box._raise_job is None
    assert all(not _is_alive(host) for host in hosts)
    assert _FakeDiscovery.instances
    assert all(item.stop.is_set() for item in _FakeDiscovery.instances)


def test_unviewable_dialog_times_out_and_self_owned_show_login_cleans_up(
    tk_root, monkeypatch, tmp_path
):
    """A never-viewable Toplevel must cancel within the configured bound."""
    host = tk.Toplevel(tk_root)
    seen = []
    real_cls = login_box.LoginDialog
    real_toplevel = login_box.tk.Toplevel

    class _NeverViewableToplevel(real_toplevel):
        def winfo_viewable(self):
            return False

    class _ProbeDialog(real_cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            seen.append(self)

    monkeypatch.setattr(login_box, "LoginDialog", _ProbeDialog)
    monkeypatch.setattr(login_box.tk, "Toplevel", _NeverViewableToplevel)
    monkeypatch.setattr(login_box.tk, "Tk", lambda: host)
    monkeypatch.setattr(login_box, "_VISIBILITY_TIMEOUT_MS", 50, raising=False)

    started = time.monotonic()
    result = login_box.show_login(
        master=None,
        prefs=Prefs(str(tmp_path / "unviewable-prefs.json")),
        default_host="127.0.0.1",
        default_port=9527,
    )
    elapsed = time.monotonic() - started

    assert result is None
    assert elapsed < 1.0, "无法映射的登录窗不能让 show_login 无限等待"
    assert seen, "show_login 应保留被取消的 partial LoginDialog 供清理"
    box = seen[0]
    assert not _is_alive(box.dlg)
    assert box._raise_job is None
    assert box._poll_job is None
    assert box._disco is None
    assert not _is_alive(host), "自有 host 必须在 show_login finally 销毁"
    assert tk_root.grab_current() is None
    assert all(item.stop.is_set() for item in _FakeDiscovery.instances)
