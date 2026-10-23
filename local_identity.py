"""Validated local storage identity for an authenticated client session."""

import os
import re
import stat
from pathlib import Path


_SCOPE = re.compile(r"[0-9a-f]{32}\Z")


def durable_identity(auth, uid):
    """Return a stable store/UID pair, or None for a non-durable server."""
    if type(uid) is not int or uid <= 0:
        raise ValueError("invalid local account UID")
    if not isinstance(auth, dict) or auth.get("store_mode") != "durable":
        return None
    scope = auth.get("store_scope_id")
    if type(scope) is not str or _SCOPE.fullmatch(scope) is None:
        return None
    return scope, uid


def scoped_directory(root, identity):
    """Create a v2 account directory, refusing reparse paths at every level."""
    scope, uid = identity
    base = Path(root).absolute()
    target = base / "v2" / scope / f"uid-{uid}"
    for path in (*reversed(base.parents), base, base / "v2", base / "v2" / scope, target):
        if path.exists() or path.is_symlink():
            info = os.lstat(path)
            if (stat.S_ISLNK(info.st_mode)
                    or getattr(info, "st_file_attributes", 0) & 0x400
                    or not stat.S_ISDIR(info.st_mode)):
                raise OSError("local history path is not a plain directory")
        else:
            path.mkdir()
    return str(target)


def plain_cache_leaf(parent, name):
    """Validate a single account-owned media cache target before overwrite."""
    if not name or os.path.basename(name) != name or name in (".", ".."):
        raise OSError("local media cache name is not a plain leaf")
    path = os.path.join(parent, name)
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return path
    if (not stat.S_ISREG(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & 0x400):
        raise OSError("local media cache leaf is not a plain file")
    return path
