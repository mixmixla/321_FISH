"""Physical poker cards lead; Joker scenes are passive, inspectable companions."""
import math
from boardgames.card_table_tk import art, box, text, hit
from boardgames.jokers.catalog import JOKERS

INK="#243e3b"
CREAM="#fff8e7"
GOLD="#d8ad55"
SUITS={"h":"♥","s":"♠","d":"♦","c":"♣"}


def member(ui):
    st, room, me = ui.get("state") or {}, ui.get("room") or {}, ui.get("me")
    return (me in room.get("players", st.get("players", [])) and me in st.get("players", [])
            and me not in room.get("spectators", []))


def private(ui):
    st, me = ui.get("state") or {}, ui.get("me")
    pv = ui.get("_jt_private") or {}
    if ((ui.get("room") or {}).get("status") != "playing" or not member(ui)
            or pv.get("owner_uid", me) != me or pv.get("game", st.get("game")) != st.get("game")):
        return {}
    return pv


def active(ui):
    st, room, me = ui.get("state") or {}, ui.get("room") or {}, ui.get("me")
    return (ui.get("game") == "balatro" and bool(ui.get("connected"))
            and room.get("status") == "playing" and st.get("game") == "balatro"
            and st.get("turn_uid", st.get("turn")) == me and me in st.get("alive", [])
            and st.get("winner") is None and not st.get("done") and bool(private(ui)))


def _stamp(ui):
    return id(ui.get("state")), id(ui.get("_jt_private")), ui.get("_room_context"), ui.get("me")


def send(ui, action):
    if not active(ui) or ui.get("jt_busy") == _stamp(ui):
        return
    pv=private(ui);cards={c["id"]:c for c in pv.get("hand", [])};sel=pv.get("sel") or []
    op, cid=action.get("op"),action.get("cid")
    if op == "select" and (cid not in cards or cid in sel or len(sel)>=5):return
    if op == "unselect" and cid not in sel:return
    if op == "discard" and (cid not in cards or cid in sel or int((ui["state"].get("discards_left") or {}).get(str(ui["me"]), 3))<=0):return
    if op == "play" and not sel:return
    if op not in ("select","unselect","discard","play"):return
    ui["jt_busy"]=_stamp(ui)
    result=ui.get("submit",lambda action:False)(action)
    if result is False:ui.pop("jt_busy",None)
    ui.get("repaint",lambda:None)()


def _poker(cv, card, rect, selected=False, focused=False):
    x0,y0,x1,y1=rect;w,h=x1-x0,y1-y0
    box(cv,rect,CREAM,"#32b9a3" if selected else GOLD if focused else "#b6a781",3 if selected or focused else 1)
    cv.create_rectangle(x0+3,y0+3,x1-3,y1-3,outline="#e1d1a4",tags="jt-playing-card")
    rank={"T":"10"}.get(card.get("c"),card.get("c","?"));suit=SUITS.get(card.get("s"),"?")
    color="#b33548" if card.get("s") in ("h","d") else "#233c3b"
    text(cv,x0+5,y0+6,rank,max(9,int(w*.19)),color,anchor="nw",bold=True)
    text(cv,x1-5,y0+6,suit,max(10,int(w*.22)),color,anchor="ne")
    text(cv,(x0+x1)/2,y0+h*.43,rank,max(16,int(h*.28)),color,"center",True)
    text(cv,(x0+x1)/2,y0+h*.73,suit,max(16,int(h*.25)),color,"center")
    badges=[{"foil":"箔","holo":"全","poly":"彩"}.get(card.get("edt")),
            {"bonus":"珠","mult":"曙","face":"庆","glass":"璃","steel":"钢","stone":"石"}.get(card.get("enh")),
            {"red":"赤","gold":"金","purple":"紫"}.get(card.get("seal"))]
    label="·".join(b for b in badges if b)
    if label:text(cv,x0+4,y1-6,label,7,"#685188",anchor="sw",bold=True)


def _pile(cv,rect,label,sub,chosen=False):
    x0,y0,x1,y1=rect
    for offset in (5,2,0):
        box(cv,(x0+offset,y0+offset,x1+offset,y1+offset),"#fff7dd","#98703e")
    box(cv,(x0+4,y0+4,x1-4,y1-4),"#8d4056" if chosen else "#2d6059",GOLD,2)
    text(cv,(x0+x1)/2,y0+(y1-y0)*.36,label,11,"#fff8dc","center",True)
    text(cv,(x0+x1)/2,y0+(y1-y0)*.72,sub,8,"#fff2ca","center")


def _bind(cv,ui):
    if not isinstance(getattr(cv,"_w",None),str) or getattr(cv,"_jt_keys",False):return
    cv._jt_keys=True
    for name in ("Left","Right","space","Return","KP_Enter","Delete","Escape"):
        cv.bind("<"+name+">",lambda e,k=name:key(ui,k),add="+")


def key(ui,name):
    if ui.get("game")!="balatro":return
    if name=="Escape":
        ui.pop("jt_inspect",None);ui["jt_discard_mode"]=False;ui.get("repaint",lambda:None)();return "break"
    if ui.get("jt_inspect") or not active(ui):return
    hand=private(ui).get("hand") or []
    if name in ("Left","Right") and hand:
        ui["jt_key_index"]=(ui.get("jt_key_index",-1 if name=="Right" else 0)+(1 if name=="Right" else -1))%len(hand)
        ui.get("repaint",lambda:None)()
    elif name=="Delete":
        ui["jt_discard_mode"]=not ui.get("jt_discard_mode");ui.get("repaint",lambda:None)()
    elif name=="space" and hand:
        card=hand[ui.get("jt_key_index",0)%len(hand)];cid=card["id"]
        op="unselect" if cid in (private(ui).get("sel") or []) else "discard" if ui.get("jt_discard_mode") else "select"
        send(ui,{"op":op,"cid":cid})
    elif name in ("Return","KP_Enter"):send(ui,{"op":"play"})
    return "break"


def click(ui,x,y):
    if ui.get("game")!="balatro":return
    for *rect,kind,value in ui.get("jt_hits") or []:
        if not hit(rect,x,y):continue
        if kind=="close":ui.pop("jt_inspect",None)
        elif kind=="inspect":ui["jt_inspect"]=value
        elif kind=="discard_mode":
            if active(ui):ui["jt_discard_mode"]=not ui.get("jt_discard_mode")
        elif kind=="card":
            cid=value;sel=private(ui).get("sel") or []
            op="unselect" if cid in sel else "discard" if ui.get("jt_discard_mode") else "select"
            send(ui,{"op":op,"cid":cid});return
        elif kind=="unselect":send(ui,{"op":"unselect","cid":value});return
        elif kind=="play":send(ui,{"op":"play"});return
        ui.get("repaint",lambda:None)();return


def paint(cv,st,me,nick,submit,repaint,ui,priv,w,h):
    ui.update(game="balatro",_jt_private=priv)
    _bind(cv,ui)
    context=(ui.get("_room_context"),me,st.get("blind"))
    if ui.get("jt_context")!=context:
        ui.update(jt_context=context,jt_discard_mode=False,jt_key_index=0);ui.pop("jt_inspect",None)
    ui["jt_hits"]=[]
    pv=private(ui);hand=pv.get("hand") or [];sel=pv.get("sel") or []
    myturn=active(ui);compact=h<480
    finished=st.get("done") or (ui.get("room") or {}).get("status")=="ended"
    box(cv,(0,0,w,h),"#16463f","#16463f")
    box(cv,(0,0,w,34),"#102f2e",GOLD)
    title=f"小丑牌 · 第 {st.get('blind',1)} 盲注"
    if finished:title=f"{nick(st.get('winner'))} 获胜" if st.get("winner") is not None else "本局已结束"
    elif st.get("turn_uid") is not None:title+=" · "+("你的回合" if myturn else "轮到 "+str(nick(st['turn_uid'])))
    text(cv,12,17,title,11,"#fff4ce",bold=True)
    players=st.get("players") or [];cols=max(1,int(w//145));seat_h=28*math.ceil(max(1,len(players))/cols)
    for i,uid in enumerate(players):
        col,row=i%cols,i//cols;sw=w/cols
        x,y=col*sw+8,47+row*28
        text(cv,x,y,f"{str(nick(uid))[:6]}  ♥{(st.get('hp') or {}).get(str(uid),0)}  ◉{(st.get('score') or {}).get(str(uid),0)}",8,"#fff2ce" if uid==st.get("turn_uid") else "#bed3c6")
    arena_y=42+seat_h;arena_h=82 if compact else min(138,h*.23)
    area=(12,arena_y,w-104,arena_y+arena_h)
    box(cv,area,"#1c5148","#63846a")
    selected=[c for c in hand if c["id"] in sel]
    last=st.get("last_play") or {};shown=selected or last.get("cards") or []
    caption=(pv.get("preview") or {}).get("name", "选牌入台") if selected else (f"上次结算 · {nick(last['uid'])} · {last.get('name','')} +{last.get('points',0)}" if last else "点选手牌，最多 5 张入台")
    text(cv,area[0]+7,area[1]+10,caption,8,"#f6e3ae",bold=True)
    ch=arena_h-26;cw=min(72,ch*.7,(area[2]-area[0]-30)/5)
    start=(area[0]+area[2]-len(shown)*(cw+5)+5)/2
    for i,card in enumerate(shown):
        rect=(start+i*(cw+5),arena_y+22,start+i*(cw+5)+cw,arena_y+22+ch)
        _poker(cv,card,rect,bool(selected))
        if selected and myturn:ui["jt_hits"].append((*rect,"unselect",card["id"]))
    pile=(w-88,arena_y+4,w-18,arena_y+arena_h-4)
    left=(st.get("discards_left") or {}).get(str(me))
    _pile(cv,pile,"弃牌堆",f"余 {left} 次" if left is not None and member(ui) and not finished else "只读",ui.get("jt_discard_mode"))
    if myturn:ui["jt_hits"].append((*pile,"discard_mode",None))
    jy=arena_y+arena_h+12;jh=66 if compact else min(133,h*.23)
    owned=(st.get("jokers") or {}).get(str(me),[]) if member(ui) else []
    for i,jid in enumerate(owned):
        item=JOKERS.get(jid,{"name":jid,"desc":""});x=12+i*min(215,(w-145)/max(1,len(owned)))
        width=min(203,(w-145)/max(1,len(owned))-8);rect=(x,jy,x+width,jy+jh)
        box(cv,rect,"#fff3d5","#c69a56")
        aw=min(jh*.72,width*.43)
        if item.get("file"):art(cv,item["file"],item["index"],4,2,(x+3,jy+3,x+aw,jy+jh-3),contain=True)
        text(cv,x+aw+6,jy+16,item["name"],8,INK,bold=True,width=max(25,width-aw-10))
        text(cv,x+aw+6,jy+39,item["desc"],7,"#775a38",width=max(25,width-aw-10))
        ui["jt_hits"].append((*rect,"inspect",jid))
    target=(st.get("blind_targets") or {}).get(str(me))
    px=w-123;py=jy+5
    cv.create_oval(px,py,px+104,py+50,fill="#e9c871",outline="#fff1bb",width=2)
    text(cv,px+52,py+15,"本局结束" if finished else "结算台",10,INK,"center",True)
    plays=(st.get("plays_left") or {}).get(str(me),"—")
    text(cv,px+52,py+34,"回看公开结算" if finished else f"目标 {target} · 余{plays}手" if target is not None else "仅本人操作",8,INK,"center")
    if myturn and sel:ui["jt_hits"].append((px,py,px+104,py+50,"play",None))
    hy=max(jy+jh+15,h-(92 if compact else 155));hh=max(52,min(h-hy-16,130))
    if hand:
        gap=5;hcw=min(91,(w-24-gap*(len(hand)-1))/len(hand));hch=min(hh,hcw*1.45)
        sx=(w-(hcw+gap)*len(hand)+gap)/2
        instruction="弃牌模式：点未出战手牌弃掉并补抽" if ui.get("jt_discard_mode") else "我的手牌 · 点选入台 / 再点撤回"
        text(cv,12,hy-8,instruction,8,"#f4e7c8")
        for i,card in enumerate(hand):
            on=card["id"] in sel;dy=-5 if on else 0
            rect=(sx+i*(hcw+gap),hy+dy,sx+i*(hcw+gap)+hcw,hy+dy+hch)
            _poker(cv,card,rect,on,i==ui.get("jt_key_index") and myturn)
            if myturn:ui["jt_hits"].append((*rect,"card",card["id"]))
    else:text(cv,w/2,hy+20,"本局已结束 · 仅保留公开结算牌" if finished else "私人手牌仅本人可见" if not pv else "本盲注手牌已打完",11,"#d2d9ba","center")
    text(cv,12,h-7,"←→选牌 · 空格入台/撤回 · Delete切换弃牌 · Enter结算 · Esc取消",7,"#b7cdbd",anchor="sw")
    inspect=JOKERS.get(ui.get("jt_inspect"))
    if inspect:
        box(cv,(0,34,w,h),"#123b35","#123b35")
        ah=max(100,h-122);aw=ah*.75;x=(w-aw)/2
        art(cv,inspect["file"],inspect["index"],4,2,(x,48,x+aw,48+ah),contain=True)
        text(cv,w/2,h-56,inspect["name"],12,"#ffe3a3","center",True)
        text(cv,w/2,h-35,inspect["desc"],9,"#fff2d8","center")
        text(cv,w-14,50,"返回 ×",10,"#fff2d8","ne",True)
        ui["jt_hits"]=[(w-90,35,w,70,"close",None)]
