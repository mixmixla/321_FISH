"""Orchard club: a true-state fruit table for the existing slow-turn rules.

Every rule card contains ONE fruit. Five-slot tracks count the public area;
portraits are decorative player seats, never fruit values or private cards.
"""
from boardgames.card_table_tk import art as _base_art, box, text, hit

ATLAS = "arcade-orchard.webp"
FRUITS = ("🍓", "🍋", "🍊", "🍌", "🍎")
NAMES = ("草莓", "柠檬", "橙子", "香蕉", "苹果")
GOLD = "#bb914a"
INK, CREAM, GREEN, RED = "#264b42", "#fff5de", "#244e43", "#b94252"


def art(cv, filename, index, cols, rows, rect, contain=False):
    if filename == ATLAS and index == 8:
        canvas, scale = (cv.canvas, cv.scale) if isinstance(cv, _Scaled) else (cv, 1)
        if isinstance(getattr(canvas, '_w', None), str):
            from PIL import Image, ImageOps, ImageTk
            from boardgames.gallery import resource_path
            a, b, c, d = rect
            size = max(8, round(c-a)), max(8, round((d-b)*scale))
            cache = getattr(canvas, '_orchard_bell_cache', None)
            if cache is None: cache = canvas._orchard_bell_cache = {}
            if size not in cache:
                with Image.open(resource_path('arcade-bell.png')) as source:
                    pixels = ImageOps.contain(source.convert('RGBA'), size, Image.Resampling.LANCZOS)
                if len(cache)>8: cache.clear()
                cache[size] = ImageTk.PhotoImage(pixels, master=canvas)
            canvas.create_image((a+c)/2, (b+d)*scale/2, image=cache[size], tags='card-illustration')
            return True
    if isinstance(cv, _Scaled):
        a, b, c, d = rect
        return _base_art(cv.canvas, filename, index, cols, rows,
                         (a, b*cv.scale, c, d*cv.scale), contain)
    return _base_art(cv, filename, index, cols, rows, rect, contain)


class _Scaled:
    def __init__(self, canvas, scale):
        object.__setattr__(self, "canvas", canvas)
        object.__setattr__(self, "scale", scale)

    def __getattr__(self, name):
        if name.startswith("create_"):
            def draw(*args, **kwargs):
                coords = [a*self.scale if i%2 else a for i, a in enumerate(args)]
                if "font" in kwargs:
                    family, size, *rest = kwargs["font"]
                    kwargs["font"] = (family, max(7, round(size*self.scale)), *rest)
                return getattr(self.canvas, name)(*coords, **kwargs)
            return draw
        return getattr(self.canvas, name)

    def __setattr__(self, name, value):
        setattr(self.canvas, name, value)


def players(st):
    return st.get("players") or [int(u) for u in (st.get("score") or {})]


def allowed(st, me, room=None, connected=True):
    room = room or {}
    members = room.get("players", players(st))
    return (connected is not False and me is not None and me in members
            and me not in room.get("spectators", []) and st.get("turn") == me
            and st.get("status") != "ended" and st.get("winner_uid") is None
            and room.get("status", "playing") == "playing")


def _fruit(cv, f, rect):
    if f not in FRUITS:
        return
    i = FRUITS.index(f)
    if not art(cv, ATLAS, i+3, 3, 3, rect, contain=True):
        text(cv, (rect[0]+rect[2])/2, (rect[1]+rect[3])/2, NAMES[i], 9, INK, "center")


def paint(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    if h < 430:
        return _compact(cv, st, me, nick, submit, repaint, ui, priv, w, h)
    import math
    import time
    ui["orchard_hits"] = []
    if isinstance(getattr(cv, "_w", None), str):
        cv._orchard_ui = ui
        for key, op in (("f", "flip"), ("b", "slap"), ("p", "pass")):
            cv.bind("<KeyPress-"+key+">", lambda event, op=op: key_action(cv._orchard_ui, op))
    box(cv, (0, 0, w, h), CREAM, CREAM)
    box(cv, (0, 0, w, 54), GREEN, GREEN)
    text(cv, 14, 19, "果园社团 / 德国心脏病", 13, CREAM, bold=True)
    seats=players(st);room=ui.get("room") or {};ended=st.get("status")=="ended" or st.get("winner_uid") is not None
    observer=me not in seats or me in room.get("spectators",[])
    enabled=allowed(st,me,room,ui.get("connected",True))
    label=(nick(st["winner_uid"])+" 获胜" if st.get("winner_uid") is not None else "收牌同分 · 平局") if ended else ("轮到你" if enabled else "轮到 "+nick(st.get("turn")))
    text(cv,14,42,("旁观席 · " if observer else "")+label+" · 同类恰好5个拍铃",9,"#d7e7c9")
    sw=(w-24)/max(1,len(seats));seat_centers={}
    for i,uid in enumerate(seats):
        x=12+i*sw;size=min(45,sw-12);seat_centers[uid]=(x+sw/2,92)
        box(cv,(x,63,x+sw-5,133),"#e7edd9" if uid==st.get("turn") else "#f5e9d0",GOLD if uid==me else "#dac8a6",2 if uid==me else 1)
        art(cv,ATLAS,i%3,3,3,(x+4,66,x+4+size,66+size))
        tx=x+size+10 if sw>=150 else x+4;ty=81 if sw>=150 else 118
        text(cv,tx,ty,nick(uid)[:5]+("·我" if uid==me else ""),9,INK,bold=True)
        score=st.get('score',{}).get(str(uid),0)
        if sw>=150:text(cv,tx,ty+20,"得分 "+str(score),10,INK,bold=True)
        else:text(cv,x+sw-9,118,score,9,RED,"e",True)
        dx=x+sw-40 if sw>=150 else x+sw-30;dy=74 if sw>=150 else 79
        for shift in (3,1,0):box(cv,(dx+shift,dy+shift,dx+26+shift,dy+36+shift),"#d8b97d","#927343")
        box(cv,(dx+4,dy+4,dx+22,dy+32),GREEN,"#fff4d6")
        text(cv,dx+13,dy+17,"✦",11,CREAM,"center")
        text(cv,dx+13,dy+47,st.get('left',{}).get(str(uid),0),8,INK,"center")
        if uid==me and enabled and not st.get('flipped'):ui['orchard_hits'].append((dx-3,dy-3,dx+32,dy+54,'flip'))
    cy=(145+h-99)/2;bell=min(w*.31,(h-195)*.72,195);cx=w/2
    cv.create_oval(cx-bell*.67,cy-bell*.55,cx+bell*.67,cy+bell*.68,fill='#ebdbb8',outline='#d5bd86',width=2)
    # Public cards are grouped by the actual flipper, never guessed from position.
    cards=st.get('area_cards') or [{'fruit':f,'uid':None} for f in st.get('area',[])]
    groups=[(u,[c['fruit'] for c in cards if c.get('uid')==u]) for u in seats]
    unknown=[c['fruit'] for c in cards if c.get('uid') not in seats]
    if unknown:groups.append((None,unknown))
    rows=max(1,math.ceil(len(groups)/2));ph=min(104,(h-207)/rows-7);pw=min(74,w*.15)
    for i,(uid,fruits) in enumerate(groups):
        side=i%2;row=i//2;px=w*(.17 if side==0 else .83)-pw/2
        py=149+row*((h-211)/rows)+(h-211)/rows/2-ph/2
        if not fruits:
            cv.create_rectangle(px,py,px+pw,py+ph,outline='#d9c7a3',dash=(3,3))
        for j,f in enumerate(fruits[-3:]):
            xx=px+j*4;yy=py-j*4
            box(cv,(xx,yy,xx+pw,yy+ph),'#fffef5','#b39b70',1)
            _fruit(cv,f,(xx+4,yy+5,xx+pw-4,yy+ph-8))
        text(cv,px+pw/2,py+ph+14,('公共牌' if uid is None else nick(uid)[:6])+' · '+str(len(fruits))+'张',8,INK,'center')
    art(cv,ATLAS,8,3,3,(cx-bell/2,cy-bell/2,cx+bell/2,cy+bell/2),contain=True)
    text(cv,cx,cy+bell*.48,'拍铃收牌' if st.get('can_slap') else '拍铃',10,RED,'center',True)
    if enabled and st.get('flipped'):ui['orchard_hits'].append((cx-bell/2,cy-bell/2,cx+bell/2,cy+bell/2,'slap'))
    last=st.get('last_action') or {};signature=(last.get('op'),last.get('uid'),last.get('value'),tuple(st.get('area') or []),tuple((st.get('score') or {}).values()))
    if ui.get('orchard_last_signature')!=signature:
        ui['orchard_last_signature']=signature
        if last.get('op')=='slap_ok':ui['orchard_flight']={'start':time.monotonic(),'uid':last.get('uid'),'cards':(ui.get('orchard_previous_area') or [])[-3:]}
    ui['orchard_previous_area']=list(st.get('area') or [])
    if last.get('op') in ('slap_ok','slap_bad'):
        feedback=nick(last.get('uid'))+(' 收走 '+str(last.get('value'))+' 张！' if last.get('op')=='slap_ok' else ' 空拍 · 扣1分')
        text(cv,cx,151,feedback,10,RED,'center',True)
    flight=ui.get('orchard_flight')
    if flight:
        t=min(1,(time.monotonic()-flight['start'])/.7)
        if t<1:
            target=seat_centers.get(flight['uid'],(cx,90))
            for i,f in enumerate(flight['cards']):
                fx=cx+(target[0]-cx)*t+i*8;fy=cy+(target[1]-cy)*t-math.sin(t*math.pi)*40
                box(cv,(fx-15,fy-20,fx+15,fy+20),'#fffdf2','#c4973c');_fruit(cv,f,(fx-13,fy-18,fx+13,fy+18))
            schedule=ui.get('_schedule_repaint')
            if callable(schedule):schedule(40)
    py=h-82
    cv.create_oval(cx-17,py-15,cx+17,py+19,fill=GREEN if enabled and st.get('flipped') else '#d4d5c2',outline='#bba375',width=2)
    text(cv,cx,py+2,'→',18,CREAM,'center')
    text(cv,cx+26,py+2,'结束回合',8,INK)
    if enabled and st.get('flipped'):ui['orchard_hits'].append((cx-22,py-20,cx+78,py+23,'pass'))
    counts=st.get('counts') or {};cw=(w-24)/5
    for i,f in enumerate(FRUITS):
        x=12+i*cw;n=counts.get(f,0)
        if n==5:box(cv,(x,h-51,x+cw-4,h-11),'#f4dca0','#bb914a',2)
        _fruit(cv,f,(x+2,h-48,x+31,h-19));text(cv,x+37,h-33,n,13,RED if n==5 else INK,bold=True)
        text(cv,x+37,h-16,'/ 5',7,INK)
    text(cv,12,h-4,'每张1个水果 · F翻牌 / B拍铃 / P结束',7,'#768168')


def click(ui, x, y):
    if not allowed(ui.get("state") or {}, ui.get("me"), ui.get("room"), ui.get("connected", True)):
        return
    for rect in ui.get("orchard_hits", []):
        if hit(rect[:4], x, y):
            op = rect[4]
            flipped = bool((ui.get("state") or {}).get("flipped"))
            if (op == "flip" and not flipped) or (op in ("slap", "pass") and flipped):
                ui["submit"]({"op": op})
            return


def key_action(ui, op):
    if ui.get("game") != "halloween":
        return
    for rect in ui.get("orchard_hits", []):
        if rect[-1] == op:
            click(ui, (rect[0]+rect[2])/2, (rect[1]+rect[3])/2)
            return "break"


def _compact(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    """A proxy maps only Y coordinates; artwork is decoded at physical size."""
    # art() uses the mapped image rectangle size, so scale it before decoding.
    proxy = _Scaled(cv, h/430)
    paint(proxy, st, me, nick, submit, repaint, ui, priv, w, 430)
    ui["orchard_hits"] = [(a, b*h/430, c, d*h/430, op) for a, b, c, d, op in ui["orchard_hits"]]


WEB_JS = r"""
const OrchardTable=(()=>{
 const fruits=['🍓','🍋','🍊','🍌','🍎'],names=['草莓','柠檬','橙子','香蕉','苹果'];
 function el(tag,cls,label){const e=document.createElement(tag);e.className=cls||'';if(label!=null)e.textContent=label;return e;}
 function art(i,label){const e=el('span','orch-art');e.style.backgroundPosition=(i%3*50)+'% '+(Math.floor(i/3)*50)+'%';e.setAttribute('role','img');e.setAttribute('aria-label',label);e.dataset.art=i;return e;}
 function members(s){return s.players||Object.keys(s.score||{}).map(Number);}
 function allowed(s){const r=state.gst&&state.gst.room||{};return state.uid!=null&&(r.players||members(s)).includes(state.uid)&&!(r.spectators||[]).includes(state.uid)&&s.turn===state.uid&&s.winner_uid==null&&s.status!=='ended'&&r.status==='playing';}
 function card(f){const e=el('span','orch-card'),i=fruits.indexOf(f);e.dataset.fruit=f;if(i>=0)e.append(art(i+3,names[i]));return e;}
 function render(box,s){
  const captured={room:state.gst&&state.gst.room,round:state.gst&&state.gst.room&&state.gst.room.round,uid:state.uid,token:state.token,rid:state.groom};const current=()=>state.gst&&state.gst.room===captured.room&&state.gst.state===s&&state.gst.room.round===captured.round&&state.uid===captured.uid&&state.token===captured.token&&state.groom===captured.rid;
  const root=el('section','orch-table'),on=allowed(s),people=members(s),last=s.last_action||{},ended=s.status==='ended';
  root.append(el('h3','','果园社团 / 德国心脏病'),el('p','orch-hint',ended?(s.winner_uid!=null?gnick(s.winner_uid)+' 获胜':'收牌同分 · 平局'):(people.includes(state.uid)?'轮到 '+gnick(s.turn):'旁观席')+' · 同类恰好5个拍铃'));
  function action(op,label){const b=el('button','orch-action');b.type='button';b.dataset.op=op;b.setAttribute('aria-label',label);b.disabled=!on||(op==='flip'?!!s.flipped:!s.flipped);b.onclick=()=>{if(current()&&allowed(s)&&((op==='flip'&&!s.flipped)||(op!=='flip'&&s.flipped)))gameAPI('action',{room_id:state.groom,action:{op}});};return b;}
  const seats=el('div','orch-seats');people.forEach((u,i)=>{const seat=el('article','orch-seat'+(u===state.uid?' orch-me':'')+(u===s.turn?' orch-turn':''));const info=el('div');info.append(el('b','',gnick(u)+(u===state.uid?' · 我':'')),el('small','','得分 '+((s.score||{})[u]||0)));const deck=u===state.uid?action('flip','翻开自己的牌堆'):el('div','orch-deck');deck.classList.add('orch-deck');deck.append(el('i','orch-deck-back','✦'),el('small','',String((s.left||{})[u]||0)));seat.append(art(i%3,'社团成员'),info,deck);seats.append(seat);});root.append(seats);
  const stage=el('div','orch-stage');stage.setAttribute('aria-label','中央桌铃与各家真实翻牌堆');
  const area=s.area_cards||((s.area||[]).map(f=>({fruit:f,uid:null}))),groups=people.map(u=>({u,items:area.filter(c=>c.uid===u).map(c=>c.fruit)})),unknown=area.filter(c=>!people.includes(c.uid)).map(c=>c.fruit);if(unknown.length)groups.push({u:null,items:unknown});const rows=Math.ceil(groups.length/2);
  groups.forEach((g,i)=>{const pile=el('div','orch-pile');pile.dataset.owner=g.u==null?'public':g.u;pile.style.left=i%2?'78%':'2%';pile.style.top=((Math.floor(i/2)+.5)*100/rows)+'%';const stack=el('div','orch-stack');g.items.slice(-3).forEach((f,j)=>{const c=card(f);c.style.left=(j*4)+'px';c.style.top=(-j*4)+'px';stack.append(c);});if(!g.items.length)stack.classList.add('empty');pile.append(stack,el('small','',(g.u==null?'公共牌':gnick(g.u))+' · '+g.items.length+'张'));stage.append(pile);});
  const bell=action('slap','拍中央桌铃'+(s.can_slap?'收走全部公共牌':'，空拍扣分'));bell.classList.add('orch-bell');if(s.can_slap)bell.classList.add('ready');bell.append(art(8,'大号黄铜实体桌铃'),el('b','',s.can_slap?'拍铃收牌':'拍铃'));stage.append(bell);
  if(last.op==='slap_ok'||last.op==='slap_bad')stage.append(el('strong','orch-feedback',gnick(last.uid)+(last.op==='slap_ok'?' 收走 '+last.value+' 张！':' 空拍 · 扣1分')));
  const sig=JSON.stringify([state.groom,last,s.score,s.area]);if(state.orchardSig!==sig){if(last.op==='slap_ok'){state.orchardFlight={until:Date.now()+800,cards:(state.orchardPrev||[]).slice(-3)};}state.orchardSig=sig;}state.orchardPrev=s.area||[];
  if(state.orchardFlight&&Date.now()<state.orchardFlight.until)state.orchardFlight.cards.forEach((f,i)=>{const c=card(f);c.classList.add('orch-flight');c.style.animationDelay=(i*.04)+'s';stage.append(c);});
  root.append(stage);const pass=action('pass','结束本回合');pass.classList.add('orch-pass');pass.append(el('i','','→'),el('small','','结束回合'));root.append(pass);
  const counts=el('div','orch-counts');fruits.forEach((f,i)=>{const n=Number((s.counts||{})[f])||0,t=el('div','orch-count'+(n===5?' five':''));t.dataset.fruit=f;t.dataset.count=n;t.append(art(i+3,names[i]),el('b','',String(n)),el('small','','/5'));counts.append(t);});root.append(counts,el('small','orch-rule','每张1个水果 · 点自己的牌堆翻牌，点中央桌铃收牌'));box.append(root);
 }
 return {render};
})();
"""

WEB_CSS = r"""
#gmain:has(.orch-table){max-height:calc(90vh - 145px)}.orch-table{background:#fff5de;color:#264b42;padding:12px;border:1px solid #cdb88c;border-radius:14px}.orch-table h3{margin:0;font-size:18px}.orch-hint{font-size:11px;color:#647a62;margin:6px 0 12px}.orch-art{display:block;background-image:url('/game-art/arcade-orchard.webp');background-size:300% 300%;aspect-ratio:1;flex-shrink:0}.orch-seats{display:flex;gap:7px;overflow:auto;padding:3px;margin-bottom:8px}.orch-seat{display:grid;grid-template-columns:42px 1fr 31px;align-items:center;gap:6px;padding:6px;border:1px solid #dfcdac;background:#f4ead2;border-radius:8px;min-width:133px;flex:1}.orch-seat>.orch-art{width:42px;border-radius:4px}.orch-seat b,.orch-seat small{display:block;font-size:10px;white-space:nowrap}.orch-seat small{margin-top:4px}.orch-me{outline:2px solid #bb8452}.orch-turn{background:#e4edda}#gmain .orch-action{background:transparent;color:#264b42;padding:0;border:0;box-shadow:none;cursor:pointer;border-radius:0}#gmain .orch-action:disabled{cursor:default}.orch-deck{width:31px;text-align:center}.orch-deck-back{display:block;height:37px;line-height:28px;border:4px double #d8b97d;background:#244e43;color:#fff5de;box-shadow:2px 2px 0 #c7aa70,4px 4px 0 #987c46;border-radius:2px;font-style:normal}.orch-deck:disabled .orch-deck-back{background:#7f9279}.orch-deck small{margin-top:6px}.orch-stage{height:270px;position:relative;background:radial-gradient(ellipse at center,#eadbb8 0%,#f9eed7 64%,#fff5de 75%);margin-top:5px}.orch-pile{position:absolute;width:20%;transform:translateY(-50%);text-align:center}.orch-stack{height:80px;position:relative;max-width:63px;margin:auto}.orch-stack.empty{border:1px dashed #d7c39c;border-radius:5px}.orch-card{display:block;position:absolute;width:100%;height:80px;padding:4px;background:#fffef6;border:1px solid #b49c70;border-radius:4px;box-sizing:border-box;box-shadow:1px 2px 2px #bca98255}.orch-card .orch-art{width:100%;position:absolute;top:50%;left:0;transform:translateY(-50%)}.orch-pile small{display:block;font-size:10px;margin-top:6px;white-space:nowrap}#gmain .orch-bell{position:absolute;width:43%;left:50%;top:50%;transform:translate(-50%,-50%);max-width:210px;border-radius:50%;filter:drop-shadow(0 7px 4px #a68a4b77)}.orch-bell .orch-art{width:100%;border-radius:50%}.orch-bell b{font-size:12px;display:block;color:#a83d4c;margin-top:-4px}.orch-bell.ready{filter:drop-shadow(0 0 10px #e3b239)!important}.orch-feedback{position:absolute;top:3px;left:0;right:0;text-align:center;color:#b94252;font-size:12px}#gmain .orch-pass{display:flex;align-items:center;gap:7px;width:max-content;margin:0 auto 9px}.orch-pass i{display:block;width:32px;height:32px;line-height:29px;border:2px solid #bba375;border-radius:50%;background:#244e43;color:#fff5de;font-size:24px;font-style:normal}.orch-pass:disabled{opacity:.45}.orch-pass small{font-size:10px}.orch-counts{display:grid;grid-template-columns:repeat(5,1fr);gap:4px;border-top:1px solid #dfcdac;padding-top:7px}.orch-count{display:flex;gap:4px;align-items:center;padding:3px}.orch-count .orch-art{width:29px}.orch-count b{font-size:16px}.orch-count small{font-size:9px}.orch-count.five{background:#f4dca0;border:1px solid #bb914a;border-radius:4px}.orch-rule{display:block;font-size:10px;margin-top:7px;color:#647a62}.orch-flight{left:46%;top:45%;width:36px;height:46px;animation:orchard-take .7s ease-out forwards;pointer-events:none}@keyframes orchard-take{from{transform:translate(0,0) rotate(-12deg);opacity:1}to{transform:translate(-70px,-180px) rotate(24deg);opacity:0}}.orch-table button:focus-visible{outline:3px solid #bc9145;outline-offset:3px}@media(max-width:420px){.orch-table{padding:8px}.orch-seat{min-width:125px;grid-template-columns:36px 1fr 27px;padding:4px;gap:4px}.orch-seat>.orch-art{width:36px}.orch-stage{height:245px}.orch-count{gap:2px;padding:1px}.orch-count .orch-art{width:23px}.orch-count b{font-size:14px}.orch-count small{font-size:8px}.orch-stack,.orch-card{height:73px}}
"""

WEB_CSS += r"""
.orch-bell .orch-art{background-image:url('/game-art/arcade-bell.png');background-size:contain;background-position:center!important;background-repeat:no-repeat;border-radius:0}
"""
