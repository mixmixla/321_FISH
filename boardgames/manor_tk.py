"""The revealed manor, discovery journal and usable inventory for Tk."""
from boardgames.card_table_tk import art


PAPER, INK, MUTED = "#f3edf5", "#332c48", "#615774"
NIGHT, GOLD, EDGE = "#28223c", "#e1b760", "#9e91b0"
DIRS = {"up": (0, -1, "北"), "down": (0, 1, "南"), "left": (-1, 0, "西"), "right": (1, 0, "东")}
PLAYER_COLORS = ("#e7bd56", "#8dc8bb", "#c8a9df", "#8cb9e2", "#ec9b74", "#d395b1")
# Fallback copy for old snapshots, matching BetrayalGame._use exactly.
ITEM_HELP = {"消防斧": "被动武器：攻击掷骰自动 +1，无需使用。",
             "急救包": "力量、速度中较低的一项 +2，使用后消耗。",
             "镇静剂": "理智、知识中较低的一项 +2，使用后消耗。",
             "光之水晶": "速度 +1，使用后消耗。", "力量护符": "力量 +1，使用后消耗。",
             "圣水": "下一次攻击掷骰 +2，使用后消耗。"}


def label(cv, x, y, value, size=9, color=INK, anchor="w", bold=False, width=None):
    kw = dict(text=str(value), fill=color, anchor=anchor,
              font=("Microsoft YaHei UI", size, "bold" if bold else "normal"))
    if width:
        kw.update(width=width, justify="left")
    return cv.create_text(x, y, **kw)


def panel(cv, rect, fill=PAPER, edge=EDGE, line=1, tag=""):
    cv.create_rectangle(*rect, fill=fill, outline=edge, width=line, tags=tag)


def control(cv, ui, rect, title, key, selected=False, enabled=True):
    panel(cv, rect, NIGHT if selected else "#e1d9eb", GOLD if enabled else "#a9b3a8")
    label(cv, (rect[0]+rect[2])/2, (rect[1]+rect[3])/2, title, 9,
          PAPER if selected else INK if enabled else "#899389", "center", True)
    if enabled:
        ui["manor_hits"].append((*rect, key))


def _catalog():
    try:
        from boardgames.manor_catalog import ATLASES
        return ATLASES
    except ImportError:
        return {}


def illustration(cv, kind, name, rect):
    atlas = _catalog().get(kind) or {}
    names = atlas.get("names") or ()
    if name not in names:
        return False
    ok = art(cv, atlas["file"], names.index(name), atlas["cols"], atlas["rows"], rect,
             contain=kind != "room")
    if ok:
        cv.addtag_withtag("manor-"+kind, cv.find_all()[-1])
    return ok


def point(key):
    x, y = str(key).split(",")
    return int(x), int(y)


def coord(x, y):
    return f"{x},{y}"


def room_name(st, key):
    return (st.get("room_names") or {}).get(key) or (st.get("rooms") or {}).get(key, "未知")


def can_act(ui):
    st, room, me = ui.get("state") or {}, ui.get("room") or {}, ui.get("me")
    return bool(ui.get("connected") and room.get("status") == "playing"
                and st.get("status") == "playing" and st.get("turn_uid") == me
                and me in room.get("players", []) and me in st.get("alive", [])
                and st.get("winner_uid") is None)


def _item_text(st, name):
    for record in reversed(st.get("discoveries") or []):
        for card in record.get("cards") or []:
            if card.get("kind") == "item" and card.get("name") == name and card.get("text"):
                return card["text"]
    return ITEM_HELP.get(name, "用途请见规则与本局事件记录。")


def _viewport(ui, st, w, h):
    rooms = st.get("rooms") or {}
    mine = (st.get("pos") or {}).get(str(ui.get("me"))) or next(iter(rooms), "0,0")
    if ui.get("manor_follow", True):
        ui["manor_center"] = point(mine)
    cx, cy = ui.get("manor_center", point(mine))
    top, bottom = 92, h-80
    if ui.get("manor_overview"):
        points = [point(k) for k in rooms] or [(cx, cy)]
        left, right = min(p[0] for p in points), max(p[0] for p in points)
        north, south = min(p[1] for p in points), max(p[1] for p in points)
    elif ui.get("manor_close"):
        left = right = cx
        north = south = cy
    else:
        points = [point(key) for key in rooms]
        near = points and all(abs(x-cx)<=1 and abs(y-cy)<=1 for x, y in points)
        if near and ui.get("manor_follow", True):
            left, right = min(x for x, _ in points), max(x for x, _ in points)
            north, south = min(y for _, y in points), max(y for _, y in points)
        else:
            left, right, north, south = cx-1, cx+1, cy-1, cy+1
    cols, rows = right-left+1, south-north+1
    map_w = w - (min(168, int(w*.29)) if st.get("discoveries") and not ui.get("manor_overview") else 0)
    cell = max(1, min((map_w-20)/cols, (bottom-top)/rows, 250))
    if cell >= 24:
        cell = (int(cell)//8)*8  # Match the image cache sizes: adjoining art has no inset gap.
    ox, oy = (map_w-cols*cell)/2, top+(bottom-top-rows*cell)/2
    return left, right, north, south, cell, ox, oy


def _map(cv, st, me, nick, ui, w, h):
    overview = bool(ui.get("manor_overview"))
    control(cv, ui, (10, 65, 82, 87), "回到我", "follow")
    control(cv, ui, (88, 65, 150, 87), "局部图" if overview else "看全图", "overview", overview)
    control(cv, ui, (156, 65, 216, 87), "看周边" if ui.get("manor_close") else "近看房间", "close", ui.get("manor_close", False))
    rooms, positions = st.get("rooms") or {}, st.get("pos") or {}
    left, right, north, south, cell, ox, oy = _viewport(ui, st, w, h)
    focus = coord(*ui.get("manor_center", (0, 0)))
    label(cv, 224, 76, "全屋" if overview else room_name(st, focus), 9, INK, bold=True, width=max(20, w-392))
    ui["manor_cells"], ui["manor_doors"], ui["manor_people"] = {}, [], []
    exit_pos = (st.get("haunt") or {}).get("exit")
    players, alive = st.get("players") or [], st.get("alive") or []
    for y in range(north, south+1):
        for x in range(left, right+1):
            key = coord(x, y)
            x0, y0 = ox+(x-left)*cell, oy+(y-north)*cell
            rect = x0, y0, x0+cell, y0+cell
            panel(cv, rect, "#41374d" if key in rooms else "#292638", "#5e506c")
            if key not in rooms:
                continue
            ui["manor_cells"][key] = rect
            ui["manor_hits"].append((*rect, ("room", key)))
            if cell >= 24:
                illustration(cv, "room", room_name(st, key), rect)
            if cell >= 42 and (overview or positions.get(str(me)) != key):
                panel(cv, (x0+1, y0+cell-15, x0+cell-1, y0+cell-1), NIGHT, NIGHT)
                label(cv, x0+cell/2, y0+cell-8, room_name(st, key), 8, PAPER, "center")
            if key == exit_pos:
                panel(cv, (x0+1, y0+1, x0+cell-1, y0+cell-1), "", GOLD, 3, "manor-exit")
                label(cv, x0+cell/2, y0+8, "出口", 8, "#fff1a7", "center", True)
            occupants = [u for u in players if positions.get(str(u)) == key]
            for i, uid in enumerate(occupants):
                row, col = divmod(i, 3)
                px, py = x0+(col+1)*cell/4, y0+cell*(0.38+row*0.24)
                radius = max(3, min(10, cell*0.105))
                seat = (st.get("seats") or {}).get(str(uid), players.index(uid)+1)
                cv.create_oval(px-radius, py-radius, px+radius, py+radius,
                               fill=PLAYER_COLORS[(int(seat)-1)%6] if uid in alive else "#7a7976",
                               outline="#fffbe8" if uid == me else NIGHT, width=2 if uid == me else 1,
                               tags="manor-player")
                attackable = (not overview and can_act(ui) and st.get("phase") == "haunt"
                              and not st.get("attack_used") and positions.get(str(me)) == key
                              and uid != me and uid in alive)
                if attackable:
                    cv.create_oval(px-radius-2, py-radius-2, px+radius+2, py+radius+2,
                                   outline=GOLD, width=2, tags="manor-fight")
                label(cv, px, py, seat, max(6, min(9, int(radius))), NIGHT, "center", True)
                hit = px-radius, py-radius, px+radius, py+radius
                ui["manor_people"].append((*hit, uid, key))
            if key == exit_pos and not overview and me in alive:
                traitor = (st.get("haunt") or {}).get("traitor")
                if me != traitor:
                    ready = all(positions.get(str(uid)) == key for uid in alive if uid != traitor)
                    rect = (x0+cell*.24, y0+cell*.70, x0+cell*.79, y0+cell*.89)
                    control(cv, ui, rect, "撤离", ("action", {"escape": True}), enabled=ready and can_act(ui))
            if positions.get(str(me)) == key:
                panel(cv, (x0+1, y0+1, x0+cell-1, y0+cell-1), "", "#e9daa8", 2)
    # Door hits are restricted to the four true edge centres of my current tile.
    here = positions.get(str(me))
    if not overview and here in ui["manor_cells"]:
        x0, y0, x1, y1 = ui["manor_cells"][here]
        cx, cy = (x0+x1)/2, (y0+y1)/2
        half = max(8, min(17, cell*0.18))
        centres = {"up": (cx, y0), "down": (cx, y1), "left": (x0, cy), "right": (x1, cy)}
        hx, hy = point(here)
        for direction, (px, py) in centres.items():
            dx, dy, title = DIRS[direction]
            target = coord(hx+dx, hy+dy)
            enabled = (can_act(ui) and st.get("steps_left", 0) > 0
                       and (target in rooms or st.get("tiles_left", 1) > 0))
            rect = ((px-half, py-6, px+half, py+6) if direction in ("up", "down")
                    else (px-6, py-half, px+6, py+half))
            panel(cv, rect, GOLD if enabled else "#67766a", NIGHT, 1, "manor-door")
            label(cv, px, py, title, 8, NIGHT, "center", True)
            if enabled:
                ui["manor_doors"].append((*rect, direction, target))
    discovered = st.get("discoveries") or []
    if discovered and not overview:
        entry = discovered[-1]
        cards = entry.get("cards") or []
        if cards:
            rail = min(168, int(w*.29))
            left, right = w-rail+3, w-8
            label(cv, left, 100, "刚刚揭开 · "+entry["room"], 8, INK, bold=True)
            slot = min(100, max(44, (h-203)/len(cards)))
            for i, card in enumerate(cards):
                y = 112+i*slot
                frame = left, y, right, y+slot-3
                panel(cv, frame, "#e3d8ed", GOLD)
                illustration(cv, card["kind"], card["name"], (left+1,y+1,right-1,y+slot-19))
                label(cv, (left+right)/2, y+slot-11, card["name"], 8, INK, "center", True)
                ui["manor_hits"].append((*frame, ("reveal", entry["pos"])))
    label(cv, 11, h-74, "全图只作导航：点房间放大" if overview else "点当前房间的方向门移动 · 点房间回看发现" if not st.get("haunt") else "点门移动 · 点同格金圈棋子攻击 · 齐集出口撤离", 8, MUTED)


def _journal(cv, st, me, nick, ui, w, h):
    rooms = st.get("rooms") or {}
    keys = list(rooms)
    if not keys:
        label(cv, 14, 100, "尚未揭示房间。", 11)
        return
    selected = ui.get("manor_book_pos")
    if selected not in rooms:
        selected = ui["manor_book_pos"] = keys[-1]
    index = keys.index(selected)
    control(cv, ui, (10, 65, 78, 87), "上一间", ("book", -1), enabled=index > 0)
    control(cv, ui, (w-78, 65, w-10, 87), "下一间", ("book", 1), enabled=index+1 < len(keys))
    label(cv, w/2, 76, f"{room_name(st, selected)} · {index+1}/{len(keys)}", 10, INK, "center", True)
    record = next((r for r in st.get("discoveries") or [] if r.get("pos") == selected), None)
    cards = (record or {}).get("cards") or []
    if record:
        label(cv, 12, 101, f"发现者：{nick(record.get('uid'))} · 本次实际揭牌 {len(cards)} 张", 9, MUTED)
    else:
        label(cv, 12, 101, "已揭示的房间 · 此处没有发现牌记录", 9, MUTED)
    if not cards:
        side = max(40, min(w-32, h-196, 280))
        rect = (w-side)/2, 118, (w+side)/2, 118+side
        panel(cv, rect, "#d7ccaf")
        illustration(cv, "room", room_name(st, selected), rect)
        return
    width = (w-30)/len(cards)-10
    for i, card in enumerate(cards):
        x, top = 15+i*(width+10), 118
        story = label(cv, x+4, 0, card.get("text", ""), 9, INK, "nw", width=width-8)
        bounds = cv.bbox(story) if story is not None else None
        story_height = bounds[3]-bounds[1] if bounds else 50
        image_h = max(40, min(width*0.75, h-67-top-36-story_height))
        rect = x, top, x+width, top+image_h
        panel(cv, rect, "#dcd2b9")
        illustration(cv, card.get("kind"), card.get("name"), rect)
        kinds = {"item": "物品", "event": "事件", "omen": "预兆"}
        label(cv, x+4, top+image_h+14, f"{kinds.get(card.get('kind'), '发现')} · {card.get('name', '')}", 10, INK, bold=True)
        if story is not None:
            cv.coords(story, x+4, top+image_h+28)


def _inventory(cv, st, me, nick, ui, w, h):
    owner = ui.get("manor_inspect", me)
    players = st.get("players") or []
    if owner not in players:
        owner = ui["manor_inspect"] = me if me in players else next(iter(players), None)
    step = (w-20)/max(1, len(players))
    for i, uid in enumerate(players):
        control(cv, ui, (10+i*step, 65, 7+(i+1)*step, 87),
                ("我" if uid == me else str(nick(uid))[:5]), ("person", uid), owner == uid)
    items = (st.get("items") or {}).get(str(owner)) or []
    label(cv, 12, 102, ("我的背包" if owner == me else f"他人背包：{nick(owner)}（只读）")+f" · {len(items)} 件", 10, INK, bold=True)
    if not items:
        label(cv, 12, 140, "暂未持有道具，首次开门可能获得物品。", 10, MUTED)
        return
    selected = min(max(0, ui.get("manor_item", 0)), len(items)-1)
    ui["manor_item"] = selected
    rect = 12, 118, w/2-10, h-127
    panel(cv, rect, "#dcd2b9", GOLD, 2)
    illustration(cv, "item", items[selected], rect)
    label(cv, 14, h-115, f"{selected+1}/{len(items)} · {items[selected]}", 10, INK, bold=True)
    label(cv, w/2+4, 124, "道具用途", 10, INK, bold=True)
    label(cv, w/2+4, 146, _item_text(st, items[selected]), 9, INK, "nw", width=w/2-18)
    # Each owned object is its own selector. The enlarged card itself is the use target.
    width = min(55, (w-24)/len(items))
    for i, item in enumerate(items if len(items) > 1 else ()):
        left = 12+i*width
        thumb = left, h-104, left+width-4, h-72
        panel(cv, thumb, NIGHT, GOLD if i == selected else EDGE, 2 if i == selected else 1)
        illustration(cv, "item", item, thumb)
        ui["manor_hits"].append((*thumb, ("item", i)))
    usable = can_act(ui) and owner == me and items[selected] != "消防斧"
    if usable:
        ui["manor_hits"].append((*rect, ("action", {"use": items[selected]})))
        label(cv, w/2+4, h-123, "点左侧道具牌使用", 9, INK, bold=True)


def paint(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    ui["game"] = "betrayal"
    ui.pop("_hover", None)
    context = ui.get("_room_context"), me
    if ui.get("manor_context") != context:
        ui.update(manor_context=context, manor_tab="map", manor_follow=True,
                  manor_overview=False, manor_close=False, manor_book_pos=None, manor_seen=0, manor_inspect=me, manor_item=0)
    if ui.get("manor_inspect") not in st.get("players", []):
        ui["manor_inspect"] = next(iter(st.get("players") or []), None)
    discoveries = st.get("discoveries") or []
    if len(discoveries) > ui.get("manor_seen", 0):
        if discoveries[-1].get("uid") == me or ui.get("manor_book_pos") is None:
            ui["manor_book_pos"] = discoveries[-1].get("pos")
    ui["manor_seen"] = len(discoveries)
    ui["manor_hits"], ui["manor_doors"], ui["manor_people"] = [], [], []
    panel(cv, (0, 0, w, h), PAPER, PAPER, tag="manor-paper")
    panel(cv, (0, 0, w, 31), NIGHT, NIGHT)
    ended = (ui.get("room") or {}).get("status") == "ended" or st.get("status") == "ended"
    phase = "已结束" if ended else "惊魂" if st.get("haunt") else "探索"
    label(cv, 11, 16, "山屋惊魂 · "+phase, 11, PAPER, bold=True)
    turn = "结算中" if ended else "轮到你" if st.get("turn_uid") == me else "等待 "+str(nick(st.get("turn_uid")))[:8]
    label(cv, w-10, 16, f"{turn} · 剩{st.get('steps_left', 0)}步 · 预兆{st.get('omens', 0)}", 9, PAPER, "e")
    for i, (key, title) in enumerate((("map", "房间地图"), ("journal", "发现簿"), ("inventory", "道具背包"))):
        rect = 10+i*(w-20)/3, 37, 7+(i+1)*(w-20)/3, 60
        control(cv, ui, rect, title, ("tab", key), ui.get("manor_tab") == key)
    tab = ui.get("manor_tab", "map")
    if tab == "map":
        _map(cv, st, me, nick, ui, w, h)
    elif tab == "journal":
        _journal(cv, st, me, nick, ui, w, h)
    else:
        _inventory(cv, st, me, nick, ui, w, h)
    # The focus window retains real turn controls and a selected player's stats.
    panel(cv, (5, h-67, w-5, h-5), "#e1d9eb", EDGE)
    who = ui.get("manor_inspect", me)
    stats = (st.get("stats") or {}).get(str(who)) or {}
    seat = (st.get("seats") or {}).get(str(who), "?")
    if ended:
        panel(cv, (6,h-65,w-6,h-6), "#3b2b52", GOLD, 2, "manor-result")
        label(cv, 16, h-51, "◆ 终局", 10, "#f5cf77", bold=True)
        verdict = ui.get("manor_outcome") or "本局结束"
        label(cv, 16, h-40, verdict, 10, "#fff4dd", "nw", width=w-36)
        return
    label(cv, 12,h-52,f"{seat}号 · {nick(who)}",9,INK,bold=True)
    attributes = (("might","力","#b4455a"),("speed","速","#34796e"),
                  ("sanity","理","#765ca0"),("knowledge","知","#4e6f9a"))
    for i,(key,short,color) in enumerate(attributes):
        x=12+i*44
        panel(cv,(x,h-37,x+40,h-15),color,color,tag="manor-stat")
        label(cv,x+20,h-26,f"{short} {stats.get(key,0)}",9,"#fff","center",True)
    label(cv,w-118,h-52,"未探 "+str(st.get("tiles_left","?"))+" 间",8,MUTED,"e")
    control(cv, ui, (w-108, h-39, w-12, h-13), "结束回合", ("action", {"end": True}), enabled=can_act(ui))


def click(ui, x, y):
    st, me = ui.get("state") or {}, ui.get("me")
    # Doors precede room inspection. In a haunt, highlighted occupied seats are attack targets.
    for x0, y0, x1, y1, direction, target in ui.get("manor_doors") or []:
        if x0 <= x <= x1 and y0 <= y <= y1:
            if can_act(ui) and st.get("steps_left", 0) > 0:
                ui["submit"]({"move": direction})
            return
    for x0, y0, x1, y1, uid, key in ui.get("manor_people") or []:
        if x0 <= x <= x1 and y0 <= y <= y1:
            if (can_act(ui) and st.get("phase") == "haunt" and not st.get("attack_used")
                    and not ui.get("manor_overview") and uid != me and uid in (st.get("alive") or [])
                    and (st.get("pos") or {}).get(str(me)) == key):
                ui["submit"]({"attack": uid})
                return
            ui["manor_inspect"] = uid
            ui.get("repaint", lambda: None)()
            return
    for *rect, key in reversed(ui.get("manor_hits") or []):
        if not (rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]):
            continue
        if key == "follow":
            ui.update(manor_follow=True, manor_overview=False)
        elif key == "overview":
            ui["manor_overview"] = not ui.get("manor_overview")
        elif key == "close":
            ui.update(manor_close=not ui.get("manor_close"), manor_overview=False)
        elif key[0] == "pan":
            dx, dy, _ = DIRS[key[1]]
            cx, cy = ui.get("manor_center", (0, 0))
            ui.update(manor_center=(cx+dx, cy+dy), manor_follow=False, manor_overview=False)
        elif key[0] == "tab":
            ui["manor_tab"] = key[1]
        elif key[0] == "room":
            if ui.get("manor_overview"):
                ui.update(manor_center=point(key[1]), manor_follow=False, manor_overview=False)
            else:
                ui.update(manor_tab="journal", manor_book_pos=key[1])
        elif key[0] == "reveal":
            ui.update(manor_tab="journal", manor_book_pos=key[1])
        elif key[0] == "book":
            keys = list(st.get("rooms") or {})
            index = keys.index(ui["manor_book_pos"])
            ui["manor_book_pos"] = keys[min(max(0, index+key[1]), len(keys)-1)]
        elif key[0] == "person":
            ui.update(manor_inspect=key[1], manor_item=0)
        elif key[0] == "item":
            ui["manor_item"] = key[1]
        elif key[0] == "action":
            if can_act(ui):
                ui["submit"](key[1])
            return
        ui.get("repaint", lambda: None)()
        return
