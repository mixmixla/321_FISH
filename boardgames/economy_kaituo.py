"""Kaituo tabletop and its shared desktop send boundary."""
import json
from uuid import uuid4
from games_pkg.kaituo import RES_COST, RES_ORDER, SIZE
from boardgames.card_table_tk import text
from boardgames.kaituo_objects import LAND, HARBOUR, GOODS, MODELS, die, sprite

NAMES = dict(zip(RES_ORDER, ("木材", "砖块", "羊", "麦穗", "矿石")))
MODELS_NAMES = {"road": "道路", "settle": "村庄", "city": "城市"}
OWNERS = ("#a53e37", "#3b668e", "#31776b", "#8e6131")
INK, MUTED, TEAL = "#233d43", "#49666a", "#236e66"
PAPER, LIGHT, BORDER = "#eef1e8", "#fffbf1", "#c3cbbc"


def _frame(core, room, state):
    revision = state.get("action_seq")
    if revision is None:
        revision = json.dumps(state, sort_keys=True, ensure_ascii=False)
    return (room.get("room_id"), room.get("round"), core.uid,
            getattr(core, "connection_epoch", None), revision)


def sync_pending(host, room, state):
    pending = getattr(host, "_kt_pending", None)
    if pending and (not host.core.connected or pending[0] != _frame(host.core, room, state)):
        host._kt_pending = None
    return bool(getattr(host, "_kt_pending", None))


def reject_action(host, request):
    pending = getattr(host, "_kt_pending", None)
    if pending and pending[1] == request:
        host._kt_pending = None
        host._render_canvas()


def submit_action(host, room, state, ui, action):
    core = host.core
    uid = core.uid
    if (not ui or room.get("game") != "kaituo" or ui.get("game") != "kaituo"
            or ui.get("_room_context") != (room.get("room_id"), room.get("round"))
            or ui.get("state") is not state or ui.get("me") != uid
            or not _my_turn(room, state, uid, core.connected) or sync_pending(host, room, state)):
        return False
    request = uuid4().hex
    pending = (_frame(core, room, state), request)
    host._kt_pending = pending
    sent = core.game_action(room["room_id"], {**action, "_kt_request": request})
    if not sent and host._kt_pending == pending:
        host._kt_pending = None
    repaint = ui.get("repaint")
    if repaint:
        repaint()
    return sent


def _my_turn(room, state, uid, connected=True):
    return (connected and room.get("status") == "playing" and state.get("status") == "playing"
            and state.get("winner_uid") is None and state.get("turn_uid") == uid
            and uid in room.get("players", ()) and uid not in room.get("spectators", ())
            and uid in state.get("players", ()))


def _key(point):
    return f"{point[0]},{point[1]}"


def _neighbours(point):
    r, c = point
    return [(r+dr, c+dc) for dr, dc in ((0,1),(0,-1),(1,0),(-1,0))
            if 0 <= r+dr <= SIZE and 0 <= c+dc <= SIZE]


def _edge(a, b):
    return ">".join(_key(point) for point in sorted((a,b)))


def legal_targets(state, uid, model, start=None):
    """Use the same adjacency, ownership and tariffs as the authoritative game."""
    board, roads = state.get("board", {}), state.get("roads", {})
    all_points = [(r,c) for r in range(SIZE+1) for c in range(SIZE+1)]
    if state.get("robber_pending"):
        return [], []
    def free(point):
        return _key(point) not in board and all(_key(p) not in board for p in _neighbours(point))
    if state.get("phase") == "setup":
        if start is None:
            return [p for p in all_points if free(p)], []
        edges = [(start, p) for p in _neighbours(start) if _edge(start,p) not in roads]
        return [start], edges
    stock = state.get("res", {}).get(str(uid), {})
    if model not in RES_COST or not state.get("rolled") or any(stock.get(k,0)<n for k,n in RES_COST[model].items()):
        return [], []
    anchors = {k for k, value in board.items() if value["owner"] == uid}
    for key, owner in roads.items():
        if owner == uid:
            anchors.update(key.split(">"))
    if model == "road":
        edges = [(a,b) for a in all_points for b in _neighbours(a) if a < b
                 and (_key(a) in anchors or _key(b) in anchors) and _edge(a,b) not in roads]
        return [], edges
    if model == "city":
        return [p for p in all_points if _key(p) in board and board[_key(p)]["owner"] == uid
                and not board[_key(p)]["city"]], []
    return [p for p in all_points if free(p) and any(_key(q) in anchors for q in _neighbours(p))], []


def click(ui, x, y):
    state = ui.get("state")
    if state is not ui.get("kt_frame"):
        return
    for rect, target in reversed(ui.get("kt_hits", ())):
        if not (rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]):
            continue
        kind, value = target
        if kind == "tab":
            ui["kt_tab"] = value
        elif not _my_turn(ui.get("room") or {}, state, ui.get("me"), ui.get("connected", False)) or ui.get("kt_pending"):
            return
        elif kind in ("model", "give", "want"):
            ui["kt_" + kind] = value
        elif kind == "vertex" and state["phase"] == "setup":
            ui["kt_start"] = None if ui.get("kt_start") == value else value
        else:
            if kind == "edge":
                a,b = value
                action = {"op": "setup" if state["phase"] == "setup" else "build",
                          "i": a[0], "j": a[1], "b_i": b[0], "b_j": b[1]}
                if action["op"] == "build":
                    action["kind"] = "road"
            elif kind == "vertex":
                action = {"op":"build", "kind":ui["kt_model"], "i":value[0], "j":value[1]}
            elif kind == "land":
                action = {"op":"robber", "r":value[0], "c":value[1]}
            elif kind == "trade":
                action = {"op":"trade", "give":ui["kt_give"], "want":ui["kt_want"], "n":4}
            else:
                action = {"op":kind}
            ui["submit"](action)
            return
        ui["repaint"]()
        return


def _bind_keys(canvas, ui):
    if not isinstance(getattr(canvas, "_w", None), str) or getattr(canvas,"_kt_keys",False):
        return
    canvas._kt_keys = True
    canvas.configure(takefocus=True)
    def key(event):
        if ui.get("game") != "kaituo" or not ui.get("kt_hits"):
            return None
        hits = ui["kt_hits"]
        index = ui.get("kt_focus", 0) % len(hits)
        if event.keysym in ("Return", "KP_Enter", "space"):
            rect = hits[index][0]
            click(ui, (rect[0]+rect[2])/2, (rect[1]+rect[3])/2)
        else:
            ui["kt_focus"] = (index+(1 if event.keysym in ("Right","Down") else -1)) % len(hits)
            ui["kt_show_focus"] = True
            ui["repaint"]()
        return "break"
    for key_name in ("Up","Down","Left","Right","Return","KP_Enter","space"):
        canvas.bind(f"<{key_name}>", key, add="+")


def _owner(state, uid):
    players = state.get("players", ())
    return OWNERS[players.index(uid) % len(OWNERS)] if uid in players else "#758581"


def _panel(canvas, rect, fill=LIGHT, border=BORDER):
    canvas.create_rectangle(*rect, fill=fill, outline=border, width=1)


def _hit(ui, rect, kind, value=None, enabled=True):
    if enabled:
        ui["kt_hits"].append((rect, (kind,value)))


def _resource(canvas, kind, rect):
    sprite(canvas, GOODS, RES_ORDER.index(kind), rect)


def _map(canvas, state, me, ui, rect, can_act):
    x, y, x1, y1 = rect
    cell = (x1-x)/SIZE
    _panel(canvas,(x-6,y-6,x1+6,y1+6),"#cedbd0","#8fa79b")
    live_production = {(entry["r"],entry["c"]) for entry in state.get("production", ()) if state.get("rolled")}
    robber = tuple(state.get("robber", ()))
    for coord, land in state["tiles"].items():
        r,c = map(int,coord.split(","))
        cell_rect = (x+c*cell+1,y+r*cell+1,x+(c+1)*cell-1,y+(r+1)*cell-1)
        material = land["res"]
        sprite(canvas,LAND,RES_ORDER.index(material) if material in RES_ORDER else 5,cell_rect)
        if (r,c) in live_production:
            canvas.create_rectangle(*cell_rect,outline="#fdf2bc",width=3)
        if can_act and state.get("robber_pending") and (r,c)!=robber:
            _hit(ui,cell_rect,"land",(r,c))
        cx,cy=x+(c+.5)*cell,y+(r+.64)*cell
        radius=max(8,min(14,cell*.17))
        canvas.create_oval(cx-radius,cy-radius,cx+radius,cy+radius,fill="#fff4d5",outline="#8a754e")
        text(canvas,cx,cy,land["num"] if material!="desert" else "沙",max(7,int(radius*.7)),INK,"center",True)
        if (r,c)==robber:
            size=min(cell*.52,40)
            sprite(canvas,MODELS,5,(cell_rect[2]-size,cell_rect[1],cell_rect[2],cell_rect[1]+size))
    def center(point):
        return x+point[1]*cell,y+point[0]*cell
    for edge,owner in state["roads"].items():
        a,b = (tuple(map(int,p.split(","))) for p in edge.split(">"))
        coords=(*center(a),*center(b))
        canvas.create_line(*coords,fill="#f4e4bf",width=max(5,cell*.135),capstyle="round")
        canvas.create_line(*coords,fill=_owner(state,owner),width=max(3,cell*.086),capstyle="round")
    vertices, edges = legal_targets(state,me,ui.get("kt_model"),ui.get("kt_start")) if can_act else ([],[])
    for a,b in edges:
        ax,ay=center(a);bx,by=center(b);cx,cy=(ax+bx)/2,(ay+by)/2
        canvas.create_line(ax+(bx-ax)*.24,ay+(by-ay)*.24,ax+(bx-ax)*.76,ay+(by-ay)*.76,fill="#f9e6a0",width=5,dash=(3,2),capstyle="round")
        _hit(ui,(cx-10,cy-10,cx+10,cy+10),"edge",(a,b))
    for r in range(SIZE+1):
        for c in range(SIZE+1):
            point=(r,c);cx,cy=center(point);building=state["board"].get(_key(point))
            if building or ui.get("kt_start")==point:
                owner=building["owner"] if building else me
                max_size = 25 if r == 0 and ui.get("kt_compact") else 48
                size=min(max_size,max(18,cell*.56))
                canvas.create_oval(cx-size*.43,cy-size*.13,cx+size*.43,cy+size*.15,fill=_owner(state,owner),outline="#fff2cd",width=2)
                sprite(canvas,MODELS,2 if building and building["city"] else 1,(cx-size/2,cy-size*.91,cx+size/2,cy+size*.09))
            else:
                colour="#eac46a" if point in vertices else "#68877c"
                canvas.create_oval(cx-3.5,cy-3.5,cx+3.5,cy+3.5,fill=colour,outline="#fff4d5")
            _hit(ui,(cx-10,cy-10,cx+10,cy+10),"vertex",point,point in vertices)


def _rack(canvas,state,me,ui,rect,can_act,compact):
    x,y,x1,y1=rect
    if compact:
        y1 = min(y1, y+171)
        rect = (x,y,x1,y1)
    _panel(canvas,rect,"#f9f1de")
    inventory=state["res"].get(str(me),{})
    horizontal=not compact
    for index, (model,name) in enumerate(MODELS_NAMES.items()):
        if horizontal:
            width=(x1-x)/3
            slot=(x+index*width+2,y+2,x+(index+1)*width-2,y1-2)
        else:
            height=(y1-y)/3
            slot=(x+2,y+index*height+1,x1-2,y+(index+1)*height-1)
        a,b,c,d=slot;cx=(a+c)/2
        if model==ui.get("kt_model"):
            _panel(canvas,slot,"#dcebe0","#84a899")
        size=min((d-b)*.65,(c-a)*.62) if horizontal else min(d-b-6,44)
        if horizontal:
            sprite(canvas,MODELS,index,(cx-size/2,b+1,cx+size/2,b+size+1))
            text(canvas,cx,b+size+8,name,8,INK,"center",True)
            fee_x,fee_y=cx,b+size+21
        else:
            sprite(canvas,MODELS,index,(a+1,b+3,a+size+1,b+size+3))
            text(canvas,a+size+5,b+10,name,8,INK,"w",True)
            fee_x,fee_y=(a+size+4+c)/2,d-14
        fees=list(RES_COST[model].items());pitch=min(31 if horizontal else 23,(c-a-(size if compact else 0)-6)/len(fees))
        for i,(material,amount) in enumerate(fees):
            left=fee_x+(i-len(fees)/2)*pitch
            _resource(canvas,material,(left,fee_y-10,left+pitch-9,fee_y+11))
            text(canvas,left+pitch-4,fee_y+1,amount,8,INK if inventory.get(material,0)>=amount else "#a14135","center",True)
        _hit(ui,slot,"model",model,can_act and state.get("rolled") and not state.get("robber_pending"))


def _dice_and_turn(canvas,state,ui,rect,can_act):
    x,y,x1,y1=rect;length=x1-x;h=y1-y
    tray=(x,y,x+length*.72,y1)
    _panel(canvas,tray,"#dceae0","#a0b7a5")
    faces=(state.get("last_dice") or [None,None]) if state.get("rolled") else [None,None]
    size=min(h*.49,length*.19)
    sprite(canvas,MODELS,3,(x+3,y+4,x+length*.31,y1-4))
    for i,value in enumerate(faces):
        die(canvas,x+length*.31+i*(size+5),y+(h-size)/2-3,size,value)
    if not state.get("rolled"):
        text(canvas,x+length*.51,y1-9,"待掷",7,MUTED,"center")
    elif faces==[None,None] and state.get("last_roll") is not None:
        text(canvas,x+length*.51,y1-9,f"合计 {state['last_roll']}",7,MUTED,"center")
    allowed=can_act and state["phase"]!="setup" and not state.get("robber_pending")
    _hit(ui,tray,"roll",enabled=allowed and not state.get("rolled"))
    turn=(x+length*.74,y,x1,y1)
    sprite(canvas,MODELS,4,(turn[0]+2,y+2,x1-2,y1-8))
    text(canvas,(turn[0]+x1)/2,y1-7,"交接",7,MUTED,"center")
    _hit(ui,turn,"skip",enabled=allowed)


def _harbour(canvas,state,me,ui,rect,can_act):
    x,y,x1,maximum_y=rect
    width=x1-x
    portrait_width=min(110,max(65,width*.235))
    left=x+portrait_width+13
    right=x1-7
    col=(right-left)/5
    footer=48
    row_h=min(79,col+25,(maximum_y-y-footer-11)/2)
    y1=y+2*row_h+footer+11
    _panel(canvas,(x,y,x1,y1),"#efe8d8")
    portrait_height=portrait_width*12/11
    portrait_y=y+(y1-y-portrait_height-20)/2
    portrait_x=x+6
    _panel(canvas,(portrait_x-1,portrait_y-1,portrait_x+portrait_width+1,
                   portrait_y+portrait_height+1),"#f7efdc","#c8b798")
    sprite(canvas,HARBOUR,0,(portrait_x,portrait_y,portrait_x+portrait_width,
                           portrait_y+portrait_height))
    text(canvas,portrait_x+portrait_width/2,portrait_y+portrait_height+12,"港务员",8,INK,"center",True)
    inventory=state["res"].get(str(me),{})
    allowed=can_act and state.get("rolled") and not state.get("robber_pending")
    for row,kind in enumerate(("give","want")):
        top=y+3+row*row_h
        text(canvas,left,top+8,"交货 4 件" if row==0 else "取货 1 件",8,INK,"w",True)
        for i,material in enumerate(RES_ORDER):
            a=left+i*col;slot=(a+1,top+18,a+col-2,top+row_h-1)
            selected=ui.get("kt_"+kind)==material
            _panel(canvas,slot,"#d9ebe1" if selected else "#fffbf1","#80a695" if selected else "#d8d3c4")
            icon=min(47,col-7, row_h-35)
            icon_x=a+(col-icon)/2
            _resource(canvas,material,(icon_x,top+20,icon_x+icon,top+20+icon))
            canvas.create_line(a+4,top+row_h-16,a+col-5,top+row_h-16,fill="#d9d3c5")
            count=inventory.get(material,0) if row==0 else 1
            text(canvas,a+col/2,top+row_h-8,count,8,"#a14135" if row==0 and count<4 else INK,"center",True)
            _hit(ui,slot,kind,material,allowed)
    give,want=ui.get("kt_give"),ui.get("kt_want")
    receipt=state.get("last_trade") or {}
    ready=allowed and give and want and give!=want and inventory.get(give,0)>=4
    if ui.get("kt_pending"):
        message="等待成交确认"
    elif give and inventory.get(give,0)<4:
        message=f"{NAMES[give]}库存 {inventory.get(give,0)}，需 4"
    elif give and want and give==want:
        message="请选择不同货物"
    elif ready:
        message=f"{NAMES[give]} −4  /  {NAMES[want]} +1"
    elif receipt.get("uid")==me:
        message=f"已成交  {NAMES[receipt['give']]} −{receipt['n']}  /  {NAMES[receipt['want']]} +1"
    else:
        message="选择货物后盖章" if allowed else "码头等待开市"
    fy=y1-footer+3
    _panel(canvas,(left,fy,right,y1-4),"#e4ebdc" if ready else "#f7f0de")
    text(canvas,left+5,(fy+y1)/2,message,8,INK)
    stamp=(right-footer,fy,right,y1-4)
    stamp_x=(stamp[0]+stamp[2])/2
    sprite(canvas,GOODS,5,(stamp_x-17,fy+1,stamp_x+17,y1-17))
    text(canvas,stamp_x,y1-10,"成交",8,TEAL if ready else MUTED,"center",True)
    _hit(ui,stamp,"trade",enabled=ready)


def paint(canvas,state,me,nick,submit,repaint,ui,width,height):
    room=ui.get("room") or {}
    context=(room.get("room_id"),room.get("round"),me)
    if ui.get("kt_context")!=context:
        ui.update(kt_context=context,kt_tab="map",kt_model=None,kt_focus=0,kt_show_focus=False)
    if ui.get("kt_frame") is not state:
        ui.update(kt_start=None,kt_give=None,kt_want=None)
    ui.update(game="kaituo",kt_frame=state,kt_hits=[],me=me,submit=submit,repaint=repaint)
    _bind_keys(canvas,ui)
    can_act=_my_turn(room,state,me,ui.get("connected",False)) and not ui.get("kt_pending")
    _panel(canvas,(0,0,width,height),PAPER,PAPER)
    _panel(canvas,(0,0,width,45),INK,INK)
    text(canvas,14,22,"开拓 · 海风商路",13,"#fff5df","w",True)
    if state.get("winner_uid") is not None:
        label=f"{nick(state['winner_uid'])} 获胜"
    elif me not in state["players"]:
        label="旁观"
    elif ui.get("kt_pending"):
        label="等待确认"
    elif can_act:
        label="轮到你"
    else:
        label=f"等待 {nick(state['turn_uid'])[:10]}"
    text(canvas,width-14,22,label,9,"#e9eddd","e",True)
    wide=width>=760 and height>=475
    two_levels = not wide and width>=500 and height>=555
    ui["kt_compact"] = not wide
    if wide:
        side=min(width*.54,height-146);x=28;y=94;right=x+side+25
        _map(canvas,state,me,ui,(x,y,x+side,y+side),can_act)
        tools_y = 58
        _dice_and_turn(canvas,state,ui,(right,tools_y,width-14,tools_y+58),can_act)
        rack_height=min(122,(height-126)*.29)
        _rack(canvas,state,me,ui,(right,tools_y+67,width-14,tools_y+67+rack_height),can_act,False)
        harbour_y=tools_y+76+rack_height
        _harbour(canvas,state,me,ui,(right,harbour_y,width-14,min(height-42,harbour_y+262)),can_act)
    elif two_levels:
        dock_y=height-263
        x,y=26,86
        side=min(width-226,dock_y-y-24)
        right=x+side+29
        _map(canvas,state,me,ui,(x,y,x+side,y+side),can_act)
        _dice_and_turn(canvas,state,ui,(right,y,width-14,y+53),can_act)
        _rack(canvas,state,me,ui,(right,y+61,width-14,dock_y-10),can_act,True)
        _harbour(canvas,state,me,ui,(14,dock_y,width-14,height-43),can_act)
    else:
        for i,(tab,title) in enumerate((("map","地图与建造"),("harbour","港口贸易"))):
            rect=(12+i*109,49,115+i*109,72)
            _panel(canvas,rect,"#d7e9dc" if ui.get("kt_tab")==tab else LIGHT)
            text(canvas,(rect[0]+rect[2])/2,61,title,8,INK,"center",True)
            _hit(ui,rect,"tab",tab)
        if ui.get("kt_tab")=="harbour":
            _harbour(canvas,state,me,ui,(12,80,width-12,height-43),can_act)
        else:
            shelf_width=min(150,max(115,width*.31));side=min(width-shelf_width-61,height-146)
            if side>10:
                x=26;y=102;right=width-shelf_width-11
                _map(canvas,state,me,ui,(x,y,x+side,y+side),can_act)
                model = ui.get("kt_model")
                if model in RES_COST:
                    short_names = dict(zip(RES_ORDER, ("木","砖","羊","麦","矿")))
                    fee = "  ".join(short_names[key]+str(count) for key,count in RES_COST[model].items())
                    text(canvas,right+2,y-11,fee,8,TEAL,"w",True)
                _dice_and_turn(canvas,state,ui,(right,y,width-11,y+52),can_act)
                _rack(canvas,state,me,ui,(right,y+59,width-11,height-43),can_act,True)
                if height-y >= 365 and me in state["players"]:
                    inventory = state["res"][str(me)]
                    top = y+240
                    _panel(canvas,(right,top,width-11,min(height-43,top+126)),"#f7efdc")
                    text(canvas,right+7,top+12,"手边货物",8,INK,"w",True)
                    for i, material in enumerate(RES_ORDER):
                        row_y=top+30+i*18
                        _resource(canvas,material,(right+6,row_y-8,right+25,row_y+8))
                        text(canvas,right+29,row_y,NAMES[material],8,INK)
                        text(canvas,width-22,row_y,inventory[material],8,INK,"e",True)
    players=state["players"]
    for i,uid in enumerate(players):
        slot_width=(width-24)/len(players);left=12+i*slot_width
        _panel(canvas,(left,height-33,left+slot_width-4,height-7),LIGHT)
        canvas.create_rectangle(left,height-33,left+4,height-7,fill=_owner(state,uid),outline="")
        text(canvas,left+8,height-20,f"{nick(uid)[:7]}  {state['score'].get(str(uid),0)}分",8,INK)
    if ui.get("kt_show_focus") and ui["kt_hits"]:
        rect=ui["kt_hits"][ui.get("kt_focus",0)%len(ui["kt_hits"])][0]
        canvas.create_rectangle(*rect,outline=TEAL,width=2,dash=(3,2))
