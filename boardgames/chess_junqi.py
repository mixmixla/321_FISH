"""A military table of actual, named rectangular Junqi counters."""
from boardgames.registry import register, GamePackage
from boardgames.chess_table_art import photo

ART = "junqi-officers.webp"
NAMES = ("军旗","地雷","炸弹","工兵","排长","连长","营长","团长","旅长","师长","军长","司令")
SIDES = ("#b7414b", "#2b6291")
EVENTS = {"eat":"吃子成功", "beaten":"进攻棋子阵亡", "trade":"双方兑子", "mine_clear":"工兵挖雷", "win":"扛旗获胜", "move":"阵线推进"}


def identity(code):
    if 10 <= code <= 21: return 0, code - 10
    if 40 <= code <= 51: return 1, code - 40
    return None


def can_act(st, me, room=None, connected=True):
    room = room or {}
    return bool(connected and st.get("winner_uid") is None and st.get("turn_uid") == me
                and me in st.get("players", []) and me in room.get("players", st.get("players", []))
                and me not in room.get("spectators", []) and room.get("status", "playing") == "playing")


def paint(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    context=(ui.get("_room_context"),me)
    if ui.get("junqi_context") != context: ui["sel"]={}
    ui.update(game="junqi",state=st,me=me,submit=submit,repaint=repaint,junqi_state=st,junqi_context=context,junqi_legal=(priv or {}).get("legal",[]))
    cv._junqi_ui = ui
    if not getattr(cv,"_junqi_bound",False):
        for k in ("Up","Down","Left","Right","Return","space","Escape"):
            cv.bind("<"+k+">",lambda e:key(cv,e.keysym),add="+")
        cv._junqi_bound=True
    cv.configure(background="#e5e9eb")
    cv.create_rectangle(0,0,w,55,fill="#223b51",outline="")
    cv.create_text(13,16,anchor="w",text="军棋 · 学院战术桌",fill="#fff2d1",font=("Microsoft YaHei UI",12,"bold"))
    players=st.get("players",[]);seat=players.index(me) if me in players else -1
    role=("你执红方","你执蓝方")[seat] if seat>=0 else "旁观者 · 只读"
    status=(str(nick(st["winner_uid"]))+" 获胜") if st.get("winner_uid") is not None else ("轮到你" if st.get("turn_uid")==me and seat>=0 else "等待 "+str(nick(st.get("turn_uid"))))
    cv.create_text(13,39,anchor="w",text=role+" · "+status[:25],fill="#d8e4ed",font=("Microsoft YaHei UI",10))
    ch=max(6,min((h-96)/10,(w-38)/10));cw=ch*2
    ox,oy=(w-5*cw)/2+7,71
    ui.update(ox=ox,oy=oy,cell=ch,n=10,cols=5,rows=10,junqi_cw=cw)
    cv.create_rectangle(ox-5,oy-5,ox+cw*5+5,oy+ch*10+5,fill="#435d68",outline="#1b3545",width=3)
    selected=ui.get("sel") or {};legal=ui["junqi_legal"]
    for x in range(5):cv.create_text(ox+(x+.5)*cw,oy-11,text=chr(65+x),font=("Arial",8),fill="#3d5562")
    for y in range(10):
        cv.create_text(ox-12,oy+(y+.5)*ch,text=y+1,font=("Arial",8),fill="#3d5562")
        for x in range(5):
            x0,y0=ox+x*cw,oy+y*ch
            cv.create_rectangle(x0,y0,x0+cw,y0+ch,fill="#c8d7d7" if y<5 else "#dce3cf",outline="#8a9c9f")
            piece=identity(st["board"][y][x])
            if piece:
                side,rank=piece;gap=max(2,ch*.07);image_size=max(1,round(ch-gap*2));px=x0+gap;py=y0+gap
                cv.create_rectangle(px+1,py+2,x0+cw-gap+1,y0+ch-gap+2,fill="#263b45",outline="")
                cv.create_rectangle(px,py,x0+cw-gap,y0+ch-gap,fill="#fff3df",outline=SIDES[side],width=2)
                cv.create_image(px,py,anchor="nw",image=photo(cv,ART,(image_size,image_size),rank,4,3),tags="junqi-character")
                cv.create_text(x0+cw*.72,y0+ch*.48,text=NAMES[rank],fill=SIDES[side],font=("Microsoft YaHei UI",max(7,int(ch*.29)),"bold"))
                if rank<2:
                    cv.create_text(x0+cw-gap-3,y0+ch-gap-3,text="◆",anchor="se",fill="#7e6b52",font=("Arial",max(5,int(ch*.15))))
            if selected.get("game")=="junqi" and [x,y]==[selected.get("fx"),selected.get("fy")]:
                cv.create_rectangle(x0+1,y0+1,x0+cw-1,y0+ch-1,outline="#f9bd31",width=3)
            if any(m.get("from")==[selected.get("fx"),selected.get("fy")] and m.get("to")==[x,y] for m in legal):
                cv.create_rectangle(x0+2,y0+2,x0+cw-2,y0+ch-2,outline="#dd9a0a",width=3,dash=(3,2),tags="junqi-legal")
    last=st.get("last_move")
    if last:
        x,y=last[1];cv.create_rectangle(ox+x*cw+1,oy+y*ch+1,ox+(x+1)*cw-1,oy+(y+1)*ch-1,outline="#e39c2c",width=2)
    cursor=ui.get("junqi_cursor")
    if cursor:
        x,y=cursor;cv.create_rectangle(ox+x*cw+3,oy+y*ch+3,ox+(x+1)*cw-3,oy+(y+1)*ch-3,outline="#7257b5",width=2,dash=(2,2))
    if ox>=108:
        p=None
        if selected.get("game")=="junqi" and "fx" in selected:p=identity(st["board"][selected["fy"]][selected["fx"]])
        side,rank=p or (max(0,seat),11);size=min(104,round(ox-23))
        cv.create_image(10,104,anchor="nw",image=photo(cv,ART,(size,size),rank,4,3),tags="junqi-preview")
        cv.create_text(10+size/2,89,text="当前棋子" if p else "战术图鉴",font=("Microsoft YaHei UI",9),fill="#385267")
        cv.create_text(10+size/2,122+size,text=NAMES[rank],fill=SIDES[side],font=("Microsoft YaHei UI",11,"bold"))
        ability=("不可移动\n守护军旗","不可移动\n工兵可挖","接触双方同归","可以挖地雷")[rank] if rank<4 else "军衔比较\n同级兑子"
        cv.create_text(10+size/2,153+size,text=ability,justify="center",font=("Microsoft YaHei UI",9),fill="#385267")
    event=EVENTS.get((st.get("last_event") or {}).get("kind"),"明棋 · 相邻一步 · 军旗/地雷不可动")
    cv.create_text(w/2,h-12,text=event,fill="#385267",font=("Microsoft YaHei UI",9))


def click(ui,x,y):
    st=ui.get("state") or {};me=ui.get("me")
    if (ui.get("game")!="junqi" or st is not ui.get("junqi_state")
            or ui.get("junqi_context")!=(ui.get("_room_context"),me)
            or not can_act(st,me,ui.get("room"),ui.get("connected",True))):return
    ox,oy,cw,ch=(ui[k] for k in ("ox","oy","junqi_cw","cell"))
    if not(ox<=x<ox+5*cw and oy<=y<oy+10*ch):return
    x,y=int((x-ox)/cw),int((y-oy)/ch);piece=identity(st["board"][y][x]);sel=ui.setdefault("sel",{})
    if piece and piece[0]==st["players"].index(me):
        if piece[1]<2:return
        if [x,y]==[sel.get("fx"),sel.get("fy")]:sel.clear()
        else:sel.update(game="junqi",fx=x,fy=y)
    elif sel.get("game")=="junqi" and any(m.get("from")==[sel.get("fx"),sel.get("fy")] and m.get("to")==[x,y] for m in ui.get("junqi_legal",[])):
        a=dict(fx=sel["fx"],fy=sel["fy"],tx=x,ty=y);sel.clear();ui["submit"](a)
    ui["repaint"]()


def key(cv,k):
    if getattr(cv,"_gkey",None)!="junqi":return
    ui=cv._junqi_ui;c=ui.setdefault("junqi_cursor",[0,0]);d={"Up":(0,-1),"Down":(0,1),"Left":(-1,0),"Right":(1,0)}.get(k)
    if d:ui["junqi_cursor"]=[max(0,min(4,c[0]+d[0])),max(0,min(9,c[1]+d[1]))]
    elif k in ("Return","space"):
        click(ui,ui["ox"]+(c[0]+.5)*ui["junqi_cw"],ui["oy"]+(c[1]+.5)*ui["cell"]);return "break"
    elif k=="Escape":ui.setdefault("sel",{}).clear()
    ui["repaint"]();return "break"


register(GamePackage(name="junqi",label="军棋 · 学院战术桌",rules="games_pkg.junqi:JunqiGame",
                     web_js="boardgames.chess_junqi_web:WEB_JS",web_css="boardgames.chess_junqi_web:WEB_CSS"))
