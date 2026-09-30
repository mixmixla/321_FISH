# -*- coding: utf-8 -*-
"""狼人杀：经典多人社交推理（多夜多日）。角色：村民/狼人/预言家/女巫/猎人。
夜晚顺序：预言家验人 → 狼人樵刀 → 女巫救/毒（被灭火死不能开枪）；天亮结算死伤。
白天：讨论后全员投票放逐一人；猎人被放逐或死于夜晚均可开枪带走一人。
胜负：狼人全灭→好人胜；存活好人不多于存活狼人→狼人胜。"""
from games_pkg.base import BaseGame, GameRuleError

VILLAGER, WEREWOLF, SEER, WITCH, HUNTER = 0, 1, 2, 3, 4
ROLES = {
    VILLAGER: ("村民", "👨‍🌾", "找出狼人投票放逐。"),
    WEREWOLF: ("狼人", "🐺", "夜晚刀一人，杀光好人团获胜。"),
    SEER: ("预言家", "🔮", "每晚查验一人的身份。"),
    WITCH: ("女巫", "🧪", "一晚可救一人（解药）或毒一人（毒药），各一次。"),
    HUNTER: ("猎人", "🏹", "死亡时可开枪带走一人（被毒死除外）。"),
}
NAME = {r: n for r, (n, _, _) in ROLES.items()}
EMO = {r: e for r, (_, e, _) in ROLES.items()}


def _counter(n):
    """身份数量 [村民,狼人,预言家,女巫,猎人]，总数 = n"""
    wolves = 2 if n >= 8 else 1
    return [n - wolves - 3, wolves, 1, 1, 1]


class WerewolfGame(BaseGame):
    name = "werewolf"
    min_players = 6
    max_players = 16

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.players = list(players)
        deck = []
        for role, c in enumerate(_counter(len(players))):
            deck.extend([role] * c)
        self.rng.shuffle(deck)
        self.role = {u: deck[i] for i, u in enumerate(players)}
        self.alive = set(players)
        self.hunter_uid = next(u for u in self.players if self.role[u] == HUNTER)
        # 夜间状态
        self.phase = "night_seer"          # night_seer→night_wolf→night_witch→shoot→day→(下一夜)
        self.night = 1
        self.acted = []
        self.need = []
        self.seer_view = None              # {target, role, name}
        self.wolf_kill = None
        self.witch_saved = False
        self.witch_saved_uid = None
        self.witch_poison = None
        self.witch_save_left = True
        self.witch_poison_left = True
        self.votes = {}
        self.lynched = None
        self.hunter_shot = False
        self.shoot_pending = False
        self.winner = None
        self._reset_phase("night_seer",
                          [u for u in self.players if self.role[u] == SEER])

    # ---- 快照与私密 ----
    def snapshot(self):
        return {
            "game": self.name, "phase": self.phase, "night": self.night,
            "players": list(self.players), "alive": sorted(self.alive),
            "acted": list(self.acted), "need": list(self.need),
            "voted": [u for u in self.players if u in self.votes],
            "lynched": self.lynched, "winner": self.winner,
            "done": self.winner is not None,
        }

    def private(self, uid):
        if uid not in self.role:
            return None
        info = {"role": self.role[uid], "name": NAME[self.role[uid]]}
        if self.role[uid] == WEREWOLF:
            info["teammates"] = [u for u in self.players
                                 if self.role[u] == WEREWOLF and u != uid]
        if self.witch_saved_uid == uid:
            info["saved_by_witch"] = True
        if uid == self.hunter_uid and not self.hunter_shot:
            info["hunter"] = True
        if self.role[uid] == SEER and self.seer_view:
            info["seer_view"] = dict(self.seer_view)
        # 女巫：夜晚被告知狼刀目标
        if self.role[uid] == WITCH and self.phase == "night_witch" and self.wolf_kill:
            info["witch_kill"] = self.wolf_kill
        return info

    def act(self, uid, action):
        if self.winner is not None or self.phase == "done":
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
        op = action.get("op")
        nk = self._nick
        if self.phase == "night_seer":
            t = action.get("target")
            if t not in self.players or t == uid or t not in self.alive:
                raise GameRuleError("非法查验目标")
            self.seer_view = {"target": t, "role": self.role[t], "name": NAME[self.role[t]]}
            return [f"🔮 预言家查验了 {nk(t)}"]
        if self.phase == "night_wolf":
            t = action.get("target")
            if t not in self.players or t == uid or t not in self.alive:
                raise GameRuleError("非法刀人目标")
            if self.role[t] == WEREWOLF:
                raise GameRuleError("狼人不能刀自己的队友")
            self.wolf_kill = t
            return [f"🐺 狼人决定刀 {nk(t)}"]
        if self.phase == "night_witch":
            if op == "save":
                if not self.witch_save_left:
                    raise GameRuleError("解药已用完")
                self.witch_saved = True
                self.witch_save_left = False
                return [f"🧪 女巫用了解药"]
            if op == "poison":
                if not self.witch_poison_left:
                    raise GameRuleError("毒药已用完")
                t = action.get("target")
                if t not in self.players or t == uid or t not in self.alive:
                    raise GameRuleError("非法毒杀目标")
                self.witch_poison = t
                self.witch_poison_left = False
                return [f"🧪 女巫使用了毒药"]
            raise GameRuleError("女巫需 save 或 poison")
        if self.phase == "shoot":
            t = action.get("target")
            if t not in self.players or t == uid or t not in self.alive:
                raise GameRuleError("非法开枪目标")
            self.alive.discard(t)
            self.hunter_shot = True
            self._maybe_end()
            return [f"🏹 {nk(uid)} 开枪带走 {nk(t)}"]
        if self.phase == "day":
            t = action.get("target") or None          # 0/None 视为弃票
            if t is not None and (t not in self.players or t not in self.alive):
                raise GameRuleError("非法投票目标")
            self.votes[uid] = t
            return [f"🗳️ {nk(uid)} 投票" + (f"：{nk(t)}" if t else "（弃票）")]
        raise GameRuleError("未知阶段")

    # ---- 推进状态机 ----
    def _advance(self):
        if self.phase == "done":
            return []
        if any(u not in self.acted for u in self.need):
            return []
        msgs = []
        if self.phase == "night_seer":
            self._reset_phase("night_wolf",
                              [u for u in self.players if self.role[u] == WEREWOLF and u in self.alive])
        elif self.phase == "night_wolf":
            wolf = [u for u in self.players if self.role[u] == WITCH and u in self.alive
                    and (self.witch_save_left or self.witch_poison_left)]
            self._reset_phase("night_witch", wolf)
        elif self.phase == "night_witch":
            msgs = self._resolve_night()
            if self.phase == "done":
                return msgs
            if self.shoot_pending:
                self._reset_phase("shoot", [self.hunter_uid])
                msgs.append(f"🏹 猎人 {self._nick(self.hunter_uid)} 死亡，可选择开枪带走一人")
            else:
                self._enter_day()
        elif self.phase == "shoot":
            self._enter_day()
        elif self.phase == "day":
            msgs = self._resolve_day()
            if self.phase == "done":
                return msgs
            if self.shoot_pending:
                self._reset_phase("shoot", [self.hunter_uid])
                msgs.append(f"🏹 猎人 {self._nick(self.hunter_uid)} 被放逐，可选择开枪带走一人")
            else:
                self._next_night()
        return msgs

    def _enter_day(self):
        self.votes = {}
        self.lynched = None
        self.shoot_pending = False
        self._reset_phase("day", sorted(self.alive))
        return ["☀️ 天亮了，进入白天讨论与投票"]

    def _next_night(self):
        self.night += 1
        self.wolf_kill = None
        self.witch_saved = False
        self.witch_saved_uid = None
        self.witch_poison = None
        self.seer_view = None
        self.votes = {}
        self.lynched = None
        self.shoot_pending = False
        self._reset_phase("night_seer",
                          [u for u in self.players if self.role[u] == SEER and u in self.alive])
        return [f"🌙 第 {self.night} 夜降临，预言家请行动"]

    def _reset_phase(self, phase, need):
        self.phase = phase
        self.acted = []
        self.need = list(need)

    def _maybe_end(self):
        w = self._winner()
        if w is not None:
            self.winner = w
            self.phase = "done"
            self.need = []
            return True
        return False

    def _winner(self):
        wc = sum(1 for u in self.alive if self.role[u] == WEREWOLF)
        gc = len(self.alive) - wc
        if wc == 0:
            return True
        if gc <= wc:
            return False
        return None

    def _resolve_night(self):
        msgs = []
        dead = set()
        if self.wolf_kill is not None:
            if self.witch_saved:
                self.witch_saved_uid = self.wolf_kill
                msgs.append(f"🧪 {self._nick(self.wolf_kill)} 被女巫解药救活")
            else:
                dead.add(self.wolf_kill)
        if self.witch_poison is not None:
            dead.add(self.witch_poison)
        for u in dead:
            msgs.append(f"💀 {self._nick(u)} 在夜晚死亡")
            self.alive.discard(u)
        if self._maybe_end():
            return msgs
        # 猎人死于夜晚（非毒杀）可开枪
        self.shoot_pending = (self.hunter_uid in dead
                              and not self.hunter_shot
                              and self.witch_poison != self.hunter_uid)
        return msgs

    def _resolve_day(self):
        cnt = {}
        for t in self.votes.values():
            if t is not None:
                cnt[t] = cnt.get(t, 0) + 1
        msgs = []
        if not cnt:
            msgs.append("🤚 无人投票，本日无人被放逐")
        else:
            mx = max(cnt.values())
            top = [u for u, c in cnt.items() if c == mx]
            if len(top) == 1:
                self.lynched = top[0]
                msgs.append(f"⚖️ {self._nick(top[0])} 以 {mx} 票被放逐")
                self.alive.discard(top[0])
            else:
                msgs.append(f"⚖️ 平票 {len(top)} 人，本日无人被放逐")
        if self._maybe_end():
            return msgs
        self.shoot_pending = self.lynched == self.hunter_uid and not self.hunter_shot
        return msgs

    def ended(self):
        if self.winner is None:
            return None
        return {"winner_uid": None,
                "detail": "🐺 狼人获胜" if self.winner is False else "🎉 好人获胜",
                "winner": self.winner}

    def player_left(self, uid):
        """夜/日任意阶段掉线：干净剔除并按剩余玩家推进状态机，避免永久等待缺失者"""
        if uid not in self.players:
            return []
        msgs = [f"{self._nick(uid)} 离开了游戏"]
        was_hunter = (self.hunter_uid == uid)
        self.players.remove(uid)
        self.role.pop(uid, None)
        self.alive.discard(uid)
        if was_hunter:
            self.hunter_uid = None
        self.acted = [u for u in self.acted if u != uid]
        if uid in self.need:
            self.need.remove(uid)
        self.votes.pop(uid, None)
        if self.lynched == uid:
            self.lynched = None
        if self.seer_view and self.seer_view.get("target") == uid:
            self.seer_view = None
        if self.wolf_kill == uid:
            self.wolf_kill = None
            self.witch_saved = False
            self.witch_saved_uid = None
        if self.witch_poison == uid:
            self.witch_poison = None
        if was_hunter:
            self.shoot_pending = False
        if self.winner is not None or self.phase == "done":
            return msgs
        self.need = [u for u in self.need if u in self.players and u in self.alive]
        if len(self.players) < 2:
            self.winner = False
            self.phase = "done"
            self.need = []
            msgs.append("剩余玩家不足，对局结束")
            return msgs
        if not self._maybe_end():
            self._advance()
        return msgs

    def _nick(self, uid):
        return f"玩家{uid}"