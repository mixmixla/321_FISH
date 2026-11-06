"""Opt-in headless production HTTP/SSE proof. No real account/profile/device."""
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from config import CFG
    from server import Hub
    from server_recovery import StoreCoordinator
    from web import serve
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="blokus-browser-", dir=ROOT / "_tmp_gui") as tmp:
        path = Path(tmp)
        assert path.resolve().is_relative_to((ROOT / "_tmp_gui").resolve())
        StoreCoordinator.initialize_new(path / "store")
        cfg = replace(CFG, admin_pwd=secrets.token_urlsafe(24), bind_host="127.0.0.1",
                      audit_dir=str(path/"audit"), web_files_dir=str(path/"files"),
                      discovery_enabled=False, tray_enabled=False, persist_interval=3600)
        hub = Hub(cfg=cfg, store_dir=str(path/"store"), web_password="")
        hub.rooms._seed_for = lambda room: 19
        listener = serve(hub, port=0, https=False)
        final = {}
        stop = threading.Event()
        def observe_terminal():
            while not stop.wait(.02):
                with hub.rooms.lock:
                    for room in hub.rooms.rooms.values():
                        if room.gs is not None and room.gs.ended() is not None:
                            final.update(room=room.summary(), state=room.gs.snapshot())
        observer = threading.Thread(target=observe_terminal, daemon=True)
        observer.start()
        try:
            result = subprocess.run(["node", str(ROOT/"tests/boards_blokus_browser.cjs"),
                                     str(listener.server_address[1]), str(Path(args.browser).resolve()),
                                     str(path/"chromium"), str(output)], cwd=ROOT,
                                    capture_output=True, text=True, encoding="utf-8", timeout=100,
                                    creationflags=0x08000000 if os.name == "nt" else 0)
            (output/"blokus-browser.log").write_text(result.stdout+result.stderr, encoding="utf-8")
            print(result.stdout, end="")
            if result.returncode:
                print(result.stderr)
            assert result.returncode == 0
            state, room = final["state"], final["room"]
            assert state["placed"][str(room["players"][0])] == 3
            assert state["winner_uid"] == room["players"][0]
            (output/"blokus-server-state.json").write_text(json.dumps(dict(
                room=room, state=state, production_http=True, production_sse=True,
                synthetic_only=True), ensure_ascii=False, indent=2), encoding="utf-8")
        finally:
            stop.set()
            observer.join(2)
            hub.shutdown(normal=False, timeout=8)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
