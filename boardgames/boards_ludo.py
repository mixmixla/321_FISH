"""Cloud airports: four real aprons, forty curved stops and movable aircraft."""
from collections import defaultdict
import math
from boardgames.card_table_tk import art, text, hit

COLORS = ("#bf3546", "#2764c9", "#18866c", "#d59a21")
ART, MAP = "ludo-aviators.webp", "ludo-cloud-airports.webp"


def ring(index, w=1000, h=700):
    value = index % 40
    side, t = int(value//10), (value % 10)/10
    ports = ((.31,.27),(.69,.27),(.69,.73),(.31,.73))
    controls = ((.5,.02),(.97,.5),(.5,.98),(.03,.5))
    a,b,c = ports[side],controls[side],ports[(side+1)%4]
    return (w*((1-t)**2*a[0]+2*(1-t)*t*b[0]+t*t*c[0]),
            h*((1-t)**2*a[1]+2*(1-t)*t*b[1]+t*t*c[1]))


def parking(pi, idx, w, h):
    x,y = ((.17,.235),(.83,.235),(.83,.815),(.17,.815))[pi % 4]
    pitch = min(w/17,h/13)
    return x*w+(idx % 2-.5)*pitch,y*h+(idx//2-.5)*pitch


def can_act(st, me, room=None, connected=True):
    room = room or {}
    return (connected is not False and me in st.get("players",[]) and me in room.get("players",st.get("players",[]))
            and me not in room.get("spectators",[]) and not (st.get("common") or {}).get("ended")
            and room.get("status","playing") == "playing" and st.get("status","playing") == "playing"
            and st.get("winner_uid") is None and st.get("turn_uid") == me)


def movable(st, me):
    if not can_act(st,me) or st.get("dice") is None:
        return []
    start,dice = st.get("starts",{}).get(str(me),0),st["dice"]
    return [i for i,v in enumerate(st.get("positions",{}).get(str(me),[]))
            if (v == -1 and dice == 6) or (type(v) is int and v >= 0 and (v-start) % 40+dice <= 40)]


def aircraft(cv,x,y,r,color,idx,enabled=False,done=False,ghost=False):
    if enabled:
        cv.create_oval(x-r-3,y-r-3,x+r+3,y+r+3,fill="#ffe289",outline="#ce9124",width=2)
    if ghost:
        cv.create_oval(x-r-3,y-r-3,x+r+3,y+r+3,fill="",outline="#f3bf35",width=2,dash=(3,2))
    points=(x,y-r,x+r*.22,y-r*.12,x+r,y+r*.23,x+r,y+r*.48,x+r*.22,y+r*.25,
            x+r*.18,y+r*.65,x+r*.43,y+r*.84,x+r*.43,y+r,x-r*.43,y+r,
            x-r*.43,y+r*.84,x-r*.18,y+r*.65,x-r*.22,y+r*.25,x-r,y+r*.48,
            x-r,y+r*.23,x-r*.22,y-r*.12)
    cv.create_polygon(*[p+2 for p in points],fill="#5b797d",outline="",stipple="gray50")
    cv.create_polygon(*points,fill="#fffef1" if ghost else color,outline="#fff8da",width=1.5)
    cv.create_line(x,y-r*.82,x,y+r*.72,fill="#fffdf1",width=max(2,r*.32))
    cv.create_oval(x-r*.13,y-r*.65,x+r*.13,y-r*.25,fill="#24435c",outline="")
    text(cv,x,y+r*.22,idx+1,max(8,int(r*.68)),color if ghost else "#233c51","center",True)
    if done:
        cv.create_oval(x+r*.25,y+r*.42,x+r*1.15,y+r*1.3,fill="#ebffe8",outline="#25815d")
        text(cv,x+r*.7,y+r*.86,"✓",8,"#25815d","center",True)


def path(cv,points,color,width=3,dash=None):
    if len(points)>1:
        kw=dict(fill=color,width=width,capstyle="round",joinstyle="round")
        if dash: kw["dash"]=dash
        cv.create_line(*[v for p in points for v in p],**kw)


def paint(cv,st,me,nick,submit,repaint,ui,priv,w,h):
    ui.update(game="ludo",me=me,ludo_hits=[],ludo_planes=[],ludo_state=st,ludo_context=ui.get("_room_context"),tokens=[])
    ui["repaint"]=repaint
    ui.pop("_hover",None)
    cv.create_rectangle(0,0,w,h,fill="#70cee8",outline="")
    art(cv,MAP,0,1,1,(0,0,w,h))
    players,positions=st.get("players",[]),st.get("positions",{})
    active=can_act(st,me,ui.get("room"),ui.get("connected",True))
    moves=movable(st,me) if active else []
    r=max(11,min(17,w/30,h/24))
    line=[ring(i/3,w,h) for i in range(121)]
    path(cv,line,"#388aa7",max(17,r*1.8));path(cv,line,"#fff6da",max(13,r*1.45));path(cv,line,"#c7b878",1,(2,5))
    for i in range(40):
        x,y=ring(i,w,h);sr=max(4,r*.40);color=COLORS[i//10]
        if i % 10 == 0:
            cv.create_oval(x-r*.75,y-r*.75,x+r*.75,y+r*.75,fill=color,outline="#fff4c6",width=2)
            text(cv,x,y,"»",max(9,int(r)),"#fffdf2","center",True)
        else:
            cv.create_polygon(x,y-sr,x+sr,y,x,y+sr,x-sr,y,fill=color if i % 5 == 0 else "#fffdf1",outline=color,width=1)
    for pi in range(4):
        uid=players[pi] if pi<len(players) else None
        cx,cy=((.17,.235),(.83,.235),(.83,.815),(.17,.815))[pi];x,y=cx*w,cy*h
        portrait=min(22,w/23)
        if uid is not None:
            art(cv,ART,pi,2,2,(x-portrait/2,y-r*2.7-portrait/2,x+portrait/2,y-r*2.7+portrait/2))
            if uid==st.get("turn_uid") and st.get("winner_uid") is None:
                cv.create_polygon(x+portrait/2+2,y-r*2.7-7,x+portrait/2+11,y-r*2.7,x+portrait/2+2,y-r*2.7+7,fill="#ffda4e",outline="#946521")
            label="你" if uid==me else str(nick(uid))[:5]
        else: label="空港"
        text(cv,x,y+r*2.7,label,8,COLORS[pi],"center",True)
    groups=defaultdict(list)
    for pi,uid in enumerate(players):
        for idx,value in enumerate(positions.get(str(uid),[])):
            if value==-1 or value=="FIN":
                x,y=parking(pi,idx,w,h);enabled=uid==me and idx in moves
                aircraft(cv,x,y,r,COLORS[pi],idx,enabled,value=="FIN")
                if enabled: ui["ludo_planes"].append((x-r-3,y-r-3,x+r+3,y+r+3,idx))
            elif type(value) is int: groups[value % 40].append((pi,uid,idx))
    for stall,tokens in groups.items():
        x,y=ring(stall,w,h);cols=math.ceil(math.sqrt(len(tokens)));rows=math.ceil(len(tokens)/cols)
        for k,(pi,uid,idx) in enumerate(tokens):
            sx,sy=x+(k % cols-(cols-1)/2)*r*1.3,y+(k//cols-(rows-1)/2)*r*1.3
            enabled=uid==me and idx in moves
            aircraft(cv,sx,sy,r*.90,COLORS[pi],idx,enabled)
            if enabled: ui["ludo_planes"].append((sx-r,sy-r,sx+r,sy+r,idx))
    for *rect,idx in ui["ludo_planes"]: ui["ludo_hits"].append((*rect,{"op":"move","idx":idx}))
    pick=ui.get("ludo_hover") if ui.get("ludo_hover") in moves else (moves[0] if moves else None)
    caption="掷出6起飞"
    if pick is not None:
        pi=players.index(me);value=positions[str(me)][pick];start=st.get("starts",{}).get(str(me),pi*10)
        if value==-1:
            dest=ring(start,w,h);trail=[parking(pi,pick,w,h),dest];caption=f"{pick+1}号 · 起飞"
        else:
            target=(value-start) % 40+st["dice"];trail=[ring(value+i,w,h) for i in range(st["dice"]+1)]
            dest=parking(pi,pick,w,h) if target==40 else trail[-1]
            if target==40: trail.append(dest)
            caption=f"{pick+1}号 · 前进{st['dice']}格"+(" · 到达" if target==40 else "")
        path(cv,trail,"#f8d247",3,(4,3));aircraft(cv,*dest,r*.8,COLORS[pi],pick,ghost=True)
    elif isinstance(st.get("last_move"),dict):
        lm=st["last_move"]
        if lm.get("from_stall") is not None and lm.get("steps"):
            path(cv,[ring(lm["from_stall"]+i,w,h) for i in range(lm["steps"]+1)],"#ffe173",4)
        caption=f"{lm.get('idx',0)+1}号 · 已起飞" if lm.get("takeoff") else f"{lm.get('idx',0)+1}号 · 已前进{lm.get('steps','')}格"
    from client_gameui import _die_face
    dx,dy=w*.5,h*.50;ds=max(23,min(32,w*.065))
    cv.create_oval(dx-ds,dy+ds*.5,dx+ds*1.3,dy+ds*1.3,fill="#518da1",outline="",stipple="gray50")
    shown=st.get("dice") if st.get("dice") is not None else st.get("last_roll")
    _die_face(cv,dx,dy,ds,shown,"#345775",blank=shown is None)
    text(cv,dx,dy+ds+11,"掷骰 · R" if st.get("dice") is None else f"骰值 {st['dice']}",9,"#294c66","center",True)
    if active and st.get("dice") is None: ui["ludo_hits"].append((dx-ds-5,dy-ds-5,dx+ds+5,dy+ds+16,{"op":"roll"}))
    text(cv,w/2,dy+ds+32,caption,9,"#234d65","center",True)
    sx,sy=w-28,h-24
    cv.create_oval(sx-15,sy-15,sx+15,sy+15,fill="#edf4d8",outline="#819d7b");text(cv,sx,sy,"↪",15,"#426d56","center",True)
    if active: ui["ludo_hits"].append((sx-15,sy-15,sx+15,sy+15,{"op":"skip"}))
    winner=st.get("winner_uid");role="观战" if me not in players else ""
    title=f"{nick(winner)} 四机到达" if winner is not None else role+" · "+("你行动" if st.get("turn_uid")==me else f"{nick(st.get('turn_uid'))}行动")
    cv.create_rectangle(0,0,w,28,fill="#d8f0f4",outline="",stipple="gray75")
    text(cv,10,14,"飞行棋 · 云岛航线",11,"#21475b",bold=True);text(cv,w-10,14,title.strip(" ·"),9,"#21475b","e")
    text(cv,10,h-11,"点飞机起飞/前进 · R掷骰 · 1–4选机",8,"#21475b")
    if isinstance(getattr(cv,"_w",None),str):
        cv._ludo_ui=ui
        for keyname in ("r","R","1","2","3","4"):
            cv.bind("<KeyPress-"+keyname+">",lambda e,n=keyname:key(cv._ludo_ui,n))
        if not getattr(cv,"_ludo_hover_bound",False):
            cv._ludo_hover_bound=True
            def motion(event):
                target=cv._ludo_ui
                if target.get("game")!="ludo": return
                index=next((r[-1] for r in target.get("ludo_planes",[]) if hit(r[:4],event.x,event.y)),None)
                if index!=target.get("ludo_hover"):
                    target["ludo_hover"]=index;target["repaint"]()
            cv.bind("<Motion>",motion,add="+")


def dispatch(ui,action):
    st=ui.get("state") or {}
    if (ui.get("game")!="ludo" or st is not ui.get("ludo_state") or ui.get("_room_context")!=ui.get("ludo_context")
        or not can_act(st,ui.get("me"),ui.get("room"),ui.get("connected",True))): return
    if action["op"]=="roll" and st.get("dice") is not None: return
    if action["op"]=="move" and action["idx"] not in movable(st,ui.get("me")): return
    ui["submit"](action)


def submit_allowed(core, source_ui, action):
    """Last boundary: inspect Core now, not just the previously painted UI."""
    room,st = core.game_room or {},core.game_state or {}
    uid = core.uid
    if (room.get("game") != "ludo" or st.get("game") != "ludo"
            or not getattr(core,"connected",False) or room.get("status") != "playing"
            or st.get("status") != "playing" or uid not in room.get("players",[])
            or uid not in st.get("players",[]) or uid in room.get("spectators",[])
            or st.get("winner_uid") is not None or (st.get("common") or {}).get("ended")):
        return False
    if source_ui is not None and (
            source_ui.get("game") != "ludo" or source_ui.get("room") is not room
            or source_ui.get("state") is not st or source_ui.get("me") != uid
            or source_ui.get("_room_context") != (room.get("room_id"),room.get("round"))):
        return False
    op = action.get("op")
    if op in ("roll","move","skip"):
        if not can_act(st,uid,room,core.connected):
            return False
        if op == "roll":
            return st.get("dice") is None
        if op == "move":
            return type(action.get("idx")) is int and action["idx"] in movable(st,uid)
        return True
    # Common room actions retain their server-defined off-turn semantics.
    return op in ("resign","undo","draw","draw_accept","draw_reject")


def click(ui,x,y):
    for *rect,action in sorted(ui.get("ludo_hits",[]),key=lambda r:(x-(r[0]+r[2])/2)**2+(y-(r[1]+r[3])/2)**2):
        if hit(rect,x,y): dispatch(ui,action);return


def key(ui,value):
    dispatch(ui,{"op":"roll"} if value.lower()=="r" else {"op":"move","idx":int(value)-1})
    return "break"


from boardgames.registry import GamePackage,register
register(GamePackage(name="ludo",label="飞行棋 · 云岛航线",rules="games_pkg.ludo:LudoGame",
    desktop="boardgames.boards_ludo:paint",web_js="boardgames.boards_ludo_web:WEB_JS",web_css="boardgames.boards_ludo_web:WEB_CSS"))
