# -*- coding: utf-8 -*-
"""阿瓦隆（团队推理）。好人：梅林(知晓所有叛军但必须隐藏)、亚瑟忠臣；坏人：刺客、莫德雷德。
流程：领袖选出团队 → 全体投票通过/否决（否决换领袖重提）→ 团队秘密出任务 成功/失败（一次失败即失败）。
3 次成功：刺客指认梅林，指对则坏人胜，指错则好人胜；3 次失败：坏人直接胜。"""
from games_pkg.base import BaseGame, GameRuleError

LOYAL, MERLIN, ASSASSIN, MORDRED = 0, 1, 2, 3
ROLES = {
    LOYAL: ("亚瑟忠臣", "🛡️", "投出通过的团队并尽力成功。"),
    MERLIN: ("梅林", "⭐", "知晓所有叛军，但须隐藏身份。"),
    ASSASSIN: ("刺客", "🗡️", "叛军领袖，终局指认梅林。"),
    MORDRED: ("莫德雷德", "🌑", "叛军：知晓队友，出失败任务。"),
}
NAME = {r: n for r, (n, _, _) in ROLES.items()}
EMO = {r: e for r, (_, e, _) in ROLES.items()}

# 每队任务人数（5 次），按人数取值
QUESTS = {
    4: [2, 3, 2, 3, 3], 5: [2, 3, 2, 3, 3], 6: [2, 3, 4, 3, 4],
    7: [2, 3, 3, 4, 4], 8: [2, 3, 4, 3, 4], 9: [3, 4, 4, 5, 5],
    10: [3, 4, 4, 5, 5],
}


class AvalonGame(BaseGame):
    name = "avalon"
    min_players = 4
    max_players = 10

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.players = list(players)
        n = len(players)
        evil_n = 2 if n >= 5 else 1
        pool = [ASSASSIN, MORDRED][:evil_n] + [MERLIN] + [LOYAL] * (n - evil_n - 1)
        self.rng.shuffle(pool)
        self.role = {u: pool[i] for i, u in enumerate(players)}
        self.evil_uids = {u for u in self.players if self.role[u] in (ASSASSIN, MORDRED)}
        self.merlin_uid = next(u for u in self.players if self.role[u] == MERLIN)
        self.assassin_uid = next(u for u in self.players if self.role[u] == ASSASSIN)
        # 状态
        self.quest = 0                 # 0..4
        self.attempt = 0               # 第几次组队
        self.leader_idx = 0
        self.phase = "nominate"        # nominate → teamvote → quest → (最终指认 final / 下一任务)
        self.team = []                 # 领袖提名的团队
        self.votes = {}                # 团队投票 {uid: 是否通过}
        self.quest_votes = {}          # 执行任务 {uid: True成功/False失败}
        self.results = []              # 每次任务结果 True=成功 False=失败
        self.winner = None
        self.detail = None
        self._need_leader()

    def _quest_size(self):
        return QUESTS[min(len(self.players), 10)][self.quest]

    def _need_leader(self):
        self.phase = "nominate"
        self.team = []
        self.need = [self.players[self.leader_idx]]
        self.acted = []

    def _leader_uid(self):
        return self.players[self.leader_idx % len(self.players)]

    # ---- 快照与私密 ----
    def snapshot(self):
        return {
            "game": self.name, "phase": self.phase,
            "quest": self.quest + 1, "attempt": self.attempt + 1,
            "leader": self._leader_uid(),
            "team": list(self.team), "need_size": self._quest_size(),
            "players": list(self.players),
            "voted": [u for u in self.players if u in self.votes],
            "quest_done": [u for u in self.team if u in self.quest_votes],
            "results": list(self.results),
            "winner": self.winner, "done": self.winner is not None,
        }

    def private(self, uid):
        if uid not in self.role:
            return None
        info = {"role": self.role[uid], "name": NAME[self.role[uid]]}
        if self.role[uid] == MERLIN:
            info["evil"] = sorted(self.evil_uids)
            info["evil_name"] = [NAME[self.role[u]] for u in sorted(self.evil_uids)]
        elif self.role[uid] in (ASSASSIN, MORDRED):
            info["evil"] = sorted(self.evil_uids)
            info["teammates"] = sorted(self.evil_uids - {uid})
            if self.role[uid] == ASSASSIN and self.phase == "final":
                info["guess_required"] = True
        return info

    def act(self, uid, action):
        if self.winner is not None or self.phase in ("done", "final"):
            if not (self.phase == "final" and uid == self.assassin_uid and action.get("op") == "guess"):
                raise GameRuleError("本局已结束")
        if uid not in self.need:
            raise GameRuleError("当前无需你行动")
        if uid in self.acted:
            raise GameRuleError("你已经行动过了")
        msgs = self._do(uid, action)
        self.acted.append(uid)
        msgs.extend(self._advance())
        return msgs

    def _do(self, uid, action):
        nk = self._nick
        if self.phase == "nominate":
            team = action.get("team")
            if not isinstance(team, (list, tuple)) or len(team) != self._quest_size():
                raise GameRuleError(f"需提名 {self._quest_size()} 人")
            team = [int(t) for t in team]
            if len(set(team)) != len(team):
                raise GameRuleError("团队不能重复")
            if any(t not in self.players for t in team):
                raise GameRuleError("含无效玩家")
            self.team = sorted(team)
            self.votes = {}
            self.phase = "teamvote"
            self.need = list(self.players)[:]
            return [f"👑 {nk(uid)} 提议团队：{'、'.join(nk(t) for t in sorted(team))}，请全体投票"]
        if self.phase == "teamvote":
            ok = bool(action.get("approve"))
            self.votes[uid] = ok
            return [f"🗳️ {nk(uid)} {'赞成' if ok else '反对'}这个团队"]
        if self.phase == "quest":
            good = bool(action.get("success"))
            self.quest_votes[uid] = good
            return [f"🃏 {nk(uid)} 任务结果：{'成功' if good else '失败'}"]
        if self.phase == "final":
            t = int(action.get("target"))
            if t not in self.players:
                raise GameRuleError("非法指认目标")
            self.winner = True if (t != self.merlin_uid) else False
            if self.winner:
                self.detail = f"刺客指认 {nk(t)} 失败，好人获胜"
            else:
                self.detail = f"刺客指认 {nk(t)}（梅林），坏人获胜"
            self.phase = "done"
            return [self.detail]
        raise GameRuleError("未知阶段")

    def _advance(self):
        if any(u not in self.acted for u in self.need):
            return []
        msgs = []
        if self.phase == "teamvote":
            yays = sum(1 for v in self.votes.values() if v)
            if yays > len(self.players) / 2:
                self.phase = "quest"
                self.quest_votes = {}
                self.need = list(self.team)
                self.acted = []
                msgs.append(f"✅ 团队通过（{yays} 赞成），成员进入任务")
            else:
                self.attempt += 1
                self.leader_idx = (self.leader_idx + 1) % len(self.players)
                self._need_leader()
                msgs.append(f"❌ 团队被否决，换 {self._nick(self._leader_uid())} 重新组队")
        elif self.phase == "quest":
            msgs = self._resolve_quest()
        return msgs

    def _resolve_quest(self):
        fail = any(not g for g in self.quest_votes.values())
        self.results.append(not fail)
        msgs = []
        if fail:
            msgs.append(f"💥 任务失败！（{'、'.join(self._nick(u) for u in self.quest_votes if not self.quest_votes[u])} 投了失败）")
        else:
            msgs.append("✅ 任务成功！")
        fails = self.results.count(False)
        sues = self.results.count(True)
        if fails >= 3:
            self.winner = False
            self.detail = "坏人方累计 3 次失败，坏人获胜"
            self.phase = "done"
            msgs.append(self.detail)
        elif sues >= 3:
            self.phase = "final"
            self.need = [self.assassin_uid]
            self.acted = []
            msgs.append("🎯 好人方已达成 3 次成功！刺客请指认谁是梅林")
        else:
            self._next_quest()
        return msgs

    def _next_quest(self):
        self.quest += 1
        self.attempt = 0
        self.leader_idx = (self.leader_idx + 1) % len(self.players)
        self._need_leader()

    def ended(self):
        if self.winner is None:
            return None
        return {"winner_uid": None, "winner": self.winner,
                "detail": self.detail or ("🛡️ 好人获胜" if self.winner else "🗡️ 坏人获胜")}

    def _nick(self, uid):
        return f"玩家{uid}"