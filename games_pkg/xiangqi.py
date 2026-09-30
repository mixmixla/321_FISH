# -*- coding: utf-8 -*-
"""中国象棋（红黑）：9x10，将/士/象/马/车/炮/兵。红方在下(player0)，黑方在上(player1)。
走法遵守各自规则（蹩马腿、塞象眼、炮隔山打、兵过河横走、将帅不出九宫），
任何走法结束自身将帅不得被将军；将死(被将且无解)或困毙(无子可动)判负。"""
from games_pkg.base import BaseGame, GameRuleError

COLS, ROWS = 9, 10          # x:0-8, y:0-9

# 棋子编码：<=10 红(player0)，>10 黑(player1)；个位为棋子类型
KING, ADVISOR, ELEPHANT, HORSE, ROOK, CANNON, PAWN = 1, 2, 3, 4, 5, 6, 7
RED_BASE, BLK_BASE = 0, 10


def _p(code):
    return 0 if code and code <= 10 else 1


def _t(code):
    return (code % 10) if code else 0


PIECE_CN = {1: "帅", 2: "仕", 3: "相", 4: "马", 5: "车", 6: "炮", 7: "兵",
            11: "将", 12: "士", 13: "象", 14: "马", 15: "车", 16: "炮", 17: "卒"}


def _in_palace(player, x, y):
    if player == 0:      # 红：y7-9
        return 3 <= x <= 5 and 7 <= y <= 9
    return 3 <= x <= 5 and 0 <= y <= 2


_CN_RED = "将士卒象马炮车"


class XiangQiGame(BaseGame):
    name = "xiangqi"
    min_players = 2
    max_players = 2

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.p0, self.p1 = players[0], players[1]
        self.board = [[0] * COLS for _ in range(ROWS)]
        self.turn = 0
        self.winner = None
        self._setup()

    def _setup(self):
        b = self.board
        rrow = [5, 4, 3, 2, 1, 2, 3, 4, 5]     # 车马相仕帅仕相马车
        for x, code in enumerate(rrow):
            b[9][x] = code
            b[0][x] = code + 10
        b[7][1], b[7][7] = 6, 6               # 红炮
        b[2][1], b[2][7] = 16, 16             # 黑炮
        for x in (0, 2, 4, 6, 8):
            b[6][x] = 7                        # 红兵
            b[3][x] = 17                       # 黑卒

    # ---- 基础 ----
    def _own(self, code):
        return bool(code) and _p(code) == self.turn

    def _move_gen(self, x, y, code):
        """返回该棋子的合法落点集合(仅走眼，不判王在check)"""
        t = _t(code)
        moves = set()
        def inside(nx, ny):
            return 0 <= nx < COLS and 0 <= ny < ROWS
        def get(nx, ny):
            return self.board[ny][nx] if inside(nx, ny) else -1   # -1 越界哨兵
        def add(nx, ny):
            if inside(nx, ny):
                d = get(nx, ny)
                if d == 0 or _p(d) != self.turn:
                    moves.add((nx, ny))
        if t == KING:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if inside(nx, ny) and _in_palace(self.turn, nx, ny) and \
                   (get(nx, ny) == 0 or _p(get(nx, ny)) != self.turn):
                    moves.add((nx, ny))
            # 飞将：将帅对脸，中间无子可直线吃掉对方将
            pass
        elif t == ADVISOR:
            for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
                nx, ny = x + dx, y + dy
                if _in_palace(self.turn, nx, ny) and \
                   (self.board[ny][nx] == 0 or _p(self.board[ny][nx]) != self.turn):
                    moves.add((nx, ny))
        elif t == ELEPHANT:
            for dx, dy in ((2, 2), (-2, 2), (2, -2), (-2, -2)):
                ey, ex = y + dy // 2, x + dx // 2
                if not inside(ex, ey) or get(ex, ey) != 0:      # 塞象眼
                    continue
                nx, ny = x + dx, y + dy
                if inside(nx, ny):
                    stay_red = self.turn == 0 and ny >= 5
                    stay_blk = self.turn == 1 and ny <= 4
                    if (stay_red or stay_blk) and (get(nx, ny) == 0 or _p(get(nx, ny)) != self.turn):
                        moves.add((nx, ny))
        elif t == HORSE:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):   # 蹩马腿的基点
                lbx, lby = x + dx, y + dy                        # 马腿位置
                if not inside(lbx, lby) or get(lbx, lby) != 0:
                    continue
                if dx != 0:    # 横向长边，两个落脚点
                    add(lbx + dx, y - 1); add(lbx + dx, y + 1)
                else:          # 纵向长边
                    add(x - 1, lby + dy); add(x + 1, lby + dy)
        elif t == ROOK:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):   # 车：直线行
                nx, ny = x + dx, y + dy
                while 0 <= nx < COLS and 0 <= ny < ROWS:
                    if self.board[ny][nx] == 0:
                        moves.add((nx, ny))
                    else:
                        if _p(self.board[ny][nx]) != self.turn:
                            moves.add((nx, ny))
                        break
                    nx += dx; ny += dy
        elif t == CANNON:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                while 0 <= nx < COLS and 0 <= ny < ROWS:
                    if self.board[ny][nx] == 0:
                        moves.add((nx, ny))           # 平移（不含吃）
                        nx += dx; ny += dy
                    else:                              # 隔山打：跳过第一个子吃后面第一个敌子
                        nx += dx; ny += dy
                        while 0 <= nx < COLS and 0 <= ny < ROWS:
                            if self.board[ny][nx] != 0:
                                if _p(self.board[ny][nx]) != self.turn:
                                    moves.add((nx, ny))
                                break
                            nx += dx; ny += dy
                        break
        elif t == PAWN:
            if self.turn == 0:   # 红兵向上
                if y > 0 and (self.board[y - 1][x] == 0 or _p(self.board[y - 1][x]) != self.turn):
                    moves.add((x, y - 1))
                if y <= 4:       # 过河可左右
                    for dx in (-1, 1):
                        add(x + dx, y)
            else:                # 黑卒向下
                if y < ROWS - 1 and (self.board[y + 1][x] == 0 or _p(self.board[y + 1][x]) != self.turn):
                    moves.add((x, y + 1))
                if y >= 5:
                    for dx in (-1, 1):
                        add(x + dx, y)
        return moves

    def _king_at(self, player):
        k = RED_BASE + KING if player == 0 else BLK_BASE + KING
        for y in range(ROWS):
            for x in range(COLS):
                if self.board[y][x] == k:
                    return (x, y)
        return None

    def _attacked(self, king_pos, by_player):
        """(kx,ky) 是否被 by_player 的任意子攻击（含飞将）"""
        kx, ky = king_pos
        # 枚举 by_player 的每个子的落点是否含王
        for y in range(ROWS):
            for x in range(COLS):
                c = self.board[y][x]
                if c and _p(c) == by_player:
                    # 炮/马等走法 + 飞将
                    if _t(c) == CANNON:
                        if (kx, ky) in self._cannon_targets(x, y, c):
                            return True
                    else:
                        if (kx, ky) in self._move_gen(x, y, c):
                            return True
        # 飞将：对方将在同列且中间无子
        oy = [i for i in range(ROWS) if self.board[i][kx] != 0]
        if len(oy) >= 1:
            pass
        return False

    def _cannon_targets(self, x, y, code):
        """炮的攻击目标：隔一个子吃之后的第一个敌子"""
        out = set()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            while 0 <= nx < COLS and 0 <= ny < ROWS:
                if self.board[ny][nx] != 0:
                    nx += dx; ny += dy
                    while 0 <= nx < COLS and 0 <= ny < ROWS:
                        if self.board[ny][nx] != 0:
                            if _p(self.board[ny][nx]) != self.turn:
                                out.add((nx, ny))
                            break
                        nx += dx; ny += dy
                    break
                nx += dx; ny += dy
        return out

    def _in_check_self(self):
        k = self._king_at(self.turn)
        if not k:
            return False
        if self._flying_general(k, self.turn):
            return True
        return self._attacked(k, 1 - self.turn)

    def _flying_general(self, k, player):
        """飞将：本方将帅与对方将帅同列且中间无子（被"面对面"攻击）"""
        kx, ky = k
        ek = self._king_at(1 - player)
        if not ek or ek[0] != kx:
            return False
        for yy in range(min(ky, ek[1]) + 1, max(ky, ek[1])):
            if self.board[yy][kx] != 0:
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
        if not (0 <= fx < COLS and 0 <= fy < ROWS and 0 <= tx < COLS and 0 <= ty < ROWS):
            raise GameRuleError("越界")
        cell = self.board[fy][fx]
        if cell == 0 or not self._own(cell):
            raise GameRuleError("只能移动己方棋子")
        if (tx, ty) not in self._move_gen(fx, fy, cell):
            raise GameRuleError("该棋子不能这样走")
        # 模拟走子，检测自身被将军
        saved = self.board[ty][tx]
        self.board[ty][tx] = cell
        self.board[fy][fx] = 0
        if self._in_check_self():
            self.board[fy][fx] = cell
            self.board[ty][tx] = saved
            raise GameRuleError("不能送将/让己方将帅被将军")
        captured = saved != 0
        msgs = [f"♟ {self._nick(uid)} {PIECE_CN[cell]} ({fx},{fy})→({tx},{ty})"]
        if captured:
            msgs.append(f"💥 吃掉对方 {PIECE_CN[saved]}")
        # 飞将判定：若对方王此刻被攻击且无解 → 将死
        self.turn = 1 - self.turn
        if self._is_stalemate(self.turn):
            self.winner = uid
            msgs.append(f"🏆 {self._nick(uid)} 将死/困毙对方获胜！")
        return msgs

    def _is_stalemate(self, player):
        """该玩家 (即将轮到的一方) 是否无任何合法着法（已轮转到它）"""
        saved = self.turn
        self.turn = player
        for y in range(ROWS):
            for x in range(COLS):
                c = self.board[y][x]
                if c and _p(c) == player:
                    for (tx, ty) in self._move_gen(x, y, c):
                        sv = self.board[ty][tx]
                        self.board[ty][tx] = c
                        self.board[y][x] = 0
                        kchk = self._in_check_self()
                        self.board[y][x] = c
                        self.board[ty][tx] = sv
                        if not kchk:
                            self.turn = saved
                            return False
        self.turn = saved
        return True

    def snapshot(self):
        return {
            "game": self.name, "status": "playing",
            "board": self.board, "rows": ROWS, "cols": COLS,
            "turn_uid": None if self.winner else self.players[self.turn],
            "players": list(self.players), "winner_uid": self.winner,
            "legend": {str(PIECE_CN[k]): PIECE_CN[k] for k in PIECE_CN},
        }

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner, "detail": f"{self._nick(self.winner)} 胜出"}
        return None

    def _nick(self, uid):
        return f"玩家{uid}"