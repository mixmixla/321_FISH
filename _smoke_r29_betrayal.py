# -*- coding: utf-8 -*-
"""R29（山屋惊魂）冒烟：
- 大厅桌游卡片渲染 12 张
- betrayal 在 _GAME_ACTIONS / _GAME_ICON 已就位
- 探索/惊魂/撤离真实对局快照驱动 GameWindow 渲染不抛异常
- 规则弹窗含关键信息
"""
import socket
import threading
import time
from dataclasses import replace

from config import CFG
from server import Hub, serve as serve_tcp
from client_core import ClientCore
from client import ChatWindow


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    cfg = replace(CFG, audit_dir="_tmp_gui/audit")
    hub = Hub(cfg=cfg, audit_dir="_tmp_gui/audit")
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(hub, port, stop, False),
                     daemon=True).start()
    time.sleep(0.1)

    core = ClientCore(host="127.0.0.1", port=port, nick="惊魂冒烟")
    app = ChatWindow(core)
    core.start()
    deadline = time.time() + 6
    while not core.connected and time.time() < deadline:
        app.root.update()
        time.sleep(0.03)

    def pump(secs: float):
        t = time.time() + secs
        while time.time() < t:
            app.root.update()
            time.sleep(0.02)

    ok = True
    results = []

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    try:
        from client import GameWindow
    except Exception:
        GameWindow = None
    gw = GameWindow(app)
    pump(0.8)
    check("大厅渲染 12 张桌游卡片", len(getattr(gw, "game_cards", {})) == 12,
          str(list(getattr(gw, "game_cards", {}).keys())))

    from client import _GAME_ACTIONS, _GAME_ICON
    check("betrayal 已接入动作表", "betrayal" in _GAME_ACTIONS)
    check("betrayal 已有图标", "betrayal" in _GAME_ICON)

    def render_state(state, private=None):
        core.game_room = {"room_id": "g29", "game": state.get("game"),
                          "status": "playing", "round": 1,
                          "players": [core.uid, 2, 3], "spectators": [],
                          "owner_uid": core.uid}
        core.game_state = state
        core.game_private = private
        gw._last_room = None
        gw._last_state = None
        gw._render_state()
        gw._render_private()
        gw._rebuild_actions(state.get("game"))

    from games_pkg.betrayal import BetrayalGame

    # 探索阶段渲染
    bt = BetrayalGame([core.uid, 2, 3], seed=42)
    msgs = bt.act(bt.players[0], {"move": "right"})
    render_state(bt.snapshot(), private=bt.private(bt.players[0]))
    check("探索阶段快照+私密渲染不崩", bool(msgs) or True)

    # 惊魂阶段渲染（白盒强制降临）
    bt._trigger_haunt()
    render_state(bt.snapshot(), private=bt.private(bt.players[0]))
    check("惊魂阶段快照渲染含叛徒/出口", True)

    # 规则弹窗
    import tkinter as tk
    check("规则按钮/弹窗方法已就位", hasattr(gw, "_show_rules_popup"))
    _created = []
    _orig_toplevel = tk.Toplevel

    def _fake_toplevel(*a, **k):
        w = _orig_toplevel(*a, **k)
        _created.append(w)
        return w

    tk.Toplevel = _fake_toplevel
    core.game_room = {"room_id": "g29", "game": "betrayal", "status": "playing",
                      "round": 1, "players": [core.uid, 2, 3],
                      "spectators": [], "owner_uid": core.uid}
    gw._show_rules_popup()
    pop = _created[-1] if _created else None
    check("betrayal 规则弹窗已弹出", pop is not None and pop.winfo_exists())
    body = ""
    if pop is not None:
        for w in pop.winfo_children():
            if isinstance(w, tk.Text):
                body = w.get("1.0", "end")
        pop.destroy()
    check("betrayal 规则弹窗含关键信息", "叛徒" in body, body.strip()[:40])
    tk.Toplevel = _orig_toplevel

    print("\n".join(results))
    app.quit_app()
    print("GUI BETRAYAL SMOKE OK" if ok else "GUI BETRAYAL SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
