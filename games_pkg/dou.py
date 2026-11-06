# -*- coding: utf-8 -*-
"""斗兽棋：7×9，双河、三陷阱、营地；兽娘图像不改变动物身份与等级。
狮虎横纵跳河，鼠可游泳；同级可吃，鼠吃象、象不能吃鼠。"""
from games_pkg.base import BaseGame, GameRuleError

COLS, ROWS = 7, 9
MOUSE, CAT, DOG, WOLF, LEOPARD, TIGER, LION, ELEPHANT = 1, 2, 3, 4, 5, 6, 7, 8
CN = {1: "鼠", 2: "猫", 3: "狗", 4: "狼", 5: "豹", 6: "虎", 7: "狮", 8: "象"}
EMO = {1: "🐭", 2: "🐱", 3: "🐶", 4: "🐺", 5: "🐆", 6: "🐅", 7: "🦁", 8: "🐘"}
WATER = {(x, y) for x in (1, 2, 4, 5) for y in (3, 4, 5)}
DENS = {0: (3, 0), 1: (3, 8)}
TRAPS = {0: {(2, 0), (4, 0), (3, 1)}, 1: {(2, 8), (4, 8), (3, 7)}}
HOMES = {0: DENS[1], 1: DENS[0]}
# 两方围绕自己的营地按 180 度旋转对称布阵，0=红上、1=蓝下。
_TOP = [((0, 0), LION), ((6, 0), TIGER), ((1, 1), DOG), ((5, 1), CAT),
        ((0, 2), MOUSE), ((2, 2), LEOPARD), ((4, 2), WOLF), ((6, 2), ELEPHANT)]
SETUP = [(pos, 0, a) for pos, a in _TOP] + [((6-x, 8-y), 1, a) for (x, y), a in _TOP]


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
        self.last_move = None
        self.last_event = None          # 最近一步结果反馈 {kind,x,y}，供 UI 提示

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
        if (fx, fy) == (tx, ty):
            raise GameRuleError("请选择另一个目标格")
        if (tx, ty) == DENS[pl]:
            raise GameRuleError("不能进入自己的营地")
        target = self.board.get((tx, ty))
        if target and target[0] == pl:
            raise GameRuleError("不能吃己方动物")
        if not self._can_move(a, fx, fy, tx, ty):
            raise GameRuleError("该动物不能这样走")
        target = self.board.get((tx, ty))
        # 进敌营即为胜
        if (tx, ty) == DENS[1 - pl]:
            self.board.pop((fx, fy), None)
            self.board[(tx, ty)] = (pl, a)
            self.last_move = ((fx, fy), (tx, ty))
            self.last_event = {"kind": "win", "x": tx, "y": ty}
            self.winner = uid
            return [f"🏆 {self._nick(uid)} 的 {CN[a]} 占领敌营获胜！"]
        if target and not self._can_capture(pl, a, fx, fy, tx, ty, target[1]):
            raise GameRuleError(f"{CN[a]} 吃不了该位置的 {CN[target[1]]}")
        self.board.pop((fx, fy), None)
        self.board[(tx, ty)] = (pl, a)
        self.last_move = ((fx, fy), (tx, ty))
        self.last_event = {"kind": "eat" if target else "move", "x": tx, "y": ty}
        self.turn = 1 - pl
        return [f"🐾 {self._nick(uid)} {CN[a]} ({fx},{fy})→({tx},{ty})" +
                (f"，吃掉 {CN[target[1]]}" if target else "")]

    def legal_moves(self, uid):
        """己方动物的全部可接受走法：入水/跳河/吃子规则与 act 保持一致。"""
        if self.winner or uid != self.players[self.turn]:
            return []
        pl = self.turn
        out = []
        for (fx, fy), (owner, a) in sorted(self.board.items()):
            if owner != pl:
                continue
            for tx in range(COLS):
                for ty in range(ROWS):
                    if (tx, ty) == (fx, fy):
                        continue
                    if (tx, ty) == DENS[pl]:
                        continue
                    if not self._can_move(a, fx, fy, tx, ty):
                        continue
                    target = self.board.get((tx, ty))
                    if target:
                        if target[0] == pl:
                            continue
                        if not self._can_capture(pl, a, fx, fy, tx, ty, target[1]):
                            continue
                    out.append({"from": [fx, fy], "to": [tx, ty]})
        return out

    def _in_water(self, x, y):
        return (x, y) in WATER

    def _can_move(self, a, fx, fy, tx, ty):
        if (tx, ty) in WATER and a != MOUSE:      # 只有鼠能入水
            return False
        if abs(fx - tx) + abs(fy - ty) > 1:
            # 狮虎隔河横/纵跳
            return self._jump(a, fx, fy, tx, ty)
        return True

    def _can_capture(self, pl, a, fx, fy, tx, ty, defender):
        if self._in_water(fx, fy) != self._in_water(tx, ty):
            return False
        # Rank is tested at the source: stepping OUT restores rank on the next move.
        if (fx, fy) in TRAPS[1 - pl]:
            return False
        if (tx, ty) in TRAPS[pl]:
            return True
        if a == ELEPHANT and defender == MOUSE:
            return False
        if a == MOUSE and defender == ELEPHANT:
            return True
        return a >= defender

    def _jump(self, a, fx, fy, tx, ty):
        if a not in (TIGER, LION) or self._in_water(fx, fy):
            return False
        if fx != tx and fy != ty:
            return False
        dx, dy = (tx > fx) - (tx < fx), (ty > fy) - (ty < fy)
        if not (dx or dy):
            return False
        x, y = fx + dx, fy + dy
        crossed = False
        while (x, y) in WATER:
            crossed = True
            if (x, y) in self.board:
                return False
            x, y = x + dx, y + dy
        return crossed and (x, y) == (tx, ty)

    def snapshot(self):
        return {
            "game": self.name, "status": "playing",
            "board": [[self._code(self.board.get((x, y))) for x in range(COLS)]
                      for y in range(ROWS)],
            "rows": ROWS, "cols": COLS, "water": [[(x, y) in WATER for x in range(COLS)]
                                                  for y in range(ROWS)],
            "turn_uid": None if self.winner else self.players[self.turn],
            "players": list(self.players), "winner_uid": self.winner,
            "dens": {str(pl): list(pos) for pl, pos in DENS.items()},
            "traps": {str(pl): [list(pos) for pos in sorted(squares)]
                      for pl, squares in TRAPS.items()},
            "rules_variant": "双河 / 狮虎横纵跳河 / 同级可吃 / 敌陷阱等级归零",
            "legend": {str(EMO[a]): CN[a] for a in CN},
            "last_move": self.last_move,
            "last_event": self.last_event,
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
