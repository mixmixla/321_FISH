"""Railway's physical table. All quantities and routes come from current state."""
from math import hypot
from boardgames.card_table_tk import art, box, hit, text
from games_pkg.tielu import TICKETS

COLORS = ('red', 'yellow', 'green', 'blue', 'purple')
NAMES = dict(zip(COLORS, ('红', '黄', '绿', '蓝', '紫')))
INKS = dict(zip(COLORS, ('#c8494a', '#d5a329', '#38865a', '#3c71b4', '#8d5eb1')))
OWNER = ('#d6545c', '#387cc5', '#378b5b', '#d4a132')
LANDMARKS = {0:(.16,.23), 1:(.42,.19), 2:(.72,.20), 3:(.88,.43),
             4:(.77,.76), 5:(.46,.76), 6:(.18,.75), 7:(.10,.49)}
ATLAS = 'tielu-coach-cards.webp'
STATIONS = 'tielu-stations.webp'
PAPER, DARK, EDGE = '#fff7e8', '#233b40', '#b09a72'


def member(st, ui, me):
    room = ui.get('room') or {}
    return me in room.get('players', st.get('players', ())) and me not in room.get('spectators', ())


def active(ui):
    st, me, room = ui.get('state') or {}, ui.get('me'), ui.get('room') or {}
    return (ui.get('connected', True) and member(st, ui, me)
            and room.get('status', 'playing') == 'playing' and st.get('status') == 'playing'
            and st.get('turn_uid') == me and st.get('winner_uid') is None
            and not ui.get('tl_sending'))


def signature(route):
    return route['a'], route['b'], route.get('color'), int(route['length'])


def resolve(ui):
    selected = ui.get('tl_selected')
    return next((r for r in (ui.get('state') or {}).get('routes', ())
                 if not r.get('claimed') and signature(r) == selected), None)


def private(ui):
    return (ui.get('tl_private') or {}) if member(ui.get('state') or {}, ui, ui.get('me')) else {}


def affordable(ui, route):
    return bool(route and (private(ui).get('hand') or {}).get(route.get('color'), 0) >= route['length'])


def goal_available(ui):
    goals=private(ui).get('tickets')
    return isinstance(goals,list) and len({(t['a'],t['b'],t['v']) for t in goals}) < len(TICKETS)


def _button(cv, rect, label, selected=False, enabled=True):
    box(cv, rect, '#176e68' if selected else PAPER, '#176e68' if enabled else '#aaa99c')
    text(cv, (rect[0]+rect[2])/2, (rect[1]+rect[3])/2, label, 8,
         '#fff' if selected else (DARK if enabled else '#9b9b91'), 'center', True)


def _coach(cv, cx, cy, dx, dy, length, width, color, locomotive=False):
    """A real-length route contains that many separate carriages, with wheels."""
    def point(a, b): return cx+dx*a-dy*b, cy+dy*a+dx*b
    points = [point(a,b) for a,b in ((-length/2,-width/2),(length/2,-width/2),
                                    (length/2,width/2),(-length/2,width/2))]
    cv.create_polygon(*[v for p in points for v in p], fill=color, outline='#fff6df', width=1,
                      tags='tl-coach')
    for a in (-.26, .08, .33):
        windows = [point(a*length+u*length, v*width) for u,v in ((-.085,-.26),(.085,-.26),(.085,.12),(-.085,.12))]
        cv.create_polygon(*[v for p in windows for v in p], fill='#e8f3ea', outline='', tags='tl-coach-window')
    for a in (-.31, .31):
        for b in (-.54, .54):
            x,y=point(a*length,b*width);r=max(1.3,width*.14)
            cv.create_oval(x-r,y-r,x+r,y+r,fill='#263b40',outline='',tags='tl-wheel')
    if locomotive:
        x,y=point(length*.38,0);r=max(2,width*.2)
        cv.create_oval(x-r,y-r,x+r,y+r,fill='#ffedab',outline='#263b40',tags='tl-engine')


def _card(cv, rect, index, caption, count=None, selected=False, enabled=True):
    x0,y0,x1,y1=rect
    box(cv, rect, PAPER, '#e79636' if selected else EDGE, 3 if selected else 1)
    if not art(cv, ATLAS, index, 3, 2, (x0+2,y0+2,x1-2,y1-17)):
        fill = INKS.get(COLORS[index] if index < 5 else '', '#4c7986')
        box(cv,(x0+3,y0+3,x1-3,y1-17),fill,fill)
        _coach(cv,(x0+x1)/2,(y0+y1-17)/2,1,0,max(13,(x1-x0)*.65),12,fill)
    text(cv,(x0+x1)/2,y1-9,caption,8,DARK if enabled else '#8c9893','center',True)
    if count is not None:
        x,y=x1-10,y0+11
        cv.create_oval(x-9,y-9,x+9,y+9,fill=PAPER,outline=EDGE,tags='tl-card-count')
        text(cv,x,y,count,9,DARK,'center',True)


def _bottom(cv, ui, w, h, height):
    st=ui['state'];known=isinstance(private(ui).get('hand'),dict);hand=(private(ui).get('hand') or {})
    ui['tl_entities']=[]
    step=(w-20)/7;top=h-height+5
    for i,color in enumerate(COLORS):
        rect=10+i*step,top,10+(i+1)*step-5,h-5
        if member(st,ui,ui.get('me')):
            _card(cv,rect,i,NAMES[color]+'车票',hand.get(color,0) if known else '—',ui.get('tl_color')==color)
            ui['tl_entities'].append((*rect,('color',color)))
    for i,label,op,enabled in ((5,'摸 2 张','draw',st.get('ticket_left',0)>0),
                              (6,'目的票 +1','ticket',goal_available(ui))):
        x0=10+i*step;rect=x0,top,x0+step-5,h-5
        for offset in (4,2):box(cv,(rect[0]+offset,rect[1]-offset,rect[2]+offset,rect[3]-offset),'#e7e5d1',EDGE)
        _card(cv,rect,3 if op=='draw' else 5,label,st.get('ticket_left') if op=='draw' else None,enabled=enabled and active(ui))
        if active(ui) and enabled:ui['tl_entities'].append((*rect,('action',op)))


def _goals(cv, ui, rect, city):
    x0,y0,x1,y1=rect;goals=private(ui).get('tickets') or []
    if not goals:
        text(cv,(x0+x1)/2,(y0+y1)/2,'私人目的票只对座位玩家可见',10,DARK,'center')
        return
    page_size=max(1,min(4,int((y1-y0-30)//82)))
    pages=(len(goals)+page_size-1)//page_size;page=max(0,min(ui.get('tl_page',0),pages-1));ui['tl_page']=page
    for j,goal in enumerate(goals[page*page_size:(page+1)*page_size]):
        top=y0+j*(y1-y0-30)/page_size;bottom=top+(y1-y0-30)/page_size-5
        r=x0+5,top,x1-5,bottom
        box(cv,r,'#edf5e5' if goal.get('connected') else PAPER,EDGE)
        a,b=city(goal['a']),city(goal['b'])
        stub=r[2]-85;picture=min(112,(stub-r[0]-83)/2)
        for left,cid,label in ((r[0]+7,goal['a'],a),(r[0]+picture+33,goal['b'],b)):
            image_rect=(left,top+5,left+picture,bottom-22)
            if not art(cv,STATIONS,cid,4,2,image_rect):box(cv,image_rect,'#dbe8d2',EDGE)
            text(cv,left+picture/2,bottom-10,label,9,DARK,'center',True)
        text(cv,r[0]+picture+20,(top+bottom)/2,'→',12,'#56867a','center',True)
        stamp_x=stub-31;stamp_y=(top+bottom)/2
        stamp='#247d65' if goal.get('connected') else '#a77b41'
        cv.create_oval(stamp_x-22,stamp_y-19,stamp_x+22,stamp_y+19,fill=PAPER,outline=stamp,width=2,tags='tl-goal-stamp')
        cv.create_oval(stamp_x-19,stamp_y-16,stamp_x+19,stamp_y+16,outline=stamp,width=1)
        text(cv,stamp_x,stamp_y,'已连通' if goal.get('connected') else '尚未连通',8,stamp,'center',True)
        cv.create_line(stub,top+3,stub,bottom-3,fill=EDGE,dash=(3,3),tags='tl-ticket-stub')
        for y in (top,bottom):cv.create_oval(stub-4,y-4,stub+4,y+4,fill='#eaf0e7',outline='')
        text(cv,stub+42,top+12,'终局票值',8,DARK,'center',True)
        text(cv,stub+10,top+32,'连通',8,'#43816b')
        text(cv,r[2]-10,top+32,'+'+str(goal['v']),12,'#22795e','e',bool(goal.get('connected')))
        text(cv,stub+10,bottom-15,'未通',8,'#a16b55')
        text(cv,r[2]-10,bottom-15,'−'+str(goal['v']),12,'#a15c48','e',not goal.get('connected'))
        ui['tl_entities'].append((*r,('goal',(goal['a'],goal['b'],goal['v']))))
    for r,delta,label in (((x0+5,y1-25,x0+66,y1),-1,'上一页'),((x1-66,y1-25,x1-5,y1),1,'下一页')):
        _button(cv,r,label,enabled=0<=page+delta<pages)
        if 0<=page+delta<pages:ui['tl_entities'].append((*r,('page',delta)))
    text(cv,(x0+x1)/2,y1-13,f'{page+1} / {pages} · 点票看起终站',8,DARK,'center')


def _map(cv, ui, rect, city, map_art):
    st=ui['state'];x0,y0,x1,y1=rect
    box(cv,rect,'#e8e1bd',EDGE);map_art(cv,*rect)
    pos={cid:(x0+fx*(x1-x0),y0+fy*(y1-y0)) for cid,(fx,fy) in LANDMARKS.items()}
    ui['tl_routes']=[];ui['tl_coach_count']=0
    selected=resolve(ui);goal=ui.get('tl_goal');highlight=set(goal[:2]) if goal else set()
    for route in st.get('routes',()):
        a,b=route['a'],route['b']
        if a not in pos or b not in pos:continue
        ax,ay=pos[a];bx,by=pos[b];length=int(route['length']);dist=hypot(bx-ax,by-ay)
        dx,dy=(bx-ax)/max(1,dist),(by-ay)/max(1,dist)
        own=route.get('claimed');color=INKS.get(route.get('color'),'#56767c')
        if own:
            players=st.get('players') or [];color=OWNER[players.index(own)%len(OWNER)] if own in players else color
        if selected is route:
            cv.create_line(ax,ay,bx,by,fill='#ffe29a',width=13,tags='tl-selected-route');highlight.update((a,b))
        elif not own and route.get('color') == ui.get('tl_color'):
            cv.create_line(ax,ay,bx,by,fill='#c4e8dd',width=11,tags='tl-color-route')
        cv.create_line(ax,ay,bx,by,fill='#385858',width=1,tags='tl-rail')
        coach_length=max(8,min(27,dist/(length+1)*.73));coach_width=max(6,min(11,(y1-y0)*.035))
        for i in range(length):
            t=(i+1)/(length+1)
            _coach(cv,ax+(bx-ax)*t,ay+(by-ay)*t,dx,dy,coach_length,coach_width,color,bool(own and i==0))
            ui['tl_coach_count']+=1
        if not own:
            ui['tl_routes'].append((ax,ay,bx,by,a,b,route.get('color'),length,affordable(ui,route)))
    for cid,(x,y) in pos.items():
        r=8 if cid in highlight else 5
        cv.create_oval(x-r-2,y-r-2,x+r+2,y+r+2,fill='#ffe79b' if cid in highlight else PAPER,outline='#294e4d',tags='tl-station')
        cv.create_oval(x-r,y-r,x+r,y+r,fill='#206e70',outline='')
        name=city(cid);width=max(30,len(name)*11+8);top=y+10
        box(cv,(x-width/2,top,x+width/2,top+17),PAPER,'#9e987c')
        text(cv,x,top+8,name,8,DARK,'center',True)


def paint(cv, st, me, nick, submit, repaint, ui, priv, w, h, map_art):
    ui.update(game='tielu',state=st,me=me,submit=submit,repaint=repaint,tl_private=priv)
    context=((ui.get('room') or {}).get('room_id'),(ui.get('room') or {}).get('round'),me)
    if ui.get('tl_context')!=context:
        for key in ('tl_selected','tl_goal','tl_page','tl_color','tl_view'):ui.pop(key,None)
        ui['tl_context']=context
    if not resolve(ui):ui.pop('tl_selected',None)
    goals=private(ui).get('tickets') or []
    if ui.get('tl_goal') not in [(g['a'],g['b'],g['v']) for g in goals]:ui.pop('tl_goal',None)
    cv.create_rectangle(0,0,w,h,fill='#eaf0e7',outline='')
    footer=78 if h>=500 else 66;content=(8,54,w-8,h-footer-33)
    text(cv,10,15,'铁路 · 旅行牌桌',12,DARK,bold=True)
    turn=st.get('turn_uid');status=('最终结算 · '+str(nick(st['winner_uid']))+' 胜' if st.get('final_scores') else
                                 '你的回合' if turn==me else '轮到 '+str(nick(turn)))
    if st.get('final_round'):status+=' · 最后一轮'
    if not st.get('final_scores'):status+=' · 余 '+str(st.get('route_left',0))+' 线'
    text(cv,w-10,15,status,9,DARK,'e')
    ui['tl_routes']=[];_bottom(cv,ui,w,h,footer)
    ui['tl_entities'].extend([(8,31,68,49,('view','map')),(74,31,155,49,('view','goals'))])
    _button(cv,(8,31,68,49),'地图',ui.get('tl_view','map')=='map')
    goal_count=str(len(goals)) if isinstance(private(ui).get('tickets'),list) else '—'
    _button(cv,(74,31,155,49),'目的票 '+goal_count,ui.get('tl_view')=='goals')
    players=st.get('players') or [];pitch=(w-232)/max(1,len(players))
    for i,uid in enumerate(players):
        x=162+i*pitch;score=(st.get('score') or {}).get(str(uid),(st.get('score') or {}).get(uid,0))
        if st.get('final_scores'):score=(st['final_scores'].get(str(uid),st['final_scores'].get(uid,{}))).get('total',0)
        cv.create_oval(x,36,x+8,44,fill=OWNER[i%len(OWNER)],outline='',tags='tl-owner-key')
        text(cv,x+11,40,('你' if uid==me else str(nick(uid))[-3:])+' '+str(score)+'分',7,DARK)
    _button(cv,(w-62,31,w-8,49),'跳过',enabled=active(ui))
    if active(ui):ui['tl_entities'].append((w-62,31,w-8,49,('action','skip')))
    cities=st.get('cities') or {};city=lambda cid:str(cities.get(str(cid),cities.get(cid,cid)))
    final=st.get('final_scores') or {}
    if final:
        columns=[w*f for f in (.15,.42,.59,.75,.91)]
        for x,label in zip(columns,('玩家','线路分','票证加分','票证扣分','总分')):text(cv,x,75,label,9,DARK,'center',True)
        for i,uid in enumerate(st.get('players') or []):
            row=final.get(str(uid),final.get(uid,{}));values=(nick(uid),row.get('route',0),'+'+str(row.get('ticket_bonus',0)),'−'+str(row.get('ticket_penalty',0)),row.get('total',0))
            for x,value in zip(columns,values):text(cv,x,108+i*33,value,10,DARK,'center',True)
        return
    if ui.get('tl_view')=='goals':
        _goals(cv,ui,content,city)
    else:_map(cv,ui,content,city,map_art)
    y=h-footer-28;selected=resolve(ui)
    if selected:
        color=selected['color'];have=(private(ui).get('hand') or {}).get(color,0)
        text(cv,10,y+12,city(selected['a'])+' → '+city(selected['b']),9,DARK,bold=True)
        text(cv,w*.40,y+12,f'{NAMES[color]}票 {selected["length"]} / 持有 {have}',8,INKS[color])
        r=(w-126,y,w-48,y+25);enabled=active(ui) and affordable(ui,selected)
        _button(cv,r,'认领线路' if enabled else '票卡不足',enabled=enabled)
        if enabled:ui['tl_entities'].append((*r,('confirm',signature(selected))))
        r=(w-44,y,w-7,y+25);_button(cv,r,'取消');ui['tl_entities'].append((*r,('cancel',None)))
    else:
        goal=ui.get('tl_goal')
        label=(f'目的票：{city(goal[0])} → {city(goal[1])} · {goal[2]} 分' if goal else
               '' if ui.get('tl_view')=='goals' else '点车厢选线路 · Tab 选线 / Enter 认领 · D 摸牌 / T 票证')
        text(cv,w/2,y+12,label,8,DARK,'center')


def _send(ui, action):
    if action.get('op')=='draw' and (ui.get('state') or {}).get('ticket_left',0)<=0:return
    if action.get('op')=='ticket' and not goal_available(ui):return
    if active(ui) and ui.get('submit'):ui['submit'](action)


def command(ui, command):
    kind,value=command
    if kind=='action':_send(ui,{'op':value})
    elif kind=='confirm':
        route=resolve(ui)
        if route and signature(route)==value and affordable(ui,route):_send(ui,{'op':'claim','a':route['a'],'b':route['b']})
    elif kind=='cancel':ui.pop('tl_selected',None)
    elif kind=='color':
        ui['tl_color']=None if ui.get('tl_color')==value else value;ui.pop('tl_selected',None)
    elif kind=='view':ui['tl_view']=value
    elif kind=='page':ui['tl_page']=ui.get('tl_page',0)+value
    elif kind=='goal':
        goals=private(ui).get('tickets') or []
        if value in [(g['a'],g['b'],g['v']) for g in goals]:ui['tl_goal']=value;ui['tl_view']='map';ui.pop('tl_selected',None)
    if ui.get('repaint'):ui['repaint']()


def click(ui, x, y, distance):
    for rect in reversed(ui.get('tl_entities',())):
        if hit(rect,x,y):command(ui,rect[-1]);return
    choices=[(distance(x,y,*r[:4]),r) for r in ui.get('tl_routes',())]
    if choices:
        dist,route=min(choices,key=lambda v:v[0])
        if dist<=12:
            ui['tl_selected']=tuple(route[4:8]);ui['tl_color']=route[6]
            if ui.get('repaint'):ui['repaint']()


def key(ui, value):
    if value=='Tab':
        routes=[r for r in (ui.get('state') or {}).get('routes',()) if not r.get('claimed')]
        if routes:
            current=resolve(ui);index=routes.index(current)+1 if current in routes else 0
            ui['tl_selected']=signature(routes[index%len(routes)]);ui['tl_view']='map'
            if ui.get('repaint'):ui['repaint']()
    elif value=='Return':
        route=resolve(ui)
        if route:command(ui,('confirm',signature(route)))
    elif value.lower() in ('d','t','s'):command(ui,('action',{'d':'draw','t':'ticket','s':'skip'}[value.lower()]))
    elif value=='Escape':command(ui,('cancel',None))
