"""Thin two-lane frontend for run.py test-all. No retries or pytest reimplementation."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import test_gate as gate

ROOT = Path(__file__).resolve().parent
# Reviewed on 0ac1ed4: games_pkg + standard library/pytest only; rooms use an
# in-process RLock, not sockets/servers/timers. New files stay serial.
RULE_FILES = frozenset("tests/" + name for name in """
test_azul_rules.py test_batch2_rules.py test_batch3_rules.py
test_batch4a_rules.py test_batch4b_rules.py test_batch4c_rules.py
test_batch4d_rules.py test_betrayal.py test_blokus_rules.py
test_checkers_rules.py test_fix_deadlock_selfcheck.py test_game_lifecycle.py
test_game_owner_recovery.py test_games.py test_games_coc.py test_games_euro.py
test_games_new.py test_games_w1_new.py test_games_w2_logic.py test_games_w3.py
test_games_w3_rooms.py test_games_w4.py test_games_w4b.py
test_games_w5_avalon.py test_games_w5_liar.py test_games_w5_ninja.py
test_games_w5_onewolf.py test_games_w5_werewolf.py test_gemcity_purchase.py
test_go_solo.py test_gomoku_rules.py test_kalah_terminal.py
test_legal_moves_a.py test_legal_moves_b.py test_legal_moves_c.py
test_ludo_rules.py test_othello_rules.py test_robber_rules.py test_rooms.py
test_round_flow.py test_rule_gaps_a.py test_rule_gaps_b.py test_rule_gaps_c.py
test_rule_gaps_d.py test_tielu_play.py
""".split())
# This contract file spawns two synthetic pytest children: run it alone so
# even the nested checks stay within three pytest processes on this machine.
EXCLUSIVE_FILES = frozenset({"tests/test_fast_verify.py"})


def partition(files, priority, serial=False, gui_files=()):
    if set(priority) - set(files):
        raise ValueError("priority files must be in the selected suite")
    rest = sorted(set(files) - set(priority))
    exclusive = sorted(set(rest) & EXCLUSIVE_FILES)
    rest = [name for name in rest if name not in exclusive]
    # Measured Tk event-loop slowdown erased parallel savings. Keep native
    # GUI-hint files alone, then overlap only the remaining conservative lane.
    gui = [] if serial else sorted(set(rest) & set(gui_files))
    rest = [name for name in rest if name not in gui]
    rules = [] if serial else [name for name in rest if name in RULE_FILES]
    return {key: value for key, value in {
        "priority": sorted(set(priority)), "exclusive": exclusive, "gui": gui,
        "serial": [name for name in rest if name not in rules], "rules": rules,
    }.items() if value}


def run_lane(run_dir, plan, lane):
    stop = run_dir / "STOP"
    command = [sys.executable, str(ROOT / "run.py"), "test-all",
               *plan["lanes"][lane], "--source-dir", plan["source_dir"],
               "--run-dir", str(run_dir / lane), "--timeout", str(plan["timeout"]),
               "--fail-fast", "--stop-file", str(stop)]
    with (run_dir / (lane + ".runner.log")).open("wb") as log:
        process = subprocess.Popen(
            command, cwd=plan["source_dir"], stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        try:
            code = process.wait()
        except BaseException:
            stop.touch(exist_ok=True)
            process.wait()  # Native gate drains its current bounded file.
            raise
    if code:
        stop.touch(exist_ok=True)
    print(json.dumps({"lane": lane, "exit_code": code}), flush=True)
    return {"exit_code": code, "command": command, "summary": f"{lane}/summary.json"}


def collect(run_dir, plan, outcomes):
    errors, results, failures = [], [], []
    totals, identities = Counter(), set()
    for lane, outcome in outcomes.items():
        summary = gate._load_json(run_dir / outcome["summary"])
        if summary["exit_code"] != outcome["exit_code"]:
            errors.append(f"{lane}: summary/process exit mismatch")
        if outcome["exit_code"] == 2:
            errors.append(f"{lane}: native infrastructure failure")
        if summary.get("cleanup_failures"):
            errors.append(f"{lane}: process cleanup failed")
        if outcome["exit_code"]:
            failures.append(lane)
        identities.add((summary["source_content_id"], summary["dependency_content_id"]))
        lane_results = summary["results"]
        if set(r["file"] for r in lane_results) - set(plan["lanes"][lane]):
            errors.append(f"{lane}: unplanned test file")
        totals.update(summary["totals"])
        for record in lane_results:
            results.append({"file": record["file"], "lane": lane,
                            "status": record["status"], "counts": record["counts"],
                            "exit_code": record["exit_code"]})
            if record["status"] != "passed" or record["exit_code"]:
                failures.append(record["file"])
    if len(identities) != 1:
        errors.append("lane source/dependency identities differ or are missing")
    actual = Counter(record["file"] for record in results)
    missing = sorted(set(plan["files"]) - set(actual))
    duplicates = sorted(name for name, count in actual.items() if count != 1)
    extra = sorted(set(actual) - set(plan["files"]))
    if duplicates or extra:
        errors.append("duplicate/unplanned test execution")
    source_id, dependency_id = next(iter(identities), (None, None))
    return {"source_content_id": source_id, "dependency_content_id": dependency_id,
            "full_suite": plan["full_suite"], "planned_files": len(plan["files"]),
            "files": len(results), "missing": missing, "duplicates": duplicates,
            "extra": extra, "totals": dict(totals), "failures": failures,
            "errors": errors, "lanes": outcomes, "results": results,
            "exit_code": 2 if errors else (1 if failures or missing else 0)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("test_files", nargs="*", help="省略则覆盖所有 tests/test_*.py")
    parser.add_argument("--priority", action="append", default=[], metavar="FILE")
    parser.add_argument("--source-dir", type=Path, default=ROOT)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument("--serial", action="store_true", help="单队列对照")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.timeout <= 0:
            raise ValueError("timeout must be positive")
        source = args.source_dir.resolve()
        files = [p.relative_to(source).as_posix()
                 for p in gate.discover_test_files(source, args.test_files)]
        priority = [p.relative_to(source).as_posix()
                    for p in gate.discover_test_files(source, args.priority)] if args.priority else []
        if not files:
            raise ValueError("empty test selection")
        plan = {"source_dir": str(source), "files": files,
                "full_suite": not args.test_files, "timeout": args.timeout,
                "lanes": partition(files, priority, args.serial,
                                   [name for name in files if gate._gui_hint(source / name)])}
        if args.plan_only:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0
        if args.run_dir is None:
            raise ValueError("--run-dir is required; use a new directory")
        run_dir = gate._checked_run_path(args.run_dir)
        if run_dir.exists():
            raise ValueError("run-dir already exists; no retries/overwrites")
        run_dir.mkdir(parents=True)
        gate._atomic_json(run_dir / "plan.json", plan)
        started, outcomes = time.monotonic(), {}
        for lane in ("priority", "exclusive", "gui"):
            if lane in plan["lanes"] and not (run_dir / "STOP").exists():
                outcomes[lane] = run_lane(run_dir, plan, lane)
        if not (run_dir / "STOP").exists():
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {lane: pool.submit(run_lane, run_dir, plan, lane)
                           for lane in ("serial", "rules") if lane in plan["lanes"]}
                try:
                    outcomes.update((lane, future.result()) for lane, future in futures.items())
                except BaseException:
                    (run_dir / "STOP").touch(exist_ok=True)
                    raise  # Executor waits for the native gates' bounded cleanup.
        report = collect(run_dir, plan, outcomes)
        report["seconds"] = round(time.monotonic() - started, 3)
        gate._atomic_json(run_dir / "summary.json", report)
        print("FAST_VERIFY " + json.dumps({k: v for k, v in report.items()
                                           if k != "results"}, ensure_ascii=False))
        return report["exit_code"]
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"FAST_VERIFY refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
