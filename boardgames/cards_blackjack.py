"""Blackjack's live felt, dealer, shoe and stop chip."""
from boardgames.card_table_tk import art, box, button, hit, text

ART = "cards-blackjack-dealer.webp"
INK, GOLD, FELT = "#f7f1dc", "#e4bd69", "#155345"
RESULTS = {"win": "胜 +1", "lose": "负", "push": "平", "blackjack": "21点"}


def active(st, me, room=None):
    room = room or {}
    return (st.get("status") == "playing" and st.get("current_uid") == me
            and me in st.get("players", []) and me not in room.get("spectators", [])
            and (not room or room.get("status", "playing") == "playing"))


def card(cv, rect, label, hidden=False):
    x, y, x1, y1 = rect
    box(cv, rect, "#fffdf7", "#b5b89a")
    if hidden or label == "背牌":
        art(cv, ART, 0, 1, 1, (x+3, y+3, x1-3, y1-3))
        box(cv, (x+3, y1-22, x1-3, y1-3), "#254d43", "#254d43")
        text(cv, (x+x1)/2, y1-13, "暗牌", 9, INK, "center")
        return
    suit = label[-1:] or "?"
    rank = label[:-1] or "?"
    color = "#b83146" if suit in ("♥", "♦") else "#20322d"
    text(cv, x+6, y+12, rank, 11, color, bold=True)
    text(cv, (x+x1)/2, (y+y1)/2+5, suit, max(14, int((y1-y)*.32)), color, "center", True)
    text(cv, x1-6, y1-12, rank, 9, color, "e", True)


def paint(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    members = st.get("players", [])
    chosen = ui.get("bj_view", me if me in members else (members[0] if members else None))
    if chosen not in members:
        chosen = me if me in members else (members[0] if members else None)
    can = active(st, me, ui.get("room")) and ui.get("connected", True) and ui.get("bj_sent_state") is not st
    ui.update(game="blackjack", me=me, state=st, submit=submit, repaint=repaint,
              bj_view=chosen, bj_can=can, bj_hits=[])
    box(cv, (0, 0, w, h), FELT, FELT)
    box(cv, (0, 0, w, 43), "#113c35", "#113c35")
    text(cv, 14, 22, "21点 · 翡翠牌厅", 13, INK, bold=True)
    status = "本轮结算" if st.get("status") == "round_end" else ("你来决定" if can else "等待 " + nick(st.get("current_uid")))
    text(cv, w-14, 22, status, 10, GOLD, "e")
    seat_w = (w-24)/max(1, len(members))
    for i, uid in enumerate(members):
        score = st.get("scores", {}).get(str(uid), st.get("scores", {}).get(uid, 0))
        rect = (12+i*seat_w, 49, 8+(i+1)*seat_w, 75)
        name = "我" if uid == me else (f"{i+1}席" if len(members)>4 else nick(uid)[:5])
        button(cv, rect, name+f" {score}分", selected=uid == chosen)
        if uid == st.get("current_uid"):
            cv.create_line(rect[0]+3, 77, rect[2]-3, 77, fill=GOLD, width=3)
        ui["bj_hits"].append((rect, ("view", uid)))
    art_h = min(123, max(80, int(h*.28)))
    art(cv, ART, 0, 1, 1, (12, 85, 12+art_h*.67, 85+art_h))
    text(cv, 16+art_h*.67, 91, "庄家 · " + ("明牌 " if st.get("dealer_hidden") else "合计 ")
         + str(st.get("dealer_value", 0)), 10, INK, bold=True)
    dealer = st.get("dealer", [])
    usable = max(70, w-120-art_h*.67)
    cw = min(52, max(28, (usable-6*max(0, len(dealer)-1))/max(1, len(dealer))))
    for i, label in enumerate(dealer):
        x = 16+art_h*.67+i*(cw+6)
        card(cv, (x, 107, x+cw, 107+min(78, art_h-8)), label, label == "背牌")
    shoe = (w-80, 88, w-16, 181)
    box(cv, shoe, "#102f2b", GOLD, 2)
    art(cv, ART, 0, 1, 1, (shoe[0]+4, shoe[1]+4, shoe[2]-4, shoe[3]-25))
    text(cv, w-48, shoe[3]-14, "要牌", 10, INK, "center", True)
    text(cv, w-48, shoe[3]+12, str(st.get("deck_remaining", "?"))+" 张", 8, INK, "center")
    if can:
        ui["bj_hits"].append((shoe, {"action": "hit"}))
    y = max(215, h-120)
    name = "我的手牌" if chosen == me else nick(chosen)+"的明牌"
    value = st.get("hand_values", {}).get(str(chosen), st.get("hand_values", {}).get(chosen, 0))
    result = st.get("results", {}).get(str(chosen), st.get("results", {}).get(chosen))
    note = RESULTS.get(result) if result else ("爆牌" if value > 21 else "已停牌" if chosen in st.get("stand", []) else "")
    text(cv, 12, y-13, name+f" · {value}点"+(" · "+note if note else ""), 10, GOLD, bold=True)
    hand = st.get("hands", {}).get(str(chosen), st.get("hands", {}).get(chosen, []))
    per_page = max(1, int((w-118)//58))
    pages = max(1, (len(hand)+per_page-1)//per_page)
    page = ui["bj_page"] = min(max(0, ui.get("bj_page", 0)), pages-1)
    for i, label in enumerate(hand[page*per_page:(page+1)*per_page]):
        card(cv, (12+i*58, y, 64+i*58, min(h-28, y+78)), label)
    sx, sy, r = w-51, min(h-72, y+35), 28
    cv.create_oval(sx-r, sy-r, sx+r, sy+r, fill="#f0dfb4" if can else "#a6b8a4", outline=GOLD, width=3)
    cv.create_oval(sx-r+6, sy-r+6, sx+r-6, sy+r-6, outline="#345344", width=2)
    text(cv, sx, sy, "停牌", 11, "#183e32", "center", True)
    if can:
        ui["bj_hits"].append(((sx-r, sy-r, sx+r, sy+r), {"action": "stand"}))
    if pages > 1:
        for rect, label, target in (((12,h-25,65,h-3),"上一页",page-1),((w-165,h-25,w-112,h-3),"下一页",page+1)):
            button(cv,rect,label,enabled=0 <= target < pages)
            if 0 <= target < pages: ui["bj_hits"].append((rect,("page",target)))
    text(cv,w/2,h-14,f"手牌 {page+1}/{pages} · H要牌 / S停牌",8,INK,"center")


def click(ui, x, y):
    for rect, action in ui.get("bj_hits", []):
        if not hit(rect,x,y): continue
        if isinstance(action,tuple):
            if action[0] == "view": ui["bj_view"] = action[1]; ui["bj_page"] = 0
            else: ui["bj_page"] = action[1]
            ui["repaint"]()
        elif ui.get("bj_can") and active(ui.get("state",{}),ui.get("me"),ui.get("room")):
            ui["bj_sent_state"] = ui["state"]
            ui["bj_hits"] = [(r,a) for r,a in ui["bj_hits"] if isinstance(a,tuple)]
            ui["submit"](action)
        return


def bind_keys(cv,ui):
    def pressed(event):
        if ui.get("game") != "blackjack" or event.widget.focus_get() is not cv: return None
        op = {"h":"hit","s":"stand"}.get(event.keysym.lower())
        rect = next((r for r,a in ui.get("bj_hits",[]) if a == {"action":op}),None)
        if rect: click(ui,(rect[0]+rect[2])/2,(rect[1]+rect[3])/2)
        return "break" if op else None
    cv.bind("<KeyPress>",pressed,add="+")
