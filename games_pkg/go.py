# -*- coding: utf-8 -*-
"""围棋：9 / 13 / 19 路可选（创建房间时选择）。黑白交替落子，团块无气即被提，
禁自杀并应用简单打劫同型禁着。双方轮流「过」(pass)则终局，按「各色子 +
被其完全包围的空地」计分，目数多者胜。白方按路数贴目（9 路 6.5，13/19 路 7.5）。"""
from games_pkg.base import BaseGame, GameRuleError

import math
import time

DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
AI_UID = -1                      # 单人练习里的电脑方（非房间玩家）
MCTS_TIME = 0.55                 # 每手 MCTS 思考预算（秒）
MCTS_SIMS = 800                  # 单手上限（防止极慢机器）


def _grp(board, x, y, color):
    """返回 (团块格子集合, 气/贴邻空点集合)"""
    seen = {(x, y)}
    stack = [(x, y)]
    liberties = set()
    while stack:
        cx, cy = stack.pop()
        for dx, dy in DIRS:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < len(board) and 0 <= ny < len(board)):
                continue
            v = board[ny][nx]
            if v == 0:
                liberties.add((nx, ny))
            elif v == color and (nx, ny) not in seen:
                seen.add((nx, ny))
                stack.append((nx, ny))
    return seen, liberties


# ---------- MCTS 用的扁平棋盘（9x9） ----------
_GN = 9
_GNB = [[] for _ in range(_GN * _GN)]
_GDG = [[] for _ in range(_GN * _GN)]
for _i in range(_GN * _GN):
    _x, _y = _i % _GN, _i // _GN
    for _dx, _dy in DIRS:
        _nx, _ny = _x + _dx, _y + _dy
        if 0 <= _nx < _GN and 0 <= _ny < _GN:
            _GNB[_i].append(_ny * _GN + _nx)
    for _dx, _dy in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        _nx, _ny = _x + _dx, _y + _dy
        if 0 <= _nx < _GN and 0 <= _ny < _GN:
            _GDG[_i].append(_ny * _GN + _nx)


def _go_group(b, i, color):
    seen = {i}
    stack = [i]
    libs = set()
    while stack:
        p = stack.pop()
        for q in _GNB[p]:
            v = b[q]
            if v == 0:
                libs.add(q)
            elif v == color and q not in seen:
                seen.add(q)
                stack.append(q)
    return seen, libs


def _go_legal(b, i, color):
    """扁平盘试下：返回 (新盘, 提子数) 或 None（自杀/占用）。"""
    if b[i] != 0:
        return None
    nb = b[:]
    nb[i] = color
    opp = 3 - color
    caps = 0
    for q in _GNB[i]:
        if nb[q] == opp:
            grp, libs = _go_group(nb, q, opp)
            if not libs:
                for p in grp:
                    nb[p] = 0
                caps += len(grp)
    grp, libs = _go_group(nb, i, color)
    if not libs:
        return None
    return nb, caps


def _go_is_eye(b, i, color):
    """粗略眼位：四邻皆己方且对角至少 3/4（边角按实际对角数放宽）。"""
    for q in _GNB[i]:
        if b[q] != color:
            return False
    diag = _GDG[i]
    return sum(1 for q in diag if b[q] == color) >= len(diag) - 1


def _go_area(b):
    """面积计分：子 + 只被单色包围的空地。"""
    black = b.count(1)
    white = b.count(2)
    seen = [False] * (_GN * _GN)
    for i in range(_GN * _GN):
        if b[i] != 0 or seen[i]:
            continue
        region = []
        stack = [i]
        seen[i] = True
        border = set()
        while stack:
            p = stack.pop()
            region.append(p)
            for q in _GNB[p]:
                if b[q] == 0:
                    if not seen[q]:
                        seen[q] = True
                        stack.append(q)
                else:
                    border.add(b[q])
        if len(border) == 1:
            if 1 in border:
                black += len(region)
            else:
                white += len(region)
    return black, white


def _go_rollout(b, to_move, rng, komi=0.0, limit=32):
    """随机模拟：避开己方眼位，连续两过或到达步数上限即停。"""
    passes = 0
    for _ in range(limit):
        empties = [i for i in range(_GN * _GN)
                   if b[i] == 0 and not _go_is_eye(b, i, to_move)]
        rng.shuffle(empties)
        moved = False
        for i in empties[:10]:
            res = _go_legal(b, i, to_move)
            if res:
                b = res[0]
                moved = True
                passes = 0
                break
        if not moved:
            passes += 1
            if passes >= 2:
                break
        to_move = 3 - to_move
    black, white = _go_area(b)
    return white + komi > black


class _MCTSNode:
    __slots__ = ("b", "to_move", "parent", "move", "children", "untried",
                 "visits", "wins")

    def __init__(self, b, to_move, parent=None, move=None):
        self.b = b
        self.to_move = to_move
        self.parent = parent
        self.move = move
        self.children = []
        self.untried = None
        self.visits = 0
        self.wins = 0.0


class GoGame(BaseGame):
    name = "go"
    min_players = 2
    max_players = 2
    SIZES = (9, 13, 19)             # 可选的棋盘路数
    DEFAULT_SIZE = 19
    KOMI_BY_SIZE = {9: 6.5, 13: 7.5, 19: 7.5}
    OPTIONS = {"size": SIZES}       # 房间创建参数（服务端校验）
    DEFAULT_OPTIONS = {"size": DEFAULT_SIZE}

    def __init__(self, players, seed=None, options=None):
        super().__init__(players, seed)
        self.p0 = players[0]
        self.p1 = players[1] if len(players) > 1 else None
        try:
            size = int((options or {}).get("size", self.DEFAULT_SIZE))
        except (TypeError, ValueError):
            raise GameRuleError("棋盘路数必须为整数")
        if size not in self.SIZES:
            raise GameRuleError("棋盘路数仅支持 9/13/19")
        self.size = size
        self.komi = self.KOMI_BY_SIZE[size]
        self.board = [[0] * self.size for _ in range(self.size)]
        self.turn = 0
        self.passes = 0
        self.captured = [0, 0]          # 白方吃子(player1)列为0? 用[黑吞,白吞]
        self.history = []
        self.winner = None
        self.over = False
        self.scores = None
        self.prev_key = None            # 上一手之前的局面（简单打劫判定）
        self.last_move = None

    def _own_color(self):
        return 1 if self.turn == 0 else 2

    def _lawful(self, x, y, color):
        if not (0 <= x < self.size and 0 <= y < self.size):
            raise GameRuleError("越界")
        if self.board[y][x] != 0:
            raise GameRuleError("该位已有子")
        # 试下
        self.board[y][x] = color
        # 1) 吃对手
        opp = 1 if color == 2 else 2
        killed = 0
        for dx, dy in DIRS:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < self.size and 0 <= ny < self.size):
                continue
            if self.board[ny][nx] == opp:
                grp, lib = _grp(self.board, nx, ny, opp)
                if not lib:
                    for gx, gy in grp:
                        self.board[gy][gx] = 0
                    killed += len(grp)
        # 2) 自杀检测
        grp, lib = _grp(self.board, x, y, color)
        if not lib:
            self.board[y][x] = 0
            raise GameRuleError("自杀点")
        self.board[y][x] = 0
        return True

    def _cur_uid(self):
        return self.players[self.turn]

    def _name_for(self, color):
        uid = self.p0 if color == 1 else self.p1
        return self._nick(uid) if uid is not None else "电脑"

    def act(self, uid, action):
        if self.over or self.winner:
            raise GameRuleError("本局已结束")
        if uid != self._cur_uid():
            raise GameRuleError("还没轮到你")
        return self._apply(action, self._own_color())

    def _finish_by_score(self):
        self.over = True
        self._score()
        self.winner = self._decide_winner()
        msgs = ["⏸ 双方停手，终局",
                f"🏁 黑 {self.scores[1]} 目 / 白 {self.scores[2]} 目"]
        if self.winner:
            msgs.append(f"🏆 {self._name_for(1 if self.winner == self.p0 else 2)} 目数领先获胜")
        else:
            msgs.append("🤝 和棋")
        return msgs

    def _apply(self, action, color):
        """按颜色执行一手（落子/过），不校验 uid；供多人对局与单人 AI 共用。"""
        if action.get("pass"):
            self.last_move = None
            self.passes += 1
            if self.passes >= 2:          # 连续两次过 → 终局
                return self._finish_by_score()
            self.turn = 1 - self.turn
            return [f"⏸ {self._name_for(color)} 过"]
        try:
            x = int(action.get("x")); y = int(action.get("y"))
        except (TypeError, ValueError):
            raise GameRuleError("坐标必须为整数")
        if not (0 <= x < self.size and 0 <= y < self.size):
            raise GameRuleError("越界")
        if self.board[y][x] != 0:
            raise GameRuleError("该位已有子")
        before = [row[:] for row in self.board]
        before_caps = list(self.captured)
        before_key = str(self.board)
        self.board[y][x] = color
        opp = 1 if color == 2 else 2
        caps = []
        for dx, dy in DIRS:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < self.size and 0 <= ny < self.size):
                continue
            if self.board[ny][nx] == opp:
                grp, lib = _grp(self.board, nx, ny, opp)
                if not lib:
                    caps.extend(grp)
        if not caps:
            grp, lib = _grp(self.board, x, y, color)
            if not lib:
                self.board = before
                raise GameRuleError("自杀点")
        for gx, gy in caps:
            self.board[gy][gx] = 0
        self.captured[color - 1] += len(caps)
        # 简单打劫：新局面对上上一手之前的局面 → 禁止并回滚
        key = str(self.board)
        if key == self.prev_key:
            self.board = before
            self.captured = before_caps
            raise GameRuleError("同型反复禁止(打劫)")
        self.history.append(key)
        self.passes = 0
        self.prev_key = before_key
        self.last_move = (x, y)
        self.turn = 1 - self.turn
        return [f"{'⚫' if color == 1 else '⚪'} {self._name_for(color)} 落子({x},{y})"
                + (f"，提 {len(caps)} 子" if caps else "")]

    def _score(self):
        """计分：各色子 + 完全被该色包围的空地"""
        size = self.size
        owned = {1: [0, 0], 2: [0, 0]}   # {颜色:[石头数, 空地数]}
        for y in range(size):
            for x in range(size):
                v = self.board[y][x]
                if v:
                    owned[v][0] += 1
        # 空地归属标记
        visited = set()
        for y in range(size):
            for x in range(size):
                if self.board[y][x] != 0 or (x, y) in visited:
                    continue
                region = {(x, y)}
                stack = [(x, y)]
                touches = set()
                while stack:
                    cx, cy = stack.pop()
                    for dx, dy in DIRS:
                        nx, ny = cx + dx, cy + dy
                        if not (0 <= nx < size and 0 <= ny < size):
                            continue
                        v = self.board[ny][nx]
                        if v == 0:
                            if (nx, ny) not in region:
                                region.add((nx, ny))
                                stack.append((nx, ny))
                        else:
                            touches.add(v)
                for rx, ry in region:
                    visited.add((rx, ry))
                if len(touches) == 1:
                    c = touches.pop()
                    owned[c][1] += len(region)
        self.scores = {1: owned[1][0] + owned[1][1],
                       2: owned[2][0] + owned[2][1] + self.komi}

    def _decide_winner(self):
        b, w = self.scores[1], self.scores[2]
        if b > w:
            return self.p0
        if w > b:
            return self.p1
        return None

    def snapshot(self):
        return {
            "game": self.name, "status": "playing",
            "board": self.board, "size": self.size,
            "turn_uid": None if self.over else self._cur_uid(),
            "captured": self.captured, "players": list(self.players),
            "winner_uid": self.winner, "scores": self.scores, "over": self.over,
            "last_move": self.last_move,
            "legend": {"0": "空", "1": "⚫", "2": "⚪"},
        }

    def ended(self):
        if self.over:
            if self.winner:
                return {"winner_uid": self.winner,
                        "detail": f"黑 {self.scores[1]} 目 / 白 {self.scores[2]} 目，{self._nick(self.winner)} 胜"}
            return {"winner_uid": None, "detail": "和棋"}
        return None

    def _nick(self, uid):
        return f"玩家{uid}"


class GoSoloGame(GoGame):
    """单人练习：玩家执黑，电脑执白；玩家每落一手，电脑立即应一手。固定 9 路。"""
    name = "go_solo"
    min_players = 1
    max_players = 1
    SIZES = (9,)                    # 练习 AI 的搜索按 9 路优化
    DEFAULT_SIZE = 9
    OPTIONS = {"size": SIZES}
    DEFAULT_OPTIONS = {"size": DEFAULT_SIZE}

    def __init__(self, players, seed=None, options=None):
        super().__init__(players, seed, options={"size": 9})
        self.human = players[0]
        self.p1 = AI_UID          # 电脑方（非房间玩家）
        self.turn = 0             # 玩家先手（黑）
        self.mcts_time = MCTS_TIME

    def _cur_uid(self):
        return self.human if self.turn == 0 else AI_UID

    def _name_for(self, color):
        return self._nick(self.human) if color == 1 else "电脑"

    def _nick(self, uid):
        return "电脑" if uid == AI_UID else f"玩家{uid}"

    def _decide_winner(self):
        b, w = self.scores[1], self.scores[2]
        if b > w:
            return self.human
        if w > b:
            return AI_UID
        return None

    def snapshot(self):
        s = super().snapshot()
        s.update(solo=True, ai_uid=AI_UID)
        return s

    def act(self, uid, action):
        if self.over or self.winner:
            raise GameRuleError("本局已结束")
        if uid != self.human:
            raise GameRuleError("单人练习只能由房主操作")
        msgs = self._apply(action, 1)
        if self.over or self.winner:
            return msgs
        msgs += self._apply(self._ai_choose(), 2)
        return msgs

    # ---- 简单练习 AI ----
    def _sim(self, x, y, color):
        """在副本上试下一手：返回 (是否合法, 提子数, 新棋盘)。"""
        b = [row[:] for row in self.board]
        b[y][x] = color
        opp = 3 - color
        caps = 0
        for dx, dy in DIRS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.size and 0 <= ny < self.size and b[ny][nx] == opp:
                grp, lib = _grp(b, nx, ny, opp)
                if not lib:
                    for gx, gy in grp:
                        b[gy][gx] = 0
                    caps += len(grp)
        grp, lib = _grp(b, x, y, color)
        if not lib:
            return False, caps, b
        return True, caps, b

    # ---- 练习 AI：MCTS 主引擎 + 提子捷径 + 启发式兜底 ----
    def _best_capture(self):
        """立即能提子的着法（战术捷径，保证 AI 不错过吃子）。"""
        n = self.size
        b = [self.board[y][x] for y in range(n) for x in range(n)]
        best, best_caps = None, 0
        for i in range(n * n):
            if b[i] != 0:
                continue
            res = _go_legal(b, i, 2)
            if res and res[1] > best_caps:
                nb = res[0]
                nb2 = [nb[y * n:(y + 1) * n] for y in range(n)]
                if str(nb2) == self.prev_key:
                    continue
                best_caps, best = res[1], i
        return best

    def _mcts_choose(self):
        """UCT-MCTS：随机模拟 + 面积计分，按访问次数选点。"""
        n = self.size
        b = [self.board[y][x] for y in range(n) for x in range(n)]
        # 玩家刚过且电脑面积不落后 → 跟着过，直接收子
        if self.passes >= 1:
            black, white = _go_area(b)
            if white + self.komi >= black:
                return {"pass": True}
        # 根节点合法着法（排除自杀、己方眼、打劫回提）
        roots = []
        for i in range(n * n):
            if b[i] != 0 or _go_is_eye(b, i, 2):
                continue
            res = _go_legal(b, i, 2)
            if not res:
                continue
            nb = res[0]
            nb2 = [nb[y * n:(y + 1) * n] for y in range(n)]
            if str(nb2) == self.prev_key:
                continue
            roots.append(i)
        if not roots:
            return {"pass": True}
        root = _MCTSNode(b, 2)
        root.untried = list(roots)
        deadline = time.monotonic() + self.mcts_time
        sims = 0
        while sims < MCTS_SIMS and time.monotonic() < deadline:
            node = root
            # 选择
            while not node.untried and node.children:
                log_n = math.log(max(1, node.visits))
                node = max(
                    node.children,
                    key=lambda c: (c.wins / c.visits
                                   + 1.4 * math.sqrt(log_n / c.visits)
                                   if c.visits else 1e9))
            # 扩展
            if node.untried:
                while node.untried:
                    i = node.untried.pop(self.rng.randrange(len(node.untried)))
                    res = _go_legal(node.b, i, node.to_move)
                    if not res:
                        continue
                    child = _MCTSNode(res[0], 3 - node.to_move, node, i)
                    node.children.append(child)
                    node = child
                    break
            # 随机模拟
            ai_win = _go_rollout(node.b[:], node.to_move, self.rng, self.komi)
            # 回传：wins 记在「走到该节点的那一方」视角
            leaf = node
            while leaf.parent is not None:
                if leaf.parent.to_move == 2:
                    leaf.wins += 1.0 if ai_win else 0.0
                else:
                    leaf.wins += 0.0 if ai_win else 1.0
                leaf.visits += 1
                leaf = leaf.parent
            root.visits += 1
            sims += 1
        if not root.children:
            return None
        best = max(root.children,
                   key=lambda c: (c.visits, c.wins / max(1, c.visits)))
        return {"x": best.move % n, "y": best.move // n}

    def _ai_choose(self):
        cap = self._best_capture()
        if cap is not None:
            return {"x": cap % self.size, "y": cap // self.size}
        mv = self._mcts_choose()
        if mv is not None:
            return mv
        return self._heuristic_choose()

    def _heuristic_choose(self):
        """兜底启发式：优先提子/打吃/救自己 1 气团，其次在棋子附近落子；无收益则过。"""
        color, opp = 2, 1
        best, best_score = None, -1
        for y in range(self.size):
            for x in range(self.size):
                if self.board[y][x] != 0:
                    continue
                ok, caps, nb = self._sim(x, y, color)
                if not ok or str(nb) == self.prev_key:
                    continue
                score = caps * 100
                near = 0
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx, ny = x + dx, y + dy
                        if not (0 <= nx < self.size and 0 <= ny < self.size):
                            continue
                        v = self.board[ny][nx]
                        if v:
                            near += 1
                        if v == color:
                            grp, lib = _grp(self.board, nx, ny, color)
                            if len(lib) == 1:
                                score += 40          # 救自己 1 气团
                        elif v == opp:
                            grp, lib = _grp(nb, nx, ny, opp)
                            if len(lib) == 1:
                                score += 30          # 打吃对方
                if all(self.board[y + dy][x + dx] == color
                       for dx, dy in DIRS
                       if 0 <= x + dx < self.size and 0 <= y + dy < self.size):
                    score -= 60                      # 不填自己的眼
                score += near * 2
                if score > best_score:
                    best_score, best = score, {"x": x, "y": y}
        if best is None:
            return {"pass": True}
        if self.passes >= 1 and best_score < 40:
            return {"pass": True}
        return best