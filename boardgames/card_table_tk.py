"""Illustrated GemCity market and Love Letter court on the existing Tk canvas."""
from collections import OrderedDict
from functools import lru_cache
import io


INK, MUTED, PAPER, GREEN, GOLD = "#263c39", "#5e726d", "#fbf7ed", "#187461", "#ad7833"
COLORS = ("o", "d", "r", "e", "s")
GEMS = {"o": ("黑", "#374343"), "d": ("钻", "#e1edf3"), "r": ("红", "#b94f50"),
        "e": ("绿", "#338469"), "s": ("蓝", "#477ba8"), "g": ("金", "#d5ac56")}
ROLES = {1: "护卫", 2: "牧师", 3: "男爵", 4: "侍女", 5: "王子", 6: "国王", 7: "伯爵夫人", 8: "公主"}
EFFECTS = {1: "指定一人，猜其手牌", 2: "查看一人的手牌", 3: "与一人比较手牌", 4: "获得侍女保护",
           5: "令一人弃牌重抽", 6: "与一人交换手牌", 7: "弃牌，无额外效果", 8: "弃掉公主，自己出局"}


def text(cv, x, y, value, size=10, color=INK, anchor="w", bold=False, width=None):
    kw = {"text": str(value), "font": ("Microsoft YaHei UI", size, "bold" if bold else "normal"),
          "fill": color, "anchor": anchor}
    if width:
        kw.update(width=width, justify="left")
    cv.create_text(x, y, **kw)


def box(cv, rect, fill=PAPER, edge="#c6cfc5", line=1):
    cv.create_rectangle(*rect, fill=fill, outline=edge, width=line)


def button(cv, rect, label, selected=False, enabled=True):
    box(cv, rect, GREEN if selected else "#eef2e8", GREEN if enabled else "#d5d9d1")
    text(cv, (rect[0]+rect[2])/2, (rect[1]+rect[3])/2, label, 9,
         "#ffffff" if selected else (INK if enabled else "#8c9791"), "center", True)


def hit(rect, x, y):
    return rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]


@lru_cache(maxsize=5)
def _atlas(name):
    from PIL import Image
    from boardgames.gallery import resource_path
    with Image.open(resource_path(name)) as source:
        return source.convert("RGB")


def art(cv, filename, index, columns, rows, rect, contain=False):
    """Exact atlas cell, including index zero; bounded, canvas-owned Tk cache."""
    if type(index) is not int or not 0 <= index < columns*rows or not isinstance(getattr(cv, "_w", None), str):
        return False
    width = max(8, int(rect[2]-rect[0])//8*8)
    height = max(8, int(rect[3]-rect[1])//8*8)
    key = filename, index, width, height, contain
    cache = getattr(cv, "_card_art_cache", None)
    if cache is None:
        cache = cv._card_art_cache = OrderedDict()
    try:
        if key not in cache:
            from PIL import Image, ImageOps
            import tkinter as tk
            source = _atlas(filename)
            col, row = index % columns, index // columns
            crop = source.crop((col*source.width//columns, row*source.height//rows,
                                (col+1)*source.width//columns, (row+1)*source.height//rows))
            # Short windows keep the face and headdress, cropping the lower
            # body rather than the top of a court/patron portrait.
            center = (0.5, 0.0) if filename in ("lovelove-court.webp", "gemcity-patrons.webp") else (0.5, 0.5)
            pixels = (ImageOps.pad(crop, (width, height), Image.Resampling.LANCZOS, color="#eee7d9")
                      if contain else ImageOps.fit(crop, (width, height), Image.Resampling.LANCZOS, centering=center))
            data = io.BytesIO()
            pixels.save(data, format="PNG")
            cache[key] = tk.PhotoImage(master=cv, data=data.getvalue())
            while len(cache) > 64:
                cache.popitem(last=False)
        cache.move_to_end(key)
        cv.create_image((rect[0]+rect[2])/2, (rect[1]+rect[3])/2, image=cache[key], tags="card-illustration")
        return True
    except (ImportError, OSError, ValueError):
        return False


def _member(st, ui, me):
    room = ui.get("room") or {}
    members = room.get("players", st.get("players", st.get("alive", [])))
    return me is not None and me in members and me not in room.get("spectators", [])


def _private(st, ui, me, priv):
    return (priv or {}) if _member(st, ui, me) else {}


def _token(cv, x, y, color, value, size=8):
    name, fill = GEMS.get(color, (str(color), "#aaa"))
    cv.create_oval(x-size, y-size, x+size, y+size, fill=fill, outline="#7a8981")
    text(cv, x, y, value, 8, INK if color in ("d", "g") else "#fff", "center", True)
    return name


def _cost(cv, rect, cost, size=8):
    items = [(k, v) for k, v in (cost or {}).items() if v]
    step = min(23, (rect[2]-rect[0])/max(1, len(items)))
    if not items:
        text(cv, rect[0], rect[1], "免费", size, GREEN)
    for i, (key, value) in enumerate(items):
        _token(cv, rect[0]+8+i*step, rect[1], key, value, size)


def _development(cv, card, rect, affordable=False, reserve=False):
    x0, y0, x1, y1 = rect
    height = y1-y0
    box(cv, rect, "#fffdf5", GREEN if affordable else "#a7b9aa", 2 if affordable else 1)
    image_rect = x0+2, y0+2, x1-2, y1-37
    tier = card.get("tier", 1)
    if not art(cv, f"gemcity-tier{tier}.webp", card.get("art"), 4, 5, image_rect):
        box(cv, image_rect, "#e9e5d6", "#e9e5d6")
        text(cv, (x0+x1)/2, (y0+y1-37)/2, f"{tier}级发展卡", 10, MUTED, "center")
    title = card.get("title") or f"{tier}级·{GEMS.get(card.get('disc'), ('宝石',))[0]}发展卡"
    text(cv, x0+4, y1-29, title, 8 if height < 100 else 10, width=x1-x0-(36 if reserve else 8))
    _token(cv, x1-13, y0+12, card.get("disc"), "+1", 9)
    box(cv, (x0+3, y0+3, x0+34, y0+21), "#234b43", "#234b43")
    text(cv, x0+18, y0+12, f"{card.get('pts', 0)}分", 8, "#fff", "center", True)
    _cost(cv, (x0+5, y1-10, x1-5, y1), card.get("cost"), 7)
    if reserve:
        r = x1-28, y1-40, x1-2, y1-23
        button(cv, r, "留")
        return r


def paint_gemcity(cv, st, me, nick, submit, repaint, ui, priv, w, h, afford):
    cv.create_rectangle(0, 0, w, h, fill=PAPER, outline=PAPER, tags="card-table-paper")
    ui["game"] = "gemcity"
    ui["_card_private"] = priv
    ui.pop("_hover", None)
    context = ui.get("_room_context"), me
    if ui.get("gc_view_context") != context:
        ui.update(gc_view_context=context, gc_view="market", gc_page=0, gc_detail=None)
    private = _private(st, ui, me, priv)
    reserved, collection = private.get("reserved") or [], private.get("collection") or []
    view = ui.get("gc_view", "market")
    if not _member(st, ui, me) and view in ("reserved", "collection"):
        view = ui["gc_view"] = "market"
        ui["gc_detail"] = None
    for name in ("gc_bank", "gc_cards", "gc_reserve", "gc_reserved", "gc_navigation"):
        ui[name] = []
    ui["gc_take"] = None
    active = st.get("status") == "playing" and st.get("turn_uid") == me and st.get("winner_uid") is None
    if not active:
        ui["gc_sel"] = []
    sel = ui.setdefault("gc_sel", [])
    box(cv, (0, 0, w, 34), "#244f46", "#244f46")
    title = "璀璨宝石 · 发展卡市集"
    if st.get("winner_uid") is not None:
        title = f"{nick(st['winner_uid'])} 获胜"
    text(cv, 12, 16, title, 11, "#fff", bold=True)
    text(cv, w-10, 16, "轮到你" if active else "等待 " + str(nick(st.get("turn_uid"))), 9, "#e1ead6", "e")
    tabs = [("market", "三级市集"), ("reserved", f"我的保留 {len(reserved)}"),
            ("collection", f"我的卡册 {len(collection) or private.get('cards', 0)}"),
            ("nobles", f"贵宾 {len(st.get('nobles') or [])}")]
    for i, (key, label) in enumerate(tabs):
        rect = 7+i*(w-14)/4, 40, 4+(i+1)*(w-14)/4, 65
        enabled = key not in ("reserved", "collection") or _member(st, ui, me)
        button(cv, rect, label, view == key, enabled)
        if enabled:
            ui["gc_navigation"].append((*rect, key))
    top, bottom = 72, h-104
    market = st.get("market") or {}
    tokens = st.get("tokens") or {}
    discounts = st.get("discount") or {}
    mine, discount = tokens.get(str(me), tokens.get(me, {})), discounts.get(str(me), discounts.get(me, {}))
    detail = ui.get("gc_detail")
    if view == "collection" and type(detail) is int and 0 <= detail < len(collection):
        card = collection[detail]
        tier = card.get("tier", 1)
        box(cv, (6, 68, w-6, h-5), PAPER, "#c6cfc5")
        rect = 12, 72, 114, 99
        button(cv, rect, "返回卡册")
        ui["gc_navigation"].append((*rect, "album_back"))
        title = card.get("title") or f"{tier}级发展卡"
        text(cv, 126, 85, title, 11, GREEN, bold=True, width=w-140)
        frame = 12, 105, w-12, h-54
        box(cv, frame, "#eee7d9", "#b9a786")
        if not art(cv, f"gemcity-tier{tier}.webp", card.get("art"), 4, 5, frame, contain=True):
            text(cv, w/2, (105+h-54)/2, title, 17, MUTED, "center")
        color = GEMS.get(card.get("disc"), ("宝石",))[0]
        text(cv, 14, h-34, f"{tier}级 · {card.get('pts', 0)}分 · {color}折扣 +1", 10, GREEN, bold=True)
        text(cv, w-180, h-34, "费用", 9, MUTED)
        _cost(cv, (w-142, h-34, w-14, h-20), card.get("cost"), 8)
        text(cv, w/2, h-14, "已购买的卡面 · 只读欣赏", 9, MUTED, "center")
        return
    if view == "market":
        row_height = (bottom-top)/3
        card_width = (w-40)/4-6
        for row, tier in enumerate((3, 2, 1)):
            y = top+row*row_height
            cv.create_rectangle(6, y+3, 25, y+27, fill=GREEN, outline=GREEN, tags="gc-tier-label")
            text(cv, 15.5, y+15, str(tier), 9, PAPER, "center", True)
            for index, card in enumerate(market.get(str(tier), market.get(tier, []))[:4]):
                x = 28+index*(card_width+6)
                rect = x, y, x+card_width, y+row_height-6
                ok = afford(mine, discount, card)
                r = _development(cv, card, rect, ok, True)
                ui["gc_cards"].append((*rect, tier, index, ok))
                ui["gc_reserve"].append((*r, tier, index))
    elif view in ("reserved", "collection"):
        cards = reserved if view == "reserved" else collection
        page = min(max(0, ui.get("gc_page", 0)), max(0, (len(cards)-1)//6))
        ui["gc_page"] = page
        shown = cards[page*6:page*6+6]
        cols = 3
        rows = 1 if len(shown) <= 3 else 2
        cw, ch = (w-28)/cols-8, (bottom-top-26)/rows-5
        for i, card in enumerate(shown):
            x, y = 14+(i%cols)*(cw+8), top+(i//cols)*(ch+5)
            rect = x, y, x+cw, y+ch
            ok = afford(mine, discount, card)
            _development(cv, card, rect, ok if view == "reserved" else False)
            if view == "reserved":
                ui["gc_reserved"].append((*rect, page*6+i, ok))
            else:
                ui["gc_navigation"].append((*rect, ("open", page*6+i)))
        if not cards:
            text(cv, w/2, (top+bottom)/2, "暂无保留卡" if view == "reserved" else
                 (f"已购 {private.get('cards', 0)} 张，服务器未提供卡册" if private.get("cards") else "购买发展卡后会收入你的卡册"),
                 11, MUTED, "center")
        elif view == "reserved":
            text(cv, 14, bottom-10, "绿边卡可点击购买 · 图号与市集原卡一致", 9, GREEN)
        else:
            for rect, key, label in (((14, bottom-22, 76, bottom), "prev", "上一页"),
                                      ((w-76, bottom-22, w-14, bottom), "next", "下一页")):
                button(cv, rect, label)
                ui["gc_navigation"].append((*rect, key))
            text(cv, w/2, bottom-11, f"点击卡面欣赏 · {page+1}/{max(1, (len(cards)+5)//6)} 页", 9, GREEN, "center")
    else:
        nobles = st.get("nobles") or []
        ids, titles = st.get("noble_art") or [], st.get("noble_titles") or []
        count = max(1, len(nobles))
        cw = (w-20)/count-6
        for i, cost in enumerate(nobles):
            x, y = 10+i*(cw+6), top+10
            rect = x, y, x+cw, bottom-12
            box(cv, rect, "#fffaf0", "#c1a16d")
            art(cv, "gemcity-patrons.webp", ids[i] if i < len(ids) else None, 5, 1,
                (x+2, y+2, x+cw-2, bottom-76))
            text(cv, x+5, bottom-66, titles[i] if i < len(titles) else f"贵宾 {i+1}", 8, bold=True)
            text(cv, x+5, bottom-49, "+3 分 · 需折扣", 8, GOLD)
            _cost(cv, (x+4, bottom-29, x+cw-4, bottom-19), cost, 7)
        if not nobles:
            text(cv, w/2, (top+bottom)/2, "贵宾均已受邀", 12, GOLD, "center")
    # The shared bank never disappears when browsing the private card album.
    box(cv, (6, h-96, w-6, h-5), "#eef1e6", "#b8c9b7")
    text(cv, 14, h-76, "宝石池", 9, bold=True)
    step = min(43, (w-160)/6)
    for i, key in enumerate((*COLORS, "g")):
        x = 82+i*step
        _token(cv, x, h-77, key, (st.get("bank") or {}).get(key, 0), 10)
        text(cv, x, h-59, GEMS[key][0], 8, MUTED, "center")
        if key != "g":
            ui["gc_bank"].append((x-17, h-92, x+17, h-58, key))
        if key in sel:
            cv.create_oval(x-14, h-91, x+14, h-63, outline=GREEN, width=3)
    rect = w-102, h-92, w-14, h-62
    button(cv, rect, f"取 {len(sel)} 颗" if sel else "点选宝石", bool(sel), bool(sel))
    if sel:
        ui["gc_take"] = rect
    public_players = st.get("players") or []
    ui["gc_players"] = public_players
    if public_players:
        order = ([me] if me in public_players else []) + [u for u in public_players if u != me]
        viewed = order[ui.get("gc_inspect_idx", 0) % len(order)]
        held = tokens.get(str(viewed), tokens.get(viewed, {}))
        reductions = discounts.get(str(viewed), discounts.get(viewed, {}))
        who = "我" if viewed == me else "他人 " + str(nick(viewed))[:5]
        own = who + " ↔  " + "  ".join(f"{GEMS[k][0]}{held.get(k, 0)}" for k in (*COLORS, "g"))
        disc = "折扣  " + "  ".join(f"{GEMS[k][0]}{reductions.get(k, 0)}" for k in COLORS)
        text(cv, 14, h-38, own, 9)
        text(cv, 14, h-19, disc, 9, GREEN)
        score = (st.get("score") or {}).get(str(viewed), (st.get("score") or {}).get(viewed, 0))
        text(cv, w-15, h-20, f"{score}/15 分", 10, GREEN, "e", True)
        ui["gc_navigation"].append((8, h-52, 90, h-28, "inspect"))
    else:
        text(cv, 14, h-29, "旁观席 · 私人保留与卡册仅本人可见", 10, MUTED)


def browse_gemcity(ui, x, y):
    for *rect, key in ui.get("gc_navigation") or []:
        if hit(rect, x, y):
            if isinstance(key, tuple) and key[0] == "open":
                ui["gc_detail"] = key[1]
            elif key == "album_back":
                ui["gc_detail"] = None
            elif key == "inspect":
                ui["gc_inspect_idx"] = ui.get("gc_inspect_idx", 0)+1
            elif key == "prev":
                ui["gc_page"] = max(0, ui.get("gc_page", 0)-1)
            elif key == "next":
                ui["gc_page"] = ui.get("gc_page", 0)+1
            else:
                ui.update(gc_view=key, gc_page=0, gc_detail=None)
            ui.get("repaint", lambda: None)()
            return True
    return False


def _portrait(cv, value, rect, label, selected=False, enabled=False):
    x0, y0, x1, y1 = rect
    box(cv, rect, "#fff7ec", GREEN if selected else "#ba9b8c", 3 if selected else 1)
    if value in ROLES:
        art(cv, "lovelove-court.webp", value-1, 4, 2, (x0+3, y0+3, x1-3, y1-42))
        text(cv, x0+7, y1-30, f"{value} · {ROLES[value]}", 10, GREEN if enabled else INK, bold=True)
    else:
        text(cv, (x0+x1)/2, (y0+y1)/2, "未公开", 12, MUTED, "center")
    text(cv, x0+7, y1-12, label, 8, MUTED)


def paint_lovelove(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    ui["game"] = "lovelove"
    ui["_card_private"] = priv
    ui.pop("_hover", None)
    private = _private(st, ui, me, priv)
    hand, drawn = private.get("hand"), private.get("drawn")
    active = (_member(st, ui, me) and st.get("cur") == me and st.get("status") == "playing"
              and st.get("winner_uid") is None)
    key = ui.get("_room_context"), me, st.get("cur"), hand, drawn, st.get("deck_left"), len(st.get("discard") or [])
    if ui.get("ll_context") != key:
        old, chosen = ui.get("ll_context"), ui.get("ll_play")
        same_turn = old is not None and old[:3] == key[:3] and old[5:] == key[5:]
        legal = chosen in ROLES and chosen in (hand, drawn) and not ({hand, drawn} == {7, 8} and chosen != 7)
        if not (same_turn and legal):
            ui.update(ll_play=None, ll_target=None, ll_guess=None)
        ui["ll_context"] = key
    ui["ll_hits"] = []
    box(cv, (0, 0, w, h), "#f3eadf", "#f3eadf")
    box(cv, (0, 0, w, 34), "#654251", "#654251")
    text(cv, 12, 17, "情书 · 宫廷人物", 12, "#fff", bold=True)
    text(cv, w-12, 17, f"牌堆 {st.get('deck_left', 0)} 张", 9, "#fff", "e")
    alive = st.get("alive") or []
    members = (ui.get("room") or {}).get("players") or st.get("players") or alive
    text(cv, 12, 49, "  ·  ".join(str(nick(u))[:6]+(" 出局" if u not in alive else "") for u in members), 9, MUTED)
    title = (f"{nick(st['winner_uid'])} 获胜" if st.get("winner_uid") is not None else
             ("你的回合 · 选一张牌，再确认出牌" if active else "旁观公开牌" if not _member(st, ui, me) else "等待 " + str(nick(st.get("cur")))))
    text(cv, 12, 72, title, 10, GREEN, bold=True)
    top, bottom = 88, h-116
    gap, cw = 12, (w-48)/3
    selected = ui.get("ll_play")
    forced = {hand, drawn} == {7, 8}
    if _member(st, ui, me) and hand in ROLES:
        for i, (value, label) in enumerate(((hand, "我的持牌"), (drawn if active else None, "本回合新摸牌"))):
            rect = 12+i*(cw+gap), top, 12+i*(cw+gap)+cw, bottom
            enabled = active and value in ROLES and not (forced and value != 7)
            _portrait(cv, value, rect, label, value == selected and selected is not None, enabled)
            if enabled:
                ui["ll_hits"].append((*rect, "play", value))
    else:
        text(cv, 16, top+34, "私人手牌仅本人可见", 10, MUTED, width=cw*2)
    table = st.get("table")
    discard = st.get("discard") or []
    if table not in ROLES and discard:
        table = discard[-1][1]
    rect = 12+2*(cw+gap), top, w-12, bottom
    _portrait(cv, table, rect, "公开刚弃角色")
    y = h-103
    if selected in ROLES and active:
        text(cv, 12, y, f"选择 {ROLES[selected]}：{EFFECTS[selected]}", 9, GREEN)
        y += 23
        if selected in (1, 2, 3, 5, 6):
            targets = [u for u in alive if selected == 5 or u != me]
            text(cv, 12, y, "目标", 9)
            step = min(105, (w-66)/max(1, len(targets)))
            for i, uid in enumerate(targets):
                rect = 54+i*step, y-12, 49+(i+1)*step, y+10
                button(cv, rect, str(nick(uid))[:7], ui.get("ll_target") == uid)
                ui["ll_hits"].append((*rect, "target", uid))
            y += 25
        if selected == 1:
            text(cv, 12, y, "猜值", 9)
            step = (w-66)/8
            for i in range(8):
                rect = 54+i*step, y-12, 51+(i+1)*step, y+10
                button(cv, rect, f"{i+1}{ROLES[i+1][0]}", ui.get("ll_guess") == i+1)
                ui["ll_hits"].append((*rect, "guess", i+1))
        ready = (selected not in (1, 2, 3, 5, 6) or ui.get("ll_target") is not None) and (selected != 1 or ui.get("ll_guess") is not None)
        rect = w-123, h-30, w-12, h-7
        button(cv, rect, "确认出牌", ready, ready)
        if ready:
            ui["ll_hits"].append((*rect, "confirm", selected))
    else:
        text(cv, 12, y, "伯爵夫人 + 公主：必须先弃伯爵夫人" if forced and active else
             ("点击持牌或新摸牌；选择人物不会立即发牌" if active else "公开弃牌：" + "、".join(f"{ROLES.get(v, v)}{v}" for _, v in discard[-5:])),
             9, MUTED)


def click_lovelove(ui, x, y):
    st, me = ui.get("state") or {}, ui.get("me")
    if not (_member(st, ui, me) and st.get("cur") == me and st.get("status") == "playing" and st.get("winner_uid") is None):
        return
    for *rect, kind, value in ui.get("ll_hits") or []:
        if not hit(rect, x, y):
            continue
        if kind == "play":
            ui.update(ll_play=value, ll_target=None, ll_guess=None)
        elif kind == "target":
            ui["ll_target"] = value
        elif kind == "guess":
            ui["ll_guess"] = value
        else:
            action = {"op": "discard", "play": value}
            if ui.get("ll_target") is not None:
                action["target"] = ui["ll_target"]
            if value == 1 and ui.get("ll_guess") is not None:
                action["val"] = ui["ll_guess"]
            ui["submit"](action)
            ui.update(ll_play=None, ll_target=None, ll_guess=None)
        ui.get("repaint", lambda: None)()
        return
