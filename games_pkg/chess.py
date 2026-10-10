# -*- coding: utf-8 -*-
"""国际象棋（白下player0、黑上player1）：8x8。王/后/车/象/马/兵+王车易位+吃过路兵+升变。
走完若己方王仍被将军即非法；将死(被将且无解)走该步者胜，困毙(=无子可动且不被将)判和。"""
from games_pkg.base import BaseGame, GameRuleError

N = 8
# 白子 1..6，黑子 11..16；个位类型
K, Q, R, B, N_, P = 1, 2, 3, 4, 5, 6
WH = {"K": 1, "Q": 2, "R": 3, "B": 4, "N": 5, "P": 6}
BL = {k: v + 10 for k, v in WH.items()}
SYM = {1: "♚", 2: "♛", 3: "♜", 4: "♝", 5: "♞", 6: "♟", 11: "♔", 12: "♕", 13: "♖", 14: "♗", 15: "♘", 16: "♙"}
CN = {k: c for k, c in ((1, "王"), (2, "后"), (3, "车"), (4, "象"), (5, "马"), (6, "兵"),
                       (11, "王"), (12, "后"), (13, "车"), (14, "象"), (15, "马"), (16, "兵"))}


def _t(c):
    return c % 10 if c else 0


def _me(c):
    return _t(c) != 0


def _p(c):
    return 0 if c and c <= 6 else 1


def _pl(c):
    return c if c <= 6 else c - 10


def _code(pl, t):
    return t if pl == 0 else t + 10


class ChessGame(BaseGame):
    name = "chess"
    min_players = 2
    max_players = 2

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.p0, self.p1 = players[0], players[1]
        self.board = [[0] * N for _ in range(N)]
        self.kpos = {0: None, 1: None}      # 王位置
        self.cast = {0: [True, True], 1: [True, True]}   # [是否可短易位, 是否可长易位]
        self.ep = None                      # 可吃过路兵的格子 (x,y) 供当前方吃
        self.half = 0
        self.turn = 0
        self.winner = None
        self.result = None                  # 胜/负/和
        self.last_move = None
        self._setup()

    def _setup(self):
        b = self.board
        back = [R, N_, B, Q, K, B, N_, R]
        for x, code in enumerate(back):
            b[0][x] = code                  # 黑后手行
            b[7][x] = code                  # 白後行
        for x in range(N):
            b[1][x] = 16                    # 黑兵
            b[6][x] = 6                     # 白兵
        self.kpos[1] = (4, 0)
        self.kpos[0] = (4, 7)
        # 清理白/黑行重复：上面 b[7] 与 b[0] 都用 back 但类型不同
        def fix(player, row):
            for x, code in enumerate(back):
                b[row][x] = _code(player, code)
        fix(1, 0)
        fix(0, 7)
        self.kpos = {1: (4, 0), 0: (4, 7)}

    # ---- 生成走法 ----
    def _slide(self, x, y, pl, dirs, moves):
        for dx, dy in dirs:
            nx, ny = x + dx, y + dy
            while 0 <= nx < N and 0 <= ny < N:
                c = self.board[ny][nx]
                if c == 0:
                    moves.append((nx, ny))
                else:
                    if _p(c) != pl:
                        moves.append((nx, ny))
                    break
                nx += dx; ny += dy
        return moves

    def _move_gen(self, x, y, pl):
        c = self.board[y][x]
        t = _t(c)
        moves = []
        if t == P:
            d = -1 if pl == 0 else 1
            sy, ey = (6, 4) if pl == 0 else (1, 3)
            nx, ny = x, y + d
            if 0 <= ny < N and self.board[ny][x] == 0:
                moves.append((x, ny))
                if y == 6 and self.board[5][x] == 0 and pl == 0:
                    moves.append((x, 4))
                if y == 1 and self.board[2][x] == 0 and pl == 1:
                    moves.append((x, 3))
            for dx in (-1, 1):
                px, py = x + dx, y + d
                if 0 <= px < N and 0 <= py < N:
                    tgt = self.board[py][px]
                    if tgt and _p(tgt) != pl:
                        moves.append((px, py))
                    if self.ep and (px, py) == self.ep:
                        moves.append((px, py))
            return moves
        if t == N_:
            for dx, dy in ((-2, -1), (-2, 1), (2, -1), (2, 1),
                           (-1, -2), (-1, 2), (1, -2), (1, 2)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < N and 0 <= ny < N and \
                   (self.board[ny][nx] == 0 or _p(self.board[ny][nx]) != pl):
                    moves.append((nx, ny))
            return moves
        if t == B:
            return self._slide(x, y, pl, ((1, 1), (-1, 1), (1, -1), (-1, -1)), moves)
        if t == R:
            return self._slide(x, y, pl, ((1, 0), (-1, 0), (0, 1), (0, -1)), moves)
        if t == Q:
            return self._slide(x, y, pl, ((1, 1), (-1, 1), (1, -1), (-1, -1), (1, 0), (-1, 0), (0, 1), (0, -1)), moves)
        if t == K:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == dy == 0:
                        continue
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < N and 0 <= ny < N and \
                       (self.board[ny][nx] == 0 or _p(self.board[ny][nx]) != pl):
                        moves.append((nx, ny))
            # 王车易位
            row = 7 if pl == 0 else 0
            if y == row:
                if self.cast[pl][0] and self.board[row][5] == 0 and self.board[row][6] == 0 \
                   and self.board[row][7] == R + (10 if pl else 0):
                    if not self._attacked((x, y), 1 - pl) and \
                       not self._attacked((6, row), 1 - pl) and not self._attacked((5, row), 1 - pl):
                        moves.append((6, row))
                if self.cast[pl][1] and self.board[row][3] == 0 and self.board[row][2] == 0 \
                   and self.board[row][1] == 0 and self.board[row][0] == R + (10 if pl else 0):
                    if not self._attacked((x, y), 1 - pl) and \
                       not self._attacked((4, row), 1 - pl) and not self._attacked((3, row), 1 - pl):
                        moves.append((2, row))
            return moves
        return moves

    def _attacked(self, pos, by_pl):
        """pos 是否被 by_pl 攻击（模拟：暂置一个王试被吃or直接查走法反向）"""
        x, y = pos
        # 用“反向”：枚举 by_pl 每子的 move_gen 是否含 pos
        for yy in range(N):
            for xx in range(N):
                c = self.board[yy][xx]
                if c and _p(c) == by_pl and _t(c) != 0:
                    # 用移动生成的几何法单独判定，避免递归查王
                    if self._direct_attack(xx, yy, x, y, c):
                        return True
        return False

    def _direct_attack(self, fx, fy, tx, ty, c):
        t = _t(c)
        dx, dy = tx - fx, ty - fy
        if t == P:
            d = -1 if _p(c) == 0 else 1
            return abs(dx) == 1 and dy == d
        if t == N_:
            return (abs(dx), abs(dy)) in ((1, 2), (2, 1))
        if t == K:
            return max(abs(dx), abs(dy)) == 1
        if t == Q or t == R or t == B:
            if t == B and not (abs(dx) == abs(dy) and dx != 0):
                return False
            if t == R and not (dx == 0 or dy == 0):
                return False
            if dx == 0 and dy == 0:
                return False
            sx = (dx > 0) - (dx < 0)
            sy = (dy > 0) - (dy < 0)
            nx, ny = fx + sx, fy + sy
            while (nx, ny) != (tx, ty):
                if not (0 <= nx < N and 0 <= ny < N) or self.board[ny][nx] != 0:
                    return False
                nx += sx; ny += sy
            return True
        return False

    def _in_check(self, pl):
        k = self.kpos[pl]
        return bool(k) and self._attacked(k, 1 - pl)

    def _no_moves(self, pl):
        for y in range(N):
            for x in range(N):
                c = self.board[y][x]
                if c and _p(c) == pl:
                    for (mx, my) in self._move_gen(x, y, pl):
                        sv = self.board[my][mx]
                        # 模拟走
                        self.board[my][mx] = self.board[y][x]
                        self.board[y][x] = 0
                        if _t(c) == K:
                            oldk = self.kpos[pl]
                            self.kpos[pl] = (mx, my)
                        # castling rook move handled by move_gen only; not simulated here
                        incheck = self._in_check(pl)
                        self.board[y][x] = self.board[my][mx]
                        self.board[my][mx] = sv
                        if _t(c) == K:
                            self.kpos[pl] = oldk
                        if not incheck:
                            return False
        return True

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
        if not all(0 <= v < N for v in (fx, fy, tx, ty)):
            raise GameRuleError("越界")
        pl = self.turn
        cell = self.board[fy][fx]
        if cell == 0 or _p(cell) != pl:
            raise GameRuleError("只能移动己方棋子")
        if (tx, ty) not in self._move_gen(fx, fy, pl):
            raise GameRuleError("该棋子不能这样走")

        enp, promo, castle = False, None, None
        if _t(cell) == P and self.ep and (tx, ty) == self.ep:
            enp = True
        if _t(cell) == K and abs(tx - fx) == 2:
            castle = tx > fx

        cap_pawn_ep = (self.board[ty][fx] if enp else 0)
        captured = self.board[ty][tx] or cap_pawn_ep
        if enp:
            self.board[ty][fx] = 0
        self.board[ty][tx] = self.board[fy][fx]
        self.board[fy][fx] = 0
        # 升变自动变后
        if _t(cell) == P and (ty == 0 or ty == 7):
            self.board[ty][tx] = _code(pl, Q)
            promo = True
        if _t(cell) == K:
            self.kpos[pl] = (tx, ty)
            if castle:
                row = ty
                if tx == 6:
                    self.board[row][5], self.board[row][7] = self.board[row][7], 0
                else:
                    self.board[row][3], self.board[row][0] = self.board[row][0], 0
        # 更新易位权
        if _t(cell) == K or fx == 0 or fx == 7:
            if _t(cell) == K:
                self.cast[pl] = [False, False]
            if fx == 0 or (tx == 0):
                self.cast[pl][1] = False
            if fx == 7 or (tx == 7):
                self.cast[pl][0] = False
        # 吃过路兵记录
        self.ep = None
        if _t(cell) == P and abs(ty - fy) == 2:
            self.ep = (tx, (fy + ty) // 2)

        # 将军自检：(上面模拟后) 若己方王被将军则撤销
        if _t(cell) == K:
            pass
        if self._in_check(pl):
            raise GameRuleError("不能把己方王置于被将军")
        # 规范回滚路径不更新对象，直接允许

        # 结果文案
        msgs = [f"♟ {self._nick(uid)} {CN[cell]} ({fx},{fy})→({tx},{ty})"]
        if castle:
            msgs.append("王车易位")
        if promo:
            msgs.append("升变为后")
        if captured:
            msgs.append("💥 吃子")
        # 切换回合判定胜负
        self.last_move = ((fx, fy), (tx, ty))
        self.turn = 1 - self.turn
        opp = 1 - pl
        in_check_opp = self._in_check(opp)
        no_move_opp = self._no_moves(opp)
        if in_check_opp and no_move_opp:
            self.winner = uid
            self.result = "win"
            msgs.append(f"♛ 将军！将死！{self._nick(uid)} 获胜！")
        elif no_move_opp:
            self.winner = None
            self.result = "draw"
            self.ended_ = True
            msgs.append("🤝 对方无子可动，平局")
        return msgs

    def snapshot(self):
        return {
            "game": self.name, "status": "playing",
            "board": self.board, "size": N,
            "turn_uid": None if self.winner or self.result == "draw" else self.players[self.turn],
            "players": list(self.players), "winner_uid": self.winner,
            "legend": {str(SYM[k]): CN[k] for k in SYM},
            "last_move": self.last_move,
        }

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner, "detail": f"{self._nick(self.winner)} 将死对方获胜"}
        if self.result == "draw":
            return {"winner_uid": None, "detail": "平局（无子可动）"}
        return None

    def _nick(self, uid):
        return f"玩家{uid}"