# -*- coding: utf-8 -*-
"""你画我猜：画手在 Canvas 上画（线条事件流广播），猜词者抢答；回合轮转。"""
import time

from games_pkg.base import BaseGame, GameRuleError

WORDS = [
    "笔记本电脑", "咖啡杯", "地铁", "火锅", "手机", "键盘", "红绿灯", "雨伞",
    "篮球", "眼镜", "自行车", "猫咪", "闹钟", "西瓜", "楼梯", "洗衣机",
    "望远镜", "公文包", "打印机", "微波炉", "水龙头", "插座", "台灯", "行李箱",
]


class DrawGuessGame(BaseGame):
    name = "drawguess"
    min_players = 2
    max_players = None

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.scores = {u: 0 for u in players}
        self.round = 0
        self.drawer_idx = 0
        self.phase = "drawing"          # drawing | round_end
        self.word = None
        self.strokes = []               # [{type,x1,y1,x2,y2,color,width}]
        self.guessed_by = None
        self.guess_log = []             # [{uid, text, ok}]
        self.round_end_at = 0.0
        self.gap = 3.0
        self.round_duration = 60.0      # 秒（可注入）
        self.round_start_at = time.time()
        self._start_round()

    def snapshot(self) -> dict:
        return {
            "game": self.name, "status": self.phase, "round": self.round,
            "drawer_uid": self.players[self.drawer_idx],
            "word_len": None if self.phase != "round_end" else len(self.word or ""),
            "word": self.word if self.phase == "round_end" else None,
            "strokes": list(self.strokes), "guessed_by": self.guessed_by,
            "guess_log": list(self.guess_log), "scores": dict(self.scores),
        }

    def private(self, uid: int):
        if self.phase == "drawing" and uid == self.players[self.drawer_idx] and self.word:
            return {"word": self.word, "hint": "你是画手，把这画出来让大家猜"}
        return None

    def act(self, uid: int, action: dict) -> list:
        if "stroke" in action:
            return self._stroke(uid, action["stroke"])
        if "clear" in action:
            return self._clear(uid)
        if "guess" in action:
            return self._guess(uid, action["guess"])
        raise GameRuleError("未知动作")

    def _start_round(self) -> list:
        self.round += 1
        self.drawer_idx = (self.drawer_idx + (1 if self.round > 1 else 0)) % len(self.players)
        self.phase = "drawing"
        self.word = self.rng.choice(WORDS)
        self.strokes = []
        self.guessed_by = None
        self.guess_log = []
        self.round_start_at = time.time()
        return [f"第 {self.round} 轮：{self._nick(self.players[self.drawer_idx])} 画画，大家抢猜"]

    def _stroke(self, uid: int, stroke: dict) -> list:
        if self.phase != "drawing" or uid != self.players[self.drawer_idx]:
            raise GameRuleError("只有画手能画画")
        if not isinstance(stroke, dict):
            raise GameRuleError("笔画数据非法")
        if len(self.strokes) > 2000:
            raise GameRuleError("笔画过多，请先清空")
        self.strokes.append(stroke)
        return []

    def _clear(self, uid: int) -> list:
        if self.phase != "drawing" or uid != self.players[self.drawer_idx]:
            raise GameRuleError("只有画手能清空")
        self.strokes = []
        return []

    def _guess(self, uid: int, text) -> list:
        if self.phase != "drawing":
            raise GameRuleError("当前不是猜词环节")
        if uid == self.players[self.drawer_idx]:
            raise GameRuleError("画手不能猜自己的词")
        text = str(text).strip()
        if not text:
            raise GameRuleError("猜测不能为空")
        if len(text) > 30:
            raise GameRuleError("猜测太长（≤30 字）")
        ok = text == self.word
        self.guess_log.append({"uid": uid, "text": text, "ok": ok})
        if ok:
            self.scores[uid] += 1
            self.guessed_by = uid
            self.phase = "round_end"
            self.round_end_at = time.time() + self.gap
            return [f"🎉 {self._nick(uid)} 猜中「{self.word}」！+1 分"]
        return [f"{self._nick(uid)} 猜「{text}」—— 不对哦"]

    def tick(self, now: float) -> list:
        if self.phase == "round_end" and now >= self.round_end_at:
            return self._start_round()
        if self.phase == "drawing" and now >= self.round_start_at + self.round_duration:
            # 超时：公布答案，轮换画手
            self.phase = "round_end"
            self.round_end_at = now + self.gap
            return [f"时间到！答案是「{self.word}」，无人猜中"]
        return []

    def ended(self):
        return None

    def _nick(self, uid: int) -> str:
        return f"玩家{uid}"
