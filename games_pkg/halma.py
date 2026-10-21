# -*- coding: utf-8 -*-
"""跳棋（致敬 中国跳棋/波子棋 Halma）：9x9 方形棋盘，四角各有一个“营”字三角目标区。
可向八个方向直移一格，或越过相邻一格棋子跳到其后空格（可跳己方/对方子，长度恰为 2）。
2~4 人：各占一个角（玩家 i 落座在角 i），目标是把己方全部棋子“反向”搬进对角营区——
对弈双方相向而行，先让所有子到达对方出发区者胜。休闲版：每手只支持一次连跳。"""
from games_pkg.base import BaseGame, GameRuleError

N = 9
SIZE = N
C = N // 2                      # 中心 4
ARMS = 4                        # 四角营区
ARM_CRIT = 3                    # 每营三角 |dx|+|dy| 阈值（角三角互不重叠）


def _arm_cells(i):
    """第 i 个角营区（0上 1右 2下 3左）的格子集合"""
    cells = set()
    if i == 0:      # 上：y + |x-C| <= CRIT
        for y in range(0, C + 1):
            for x in range(N):
                if y + abs(x - C) <= ARM_CRIT:
                    cells.add((x, y))
    elif i == 1:    # 右：x + |y-C| <= CRIT
        for x in range(C, N):
            for y in range(N):
                if (N - 1 - x) + abs(y - C) <= ARM_CRIT:
                    cells.add((x, y))
    elif i == 2:    # 下：(N-1-y) + |x-C| <= CRIT
        for y in range(N - 1 - C, N):
            for x in range(N):
                if (N - 1 - y) + abs(x - C) <= ARM_CRIT:
                    cells.add((x, y))
    else:           # 左：x + |y-C| <= CRIT
        for x in range(0, C + 1):
            for y in range(N):
                if x + abs(y - C) <= ARM_CRIT:
                    cells.add((x, y))
    return cells


ARM_CELLS = []
for _i in range(ARMS):
    ARM_CELLS.append(_arm_cells(_i))

# 全部合法格子 = 四角营区并集（星形）
VALID = set()
for c in ARM_CELLS:
    VALID |= c
# 中央连接区：四营尖角之间的小孔必须可走，否则 4 营满座（16×4=64 格）时
# 开局棋盘被占满，3~4 人局任何一方都无子可动。
CENTER_GAPS = {(C - 1, C - 1), (C + 1, C - 1), (C - 1, C + 1),
               (C + 1, C + 1), (C, C)}
VALID |= CENTER_GAPS

DIRS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)]

ROCK_CN = ["⚫", "🔴", "🟣", "🟢"]


class HalmaGame(BaseGame):
    name = "halma"
    min_players = 2
    max_players = 4

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.n = len(players)
        self.board = {}
        # 座次：2 人面对面(对角)，3 人三角，4 人四角
        if self.n == 2:
            seats = [0, 2]
        elif self.n == 3:
            seats = [0, 2, 1]
        else:
            seats = [0, 1, 2, 3]
        self.arm_of = {p: a for p, a in zip(players, seats)}
        for i, p in enumerate(players):
            for (x, y) in ARM_CELLS[seats[i]]:
                self.board[(x, y)] = (p, seats[i])
        self.turn = 0
        self.winner = None
        self.draw = False
        self._end_detail = None
        self.last_move = None

    def _over(self):
        return self.winner is not None or self.draw

    # ---- 营区辅助 ----
    def _goal_arm(self, arm):
        return ARM_CELLS[(arm + 2) % ARMS]

    def _goal_weights(self, arm):
        # 以到目标营中心的距离给子排序（仅用于展示/提示，不参与判定）
        goal = self._goal_arm(arm)
        cx = sum(x for x, _ in goal) / len(goal)
        cy = sum(y for _, y in goal) / len(goal)
        return {p: abs(p[0] - cx) + abs(p[1] - cy) for p in goal}

    def _in(self, pos, cellset):
        return pos in cellset

    # ---- 动作 ----
    def act(self, uid, action):
        if self._over():
            raise GameRuleError("本局已结束")
        if uid != self.players[self.turn]:
            raise GameRuleError("还没轮到你")
        try:
            fx = int(action.get("fx")); fy = int(action.get("fy"))
            tx = int(action.get("tx")); ty = int(action.get("ty"))
        except (TypeError, ValueError):
            raise GameRuleError("坐标必须为整数")
        if not (0 <= fx < N and 0 <= fy < N and 0 <= tx < N and 0 <= ty < N):
            raise GameRuleError("越界")
        if (fx, fy) not in VALID or (tx, ty) not in VALID:
            raise GameRuleError("此位置不在棋盘上")
        owner, arm = self.board.get((fx, fy), (None, None))
        if owner != uid:
            raise GameRuleError("只能移动己方棋子")
        if (tx, ty) in self.board:
            raise GameRuleError("目标格已有棋子")
        dx, dy = tx - fx, ty - fy
        ad = max(abs(dx), abs(dy))
        if ad == 1:
            step = 1
        elif ad == 2 and (dx == 0 or dy == 0 or abs(dx) == abs(dy)):
            mid = (fx + dx // 2, fy + dy // 2)
            if mid not in self.board:
                raise GameRuleError("中间没有可跳的棋子")
            step = 2
        else:
            raise GameRuleError("只能直移一格或隔一子直跳")
        del self.board[(fx, fy)]
        self.board[(tx, ty)] = (uid, arm)
        self.last_move = ((fx, fy), (tx, ty))
        msgs = [f"⚪ {self._nick(uid)} 走子 ({fx},{fy})→({tx},{ty})"
                + ("（跳子）" if step == 2 else "")]
        if all((x, y) in self._goal_arm(arm) for (x, y) in
               [k for k, v in self.board.items() if v[0] == uid]):
            self.winner = uid
            msgs.append(f"🏆 {self._nick(uid)} 全部抵达对岸，获胜！")
            return msgs
        self.turn = (self.turn + 1) % self.n
        msgs.extend(self._skip_to_movable())
        return msgs

    def legal_moves(self, uid):
        """当前行动者的单步直移/跳子（连跳由 act 分步执行，此处只给下一步）。"""
        if self._over() or uid != self.players[self.turn]:
            return []
        out = []
        for (x, y), (p, _) in self.board.items():
            if p != uid:
                continue
            for tx, ty in self._targets(x, y):
                out.append({"from": [x, y], "to": [tx, ty]})
        return out

    # ---- 回合推进 / 无步跳过 ----
    def _has_move(self, uid):
        for (x, y), (p, _) in self.board.items():
            if p == uid and self._targets(x, y):
                return True
        return False

    def _progress(self, uid):
        """(已入对角营的棋子数, -剩余距离)：元组越大越领先，规则确定可复现"""
        arm = self.arm_of.get(uid)
        if arm is None:
            return (0, 0)
        goal = self._goal_arm(arm)
        cells = [pos for pos, (p, _) in self.board.items() if p == uid]
        in_goal = sum(1 for pos in cells if pos in goal)
        remain = sum(min(max(abs(x - gx), abs(y - gy)) for (gx, gy) in goal)
                     for (x, y) in cells)
        return (in_goal, -remain)

    def _skip_to_movable(self):
        """从当前座位起跳过无子可动的玩家；全员无步时立即终局，避免死循环"""
        msgs = []
        n = len(self.players)
        for _ in range(n):
            uid = self.players[self.turn]
            if self._has_move(uid):
                return msgs
            msgs.append(f"⏭ {self._nick(uid)} 无子可动，跳过")
            self.turn = (self.turn + 1) % n
        msgs.extend(self._finish_stuck())
        return msgs

    def _finish_stuck(self):
        """全员无子可动：按入营子数、剩余距离依次比较，仍相同则平局"""
        scores = {u: self._progress(u) for u in self.players}
        best = max(scores.values())
        leaders = [u for u, s in scores.items() if s == best]
        if len(leaders) == 1:
            self.winner = leaders[0]
            self._end_detail = (f"全员无子可动，{self._nick(self.winner)} 以 "
                                f"{best[0]} 子入营、剩余距离 {-best[1]} 领先")
            return [f"🏁 全员无子可动，按进度判定 {self._nick(self.winner)} 获胜"]
        self.draw = True
        self._end_detail = (f"全员无子可动，各 {best[0]} 子入营、"
                            f"剩余距离 {-best[1]}，平局")
        return ["🏁 全员无子可动，进度相同，平局"]

    # ---- 提示辅助 ----
    def _targets(self, x, y):
        """(x,y) 上棋子的合法落点 [[tx, ty], ...]：直移一格（空）+ 隔一子直跳（空）"""
        out = []
        for dx, dy in DIRS:
            nx, ny = x + dx, y + dy
            if (nx, ny) in VALID and (nx, ny) not in self.board:
                out.append([nx, ny])
            jx, jy = x + dx * 2, y + dy * 2
            if (jx, jy) in VALID and (jx, jy) not in self.board and (nx, ny) in self.board:
                out.append([jx, jy])
        return out

    def snapshot(self):
        grid = [[0] * N for _ in range(N)]
        for (x, y), (p, arm) in self.board.items():
            grid[y][x] = p
        state = {
            "game": self.name, "status": "playing",
            "board": grid, "size": N,
            "valid": [[1 if (x, y) in VALID else 0 for x in range(N)] for y in range(N)],
            "arms": [[[1 if (x, y) in ARM_CELLS[a] else 0 for x in range(N)] for y in range(N)]
                     for a in range(ARMS)],
            "turn_uid": None if self._over() else self.players[self.turn],
            "players": list(self.players), "winner_uid": self.winner,
            "owners": {str(p): self.arm_of[p] for p in self.players},
        }
        if not self._over():
            me = self.players[self.turn]
            hints = {}
            for (x, y), (p, arm) in self.board.items():
                if p == me:
                    tg = self._targets(x, y)
                    if tg:
                        hints[f"{x},{y}"] = tg
            state["hints"] = hints
        return state

    def ended(self):
        # 兜底：若盘面已无任何人可走（如掉线后），查询终局时直接结算
        if not self._over() and self.players and not any(
                self._has_move(u) for u in self.players):
            self._finish_stuck()
        if self.winner is not None:
            return {"winner_uid": self.winner,
                    "detail": self._end_detail
                    or f"{self._nick(self.winner)} 率先全部抵达对岸"}
        if self.draw:
            return {"winner_uid": None, "detail": self._end_detail or "平局"}
        return None

    def player_left(self, uid):
        if uid not in self.players:
            return []
        idx = self.players.index(uid)
        self.arm_of.pop(uid, None)
        # 离场者的棋子一并移出，避免永远占住营区格子
        self.board = {k: v for k, v in self.board.items() if v[0] != uid}
        self.players.remove(uid)
        self.n = len(self.players)
        if not self.players:
            return [f"💨 {self._nick(uid)} 离开了对局"]
        if self.turn > idx:
            self.turn -= 1
        self.turn %= self.n
        if self.n < self.min_players and not self._over():
            self.winner = self.players[self.turn]
            self._end_detail = (f"{self._nick(uid)} 离开，仅剩 "
                                f"{self._nick(self.winner)}，判其获胜")
            return [f"💨 {self._nick(uid)} 离开，{self._nick(self.winner)} 获胜"]
        msgs = [f"💨 {self._nick(uid)} 离开了对局"]
        if not self._over():
            msgs.extend(self._skip_to_movable())
        return msgs

    def _nick(self, uid):
        return f"玩家{uid}"