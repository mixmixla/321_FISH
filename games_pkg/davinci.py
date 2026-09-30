# -*- coding: utf-8 -*-
"""达芬奇密码（致敬 Da Vinci Code）：0~11 数字牌 ×4 色 + 2 张黑色“反间谍”（值记 -1，须按“黑”才猜中）。
每人按数字升序竖一排（暗），只露出一张。轮流：摸 1 张（选明/暗，并按值插到正确空位），随后可猜一位
对手手牌的数字——猜中则该牌翻开（永久公开），猜错则自己刚摸的牌翻开。某玩家所有牌均被翻开即出局；
最后存活者胜。摸牌时原位置重叠/空格用“倒扣占位”，简化：每人牌固定 3~4 张，摸到后按数字插入末尾空槽。"""
from games_pkg.base import BaseGame, GameRuleError

DIGITS = 12                       # 0..11


def _hands_count(n):
    return 4 if n == 2 else 3     # 2 人各 4 张，其余各 3 张


class DaVinCiGame(BaseGame):
    name = "davinci"
    min_players = 2
    max_players = 6

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        deck = [v for v in range(DIGITS) for _ in range(4)] + [-1, -1]
        self.rng.shuffle(deck)
        self.draw = deck
        self.hands = {}
        self.order_uid = 0
        self.turn = players[0]
        for u in players:
            n = _hands_count(len(players))
            tiles = [self.draw.pop() for _ in range(n)]
            tiles.sort(key=lambda v: (v, 0))
            # 把最大值那张翻开作为“明牌”，其余暗藏
            open_at = n - 1
            rows = [{"v": v, "open": (i == open_at), "pos": i, "removed": False} for i, v in enumerate(tiles)]
            self.hands[u] = rows
        self.dead = []
        self.discard = []
        self.last_action = None
        self.winner = None
        self.phase = "playing"

    # ---- 工具 ----
    def _row_uid(self, u):
        return [r for r in self.hands[u] if not r["open"]]

    @staticmethod
    def _label(v):
        return "黑" if v == -1 else str(v)

    def _locked(self):
        """所有已被翻开的牌（对手已知）"""
        return {u: [r for r in self.hands[u] if r["open"]] for u in self.hands}

    def _check_elim(self):
        """淘汰所有牌已全部翻开的玩家"""
        for u in list(self.hands):
            self.hands[u] = [r for r in self.hands[u] if not r.get("removed")]
            if len(self.hands[u]) == 0 or all(r["open"] for r in self.hands[u]):
                if u not in self.dead:
                    self.dead.append(u)
                del self.hands[u]
        alive = list(self.hands)
        if len(alive) == 1:
            self.winner = alive[0]
            self.phase = "ended"

    # ---- 动作 ----
    def act(self, uid, action):
        if self.winner:
            raise GameRuleError("本局已结束")
        if uid != self.turn:
            raise GameRuleError("还没轮到你")
        if uid not in self.hands:
            raise GameRuleError("你已出局")
        op = action.get("op")
        if op == "draw":
            return self._draw(uid, action)
        if op == "guess":
            return self._guess(uid, action)
        raise GameRuleError("未知操作")

    def _draw(self, uid, action):
        if not self.draw:
            raise GameRuleError("牌堆已空，无法摸牌")
        visible = action.get("open", True)
        v = self.draw.pop()
        row = self.hands[uid]
        newtile = {"v": v, "open": bool(visible), "pos": len(row), "removed": False}
        row.append(newtile)
        self._last_drawn_obj = newtile
        # 重新按值排序编位
        row.sort(key=lambda r: (r.get("removed"), r["v"]))
        for i, r in enumerate(row):
            r["pos"] = i
        self.last_action = ("draw", uid, v, visible)
        # 排序后再检查是否已实际上没移动——摸到的明牌保持 open
        msgs = [f"🃏 {self._nick(uid)} 摸了一张牌" + ("（明牌）" if visible else "（暗牌）")]
        if visible:
            msgs.append(f"🂠 {self._nick(uid)} 展示：{self._label(v)}")
        return msgs

    def _guess(self, uid, action):
        target = action.get("target")
        pos = action.get("pos")
        val = action.get("val")
        try:
            pos = int(pos)
        except (TypeError, ValueError):
            raise GameRuleError("位置无效")
        # 解析目标：val 若是 "black" -> -1
        if isinstance(val, str) and val.strip().lower() in ("black", "黑", "b"):
            val = -1
        else:
            try:
                val = int(val)
            except (TypeError, ValueError):
                raise GameRuleError("猜值无效")
        if target not in self.hands or target == uid:
            raise GameRuleError("猜牌对象无效")
        rows = [r for r in self.hands[target] if not r["removed"]]
        if pos < 0 or pos >= len(rows):
            raise GameRuleError("位置超出范围")
        r = rows[pos]
        hit = (r["v"] == val)
        drawn_open = None
        if hit:
            old = r["open"]
            r["open"] = True
            drawn_open = True
            msgs = [f"🎯 {self._nick(uid)} 猜中 {self._nick(target)} 第 {pos + 1} 位 = "
                    f"{self._label(r['v'])}（翻开）"]
            if not old:
                msgs.append(f"🂠 {self._nick(target)} 的 {self._label(r['v'])} 被翻开")
        else:
            # 猜错：自己最后摸的那张暗牌翻开
            last_drawn = getattr(self, "_last_drawn_obj", None)
            if last_drawn and last_drawn in [x for x in self.hands[uid] if not x["removed"]] \
                    and not last_drawn["open"]:
                last_drawn["open"] = True
                msgs = [f"❌ {self._nick(uid)} 猜 {self._nick(target)} 第 {pos + 1} 位 = {self._label(val)} 猜错了！",
                        f"🂠 自罚翻开自己刚摸的牌：{self._label(last_drawn['v'])}"]
            else:
                msgs = [f"❌ {self._nick(uid)} 猜 {self._nick(target)} 第 {pos + 1} 位 = {self._label(val)} 猜错了"]
            drawn_open = False
        self.last_action = ("guess", uid, target, pos)
        self._check_elim()
        if self.winner:
            msgs.append(f"🏆 {self._nick(self.winner)} 笑到最后，成为最后的达芬奇！")
        else:
            # 移交回合
            self.order_uid = (self.order_uid + 1) % len(self.players)
            self.turn = self.players[self.order_uid]
        return msgs

    def snapshot(self):
        def row_list(u):
            # 公开快照：只暴露已翻开的牌，暗牌一律隐藏其值
            return [{"v": r["v"] if r["open"] else None, "open": r["open"]}
                    for r in self.hands[u] if not r["removed"]]
        return {
            "game": self.name, "status": self.phase,
            "turn": self.turn, "hands": {str(u): row_list(u) for u in self.hands},
            "dead": self.dead, "draw_left": len(self.draw), "winner_uid": self.winner,
            "label": {str(v): self._label(v) for v in set([-1]) | set(range(DIGITS))},
        }

    def private(self, uid):
        if uid not in self.hands:
            return None
        # 自己知道自己所有牌（含暗牌）
        return {"row": [{"v": r["v"], "open": r["open"]}
                        for r in self.hands[uid] if not r["removed"]]}

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner,
                    "detail": f"{self._nick(self.winner)} 最后的达芬奇"}
        return None

    def player_left(self, uid):
        if uid in self.hands:
            del self.hands[uid]
        if uid == self.turn:
            self.order_uid = (self.order_uid + 1) % len(self.players)
            self.turn = self.players[self.order_uid]
        self._check_elim()
        return [f"💨 {self._nick(uid)} 离开了对局"]

    def _nick(self, uid):
        return f"玩家{uid}"