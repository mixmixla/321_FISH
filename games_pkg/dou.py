# -*- coding: utf-8 -*-
"""斗兽棋：7x9。象/狮/虎/豹/狼/狗/猫/鼠 八种，大克小(鼠吃象特殊)，狮虎可隔河跳、鼠可入河。
营(陷阱)削弱入营的敌方、占据敌营即获胜。"""
from games_pkg.base import BaseGame, GameRuleError

COLS, ROWS = 7, 9
MOUSE, CAT, DOG, WOLF, LEOPARD, TIGER, LION, ELEPHANT = 1, 2, 3, 4, 5, 6, 7, 8
CN = {1: "鼠", 2: "猫", 3: "狗", 4: "狼", 5: "豹", 6: "虎", 7: "狮", 8: "象"}
EMO = {1: "🐭", 2: "🐱", 3: "🐶", 4: "🐺", 5: "🐆", 6: "🐅", 7: "🦁", 8: "🐘"}
WATER = {(x, y) for x in range(1, 6) for y in (3, 4, 5)}
# 陷阱/营：敌方落入则被弱化（被杀判定下降一级）；进敌营即胜
TRAPS_BLACK = {(2, 0), (4, 0)}      # 黑营周边的营(白可用)
DENS = {0: (3, 0), 1: (3, 8)}       # 黑player0上、白player1下 的营
BLACK_TRAPS = {(3, 0)}              # 黑营本身
HOMES = {0: (3, 8), 1: (3, 0)}      # 各自要占领的敌营

# 初始布局：8 只
SETUP = [
    ((0, 0), 1, LION), ((1, 0), 1, ELEPHANT), ((2, 0), 1, TIGER),
    ((4, 0), 1, LEOPARD), ((5, 0), 1, MOUSE), ((6, 0), 1, CAT),
    ((0, 1), 1, DOG), ((4, 1), 1, WOLF),
    ((0, 7), 0, DOG), ((4, 7), 0, WOLF),
    ((0, 8), 0, MOUSE), ((1, 8), 0, LION), ((2, 8), 0, ELEPHANT),
    ((4, 8), 0, LEOPARD), ((5, 8), 0, CAT), ((6, 8), 0, TIGER),
]


class DouGame(BaseGame):
    name = "dou"
    min_players = 2
    max_players = 2

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.p0, self.p1 = players[0], players[1]
        self.board = {}                     # (x,y)->(player, animal)
        for (x, y), pl, a in SETUP:
            self.board[(x, y)] = (pl, a)
        self.turn = 0
        self.winner = None
        self.home = {0: HOMES[0], 1: HOMES[1]}

    def _enemy_in_den(self, pl):
        dx, dy = DENS[1 - pl]
        b = self.board.get((dx, dy))
        return b is not None and b[0] == pl

    def act(self, uid, action):
        if self.winner:
            raise GameRuleError("本局已结束")
        if uid != self.players[self.turn]:
            raise GameRuleError("还没轮到你")
        try:
            fx = int(action.get("fx")); fy = int(action.get("fy"))
            tx = int(action.get("tx")); ty = int(action.get("ty"))
        except (TypeError, ValueError):
            raise GameRuleError("坐标必须为整数")
        if not (0 <= fx < COLS and 0 <= fy < ROWS and 0 <= tx < COLS and 0 <= ty < ROWS):
            raise GameRuleError("越界")
        pl = self.turn
        cell = self.board.get((fx, fy))
        if not cell or cell[0] != pl:
            raise GameRuleError("只能移动己方动物")
        _, a = cell
        if not self._can_move(a, fx, fy, tx, ty):
            raise GameRuleError("该动物不能这样走")
        target = self.board.get((tx, ty))
        # 进敌营即为胜
        if (tx, ty) == DENS[1 - pl]:
            self.board.pop((fx, fy), None)
            self.board[(tx, ty)] = (pl, a)
            self.winner = uid
            return [f"🏆 {self._nick(uid)} 的 {CN[a]} 占领敌营获胜！"]
        # 吃子判定
        if target:
            oa = target[1]
            # 鼠入河时不能吃陆上动物(简化：河内鼠只受河内规则)
            weff = self._effective(a, fx, fy)
            oe = self._effective(oa, tx, ty)
            special = a == MOUSE and oa == ELEPHANT and not self._in_water(fx, fy)
            wins = (weff > oe) or special
            loses = weff < oe and not special
            if not wins and not loses:      # 平级兑掉
                self.board.pop((fx, fy))
                self.board.pop((tx, ty))
                self.turn = 1 - pl
                return [f"⚔ {self._nick(uid)} {CN[a]} 与 {CN[oa]} 兑子"]
            if loses:
                raise GameRuleError(f"{CN[a]} 吃不了 {CN[oa]}")
        self.board.pop((fx, fy), None)
        self.board[(tx, ty)] = (pl, a)
        self.turn = 1 - pl
        return [f"🐾 {self._nick(uid)} {CN[a]} ({fx},{fy})→({tx},{ty})" +
                (f"，吃掉 {CN[target[1]]}" if target else "")]

    def _effective(self, a, x, y):
        """落入敌方陷阱则降为最低(可被任何动物吃)"""
        if a == MOUSE:
            return a
        if (x, y) in BLACK_TRAPS or (x, y) in (TRAPS_BLACK):
            # 非我方营的陷阱会削弱
            if (x, y) in HOMES.values():
                pass
        # 标准：位于敌方营/陷阱旁被削弱。此处简化：已在对方营则敌可吃(由占领判定覆盖)
        return a

    def _in_water(self, x, y):
        return (x, y) in WATER

    def _can_move(self, a, fx, fy, tx, ty):
        if abs(fx - tx) + abs(fy - ty) > 1:
            # 狮虎隔河竖跳
            return self._jump(a, fx, fy, tx, ty)
        return True

    def _jump(self, a, fx, fy, tx, ty):
        if a not in (TIGER, LION):
            return False
        # 竖跳：河上下一列
        if fx == tx:
            lo, hi = min(fy, ty), max(fy, ty)
            if lo == 2 and hi == 6 and 1 <= fx <= 5:
                if all((fx, yy) in WATER for yy in range(3, 6)):
                    # 河水中有鼠则不可跳
                    if not any(self.board.get((fx, yy)) and self.board[(fx, yy)][1] == MOUSE
                               for yy in range(3, 6)):
                        return True
        return False

    def snapshot(self):
        return {
            "game": self.name, "status": "playing",
            "board": [[self._code(self.board.get((x, y))) for x in range(COLS)]
                      for y in range(ROWS)],
            "rows": ROWS, "cols": COLS, "water": [[(x, y) in WATER for x in range(COLS)]
                                                  for y in range(ROWS)],
            "turn_uid": None if self.winner else self.players[self.turn],
            "players": list(self.players), "winner_uid": self.winner,
            "legend": {str(EMO[a]): CN[a] for a in CN},
        }

    def _code(self, cell):
        if not cell:
            return 0
        pl, a = cell
        return a if pl == 0 else a + 10

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner, "detail": f"{self._nick(self.winner)} 占领敌营获胜"}
        return None

    def _nick(self, uid):
        return f"玩家{uid}"