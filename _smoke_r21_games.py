# -*- coding: utf-8 -*-
"""R21（游戏中心扩展：四子棋/奥赛罗/24点/抽牌配对）冒烟：
- 大厅桌游卡片渲染 12 张（R29 加入山屋惊魂）
- 新游戏在 _GAME_ACTIONS / _GAME_ICON 已就位
- 用真实对局快照驱动 GameWindow._fmt_state / _render_private 不抛异常
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

    core = ClientCore(host="127.0.0.1", port=port, nick="冒烟主")
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

    gw = GameWindow = None
    try:
        from client import GameWindow
    except Exception:
        GameWindow = None
    gw = GameWindow(app)
    pump(0.8)
    check("大厅渲染 12 张桌游卡片", len(getattr(gw, "game_cards", {})) == 12,
          str(list(getattr(gw, "game_cards", {}).keys())))

    new_games = ["connect4", "othello", "calc24", "matchpairs", "betrayal"]
    from client import _GAME_ACTIONS, _GAME_ICON
    for g in new_games:
        check(f"{g} 已接入动作表", g in _GAME_ACTIONS)
        check(f"{g} 已有图标", g in _GAME_ICON)

    # 用真实对局驱动的快照渲染
    def render_state(state, private=None):
        core.game_room = {"room_id": "g9", "game": state.get("game"),
                          "status": "playing", "round": 1,
                          "players": [core.uid, 2], "spectators": [],
                          "owner_uid": core.uid}
        core.game_state = state
        core.game_private = private
        gw._last_room = None
        gw._last_state = None
        gw._render_state()
        gw._render_private()
        gw._rebuild_actions(state.get("game"))

    # 四子棋
    from games_pkg.connect4 import Connect4Game
    c4 = Connect4Game([core.uid, 2], seed=1)
    c4.act(core.uid, {"col": 0}); c4.act(2, {"col": 1}); c4.act(core.uid, {"col": 0})
    render_state(c4.snapshot())
    check("四子棋快照渲染不崩", True)

    # 奥赛罗
    from games_pkg.othello import OthelloGame
    ot = OthelloGame([core.uid, 2], seed=1)
    ot.act(core.uid, {"x": 2, "y": 4})
    render_state(ot.snapshot())
    check("奥赛罗快照渲染不崩", True)

    # 24点
    from games_pkg.calc24 import Calc24Game
    c24 = Calc24Game([core.uid, 2], seed=1)
    render_state(c24.snapshot())
    check("24点快照渲染不崩", True)

    # 抽牌配对
    from games_pkg.matchpairs import MatchPairsGame
    mp = MatchPairsGame([core.uid, 2, 3], seed=2)
    render_state(mp.snapshot(), private=mp.private(core.uid))
    check("抽牌配对快照+私密渲染不崩", True)

    # 山屋惊魂
    from games_pkg.betrayal import BetrayalGame
    bt = BetrayalGame([core.uid, 2, 3], seed=4)
    bt._trigger_haunt()
    render_state(bt.snapshot(), private=bt.private(core.uid))
    check("山屋惊魂快照+私密渲染不崩", True)

    # 游戏内规则弹窗：入房后点「📖 游戏规则」→ 弹出 Toplevel，正文含该游戏规则关键信息
    import tkinter as tk
    check("规则按钮/弹窗方法已就位", hasattr(gw, "_show_rules_popup"))
    _created = []
    _orig_toplevel = tk.Toplevel

    def _fake_toplevel(*a, **k):
        w = _orig_toplevel(*a, **k)
        _created.append(w)
        return w

    tk.Toplevel = _fake_toplevel
    for g, kw in (("connect4", "连成 4 子"), ("othello", "夹住对方子"),
                  ("calc24", "凑出 24"), ("matchpairs", "王八"),
                  ("betrayal", "叛徒")):
        core.game_room = {"room_id": "g9", "game": g, "status": "playing",
                          "round": 1, "players": [core.uid, 2],
                          "spectators": [], "owner_uid": core.uid}
        gw._show_rules_popup()
        pop = _created[-1] if _created else None
        check(f"{g} 规则弹窗已弹出", pop is not None and pop.winfo_exists())
        body = ""
        if pop is not None:
            for w in pop.winfo_children():
                if isinstance(w, tk.Text):
                    body = w.get("1.0", "end")
            pop.destroy()
        check(f"{g} 规则弹窗含关键信息", kw in body, body.strip()[:40])
    tk.Toplevel = _orig_toplevel

    print("\n".join(results))
    app.quit_app()
    print("GUI GAMES SMOKE OK" if ok else "GUI GAMES SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())