# -*- coding: utf-8 -*-
"""游戏房间与房间管理（纯逻辑，服务器权威；锁由调用方负责）。

生命周期：CREATED(大厅) -> PLAYING(开赛) -> ENDED(结算) -> 回 CREATED
观战者只收 game_state，动作一律拒绝；owner 离场自动移交或关房。
"""
import itertools
import threading
import time
from enum import Enum

from games_pkg.base import BaseGame, GameRuleError


class RoomStatus(str, Enum):
    CREATED = "created"
    PLAYING = "playing"
    ENDED = "ended"


class Room:
    def __init__(self, room_id: str, game_cls, owner_uid: int) -> None:
        self.room_id = room_id
        self.game_cls = game_cls
        self.game_name = game_cls.name
        self.owner_uid = owner_uid
        self.status = RoomStatus.CREATED
        self.players: list = []          # 座位顺序
        self.spectators: set = set()
        self.scores: dict = {}           # 跨轮累计
        self.gs: BaseGame | None = None  # 当前对局
        self.created_at = time.time()
        self.round_no = 0

    @property
    def members(self) -> list:
        return self.players + sorted(self.spectators)

    def summary(self) -> dict:
        return {
            "room_id": self.room_id, "game": self.game_name,
            "status": self.status.value,
            "owner_uid": self.owner_uid, "players": list(self.players),
            "spectators": sorted(self.spectators), "round": self.round_no,
        }


class RoomManager:
    def __init__(self, registry: dict, clock=time.time, tick_now=None) -> None:
        """registry: {game_name: GameClass}"""
        self.registry = registry
        self._clock = clock
        self._tick_now = tick_now or (lambda: clock())
        self.rooms: dict = {}
        self._seq = itertools.count(1)
        self.lock = threading.RLock()

    # ---- 生命周期 ----
    def create(self, uid: int, game: str) -> Room:
        with self.lock:
            if game not in self.registry:
                raise GameRuleError(f"未知游戏: {game}")
            room_id = f"g{next(self._seq)}"
            room = Room(room_id, self.registry[game], uid)
            room.players.append(uid)
            self.rooms[room_id] = room
            return room

    def join(self, uid: int, room_id: str) -> Room:
        with self.lock:
            room = self._get(room_id)
            if uid in room.players or uid in room.spectators:
                raise GameRuleError("已在房间中")
            if room.status == RoomStatus.PLAYING:
                raise GameRuleError("对局进行中，请观战或等待")
            if room.game_cls.max_players and len(room.players) >= room.game_cls.max_players:
                room.spectators.add(uid)
            else:
                room.players.append(uid)
            return room

    def spectate(self, uid: int, room_id: str) -> Room:
        with self.lock:
            room = self._get(room_id)
            if uid in room.players:
                raise GameRuleError("你已是玩家")
            room.spectators.add(uid)
            return room

    def leave(self, uid: int, room_id: str) -> bool:
        """返回 True 表示房间可关闭（无人）"""
        return bool(self.leave_detail(uid, room_id)["closed"])

    def leave_detail(self, uid: int, room_id: str) -> dict:
        """移除成员并返回公共生命周期细节；``leave`` 的 bool API 保持不变。"""
        with self.lock:
            room = self.rooms.get(room_id)
            if not room:
                return {"room_id": room_id, "room": None, "closed": True,
                        "events": [], "ended": None, "gs": None,
                        "round_no": None}
            events = []
            ended = None
            captured_gs = room.gs
            captured_round = room.round_no
            if uid in room.players:
                in_game = (room.status == RoomStatus.PLAYING
                           and room.gs is not None)
                if in_game:
                    events = list(room.gs.player_left(uid) or [])
                    ended = room.gs.ended()
                room.players.remove(uid)
                # A rule without native player_left/ended support is stopped at
                # the public lifecycle layer once it falls below min_players;
                # no winner or reward is invented.
                if in_game and ended is None and \
                        len(room.players) < room.game_cls.min_players:
                    events.append(f"💨 玩家{uid} 离开，对局中止")
                    ended = {"winner_uid": None, "detail": "玩家离开，对局中止"}
            room.spectators.discard(uid)
            if not room.players and not room.spectators:
                del self.rooms[room_id]
                return {"room_id": room_id, "room": room, "closed": True,
                        "events": events, "ended": ended, "gs": captured_gs,
                        "round_no": captured_round}
            if uid == room.owner_uid and room.players:
                room.owner_uid = room.players[0]
            return {"room_id": room_id, "room": room, "closed": False,
                    "events": events, "ended": ended, "gs": captured_gs,
                    "round_no": captured_round}

    def start(self, uid: int, room_id: str) -> Room:
        with self.lock:
            room = self._get(room_id)
            if uid != room.owner_uid:
                raise GameRuleError("只有房主能开始")
            if room.status != RoomStatus.CREATED:
                raise GameRuleError("当前对局尚未回到大厅，不能再次开始")
            if len(room.players) < room.game_cls.min_players:
                raise GameRuleError(
                    f"至少需要 {room.game_cls.min_players} 人"
                    f"（当前 {len(room.players)} 人，其余可点观战）")
            room.gs = room.game_cls(room.players, seed=self._seed_for(room))
            room.status = RoomStatus.PLAYING
            room.round_no += 1
            return room

    def handle_action(self, uid: int, room_id: str, action: dict) -> list:
        """处理动作：返回系统消息行（广播用）；观战/无局/非法均拒绝"""
        with self.lock:
            room = self._get(room_id)
            if uid not in room.players:
                raise GameRuleError("观战者不能操作")
            if room.status != RoomStatus.PLAYING or room.gs is None:
                raise GameRuleError("对局未开始")
            return list(room.gs.act(uid, action))

    def tick(self) -> list:
        """服务器定时推进：推进所有进行中房间，返回全局消息行"""
        with self.lock:
            out = []
            now = self._tick_now()
            for room in list(self.rooms.values()):
                if room.status == RoomStatus.PLAYING and room.gs is not None:
                    out.extend(room.gs.tick(now))
            return out

    def on_disconnect(self, uid: int) -> list:
        """玩家掉线：剔除并清空空房；对局中先 do 游戏善后；返回受影响房间"""
        return [d["room_id"] for d in self.on_disconnect_detail(uid)]

    def on_disconnect_detail(self, uid: int) -> list:
        """断线 detail 版本；保留 ``on_disconnect`` 的 room-id 返回 API。"""
        with self.lock:
            affected = []
            for room in list(self.rooms.values()):
                if uid in room.players or uid in room.spectators:
                    affected.append(self.leave_detail(uid, room.room_id))
            return affected

    def list_rooms(self) -> list:
        with self.lock:
            return [r.summary() for r in self.rooms.values()]

    def room_for(self, room_id: str) -> Room | None:
        with self.lock:
            return self.rooms.get(room_id)

    # ---- 内部 ----
    def _get(self, room_id: str) -> Room:
        room = self.rooms.get(room_id)
        if room is None:
            raise GameRuleError(f"房间不存在: {room_id}")
        return room

    def _seed_for(self, room: Room) -> int:
        """可复现种子：房间 id + 轮次"""
        try:
            idx = int(room.room_id[1:])
        except ValueError:
            idx = 1
        return idx * 1000 + room.round_no
