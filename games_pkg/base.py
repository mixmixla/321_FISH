# -*- coding: utf-8 -*-
"""游戏基类接口与规则错误（纯逻辑，零 IO）"""


class GameRuleError(Exception):
    """非法动作：服务器拒绝并回 game_error，状态不变"""


class BaseGame:
    """所有联机游戏的统一接口（服务器权威状态，客户端只渲染快照）。

    - players: 座位顺序的 uid 列表（加入顺序）
    - snapshot(): 公开状态 -> dict（广播给房间成员与观战者）
    - private(uid): 私密投递 -> dict 或 None（谁是卧底词面 / UNO 手牌）
    - act(uid, action): 处理玩家动作，返回系统消息行列表；非法抛 GameRuleError
    - tick(now): 服务器定时推进（超时/自动下一轮），返回消息行
    - ended(): 非 None 表示对局结束 -> {"winner_uid": int|None, "detail": str}
    - player_left(uid): 对局中玩家掉线时的善后（收发牌类并入他人），返回消息行
    """
    name = "base"
    min_players = 0
    max_players = None          # None = 不限

    def __init__(self, players, seed=None):
        self.players = list(players)
        self.rng = __import__("random").Random(seed)

    def snapshot(self) -> dict:
        raise NotImplementedError

    def private(self, uid: int):
        return None

    def act(self, uid: int, action: dict) -> list:
        raise GameRuleError("该游戏暂不可操作")

    def tick(self, now: float) -> list:
        return []

    def ended(self):
        return None

    def player_left(self, uid: int) -> list:
        """默认无需善后；收发牌类游戏可覆写并把手牌并入他人"""
        return []
