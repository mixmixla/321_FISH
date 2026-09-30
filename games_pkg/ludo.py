# -*- coding: utf-8 -*-
"""飞行棋（致敬 Ludo）：4 色各 4 架机，掷骰(1~6)前进，掷 6 可再次投掷。机棚内的机需掷 6 才起飞；
沿 40 格轨道绕行一圈回到自家起算“完成”，最后一家机落地踩到他人掷子则将其送回机棚。
先把 4 架机全部飞到终点的玩家胜。"""
from games_pkg.base import BaseGame, GameRuleError

NS = 4              # 每人机数
TRACK = 40          # 一圈格数
FIN = 40            # 走到 40 视为完成

STONE_CN = ["✈️", "🚢", "🚗", "🚁"]


class LudoGame(BaseGame):
    name = "ludo"
    min_players = 2
    max_players = 4

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.start0 = 0
        self.turn = 0
        self.miles = {u: [-1] * NS for u in players}   # -1=机棚, >=40=完成
        self.dice = None
        self.need_roll = True
        self.winner = None
        self.last_roll = None
        self.finished_seq = []

    # ---- 轨道位置 ----
    def _start(self, i):
        return (self.start0 + i * (TRACK // 4)) % TRACK

    def _stall_of(self, idx):
        """玩家下标->其4架机在轨道上所在格(映射吞并判定)，仅对起飞且未完成的机"""
        u = self.players[idx]
        out = []
        for s in self.miles[u]:
            if -1 < s < FIN:
                out.append((self._start(idx) + s) % TRACK)
        return out

    def _collide_others(self, uid, target_stall):
        for oi, ou in enumerate(self.players):
            if ou == uid:
                continue
            for k, s in enumerate(self.miles[ou]):
                if -1 < s < FIN and (self._start(oi) + s) % TRACK == target_stall:
                    self.miles[ou][k] = -1          # 送回机棚
                    return ou, k
        return None, None

    def act(self, uid, action):
        if self.winner:
            raise GameRuleError("本局已结束")
        if uid != self.players[self.turn]:
            raise GameRuleError("还没轮到你")
        op = action.get("op")
        if op == "roll":
            return self._roll()
        if op == "move":
            return self._move(action)
        if op == "skip":
            return [self._end_turn_msgs("主动结束本回合")]
        raise GameRuleError("未知操作")

    def _roll(self):
        if not self.need_roll:
            raise GameRuleError("先让一架机前进，或已过")
        d = self.rng.randint(1, 6)
        self.dice = d
        self.last_roll = d
        self.need_roll = False
        msgs = [f"🎲 {self._nick(self.players[self.turn])} 掷出 {d}"]
        if self._moves_available() == 0:
            msgs.append(self._end_turn_msgs("无机能动，回合结束"))
        return msgs

    def _moves_available(self):
        """可动车数：能起飞的(6且有棚内机) / 前进不超圈不越过FIN的"""
        u = self.players[self.turn]
        cnt = 0
        for s in self.miles[u]:
            if s == -1:
                if self.dice == 6:
                    cnt += 1
            elif s + self.dice <= FIN:
                cnt += 1
        return cnt

    def _move(self, action):
        if self.need_roll:
            raise GameRuleError("请先掷骰")
        if self.dice is None:
            raise GameRuleError("先掷骰")
        idx = action.get("idx")
        try:
            idx = int(idx)
        except (TypeError, ValueError):
            raise GameRuleError("机号无效")
        u = self.players[self.turn]
        if not (0 <= idx < NS):
            raise GameRuleError("机号超出范围")
        s = self.miles[u][idx]
        if s == -1:
            if self.dice != 6:
                raise GameRuleError("需掷 6 才能起飞")
            s = 0
            msgs = [f"🛫 {self._nick(u)} 第 {idx + 1} 架 {STONE_CN[idx]} 起飞！"]
        elif s + self.dice > FIN:
            raise GameRuleError("该机无法步进过终点")
        else:
            s += self.dice
            msgs = [f"✈️ {self._nick(u)} 第 {idx + 1} 架 {STONE_CN[idx]} 前进 {self.dice} 格"]
        self.miles[u][idx] = s
        self.dice_val = s
        if s < FIN:
            ti = self._start(self.turn)
            stall = (ti + s) % TRACK
            hit, _ = self._collide_others(u, stall)
            if hit is not None:
                msgs.append(f"💥 {self._nick(u)} 把 {self._nick(hit)} 的一架机送回机棚！")
        if s >= FIN:
            self.finished_seq.append(u)
            msgs.append(f"🏁 {self._nick(u)} 第 {idx + 1} 架机到达终点！")
            if all(m >= FIN or m == -1 for m in self.miles[u]) and self.miles[u][idx] >= FIN:
                if all(mm >= FIN for mm in self.miles[u]):
                    self.winner = u
                    msgs.append(f"🏆 {self._nick(u)} 四架机全部到达，获胜！")
                    return msgs
        self.dice = None
        self.need_roll = True
        return msgs

    def _end_turn_msgs(self, why):
        self.dice = None
        self.need_roll = True
        self.turn = (self.turn + 1) % len(self.players)
        return f"⏭️ {why} → 轮到 {self._nick(self.players[self.turn])}" \
            if self.turn != 0 else f"⏭️ {why}"

    def snapshot(self):
        def row(u):
            out = []
            for s in self.miles[u]:
                if s == -1:
                    out.append(-1)
                elif s >= FIN:
                    out.append("FIN")
                else:
                    out.append((self._start(self.players.index(u)) + s) % TRACK)
            return out
        return {
            "game": self.name, "status": "playing",
            "turn_uid": None if self.winner else self.players[self.turn],
            "positions": {str(u): row(u) for u in self.players},
            "starts": {str(self.players[i]): self._start(i) for i in range(len(self.players))},
            "track": TRACK, "dice": self.dice, "winner_uid": self.winner,
            "stones": STONE_CN, "players": list(self.players),
        }

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner, "detail": f"{self._nick(self.winner)} 率先四架登岛"}
        return None

    def _nick(self, uid):
        return f"玩家{uid}"