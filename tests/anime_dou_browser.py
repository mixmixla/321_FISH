"""Production Hub + HTTP/SSE, synthetic isolated Store, headless browser only."""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from config import CFG
    from server import Hub
    from server_recovery import StoreCoordinator
    from web import serve
    from games_pkg.dou import CAT, DOG, LION, MOUSE
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dou-wire-", dir=ROOT / "_tmp_gui") as tmp:
        path = Path(tmp); StoreCoordinator.initialize_new(path / "store")
        cfg = replace(CFG, admin_pwd=secrets.token_urlsafe(24), bind_host="127.0.0.1",
                      audit_dir=str(path/"audit"), web_files_dir=str(path/"files"),
                      discovery_enabled=False, tray_enabled=False, persist_interval=3600)
        hub = Hub(cfg=cfg, store_dir=str(path/"store"), web_password="")
        listener = serve(hub, port=0, https=False)

        class Control(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_POST(self):
                with hub.rooms.lock:
                    room = next(iter(hub.rooms.rooms.values())); g = room.gs
                    g.winner = None; g.last_event = None; g.last_move = None; g.turn = 0
                    if self.path == "/capture":
                        g.board = {(0, 2): (0, DOG), (0, 1): (1, CAT), (6, 6): (1, LION), (6, 7): (0, CAT)}
                    else:
                        g.board = {(3, 7): (0, MOUSE), (0, 0): (1, CAT)}
                self.send_response(200); self.end_headers(); self.wfile.write(b"ok")

        controller = ThreadingHTTPServer(("127.0.0.1", 0), Control)
        worker = threading.Thread(target=controller.serve_forever, daemon=True); worker.start()
        try:
            result = subprocess.run(["node", "tests/anime_dou_production.cjs", str(listener.server_address[1]), str(output), str(controller.server_address[1])], cwd=ROOT, timeout=65, capture_output=True, text=True, encoding="utf-8", creationflags=0x08000000 if os.name == "nt" else 0)
            (output/"production-browser.txt").write_text(result.stdout+result.stderr, encoding="utf-8")
            assert result.returncode == 0, result.stdout + result.stderr
            room = next(iter(hub.rooms.rooms.values()))
            assert room.gs.snapshot()["winner_uid"] == room.players[0]
            (output/"production-server.json").write_text(json.dumps({"room": room.summary(), "state": room.gs.snapshot(), "production_http": True, "production_sse": True, "synthetic_only": True}, ensure_ascii=False, indent=2), encoding="utf-8")
            print("Production HTTP/SSE: PASS")
        finally:
            controller.shutdown(); controller.server_close(); worker.join(5)
            hub.shutdown(normal=False, timeout=8)
    return 0


if __name__ == "__main__": raise SystemExit(main())
