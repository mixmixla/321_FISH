"""Unreadable preference schemas must never be replaced by defaults."""

import json

import pytest

from prefs import Prefs


SCOPE = "a" * 32


@pytest.mark.parametrize("original", [
    b'[]', b'["preserve-me"]', b'null', b'"preserve-me"',
    b'42', b'1.5', b'true', b'false',
])
@pytest.mark.parametrize("operation", ["login", "setting", "uid"])
def test_non_object_root_is_preserved(tmp_path, original, operation):
    path = tmp_path / "prefs.json"
    path.write_bytes(original)
    prefs = Prefs(str(path))

    if operation == "uid":
        prefs.enable_uid_chat_view()
        assert prefs.get("drafts") == {}
        with pytest.raises(OSError, match="original file preserved"):
            prefs.bind_uid_chat_view((SCOPE, 11))
        # A failed durable binding leaves only a memory view; no delayed overwrite.
        prefs.set("drafts", {"public": "temporary"})
    elif operation == "login":
        with pytest.raises(OSError, match="original file preserved"):
            prefs.remember_login_nick("synthetic-login")
    else:
        with pytest.raises(OSError, match="original file preserved"):
            prefs.set("dnd", True)

    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".prefs-uid-*"))


@pytest.mark.parametrize("initial", [None, b'{}', b'{"custom":{"keep":17}}'])
def test_object_or_missing_prefs_remains_writable(tmp_path, initial):
    path = tmp_path / "prefs.json"
    if initial is not None:
        path.write_bytes(initial)
    prefs = Prefs(str(path))
    prefs.remember_login_nick("synthetic-login")
    prefs.set("dnd", True)
    prefs.enable_uid_chat_view()
    prefs.bind_uid_chat_view((SCOPE, 11))
    prefs.set("drafts", {"public": "synthetic-draft"})

    restored = Prefs(str(path))
    assert restored.get("dnd") is True
    restored.enable_uid_chat_view()
    restored.bind_uid_chat_view((SCOPE, 11))
    assert restored.get("drafts") == {"public": "synthetic-draft"}
    if initial and json.loads(initial).get("custom"):
        assert json.loads(path.read_bytes())["custom"] == {"keep": 17}
