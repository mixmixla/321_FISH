"""Reproducible real Tk + headless Chromium evidence using synthetic RoomManager.

No front desktop switching, human input injection, real account or device access.
Run from repository root; --tk is launched only on a private desktop by --all.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from games_pkg.dou import DouGame, CAT, DOG, LION, MOUSE
from games_pkg.rooms import RoomManager


class Table:
    def __init__(self):
        self.manager = RoomManager({"dou": DouGame})
        self.room = self.manager.create(1, "dou")
        self.manager.join(2, self.room.room_id)
        self.manager.spectate(3, self.room.room_id)
        self.manager.start(1, self.room.room_id)
        self.actions = []

    def payload(self, uid):
        return {"room": self.room.summary(), "state": self.room.gs.snapshot(),
                "private": {"legal": self.room.gs.legal_moves(uid)}}

    def fixture(self, name):
        g = self.room.gs
        g.winner = None; g.last_event = None; g.last_move = None; g.turn = 0
        if name == "capture":
            g.board = {(0, 2): (0, DOG), (0, 1): (1, CAT),
                       (6, 6): (1, LION), (6, 7): (0, CAT)}
        elif name == "den":
            g.board = {(3, 7): (0, MOUSE), (0, 0): (1, CAT)}
        else:
            raise AssertionError(name)

    def act(self, uid, action):
        before = self.room.gs.snapshot()
        events = self.manager.handle_action(uid, self.room.room_id, action)
        self.actions.append({"uid": uid, "action": action, "events": events,
                             "before": before, "after": self.room.gs.snapshot()})
        return events


def tk_probe(output):
    import tkinter as tk
    import tkguard  # noqa
    from PIL import ImageGrab
    import client_gameui as cu
    table = Table()
    root = tk.Tk(); root.title("森境 · 合成资料验证"); root.geometry("480x400")
    cv = tk.Canvas(root, highlightthickness=0); cv.pack(fill="both", expand=True)
    errors = []; root.report_callback_exception = lambda *args: errors.append(str(args))
    ui = {"connected": True, "sel": {}}; who = [1]

    def paint():
        p = table.payload(who[0]); ui.update(room=p["room"], state=p["state"], me=who[0])
        cu.render(cv, "dou", p["state"], who[0], lambda uid: f"合成玩家{uid}",
                  submit, paint, ui, p["private"], cv.winfo_width(), cv.winfo_height())

    def submit(action):
        table.act(who[0], action); paint()

    cv.bind("<Button-1>", lambda e: cu.handle_click(ui, e.x, e.y))
    root.update(); paint(); root.update()

    def click(x, y):
        cv.event_generate("<Button-1>", x=round(ui["ox"] + (x+.5)*ui["cell"]),
                          y=round(ui["oy"] + (y+.5)*ui["cell"])); root.update()

    def shot(name):
        root.update()
        hwnd = ctypes.windll.user32.GetAncestor(root.winfo_id(), 2)
        image = ImageGrab.grab(window=hwnd)
        assert image.width >= 480 and image.height >= 400
        image.save(output / (name + ".png"))

    shot("tk-initial-480")
    assert len(cv.find_withtag("dou-character")) == 16
    click(0, 2); assert ui["sel"] == {"game": "dou", "fx": 0, "fy": 2}
    assert cv.find_withtag("dou-legal")
    shot("tk-decision-480"); click(0, 3)
    assert table.room.gs.board[(0, 3)] == (0, MOUSE)
    who[0] = 2; paint(); click(6, 6); click(6, 5)
    assert table.room.gs.board[(6, 5)] == (1, MOUSE)
    shot("tk-player2-480")
    who[0] = 3; paint(); count = len(table.actions); click(0, 3); click(0, 4)
    assert len(table.actions) == count; shot("tk-spectator-480")
    table.fixture("capture"); who[0] = 1; paint(); click(0, 2); click(0, 1)
    assert table.room.gs.last_event["kind"] == "eat"
    who[0] = 2; paint(); click(6, 6); click(6, 7)
    assert table.room.gs.board[(6, 7)] == (1, LION)
    shot("tk-captures-480")
    table.fixture("den"); who[0] = 1; paint(); click(3, 7)
    # Exercise the same handler used by focused Tk key events.
    from boardgames.chess_dou.desktop import keyboard
    ui["dou_cursor"] = [3, 7]; keyboard(cv, "Down"); keyboard(cv, "Return")
    assert table.room.gs.winner == 1; shot("tk-finished-480")
    count = len(table.actions); click(3, 8); click(3, 7); assert len(table.actions) == count
    root.geometry("860x650"); root.update(); paint(); root.update(); shot("tk-finished-wide")
    assert not errors, errors
    (output / "tk-actions.json").write_text(json.dumps(table.actions, ensure_ascii=False, indent=2), encoding="utf-8")
    root.destroy()


def web_probe(output):
    import web
    from boardgames.gallery import read_resource
    table = Table()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def reply(self, data, mime="application/json"):
            if mime == "application/json": data = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", mime); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        def do_GET(self):
            if self.path == "/": self.reply(web._SERVED_PAGE(), "text/html; charset=utf-8")
            elif self.path.startswith("/game-art/"):
                try: data, mime = read_resource(self.path.split("/")[-1]); self.reply(data, mime)
                except FileNotFoundError: self.send_error(404)
            elif self.path.startswith("/probe/state/"): self.reply(table.payload(int(self.path.rsplit("/", 1)[-1])))
            else: self.send_error(404)
        def do_POST(self):
            p = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/probe/fixture": table.fixture(p["name"]); self.reply({"ok": True}); return
            try: table.act(p["uid"], p["action"]); self.reply({"ok": True})
            except Exception as error: self.reply({"ok": False, "error": str(error)})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
    try:
        result = subprocess.run(["node", "tests/anime_dou_web_probe.cjs", f"http://127.0.0.1:{server.server_port}", str(output)], cwd=ROOT, timeout=60, capture_output=True, text=True, encoding="utf-8")
        (output / "web-probe.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        assert result.returncode == 0, result.stdout + result.stderr
        (output / "web-actions.json").write_text(json.dumps(table.actions, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        server.shutdown(); server.server_close(); worker.join(5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("mode", choices=("all", "tk", "web")); parser.add_argument("output", type=Path)
    args = parser.parse_args(); output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    if args.mode == "tk": tk_probe(output)
    elif args.mode == "web": web_probe(output)
    else:
        from friend_trial_process import launch_owned
        with tempfile.TemporaryDirectory(prefix="anime-dou-profile-") as directory:
            env = dict(os.environ); env.update({"APPDATA": directory, "LOCALAPPDATA": directory, "PYTHONUTF8": "1"})
            proc = launch_owned([sys.executable, "tests/anime_dou_probe.py", "tk", str(output)], cwd=str(ROOT), env=env, log_path=output/"tk-probe.log", desktop_name="anime-dou-" + str(os.getpid()))
            try:
                code = proc.wait(45); assert code == 0, (output/"tk-probe.log").read_text(encoding="utf-8")
            finally:
                proc.terminate_tree(); proc.close()
        web_probe(output)
    print(json.dumps({"mode": args.mode, "passed": True, "output": str(output)}))
