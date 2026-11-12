"""Opt-in real HTTP/SSE and headless browser probe for the Who Is the Spy table."""

import argparse
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import CFG
from friend_trial_process import launch_owned
from server import Hub
from server_recovery import StoreCoordinator
from web import _SERVED_PAGE, serve

EVIDENCE = ROOT / "_tmp_gui" / "spy-web-20261112"


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def bind_source():
    paths = [ROOT / name for name in ("web.py", "server.py", "games_pkg/rooms.py", "games_pkg/spy.py", "boardgames/spy_web.py",
             "boardgames/gallery.py", "boardgames/cards_pending_web.py",
             "tests/spy_web_probe.py", "tests/spy_web_probe.cjs")]
    paths.extend(sorted((ROOT / "assets" / "boardgame" / "gallery").glob("spy-*.webp")))
    source = {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "files": {path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest() for path in paths},
        "served_sha256": sha256(_SERVED_PAGE()).hexdigest(),
    }
    source["id"] = sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
    return source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("art", "final", "departure"), required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    out = (EVIDENCE / args.run).resolve()
    if out.parent != EVIDENCE.resolve():
        parser.error("run must be a direct child of the evidence directory")
    out.mkdir(parents=True, exist_ok=False)
    source = bind_source()
    write_json(out / "source.json", source)
    cleanup = {"loopback": True, "synthetic_profile": True}
    with tempfile.TemporaryDirectory(prefix="spy-profile-", dir=EVIDENCE) as folder:
        tmp = Path(folder)
        StoreCoordinator.initialize_new(tmp / "store")
        cfg = replace(CFG, admin_pwd=secrets.token_urlsafe(24), bind_host="127.0.0.1",
                      audit_dir=str(tmp / "audit"), web_files_dir=str(tmp / "files"),
                      discovery_enabled=False, tray_enabled=False, persist_interval=3600)
        hub = Hub(cfg=cfg, store_dir=str(tmp / "store"), web_password="")
        try:
            listener = serve(hub, port=0, https=False)
            fixture = tmp / "fixture.json"
            write_json(fixture, {"url": f"http://127.0.0.1:{listener.server_address[1]}",
                       "output": str(out), "stage": args.stage, "runtime": str(args.runtime.resolve()),
                       "cache": str(args.cache.resolve()), "source": source})
            env = dict(os.environ, TMP=str(tmp), TEMP=str(tmp))
            child = launch_owned([shutil.which("node"), str(ROOT / "tests" / "spy_web_probe.cjs"), str(fixture)],
                                 cwd=str(ROOT), env=env, log_path=out / "probe.log")
            cleanup["node_pid"] = child.pid
            try:
                cleanup["exit_code"] = child.wait(180)
            finally:
                cleanup["owned_processes_before_close"] = child.active_count()
                cleanup["owned_process_tree_stopped"] = child.terminate_tree()
                child.close()
        finally:
            hub.shutdown(normal=False, timeout=8)
            cleanup["hub_shutdown_returned"] = True
            write_json(out / "cleanup.json", cleanup)
    cleanup["profile_removed"] = not tmp.exists()
    write_json(out / "cleanup.json", cleanup)
    print((out / "probe.log").read_text(encoding="utf-8", errors="replace"), end="")
    if cleanup.get("exit_code") != 0 or not cleanup["owned_process_tree_stopped"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
