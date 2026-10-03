# -*- coding: utf-8 -*-
"""隔离逐文件门禁的子进程安全边界。

这个模块有两种用途：门禁子进程启动时安装网络、设备和 Agent 防护；在
Windows 上为 Tk 用例提供一个不抢当前桌面的 private desktop 进程入口。
默认环境不会安装任何 monkeypatch，因此普通 ``pytest`` 行为保持不变。
"""

from __future__ import annotations

import builtins
import ctypes
from ctypes import wintypes
import importlib
import ipaddress
import json
import os
from pathlib import Path
import socket as _socket
import subprocess as _subprocess
import sys
import threading
import time
import uuid


class NetworkBlocked(OSError):
    """门禁子进程尝试访问非回环网络。"""


class AgentBlocked(RuntimeError):
    """门禁子进程尝试载入或启动真实 Agent 工具。"""


class DeviceBlocked(RuntimeError):
    """门禁子进程尝试打开真实摄像头或麦克风。"""


_ORIGINAL_SOCKET = _socket.socket
_ORIGINAL_CREATE_CONNECTION = _socket.create_connection
_ORIGINAL_GETADDRINFO = _socket.getaddrinfo
_ORIGINAL_GETHOSTBYNAME = _socket.gethostbyname
_ORIGINAL_IMPORT = builtins.__import__
_ORIGINAL_IMPORT_MODULE = importlib.import_module
_ORIGINAL_POPEN = _subprocess.Popen
_STATE: dict = {
    "installed": False,
    "events": [],
    "blocked": 0,
    "remapped": 0,
    "lock": threading.Lock(),
}
_MAX_EVENTS = 200


def _record(action: str, **detail) -> None:
    """只记录策略事实，不记录请求正文、环境值或凭据。"""
    with _STATE["lock"]:
        if action in {"network_blocked", "agent_blocked", "device_blocked"}:
            _STATE["blocked"] += 1
        if action in {"network_bind_remapped", "network_broadcast_remapped"}:
            _STATE["remapped"] += 1
        if len(_STATE["events"]) < _MAX_EVENTS:
            event = {"action": action, "at": time.time()}
            event.update({str(k): _safe_detail(v) for k, v in detail.items()})
            _STATE["events"].append(event)


def _safe_detail(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (tuple, list)):
        return [_safe_detail(v) for v in value[:4]]
    return type(value).__name__


def _host_from_address(address):
    if isinstance(address, tuple) and address:
        return address[0]
    return address


def _replace_host(address, host):
    if not isinstance(address, tuple) or not address:
        return address
    values = list(address)
    values[0] = host
    return tuple(values)


def _classify_host(host):
    """Return ``loopback``, ``wildcard``, ``broadcast`` or ``external``."""
    if host is None or host == "":
        return "wildcard"
    text = str(host).strip().strip("[]").lower()
    if text == "localhost":
        return "loopback"
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return "external"
    if ip.is_loopback:
        return "loopback"
    if ip.is_unspecified:
        return "wildcard"
    if ip.is_multicast or text in {"255.255.255.255", "<broadcast>"}:
        return "broadcast"
    return "external"


def _guard_address(address, *, operation: str, allow_broadcast: bool = False):
    """Validate an IPv4/IPv6 endpoint and map server wildcards to loopback."""
    host = _host_from_address(address)
    kind = _classify_host(host)
    if kind == "loopback":
        return address
    if kind == "wildcard" and operation == "bind":
        effective = "::1" if isinstance(host, str) and ":" in host else "127.0.0.1"
        _record("network_bind_remapped", requested_host=host,
                effective_host=effective, operation=operation)
        return _replace_host(address, effective)
    if kind == "broadcast" and allow_broadcast:
        # Tests of DiscoveryBroadcaster only need a local sink.  The remap is
        # deliberate and is reported in sandbox.json; it is not a fake pass.
        effective = "::1" if isinstance(host, str) and ":" in host else "127.0.0.1"
        _record("network_broadcast_remapped", requested_host=host,
                effective_host=effective, operation=operation)
        return _replace_host(address, effective)
    _record("network_blocked", requested_host=host, operation=operation)
    raise NetworkBlocked(
        f"VB-01 sandbox blocks non-loopback {operation}: {host!r}"
    )


class GuardedSocket(_ORIGINAL_SOCKET):
    """Socket subclass that keeps socketpair/fileno semantics intact."""

    def bind(self, address):
        return super().bind(_guard_address(address, operation="bind"))

    def connect(self, address):
        return super().connect(_guard_address(address, operation="connect"))

    def connect_ex(self, address):
        try:
            address = _guard_address(address, operation="connect_ex")
        except NetworkBlocked:
            # connect_ex reports errors rather than raising for a normal
            # socket.  EACCES is the least surprising portable errno here.
            return 13
        return super().connect_ex(address)

    def sendto(self, data, *args):
        if not args:
            return super().sendto(data)
        # sendto(data, address) or sendto(data, flags, address)
        address = args[-1]
        mapped = _guard_address(address, operation="sendto", allow_broadcast=True)
        if len(args) == 1:
            return super().sendto(data, mapped)
        return super().sendto(data, *args[:-1], mapped)


def _guarded_getaddrinfo(host, *args, **kwargs):
    if host is not None:
        kind = _classify_host(host)
        if kind == "external":
            _record("network_blocked", requested_host=host,
                    operation="getaddrinfo")
            raise NetworkBlocked(
                f"VB-01 sandbox blocks external name resolution: {host!r}"
            )
    return _ORIGINAL_GETADDRINFO(host, *args, **kwargs)


def _guarded_gethostbyname(host):
    if _classify_host(host) == "external":
        _record("network_blocked", requested_host=host,
                operation="gethostbyname")
        raise NetworkBlocked(
            f"VB-01 sandbox blocks external name resolution: {host!r}"
        )
    return _ORIGINAL_GETHOSTBYNAME(host)


def _guarded_create_connection(address, *args, **kwargs):
    address = _guard_address(address, operation="create_connection")
    return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)


_AGENT_MODULE_PREFIXES = (
    "04_mcp_im", "mcp", "openai", "anthropic", "google.generativeai",
)
_AGENT_COMMAND_WORDS = {
    "agent", "mcp", "claude", "codex", "openai", "anthropic",
    "deep-research", "coding-agent",
}
_HARDWARE_MODULES = {"cv2", "sounddevice", "pyaudio", "soundcard", "av"}


def _is_agent_module(name: str) -> bool:
    return any(name == prefix or name.startswith(prefix + ".")
               for prefix in _AGENT_MODULE_PREFIXES)


def _blocked_agent(module: str, operation: str):
    _record("agent_blocked", module=module, operation=operation)
    raise AgentBlocked(f"VB-01 sandbox blocks Agent adapter: {module}.{operation}")


def _blocked_device(module: str, operation: str):
    _record("device_blocked", module=module, operation=operation)
    raise DeviceBlocked(f"VB-01 sandbox blocks hardware device: {module}.{operation}")


def _patch_hardware_module(module_name: str, module) -> None:
    root_name = module_name.split(".", 1)[0]
    if root_name not in _HARDWARE_MODULES or getattr(module, "_moyu_gate_patched", False):
        return
    names = {
        "cv2": ("VideoCapture", "VideoWriter"),
        "sounddevice": ("InputStream", "RawInputStream", "OutputStream",
                         "RawOutputStream", "rec", "play", "query_devices"),
        "pyaudio": ("PyAudio",),
        "soundcard": ("default_microphone", "all_microphones",
                       "default_speaker", "all_speakers"),
        "av": ("open",),
    }.get(root_name, ())
    for name in names:
        if hasattr(module, name):
            setattr(module, name, lambda *a, _m=root_name, _n=name, **k:
                    _blocked_device(_m, _n))
    try:
        module._moyu_gate_patched = True
    except Exception:
        pass


def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level == 0 and _is_agent_module(name):
        _blocked_agent(name, "import")
    module = _ORIGINAL_IMPORT(name, globals, locals, fromlist, level)
    try:
        _patch_hardware_module(name, module)
    except Exception:
        pass
    return module


def _guarded_import_module(name, package=None):
    if _is_agent_module(name):
        _blocked_agent(name, "import_module")
    module = _ORIGINAL_IMPORT_MODULE(name, package)
    try:
        _patch_hardware_module(name, module)
    except Exception:
        pass
    return module


def _command_text(command) -> str:
    if isinstance(command, str):
        return command.lower()
    return " ".join(str(part) for part in command).lower()


def _looks_like_agent_command(command) -> bool:
    text = _command_text(command)
    first = text.split()[0] if text.split() else ""
    stem = Path(first.strip('"')).stem
    if stem in {"python", "python3", "node", "nodejs", "cmd", "powershell",
                "pwsh", "pytest"}:
        # A Python/Node command can still be an adapter when its command line
        # names one of the explicitly blocked tool trees.
        return any(token in text for token in ("04_mcp_im", "mcp-server",
                                                "deep-research", "coding-agent"))
    return any(word in stem or word in text.split() for word in _AGENT_COMMAND_WORDS)


def _guarded_popen(*args, **kwargs):
    command = args[0] if args else kwargs.get("args", ())
    if _looks_like_agent_command(command):
        _blocked_agent("subprocess", "Popen")
    return _ORIGINAL_POPEN(*args, **kwargs)


class GuardedPopen(_ORIGINAL_POPEN):
    """Popen subclass so stdlib modules may still subclass subprocess.Popen."""

    def __init__(self, *args, **kwargs):
        command = args[0] if args else kwargs.get("args", ())
        if _looks_like_agent_command(command):
            _blocked_agent("subprocess", "Popen")
        super().__init__(*args, **kwargs)


def install_from_environment() -> bool:
    """Install guards when launched by ``test_gate.py``.

    The operation is idempotent, which is useful because pytest loads the
    plugin before ``tests/conftest.py`` and the latter also calls this hook.
    """
    if os.environ.get("MOYU_GATE_SANDBOX") != "1":
        return False
    if _STATE["installed"]:
        return True
    _STATE["installed"] = True
    _socket.socket = GuardedSocket
    _socket.getaddrinfo = _guarded_getaddrinfo
    _socket.gethostbyname = _guarded_gethostbyname
    _socket.create_connection = _guarded_create_connection
    builtins.__import__ = _guarded_import
    importlib.import_module = _guarded_import_module
    _subprocess.Popen = GuardedPopen
    _record("sandbox_installed", network="loopback_only",
            agent="blocked", devices="blocked")
    return True


def finalize() -> None:
    """Persist strategy evidence before the project's ``os._exit`` hook."""
    report_path = os.environ.get("MOYU_GATE_SANDBOX_REPORT")
    if not report_path:
        return
    report = {
        "schema_version": "VB-01.v1",
        "installed": bool(_STATE["installed"]),
        "policy": {
            "network": "loopback_only",
            "wildcard_bind": "remap_to_loopback",
            "broadcast_sendto": "remap_to_loopback_and_record",
            "agent": "blocked",
            "hardware": "blocked",
        },
        "desktop": os.environ.get("MOYU_GATE_DESKTOP_NAME") or None,
        "blocked_events": int(_STATE["blocked"]),
        "remapped_events": int(_STATE["remapped"]),
        "events": list(_STATE["events"]),
    }
    path = Path(report_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + f".{os.getpid()}.tmp")
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        os.replace(temp, path)
    except OSError:
        # The test result itself must remain authoritative if diagnostics are
        # unavailable after a native crash.  The parent marks this as missing.
        pass


def pytest_unconfigure(config) -> None:
    """pytest plugin hook; runs even when the project conftest is absent."""
    finalize()


def _windows_handles():
    if os.name != "nt":
        return None
    return ctypes.windll.kernel32, ctypes.windll.user32


class _STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


def _win32_error(prefix: str) -> OSError:
    return OSError(ctypes.get_last_error(), prefix)


def _new_desktop_name() -> str:
    return f"MoyuGate-{os.getpid()}-{uuid.uuid4().hex[:10]}"


def _create_private_desktop(name: str):
    if os.name != "nt":
        return None
    _, user32 = _windows_handles()
    user32.CreateDesktopW.restype = wintypes.HANDLE
    handle = user32.CreateDesktopW(
        name, None, None, 0, 0x10000000, None  # GENERIC_ALL
    )
    if not handle:
        raise _win32_error("CreateDesktopW failed")
    return handle


class DesktopProcess:
    """Small wait/terminate wrapper shared by the gate and probe tests."""

    def __init__(self, *, popen=None, process_handle=None, thread_handle=None,
                 desktop_handle=None, log_file=None, pid=None):
        self._popen = popen
        self._process_handle = process_handle
        self._thread_handle = thread_handle
        self._desktop_handle = desktop_handle
        self._log_file = log_file
        self.pid = int(pid or (popen.pid if popen is not None else 0))
        self.session_id = process_session_id(self.pid)

    def poll(self):
        if self._popen is not None:
            return self._popen.poll()
        kernel32, _ = _windows_handles()
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(self._process_handle, ctypes.byref(code)):
            return None
        if code.value == 259:  # STILL_ACTIVE
            return None
        return ctypes.c_long(code.value).value if code.value >= 2**31 else code.value

    def wait(self, timeout=None):
        if self._popen is not None:
            return self._popen.wait(timeout=timeout)
        kernel32, _ = _windows_handles()
        milliseconds = 0xFFFFFFFF if timeout is None else max(0, int(timeout * 1000))
        result = kernel32.WaitForSingleObject(self._process_handle, milliseconds)
        if result == 0x102:
            raise TimeoutError("process wait timed out")
        if result != 0:
            raise _win32_error("WaitForSingleObject failed")
        return self.poll()

    def terminate_tree(self):
        if not self.pid:
            return True
        terminated = False
        owned_pids = process_tree_pids(self.pid)
        try:
            result = _ORIGINAL_POPEN(
                ["taskkill", "/PID", str(self.pid), "/T", "/F"],
                stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL,
                stdin=_subprocess.DEVNULL, creationflags=0x08000000).wait(10)
            terminated = result == 0
        except Exception:
            pass
        # taskkill /T normally covers descendants.  Explicitly target the
        # PIDs observed before termination as a second bounded cleanup pass,
        # then verify each owned PID has exited; no global process sweep is
        # recorded or touched.
        for child_pid in owned_pids:
            if child_pid == self.pid:
                continue
            try:
                _ORIGINAL_POPEN(
                    ["taskkill", "/PID", str(child_pid), "/T", "/F"],
                    stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL,
                    stdin=_subprocess.DEVNULL, creationflags=0x08000000,
                ).wait(10)
            except Exception:
                pass
        if self._popen is not None:
            if self._popen.poll() is None:
                try:
                    self._popen.kill()
                    terminated = True
                except Exception:
                    pass
            if self._popen.poll() is None:
                return False
            return _wait_owned_processes_gone(owned_pids)
        if self.poll() is None:
            kernel32, _ = _windows_handles()
            terminated = bool(kernel32.TerminateProcess(self._process_handle, 124)) or terminated
        return self.poll() is not None and _wait_owned_processes_gone(owned_pids)

    def close(self):
        if self._popen is not None:
            if self._log_file is not None:
                try:
                    self._log_file.close()
                except Exception:
                    pass
            return
        kernel32, user32 = _windows_handles()
        for handle in (self._thread_handle, self._process_handle):
            if handle:
                kernel32.CloseHandle(handle)
        if self._desktop_handle:
            user32.CloseDesktop(self._desktop_handle)
        if self._log_file is not None:
            try:
                self._log_file.close()
            except Exception:
                pass


def launch_process(command, *, cwd: str, env: dict[str, str], log_path: Path,
                   desktop_name: str | None = None) -> DesktopProcess:
    """Launch a child, optionally attached to a private Windows desktop."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt" or not desktop_name:
        flags = 0
        if os.name == "nt":
            flags = 0x00000200 | 0x08000000  # NEW_PROCESS_GROUP|NO_WINDOW
        log_file = log_path.open("wb")
        try:
            proc = _ORIGINAL_POPEN(
                list(command), cwd=cwd, env=env, stdin=_subprocess.DEVNULL,
                stdout=log_file, stderr=_subprocess.STDOUT,
                creationflags=flags,
            )
        except Exception:
            log_file.close()
            raise
        return DesktopProcess(popen=proc, log_file=log_file)

    kernel32, _ = _windows_handles()
    desktop_handle = _create_private_desktop(desktop_name)
    log_file = log_path.open("wb")
    try:
        import msvcrt
        handle = msvcrt.get_osfhandle(log_file.fileno())
        kernel32.SetHandleInformation(
            wintypes.HANDLE(handle), 1, 1  # HANDLE_FLAG_INHERIT
        )
        si = _STARTUPINFOW()
        si.cb = ctypes.sizeof(si)
        si.lpDesktop = f"WinSta0\\{desktop_name}"
        si.dwFlags = 0x00000100  # STARTF_USESTDHANDLES
        si.hStdInput = wintypes.HANDLE(0)
        si.hStdOutput = wintypes.HANDLE(handle)
        si.hStdError = wintypes.HANDLE(handle)
        pi = _PROCESS_INFORMATION()
        env_text = "\0".join(f"{k}={v}" for k, v in sorted(env.items())) + "\0\0"
        env_buffer = ctypes.create_unicode_buffer(env_text)
        command_text = _subprocess.list2cmdline([str(x) for x in command])
        command_buffer = ctypes.create_unicode_buffer(command_text)
        flags = 0x00000400 | 0x00000200 | 0x08000000  # unicode|group|no-window
        ok = kernel32.CreateProcessW(
            str(command[0]), command_buffer, None, None, True, flags,
            ctypes.byref(env_buffer), cwd, ctypes.byref(si), ctypes.byref(pi)
        )
        if not ok:
            raise _win32_error("CreateProcessW on private desktop failed")
        kernel32.CloseHandle(pi.hThread)
        return DesktopProcess(
            process_handle=pi.hProcess, thread_handle=None,
            desktop_handle=desktop_handle, log_file=log_file,
            pid=pi.dwProcessId,
        )
    except Exception:
        try:
            log_file.close()
        finally:
            _windows_handles()[1].CloseDesktop(desktop_handle)
        raise


def private_desktop_probe() -> dict:
    """Small side-effect-free probe used by runner tests and diagnostics."""
    if os.name != "nt":
        return {"available": False, "reason": "non-windows"}
    name = _new_desktop_name()
    handle = None
    try:
        handle = _create_private_desktop(name)
        return {"available": bool(handle), "name": name}
    except OSError as exc:
        return {"available": False, "name": name, "error": str(exc)}
    finally:
        if handle:
            _windows_handles()[1].CloseDesktop(handle)


def process_session_id(pid: int | None) -> int | None:
    """Return only the Windows session number for this child process."""
    if os.name != "nt" or not pid:
        return None
    kernel32, _ = _windows_handles()
    kernel32.ProcessIdToSessionId.restype = wintypes.BOOL
    kernel32.ProcessIdToSessionId.argtypes = [wintypes.DWORD,
                                               ctypes.POINTER(wintypes.DWORD)]
    session = wintypes.DWORD()
    if not kernel32.ProcessIdToSessionId(int(pid), ctypes.byref(session)):
        return None
    return int(session.value)


def process_state(pid: int | None) -> str:
    """Distinguish an exited PID from access/query uncertainty; never kill it."""
    if type(pid) is not int or pid <= 0:
        return "unknown"
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return "exited"
        except OSError:
            return "unknown"
        return "running"
    kernel32, _ = _windows_handles()
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        # ERROR_INVALID_PARAMETER is the documented response for absent PIDs.
        # ACCESS_DENIED and other errors are not evidence of process exit.
        return "exited" if kernel32.GetLastError() == 87 else "unknown"
    try:
        code = wintypes.DWORD()
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return "unknown"
        return "running" if code.value == 259 else "exited"
    finally:
        kernel32.CloseHandle(wintypes.HANDLE(handle))


def process_image_path(pid: int | None) -> str | None:
    """Read a live process image for PID ownership checks only."""
    if os.name != "nt" or not pid:
        return None
    kernel32, _ = _windows_handles()
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    handle = kernel32.OpenProcess(0x1000, False, int(pid))  # QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        if not kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)):
            return None
        return buffer.value
    finally:
        kernel32.CloseHandle(handle)


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def process_tree_pids(root_pid: int | None) -> list[int]:
    """List only the recorded child PID and descendants for cleanup proof."""
    if os.name != "nt" or not root_pid:
        return [int(root_pid)] if root_pid else []
    kernel32, _ = _windows_handles()
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot in (None, 0, -1):
        return [int(root_pid)]
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.restype = wintypes.BOOL
        parent_map = {}
        if kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            while True:
                parent_map[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
                if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
        result = {int(root_pid)}
        changed = True
        while changed:
            changed = False
            for pid, parent in parent_map.items():
                if parent in result and pid not in result:
                    result.add(pid)
                    changed = True
        return sorted(result)
    finally:
        kernel32.CloseHandle(snapshot)


def _wait_owned_processes_gone(pids: list[int], timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(process_state(pid) == "exited" for pid in pids):
            return True
        time.sleep(0.05)
    return all(process_state(pid) == "exited" for pid in pids)


if os.environ.get("MOYU_GATE_SANDBOX") == "1":
    install_from_environment()
