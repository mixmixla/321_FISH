# -*- coding: utf-8 -*-
"""角斗士棋（致敬 Blokus）：20x20 棋盘，2~4 人轮流放置自己的一套“角斗方块”（拼块）。
第一块必须触及棋盘四角之一；之后每块必须「角对角」接触己方已有方块（至少一个格子与其
斜对角相邻），同时**不得**与己方方块同边相邻。全部放完或无人可放即终局，
剩余方块格子越少者胜——即铺满棋盘最多者赢。"""
from games_pkg.base import BaseGame, GameRuleError

BOARD = 20
PLAYER_COL = ["#e05555", "#3f6fe0", "#3ba55d", "#e8b93c"]
PLAYER_PIECES = 21

# 每个方块定义：[名称缩写, 单元格列表(行,列), 面积]；均为「标准位形」，运行时生成旋转/镜像
PIECES = [
    ("M", [(0, 0)], 1),
    ("D", [(0, 0), (1, 0)], 2),
    ("T3I", [(0, 0), (1, 0), (2, 0)], 3),
    ("T3L", [(0, 0), (1, 0), (1, 1)], 3),
    ("O4", [(0, 0), (0, 1), (1, 0), (1, 1)], 4),
    ("I4", [(0, 0), (1, 0), (2, 0), (3, 0)], 4),
    ("L4", [(0, 0), (1, 0), (2, 0), (2, 1)], 4),
    ("S4", [(0, 1), (0, 2), (1, 0), (1, 1)], 4),
    ("T4", [(0, 0), (1, 0), (2, 0), (1, 1)], 4),
    ("F5", [(0, 1), (1, 0), (1, 1), (1, 2), (2, 0)], 5),
    ("I5", [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)], 5),
    ("L5", [(0, 0), (1, 0), (2, 0), (3, 0), (3, 1)], 5),
    ("P5", [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)], 5),
    ("N5", [(0, 0), (1, 0), (2, 0), (2, 1), (3, 1)], 5),
    ("T5", [(0, 0), (1, 0), (2, 0), (1, 1), (1, 2)], 5),
    ("U5", [(0, 0), (0, 1), (0, 2), (1, 0), (1, 2)], 5),
    ("V5", [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)], 5),
    ("W5", [(0, 0), (1, 0), (1, 1), (2, 1), (2, 2)], 5),
    ("X5", [(0, 1), (1, 0), (1, 1), (1, 2), (2, 1)], 5),
    ("Y5", [(0, 0), (1, 0), (2, 0), (3, 0), (2, 1)], 5),
    ("Z5", [(0, 0), (1, 0), (1, 1), (2, 1), (2, 2)], 5),
]

ORTHO = [(1, 0), (-1, 0), (0, 1), (0, -1)]
DIAG = [(1, 1), (1, -1), (-1, 1), (-1, -1)]


def _orientations(cells):
    """对标准位形生成所有旋转与镜像后的归一化位形（去重）。返回坐标格子集合列表。"""
    out = []
    seen = set()
    cur = [tuple(c) for c in cells]
    for flip in (0, 1):
        base = cur if flip == 0 else [(-r, c) for (r, c) in cur]
        rot = base
        for _ in range(4):
            # 归一化到最小包围盒原点
            mr = min(r for r, _ in rot); mc = min(c for _, c in rot)
            norm = tuple(sorted((r - mr, c - mc) for (r, c) in rot))
            if norm not in seen:
                seen.add(norm)
                out.append({(r, c) for (r, c) in norm})
            # 顺时针旋转 90°： (r,c)->(c,-r)
            rot = [(c, -r) for (r, c) in rot]
    return out


# 预生成全部拼块的旋转/镜像位形，供前端展示与试放
PIECE_CATALOG = {name: _orientations(cells) for name, cells, _ in PIECES}


class BlokusGame(BaseGame):
    name = "blokus"
    min_players = 2
    max_players = 4

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.n = len(players)
        self.board = {}                       # (r,c) -> uid
        # 每个玩家的剩余角斗方块：name -> [面积, orientations列表]
        self.bag = {}
        for p in players:
            self.bag[p] = {}
            for name, cells, area in PIECES:
                self.bag[p][name] = [area, _orientations(cells)]
        self.turn = 0
        self.placed = {p: 0 for p in players}      # 已放置面积
        self.pass_seq = 0                          # 已连续跳过的人数
        self.last_action = None
        self.last_move = None
        self.winner = None

    # ---- 规则判定 ----
    def _diag_contact(self, uid, r, c):
        return any(self.board.get((r + dr, c + dc)) == uid for dr, dc in DIAG)

    def _ortho_contact(self, uid, r, c):
        return any(self.board.get((r + dr, c + dc)) == uid for dr, dc in ORTHO)

    def _advance_turn(self):
        """轮到下一个还有拼块的玩家；全部用完则终局。"""
        for _ in range(self.n):
            self.turn = (self.turn + 1) % self.n
            if self.bag[self.players[self.turn]]:
                return None
        return self._finish("所有玩家拼块用完，对局结束")

    # ---- 动作 ----
    def act(self, uid, action):
        if self.winner:
            raise GameRuleError("本局已结束")
        if uid != self.players[self.turn]:
            raise GameRuleError("还没轮到你")
        op = action.get("op")
        if op == "pass":
            return self._pass()
        if op == "place":
            return self._place(uid, action)
        raise GameRuleError("未知操作")

    def _pass(self):
        old = self.turn
        self.pass_seq += 1
        active = sum(1 for p in self.players if self.bag[p])
        if self.pass_seq >= max(1, active):
            return [self._finish("所有玩家连续跳过，对局结束")]
        msg = self._advance_turn()
        if msg:
            return [msg]
        return [f"⏭️ {self._nick(self.players[old])} 跳过"]

    def _place(self, uid, action):
        name = action.get("piece")
        if name not in self.bag.get(uid, {}):
            raise GameRuleError("没有该拼块")
        area, ots = self.bag[uid][name]
        try:
            oi = int(action.get("oi", 0))
            x = int(action.get("x")); y = int(action.get("y"))
        except (TypeError, ValueError):
            raise GameRuleError("参数无效")
        if not (0 <= oi < len(ots)):
            raise GameRuleError("方向号无效")
        cells = ots[oi]
        if not (0 <= x < BOARD and 0 <= y < BOARD):
            raise GameRuleError("越界")
        # 校验所有格子可落且符合规则
        placed_cells = []
        first = self.placed[uid] == 0
        for (ar, ac) in cells:
            rr, cc = x + ar, y + ac
            if not (0 <= rr < BOARD and 0 <= cc < BOARD):
                raise GameRuleError("拼块超出棋盘")
            if (rr, cc) in self.board:
                raise GameRuleError("该位置已被占用")
            placed_cells.append((rr, cc))
        if first:
            if not any((r, c) in {(0, 0), (0, BOARD - 1), (BOARD - 1, 0), (BOARD - 1, BOARD - 1)}
                       for (r, c) in placed_cells):
                raise GameRuleError("首块必须触及一个棋盘角")
        else:
            if not any(self._diag_contact(uid, rr, cc) for (rr, cc) in placed_cells):
                raise GameRuleError("必须与己方角对角相连")
            if any(self._ortho_contact(uid, rr, cc) for (rr, cc) in placed_cells):
                raise GameRuleError("不能与己方同边相邻")
        for (rr, cc) in placed_cells:
            self.board[(rr, cc)] = uid
        del self.bag[uid][name]
        self.placed[uid] += area
        self.last_action = (uid, name)
        self.last_move = [[rr, cc] for (rr, cc) in placed_cells]
        msgs = [f"🧩 {self._nick(uid)} 放置拼块「{name}」"]
        self.pass_seq = 0
        done = self._advance_turn()
        if done:
            msgs.append(done)
        return msgs

    def _finish(self, why):
        # 剩余格子少者胜
        remain = {p: sum(a for n, (a, _) in self.bag[p].items()) for p in self.players}
        best = min(self.players, key=lambda p: remain[p])
        ranks = sorted(self.players, key=lambda p: (remain[p],
                                                    -self.placed[p],
                                                    self.players.index(p)))
        self.winner = best
        rtxt = "  >  ".join(f"{self._nick(p)}剩{remain[p]}格" for p in ranks)
        return f"🏁 {why}｜{rtxt}｜🏆 {self._nick(best)} 获胜！"

    def snapshot(self):
        grid = [[None] * BOARD for _ in range(BOARD)]
        for (r, c), u in self.board.items():
            grid[r][c] = u
        return {
            "game": self.name, "status": "playing",
            "board": grid, "size": BOARD,
            "turn_uid": None if self.winner else self.players[self.turn],
            "players": list(self.players), "winner_uid": self.winner,
            "placed": {str(u): self.placed[u] for u in self.players},
            "has_piece": {str(u): sorted(self.bag[u].keys()) for u in self.players},
            "colors": PLAYER_COL[:self.n],
            "last_move": self.last_move,
            # JSON-safe：每个朝向表示为 ["r,c", ...] 字符串列表（set 不可序列化）
            "pieces": {name: [sorted(f"{r},{c}" for (r, c) in ori)
                              for ori in PIECE_CATALOG[name]]
                       for name in PIECE_CATALOG},
        }

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner,
                    "detail": f"{self._nick(self.winner)} 剩余格子最少获胜"}
        return None

    def _nick(self, uid):
        return f"玩家{uid}"