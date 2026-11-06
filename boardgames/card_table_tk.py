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
            # The anime patrons place faces and role props below tall hair.
            # A short patron banner keeps that face/prop band in view.
            center = ((0.5, 0.45) if filename == "gemcity-patrons.webp" else
                      (0.5, 0.0) if filename == "lovelove-court.webp" else (0.5, 0.5))
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


# GemCity owns the functions below; shared helpers and the Love Letter court stay unchanged.
_GC_NAMES = {'o':'黑玛瑙','d':'白钻石','r':'红宝石','e':'祖母绿','s':'蓝宝石','g':'黄金'}
_GC_FILL = {'o':'#252a2b','d':'#ecf2f5','r':'#bd3448','e':'#268558','s':'#246eb1','g':'#d7a741'}
_GC_LIGHT, _GC_DARK, _GC_EDGE = '#f5ead3', '#203833', '#c1a578'


def _gc_text(cv,x,y,value,size=9,color=_GC_LIGHT,anchor='w',bold=False,width=None):
    text(cv,x,y,value,size,color,anchor,bold,width)


def _gc_button(cv,rect,label,selected=False,enabled=True):
    box(cv,rect,'#d9bd83' if selected else '#344d44','#d9bd83' if enabled else '#53645a')
    _gc_text(cv,(rect[0]+rect[2])/2,(rect[1]+rect[3])/2,label,8,
             '#182d27' if selected else (_GC_LIGHT if enabled else '#9ba99c'),'center',True)


@lru_cache(maxsize=6)
def _gc_jewel_source(color):
    from PIL import Image
    from boardgames.gallery import resource_path
    with Image.open(resource_path('gemcity-jewels.webp')) as image:
        image=image.convert('RGBA')
        i=(*COLORS,'g').index(color)
        return image.crop((i%3*image.width//3,i//3*image.height//2,
                           (i%3+1)*image.width//3,(i//3+1)*image.height//2))


def _gc_jewel(cv,x,y,color,radius):
    """Preserve the transparent jewel atlas, with a bounded per-canvas Tk cache."""
    if color not in _GC_FILL:return
    if isinstance(getattr(cv,'_w',None),str):
        try:
            from PIL import Image,ImageTk
            side=max(8,round(radius*2.25))
            cache=getattr(cv,'_gc_jewel_photos',None)
            if cache is None:cache=cv._gc_jewel_photos=OrderedDict()
            key=color,side
            if key not in cache:
                cache[key]=ImageTk.PhotoImage(_gc_jewel_source(color).resize((side,side),Image.Resampling.LANCZOS),master=cv)
                while len(cache)>48:cache.popitem(last=False)
            cache.move_to_end(key)
            cv.create_image(x,y,image=cache[key],tags='gc-jewel')
            return
        except (ImportError,OSError,ValueError):pass
    fill=_GC_FILL[color]
    if color=='d':points=[x,y-radius,x+radius,y,x,y+radius,x-radius,y]
    elif color=='e':points=[x-radius*.6,y-radius,x+radius*.6,y-radius,x+radius,y-radius*.6,x+radius,y+radius*.6,x+radius*.6,y+radius,x-radius*.6,y+radius,x-radius,y+radius*.6,x-radius,y-radius*.6]
    elif color=='r':points=[x-radius*.6,y-radius,x+radius*.6,y-radius,x+radius,y,x+radius*.6,y+radius,x-radius*.6,y+radius,x-radius,y]
    elif color=='o':points=[x-radius*.7,y-radius,x+radius*.7,y-radius,x+radius,y-radius*.7,x+radius,y+radius*.7,x+radius*.7,y+radius,x-radius*.7,y+radius,x-radius,y+radius*.7,x-radius,y-radius*.7]
    else:
        cv.create_oval(x-radius,y-radius,x+radius,y+radius,fill=fill,outline='#d7d3c5',width=1,tags='gc-jewel-fallback')
        return
    cv.create_polygon(*points,fill=fill,outline='#d7d3c5',width=1,tags='gc-jewel-fallback')


def _gc_chip(cv,x,y,color,value,radius=7):
    """Costs always have a circular ground and a true, contrasting rule number."""
    fill=_GC_FILL.get(color,'#68776b')
    cv.create_oval(x-radius,y-radius,x+radius,y+radius,fill=fill,outline='#f5e9d0',width=1,tags='gc-cost-chip')
    _gc_text(cv,x,y,value,max(7,round(radius*.8)),'#172d32' if color in ('d','g') else '#ffffff','center',True)


def _gc_cost(cv,x,y,width,cost,radius=7):
    values=[(k,(cost or {}).get(k,0)) for k in COLORS if (cost or {}).get(k,0)]
    if not values:
        _gc_text(cv,x,y,'免费',7,'#fff8e6',bold=True)
        return
    pitch=radius*2+2
    cols=max(1,min(len(values),int(width//pitch)))
    rows=(len(values)+cols-1)//cols
    for i,(key,value) in enumerate(values):
        _gc_chip(cv,x+radius+(i%cols)*pitch,y-(rows-1-i//cols)*pitch,key,value,radius)


def _gc_art_index(card):
    index,disc=card.get('art'),card.get('disc')
    if (card.get('art_set')=='jewel-v2' and type(index) is int and 0<=index<20
            and disc in COLORS and index//4==COLORS.index(disc)):
        return index
    return None


def _gc_name(card):
    # Older cards could have an unrelated yellow/purple/blue painting and name.
    # Their actual permanent discount is the only safe source for the neutral face.
    if _gc_art_index(card) is not None and card.get('title'):return str(card['title'])
    return f"{_GC_NAMES.get(card.get('disc'),'宝石')}·{card.get('tier',1)}级发展卡"


def _gc_signature(card):
    return (card.get('art_set'),card.get('tier'),card.get('art'),card.get('disc'),
            card.get('title'),card.get('pts'),tuple(sorted((card.get('cost') or {}).items())))


def _development(cv,card,rect,affordable=False,reserve=False,selected=False,contain=False):
    """Full-bleed portrait; only real prestige, permanent jewel and costs overlay it."""
    x0,y0,x1,y1=rect
    height,width=y1-y0,x1-x0
    box(cv,rect,'#384d43','#ffe1a1' if selected else ('#92c799' if affordable else '#bbac87'),3 if selected else 1)
    index=_gc_art_index(card)
    inner=x0+2,y0+2,x1-2,y1-2
    if index is None or not art(cv,f"gemcity-tier{card.get('tier',1)}.webp",index,4,5,inner,contain=contain):
        fill=_GC_FILL.get(card.get('disc'),'#546356')
        box(cv,inner,'#3a4d43','#3a4d43')
        # Neutral cards have a large unambiguous jewel, never the old illustration.
        _gc_jewel(cv,(x0+x1)/2,y0+height*.46,card.get('disc'),min(width*.24,height*.19))
        _gc_text(cv,(x0+x1)/2,y0+height*.7,_GC_NAMES.get(card.get('disc'),'发展卡'),7,'#f0e6d3','center')
    r=max(7,min(13,width*.14))
    # Dark local backing keeps a white diamond distinct from every painting.
    cv.create_oval(x1-r*2.15,y0+3,x1-3,y0+r*2.15,fill='#203832',outline='#cfba8c',tags='gc-permanent-ground')
    _gc_jewel(cv,x1-r-3,y0+r+3,card.get('disc'),r*.85)
    pts=card.get('pts',0)
    if pts:
        # Small shadow rather than a badge or a strip cut from the artwork.
        _gc_text(cv,x0+6,y0+13,pts,max(11,min(22,round(height*.13))),'#1c2924',bold=True)
        _gc_text(cv,x0+5,y0+12,pts,max(11,min(22,round(height*.13))),'#fff3cb',bold=True)
    # A narrow dark caption is part of the full card; there is no white fee panel.
    box(cv,(x0+2,y1-15,x1-2,y1-2),'#273e36','#273e36')
    label=_gc_name(card)
    limit=max(4,int(width/10))
    if len(label)>limit:label=label[:limit-1]+'…'
    _gc_text(cv,(x0+x1)/2,y1-8,label,7 if width<100 else 9,'#fff2d5','center')
    _gc_cost(cv,x0+5,y1-25,width-10,card.get('cost'),max(6,min(10,round(width*.1))))


def _gc_active(st,ui,me):
    return (ui.get('connected',True) and _member(st,ui,me)
            and st.get('status',(ui.get('room') or {}).get('status'))=='playing'
            and (ui.get('room') or {}).get('status','playing')=='playing'
            and st.get('turn_uid')==me and st.get('winner_uid') is None)


def _gc_book(st,field,uid):
    values=st.get(field) or {}
    return values.get(str(uid),values.get(uid,{}))


def _gc_resolve(ui,focus=None):
    st,me=ui.get('state') or {},ui.get('me')
    focus=ui.get('gc_focus') if focus is None else focus
    if not isinstance(focus,tuple) or len(focus)!=4:return None
    kind,tier,index,signature=focus
    if kind=='market':
        market=st.get('market') or {}
        cards=market.get(str(tier),market.get(tier,[]))
    else:
        cards=_private(st,ui,me,ui.get('_card_private')).get(kind) or []
    if type(index) is not int or not 0<=index<len(cards):return None
    card=cards[index]
    return card if _gc_signature(card)==signature else None


def _gc_focus(kind,tier,index,card):
    return kind,tier,index,_gc_signature(card)


def _gc_layout(w,h):
    top,bottom=57,h-83
    row=(bottom-top)/3
    ch=max(38,row-6);cw=ch*.72
    deck=min(40,max(24,cw*.34));bank=min(76,max(44,cw*.63));noble=min(144,max(76,cw*1.25));gap=8
    total=deck+gap+4*cw+18+gap+bank+gap+noble
    if total>w-12:
        ratio=max(.1,(w-12-42)/(total-42))
        cw*=ratio;ch*=ratio;deck*=ratio;bank*=ratio;noble*=ratio
        total=deck+gap+4*cw+18+gap+bank+gap+noble
    left=max(4,(w-total)/2)
    market=left+deck+gap
    bx=market+4*cw+18+gap
    return dict(top=top,bottom=bottom,row=row,ch=ch,cw=cw,deck=deck,left=left,
                market=market,bank=(bx,bx+bank),noble=(bx+bank+gap,bx+bank+gap+noble))


def _gc_nobles(cv,st,rect,ui=None,large=False):
    x0,y0,x1,y1=rect
    nobles=st.get('nobles') or []
    ids,titles=st.get('noble_art') or [],st.get('noble_titles') or []
    _gc_text(cv,(x0+x1)/2,y0+6,'贵宾',9,'#e3cea0','center',True)
    if not nobles:
        _gc_text(cv,(x0+x1)/2,(y0+y1)/2,'均已受邀',8,'#d0c7ac','center')
        return
    pitch=(y1-y0-18)/len(nobles)
    for i,cost in enumerate(nobles):
        top=y0+18+i*pitch
        height=min(pitch-4,(x1-x0)*1.2 if large else pitch-4)
        r=x0+1,top,x1-1,top+height
        box(cv,r,'#3b4e42','#b89d70')
        art(cv,'gemcity-patrons.webp',ids[i] if i<len(ids) else None,5,1,(r[0]+1,r[1]+1,r[2]-1,r[3]-1))
        _gc_text(cv,r[2]-5,r[1]+10,'3',11,'#fff2c2','e',True)
        if large or pitch>82:
            box(cv,(r[0]+1,r[3]-34,r[2]-1,r[3]-1),'#293e33','#293e33')
            _gc_text(cv,r[0]+5,r[3]-26,titles[i] if i<len(titles) else f'贵宾 {i+1}',8,width=x1-x0-10)
        _gc_cost(cv,r[0]+4,r[3]-10,x1-x0-8,cost,7 if x1-x0<110 else 9)
        if large:_gc_text(cv,r[0]+4,r[1]+11,'需折扣',7,'#f5e8c4')
    if ui is not None:ui['gc_navigation'].append((*rect,'nobles'))


def _gc_bank(cv,st,ui,rect,active):
    x0,y0,x1,y1=rect;center=(x0+x1)/2
    _gc_text(cv,center,y0+6,'银行',9,'#e3cea0','center',True)
    pitch=(y1-y0-18)/6
    for i,key in enumerate((*COLORS,'g')):
        y=y0+18+(i+.42)*pitch
        radius=max(10,min(19,pitch*.29))
        fill=_GC_FILL[key]
        for offset in (3,1,0):
            cv.create_oval(center-radius,y-radius+offset,center+radius,y+radius+offset,fill=fill,outline='#d5c5a1')
        _gc_jewel(cv,center,y-2,key,radius*.7)
        # The count is a separate contrasting disc, not painted into the jewel art.
        cv.create_oval(center+radius*.35,y+radius*.1,center+radius*1.2,y+radius*.95,fill='#172b26',outline='#e0d1b0')
        _gc_text(cv,center+radius*.76,y+radius*.55,(st.get('bank') or {}).get(key,0),8,'#fff4d4','center',True)
        _gc_text(cv,center,y+radius+9,'金·万能' if key=='g' else GEMS[key][0],7,'#e7ddc6','center')
        if key in (ui.get('gc_sel') or []):
            cv.create_oval(center-radius-3,y-radius-3,center+radius+3,y+radius+3,outline='#ffe098',width=2)
        if key!='g':
            r=(x0,y0+18+i*pitch,x1,y0+18+(i+1)*pitch)
            ui['gc_bank'].append((*r,key));ui['gc_navigation'].append((*r,('bank',key)))


def _gc_player_bar(cv,st,ui,me,nick,w,h):
    box(cv,(0,h-48,w,h),'#182e28','#44594a')
    players=st.get('players') or []
    order=([me] if me in players else [])+[u for u in players if u!=me]
    ui['gc_players']=players
    slots=min(len(order),max(1,int(w//230)))
    if not slots:
        _gc_text(cv,12,h-24,'观战 · 私人保留与藏册仅本人可见',9)
        return
    offset=ui.get('gc_inspect_idx',0)%len(order)
    shown=(order+order)[offset:offset+slots]
    for i,uid in enumerate(shown):
        left=i*w/slots;right=(i+1)*w/slots
        name=('我' if uid==me else str(nick(uid))[:5])
        score=(st.get('score') or {}).get(str(uid),(st.get('score') or {}).get(uid,0))
        _gc_text(cv,left+8,h-35,f'{name}  {score}分',8,'#efddb6',bold=True)
        _gc_text(cv,left+8,h-15,'折扣',7,'#b0c5af')
        held,discount=_gc_book(st,'tokens',uid),_gc_book(st,'discount',uid)
        start=left+74;step=min(25,(right-start-6)/6)
        for j,key in enumerate((*COLORS,'g')):
            x=start+j*step
            _gc_jewel(cv,x,h-35,key,5)
            _gc_text(cv,x+7,h-35,held.get(key,0),7,'#fff4d4')
            if key!='g':
                _gc_jewel(cv,x,h-15,key,5)
                _gc_text(cv,x+7,h-15,discount.get(key,0),7,'#fff4d4')
        ui['gc_navigation'].append((left,h-48,right,h,'inspect'))


def _gc_action_bar(cv,st,ui,me,private,w,h,afford):
    y=h-79;box(cv,(5,y,w-5,h-52),'#2d4439','#68755b')
    focus=ui.get('gc_focus');card=_gc_resolve(ui)
    active=_gc_active(st,ui,me)
    if card is not None:
        kind,tier,index,_=focus
        _gc_text(cv,12,y+13,_gc_name(card),8,width=max(80,w-266))
        commands=[('赏卡','detail',True)]
        if kind!='collection':
            can_buy=active and afford(_gc_book(st,'tokens',me),_gc_book(st,'discount',me),card)
            commands.insert(0,('买入' if active else '等待回合','buy',can_buy))
        if kind=='market':commands.insert(1,('保留','reserve',active and len(private.get('reserved') or [])<3))
        for j,(label,op,enabled) in enumerate(commands):
            r=w-7-(len(commands)-j)*76,y+2,w-12-(len(commands)-1-j)*76,y+25
            _gc_button(cv,r,label,op=='buy' and enabled,enabled)
            if enabled:ui['gc_navigation'].append((*r,('command',op,focus)))
        return
    sel=ui.get('gc_sel') or []
    _gc_text(cv,12,y+13,'选牌看费用 · 点宝石选色' if not sel else '已选 '+ '、'.join(GEMS[k][0] for k in sel),8,width=w-200)
    take=w-177,y+2,w-94,y+25
    _gc_button(cv,take,f'取 {len(sel)} 颗' if sel else '确认取筹码',bool(sel),active and bool(sel))
    if active and sel:
        ui['gc_take']=take;ui['gc_navigation'].append((*take,('take',tuple(sel))))
    two=w-88,y+2,w-12,y+25
    can_two=active and len(sel)==1 and (st.get('bank') or {}).get(sel[0],0)>=4
    _gc_button(cv,two,'取同色 2',False,can_two)
    if can_two:ui['gc_navigation'].append((*two,('take2',sel[0])))


def paint_gemcity(cv,st,me,nick,submit,repaint,ui,priv,w,h,afford):
    box(cv,(0,0,w,h),_GC_DARK,_GC_DARK)
    ui.update(game='gemcity',_card_private=priv,_gc_afford=afford)
    ui.pop('_hover',None)
    context=ui.get('_room_context'),me
    if ui.get('gc_view_context')!=context:
        ui.update(gc_view_context=context,gc_view='market',gc_page=0,gc_detail=None,gc_focus=None,gc_sel=[])
    private=_private(st,ui,me,priv)
    view=ui.get('gc_view','market')
    if not _member(st,ui,me) and view in ('reserved','collection'):
        view=ui['gc_view']='market';ui['gc_detail']=ui['gc_focus']=None
    for key in ('gc_cards','gc_reserve','gc_reserved','gc_bank','gc_navigation'):ui[key]=[]
    ui['gc_take']=None
    if not _gc_active(st,ui,me):ui['gc_sel']=[]
    if _gc_resolve(ui) is None:ui['gc_focus']=None
    box(cv,(0,0,w,27),'#182f28','#8e875f')
    _gc_text(cv,10,13,'璀璨宝石 · 珠宝市集',11,'#f0dcad',bold=True)
    status=(f"{nick(st['winner_uid'])} 获胜" if st.get('winner_uid') is not None else
            '轮到你' if _gc_active(st,ui,me) else '等待 '+str(nick(st.get('turn_uid'))))
    _gc_text(cv,w-10,13,status,8,'#e7dac0','e')
    reserved,collection=private.get('reserved') or [],private.get('collection') or []
    tabs=[('market','三级市集'),('reserved',f'保留 {len(reserved)}'),
          ('collection',f"藏册 {len(collection) or private.get('cards',0)}"),('nobles',f"贵宾 {len(st.get('nobles') or [])}")]
    for i,(key,label) in enumerate(tabs):
        r=6+i*(w-12)/4,31,3+(i+1)*(w-12)/4,52
        enabled=key not in ('reserved','collection') or _member(st,ui,me)
        _gc_button(cv,r,label,view==key,enabled)
        if enabled:ui['gc_navigation'].append((*r,key))
    layout=_gc_layout(w,h);top,bottom=layout['top'],layout['bottom']
    detail=ui.get('gc_detail')
    detail_card=None
    if type(detail) is int and view=='collection' and 0<=detail<len(collection):detail_card=collection[detail]
    elif isinstance(detail,tuple):detail_card=_gc_resolve(ui,detail)
    if detail_card is not None:
        r=10,top,w-10,bottom;box(cv,r,'#253c32','#9c986f')
        back=16,top+6,112,top+29;_gc_button(cv,back,'返回藏册' if view=='collection' else '返回牌桌')
        ui['gc_navigation'].append((*back,'album_back'))
        ch=max(40,bottom-top-43);cw=ch*.72
        rect=18,top+36,18+cw,bottom-7
        _development(cv,detail_card,rect,selected=True,contain=True)
        x=rect[2]+20
        _gc_text(cv,x,top+53,_gc_name(detail_card),12,bold=True,width=w-x-16)
        _gc_text(cv,x,top+89,f"声望 {detail_card.get('pts',0)}",10,'#f1d69d')
        _gc_jewel(cv,x+9,top+118,detail_card.get('disc'),10)
        _gc_text(cv,x+28,top+118,_GC_NAMES.get(detail_card.get('disc'),'宝石')+'永久折扣 +1',9,width=w-x-42)
        _gc_text(cv,x,top+153,'原价费用',9)
        _gc_cost(cv,x,top+178,w-x-18,detail_card.get('cost'),10)
        _gc_text(cv,x,bottom-20,'已购买的卡面 · 只读欣赏' if view=='collection' else '选中卡牌 · 确认后才执行交易',8,'#c8cdb7',width=w-x-16)
    elif view=='market':
        market=st.get('market') or {};mine=_gc_book(st,'tokens',me);discount=_gc_book(st,'discount',me)
        for row,tier in enumerate((3,2,1)):
            y=top+row*layout['row']
            back=(layout['left'],y+4,layout['left']+layout['deck'],y+layout['ch']-3)
            box(cv,back,('#657f61','#8e824a','#a57543')[row],'#d5c195')
            _gc_text(cv,(back[0]+back[2])/2,y+layout['ch']*.32,('III','II','I')[row],10,'#ffedc4','center',True)
            remaining=(st.get('deck_left') or {}).get(str(tier),(st.get('deck_left') or {}).get(tier))
            _gc_text(cv,(back[0]+back[2])/2,y+layout['ch']*.66,str(remaining) if remaining is not None else '—',8,'#fff0cf','center')
            for index,card in enumerate(market.get(str(tier),market.get(tier,[]))[:4]):
                x=layout['market']+index*(layout['cw']+6)
                rect=x,y,x+layout['cw'],y+layout['ch']
                focus=_gc_focus('market',tier,index,card);ok=afford(mine,discount,card)
                _development(cv,card,rect,ok,selected=focus==ui.get('gc_focus'))
                ui['gc_cards'].append((*rect,tier,index,ok))
                ui['gc_navigation'].append((*rect,('select',focus)))
        _gc_bank(cv,st,ui,(layout['bank'][0],top,layout['bank'][1],bottom),_gc_active(st,ui,me))
        _gc_nobles(cv,st,(layout['noble'][0],top,layout['noble'][1],bottom),ui)
    elif view in ('reserved','collection'):
        cards=reserved if view=='reserved' else collection
        page=min(max(0,ui.get('gc_page',0)),max(0,(len(cards)-1)//6));ui['gc_page']=page
        shown=cards[page*6:page*6+6];rows=1 if len(shown)<=3 else 2
        ch=(bottom-top-27)/rows-6;cw=min(ch*.72,(w-52)/3)
        full=cw*3+24;left=(w-full)/2
        for i,card in enumerate(shown):
            idx=page*6+i;x=left+i%3*(cw+12);y=top+i//3*(ch+6)
            rect=x,y,x+cw,y+ch;focus=_gc_focus(view,card.get('tier'),idx,card)
            ok=afford(_gc_book(st,'tokens',me),_gc_book(st,'discount',me),card)
            _development(cv,card,rect,view=='reserved' and ok,selected=focus==ui.get('gc_focus'))
            if view=='reserved':
                ui['gc_reserved'].append((*rect,idx,ok));ui['gc_navigation'].append((*rect,('select',focus)))
            else:ui['gc_navigation'].append((*rect,('open',idx)))
        if not shown:_gc_text(cv,w/2,(top+bottom)/2,'暂无保留卡' if view=='reserved' else '购买的发展卡会收入你的藏册',10,'#d8d6bc','center')
        else:
            for r,key,label in [((12,bottom-23,82,bottom-2),'prev','上一页'),((w-82,bottom-23,w-12,bottom-2),'next','下一页')]:
                _gc_button(cv,r,label);ui['gc_navigation'].append((*r,key))
            _gc_text(cv,w/2,bottom-12,f'{page+1}/{max(1,(len(cards)+5)//6)} · 点卡赏图' if view=='collection' else '点牌后确认买入',8,'#dbd6ba','center')
    else:
        # The public noble page opens larger portraits without hiding any requirement.
        nobles=st.get('nobles') or [];cols=max(1,min(5,len(nobles)));cw=(w-24)/cols-6
        for i,cost in enumerate(nobles):
            mini={**st,'nobles':[cost],'noble_art':(st.get('noble_art') or [None]*len(nobles))[i:i+1],
                  'noble_titles':(st.get('noble_titles') or ['贵宾']*len(nobles))[i:i+1]}
            _gc_nobles(cv,mini,(12+i*(cw+6),top,12+i*(cw+6)+cw,bottom),large=True)
        if not nobles:_gc_text(cv,w/2,(top+bottom)/2,'贵宾均已受邀',12,'#e8cea1','center')
    _gc_action_bar(cv,st,ui,me,private,w,h,afford)
    _gc_player_bar(cv,st,ui,me,nick,w,h)


def browse_gemcity(ui,x,y):
    """Selection and confirmation use the existing click hook, never per-card buys."""
    for *rect,key in ui.get('gc_navigation') or []:
        if not hit(rect,x,y):continue
        st,me=ui.get('state') or {},ui.get('me')
        private=_private(st,ui,me,ui.get('_card_private'))
        if isinstance(key,tuple):
            kind=key[0]
            if kind=='select':
                if _gc_resolve(ui,key[1]) is not None:ui.update(gc_focus=key[1],gc_sel=[])
            elif kind=='open':
                cards=private.get('collection') or [];idx=key[1]
                if 0<=idx<len(cards):ui.update(gc_detail=idx,gc_focus=_gc_focus('collection',cards[idx].get('tier'),idx,cards[idx]))
            elif kind=='bank':
                if _gc_active(st,ui,me) and (st.get('bank') or {}).get(key[1],0)>0:
                    sel=list(ui.get('gc_sel') or [])
                    if key[1] in sel:sel.remove(key[1])
                    elif len(sel)<3:sel.append(key[1])
                    ui.update(gc_sel=sel,gc_focus=None,gc_detail=None)
            elif kind in ('take','take2'):
                if _gc_active(st,ui,me):
                    bank=st.get('bank') or {};sel=list(ui.get('gc_sel') or [])
                    valid=(kind=='take' and tuple(sel)==key[1] and 1<=len(sel)<=3 and all(k in COLORS and bank.get(k,0)>0 for k in sel))
                    valid_two=(kind=='take2' and sel==[key[1]] and key[1] in COLORS and bank.get(key[1],0)>=4)
                    if valid or valid_two:
                        action={'op':'take','colors':sel} if valid else {'op':'take2','color':key[1]}
                        ui.get('submit',lambda action:None)(action);ui.update(gc_sel=[],gc_focus=None)
            elif kind=='command':
                op,focus=key[1:];card=_gc_resolve(ui,focus)
                if card is not None and focus==ui.get('gc_focus'):
                    if op=='detail':ui['gc_detail']=focus[2] if focus[0]=='collection' else focus
                    elif _gc_active(st,ui,me):
                        afford=ui.get('_gc_afford',lambda *a:False)
                        can_buy=afford(_gc_book(st,'tokens',me),_gc_book(st,'discount',me),card)
                        if op=='buy' and focus[0] in ('market','reserved') and can_buy:
                            action={'op':'buy','tier':focus[1],'idx':focus[2]} if focus[0]=='market' else {'op':'buy_res','idx':focus[2]}
                            ui.get('submit',lambda action:None)(action);ui.update(gc_focus=None,gc_detail=None,gc_sel=[])
                        elif op=='reserve' and focus[0]=='market' and len(private.get('reserved') or [])<3:
                            ui.get('submit',lambda action:None)({'op':'reserve','tier':focus[1],'idx':focus[2]})
                            ui.update(gc_focus=None,gc_detail=None,gc_sel=[])
        elif key=='album_back':ui['gc_detail']=None
        elif key=='inspect':ui['gc_inspect_idx']=ui.get('gc_inspect_idx',0)+1
        elif key=='prev':ui['gc_page']=max(0,ui.get('gc_page',0)-1)
        elif key=='next':ui['gc_page']=ui.get('gc_page',0)+1
        elif key in ('reserved','collection') and not _member(st,ui,me):pass
        else:ui.update(gc_view=key,gc_page=0,gc_detail=None,gc_focus=None,gc_sel=[])
        ui.get('repaint',lambda:None)()
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
