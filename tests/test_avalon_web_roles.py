"""Actual Avalon private snapshots against the production Web renderer."""
import copy
import json
from pathlib import Path
import shutil
import subprocess

from games_pkg.avalon import AvalonGame, ASSASSIN, MORDRED, LOYAL
from games_pkg.gongfang import GongfangGame
import web


def test_real_private_roles_match_web_hints_and_final_guess(tmp_path):
    game = AvalonGame([11, 12, 13, 14, 15], seed=3)
    for _ in range(3):
        game.act(game.players[game.leader_idx], {"team": game.players[:game._quest_size()]})
        for uid in game.players:
            game.act(uid, {"approve": True})
        for uid in list(game.team):
            game.act(uid, {"success": True})
    assert game.phase == "final"
    source = Path(web.__file__).read_text(encoding="utf-8")
    start = source.index("avalon(box,s){")
    data = tmp_path / "avalon.json"
    traces = []
    for outcome in ("good", "assassinate", "failed_quests"):
        flow = AvalonGame([11, 12, 13, 14, 15], seed=3)
        steps = []

        def step(uid, action):
            steps.append({"uid": uid, "snapshot": copy.deepcopy(flow.snapshot()),
                          "private": flow.private(uid), "action": action})
            flow.act(uid, action)

        for quest in range(3):
            team = flow.players[:flow._quest_size()]
            if outcome == "failed_quests":
                evil = [uid for uid in flow.players if flow.role[uid] in (ASSASSIN, MORDRED)]
                team = sorted((evil + [uid for uid in flow.players if uid not in evil])[:flow._quest_size()])
            step(flow.players[flow.leader_idx], {"team": team})
            for index, uid in enumerate(flow.players):
                step(uid, {"approve": index != 0})  # one legal rejection; majority still approves
            fail_role = ASSASSIN if quest != 1 else MORDRED
            for uid in list(flow.team):
                step(uid, {"success": not (outcome == "failed_quests" and flow.role[uid] == fail_role)})
        if outcome != "failed_quests":
            target = flow.merlin_uid if outcome == "assassinate" else next(uid for uid in flow.players if flow.role[uid] == LOYAL)
            step(flow.assassin_uid, {"op": "guess", "target": target})
        assert flow.phase == "done"
        traces.append({"name": outcome, "steps": steps, "winner": flow.winner})
    workshop = GongfangGame([11, 12], seed=1)
    workshop.act(11, {"op": "work", "id": 0})
    workshop_start = source.index("gongfang(box,s){")
    data.write_text(json.dumps({"renderer": source[start:source.index("  liar(box,s){", start)],
                               "snapshot": game.snapshot(),
                               "private": {uid: game.private(uid) for uid in game.players},
                               "traces": traces, "workshop": workshop.snapshot(),
                               "gongfang": source[workshop_start:source.index("  chengzhu(box,s){", workshop_start)]}), encoding="utf-8")
    node = shutil.which("node")
    assert node
    result = subprocess.run([node, str(Path(__file__).with_name("avalon_web_role_probe.cjs")), str(data)],
                            capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["only_assassin_guess"] and report["workshop_no_false_exclusive"]
    for trace, produced in zip(traces, report["actions"]):
        replay = AvalonGame([11, 12, 13, 14, 15], seed=3)
        assert len(produced) == len(trace["steps"])
        for step, action in zip(trace["steps"], produced):
            assert replay.snapshot() == step["snapshot"]
            replay.act(step["uid"], action)  # actual actions emitted by the production renderer
        assert replay.phase == "done" and replay.winner is trace["winner"]
