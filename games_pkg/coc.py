# -*- coding: utf-8 -*-
"""克苏鲁的呼唤（COC）规则判定器：KP 自由剧情 + 玩家 d100 技能检定。

角色体系：预设 6 张调查员卡，开局每人选一张（不重复）。
玩法核心：房主(players[0])作为 KP 推进场景，任一玩家随时发起技能检定，
按 COC 规则给出 大成功/极难成功/困难成功/普通成功/失败/大失败。
私密性：角色属性与技能值仅经 private() 私密可见；公开快照只公告
「某玩家对某技能检定→成功级别」与 KP 剧情消息。不强制回合，无自动终局。
"""
from games_pkg.base import BaseGame, GameRuleError

# —— 预设调查员卡：{id,name,emoji,attrs,desc,sig(常用技能与值)} ——
CHARS = [
    {"id": "det", "name": "侦探", "emoji": "🔍",
     "attrs": {"STR": 50, "DEX": 60, "POW": 60, "CON": 55, "INT": 75, "SIZ": 55},
     "desc": "观察入微，擅长盘问与现场推理。",
     "sig": {"侦查": 70, "聆听": 60, "图书馆使用": 65, "话术": 60, "手枪": 60, "心理学": 50}},
    {"id": "doc", "name": "医生", "emoji": "💉",
     "attrs": {"STR": 45, "DEX": 55, "POW": 65, "CON": 60, "INT": 70, "SIZ": 55},
     "desc": "冷静克制，精通医学与急救。",
     "sig": {"医学": 75, "急救": 70, "生物": 60, "心理学": 60, "潜行": 40}},
    {"id": "rep", "name": "记者", "emoji": "📰",
     "attrs": {"STR": 50, "DEX": 60, "POW": 55, "CON": 55, "INT": 70, "SIZ": 50},
     "desc": "口若悬河，擅长挖掘内幕。",
     "sig": {"摄影": 60, "话术": 70, "说服": 65, "图书馆使用": 60, "聆听": 60, "侦查": 50}},
    {"id": "nat", "name": "博物学家", "emoji": "🦋",
     "attrs": {"STR": 55, "DEX": 55, "POW": 60, "CON": 60, "INT": 70, "SIZ": 55},
     "desc": "跋山涉水，热衷自然与涉猎。",
     "sig": {"博物": 70, "追踪": 60, "潜行": 55, "手枪": 50, "急救": 50, "攀爬": 55}},
    {"id": "occ", "name": "神秘学家", "emoji": "🔮",
     "attrs": {"STR": 45, "DEX": 60, "POW": 80, "CON": 50, "INT": 75, "SIZ": 50},
     "desc": "涉猎禁忌，熟知古物与咒印。",
     "sig": {"神秘学": 75, "克苏鲁神话": 20, "图书馆使用": 60, "心理学": 50, "侦查": 50}},
    {"id": "arc", "name": "考古学家", "emoji": "⛏️",
     "attrs": {"STR": 55, "DEX": 50, "POW": 60, "CON": 65, "INT": 75, "SIZ": 60},
     "desc": "不畏险阻，精于勘察与器物。",
     "sig": {"考古学": 70, "历史": 65, "侦查": 60, "攀爬": 50, "锁匠": 45, "手枪": 55}},
]

_CHAR_BY_ID = {c["id"]: c for c in CHARS}


def check_level(roll: int, skill: int) -> str:
    """依据 COC 判定表给投出的 d100 一个成功级别。

    buy.get 大成功≤5(或1)/极难≤20/困难≤50/普通≤技能/大失败≥96且>技能/其余失败。
    """
    if not (0 <= roll <= 100):
        raise ValueError(f"d100 必须在 0~100 之间，收到 {roll}")
    if roll == 1 or roll <= 5:
        return "大成功"
    if roll <= 20:
        return "极难成功"
    if roll <= 50:
        return "困难成功"
    if roll <= skill:
        return "普通成功"
    if roll >= 96 and roll > skill:
        return "大失败"
    return "失败"


def roll_d100(rng):
    return rng.randint(1, 100)


def resolve_check(skill: int, rng) -> tuple:
    """掷 d100 并按技能值判定，返回 (roll, level)。skill 需为 int。"""
    roll = roll_d100(rng)
    return roll, check_level(roll, int(skill))


class CocGame(BaseGame):
    name = "coc"
    min_players = 2
    max_players = None

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.players = list(players)
        self.kp_uid = self.players[0]           # 房主即 KP
        self.phase = "setup"                     # setup(选卡) → play(自由剧情)
        self.chars = [dict(c) for c in CHARS]
        self.rng.shuffle(self.chars)             # 打乱可选卡池
        self.assigned = {}                       # uid -> card
        self.picked = set()                      # 已被选走的 card id
        self.scene = ""
        self.logs = []                           # 保留最近 N 条剧情/检定行
        self._log_max = 30
        self._ended = False

    # ---- 公开快照 ----
    def snapshot(self):
        return {
            "game": self.name, "phase": self.phase, "kp_uid": self.kp_uid,
            "players": list(self.players),
            "picked": {u: cid for u, cid in
                       ((u, c["id"]) for u, c in self.assigned.items())},
            "scene": self.scene,
            "logs": list(self.logs),
        }

    def private(self, uid):
        if uid not in self.players:
            return None
        if self.phase == "setup":
            # 只用 id/名字/emoji/简介，不泄露属性与技能值（选卡用）
            deck = [{"id": c["id"], "name": c["name"], "emoji": c["emoji"],
                     "desc": c["desc"]} for c in self.chars]
            return {"deck": deck}
        if self.phase == "play" and uid in self.assigned:
            c = self.assigned[uid]
            return {"card": {"id": c["id"], "name": c["name"], "emoji": c["emoji"],
                             "attrs": dict(c["attrs"]), "sig": dict(c["sig"])}}
        return None

    # ---- 动作分发 ----
    def act(self, uid, action):
        if self._ended:
            raise GameRuleError("本局已结束")
        if uid not in self.players:
            raise GameRuleError("尚未加入对局")
        op = action.get("op")
        if self.phase == "setup":
            if op == "choose_card":
                return self._choose(uid, action)
            if op == "begin":
                return self._begin(uid)
            raise GameRuleError("选卡阶段可选卡或开始")
        # play
        if op == "check":
            return self._check(uid, action)
        if op == "set_scene" and uid == self.kp_uid:
            return self._set_scene(uid, action)
        if op == "end" and uid == self.kp_uid:
            return self._end(uid)
        if op in ("set_scene", "end"):
            raise GameRuleError("只有 KP 能操作剧情")
        raise GameRuleError("未知操作")

    # ---- 选卡 ----
    def _choose(self, uid, action):
        if uid in self.assigned:
            raise GameRuleError("你已经选过调查员了")
        cid = action.get("card_id")
        card = _CHAR_BY_ID.get(cid)
        if not card:
            raise GameRuleError(f"未知的调查员卡: {cid}")
        if cid in self.picked:
            raise GameRuleError("该调查员已被选走")
        self.assigned[uid] = card
        self.picked.add(cid)
        self._log(f"🔰 {self._nick(uid)} 选择了 {card['emoji']}{card['name']}")
        return [f"🔰 {self._nick(uid)} 选了 {card['emoji']}{card['name']}"]

    def _begin(self, uid):
        if uid != self.kp_uid:
            raise GameRuleError("只有 KP 能开始调查")
        missing = [u for u in self.players if u not in self.assigned]
        if missing:
            raise GameRuleError(f"还有 {len(missing)} 人未选调查员")
        self.phase = "play"
        self._log("🎭 调查开始，请 KP 讲述场景，玩家可随时发起检定")
        return ["🎭 调查开始！KP 请描述场景，玩家可随时发起技能检定（check 技能名）"]

    # ---- 检定 ----
    def _check(self, uid, action):
        if uid not in self.assigned:
            raise GameRuleError("你还没有调查员卡")
        card = self.assigned[uid]
        skill = action.get("skill")
        base = action.get("base")
        if isinstance(skill, str):
            val = card["sig"].get(skill)
            if val is None:
                # 允许检定任意已知技能；未列出的按 base 或 50
                val = int(base) if base is not None and str(base).lstrip("-").isdigit() else 50
        else:
            val = int(base) if base is not None and str(base).lstrip("-").isdigit() else 50
        roll, level = resolve_check(val, self.rng)
        skill_label = skill if isinstance(skill, str) else f"技能{val}"
        line = f"🎲 {self._nick(uid)} 对「{skill_label}」检定 → {level}"
        self._log(line)
        return [line]

    # ---- KP 剧情 ----
    def _set_scene(self, uid, action):
        scene = action.get("scene", "").strip()
        if not scene:
            raise GameRuleError("场景内容为空")
        self.scene = scene
        self._log(f"[场景] {scene}")
        return [f"🗒️ KP 更新场景：{scene}"]

    def _end(self, uid):
        if uid != self.kp_uid:
            raise GameRuleError("只有 KP 能结束调查")
        self._ended = True
        self._log("🏁 调查结束")
        return ["🏁 KP 宣布调查结束"]

    def tick(self, now):
        return []

    def ended(self):
        if not self._ended:
            return None
        return {"winner_uid": self.kp_uid, "detail": "COC 自由剧情由 KP 收尾"}

    def player_left(self, uid):
        if uid not in self.players:
            return []
        msgs = [f"{self._nick(uid)} 离开了游戏"]
        self.players.remove(uid)
        if uid in self.assigned:
            c = self.assigned.pop(uid)
            self.picked.discard(c["id"])
            # 选卡阶段把卡放回卡池，供他人再选
            if self.phase == "setup":
                self._log(f"↩️ {c['name']} 卡回到牌堆")
        if uid == self.kp_uid and self.players:
            self.kp_uid = self.players[0]
            self._log(f"🕰️ KP 移交给了 {self._nick(self.kp_uid)}")
        if len(self.players) < self.min_players:
            self._ended = True
            msgs.append("剩余玩家人数不足，对局结束")
        return msgs

    # ---- 内部 ----
    def _nick(self, uid):
        return f"玩家{uid}"

    def _log(self, msg):
        self.logs.append(msg)
        if len(self.logs) > self._log_max:
            self.logs = self.logs[-self._log_max:]