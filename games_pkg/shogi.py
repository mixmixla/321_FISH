# -*- coding: utf-8 -*-
"""将棋：9x9。棋子：王/飞车/角行/金/银/桂/香/兵；被吃子可“打入”任一空位。
棋盘深入对方后三排即“成金/成龙/成马”升变(王、金不升)。吃掉对方王即获胜。"""
from games_pkg.base import BaseGame, GameRuleError

N = 9
# 黑(player0下) 1..，白(player1上) 11..
K, R, B, G, S, N_, L, P = 1, 2, 3, 4, 5, 6, 7, 8
PROM_R, PROM_B = 9, 10          # 龙(成飞)、马(成角)
CN = {1: "王", 2: "飞车", 3: "角行", 4: "金", 5: "银", 6: "桂", 7: "香", 8: "兵",
      9: "龙", 10: "马"}
SYM = {1: "玉", 2: "飛", 3: "角", 4: "金", 5: "銀", 6: "桂", 7: "香", 8: "歩", 9: "龍", 10: "馬"}


def _t(c):
    return c % 10 if c else 0


def _p(c):
    return 0 if c and c <= 10 else 1


def _code(pl, t):
    return t if pl == 0 else t + 10


def _d(pl):            # 向前方向：黑-1(向上)，白+1
    return -1 if pl == 0 else 1


class ShogiGame(BaseGame):
    name = "shogi"
    min_players = 2
    max_players = 2

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.p0, self.p1 = players[0], players[1]
        self.board = [[0] * N for _ in range(N)]
        self.hand = {0: [], 1: []}      # 被吃子
        self.captured = {0: [], 1: []}
        self.turn = 0
        self.winner = None
        self.kpos = {0: None, 1: None}
        self._setup()

    def _setup(self):
        b = self.board
        back = [L, N_, S, G, K, G, S, N_, L]
        for x, t in enumerate(back):
            b[8][x] = _code(0, t)      # 黑后列
            b[0][x] = _code(1, t)
        b[7][1] = _code(0, B)          # 角
        b[7][7] = _code(0, R)          # 飞
        b[1][7] = _code(1, R)
        b[1][1] = _code(1, B)
        for x in (0, 2, 4, 6, 8):
            b[6][x] = _code(0, P)
            b[2][x] = _code(1, P)
        self.kpos[0] = (4, 8)
        self.kpos[1] = (4, 0)

    def _walk(self, x, y, pl, steps, out):
        for step in steps:
            nx, ny = x + step[0], y + step[1]
            while 0 <= nx < N and 0 <= ny < N:
                c = self.board[ny][nx]
                if c == 0:
                    out.append((nx, ny))
                else:
                    if _p(c) != pl:
                        out.append((nx, ny))
                    break
                nx += step[0]; ny += step[1]
        return out

    def _move_gen(self, x, y, pl):
        c = self.board[y][x]
        m = _t(c)
        d = _d(pl)
        out = []
        fwd = d
        if m == K:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == dy == 0:
                        continue
                    self._add(x + dx, y + dy, pl, out)
        elif m == R:
            self._walk(x, y, pl, ((1, 0), (-1, 0), (0, 1), (0, -1)), out)
        elif m == B:
            self._walk(x, y, pl, ((1, 1), (-1, 1), (1, -1), (-1, -1)), out)
        elif m == G:
            self._add(x, y + fwd, pl, out); self._add(x, y - fwd, pl, out)
            self._add(x - 1, y, pl, out); self._add(x + 1, y, pl, out)
            self._add(x - 1, y + fwd, pl, out); self._add(x + 1, y + fwd, pl, out)
        elif m == S:
            self._add(x, y + fwd, pl, out)
            for dx in (-1, 1):
                self._add(x + dx, y + fwd, pl, out)
                self._add(x + dx, y - fwd, pl, out)
        elif m == N_:
            for dx in (-1, 1):
                self._add(x + dx, y + 2 * fwd, pl, out)
        elif m == L:
            self._walk(x, y, pl, ((0, fwd),), out)
        elif m == P:
            self._add(x, y + fwd, pl, out)
        elif m == PROM_R:      # 龙=车+斜一步
            self._walk(x, y, pl, ((1, 0), (-1, 0), (0, 1), (0, -1)), out)
            for dx in (-1, 1):
                for dy in (-1, 1):
                    self._add(x + dx, y + dy, pl, out)
        elif m == PROM_B:      # 马=角+横竖一步
            self._walk(x, y, pl, ((1, 1), (-1, 1), (1, -1), (-1, -1)), out)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if abs(dx) + abs(dy) != 1:
                        continue
                    self._add(x + dx, y + dy, pl, out)
        return out

    def _add(self, x, y, pl, out):
        if 0 <= x < N and 0 <= y < N:
            c = self.board[y][x]
            if c == 0 or _p(c) != pl:
                out.append((x, y))

    def _drop_gen(self, pl, t):
        d = _d(pl)
        out = []
        for yy in range(N):
            for xx in range(N):
                if self.board[yy][xx] != 0:
                    continue
                # 香/桂/兵不能落在最后一行(成不了且立即死)
                if t in (L, N_, P):
                    last = N - 1 if pl == 0 else 0
                    if yy == last:
                        continue
                # 步兵二步：同列已有己方步兵则不能打
                if t == P:
                    if any(self.board[y][xx] == _code(pl, P) for y in range(N)):
                        continue
                out.append((xx, yy))
        return out

    def act(self, uid, action):
        if self.winner:
            raise GameRuleError("本局已结束")
        if uid != self.players[self.turn]:
            raise GameRuleError("还没轮到你")
        pl = self.turn
        op = action.get("op")
        if op == "drop":            # 打入
            t = int(action.get("t"))
            if not self.owns_taken(pl, t):
                raise GameRuleError("手上没有该子")
            x, y = int(action.get("x")), int(action.get("y"))
            if not (0 <= x < N and 0 <= y < N):
                raise GameRuleError("越界")
            if self.board[y][x] != 0:
                raise GameRuleError("该位已有子")
            if (x, y) not in self._drop_gen(pl, t):
                raise GameRuleError("不能落在该处")
            self.board[y][x] = _code(pl, t)
            self.hand[pl].remove(t)
            self.turn = 1 - pl
            return [f"🪁 {self._nick(uid)} 打入 {CN[t]}({x},{y})"]
        # 普通走子
        try:
            fx = int(action.get("fx")); fy = int(action.get("fy"))
            tx = int(action.get("tx")); ty = int(action.get("ty"))
        except (TypeError, ValueError):
            raise GameRuleError("坐标必须为整数")
        if not all(0 <= v < N for v in (fx, fy, tx, ty)):
            raise GameRuleError("越界")
        c = self.board[fy][fx]
        if c == 0 or _p(c) != pl:
            raise GameRuleError("只能移动己方棋子")
        if (tx, ty) not in self._move_gen(fx, fy, pl):
            raise GameRuleError("该棋子不能这样走")
        taken = self.board[ty][tx]
        self.board[ty][tx] = c
        self.board[fy][fx] = 0
        if _t(c) == K:
            self.kpos[pl] = (tx, ty)
        msgs = [f"♟ {self._nick(uid)} {CN[_t(c)]} ({fx},{fy})→({tx},{ty})"]
        if taken:
            tt = _t(taken)
            if tt in (K,):
                self.winner = uid
                msgs.append(f"🏆 {self._nick(uid)} 吃掉对方王获胜！")
                return msgs
            # 升变后的子吃回时以原子归手
            base = {PROM_R: R, PROM_B: B}.get(tt, tt)
            self.hand[pl].append(base)
            self.captured[pl].append(base)
            msgs.append(f"💥 吃掉 {CN[tt]}({CN[base]})")
        # 升变：进入对方后三排(黑进0-2，白进6-8)
        prox = (fy <= 2) if pl == 0 else (fy >= 6)
        nprom = (ty <= 2) if pl == 0 else (ty >= 6)
        if nprom and _t(c) in (R, B, S, N_, L, P):
            nt = {R: PROM_R, B: PROM_B}.get(_t(c), G)
            if _t(c) in (P,):       # 兵成金
                nt = G
            if _t(c) in (S, N_, L):
                nt = G
            self.board[ty][tx] = _code(pl, nt)
            msgs.append(f"🎖 升变为 {CN[nt]}")
        self.turn = 1 - pl
        return msgs

    def owns_taken(self, pl, t):
        return t in self.hand[pl]

    def snapshot(self):
        return {
            "game": self.name, "status": "playing",
            "board": self.board, "size": N,
            "turn_uid": None if self.winner else self.players[self.turn],
            "players": list(self.players), "winner_uid": self.winner,
            "hand": {str(k): v for k, v in self.hand.items()},
            "legend": {str(SYM[t]): CN[t] for t in SYM},
        }

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner, "detail": f"{self._nick(self.winner)} 吃掉对方王获胜"}
        return None

    def _nick(self, uid):
        return f"玩家{uid}"