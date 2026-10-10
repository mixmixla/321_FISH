# -*- coding: utf-8 -*-
"""通用动作层：认输 / 悔棋 / 求和（服务器权威，纯逻辑零 IO）。

以"组合代理"包裹棋类实例：拦截通用 op，其余动作透传原生规则，
并在每次成功动作前用 deepcopy 快照实现"悔棋"回滚。
未注册进 COMMON_ACTION_GAMES 的游戏不受影响。
"""
import copy

from games_pkg.base import GameRuleError

# 接入通用动作层的对弈类游戏（棋类 / 回合制对局）
COMMON_ACTION_GAMES = {
    "gomoku", "connect4", "othello", "tictactoe",
    "chess", "xiangqi", "shogi", "junqi", "dou",
    "go", "checkers", "halma", "ludo",
}

_HISTORY_CAP = 32           # 悔棋栈上限（步）

_COMMON_OPS = {"resign", "undo", "draw", "draw_accept", "draw_reject"}


class CommonActionsGame:
    """代理任意棋类实例，叠加 认输 / 悔棋 / 求和 通用动作。"""

    def __init__(self, game) -> None:
        self._g = game
        self._history: list = []        # 每次动作前的深拷贝快照
        self._resigned: list = []       # 已认输的 uid
        self._draw_offer = None         # 求和提议者 uid
        self._forced = None             # 通用动作产生的终局结果

    # ---- 未覆写的一切请求透传原生实例 ----
    _INTERNAL = frozenset({"_g", "_history", "_resigned", "_draw_offer", "_forced"})

    def __getattr__(self, name):
        return getattr(self._g, name)

    def __setattr__(self, name, value):     # 保证对棋局属性的写也透传（如测试直接改 dice）
        if name in self._INTERNAL:
            object.__setattr__(self, name, value)
        else:
            setattr(self._g, name, value)

    # ---- 动作 ----
    def act(self, uid: int, action: dict) -> list:
        op = (action or {}).get("op")
        if op in _COMMON_OPS:
            return getattr(self, "_" + op)(uid)
        pushed = self._push_history()
        try:
            return list(self._g.act(uid, action))
        except Exception:
            if pushed:                  # 动作失败：丢弃快照，保持历史一致
                self._history.pop()
            raise

    def _resign(self, uid: int) -> list:
        self._require_active(uid)
        if uid in self._resigned:
            raise GameRuleError("你已认输")
        self._resigned.append(uid)
        nick = self._nick(uid)
        active = [p for p in self.players if p not in self._resigned]
        if len(active) == 1:
            winner, detail = active[0], f"{nick} 认输，{self._nick(active[0])} 获胜"
        else:                           # 多人局亦直接结束，避免通用跳回合不可行
            winner, detail = None, f"{nick} 认输，本局结束"
        self._forced = {"winner_uid": winner, "detail": detail}
        return [f"🏳️ {detail}"]

    def _undo(self, uid: int) -> list:
        self._require_active(uid)
        if not self._history:
            raise GameRuleError("暂无可悔的棋")
        self._g = self._history.pop()
        return [f"♻ {self._nick(uid)} 悔棋，回退一步"]

    def _draw(self, uid: int) -> list:
        self._require_active(uid)
        if self._draw_offer is not None and self._draw_offer != uid:
            raise GameRuleError("已有求和提议待回应")
        self._draw_offer = uid
        return [f"🤝 {self._nick(uid)} 提议和棋，等待对手回应"]

    def _draw_accept(self, uid: int) -> list:
        self._require_active(uid)
        if self._draw_offer is None:
            raise GameRuleError("当前没有待回应的求和")
        if self._draw_offer == uid:
            raise GameRuleError("不能同意自己的求和")
        self._forced = {"winner_uid": None, "detail": "双方同意，和局"}
        return [f"🤝 {self._nick(self._draw_offer)} 与 {self._nick(uid)} 同意和棋"]

    def _draw_reject(self, uid: int) -> list:
        self._require_active(uid)
        if self._draw_offer is None:
            raise GameRuleError("当前没有待回应的求和")
        if self._draw_offer == uid:
            raise GameRuleError("不能拒绝自己的求和")
        self._draw_offer = None
        return [f"❌ {self._nick(uid)} 拒绝和棋"]

    # ---- 状态 ----
    def snapshot(self) -> dict:
        snap = dict(self._g.snapshot())
        if self._forced is not None:
            snap["winner_uid"] = self._forced["winner_uid"]
        snap["common"] = {
            "can_undo": bool(self._history) and self._forced is None,
            "draw_offer": self._draw_offer,
            "resigned": list(self._resigned),
            "ended": self._forced is not None,
            "detail": self._forced["detail"] if self._forced else None,
        }
        return snap

    def ended(self):
        if self._forced is not None:
            return dict(self._forced)
        return self._g.ended()

    # ---- 内部 ----
    def _require_active(self, uid: int) -> None:
        if self._forced is not None:
            raise GameRuleError("对局已结束")
        if uid not in self.players:
            raise GameRuleError("观战者不能操作")

    def _push_history(self) -> bool:
        """成功压入返回 True；不可深拷贝则返回 False（放弃回滚能力）。"""
        if self._forced is not None:
            return False
        try:
            snap = copy.deepcopy(self._g)
        except Exception:
            return False
        self._history.append(snap)
        if len(self._history) > _HISTORY_CAP:
            self._history.pop(0)
        return True

    def _nick(self, uid: int) -> str:
        try:
            return self._g._nick(uid)
        except Exception:
            return f"玩家{uid}"
