# -*- coding: utf-8 -*-
"""忍者之夜：全员暗选行动，同时结算。每轮每人秘密选「攻击」(指定目标) 或「防御」；
若攻击对象本回合在防御，则攻击者反被反伤；否则目标掉血。相杀互扣。HP 归零出局，
最后留场者获胜。"""
from games_pkg.base import BaseGame, GameRuleError

HP = 3            # 初始生命
ATTACK, GUARD = "attack", "guard"


class NinjaNightGame(BaseGame):
    name = "ninja"
    min_players = 3
    max_players = 8

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.players = list(players)
        self.hp = {u: HP for u in players}
        self.alive = set(players)
        self.round = 1
        self.phase = "pick"          # pick → resolve
        self.moves = {}              # {uid: {"move":..., "target":...}}
        self._last_report = None
        self.winner = None
        self.detail = None

    def snapshot(self):
        return {
            "game": self.name, "phase": self.phase, "round": self.round,
            "players": list(self.players),
            "alive": sorted(self.alive),
            "hp": {str(u): self.hp[u] for u in self.players},
            "picked": list(self.moves.keys()),
            "last": self._last_report if self.phase == "resolve" else None,
            "winner": self.winner, "done": self.winner is not None,
        }

    def private(self, uid):
        if uid not in self.players:
            return None
        return {"hp": self.hp[uid]}

    def act(self, uid, action):
        if self.winner is not None:
            raise GameRuleError("本局已结束")
        if uid not in self.alive:
            raise GameRuleError("你已出局")
        if action.get("op") == "next":
            if self.phase != "resolve":
                raise GameRuleError("当前无需进入下一回合")
            self.round += 1
            self.phase = "pick"
            self.moves = {}
            self._last_report = None
            return [f"第 {self.round} 回合开始，请选择行动"]
        if self.phase != "pick":
            raise GameRuleError("等待结算中，先进入下一回合")
        if uid in self.moves:
            raise GameRuleError("你已提交")
        move = action.get("move")
        if move not in (ATTACK, GUARD):
            raise GameRuleError("请选择 攻击 或 防御")
        if move == ATTACK:
            t = action.get("target")
            if t not in self.alive:
                raise GameRuleError("攻击目标需为存活玩家")
        else:
            t = None
        self.moves[uid] = {"move": move, "target": t}
        msgs = [f"🥷 {self._nick(uid)} 已选择行动（保密）"]
        alive = [p for p in self.players if p in self.alive]
        if len(self.moves) == len(alive):
            msgs.extend(self._resolve())
        return msgs

    def _resolve(self):
        mv, hp = self.moves, self.hp
        # 先统计防御者（防御只对“被攻击”生效，二人同时互相攻击时双方皆掉血/反击规则见下）
        guard = {u for u, m in mv.items() if m["move"] == GUARD}
        hurt = {}                       # uid -> 次数
        for u, m in mv.items():
            if m["move"] != ATTACK:
                continue
            t = m["target"]
            if t in guard:
                hurt[u] = hurt.get(u, 0) + 1      # 反击：自己掉血
            else:
                hurt[t] = hurt.get(t, 0) + 1      # 目标掉血
        log = []
        for u in self.players:
            if u not in hp:
                continue
            n = hurt.get(u, 0)
            if n:
                hp[u] -= n
                log.append(f"💥 {self._nick(u)} 本回合受到 {n} 点攻击")
        new_out = [u for u in self.alive if hp.get(u, 0) <= 0]
        for u in new_out:
            self.alive.discard(u)
            log.append(f"💀 {self._nick(u)} 生命归零，忍者出局！")
        self.phase = "resolve"
        self._last_report = log
        if len(self.alive) <= 1:
            self.winner = next(iter(self.alive), None)
            self.detail = (f"{self._nick(self.winner)} 成为最后存活的忍者" if self.winner is not None else "全部出局，无人获胜")
            log.append("🏁 " + self.detail)
        else:
            log.append(f"进入第 {self.round + 1} 回合，请再次选择行动")
        return log

    def tick(self, now: float) -> list:
        return []

    def ended(self):
        if self.winner is None and self.phase == "resolve":
            return None   # 待下一回合
        if self.winner is None:
            return None
        return {"winner_uid": self.winner, "detail": self.detail}

    def _nick(self, uid):
        return f"玩家{uid}"