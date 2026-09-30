# -*- coding: utf-8 -*-
"""一夜狼人：一夜终极狼人简化版。一晚结束，投票处决一人；好人处决全部狼人获胜，狼人存活则胜。
身份：村民(无技能)/狼人/预言家(看一人或中心两张)/强盗(与他人换牌)/失眠者(看自己最终身份)。
只有预言家与强盗需要夜晚操作；其余人只看私密信息。"""
from games_pkg.base import BaseGame, GameRuleError

VILLAGER, WEREWOLF, SEER, ROBBER, INSOMNIAC = 0, 1, 2, 3, 4
ROLES = {
    VILLAGER: ("村民", "👨‍🌾", "无技能，找出狼人投票处决。"),
    WEREWOLF: ("狼人", "🐺", "杀掉好人获胜，夜晚知晓所有狼人。"),
    SEER: ("预言家", "🔮", "夜晚偷看一人的身份，或中心两张。"),
    ROBBER: ("强盗", "🗡️", "夜晚与一人互换身份并查看。"),
    INSOMNIAC: ("失眠者", "😴", "夜晚查看自己最终身份。"),
}
NAME = {r: n for r, (n, _, _) in ROLES.items()}
EMO = {r: e for r, (_, e, _) in ROLES.items()}
# 身份数量 [村民,狼人,预言家,强盗,失眠者]

def _counter(n):
    """依据玩家人数返回身份数量 [村民,狼人,预言家,强盗,失眠者]，保证牌堆 = n+3（每人一张+中心三张）"""
    wolves = 2 if n >= 6 else 1
    special = 3  # 预言家+强盗+失眠者
    villagers = n + 3 - wolves - special  # 至少 2（n=3 时）
    return [villagers, wolves, 1, 1, 1]


class OneNightWolfGame(BaseGame):
    name = "onewolf"
    min_players = 3
    max_players = 10

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.players = list(players)
        deck = []
        for role, c in enumerate(_counter(len(players))):
            deck.extend([role] * c)
        self.rng.shuffle(deck)
        self.original = {u: deck[i] for i, u in enumerate(players)}
        self.role = dict(self.original)
        self.center = deck[len(players):]          # 剩余未发（中心三张无需展示）
        self.phase = "night"                       # night → vote → result
        self.acted = set()                         # 已行动（预言家/强盗）
        self.need_act = {u for u in players if self.original[u] in (SEER, ROBBER)}
        self.votes = {}
        self.dead = []                             # 被处决者
        self.winner = None                         # True=好人胜, False=狼人胜
        self._seer_view = {}                       # uid -> (target_uid, role)
        self._seer_cen = {}                        # uid -> (a, b)
        self._rob_seen = {}                        # uid -> stolen_role

    def snapshot(self):
        return {
            "game": self.name, "phase": self.phase,
            "players": list(self.players),
            "acted": [u for u in self.players if u in self.acted],
            "need_act": [u for u in self.players if u in self.need_act],
            "voted": [u for u in self.players if u in self.votes],
            "dead": list(self.dead),
            "winner": self.winner,
            "reveal": None if self.phase != "result" else {
                str(u): NAME[self.role[u]] for u in self.players
            },
        }

    def private(self, uid):
        """私密信息：身份 + 夜间结果"""
        if uid not in self.role:
            return None
        role = self.role[uid]
        info = {"role": role, "name": NAME[role], "origin": NAME[self.original[uid]]}
        if self.original[uid] == WEREWOLF:
            info["teammates"] = [u for u in self.players if self.original[u] == WEREWOLF and u != uid]
        # 预言家已看的人的信息
        if uid in self._seer_view:
            t, r = self._seer_view[uid]
            info["seer_view"] = {"uid": t, "role": r, "name": NAME[r]}
        if uid in self._seer_cen:
            a, b = self._seer_cen[uid]
            info["seer_center"] = {"a": a, "b": b,
                                   "role_a": NAME[self.center[a]], "role_b": NAME[self.center[b]]}
        if uid in self._rob_seen:
            info["robbed_role"] = NAME[self._rob_seen[uid]]
        return info

    def act(self, uid, action):
        op = action.get("op")
        if self.phase == "night":
            return self._night(uid, action)
        if self.phase == "vote":
            if op != "vote":
                raise GameRuleError("投票阶段只能投票")
            return self._vote(uid, action)
        raise GameRuleError("本局已结束")

    # ---- 夜晚：预言家/强盗行动 ----
    def _night(self, uid, action):
        if uid not in self.need_act:
            raise GameRuleError("你无需夜晚操作")
        if uid in self.acted:
            raise GameRuleError("你已经行动过了")
        role = self.original[uid]
        if role == SEER:
            if "look_one" in action:
                t = action["look_one"]
                if t not in self.players or t == uid:
                    raise GameRuleError("非法目标")
                self._seer_view[uid] = (t, self.role[t])
                self.acted.add(uid)
                msgs = [f"🔮 {self._nick(uid)} 窥看了 {self._nick(t)}"]
            elif "look_center" in action:
                a, b = action["look_center"]
                if not (0 <= a < len(self.center) and 0 <= b < len(self.center) and a != b):
                    raise GameRuleError("中心索引需 0~2 且不同")
                self._seer_cen[uid] = (a, b)
                self.acted.add(uid)
                msgs = [f"🔮 {self._nick(uid)} 窥看了中心两张"]
            else:
                raise GameRuleError("预言家需 look_one 或 look_center")
        elif role == ROBBER:
            t = action.get("rob")
            if t not in self.players or t == uid:
                raise GameRuleError("非法目标")
            self.role[uid], self.role[t] = self.role[t], self.role[uid]
            self._rob_seen[uid] = self.role[uid]   # 偷取后的身份
            self.acted.add(uid)
            msgs = [f"🗡️ {self._nick(uid)} 与 {self._nick(t)} 交换了身份"]
        else:
            raise GameRuleError("该身份无夜间行动")
        if self.need_act <= self.acted:
            self.phase = "vote"
            msgs.append("夜晚结束，全体投票：选出要处决的玩家（target）")
        return msgs

    # ---- 投票 ----
    def _vote(self, uid, action):
        if uid in self.votes:
            raise GameRuleError("你已经投过票")
        t = action.get("target")
        if t not in self.players:
            raise GameRuleError("无效目标")
        self.votes[uid] = t
        msgs = [f"🗳️ {self._nick(uid)} 投给 {self._nick(t)}"]
        if len(self.votes) == len(self.players):
            msgs.extend(self._resolve())
        return msgs

    def _resolve(self):
        cnt = {}
        for t in self.votes.values():
            cnt[t] = cnt.get(t, 0) + 1
        mx = max(cnt.values())
        top = [u for u, c in cnt.items() if c == mx]
        msgs = []
        if len(top) == 1:
            self.dead = [top[0]]
            msgs.append(f"⚖️ {self._nick(top[0])} 以 {mx} 票被处决（身份：{NAME[self.role[top[0]]]}）")
        else:
            msgs.append(f"⚖️ 平票 {len(top)} 人，本晚无人被处决")
        # 胜负判定
        survivors_wolf = [u for u in self.players if self.role[u] == WEREWOLF and u not in self.dead]
        if not survivors_wolf:
            self.winner = True
            msgs.append("🎉 所有狼人都已出局，好人获胜！")
        else:
            self.winner = False
            msgs.append("🐺 仍有狼人存活，狼人获胜！")
        self.phase = "result"
        return msgs

    def ended(self):
        if self.winner is None:
            return None
        return {"winner_uid": None,
                "detail": "好人获胜" if self.winner else "狼人获胜"}

    def player_left(self, uid):
        """夜晚/投票中掉线：剔除并按剩余玩家推进，避免永远等待缺失行动者"""
        if uid not in self.players:
            return []
        msgs = [f"{self._nick(uid)} 离开了游戏"]
        self.players.remove(uid)
        self.role.pop(uid, None)
        self.original.pop(uid, None)
        self.need_act.discard(uid)
        self.acted.discard(uid)
        self.votes.pop(uid, None)
        self._seer_view.pop(uid, None)
        self._seer_cen.pop(uid, None)
        self._rob_seen.pop(uid, None)
        if self.dead:
            self.dead = [u for u in self.dead if u != uid]
        if self.winner is not None or len(self.players) < self.min_players:
            # 人数不足 / 已结束：直接收尾，避免卡局
            wolf_left = any(self.role.get(u) == WEREWOLF for u in self.players)
            self.winner = not wolf_left
            self.phase = "result"
            msgs.append("剩余玩家不足，对局结束")
            return msgs
        if self.phase == "night" and self.need_act.issubset(self.acted):
            self.phase = "vote"
            msgs.append("夜晚结束，全体投票：选出要处决的玩家（target）")
        elif self.phase == "vote" and all(u in self.votes for u in self.players):
            msgs.extend(self._resolve())
        return msgs

    def _nick(self, uid):
        return f"玩家{uid}"