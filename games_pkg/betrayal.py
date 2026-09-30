# -*- coding: utf-8 -*-
"""山屋惊魂（简化版）：探索 → 预兆 → 惊魂（叛徒对决），服务器权威纯逻辑。

探索阶段：每人每回合按速度在网格地图上开门探索，首次进入新房间抽一张牌
——事件（随机祸福）/ 物品（道具）/ 预兆（属性 +1 并做惊魂检定）。
惊魂检定：掷 d6，点数 ≤ 已抽预兆数即惊魂降临。
惊魂阶段：力量最高者被山屋附身成为叛徒（公开身份，力量 +2），
出口之门在远处显现。叛徒击杀全部幸存者获胜；
幸存者击杀叛徒，或全员抵达出口之门一起撤离获胜。
任意属性归 0 角色死亡，掉线视为死亡。
"""
from games_pkg.base import BaseGame, GameRuleError

STAT_CN = {"might": "力量", "speed": "速度", "sanity": "理智", "knowledge": "知识"}
DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
DIR_CN = {"up": "北", "down": "南", "left": "西", "right": "东"}

ROOM_SHORT = {
    "门厅": "门", "大厅": "厅", "起居室": "居", "餐厅": "餐", "厨房": "厨",
    "储物间": "储", "书房": "书", "图书馆": "图", "台球室": "台", "温室": "温",
    "花房": "花", "车库": "车", "地窖": "窖", "礼拜堂": "礼", "病房": "病",
    "育儿室": "育", "主卧": "卧", "浴室": "浴", "琴房": "琴", "阁楼": "阁",
    "出口之门": "出",
}
ROOM_NAMES = [n for n in ROOM_SHORT if n != "出口之门"]     # 19 张房间牌（门厅开局已放）

ITEM_DECK = ["消防斧", "急救包", "镇静剂", "光之水晶", "力量护符", "圣水"]
EVENT_DECK = {
    "寒气入骨": ("sanity", -1, "一阵寒气从脚底窜上脊背"),
    "血字浮现": ("knowledge", -1, "墙上渗出暗红血字，看得头晕目眩"),
    "地板坍塌": ("speed", -1, "脚下地板突然塌陷，爬出来时崴了脚"),
    "幽灵低语": ("sanity", +1, "幽灵的低语反而让你心神安定"),
    "古老医书": ("knowledge", +1, "你读懂了一本古老医书的残页"),
    "热血沸腾": ("might", +1, "一股热血涌上心头，握紧了拳头"),
    "意外的馈赠": (None, 0, "抽屉里藏着前人落下的东西"),
    "暗门": (None, 0, "书架后藏着一扇暗门"),
}
OMEN_DECK = [
    ("晶球", "knowledge"), ("会吹口哨的猫", "speed"), ("疯人院手册", "sanity"),
    ("蛇符", "might"), ("死亡面具", "sanity"), ("符文石板", "knowledge"),
    ("少女雕像", "might"), ("骨之骰", "speed"),
]


class BetrayalGame(BaseGame):
    name = "betrayal"
    min_players = 3
    max_players = 6

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.phase = "explore"              # explore -> haunt
        self.stats = {u: {"might": 3, "speed": 3, "sanity": 3, "knowledge": 3}
                      for u in players}
        self.pos = {u: (0, 0) for u in players}
        self.items = {u: [] for u in players}
        self.holy = set()                   # 饮下圣水者：下一次攻击 +2
        self.dead = set()
        self.room_map = {(0, 0): "门厅"}     # 已揭示房间
        kinds = ["event"] * 8 + ["omen"] * 6 + ["item"] * 5
        self.rng.shuffle(kinds)
        rooms = list(ROOM_NAMES)
        self.rng.shuffle(rooms)
        self.tiles = list(zip(rooms, kinds))    # 探索时从末尾弹出
        self.item_deck = list(ITEM_DECK)
        self.rng.shuffle(self.item_deck)
        self.event_deck = list(EVENT_DECK)
        self.rng.shuffle(self.event_deck)
        self.omen_deck = list(OMEN_DECK)
        self.rng.shuffle(self.omen_deck)
        self.omens = 0
        self.haunt = None                   # {"traitor": uid, "exit": (x,y), "scenario": str}
        self._result = None                 # ("survivors"|"traitor", 原因)
        self.turn_idx = 0
        self.steps_left = self.stats[players[0]]["speed"]
        self.attack_used = False

    # ---------- 快照 / 私密 ----------
    def snapshot(self) -> dict:
        return {
            "game": self.name, "status": "playing",
            "phase": self.phase, "omens": self.omens,
            "turn_uid": self.players[self.turn_idx] if self.players else None,
            "steps_left": self.steps_left,
            "players": list(self.players),
            "alive": sorted(u for u in self.players if u not in self.dead),
            "dead": sorted(self.dead & set(self.players)),
            "seats": {str(u): i + 1 for i, u in enumerate(self.players)},
            "pos": {str(u): f"{x},{y}" for u, (x, y) in self.pos.items()},
            "rooms": {f"{x},{y}": ROOM_SHORT.get(n, n[0])
                      for (x, y), n in self.room_map.items()},
            "stats": {str(u): dict(self.stats[u]) for u in self.players},
            "items": {str(u): list(self.items[u]) for u in self.players},
            "haunt": (None if not self.haunt else {
                "traitor": self.haunt["traitor"],
                "exit": f"{self.haunt['exit'][0]},{self.haunt['exit'][1]}",
                "scenario": self.haunt["scenario"],
            }),
        }

    def private(self, uid: int):
        if uid not in self.stats:
            return None
        x, y = self.pos[uid]
        traitor = (self.haunt or {}).get("traitor")
        return {
            "stats": dict(self.stats[uid]),
            "items": list(self.items[uid]),
            "pos": f"{x},{y}",
            "room": self.room_map.get((x, y), "未知"),
            "side": "⚡叛徒" if uid == traitor else "幸存者",
        }

    # ---------- 动作 ----------
    def act(self, uid: int, action: dict) -> list:
        if self.ended():
            raise GameRuleError("本局已结束，请开新局")
        if not self.players or uid != self.players[self.turn_idx]:
            raise GameRuleError("还没轮到你")
        if "move" in action:
            return self._move(uid, str(action["move"]))
        if "use" in action:
            return self._use(uid, str(action["use"]))
        if "attack" in action:
            return self._attack(uid, int(action["attack"]))
        if action.get("escape"):
            return self._escape(uid)
        if action.get("end"):
            return self._end_turn([f"{self._nick(uid)} 结束回合"])
        raise GameRuleError("未知动作")

    def _move(self, uid: int, d: str) -> list:
        if d not in DIRS:
            raise GameRuleError("方向只能是 up/down/left/right")
        if self.steps_left <= 0:
            raise GameRuleError("步伐已用尽，请结束回合")
        x, y = self.pos[uid]
        dx, dy = DIRS[d]
        t = (x + dx, y + dy)
        msgs = []
        if t not in self.room_map:
            if not self.tiles:
                raise GameRuleError("门后是沉重的墙壁——山屋已无可探索的房间")
            name, kind = self.tiles.pop()
            self.room_map[t] = name
            msgs.append(f"{self._nick(uid)} 推开{DIR_CN[d]}侧的门，发现【{name}】")
            msgs += self._draw(uid, kind)
        else:
            msgs.append(f"{self._nick(uid)} 走进【{self.room_map[t]}】")
        self.pos[uid] = t
        if self.haunt and t == self.haunt["exit"] and uid != self.haunt["traitor"]:
            msgs.append("🚪 出口之门就在脚下！幸存者全员到齐后可发起撤离")
        self.steps_left -= 1
        msgs += self._check_death(uid)
        if not self._result and (self.steps_left <= 0 or uid in self.dead):
            msgs += self._end_turn([])
        return msgs

    def _draw(self, uid: int, kind: str) -> list:
        if kind == "item":
            if not self.item_deck:
                return []
            it = self.item_deck.pop()
            self.items[uid].append(it)
            return [f"🎁 拾获道具【{it}】"]
        if kind == "event":
            if not self.event_deck:
                return []
            return self._apply_event(uid, self.event_deck.pop())
        if kind == "omen":
            if not self.omen_deck:
                return []
            name, stat = self.omen_deck.pop()
            self.stats[uid][stat] += 1
            self.omens += 1
            msgs = [f"🔮 预兆【{name}】！{STAT_CN[stat]} +1（第 {self.omens} 枚预兆）"]
            if self.phase == "explore":
                roll = self.rng.randint(1, 6)
                if roll <= min(self.omens, 6):
                    msgs.append(f"🎲 惊魂检定掷出 {roll} ≤ 预兆数 {self.omens}——山屋苏醒了！")
                    msgs += self._trigger_haunt()
                else:
                    msgs.append(f"🎲 惊魂检定掷出 {roll} > {self.omens}，暂时安然无恙")
            return msgs
        return []

    def _apply_event(self, uid: int, ev: str) -> list:
        stat, delta, desc = EVENT_DECK[ev]
        msgs = [f"❗事件【{ev}】：{desc}"]
        if stat:
            self.stats[uid][stat] += delta
            msgs.append(f"　{STAT_CN[stat]} {'+' if delta > 0 else ''}{delta}")
        elif ev == "意外的馈赠":
            if self.item_deck:
                it = self.item_deck.pop()
                self.items[uid].append(it)
                msgs.append(f"　🎁 获得道具【{it}】")
        elif ev == "暗门":
            x, y = self.pos[uid]
            for dx, dy in self.rng.sample(list(DIRS.values()), 4):
                t = (x + dx, y + dy)
                if t not in self.room_map and self.tiles:
                    name, _ = self.tiles.pop()
                    self.room_map[t] = name
                    msgs.append(f"　暗门通向【{name}】，已在地图上标出")
                    break
        return msgs

    def _use(self, uid: int, item: str) -> list:
        if item not in self.items[uid]:
            raise GameRuleError("你没有这件道具")
        if item == "消防斧":
            return ["消防斧是被动武器：攻击掷骰自动 +1，无需使用"]
        st = self.stats[uid]
        if item == "急救包":
            k = "might" if st["might"] <= st["speed"] else "speed"
            st[k] += 2
            msgs = [f"💊 使用急救包，{STAT_CN[k]} +2"]
        elif item == "镇静剂":
            k = "sanity" if st["sanity"] <= st["knowledge"] else "knowledge"
            st[k] += 2
            msgs = [f"💊 使用镇静剂，{STAT_CN[k]} +2"]
        elif item == "光之水晶":
            st["speed"] += 1
            msgs = ["💎 光之水晶赋能，速度 +1"]
        elif item == "力量护符":
            st["might"] += 1
            msgs = ["💪 力量护符共鸣，力量 +1"]
        elif item == "圣水":
            self.holy.add(uid)
            msgs = ["⛪ 你饮下圣水，下一次攻击掷骰 +2"]
        else:
            raise GameRuleError("这件道具现在用不了")
        self.items[uid].remove(item)
        return msgs

    def _attack(self, uid: int, target: int) -> list:
        if self.phase != "haunt":
            raise GameRuleError("探索阶段不能攻击同伴")
        if target == uid:
            raise GameRuleError("不能攻击自己")
        if target not in self.stats or target in self.dead:
            raise GameRuleError("目标已死亡")
        if self.pos[uid] != self.pos[target]:
            raise GameRuleError("目标不在同一房间")
        if self.attack_used:
            raise GameRuleError("本回合已攻击过")
        self.attack_used = True
        ra = self.rng.randint(1, 6) + self.stats[uid]["might"]
        bonus = 0
        if "消防斧" in self.items[uid]:
            bonus += 1
        if uid in self.holy:
            bonus += 2
            self.holy.discard(uid)
        ra += bonus
        rd = self.rng.randint(1, 6) + self.stats[target]["might"]
        ta, td = self._nick(uid), self._nick(target)
        msgs = [f"⚔️ {ta} 向 {td} 发起攻击：{ra} vs {rd}"
                + (f"（武器加值 +{bonus}）" if bonus else "")]
        if ra > rd:
            msgs += self._damage(target, ra - rd)
        elif rd > ra:
            msgs += self._damage(uid, rd - ra)
        else:
            msgs.append("两人僵持不下，谁也没占到便宜")
        msgs += self._check_death(uid) + self._check_death(target)
        if not self._result and uid in self.dead:
            msgs += self._end_turn([])
        return msgs

    def _damage(self, uid: int, dmg: int) -> list:
        st = self.stats[uid]
        use = min(st["might"], dmg)
        st["might"] -= use
        rest = dmg - use
        if rest:
            st["speed"] -= rest
        return [f"🩸 {self._nick(uid)} 受创 {dmg} 点（力量 {st['might']}，速度 {st['speed']}）"]

    def _escape(self, uid: int) -> list:
        if self.phase != "haunt" or not self.haunt:
            raise GameRuleError("惊魂降临后才能从出口撤离")
        if uid == self.haunt["traitor"]:
            raise GameRuleError("叛徒无法从出口之门逃离")
        if uid in self.dead:
            raise GameRuleError("阵亡者无法行动")
        ex = self.haunt["exit"]
        traitor = self.haunt["traitor"]
        survivors = [u for u in self.players if u not in self.dead and u != traitor]
        behind = [self._nick(u) for u in survivors if self.pos[u] != ex]
        if behind:
            raise GameRuleError("还有幸存者未抵达出口之门：" + "、".join(behind))
        self._result = ("survivors", "escape")
        return [f"🚪 {self._nick(uid)} 带领幸存者全员撤离，山屋在身后轰然崩塌！幸存者获胜！"]

    # ---------- 惊魂 / 回合 / 结算 ----------
    def _trigger_haunt(self) -> list:
        self.phase = "haunt"
        alive = [u for u in self.players if u not in self.dead]
        best = max(self.stats[u]["might"] for u in alive)
        traitor = self.rng.choice([u for u in alive if self.stats[u]["might"] == best])
        self.stats[traitor]["might"] += 2
        ex = self._place_exit()
        self.room_map[ex] = "出口之门"          # 出口直接上地图，确保可以走进去
        self.haunt = {"traitor": traitor, "exit": ex, "scenario": "血月惊魂"}
        return [f"⚡ 血月升起，《血月惊魂》降临！{self._nick(traitor)} 被山屋附身成为叛徒（力量 +2）！",
                f"🚪 出口之门在远处显现——幸存者全员抵达即可撤离，或击杀叛徒！"]

    def _place_exit(self) -> tuple:
        for _ in range(80):
            x, y = self.rng.randint(-5, 5), self.rng.randint(-5, 5)
            if abs(x) + abs(y) >= 4 and (x, y) not in self.room_map:
                return (x, y)
        for r in range(4, 9):
            for x in range(-r, r + 1):
                for y in (-r, r):
                    if (x, y) not in self.room_map:
                        return (x, y)
        return (0, 4)

    def _end_turn(self, msgs: list) -> list:
        if self._result:
            return msgs
        n = len(self.players)
        for _ in range(n):
            self.turn_idx = (self.turn_idx + 1) % n
            if self.players[self.turn_idx] not in self.dead:
                break
        cur = self.players[self.turn_idx]
        self.steps_left = self.stats[cur]["speed"]
        self.attack_used = False
        msgs.append(f"↪ 轮到 {self._nick(cur)}（速度 {self.stats[cur]['speed']}，可移动 {self.steps_left} 步）")
        return msgs

    def _check_death(self, uid: int) -> list:
        if uid in self.dead or uid not in self.stats:
            return []
        if any(v <= 0 for v in self.stats[uid].values()):
            self.dead.add(uid)
            return [f"☠️ {self._nick(uid)} 倒在了山屋的黑暗中……"]
        return []

    def ended(self):
        if self._result:
            side, why = self._result
            if side == "survivors":
                return {"winner_uid": None, "detail": "🚪 幸存者逃出了山屋，山屋重归寂静！"}
            t = self.haunt["traitor"]
            return {"winner_uid": t, "detail": f"☠️ 叛徒 {self._nick(t)} 献祭了所有幸存者，血月完成！"}
        alive = [u for u in self.players if u not in self.dead]
        if self.phase == "haunt" and self.haunt:
            t = self.haunt["traitor"]
            if t in self.dead:
                return {"winner_uid": None,
                        "detail": f"⚔️ 叛徒 {self._nick(t)} 被击杀，山屋重归寂静，幸存者获胜！"}
            if not [u for u in alive if u != t]:
                return {"winner_uid": t,
                        "detail": f"☠️ 叛徒 {self._nick(t)} 献祭了所有幸存者，血月完成！"}
        else:
            if not alive:
                return {"winner_uid": None, "detail": "🏚️ 山屋吞噬了所有闯入者"}
            if len(alive) == 1:
                return {"winner_uid": alive[0],
                        "detail": f"🏃 仅 {self._nick(alive[0])} 存活，独自逃出山屋"}
        return None

    def player_left(self, uid: int) -> list:
        if uid not in self.players:
            return []
        msgs = [f"👋 {self._nick(uid)} 掉线离开了对局（视为死亡）"]
        was_current = self.players[self.turn_idx] == uid
        self.dead.add(uid)
        if self.haunt and self.haunt["traitor"] == uid:
            self._result = ("survivors", "traitor_left")
        idx = self.players.index(uid)
        self.players.remove(uid)
        self.pos.pop(uid, None)
        if self.turn_idx >= len(self.players):
            self.turn_idx = 0
        elif idx < self.turn_idx:
            self.turn_idx -= 1
        if was_current and not self._result and self.players:
            cur = self.players[self.turn_idx]      # 继任者直接获得新回合，不再推进
            self.steps_left = self.stats[cur]["speed"]
            self.attack_used = False
            msgs.append(f"↪ 轮到 {self._nick(cur)}（速度 {self.stats[cur]['speed']}，可移动 {self.steps_left} 步）")
        return msgs

    def _nick(self, uid: int) -> str:
        return f"玩家{uid}"
