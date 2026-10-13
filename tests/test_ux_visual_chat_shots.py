# -*- coding: utf-8 -*-
"""UX-VISUAL-CHAT-01 独立视觉验收：fresh 合成 profile 实拍桌面聊天主窗。

仅 --run-visual 运行。不触碰现存用户窗口/偏好：使用临时 profile + 合成名单
/消息，不连接服务器。覆盖 mist/mist_dark × 无边框/原生标题栏 × 100%/125%
/150% DPI，以及离线状态、输入草稿、极低频「更多」菜单、最小窗口。

架构（稳定性）：
- 每个用例在**独立子进程**中构建一个 fresh 窗口并实拍（产品本来就是一进程
  一解释器）。本机 pyenv-win 的 Tcl 8.6 在同一进程里反复初始化/销毁解释器时
  偶发 "Can't find a usable tk.tcl" / `invalid command name "tcl_findLibrary"`
  ——属环境级瞬时抖动，会中断采集甚至拖垮进程（实测 0xC0000409）。
- 子进程只负责渲染 + 落盘 PNG + 回传像素尺寸；父进程（pytest）负责编排、
  对上述**已知瞬时 Tcl 初始化错误**做有界重试（不掩盖真实断言失败），并统一
  记录绑定信息（含磁盘实测源码 SHA），因此不产生跨进程写文件竞争。
- 每个窗口关闭时禁用进程级副作用（自动发现 / 系统托盘 / 全局热键），只保留
  本矩阵所需的绘制与状态路径。

截图写入 review-assets；每张图绑定磁盘实测源码 SHA，供独立视觉审查。
"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

import pytest

pytestmark = pytest.mark.visual

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:                 # 子进程以脚本方式运行时可直接 import 项目模块
    sys.path.insert(0, str(ROOT))

SHOT_DIR = Path(os.environ.get(
    "MOYU_SHOT_DIR", ROOT / "docs" / "review-assets" / "UX-VISUAL-CHAT-01" / "screenshots"))
BINDING = Path(os.environ.get(
    "MOYU_BINDING", ROOT / "docs" / "review-assets" / "UX-VISUAL-CHAT-01" / "stage-images.json"))
SOURCE_FILES = ("client.py", "dpi.py", "theme.py", "web.py", "ui_design.py",
                "widgets/session_list.py", "widgets/msg_list.py",
                "widgets/design_controls.py")
RUN_ID = os.environ.get("MOYU_VISUAL_RUN") or ("visual-" + time.strftime("%Y%m%d-%H%M%S"))

# 仅用于重试的「已知瞬时 Tcl 初始化抖动」指纹；真实断言失败不含这些串，不会重试。
_TRANSIENT_TCL = ("usable tk.tcl", "tcl_findlibrary", "spinbox.tcl",
                  "no such file or directory")
_MAX_ATTEMPTS = 3

_MESSAGES = [
    (2, "项目协作", "上午的清单都处理好了，下午一起过一下进度。"),
    (1, "视觉合成", "收到。我把重点整理进会话，下午一起看。"),
    (3, "产品讨论", "会议 15:00 开始，我先把资料准备好。"),
    (2, "项目协作", "这是一条较长的消息，用来检查中文换行、气泡留白和窗口缩放后的阅读体验。"),
    (1, "视觉合成", "导航、输入和消息区都保持原有聊天功能，只调整视觉层级。"),
]
_DRAFT = "这是一段输入草稿，用来检查输入区留白与发送按钮可发现性。"


# --------------------------------------------------------------------------- #
# 通用工具
# --------------------------------------------------------------------------- #
def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _pump(root, seconds: float = 0.2) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        root.update()
        time.sleep(0.02)


# --------------------------------------------------------------------------- #
# 子进程侧：构建一个 fresh 窗口并实拍
# --------------------------------------------------------------------------- #
def _open_window(spec):
    """在临时 profile 上构建 fresh 主窗；DPI 由替换 dpi._system_dpi 模拟。

    同进程/多次建窗时，自动发现线程、系统托盘与两个全局热键会互相抢占并拖慢
    / 拖垮进程。这三者是进程级副作用，关掉不影响本视觉矩阵所需的绘制/状态路径
    （窗口、皮肤、DPI、名单、消息、状态栏均照常构建）。
    """
    import dpi
    import client as client_mod
    dpi._system_dpi = lambda: float(spec["dpi"])
    client_mod.CFG.discovery_enabled = False
    client_mod.CFG.tray_enabled = False
    client_mod.CFG.global_hotkeys_enabled = False
    from client import ChatWindow
    from client_core import ClientCore
    tmp = Path(spec["tmp"])
    tmp.mkdir(parents=True, exist_ok=True)
    prefs = tmp / "prefs.json"
    prefs.write_text(json.dumps({"skin": spec["skin"], "frameless": spec["frameless"],
                                 "skin_follow_system": False, "chat_alpha": 1.0,
                                 "dpi_aware": True}), encoding="utf-8")
    core = ClientCore(nick="视觉合成", history_dir=str(tmp / "history"))
    core.uid = 1
    core.roster = {1: {"uid": 1, "nick": "视觉合成", "type": "tcp"},
                   2: {"uid": 2, "nick": "项目协作", "type": "tcp"},
                   3: {"uid": 3, "nick": "产品讨论", "type": "web"}}
    app = ChatWindow(core, prefs_path=str(prefs))
    app.msg_list.set_me_uid(core.uid)
    errors = []
    app.root.report_callback_exception = lambda *details: errors.append(details)
    geometry = spec.get("geometry")
    app.root.geometry((geometry + "+60+40") if geometry else "+60+40")
    app.root.deiconify()
    app._refresh_roster()
    for index, (uid, nick, text) in enumerate(_MESSAGES):
        app._append_msg({"t": "chat", "channel": "public", "uid": uid, "nick": nick,
                         "text": text, "seq": index + 1, "ts": time.time() + index})
    _pump(app.root, 0.4)
    return app, errors


def _grab_window(app, path: Path):
    from PIL import ImageGrab
    path.parent.mkdir(parents=True, exist_ok=True)
    hwnd = ctypes.windll.user32.GetAncestor(app.root.winfo_id(), 2)
    _pump(app.root, 0.5)
    image = ImageGrab.grab(window=hwnd)
    image.save(path)
    return image.size


def _grab_more_menu(app, path: Path):
    """复现「更多」按钮弹出坐标并实拍。

    client._more_menu() 用 tk_popup()，在 Windows 上会进入原生模态菜单循环，
    直到收到真实输入才返回；unpost()/event_generate('<Escape>') 在循环内无法结束。
    这里以 menu.post() 进入同一循环，在循环内 after 回调完成实拍后发送
    VK_ESCAPE（不移动鼠标、不点击其它窗口）结束循环。
    """
    menu = app._build_more_menu()
    x = app._more_btn.winfo_rootx()
    y = app._more_btn.winfo_rooty() - menu.winfo_reqheight() - 2
    if y < 0:                                      # 顶部放不下 → 按钮下方弹（与源码一致）
        y = app._more_btn.winfo_rooty() + app._more_btn.winfo_reqheight()
    shot = {}

    def _capture_and_dismiss():
        from PIL import ImageGrab
        path.parent.mkdir(parents=True, exist_ok=True)
        x0, y0 = app.root.winfo_rootx(), app.root.winfo_rooty()
        w, h = app.root.winfo_width(), app.root.winfo_height()
        margin = max(y0 - y, 0) + 12
        bbox = (max(0, x0 - 8), max(0, y0 - margin), x0 + w + 8, y0 + h + 8)
        image = ImageGrab.grab(bbox=bbox)
        image.save(path)
        shot["size"] = image.size
        ctypes.windll.user32.keybd_event(0x1B, 0, 0, 0)       # VK_ESCAPE down
        ctypes.windll.user32.keybd_event(0x1B, 0, 0x0002, 0)  # VK_ESCAPE up

    app.root.after(700, _capture_and_dismiss)
    try:
        menu.post(x, y)                            # 阻塞至 ESC 结束菜单循环
    finally:
        try:
            menu.unpost()
        except Exception:
            pass
    assert shot.get("size"), "menu screenshot was not captured"
    return shot["size"]


def _worker_main(spec) -> None:
    app, errors = _open_window(spec)
    path = Path(spec["shot_path"])
    size = None
    try:
        mode = spec["mode"]
        if mode in ("normal", "minimal"):
            assert app._navigation_buttons["chat"]._nav_selected
            size = _grab_window(app, path)
        elif mode == "offline":
            app._on_state("offline")
            _pump(app.root, 0.3)
            assert app.status_text.cget("text").startswith("离线")
            size = _grab_window(app, path)
        elif mode == "input":
            app.entry.insert("1.0", _DRAFT)
            _pump(app.root, 0.3)
            assert app.entry.get("1.0", "end").strip()
            size = _grab_window(app, path)
        elif mode == "more":
            size = _grab_more_menu(app, path)
        else:
            raise AssertionError(f"unknown mode: {mode!r}")
        assert not errors, errors
    finally:
        try:
            if not app._closed:
                app.quit_app()
        except Exception:
            pass
    sys.stdout.write(json.dumps({"ok": True, "size": [int(size[0]), int(size[1])]}) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    if "--case" in sys.argv:
        _spec = json.loads(sys.argv[sys.argv.index("--case") + 1])
        try:
            _worker_main(_spec)
        except Exception:
            traceback.print_exc()
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(1)
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)                                # 跳过解释器关闭期 Tcl 清理（见 conftest）


# --------------------------------------------------------------------------- #
# 父进程侧：编排、有界重试、记录绑定
# --------------------------------------------------------------------------- #
def _spawn_case(spec: dict) -> dict:
    """在独立子进程中渲染一张截图；返回子进程回传的像素尺寸。"""
    env = dict(os.environ,
               MOYU_VISUAL_RUN=RUN_ID,
               MOYU_SHOT_DIR=str(SHOT_DIR),
               MOYU_BINDING=str(BINDING))
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--case", json.dumps(spec)],
        capture_output=True, text=True, env=env, timeout=300)
    if proc.returncode != 0:
        raise AssertionError(
            f"visual worker failed rc={proc.returncode} spec={spec.get('name')}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    payload = [ln for ln in proc.stdout.splitlines() if ln.strip().startswith("{")]
    assert payload, f"worker produced no result: {proc.stdout!r}"
    return json.loads(payload[-1])


def _run_case(spec: dict) -> tuple:
    """渲染一个用例；对已知瞬时 Tcl 初始化抖动有界重试，其余失败直接上抛。"""
    last = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            result = _spawn_case(spec)
        except AssertionError as exc:
            last = exc
            text = str(exc).lower()
            if attempt < _MAX_ATTEMPTS and any(tok in text for tok in _TRANSIENT_TCL):
                time.sleep(0.6 * attempt)
                continue
            raise
        return result["size"], attempt
    raise last                                        # pragma: no cover


def _record(name: str, path: Path, fixture: str, limitation: str, size, attempts: int) -> None:
    data = {"stage_only": True, "final_visual_acceptance": False,
            "run": RUN_ID, "images": []}
    if BINDING.is_file():
        data = json.loads(BINDING.read_text(encoding="utf-8"))
        data["run"] = RUN_ID
        data.setdefault("images", [])
    entry = {"path": f"screenshots/{name}", "sha256": _sha256(path), "run": RUN_ID,
             "render_attempts": int(attempts),
             "fixture": fixture, "limitation": limitation,
             "pixel_size": [int(size[0]), int(size[1])],
             "application_inputs": [{"path": rel, "raw_sha256": _sha256(ROOT / rel)}
                                    for rel in SOURCE_FILES]}
    data["images"] = [e for e in data["images"] if e.get("path") != entry["path"]]
    data["images"].append(entry)
    BINDING.parent.mkdir(parents=True, exist_ok=True)
    BINDING.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _capture(tmp_path, *, name, mode, skin, frameless, dpi_value,
             geometry, fixture, limitation):
    spec = {"name": name, "mode": mode, "skin": skin, "frameless": frameless,
            "dpi": dpi_value, "geometry": geometry, "tmp": str(tmp_path),
            "shot_path": str(SHOT_DIR / name)}
    size, attempts = _run_case(spec)
    assert size, f"{name}: screenshot was not produced"
    _record(name, SHOT_DIR / name, fixture, limitation, size, attempts)


# --------------------------------------------------------------------------- #
# 用例
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("dpi_value", [96, 120, 144])
@pytest.mark.parametrize("frameless", [True, False])
@pytest.mark.parametrize("skin", ["mist", "mist_dark"])
def test_desktop_chat_matrix(tmp_path, skin, frameless, dpi_value):
    name = (f"ui-{skin}-{'frameless' if frameless else 'native'}"
            f"-dpi{dpi_value}-normal.png")
    _capture(
        tmp_path, name=name, mode="normal", skin=skin, frameless=frameless,
        dpi_value=dpi_value, geometry=None,
        fixture="synthetic roster+messages, fresh temp profile, no server",
        limitation=f"{skin} + {'frameless' if frameless else 'native titlebar'} "
                   f"@ {dpi_value} DPI ({dpi_value / 96:.2f}x), normal window")


@pytest.mark.parametrize("dpi_value", [96, 120, 144])
def test_minimal_window_matrix(tmp_path, dpi_value):
    scale = dpi_value / 96.0
    geometry = f"{int(680 * scale)}x{int(480 * scale)}"
    name = f"ui-mist-frameless-dpi{dpi_value}-minimal.png"
    _capture(
        tmp_path, name=name, mode="minimal", skin="mist", frameless=True,
        dpi_value=dpi_value, geometry=geometry,
        fixture="synthetic roster+messages, fresh temp profile, no server",
        limitation=f"mist + frameless @ {dpi_value} DPI ({dpi_value / 96:.2f}x), "
                   f"minimal {geometry} window")


def test_offline_state(tmp_path):
    name = "ui-mist-frameless-dpi96-offline.png"
    _capture(
        tmp_path, name=name, mode="offline", skin="mist", frameless=True,
        dpi_value=96, geometry=None,
        fixture="synthetic roster+messages, fresh temp profile, connection state forced offline",
        limitation="mist + frameless @ 96 DPI, offline/failure status bar")


def test_input_draft_state(tmp_path):
    name = "ui-mist-frameless-dpi96-input.png"
    _capture(
        tmp_path, name=name, mode="input", skin="mist", frameless=True,
        dpi_value=96, geometry=None,
        fixture="synthetic roster+messages, fresh temp profile, in-memory draft only",
        limitation="mist + frameless @ 96 DPI, compose region with typed draft")


def test_more_menu_popup(tmp_path):
    name = "ui-mist-frameless-dpi96-more.png"
    _capture(
        tmp_path, name=name, mode="more", skin="mist", frameless=True,
        dpi_value=96, geometry=None,
        fixture="synthetic roster+messages, fresh temp profile, native menu posted "
                "(dismissed via synthetic VK_ESCAPE)",
        limitation="mist + frameless @ 96 DPI, low-frequency more-menu popup "
                   "(screen region grab)")
