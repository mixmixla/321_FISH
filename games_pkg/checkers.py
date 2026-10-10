# -*- coding: utf-8 -*-
"""国际跳棋（致敬 Checkers/Draughts）：8x8，双方各 12 子，普通子只能斜向前移一格、可斜跳吃子，
王可任意斜线行走。把对方子吃光或令其无路可走者胜。休闲版：不强制优先吃子。"""
from games_pkg.base import BaseGame, GameRuleError

N = 8
BLACK_MAN, RED_MAN = 1, 2      # 玩家0(黑)、玩家1(红) 普通子
BLACK_KING, RED_KING = 3, 4    # 王


class CheckersGame(BaseGame):
    name = "checkers"
    min_players = 2
    max_players = 2

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.p0, self.p1 = players[0], players[1]
        self.board = [[0] * N for _ in range(N)]
        for r in range(3):
            for c in range(N):
                if (r + c) % 2 == 1:
                    self.board[r][c] = BLACK_MAN
        for r in range(5, N):
            for c in range(N):
                if (r + c) % 2 == 1:
                    self.board[r][c] = RED_MAN
        self.turn = 0
        self.winner = None
        self.last_move = None

    # ---- 视角 ----
    def _me(self, cell):
        """cell 是否属当前玩家的子"""
        if cell in (BLACK_MAN, BLACK_KING):
            return self.turn == 0
        if cell in (RED_MAN, RED_KING):
            return self.turn == 1
        return False

    def _dir(self, cell):
        """普通子移动方向：黑向下(+1)，红向上(-1)"""
        if cell in (BLACK_MAN, BLACK_KING):
            return 1
        return -1

    def _is_man(self, cell):
        return cell in (BLACK_MAN, RED_MAN)

    def _enemy(self, cell):
        if cell == 0:
            return False
        is_red = cell in (RED_MAN, RED_KING)
        return is_red if self.turn == 0 else not is_red

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
        cell = self.board[fy][fx]
        if cell == 0 or not self._me(cell):
            raise GameRuleError("只能移动己方棋子")
        dx, dy = tx - fx, ty - fy
        if not (abs(dx) == abs(dy)):
            raise GameRuleError("只能斜向移动")
        step = abs(dx)
        if self._is_man(cell) and step == 2 and self.board[fy + dy // 2][fx + dx // 2] == 0:
            raise GameRuleError("非法")
        if step > 2 and self._is_man(cell):
            raise GameRuleError("普通子只能走/吃一步以内")
        if self.board[ty][tx] != 0:
            raise GameRuleError("目标格已有棋子")
        # 吃子判定
        captures = 0
        if step == 2:
            midx, midy = (fx + tx) // 2, (fy + ty) // 2
            mid = self.board[midy][midx]
            if not self._enemy(mid) or mid == 0:
                raise GameRuleError("中间没有可吃的对方子")
            self.board[midy][midx] = 0
            captures = 1
        elif step > 1:
            # 王走多格，途中须为空
            sx, sy = dx // step, dy // step
            for k in range(1, step):
                if self.board[fy + sy * k][fx + sx * k] != 0:
                    raise GameRuleError("路径被挡")
        self.board[fy][fx] = 0
        # 升王
        if self._is_man(cell):
            if (self.turn == 0 and ty == N - 1):
                cell = BLACK_KING
            elif (self.turn == 1 and ty == 0):
                cell = RED_KING
        self.board[ty][tx] = cell
        self.last_move = ((fx, fy), (tx, ty))
        msgs = [f"🏃 {self._nick(uid)} {"吃子" if captures else "移动"} ({fx},{fy})→({tx},{ty})"]
        if captures:
            msgs.append(f"💥 吃掉对方一枚棋子")
        # 胜负判断
        enemy_peer = self.p1 if self.turn == 0 else self.p0
        enemy_cell0, enemy_cell1 = ((RED_MAN, RED_KING) if self.turn == 0
                                    else (BLACK_MAN, BLACK_KING))
        enemies = sum(1 for row in self.board for c in row if c in (enemy_cell0, enemy_cell1))
        if enemies == 0:
            self.winner = uid
            msgs.append(f"🏆 {self._nick(uid)} 吃光对方子获胜！")
            return msgs
        self.turn = 1 - self.turn
        if not self._has_move():
            self.winner = uid
            msgs.append(f"🏆 {self._nick(uid)} 对方无路可走获胜！")
        return msgs

    def _has_move(self):
        """当前玩家是否还有合法走/吃"""
        me0, me1 = ((BLACK_MAN, BLACK_KING) if self.turn == 0
                    else (RED_MAN, RED_KING))
        for y in range(N):
            for x in range(N):
                c = self.board[y][x]
                if c not in (me0, me1):
                    continue
                if not self._is_man(c):
                    for dx in (-1, 1):
                        for dy in (-1, 1):
                            nx, ny = x + dx, y + dy
                            found = False
                            step = 1
                            while 0 <= nx < N and 0 <= ny < N and self.board[ny][nx] == 0:
                                found = True
                                step += 1
                                nx += dx
                                ny += dy
                            if found:
                                return True
                else:
                    d = self._dir(c)
                    for dx in (-1, 1):
                        nx, ny = x + dx, y + d
                        if 0 <= nx < N and 0 <= ny < N and self.board[ny][nx] == 0:
                            return True
        return False

    def _targets(self, x, y):
        """(x,y) 上棋子的合法落点 [[tx, ty], ...]
        普通子：前向斜 1 格（空）+ 前向斜跳过一枚敌子（落点空）
        王：四斜向连续空格 + 斜向隔一枚敌子跳吃"""
        cell = self.board[y][x]
        out = []
        if self._is_man(cell):
            d = self._dir(cell)
            for dx in (-1, 1):
                nx, ny = x + dx, y + d
                if not (0 <= nx < N and 0 <= ny < N):
                    continue
                if self.board[ny][nx] == 0:
                    out.append([nx, ny])
                if self._enemy(self.board[ny][nx]):
                    jx, jy = x + dx * 2, y + d * 2
                    if 0 <= jx < N and 0 <= jy < N and self.board[jy][jx] == 0:
                        out.append([jx, jy])
        else:
            for dx in (-1, 1):
                for dy in (-1, 1):
                    nx, ny = x + dx, y + dy
                    while 0 <= nx < N and 0 <= ny < N:
                        if self.board[ny][nx] == 0:
                            out.append([nx, ny])
                            nx += dx
                            ny += dy
                        elif self._enemy(self.board[ny][nx]):
                            jx, jy = nx + dx, ny + dy
                            if 0 <= jx < N and 0 <= jy < N and self.board[jy][jx] == 0:
                                out.append([jx, jy])
                            break
                        else:
                            break
        return out

    def snapshot(self):
        state = {
            "game": self.name, "status": "playing",
            "board": self.board, "size": N,
            "turn_uid": None if self.winner else self.players[self.turn],
            "players": list(self.players), "winner_uid": self.winner,
            "legend": {str(BLACK_MAN): "黑", str(RED_MAN): "红",
                       str(BLACK_KING): "黑王", str(RED_KING): "红王"},
        }
        if not self.winner:
            hints = {}
            for y in range(N):
                for x in range(N):
                    if self._me(self.board[y][x]):
                        tg = self._targets(x, y)
                        if tg:
                            hints[f"{x},{y}"] = tg
            state["hints"] = hints
        return state

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner, "detail": f"{self._nick(self.winner)} 胜出"}
        return None

    def _nick(self, uid):
        return f"玩家{uid}"