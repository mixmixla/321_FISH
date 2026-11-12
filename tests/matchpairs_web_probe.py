"""Opt-in production HTTP/SSE browser proof with an isolated synthetic store."""
import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import CFG
from games_pkg.matchpairs import MatchPairsGame
from server import Hub
from server_recovery import StoreCoordinator
from web import _SERVED_PAGE, serve

EVIDENCE = ROOT / "_tmp_gui" / "matchpairs-web-20261111"
SOURCES = ("web.py", "boardgames/gallery.py", "boardgames/cards_matchpairs_web.py",
           "boardgames/cards_pending_web.py", "games_pkg/matchpairs.py",
           "assets/boardgame/gallery/cards-matchpairs-hostess.webp")


def indexed_plan(count, seed):
    game = MatchPairsGame(range(1, count + 1), seed)
    indices = []
    while not game.ended() and len(indices) < 80:
        state = game.snapshot()
        actor, target = state["turn_uid"], state["draw_from_uid"]
        held = {rank for rank, _ in game.hands[actor]}
        matches = [i for i, (rank, _) in enumerate(game.hands[target]) if rank in held]
        index = matches[-1] if matches else 0
        game.act(actor, {"op": "draw", "target": target, "index": index,
                         "round_key": game.round_key, "seq": game.seq})
        indices.append(index)
    assert game.ended() and indices
    return indices


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("art", "final"), required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    out = (EVIDENCE / args.run).resolve()
    if out.parent != EVIDENCE.resolve():
        parser.error("run must be a direct child of the evidence directory")
    out.mkdir(parents=True, exist_ok=False)
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}
    source = dict(head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  files=hashes, served_sha256=hashlib.sha256(_SERVED_PAGE()).hexdigest())
    source["id"] = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
    (out / "source.json").write_text(json.dumps(source, indent=2), encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="matchpairs-profile-", dir=EVIDENCE) as folder:
        tmp = Path(folder).resolve()
        assert tmp.is_relative_to(EVIDENCE.resolve())
        StoreCoordinator.initialize_new(tmp / "store")
        cfg = replace(CFG, admin_pwd=secrets.token_urlsafe(24), bind_host="127.0.0.1",
                      audit_dir=str(tmp / "audit"), web_files_dir=str(tmp / "files"),
                      discovery_enabled=False, tray_enabled=False, persist_interval=3600)
        hub = Hub(cfg=cfg, store_dir=str(tmp / "store"), web_password="")
        seeds = {5: [108, 66], 2: [19, 42]}
        hub.rooms._seed_for = lambda room: seeds[len(room.players)][min(room.round_no, 1)]
        listener = serve(hub, port=0, https=False)
        config = dict(url=f"http://127.0.0.1:{listener.server_address[1]}", output=str(out), stage=args.stage,
                      runtime=str(args.runtime.resolve()), cache=str(args.cache.resolve()), source=source,
                      plans={n: [indexed_plan(n, seed) for seed in values] for n, values in seeds.items()})
        fixture = tmp / "fixture.json"
        fixture.write_text(json.dumps(config), encoding="utf-8")
        try:
            result = subprocess.run(["node", str(ROOT / "tests" / "matchpairs_web_probe.cjs"), str(fixture)],
                                    cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                                    timeout=125, creationflags=0x08000000 if os.name == "nt" else 0)
            (out / "probe.log").write_text(result.stdout + result.stderr, encoding="utf-8")
            print(result.stdout, end="")
            if result.returncode:
                print(result.stderr, end="")
            assert result.returncode == 0
        finally:
            hub.shutdown(normal=False, timeout=8)
            (out / "cleanup.json").write_text(json.dumps({"hub_shutdown_returned": True,
                "child_returned": "result" in locals(), "synthetic_profile": True}), encoding="utf-8")


if __name__ == "__main__":
    main()
