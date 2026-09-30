# -*- coding: utf-8 -*-
"""谁是卧底：4+ 人文字社交推理。词库内置近义词对，1 卧底其余平民。"""
from games_pkg.base import BaseGame, GameRuleError

# (平民词, 卧底词)
WORD_PAIRS = [
    ("苹果", "梨子"), ("咖啡", "奶茶"), ("地铁", "公交"), ("火锅", "麻辣烫"),
    ("电影院", "剧院"), ("微信", "钉钉"), ("键盘", "鼠标"), ("衬衫", "T恤"),
    ("笔记本", "平板"), ("牙刷", "牙膏"), ("面包", "蛋糕"), ("柠檬", "橙子"),
    ("篮球", "排球"), ("钢琴", "吉他"), ("红绿灯", "路灯"), ("电梯", "扶梯"),
    ("空调", "风扇"), ("行李箱", "背包"), ("教学楼", "图书馆"), ("医生", "护士"),
    ("高铁", "飞机"), ("沙发", "床"), ("米饭", "面条"), ("QQ", "邮箱"),
]


class SpyGame(BaseGame):
    name = "spy"
    min_players = 4
    max_players = None

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.alive = list(players)
        self.scores = {u: 0 for u in players}
        self.phase = "dealing"            # dealing | describing | voting | checking | reveal
        self.spy_uid = None
        self.pair_idx = 0
        self.words = {}                    # uid -> 词
        self.speaker_idx = 0
        self.describes = []                # [{uid, text}]
        self.votes = {}                    # voter -> target
        self.eliminated_uid = None
        self.winner_uid = None
        self.loser_uid = None
        self._deal()

    def snapshot(self) -> dict:
        return {
            "game": self.name, "status": self.phase,
            "alive": list(self.alive), "players": list(self.players),
            "spy_uid": None if self.phase != "reveal" else self.spy_uid,
            "pair_idx": None if self.phase != "reveal" else self.pair_idx,
            "speaker_uid": self.alive[self.speaker_idx] if self.phase == "describing" else None,
            "describes": list(self.describes),
            "voted": sorted(self.votes.keys()),
            "vote_counts": self._vote_counts() if self.phase in ("checking", "reveal") else {},
            "eliminated_uid": self.eliminated_uid,
            "winner_uid": self.winner_uid,
            "scores": dict(self.scores),
        }

    def private(self, uid: int):
        if self.phase in ("dealing", "describing", "voting", "checking", "reveal"):
            w = self.words.get(uid)
            if w is not None:
                role = "spy" if uid == self.spy_uid else "civilian"
                return {"role": role, "word": w}
        return None

    def act(self, uid: int, action: dict) -> list:
        if "describe" in action:
            return self._describe(uid, action["describe"])
        if "vote" in action:
            return self._vote(uid, action["vote"])
        raise GameRuleError("未知动作")

    # ---- 开局 ----
    def _deal(self) -> list:
        self.pair_idx = self.rng.randrange(len(WORD_PAIRS))
        civilian_word, spy_word = WORD_PAIRS[self.pair_idx]
        self.spy_uid = self.rng.choice(self.alive)
        self.words = {}
        for u in self.alive:
            self.words[u] = spy_word if u == self.spy_uid else civilian_word
        self.phase = "describing"
        self.speaker_idx = 0
        self.describes = []
        return ["游戏开始：每人描述自己的词（不要说破！）"]

    def _describe(self, uid: int, text: str) -> list:
        if self.phase != "describing":
            raise GameRuleError("当前不是描述环节")
        if uid != self.alive[self.speaker_idx]:
            raise GameRuleError("还没轮到你描述")
        text = str(text).strip()
        if not text:
            raise GameRuleError("描述不能为空")
        if len(text) > 100:
            raise GameRuleError("描述太长（≤100 字）")
        self.describes.append({"uid": uid, "text": text})
        msgs = [f"{self._nick(uid)} 描述：{text}"]
        self.speaker_idx += 1
        if self.speaker_idx >= len(self.alive):
            self.phase = "voting"
            self.votes = {}
            msgs.append("描述完毕，开始投票（投给可疑的人，不能投自己）")
        return msgs

    def _vote(self, uid: int, target) -> list:
        if self.phase != "voting":
            raise GameRuleError("当前不是投票环节")
        if uid not in self.alive:
            raise GameRuleError("你已出局")
        if uid in self.votes:
            raise GameRuleError("你已投过票")
        try:
            target = int(target)
        except (TypeError, ValueError):
            raise GameRuleError("投票目标非法")
        if target not in self.alive or target == uid:
            raise GameRuleError("不能投自己或无效目标")
        self.votes[uid] = target
        if len(self.votes) == len(self.alive):
            return self._check()
        return []

    def _check(self) -> list:
        counts = self._vote_counts()
        max_votes = max(counts.values()) if counts else 0
        top = [u for u, c in counts.items() if c == max_votes]
        msgs = []
        if len(top) == 1:
            self.eliminated_uid = top[0]
            msgs.append(f"{self._nick(top[0])} 以 {max_votes} 票被投出局")
        else:
            self.eliminated_uid = None
            msgs.append(f"最高票平票（{len(top)} 人），本局无人出局")
        self.phase = "checking"
        if self.eliminated_uid is not None:
            self.alive.remove(self.eliminated_uid)
            self.words.pop(self.eliminated_uid, None)
        if self.spy_uid not in self.alive:
            self.winner_uid = None          # 平民胜（卧底被淘汰）
            self.loser_uid = self.spy_uid
            for u in self.alive:
                self.scores[u] += 1
            msgs.append("🎉 卧底被投出，平民获胜！")
            msgs.append(f"本轮词面：平民「{WORD_PAIRS[self.pair_idx][0]}」 vs 卧底「{WORD_PAIRS[self.pair_idx][1]}」")
            self.phase = "reveal"
        elif len(self.alive) <= 2:
            self.winner_uid = self.spy_uid
            self.loser_uid = None
            self.scores[self.spy_uid] += 1
            msgs.append("🕵️ 卧底成功潜伏到最后，卧底获胜！")
            msgs.append(f"本轮词面：平民「{WORD_PAIRS[self.pair_idx][0]}」 vs 卧底「{WORD_PAIRS[self.pair_idx][1]}」")
            self.phase = "reveal"
        else:
            msgs.append("卧底仍在场，进入下一轮描述")
            self.phase = "describing"
            self.speaker_idx = 0
            self.describes = []
            self.votes = {}
        return msgs

    def _vote_counts(self) -> dict:
        counts = {}
        for t in self.votes.values():
            counts[t] = counts.get(t, 0) + 1
        return counts

    def ended(self):
        if self.phase == "reveal":
            return {"winner_uid": self.winner_uid,
                    "detail": "平民胜" if self.winner_uid is None else "卧底胜"}
        return None

    def _nick(self, uid: int) -> str:
        return f"玩家{uid}"
