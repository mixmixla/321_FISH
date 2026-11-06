"""UNO's real card identities and compact illustrated table, without new protocol."""
from boardgames.card_table_tk import art, box, button, hit, text

COLORS = {"red": ("红", "#c43848"), "yellow": ("黄", "#e0b82f"),
          "green": ("绿", "#247759"), "blue": ("蓝", "#376dc6")}
ART = "cards-uno-dealer.webp"


def private_hand(st, me, priv, room=None):
    room = room or {}
    if me not in st.get("players", []) or me in room.get("spectators", []):
        return []
    if room and me not in room.get("players", st.get("players", [])):
        return []
    priv = priv or {}
    hand, ids = priv.get("hand", []), priv.get("hand_ids", [])
    if (not isinstance(hand, list) or not isinstance(ids, list) or len(hand) != len(ids)
            or any(type(cid) is not int or not 0 <= cid < 108 for cid in ids)
            or len(set(ids)) != len(ids) or any(not isinstance(c, str) for c in hand)):
        return []
    legal = priv.get("playable_ids")
    return [(cid, label, cid in legal if isinstance(legal, list) else True)
            for cid, label in zip(ids, hand)]


def active(st, me, room=None):
    room = room or {}
    return (st.get("status") == "playing" and st.get("current_uid") == me
            and me in st.get("players", []) and me not in room.get("spectators", [])
            and (not room or room.get("status", "playing") == "playing"))


def face(cv, rect, label, enabled=True, selected=False, back=False):
    x, y, x1, y1 = rect
    color = next((value for value in COLORS.values() if label.startswith(value[0])), None)
    ink = color[1] if color else "#383650"
    w, h = x1-x, y1-y
    box(cv, rect, "#fcf8e7", "#ffda78" if selected else "#c8d0c0", 3 if selected else 1)
    box(cv, (x+3,y+3,x1-3,y1-3), ink, ink)
    if back:
        box(cv,(x+6,y+6,x1-6,y1-6),"#182b46","#d6be77",2)
        cv.create_polygon(x+w*.5,y+h*.2,x+w*.84,y+h*.48,x+w*.5,y+h*.76,x+w*.16,y+h*.48,
                          fill="#e8dcb5",outline="#fff9da",width=2)
        for i, (_, fill) in enumerate(COLORS.values()):
            cv.create_rectangle(x+w*.28+i*w*.12,y+h*.37,x+w*.38+i*w*.12,y+h*.59,fill=fill,outline="#ffffff")
        text(cv,(x+x1)/2,y1-13,"摸牌",10,"#fff7df","center",True)
    else:
        value=label[1:] if color else label
        symbol={"跳过":"⊘","反转":"⇄","万能":"✦","万能+4":"+4"}.get(value,value)
        if color:
            cv.create_oval(x+w*.14,y+h*.20,x+w*.86,y+h*.79,fill="#fff9e9",outline="#fff9e9",width=2)
            text(cv,(x+x1)/2,(y+y1)/2,symbol,max(20,int(h*.34)),ink,"center",True)
        else:
            for i, (_, fill) in enumerate(COLORS.values()):
                cv.create_arc(x+w*.15,y+h*.23,x+w*.85,y+h*.75,start=i*90,extent=90,
                              fill=fill,outline="#fff9e9",width=1)
            text(cv,(x+x1)/2,(y+y1)/2,"+4" if value=="万能+4" else "✦",max(20,int(h*.28)),"#ffffff","center",True)
        text(cv,x+7,y+13,symbol,max(10,int(h*.13)),"#ffffff",bold=True)
        text(cv,x1-7,y1-13,symbol,max(10,int(h*.13)),"#ffffff","e",True)


def paint(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    room = ui.get("room") or {}
    hand = private_hand(st, me, priv, room)
    can = active(st, me, room) and ui.get("connected", True) and ui.get("uno_sent_state") is not st
    identity = (st.get("round"), st.get("current_uid"), tuple((c, s) for c, s, _ in hand),
                st.get("top"), st.get("top_color"), can)
    if identity != ui.get("uno_identity"):
        ui.pop("uno_wild", None)
    ui.update(game="uno", me=me, state=st, submit=submit, repaint=repaint,
              uno_identity=identity, uno_can=can, uno_hand=hand, uno_hits=[], cards=[],
              _uno_private=priv)
    if ui.get("uno_wild") not in [cid for cid, _, legal in hand if legal]:
        ui.pop("uno_wild", None)
    box(cv, (0, 0, w, h), "#173f38", "#173f38")
    cv.create_oval(10,52,w-10,h-12,fill="",outline="#3d6c5b",width=3)
    title = ("你来出牌" if can else ("旁观中" if me not in st.get("players", [])
             else "等待 " + nick(st.get("current_uid"))))
    if st.get("winner_uid") is not None:
        title = nick(st["winner_uid"]) + " 出完手牌"
    box(cv, (0, 0, w, 43), "#302e4d", "#302e4d")
    text(cv, 14, 22, "UNO · 四色牌宴", 13, "#ffffff", bold=True)
    text(cv, w-14, 22, title, 10, "#f4dc9d", "e", width=max(100, w//2-20))
    count_text = "  ·  ".join(f"{'我' if u == me else nick(u)[:7]} {st.get('hand_counts', {}).get(str(u), 0)}张 / {st.get('scores', {}).get(u, st.get('scores', {}).get(str(u), 0))}分"
                              for u in st.get("players", []))
    text(cv, 14, 59, count_text, 9, "#e8dcb5", width=w-28)
    top_y = 82
    card_h = max(76, min(148, int((h-176)*0.55)))
    card_w = max(54, int(card_h*0.68))
    dx, tx = w/2-card_w-22, w/2+22
    portrait_w=min(74,max(42,dx-32))
    art(cv,ART,0,1,1,(16,top_y+5,16+portrait_w,top_y+5+portrait_w*1.5),contain=True)
    for offset in (6,3):
        box(cv,(dx+offset,top_y+offset,dx+card_w+offset,top_y+card_h+offset),"#21314a","#aebba4")
        box(cv,(tx+offset,top_y+offset,tx+card_w+offset,top_y+card_h+offset),"#c7d1be","#899d88")
    draw_rect = (dx, top_y, dx+card_w, top_y+card_h)
    face(cv, draw_rect, "摸牌", can, back=True)
    face(cv, (tx, top_y, tx+card_w, top_y+card_h), st.get("top") or "?", True)
    if can:
        ui["uno_hits"].append((draw_rect, {"draw": True}))
    text(cv, dx+card_w/2, top_y+card_h+12,
         "牌靴 " + str(st.get("deck_remaining", "?")), 9, "#e8dcb5", anchor="center")
    color = COLORS.get(st.get("top_color"), ("?", "#383650"))
    text(cv, tx+card_w/2, top_y+card_h+12, "弃牌 · 当前 " + color[0] + "色 " + st.get("direction", "→"),
         9, "#f6dfa1", "center", True)
    hand_y = max(top_y+card_h+35, h-140)
    per_page = ui["uno_per_page"] = max(1, int((w-100)//48)+1)
    pages = max(1, (len(hand)+per_page-1)//per_page)
    page = ui["uno_page"] = min(max(0, ui.get("uno_page", 0)), pages-1)
    start = page*per_page
    width, height = 76, min(106, max(68, h-hand_y-40))
    shown = hand[start:start+per_page]
    left = (w-(76+max(0,len(shown)-1)*48))/2
    box(cv,(8,hand_y-20,w-8,h-32),"#12352f","#537765")
    text(cv,18,hand_y-10,"护牌区 · 我的手牌" if hand else "本轮牌桌",8,"#d8ceac")
    for index, (cid, label, legal) in enumerate(shown):
        fan_drop=abs(index-(len(shown)-1)/2)*2
        lifted=12 if ui.get("uno_wild")==cid or ui.get("uno_focus")==cid else 0
        rect = (left+index*48, hand_y+fan_drop-lifted, left+index*48+width, hand_y+height+fan_drop-lifted)
        face(cv, rect, label, can and legal, ui.get("uno_wild") == cid or ui.get("uno_focus") == cid)
        visible=(rect[0],rect[1],rect[0]+(48 if index<len(shown)-1 else width),rect[3])
        if can and legal:
            ui["uno_hits"].append((visible, ("wild", cid) if label.startswith("万能") else {"card": cid}))
            ui["cards"].append((*visible, cid))
    if not hand:
        text(cv, w/2, hand_y+35, "旁观只显示公开牌数" if me not in st.get("players", [])
             else "本轮出完 · 等待下一轮" if st.get("winner_uid") is not None else "等待发牌", 11,"#f5e5b9",anchor="center")
    if pages > 1:
        for rect, label, target in (((12, h-29, 72, h-5), "上一页", page-1),
                                    ((w-72, h-29, w-12, h-5), "下一页", page+1)):
            button(cv, rect, label, enabled=0 <= target < pages)
            if 0 <= target < pages:
                ui["uno_hits"].append((rect, ("page", target)))
    text(cv, w/2, h-16, f"手牌 {page+1}/{pages} · ←→选牌 Enter出牌 D摸牌", 8,"#d8ceac",anchor="center")
    if ui.get("uno_wild") is not None and can:
        # Overlay hit regions replace the hand, so a color click cannot play a card below it.
        ui["uno_hits"] = []
        pw = min(w-20, 362)
        panel = ((w-pw)/2, max(74, hand_y-28), (w+pw)/2, max(74, hand_y-28)+98)
        box(cv, panel, "#fffaf0", "#b18b50", 2)
        text(cv, w/2, panel[1]+17, "万能牌 · 选择下一种颜色", 11, anchor="center", bold=True)
        sw = (pw-20)/5
        for i, (key, (name, ink)) in enumerate(COLORS.items()):
            rect = (panel[0]+10+i*sw, panel[1]+37, panel[0]+6+(i+1)*sw, panel[1]+84)
            box(cv, rect, ink, ink)
            text(cv, (rect[0]+rect[2])/2, (rect[1]+rect[3])/2, name, 11,
                 "#ffffff" if key != "yellow" else "#302e4d", "center", True)
            ui["uno_hits"].append((rect, {"card": ui["uno_wild"], "color": key}))
        rect = (panel[0]+10+4*sw, panel[1]+37, panel[2]-10, panel[1]+84)
        button(cv, rect, "取消")
        ui["uno_hits"].append((rect, ("cancel", None)))


def click(ui, x, y):
    for rect, action in ui.get("uno_hits", []):
        if not hit(rect, x, y):
            continue
        if isinstance(action, tuple):
            op, value = action
            if op == "page":
                ui["uno_page"] = value
            elif op == "wild":
                ui["uno_wild"] = value
            else:
                ui.pop("uno_wild", None)
            ui["repaint"]()
        elif ui.get("uno_can") and active(ui.get("state", {}), ui.get("me"), ui.get("room")):
            # The first packet consumes all current hit regions until fresh state arrives.
            ui["uno_hits"] = []
            ui["uno_sent_state"] = ui["state"]
            ui.pop("uno_wild", None)
            ui["submit"](action)
        return


def key(ui, name):
    if ui.get("game") != "uno":
        return None
    if name in ("Left", "Right") and ui.get("uno_hand") and "uno_wild" not in ui:
        ids = [cid for cid, _, _ in ui["uno_hand"]]
        current = ids.index(ui["uno_focus"]) if ui.get("uno_focus") in ids else (-1 if name == "Right" else 0)
        ui["uno_focus"] = ids[(current+(1 if name == "Right" else -1)) % len(ids)]
        ui["uno_page"] = ids.index(ui["uno_focus"])//ui["uno_per_page"]
        ui["repaint"]()
    else:
        wanted = None
        if name.lower() == "d":
            wanted = {"draw": True}
        elif name == "Escape":
            wanted = ("cancel", None)
        elif name.lower() in ("r", "y", "g", "b") and "uno_wild" in ui:
            wanted = {"card": ui["uno_wild"], "color": dict(r="red", y="yellow", g="green", b="blue")[name.lower()]}
        elif name in ("Return", "space"):
            cid = ui.get("uno_focus")
            wanted = next((a for _, a in ui.get("uno_hits", [])
                           if (isinstance(a, dict) and a.get("card") == cid)
                           or a == ("wild", cid)), None)
        if wanted is not None:
            rect = next((r for r, a in ui.get("uno_hits", []) if a == wanted), None)
            if rect:
                click(ui, (rect[0]+rect[2])/2, (rect[1]+rect[3])/2)
    return "break"


def bind_keys(cv, ui):
    def pressed(event):
        if event.widget.focus_get() is cv:
            return key(ui, event.keysym)
        return None
    cv.bind("<KeyPress>", pressed, add="+")
