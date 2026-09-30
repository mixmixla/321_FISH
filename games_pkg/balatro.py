# -*- coding: utf-8 -*-
"""小丑牌（Balatro 多人版）· 生命值淘汰型 Roguelike 扑克。

玩法（多人回合制，贴合原作盲注/生命淘汰节奏）：
  每小局为一轮「盲注」。玩家按座位轮流行动。每名玩家手牌最多保留 8 张。
  起手每人抽满 8 张（牌库为 52 张标准牌，去大小王，抽空则洗回弃牌）。
  回合内玩家可（不限次数地）：
    - select cid : 把当前手牌里某张加入「出战」区（每回合最多选 5 张）
    - unselect cid: 从出战区移回手牌
    - discard cid : 弃掉手牌中一张（每回合最多 3 次弃牌，弃牌随机补一张，兑现「保留/重抽」策略）
    - play      : 结算一战。按出战区的 5 张算牌型（同花 / 顺子 / 同花顺 / 四条 / 葫芦 / 三张 / 两对 / 对子 / 高牌），
                  得分 = 牌型基础分 × (1 + 小丑牌特效加成)，回合玩家把得分累计到自己的「筹码」。
                  若筹码 ≥ 当前盲注底分（bind），该玩家过本盲注 → 回血并进入下一盲注；
                  否则掉命（-bind 伤害）。每人一个累计盲注进度，某个玩家的 blind 分数封顶后视为通关数最高者。
小丑牌特效（被动，进房时按最大人数随机发给每个玩家的卡池，每人手 2 张常驻）：
    贴在出战牌型上自动生效，常见特效如：
      - "对子王"：若含有对子，得分 ×2
      - "红心爱好者"：有红心牌时得分 +30
      - "顺子推进器"：是顺子时得分 ×3
      - "弃牌大师"：每多弃一张手牌，本局弃牌回补数 +1（操作型，可简化略过）
      - "黑桃猎人"：有黑桃时 +20
      - "五张同冲"：同花时 ×4
每局对局数 BLINDS 轮（默认 8 轮），全部盲注结束后比较各玩家「通关盲注数 + 剩余血量」总排名，最高者胜。
玩家血量从 40 开始，清 0 出局。只剩一名玩家时立即判胜；回合轮转跳过出局者。

snapshot / private：
  snapshot 公开：phase/turn/players/alive/score/手牌数量/bind 进度/每人血量。
  private(uid)：该玩家手牌列表（c=点数代码，用 2-9TJQKA，s=花色 hsdc），出战区 ids。
"""
from games_pkg.base import BaseGame, GameRuleError

RANKS = "23456789TJQKA"
SUITS = "hsdc"                 # 红桃/黑桃/方块/梅花
SUIT_CH = {"h": "♥", "s": "♠", "d": "♦", "c": "♣"}
START_HP = 40
BLINDS = 8
HAND_MAX = 8
PLAY_MAX = 5
DISCARD_MAX = 3
PLAYS_PER_BLIND = 2          # 每盲注每人最多出牌手数，打满即结算该盲注（防止无限轮转）
JOKERS_PER = 2

# 小丑牌特效：(id, 名字, 描述, 判定类型 effect_key, 参数)
# 覆盖多个乘法/加法维度；每个小丑牌另有 cost 与 rarity（见 JOKER_COST / JOKER_RARITY）。
JOKER_DEFS = {
    # ---- Type× 系列（牌型直接加倍）----
    "pair":     ("对子王", "打出对子时 得分×2", "pair", 2),
    "triple":   ("三条锋芒", "打出三条时 得分×3", "triple", 3),
    "flush":    ("同花狂热", "打出同花时 得分×3", "flush", 3),
    "straight": ("顺子推进", "打出顺子时 得分×3", "straight", 3),
    "sf":       ("同花顺神", "开出同花顺时 得分×5", "sf", 5),
    "full":     ("葫芦压阵", "开出葫芦时 得分×4", "full", 4),
    "four":     ("四条杀神", "开出四条时 得分×5", "four", 5),
    # ---- Suit× 系列（含某花色则×）----
    "heart_x":  ("红心领域", "出战含♥时 得分×2", "heart_x", 2),
    "spade_x":  ("黑桃锋芒", "出战含♠时 得分×2", "spade_x", 2),
    "diamond_x":("方块棱晶", "出战含♦时 得分×2", "diamond_x", 2),
    "club_x":   ("梅花壁垒", "出战含♣时 得分×2", "club_x", 2),
    # ---- 花色 +chips 系列（保留原 heart/spade，多维覆盖）----
    "heart":    ("红心暖手", "有♥时 +30 chips", "heart", 30),
    "spade":    ("黑桃猎手", "有♠时 +20 chips", "spade", 20),
    # ---- Type+Chips 系列（牌型加 chips）----
    "pairadd":  ("对子核心", "打出对子时 +30 chips", "pairadd", 30),
    "flushadd": ("同花洪流", "打出同花时 +90 chips", "flushadd", 90),
    "straightadd":("顺子疾风", "打出顺子时 +60 chips", "straightadd", 60),
    # ---- Card× 系列（含某点数则×）----
    "face":     ("脸牌大王", "出战含 J/Q/K 时 得分×3", "face", 3),
    # ---- 全局乘算 XMult ----
    "xmult":    ("万乘之灵", "所有牌型 得分×1.5", "xmult", 1.5),
    # ---- 成长型 ----
    "growth":   ("枯木逢春", "每冲破一个盲注 得分永久 ×1.1", "growth", 1.1),
    # ---- 弃牌加成 ----
    "discard":  ("弃牌回收", "本盲注每弃牌一次 +40 chips（可叠加）", "discard", 40),
    # ---- 高牌加成 ----
    "highcard": ("白手起家", "打出高牌时 +100 chips", "highcard", 100),
    # ---- 随机 ----
    "random":   ("命运骰子", "得分随机 ×2~×4", "random", 3),
}

# 小丑牌稀有度：common(白)/uncommon(青)/rare(金)
JOKER_RARITY = {
    "pair": "common", "triple": "common", "flush": "common", "straight": "common",
    "heart_x": "common", "spade_x": "common", "diamond_x": "common", "club_x": "common",
    "heart": "common", "spade": "common", "pairadd": "common",
    "full": "uncommon", "flushadd": "uncommon", "straightadd": "uncommon",
    "face": "uncommon", "discard": "uncommon", "random": "uncommon",
    "sf": "rare", "four": "rare", "xmult": "rare", "growth": "rare", "highcard": "rare",
}

# 小丑牌价值（cost，游玩未使用，仅供数据/展示参考）
JOKER_COST = {
    "pair": 30, "triple": 35, "flush": 35, "straight": 35,
    "heart_x": 30, "spade_x": 30, "diamond_x": 30, "club_x": 30,
    "heart": 25, "spade": 25, "pairadd": 25,
    "full": 90, "flushadd": 80, "straightadd": 80,
    "face": 100, "discard": 85, "random": 95,
    "sf": 180, "four": 160, "xmult": 200, "growth": 170, "highcard": 150,
}

# 开包/解锁抽取权重：common 高、rare 低
RARITY_WEIGHT = {"common": 4, "uncommon": 2, "rare": 1}

# 多人版（BalatroGame）仍只使用这 8 种基础特效，保证多人玩法数据不受单人新卡影响
CORE_JOKERS = {"pair", "flush", "straight", "sf", "four", "full", "heart", "spade"}

RARITY_CH = {"common": "白色·常见", "uncommon": "青色·进阶", "rare": "金色·稀有"}


class BalatroGame(BaseGame):
    name = "balatro"
    min_players = 2
    max_players = 6

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.players = list(players)
        self.phase = "play"          # 对局阶段（play 常驻，每轮到下一位）
        self.turn_idx = 0
        self.blind = 1               # 当前全局盲注序号（对局内逐轮上升）
        self.round_over = False      # 所有人生赢家已过/出局，进入下一盲注
        self.blind_base = 60         # 首盲注底分（随盲注递增 *1.4）
        self.winner = None
        self.detail = None
        self._hand = {}              # uid -> list[dict{c,s,id}]
        self._sel = {}               # uid -> list[id] 出战区
        self._discard_used = {}      # uid -> 本盲注已用弃牌次数（跨盲注重置）
        self._score = {}             # uid -> 当前盲注累计筹码
        self._cleared = {}           # uid -> 结算时是否过本盲注
        self._hp = {u: START_HP for u in players}
        self._out = set()
        self._jokers = {}            # uid -> list[id] 小丑牌
        self.deck = []               # 全牌池（未发）
        self._build_deck()
        self._assign_jokers()
        self._begin_round()

    # ---------- 初始 ----------
    def _build_deck(self):
        self.deck = [{"c": r, "s": s, "id": i}
                     for i, (r, s) in enumerate(
                         (r, s) for r in RANKS for s in SUITS)]
        self.rng.shuffle(self.deck)
        self.discard_pile = []

    def _assign_jokers(self):
        # 多人版只用 CORE_JOKERS（8 种基础特效），与旧逻辑完全一致
        pool = [j for j in JOKER_DEFS if j in CORE_JOKERS]
        for u in self.players:
            self.rng.shuffle(pool)
            self._jokers[u] = pool[:JOKERS_PER]

    def _draw(self, uid, n):
        got = []
        for _ in range(n):
            if not self.deck:
                if not self.discard_pile:
                    break
                self.deck = self.discard_pile
                self.discard_pile = []
                self.rng.shuffle(self.deck)
            card = self.deck.pop()
            card["id"] = card["id"]   # 保留唯一 id
            self._hand[uid].append(card)
            got.append(card)
        return got

    def _begin_round(self):
        """一轮盲注开局：清空出战/结算场，摸满 8 张。"""
        self.round_over = False
        self._sel = {u: [] for u in self.players}
        self._score = {u: 0 for u in self.players}
        self._cleared = {u: False for u in self.players}
        self._discard_used = {u: 0 for u in self.players}
        self._plays_used = {u: 0 for u in self.players}
        for u in self.players:
            if u in self._out:
                continue
            self._hand.setdefault(u, [])
            self._draw(u, HAND_MAX - len(self._hand[u]))
        self.turn_idx = 0
        self._skip_out()

    def _turn_uid(self):
        if not self.players:
            return None
        alive = [p for p in self.players if p not in self._out]
        if not alive:
            return None
        return self.players[self.turn_idx]

    def _skip_out(self):
        alive = [p for p in self.players if p not in self._out]
        if len(alive) <= 1:
            self._finalize()
            return
        for _ in range(len(self.players)):
            u = self.players[self.turn_idx]
            if u not in self._out:
                return
            self.turn_idx = (self.turn_idx + 1) % len(self.players)
        self._finalize()

    # ---------- 牌型 ----------
    def _rank_key(self, cards):
        return sorted([RANKS.index(c["c"]) for c in cards], reverse=True)

    def _hand_type(self, cards):
        """返回 (type_id, points, desc)。type_id 见 JOKER_DEFS 判定键。"""
        vals = sorted([RANKS.index(c["c"]) for c in cards], reverse=True)
        ctr = {}
        for v in vals:
            ctr[v] = ctr.get(v, 0) + 1
        groups = sorted(ctr.items(), key=lambda kv: (-kv[1], -kv[0]))
        flush = len({c["s"] for c in cards}) == 1
        straight = (vals[0] - vals[-1] == 4 and len(set(vals)) == 5) or \
                   set(vals) == {12, 3, 2, 1, 0}   # A2345 轮顺
        kinds = [g[1] for g in groups]
        is_sf = flush and straight
        if is_sf:
            return "sf", 80, "同花顺"
        if kinds == [4, 1]:
            return "four", 50, "四条"
        if kinds == [3, 2]:
            return "full", 35, "葫芦"
        if flush:
            return "flush", 25, "同花"
        if straight:
            return "straight", 20, "顺子"
        if kinds == [3, 1, 1]:
            return "triple", 15, "三条"
        if kinds.count(2) == 2:
            return "two_pair", 10, "两对"
        if kinds.count(2) == 1:
            return "pair", 5, "对子"
        return "high", 2, "高牌"

    def _apply_jokers(self, uid, type_id, base):
        """小丑牌特效叠加，返回 (final, effects_desc)。"""
        pts = base
        effs = []
        sel_ids = set(self._sel.get(uid, []))
        sel_cards = [c for c in self._hand.get(uid, []) if c["id"] in sel_ids]
        for jid in self._jokers.get(uid, []):
            _name, _desc, kind, val = JOKER_DEFS[jid]
            if kind in ("pair", "flush", "straight", "sf", "four", "full") \
               and type_id == kind:
                pts *= val
                effs.append(f"{_name}×{val}")
            elif kind == "heart":
                if any(c["s"] == "h" for c in sel_cards):
                    pts += val
                    effs.append(f"{_name}+{val}")
            elif kind == "spade":
                if any(c["s"] == "s" for c in sel_cards):
                    pts += val
                    effs.append(f"{_name}+{val}")
        return pts, effs

    # ---------- 动作 ----------
    def act(self, uid, action):
        if self.winner is not None:
            raise GameRuleError("本局已结束")
        if uid not in self._hand:
            raise GameRuleError("你不在这局")
        op = action.get("op")
        if op == "select":
            return self._select(uid, action)
        if op == "unselect":
            return self._unselect(uid, action)
        if op == "discard":
            return self._discard(uid, action)
        if op == "play":
            return self._play(uid)
        raise GameRuleError("未知操作")

    def _select(self, uid, action):
        cid = action.get("cid")
        if cid is None:
            raise GameRuleError("需指定要选中的牌")
        if uid in self._out:
            raise GameRuleError("你已出局")
        if uid != self._turn_uid():
            raise GameRuleError("还没轮到你")
        card = next((c for c in self._hand[uid] if c["id"] == cid), None)
        if card is None:
            raise GameRuleError("手牌中没有这张牌")
        if cid in self._sel[uid]:
            return []
        if len(self._sel[uid]) >= PLAY_MAX:
            raise GameRuleError(f"每次最多出战 {PLAY_MAX} 张")
        self._sel[uid].append(cid)
        return []

    def _unselect(self, uid, action):
        cid = action.get("cid")
        if uid in self._out:
            raise GameRuleError("你已出局")
        if uid != self._turn_uid():
            raise GameRuleError("还没轮到你")
        if cid in self._sel[uid]:
            self._sel[uid].remove(cid)
        return []

    def _discard(self, uid, action):
        cid = action.get("cid")
        if uid in self._out:
            raise GameRuleError("你已出局")
        if uid != self._turn_uid():
            raise GameRuleError("还没轮到你")
        if cid in self._sel[uid]:
            raise GameRuleError("出战中的牌请先取消选中")
        if self._discard_used.get(uid, 0) >= DISCARD_MAX:
            raise GameRuleError(f"每回合最多弃牌 {DISCARD_MAX} 次")
        card = next((c for c in self._hand[uid] if c["id"] == cid), None)
        if card is None:
            raise GameRuleError("手牌中没有这张牌")
        self._hand[uid].remove(card)
        self.discard_pile.append(card)
        self._discard_used[uid] = self._discard_used.get(uid, 0) + 1
        # 弃掉即补一张（保留/重抽）
        self._draw(uid, 1)
        return [f"🗑️ {self._nick(uid)} 弃牌一张并补抽（{self._discard_used.get(uid,0)}/{DISCARD_MAX}）"]

    def _play(self, uid):
        if uid in self._out:
            raise GameRuleError("你已出局")
        if uid != self._turn_uid():
            raise GameRuleError("还没轮到你")
        if len(self._sel[uid]) == 0:
            raise GameRuleError("请先选中要出战的牌")
        cards = [c for c in self._hand[uid] if c["id"] in self._sel[uid]]
        type_id, base, tname = self._hand_type(cards)
        pts, effs = self._apply_jokers(uid, type_id, base)
        self._score[uid] += pts
        self._plays_used[uid] = self._plays_used.get(uid, 0) + 1
        # 消耗出战牌：移出本回合手牌（不再回补，留待下盲注重发）
        for c in cards:
            self._hand[uid].remove(c)
            self.discard_pile.append(c)
        self._sel[uid] = []
        bind = self._target(uid)
        msgs = [f"🃏 {self._nick(uid)} 打出「{tname}」得 {pts}（累计 {self._score[uid]}）"]
        if effs:
            msgs.append("　🎭 " + " + ".join(effs))
        if self._score[uid] >= bind:
            self._cleared[uid] = True
            msgs.append(f"🎉 {self._nick(uid)} 过本盲注！（目标 {bind}）")
        else:
            dmg = (bind - self._score[uid]) // 25 or 1
            self._hp[uid] -= dmg
            msgs.append(f"⚔️ 未达目标 {bind}，流血 {dmg}")
            if self._hp[uid] <= 0:
                self._out.add(uid)
                msgs.append(f"☠️ {self._nick(uid)} 生命归零出局！")
        self._next_turn()
        return msgs

    # 每名玩家位置加成，但只轻微拉开差距，避免后座指数失控
    def _target(self, uid):
        seat = self.players.index(uid)
        seat_bonus = 1.0 + 0.12 * seat
        return int(self.blind_base * (self.blind ** 1.2) * seat_bonus)

    def _next_turn(self):
        # 收尾判定：存活者都结算完（本盲注出牌手数用尽）→ 进入下一盲注；只剩一人判胜
        alive = [p for p in self.players if p not in self._out]
        if len(alive) <= 1:
            self._finalize()
            return
        done = all(self._plays_used.get(u, 0) >= PLAYS_PER_BLIND
                   for u in alive)
        if done:
            self._round_clear()
            return
        self.turn_idx = (self.turn_idx + 1) % len(self.players)
        self._skip_out()

    def _round_clear(self):
        self.blind += 1
        # 补充一点血作为通过奖励
        for u in self.players:
            if u not in self._out:
                self._hp[u] = min(START_HP, self._hp[u] + 5)
        if self.blind > BLINDS:
            self._finalize()
            return
        self._begin_round()

    def _finalize(self):
        if self.winner is not None:
            return
        alive = [p for p in self.players if p not in self._out]
        if len(alive) == 1:
            self.winner = alive[0]
            self.detail = f"{self._nick(self.winner)} 存活到最后获胜"
            return
        # 否则按「存活血量」排名，血量最高者胜
        rank = sorted(self.players,
                      key=lambda u: (u not in self._out, self._hp[u]),
                      reverse=True)
        self.winner = rank[0]
        self.detail = f"{self._nick(self.winner)} 存活血量最高获胜"

    def snapshot(self):
        alive = [p for p in self.players if p not in self._out]
        return {
            "game": self.name,
            "phase": self.phase,
            "blind": self.blind,
            "players": list(self.players),
            "alive": alive,
            "turn": self._turn_uid(),
            "hand_size": {str(u): len(self._hand.get(u, [])) for u in self.players},
            "sel_size": {str(u): len(self._sel.get(u, [])) for u in self.players},
            "score": {str(u): self._score.get(u, 0) for u in self.players},
            "hp": {str(u): max(0, self._hp.get(u, 0)) for u in self.players},
            "cleared": {str(u): self._cleared.get(u, False) for u in self.players},
            "jokers": {str(u): [x for x in self._jokers.get(u, [])] for u in self.players},
            "turn_uid": self._turn_uid(),
            "winner": self.winner,
            "done": self.winner is not None,
        }

    def private(self, uid):
        if uid not in self._hand:
            return None
        return {
            "hand": [{"c": c["c"], "s": c["s"], "id": c["id"]}
                     for c in self._hand.get(uid, [])],
            "sel": list(self._sel.get(uid, [])),
        }

    def ended(self):
        if self.winner is None:
            return None
        return {"winner_uid": self.winner, "detail": self.detail or f"{self._nick(self.winner)} 获胜"}

    def _nick(self, uid):
        return f"玩家{uid}"


# =====================================================================
# 小丑牌 · 经典单人闯关（chips × mult 双轨计分，贴近原作 Balatro）
# =====================================================================
# 规则：
#   - 单人：每盲注目标分 target(n)=300*1.45^(n-1)，共 SOLO_BLINDS=8 关。
#   - 每盲注限出牌 SOLO_HANDS=4 手（摸满 8 张，选≤5 张出战，弃牌补抽 ≤3 次）。
#   - 计分：牌型给 (chips, mult)，小丑牌加成：牌型类 ×mult，花色类 +chips；
#     单次得分 = chips × mult，累计到本盲注总分。
#   - 总分 ≥ 目标 → 过关，进入下一盲注（并随机解锁 1 张新小丑牌，最多 5 张）；
#     未达标 → 扣 1 命（❤ 共 SOLO_LIVES=3）。命归零游戏结束，打通 8 关获胜。
SOLO_LIVES = 3
SOLO_HANDS = 4
SOLO_MAX_JOKERS = 5

# ---- 单人闯关·盲注节奏（1 Ante = 小盲→大盲→Boss 三连一组，替换纯 8 关直线）----
MAX_ANTES = 6                 # 最多 6 组（每组 3 盲注，共 18 桥）
BLIND_LAYERS = [              # (层名, 目标分倍率, key)
    ("小盲", 1, "small"),
    ("大盲", 1.6, "big"),
    ("BOSS", 2.2, "boss"),
]
# 过关奖金：小盲/大盲/Boss 各给多少金币（商店经济来源）
BLIND_DOLLARS = {"small": 3, "big": 4, "boss": 6}

# ---- 商店经济 ----
SOLO_START_DOLLARS = 4        # 开局金币
SOLO_CONS_SLOTS = 2           # 消耗品槽位上限
SHOP_REROLL_BASE = 3          # 商店刷新初始价，每次 +1
SHOP_JOKER_OFFER = 3          # 每次商店展示的小丑牌数
SHOP_CONS_OFFER = 2           # 每次商店展示的消耗品数
JOKER_COST_RARITY = {"common": 3, "uncommon": 5, "rare": 7}   # 商店小丑牌售价（按稀有度）
EDITION_COST_ADD = 2          # 带版本的小丑牌额外加价
INTEREST_RATE = 5             # 每持满 5 金币 +1 利息
INTEREST_CAP = 5              # 利息上限

# ---- 牌面强化/封印层（挂在每张牌上的可选修饰）----
EDITION_DEFS = {
    # id: (名称, 类型, 数值)  —— chips_add/mult_add 为加法，x_mult 为乘算
    "foil": ("箔饰", "edition", {"chip": 60}),
    "holo": ("全息", "edition", {"mult": 10}),
    "poly": ("多彩", "edition", {"x_mult": 2.0}),
}
ENH_DEFS = {
    "bonus": ("宝珠", "enhance", {"chip": 30}),        # +30 chips
    "mult":  ("曙光", "enhance", {"mult": 4}),          # +4 mult
    "face":  ("节庆", "enhance", {"face_mult": 2.0}),   # 面牌得分×2
    "glass": ("琉璃", "enhance", {"x_mult": 2.0, "break_p": 0.25}),  # ×2 但易碎
    "stone": ("磐石", "enhance", {"chip_fixed": 50}),  # 固定 +50 chips
    "steel": ("钢印", "enhance", {"x_mult_any": 1.5}), # 打出即×1.5
}
SEAL_DEFS = {
    "red":    ("赤印", "seal", {"replay": 1.25}),       # 出手 ×1.25
    "gold":   ("金印", "seal", {"cash": 3}),            # 过关 +3 金币
    "purple": ("紫印", "seal", {"mult": 2}),            # +2 mult
}

# ---- 消耗品池（Tarot 改造 / Planet 升牌型 / Spectral 高风险）----
# 每项：(id, 名称, 类别, 描述, 效果配置, 商店价)
CONS_DEFS = {
    "ct_bonus":  ("宝珠卷", "塔罗", "给一张手牌上『宝珠』增强", {"op": "enh", "enh": "bonus"}, 3),
    "ct_mult":   ("曙光卷", "塔罗", "给一张手牌上『曙光』增强", {"op": "enh", "enh": "mult"}, 3),
    "ct_face":   ("节庆卷", "塔罗", "给一张手牌上『节庆』增强", {"op": "enh", "enh": "face"}, 3),
    "ct_glass":  ("琉璃卷", "塔罗", "给一张手牌上『琉璃』增强", {"op": "enh", "enh": "glass"}, 4),
    "ct_foil":   ("箔之炼", "塔罗", "给一张手牌上『箔饰』版本", {"op": "edition", "edt": "foil"}, 4),
    "ct_holo":   ("全息术", "塔罗", "给一张手牌上『全息』版本", {"op": "edition", "edt": "holo"}, 4),
    "ct_strength": ("升阶", "塔罗", "一张手牌的点数 +1", {"op": "rank", "delta": 1}, 3),
    "cp_pair":   ("星辉·对子", "星球", "对子等级 +1", {"op": "level", "type": "pair"}, 3),
    "cp_flush":  ("星辉·同花", "星球", "同花等级 +1", {"op": "level", "type": "flush"}, 4),
    "cp_straight": ("星辉·顺子", "星球", "顺子等级 +1", {"op": "level", "type": "straight"}, 4),
    "cp_full":   ("星辉·葫芦", "星球", "葫芦等级 +1", {"op": "level", "type": "full"}, 5),
    "cs_grim":   ("冥狱", "灵体", "摧毁一张手牌→随机解锁一个小丑", {"op": "destroy_joker"}, 8),
    "cs_cash":   ("碎镜", "灵体", "摧毁全部手牌→+15 金币", {"op": "destroy_cash"}, 6),
    "cs_dupe":   ("双生", "灵体", "摧毁一张手牌→复制一张入下手牌", {"op": "destroy_dupe"}, 8),
}
CONS_CAT = {"塔罗": "改造", "星球": "升级", "灵体": "毁灭"}

# Boss 盲注池（每 Ante 的 Boss 轮换一个，debuff 只含禁花色/禁脸，复用单人_play 校验）
BOSS_POOL = [
    {"name": "铁锈", "kind": "suit_ban", "suit": "d", "debuff": "方块牌禁用"},
    {"name": "哑火", "kind": "face_ban", "debuff": "脸牌(J/Q/K)禁用"},
    {"name": "泄洪", "kind": "suit_ban", "suit": "h", "debuff": "红桃牌禁用"},
    {"name": "荆棘", "kind": "suit_ban", "suit": "c", "debuff": "梅花牌禁用"},
    {"name": "消音", "kind": "face_ban", "debuff": "脸牌(J/Q/K)禁用"},
    {"name": "封鞘", "kind": "suit_ban", "suit": "s", "debuff": "黑桃牌禁用"},
]

# 牌型等级加成（星球升级的单位涨幅）
LEVEL_CHIP = 10
LEVEL_MULT = 1

# 牌型 → (chips, mult) 基础值（原作风格）
HAND_CM = {
    "sf":    (100, 8),
    "four":  (60, 7),
    "full":  (40, 4),
    "flush": (35, 4),
    "straight": (30, 4),
    "triple": (30, 3),
    "two_pair": (20, 2),
    "pair":  (10, 2),
    "high":  (5, 1),
}

# 牌型 → 中文名（星球升级文案用）
HAND_CN = {
    "sf": "同花顺", "four": "四条", "full": "葫芦", "flush": "同花",
    "straight": "顺子", "triple": "三条", "two_pair": "两对",
    "pair": "对子", "high": "高牌",
}


class BalatroSoloGame(BalatroGame):
    """「小丑牌·单人闯关」——参考正版机制自创的完整版。

    1) 盲注节奏：1 Ante = 小盲(mult1) → 大盲(mult1.6) → BOSS(mult2.2) 三连一组循环，
       目标分 = 该 Ante 基础值 × 层倍率（替换原纯 8 关直线）。
    2) 牌面强化层：每张牌可挂 版本(edt)/增强(enh)/封印(seal) 之一，计分链先 +chips
       再 +mult 再 ×mult。
    3) 消耗品(2 槽)：塔罗改造手牌 / 星球升牌型等级 / 灵体高风险高回报。
    4) 商店经济：过关得金币 → 在两盲注之间进商店，可买 Joker/消耗品/刷新。
    """
    name = "balatro_solo"
    min_players = 1
    max_players = 1
    AMOUNTS = [300, 800, 2000, 5000, 11000, 20000, 35000, 50000]

    def __init__(self, players, seed=None):
        super().__init__(players, seed)   # 复用发牌/牌型/小丑牌/弃牌等
        self.lives = SOLO_LIVES
        self.hands_used = 0               # 本盲注已出牌手数
        self.passed = False               # 本盲注是否已达标
        self.boss = None                  # 当前 Boss（None 或 dict）
        self.is_boss = False
        self._growth_stack = 0            # 成长小丑牌累计过关层数
        self.dollars = SOLO_START_DOLLARS  # 金币（商店经济）
        self.shop_phase = False           # 是否处于两盲注之间的商店阶段
        self.shop_stock = None            # 商店货架（None 表示尚未开张）
        self._hand_level = {}             # 牌型 -> 等级（星球升级）
        self._cons = {u: [] for u in self.players}   # 消耗品（每人 ≤ SOLO_CONS_SLOTS）

    # ---------- 状态/节奏 ----------
    def _layer(self):
        """当前盲注属于小盲/大盲/BOSS 中的哪一层。"""
        return BLIND_LAYERS[(self.blind - 1) % 3]    # (名, mult, key)

    def _ante(self):
        return (self.blind - 1) // 3 + 1

    def _blind_base(self, ante):
        if ante <= len(self.AMOUNTS):
            return self.AMOUNTS[ante - 1]
        k = ante - len(self.AMOUNTS)
        return int(50000 * (1.6 + (0.75 * k) ** (1 + 0.2 * k)) ** k)

    def _blind_target(self):
        base = self._blind_base(self._ante())
        return int(base * self._layer()[1])

    def _solo_boss(self):
        layer_key = self._layer()[2]
        if layer_key != "boss":
            return None
        ante = self._ante()
        b = BOSS_POOL[(ante - 1) % len(BOSS_POOL)]
        return dict(b, ante=ante)

    def _assign_jokers(self):
        # 单人版：按稀有度加权抽取起手（common 权重高、rare 低），固定 2 张
        picks = self._weighted_draw(list(JOKER_DEFS), JOKERS_PER)
        for u in self.players:
            self._jokers[u] = list(picks)

    def _weighted_draw(self, pool, n, exclude=()):
        """按 rarity 权重（common 高 / rare 低）从 pool 抽 n 张，排除 exclude。"""
        pool = [j for j in pool if j not in exclude]
        picks = []
        for _ in range(n):
            if not pool:
                break
            weights = [RARITY_WEIGHT.get(JOKER_RARITY.get(j, "common"), 1)
                       for j in pool]
            total = sum(weights)
            r = self.rng.randrange(total)
            acc = 0
            for j, w in zip(pool, weights):
                acc += w
                if r < acc:
                    picks.append(j)
                    pool.remove(j)
                    break
        return picks

    def _select(self, uid, action):
        cid = action.get("cid")
        if cid is None:
            raise GameRuleError("需指定要选中的牌")
        if uid != self._turn_uid():
            raise GameRuleError("还没轮到你")
        card = next((c for c in self._hand[uid] if c["id"] == cid), None)
        if card is None:
            raise GameRuleError("手牌中没有这张牌")
        if cid in self._sel[uid]:
            return []
        if len(self._sel[uid]) >= PLAY_MAX:
            raise GameRuleError(f"每次最多出战 {PLAY_MAX} 张")
        boss = self.boss
        if boss:
            if boss.get("kind") == "suit_ban" and card["s"] == boss.get("suit"):
                raise GameRuleError(f"⚠ BOSS·{boss['name']}：{boss['debuff']}，此牌不能出战")
            if boss.get("kind") == "face_ban" and card["c"] in ("J", "Q", "K"):
                raise GameRuleError(f"⚠ BOSS·{boss['name']}：{boss['debuff']}，此牌不能出战")
        if self.shop_phase:
            raise GameRuleError("正处在商店阶段，先点「继续」进入下一盲注")
        self._sel[uid].append(cid)
        return []

    def act(self, uid, action):
        op = action.get("op")
        extra = {
            "next": lambda: self._next_blind(),
            "shop": lambda: self._open_shop(),
            "reroll": lambda: self._reroll(uid),
            "buy": lambda: self._buy(uid, action),
            "use": lambda: self._use_cons(uid, action),
        }
        handler = extra.get(op)
        if handler:
            return handler()
        return super().act(uid, action)

    def _turn_uid(self):
        return self.players[0] if self.players else None

    def _skip_out(self):
        return

    def _next_turn(self):
        # 单人：达标 → 进入商店阶段（等玩家点「继续」）；手数用尽未达标 → 扣命；命尽结束
        if self.winner is not None:
            return
        if self.passed:
            return                       # 已过关：等待 _next_blind 进入早报
        if self.hands_used >= SOLO_HANDS:
            self.lives -= 1
            if self.lives <= 0:
                self._finalize()
                return
            self._begin_round()          # 同盲注重来（保留 blind，重发牌）
            return

    def _on_pass(self, gold_cash):
        """过关奖励：发金币、成长层+1、随机解锁新小丑、开商店。"""
        uid = self.players[0]
        self.dollars += BLIND_DOLLARS[self._layer()[2]] + gold_cash
        if "growth" in self._jokers.get(uid, []):
            self._growth_stack += 1
        if len(self._jokers[uid]) < SOLO_MAX_JOKERS:
            new = self._weighted_draw(list(JOKER_DEFS), 1,
                                      exclude=self._jokers[uid])
            if new:
                self._jokers[uid].append(new[0])
        self.shop_phase = True
        self.shop_stock = self._gen_shop()

    # ---------- 商店经济 ----------
    def _gen_shop(self):
        uid = self.players[0]
        joks = []
        for jid in self._weighted_draw(list(JOKER_DEFS), SHOP_JOKER_OFFER,
                                       exclude=self._jokers[uid]):
            rar = JOKER_RARITY.get(jid, "common")
            price = JOKER_COST_RARITY.get(rar, 3)
            joks.append({"id": jid, "price": price, "sold": False,
                         "rarity": rar, "_nm": JOKER_DEFS[jid][0]})
        cons = []
        for cid in self.rng.sample(list(CONS_DEFS),
                                   min(SHOP_CONS_OFFER, len(CONS_DEFS))):
            _n, _cat, _d, _eff, price = CONS_DEFS[cid]
            cons.append({"id": cid, "price": price, "sold": False,
                         "cat": _cat, "_nm": _n})
        return {"jokers": joks, "cons": cons, "reroll_cost": SHOP_REROLL_BASE}

    def _open_shop(self):
        if self.winner is not None:
            raise GameRuleError("本局已结束")
        if self.shop_phase and self.shop_stock:
            return [f"🛒 商店已开张（金币 {self.dollars}），点「继续」进入下一盲注"]
        if not self.passed:
            return ["当前不是过关状态，无需逛商店"]
        self.shop_phase = True
        self.shop_stock = self._gen_shop()
        return [f"🛒 商店开张（金币 {self.dollars}）：可买 Joker/消耗品或点「继续」"]

    def _buy(self, uid, action):
        if self.winner is not None:
            raise GameRuleError("本局已结束")
        if not (self.shop_phase and self.shop_stock):
            raise GameRuleError("商店未开张")
        what = action.get("what")
        idx = action.get("idx")
        stock = self.shop_stock
        item = None
        if what == "joker":
            if not (0 <= idx < len(stock["jokers"])):
                raise GameRuleError("没有这格商品")
            item = stock["jokers"][idx]
        elif what == "cons":
            if not (0 <= idx < len(stock["cons"])):
                raise GameRuleError("没有这格商品")
            item = stock["cons"][idx]
        else:
            raise GameRuleError("未知商品类型")
        if item["sold"]:
            raise GameRuleError("该商品已被买走")
        if self.dollars < item["price"]:
            raise GameRuleError(f"金币不足（需 {item['price']}，现有 {self.dollars}）")
        if what == "joker":
            if len(self._jokers[uid]) >= SOLO_MAX_JOKERS:
                raise GameRuleError(f"小丑牌已满（{SOLO_MAX_JOKERS} 张）")
            self._jokers[uid].append(item["id"])
        else:
            if len(self._cons[uid]) >= SOLO_CONS_SLOTS:
                raise GameRuleError(f"消耗品已满（{SOLO_CONS_SLOTS} 槽）")
            self._cons[uid].append(item["id"])
        self.dollars -= item["price"]
        item["sold"] = True
        return [f"🛒 购入「{item['_nm']}」(-{item['price']}💰，剩余 {self.dollars}金币)"]

    def _reroll(self, uid):
        if self.winner is not None:
            raise GameRuleError("本局已结束")
        if not (self.shop_phase and self.shop_stock):
            raise GameRuleError("商店未开张")
        cost = self.shop_stock["reroll_cost"]
        if self.dollars < cost:
            raise GameRuleError(f"金币不足（刷新需 {cost}）")
        self.dollars -= cost
        self.shop_stock["reroll_cost"] += 1
        # 只重抽消耗品与 Joker（保留未买的已展示？原作另一套，此处直接整堆重抽）
        self.shop_stock["jokers"] = self._gen_shop()["jokers"]
        self.shop_stock["cons"] = self._gen_shop()["cons"]
        return [f"🔄 商店刷新(-{cost}💰，下次刷新 {self.shop_stock['reroll_cost']})"]

    def _next_blind(self):
        if self.winner is not None:
            raise GameRuleError("本局已结束")
        if not (self.shop_phase and self.shop_stock) and not self.passed:
            raise GameRuleError("当前不在商店/过关状态，无法继续")
        # 利息：每持满 INTEREST_RATE 金币 +1，上限 INTEREST_CAP
        interest = min(INTEREST_CAP, self.dollars // INTEREST_RATE)
        self.dollars += interest
        self.shop_phase = False
        self.shop_stock = None
        self.blind += 1
        if self.blind > MAX_ANTES * 3:
            self.winner = self.players[0]
            self.detail = "通关全部盲注，胜利！"
            return ["🏆 通关全部盲注，胜利！"]
        self._begin_round()
        return [f"🛒 商店结束（+{interest}💰利息，现有 {self.dollars}金币）→ 进入下一盲注"]

    # ---------- 消耗品 ----------
    def _use_cons(self, uid, action):
        if self.winner is not None:
            raise GameRuleError("本局已结束")
        if uid != self._turn_uid():
            raise GameRuleError("还没轮到你")
        if self.shop_phase:
            raise GameRuleError("商店阶段不能使用消耗品，先点「继续」")
        slot = action.get("slot")
        if not (0 <= slot < len(self._cons[uid])):
            raise GameRuleError("没有这个消耗品槽位")
        cid = self._cons[uid][slot]
        _name, cat, _desc, eff, _price = CONS_DEFS[cid]
        op = eff["op"]
        card = None
        tcid = action.get("cid")
        # Tarot：需选中手牌
        add = []
        if op in ("enh", "edition", "rank", "destroy_joker", "destroy_dupe"):
            if tcid is None:
                raise GameRuleError("这个效果需要给一张手牌指定目标")
            card = next((c for c in self._hand.get(uid, []) if c["id"] == tcid),
                        None)
            if card is None:
                raise GameRuleError("手牌中没有这张牌")
            if tcid in self._sel[uid]:
                raise GameRuleError("先取消选中该牌再使用消耗品")
        if op == "enh":
            card["enh"] = eff["enh"]
            add.append(f"✨ {_name}：{card['c']}{SUIT_CH[card['s']]} 获得『{ENH_DEFS[eff['enh']][0]}』增强")
        elif op == "edition":
            card["edt"] = eff["edt"]
            add.append(f"✨ {_name}：{card['c']}{SUIT_CH[card['s']]} 烙上『{EDITION_DEFS[eff['edt']][0]}』版本")
        elif op == "rank":
            idx = RANKS.index(card["c"])
            nv = max(0, min(len(RANKS) - 1, idx + eff["delta"]))
            card["c"] = RANKS[nv]
            card["v"] = nv
            add.append(f"📈 {_name}：{SUIT_CH[card['s']]}{card['c']} 点数 {'提升' if nv > idx else '不变'}（+{eff['delta']}）")
        elif op == "level":
            tp = eff["type"]
            self._hand_level[tp] = self._hand_level.get(tp, 1) + 1
            nm = HAND_CN.get(tp, tp)
            lvl = self._hand_level[tp]
            add.append(f"🌌 {_name}：{nm} 升到 Lv{lvl}（chips+{LEVEL_CHIP}, mult+{LEVEL_MULT}/级）")
        elif op == "destroy_joker":
            self._hand[uid].remove(card)
            new = self._weighted_draw(list(JOKER_DEFS), 1, exclude=self._jokers[uid])
            got = None
            if new and len(self._jokers[uid]) < SOLO_MAX_JOKERS:
                self._jokers[uid].append(new[0])
                got = new[0]
            add.append(f"💀 {_name}：摧毁 {card['c']}{SUIT_CH[card['s']]}，"
                       + (f"解锁小丑『{JOKER_DEFS[got][0]}』" if got else "（小丑已满，白损失）"))
        elif op == "destroy_cash":
            if not self._hand.get(uid):
                raise GameRuleError("手上没有牌可摧毁")
            self._hand[uid] = []
            self._sel[uid] = []
            self.dollars += 15
            add.append(f"💥 {_name}：摧毁全部手牌，+15💰（现有 {self.dollars}）")
        elif op == "destroy_dupe":
            self._hand[uid].remove(card)
            self._sel[uid] = [x for x in self._sel[uid] if x != tcid]
            self._draw(uid, 1)
            add.append(f"🔁 {_name}：摧毁 {card['c']}{SUIT_CH[card['s']]}，抽回一张新牌")
        del self._cons[uid][slot]
        return add or [f"使用了『{_name}』"]

    def _finalize(self):
        if self.winner is not None:
            return
        self.winner = None            # 单人失败 → done=True 但无胜者
        self.detail = "生命归零，本局结束"

    # ---------- 计分（chips × mult 双轨） ----------
    def _hand_type(self, cards):
        """返回 (type_id, desc)（复用父类判定，分数由 HAND_CM 查）。"""
        vals = sorted([RANKS.index(c["c"]) for c in cards], reverse=True)
        ctr = {}
        for v in vals:
            ctr[v] = ctr.get(v, 0) + 1
        groups = sorted(ctr.items(), key=lambda kv: (-kv[1], -kv[0]))
        flush = len({c["s"] for c in cards}) == 1
        straight = (vals[0] - vals[-1] == 4 and len(set(vals)) == 5) or \
                   set(vals) == {12, 3, 2, 1, 0}
        kinds = [g[1] for g in groups]
        is_sf = flush and straight
        if is_sf:
            return "sf", "同花顺"
        if kinds == [4, 1]:
            return "four", "四条"
        if kinds == [3, 2]:
            return "full", "葫芦"
        if flush:
            return "flush", "同花"
        if straight:
            return "straight", "顺子"
        if kinds == [3, 1, 1]:
            return "triple", "三条"
        if kinds.count(2) == 2:
            return "two_pair", "两对"
        if kinds.count(2) == 1:
            return "pair", "对子"
        return "high", "高牌"

    def _apply_jokers(self, uid, type_id, chips, mult):
        """单人版计分链：先算基础 chips×mult → 加法定值(cards/scaled)先加，
        倍率(mults)后乘，成长 XMult 最后永久累乘。返回 (chips, mult, effs)。"""
        effs = []
        sel_ids = set(self._sel.get(uid, []))
        sel_cards = [c for c in self._hand.get(uid, []) if c["id"] in sel_ids]
        rec_suit = {SUIT_CH[c["s"]] for c in sel_cards}
        has_face = any(c["c"] in ("J", "Q", "K") for c in sel_cards)
        disc_n = self._discard_used.get(uid, 0)
        adds, mults = [], []
        have_growth = False
        TYPE_X = {"pair", "triple", "flush", "straight", "sf", "full", "four"}
        for jid in self._jokers.get(uid, []):
            _name, _desc, kind, val = JOKER_DEFS[jid]
            if kind in ("heart", "spade", "diamond_c", "club_c"):
                if SUIT_CH[kind[0]] in rec_suit:
                    adds.append((_name, val))
            elif kind in TYPE_X and type_id == kind:
                mults.append((_name, val))
            elif kind in ("heart_x", "spade_x", "diamond_x", "club_x"):
                if SUIT_CH[kind[0]] in rec_suit:
                    mults.append((_name, val))
            elif kind == "pairadd" and type_id == "pair":
                adds.append((_name, val))
            elif kind == "flushadd" and type_id == "flush":
                adds.append((_name, val))
            elif kind == "straightadd" and type_id == "straight":
                adds.append((_name, val))
            elif kind == "highcard" and type_id == "high":
                adds.append((_name, val))
            elif kind == "discard":
                if disc_n:
                    adds.append((_name, val * disc_n))
            elif kind == "face" and has_face:
                mults.append((_name, val))
            elif kind == "xmult":
                mults.append((_name, val))
            elif kind == "random":
                rolled = self.rng.choice([2, 3, 4])
                mults.append((_name, rolled))
            elif kind == "growth":
                have_growth = True
        for _nm, v in adds:
            chips += v
            effs.append(f"{_nm}+{v}chips")
        for _nm, v in mults:
            mult *= v
            effs.append(f"{_nm}×{v}")
        if have_growth:
            g = 1.1 ** self._growth_stack
            if g > 1:
                mult *= g
                effs.append(f"枯木逢春×{g:.2f}")
        return chips, mult, effs

    def _score_card_mods(self, uid, cards):
        """聚合出战牌的 版本/增强/封印 加成。

        返回 (flat_chip, flat_mult, xmults, seals, glass_keys)
          - flat_chip/flat_mult：加法项，先于小丑牌计分加入
          - xmults：每张牌的乘算项 (来源名, 倍率)，乘于倍率阶段
          - seals：封印触发标记 {金印: 数量, 赤印: 数量, 紫印: 数量}
          - glass_keys：出战中被标记为琉璃的牌 id（算完分后可能碎裂）
        """
        flat_chip = flat_mult = 0
        xmults = []
        seals = {}
        glass = []
        face = {"J", "Q", "K"}
        for c in cards:
            cid = c.get("id")
            if c.get("enh") == "bonus":
                flat_chip += ENH_DEFS["bonus"][2]["chip"]
            elif c.get("enh") == "stone":
                flat_chip += ENH_DEFS["stone"][2]["chip_fixed"]
            elif c.get("enh") == "mult":
                flat_mult += ENH_DEFS["mult"][2]["mult"]
            elif c.get("enh") == "face":
                if c["c"] in face:
                    xmults.append(("节庆", ENH_DEFS["face"][2]["face_mult"]))
            if c.get("enh") == "glass":
                xmults.append(("琉璃", ENH_DEFS["glass"][2]["x_mult"]))
                glass.append(cid)
            elif c.get("enh") == "steel":
                xmults.append(("钢印", ENH_DEFS["steel"][2]["x_mult_any"]))
            if c.get("edt") == "foil":
                flat_chip += EDITION_DEFS["foil"][2]["chip"]
            elif c.get("edt") == "holo":
                flat_mult += EDITION_DEFS["holo"][2]["mult"]
            elif c.get("edt") == "poly":
                xmults.append(("多彩", EDITION_DEFS["poly"][2]["x_mult"]))
            if c.get("seal") == "red":
                seals["赤印"] = seals.get("赤印", 0) + 1
            elif c.get("seal") == "gold":
                seals["金印"] = seals.get("金印", 0) + 1
            elif c.get("seal") == "purple":
                flat_mult += SEAL_DEFS["purple"][2]["mult"]
        return flat_chip, flat_mult, xmults, seals, glass

    def _play(self, uid):
        if self.winner is not None:
            raise GameRuleError("本局已结束")
        if uid != self._turn_uid():
            raise GameRuleError("还没轮到你")
        if self.shop_phase:
            raise GameRuleError("当前是商店阶段，先点「继续」")
        if len(self._sel[uid]) == 0:
            raise GameRuleError("请先选中要出战的牌")
        cards = [c for c in self._hand[uid] if c["id"] in self._sel[uid]]
        type_id, tname = self._hand_type(cards)
        chips0, mult0 = HAND_CM[type_id]
        lvl = self._hand_level.get(type_id, 1)
        chips0 += LEVEL_CHIP * (lvl - 1)
        mult0 += LEVEL_MULT * (lvl - 1)
        # 牌面强化层（加法）先加
        fchip, fmult, xmults, seals, glass = self._score_card_mods(uid, cards)
        chips, mult = chips0 + fchip, mult0 + fmult
        effs = [tname, f"[Lv{lvl}]"]
        if fchip or fmult:
            effs.append(f"强化+{fchip}chips/+{fmult}mult")
        if seals.get("赤印"):
            xmults = list(xmults) + [("赤印", SEAL_DEFS["red"][2]["replay"])] * seals["赤印"]
        chips, mult, jeffs = self._apply_jokers(uid, type_id, chips, mult)
        effs += list(jeffs)
        # 乘算阶段（倍率先乘）
        for name, xmult in xmults:
            mult *= xmult
            effs.append(f"{name}×{xmult}")
        pts = int(chips * mult)
        self._score[uid] += pts
        self.hands_used += 1
        # 紫印加分已并入 fmult；金印奖金在过关时给
        gold_cash = seals.get("金印", 0) * SEAL_DEFS["gold"][2]["cash"]
        # 出手：琉璃等碎裂判定；普通牌进弃牌堆
        broken = set()
        for c in cards:
            self._hand[uid].remove(c)
            if c.get("enh") == "glass" and self.rng.random() < ENH_DEFS["glass"][2]["break_p"]:
                broken.add(c["id"])
                continue
            self.discard_pile.append(c)
        self._sel[uid] = []
        target = self.blind_target
        msgs = [f"🃏 打出「{tname}」 Lv{lvl} {chips0}chips×{mult0} → {chips}×{mult} = {pts}"
                f"（累计 {self._score[uid]}/{target}）"]
        if effs:
            msgs.append("　🎭 " + " + ".join(effs))
        if broken:
            msgs.append(f"　💔 琉璃碎裂销毁 {len(broken)} 张")
        if self._score[uid] >= target:
            self.passed = True
            self._on_pass(gold_cash)
            msgs.append(f"🎉 达标过关！+{BLIND_DOLLARS[self._layer()[2]] + gold_cash}💰"
                        f"（现有 {self.dollars}）进入商店，点「继续」开下一盲注")
        else:
            msgs.append(f"⏳ 还差 {target - self._score[uid]}（剩余手数 {SOLO_HANDS - self.hands_used}）")
        self._next_turn()
        return msgs

    def _begin_round(self):
        self.round_over = False
        self.passed = False
        self.hands_used = 0
        self.boss = self._solo_boss()
        self.is_boss = self.boss is not None
        self.blind_target = self._blind_target()
        self._sel = {u: [] for u in self.players}
        self._score = {u: 0 for u in self.players}
        self._cleared = {u: False for u in self.players}
        self._discard_used = {u: 0 for u in self.players}
        self._plays_used = {u: 0 for u in self.players}
        for u in self.players:
            self._hand.setdefault(u, [])
            self._draw(u, HAND_MAX - len(self._hand[u]))

    def snapshot(self):
        base = BalatroGame.snapshot(self)
        lk = self._layer()
        uid = self.players[0] if self.players else None
        s = dict(base)
        s.update({
            "lives": self.lives,
            "dollars": self.dollars,
            "shop_phase": self.shop_phase,
            "blind_ante": self._ante(),
            "blind_layer": lk[0],
            "blind_mult": lk[1],
            "max_blind": MAX_ANTES * 3,
            "blind_target": self.blind_target,
            "hands_used": self.hands_used,
            "hands_max": SOLO_HANDS,
            "hand_level": dict(self._hand_level),
            "cons": {str(u): list(self._cons.get(u, [])) for u in self.players},
            "passed": self.passed,
            "boss": self.boss,
            "boss_name": (self.boss or {}).get("name") if self.is_boss else None,
            "boss_debuff": (self.boss or {}).get("debuff") if self.is_boss else None,
            "is_boss": self.is_boss,
            "shop": None if not self.shop_stock else {
                "jokers": [{"id": x["id"], "price": x["price"], "rarity": x["rarity"],
                            "sold": x["sold"], "_nm": x["_nm"]} for x in self.shop_stock["jokers"]],
                "cons": [{"id": x["id"], "price": x["price"], "cat": x["cat"],
                          "sold": x["sold"], "_nm": x["_nm"]} for x in self.shop_stock["cons"]],
                "reroll_cost": self.shop_stock["reroll_cost"],
            },
        })
        return s

    def private(self, uid):
        hand = self._hand.get(uid, [])
        return {
            "hand": [{"id": c.get("id"), "c": c.get("c"), "s": c.get("s"),
                      "edt": c.get("edt"), "enh": c.get("enh"), "seal": c.get("seal")}
                     for c in hand],
            "sel": list(self._sel.get(uid, [])),
            "cons": list(self._cons.get(uid, [])),
        }

    def ended(self):
        if self.winner is None and self.lives <= 0:
            return {"winner_uid": None, "detail": self.detail or "生命归零，本局结束"}
        if self.winner is not None:
            return {"winner_uid": self.winner, "detail": self.detail}
        return None