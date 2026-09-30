# -*- coding: utf-8 -*-
"""24点：出 4 张 1~9 的牌，抢先用 + - * / 和括号凑出 24，先对者得分。
表达式用安全的递归下降解析 + Fraction 精确求值（不用 eval），且必须恰好用尽 4 张牌。"""
import random
import time
from fractions import Fraction

from games_pkg.base import BaseGame, GameRuleError

CARDS = list(range(1, 10))
ROUND_TIME = 25.0          # 每轮作答窗口
REVEAL_TIME = 3.0          # 揭晓停留
MAX_ROUNDS = 5


class Calc24Game(BaseGame):
    name = "calc24"
    min_players = 2
    max_players = 6

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.scores = {u: 0 for u in players}
        self.round_no = 0
        self.cards = []
        self.phase = "idle"           # answering | revealed | ended
        self.solved_uid = None
        self.win_expr = None
        self.win_seq = None
        self.round_end_at = 0.0
        self.reveal_end_at = 0.0
        self._next_round()

    # ---------- 轮次 ----------
    def _next_round(self) -> list:
        msgs = []
        if self.round_no >= MAX_ROUNDS:
            self.phase = "ended"
            best = max(self.scores.values(), default=0)
            winners = [u for u, s in self.scores.items() if s == best]
            if winners:
                msgs.append(
                    f"🎉 最终胜者：{'、'.join(self._nick(u) for u in winners)}"
                    f"（{best} 分）")
            return msgs
        self.round_no += 1
        self.cards = self._deal()
        self.solved_uid = None
        self.win_expr = None
        self.win_seq = _solve_seq(self.cards)
        self.phase = "answering"
        self.round_end_at = time.time() + ROUND_TIME
        msgs.append(f"第 {self.round_no} 轮：牌 {self.cards}，快用加减乘除凑 24！")
        return msgs

    def _deal(self) -> list:
        while True:
            hand = [self.rng.choice(CARDS) for _ in range(4)]
            if self._solvable(hand):
                return hand

    # ---------- 可解性 / 求解 ----------
    @staticmethod
    def _solvable(vals) -> bool:
        return any(abs(r - 24) == 0 for r in _all_values(vals))

    # ---------- 动作 ----------
    def snapshot(self) -> dict:
        return {
            "game": self.name, "status": self.phase, "round": self.round_no,
            "cards": list(self.cards), "players": list(self.players),
            "scores": dict(self.scores),
            "solved_uid": self.solved_uid,
            "win_expr": self.win_expr,
            "wait": max(0, int(self.round_end_at - time.time())) if self.phase == "answering" else 0,
        }

    def act(self, uid: int, action: dict) -> list:
        if self.phase != "answering":
            raise GameRuleError("当前不在作答阶段")
        if uid not in self.players:
            raise GameRuleError("你不在本局")
        if self.solved_uid is not None:
            raise GameRuleError("本轮已有人答对，请等待下一轮")
        raw = action.get("expr")
        expr = (raw or "").strip() if isinstance(raw, str) else ""
        if not expr:
            raise GameRuleError("请输入表达式")
        try:
            val = _parse_answer(expr, self.cards)
        except ValueAnswer as exc:
            raise GameRuleError(str(exc))
        if val != 24:
            raise GameRuleError("结果不是 24")
        # 保留一份答案供揭晓展示
        try:
            self.win_expr = _normalize_expr(expr)
        except Exception:
            self.win_expr = expr
        self.solved_uid = uid
        self.scores[uid] += 1
        self.phase = "revealed"
        self.reveal_end_at = time.time() + REVEAL_TIME
        return [f"🎯 {self._nick(uid)} 用 {self.win_expr} 凑出 24！"]

    def tick(self, now: float) -> list:
        if self.phase == "answering" and now >= self.round_end_at:
            self.phase = "revealed"
            self.reveal_end_at = now + REVEAL_TIME
            hint = self.win_seq["expr"] if self.win_seq else ""
            return [f"⏰ 时间到，无人答出。参考解：{hint}" if hint else "⏰ 时间到，无人答出。"]
        if self.phase == "revealed" and now >= self.reveal_end_at:
            return self._next_round()
        return []

    def ended(self):
        if self.phase == "ended":
            best = max(self.scores.values(), default=0)
            winners = [u for u, s in self.scores.items() if s == best]
            if len(winners) == 1:
                w = winners[0]
                return {"winner_uid": w,
                        "detail": f"{self._nick(w)} 以 {best} 分获胜"}
            return {"winner_uid": None,
                    "detail": "平局：" + "、".join(self._nick(u) for u in winners)}
        return None

    def _nick(self, uid: int) -> str:
        return f"玩家{uid}"


# ---------- 表达式解析（安全，无 eval） ----------

class ValueAnswer(Exception):
    """答案无效（格式/用牌/结果不对），转成 GameRuleError"""


def _tokenize(s: str) -> list:
    toks = []
    prev = None
    for ch in s:
        if ch in " \t":
            continue
        if ch in "+-*/()":
            toks.append(ch)
        elif "1" <= ch <= "9":
            if prev is not None and (prev.isdigit() or prev == ")"):
                raise ValueAnswer("数字需用运算符隔开，不允许拼数")
            toks.append(int(ch))
        else:
            raise ValueAnswer(f"非法字符：{ch!r}")
        prev = ch
    return toks


def _parse_answer(expr: str, cards: list) -> Fraction:
    toks = _tokenize(expr)
    if not toks:
        raise ValueAnswer("表达式为空")
    val, i = _parse_expr(toks, 0)
    if i != len(toks):
        raise ValueAnswer("表达式分隔/括号有误")
    nums = [t for t in toks if isinstance(t, int)]
    if sorted(nums) != sorted(cards):
        raise ValueAnswer("必须恰好使用每一张牌一次")
    return val


def _parse_expr(toks: list, i: int):
    val, i = _parse_term(toks, i)
    while i < len(toks) and toks[i] in "+-":
        op = toks[i]
        rhs, i = _parse_term(toks, i + 1)
        val = val + rhs if op == "+" else val - rhs
    return val, i


def _parse_term(toks: list, i: int):
    val, i = _parse_atom(toks, i)
    while i < len(toks) and toks[i] in "*/":
        op = toks[i]
        rhs, i = _parse_atom(toks, i + 1)
        if op == "*":
            val = val * rhs
        else:
            if rhs == 0:
                raise ValueAnswer("除法不能除以 0")
            val = val / rhs
    return val, i


def _parse_atom(toks: list, i: int):
    if i >= len(toks):
        raise ValueAnswer("表达式不完整")
    t = toks[i]
    if isinstance(t, int):
        return Fraction(t), i + 1
    if t == "(":
        val, i = _parse_expr(toks, i + 1)
        if i >= len(toks) or toks[i] != ")":
            raise ValueAnswer("括号不匹配")
        return val, i + 1
    raise ValueAnswer("表达式有误")


def _normalize_expr(expr: str) -> str:
    return expr.replace(" ", "")


# ---------- 可解性 / 求解提示（确定性枚举 5 种括号模板，Fraction 精确） ----------

_OP = "+-*/"
_BRACKETS = [
    ((0, 2), 0, (3, 2)),   # (a op b) op (c op d) 型，用索引占位
]


def _combine(a, b):
    res = [a + b, a - b, b - a, a * b]
    if b != 0:
        res.append(a / b)
    if a != 0:
        res.append(b / a)
    return res


def _all_values(nums) -> list:
    """枚举两两合并得到的所有分数值"""
    if len(nums) == 1:
        return nums
    out = []
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            rest = [nums[k] for k in range(len(nums)) if k != i and k != j]
            for v in _combine(nums[i], nums[j]):
                out.extend(_all_values([v] + rest))
    return out


def _p2(x, y, op):
    x = Fraction(x)
    y = Fraction(y)
    try:
        if op == "+":
            return x + y
        if op == "-":
            return x - y
        if op == "*":
            return x * y
        return x / y if y != 0 else None
    except ZeroDivisionError:
        return None


def _solve_seq(vals) -> dict | None:
    """返回一组可读解 {expr: "……"}，找不到返回 None"""
    from itertools import permutations, product

    def fmt(template, a, b, c, d, o1, o2, o3):
        return template.format(a=a, b=b, c=c, d=d, o1=o1, o2=o2, o3=o3)

    templates = [
        "({a}{o1}{b}){o3}({c}{o2}{d})",
        "{a}{o1}({b}{o3}({c}{o2}{d}))",
        "({a}{o1}({b}{o2}{c})){o3}{d}",
        "(({a}{o1}{b}){o2}{c}){o3}{d}",
        "{a}{o1}(({b}{o2}{c}){o3}{d})",
    ]
    for p in permutations(vals):
        a, b, c, d = p
        for o1, o2, o3 in product("+-*/", repeat=3):
            evals = [
                _p2(_p2(a, b, o1), _p2(c, d, o2), o3),   # (a·b)·(c·d)
                _p2(a, _p2(b, _p2(c, d, o2), o3), o1),   # a·(b·(c·d))
                _p2(_p2(a, _p2(b, c, o2), o3), d, o1),   # (a·(b·c))·d
                _p2(_p2(_p2(a, b, o1), c, o2), d, o3),   # ((a·b)·c)·d
                _p2(a, _p2(_p2(b, c, o2), d, o3), o1),   # a·((b·c)·d)
            ]
            for idx, t in enumerate(evals):
                if t is not None and t == 24:
                    return {"expr": fmt(templates[idx], a, b, c, d, o1, o2, o3)}