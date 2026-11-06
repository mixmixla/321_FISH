"""A numbered puzzle board; the secret and legal interval remain server-owned."""
from boardgames.arcade_halloween import art,box,text,hit

ATLAS='arcade-numbers.webp'
INK,PAPER,PLUM,TEAL,GOLD='#33494b','#f5efdf','#60405d','#356e69','#b99853'


def member(st,ui):
    r=ui.get('room') or {};me=ui.get('me')
    return me is not None and me in r.get('players',[int(u) for u in st.get('scores',{})]) and me not in r.get('spectators',[])


def allowed(st,ui,n):
    if not member(st,ui) or ui.get('connected',True) is False or (ui.get('room') or {}).get('status','playing')!='playing':return False
    if st.get('status')=='await_secret':return ui.get('me')==st.get('owner_uid') and 1<=n<=100
    return st.get('status')=='playing' and st.get('low',1)<=n<=st.get('high',100)


def choose(ui,n):
    st=ui.get('state') or {}
    if allowed(st,ui,n):ui['submit']({'secret' if st.get('status')=='await_secret' else 'guess':n})


def key(ui,delta=None):
    if ui.get('game')!='guess_number':return
    st=ui.get('state') or {};low,high=(1,100) if st.get('status')=='await_secret' else (st.get('low',1),st.get('high',100))
    n=ui.get('number_focus',(low+high)//2)
    if delta is None:choose(ui,n)
    else:
        n=max(low,min(high,n+delta));ui.update(number_focus=n,number_page=(n-1)//25);ui.get('repaint',lambda:None)()
    return 'break'


def paint(cv,st,me,nick,submit,repaint,ui,priv,w,h):
    context=(ui.get('_room_context'),st.get('round'),me)
    if ui.get('number_context')!=context:ui.update(number_context=context,number_page=0,number_focus=50)
    ui['number_hits']=[]
    if isinstance(getattr(cv,'_w',None),str):
        cv._number_ui=ui
        if not getattr(cv,'_number_keys',False):
            for name,delta in (('Left',-1),('Right',1),('Up',-5),('Down',5)):
                cv.bind('<'+name+'>',lambda e,d=delta:key(cv._number_ui,d),add='+')
            cv.bind('<Return>',lambda e:key(cv._number_ui),add='+');cv._number_keys=True
    low,high=st.get('low',1),st.get('high',100);phase=st.get('status');own=member(st,ui) and me==st.get('owner_uid')
    box(cv,(0,0,w,h),PAPER,PAPER);box(cv,(0,0,w,54),PLUM,PLUM)
    text(cv,14,18,'秘数社 / 猜数字',14,PAPER,bold=True)
    label=('选择一个数字锁入密匣' if own else '等待出题者锁入数字') if phase=='await_secret' else ('命中 '+str(st.get('secret'))+' · '+nick(st.get('correct_uid'))+' +1分' if phase=='round_end' else '点数字牌猜测 · 合法区间 '+str(low)+'—'+str(high))
    text(cv,14,42,label,9,'#dfcfa6')
    text(cv,14,76,low,14,TEAL,bold=True);text(cv,w-14,76,high,14,TEAL,'e',True)
    cv.create_line(48,77,w-48,77,fill='#d7cbb0',width=8)
    cv.create_line(48+(w-96)*(low-1)/99,77,48+(w-96)*(high-1)/99,77,fill=TEAL,width=8)
    guess=st.get('last_guess') or {}
    text(cv,w/2,97,(str(guess.get('val'))+' '+{'low':'偏低 ↑','high':'偏高 ↓','hit':'命中 ✓'}.get(guess.get('dir'),'') if guess else '1—100数字牌 · 每页25张'),9,INK,'center')
    left=w*.31
    art(cv,ATLAS,0 if own else 1,2,2,(12,112,left,h-73))
    art(cv,ATLAS,2,2,2,(left/2-15,h-137,left/2+40,h-82),contain=True)
    text(cv,12,h-58,('出题席' if own else '玩家席' if member(st,ui) else '旁观席'),9,PLUM,bold=True)
    scores=st.get('scores') or {};score=scores.get(me,scores.get(str(me),0))
    text(cv,12,h-39,'我的积分 '+str(score),9,INK)
    bx=left+13;bw=w-bx-12;tw=(bw-12)/5;th=(h-177)/5;page=max(0,min(3,ui.get('number_page',0)))
    if phase=='playing' and not any(low<=n<=high for n in range(page*25+1,page*25+26)):
        page=(low-1)//25;ui['number_page']=page
    if phase=='round_end' and st.get('secret') is not None:page=(st['secret']-1)//25
    for i in range(25):
        n=page*25+i+1;x=bx+i%5*(tw+3);y=111+i//5*(th+3);rect=(x,y,x+tw,y+th)
        can=allowed(st,ui,n);live=phase=='await_secret' or low<=n<=high
        box(cv,(x+1,y+2,x+tw+1,y+th+2),'#c8bc9f','#c8bc9f')
        won=phase=='round_end' and n==st.get('secret')
        box(cv,rect,'#eed08d' if won else '#fffcf0' if live else '#dfdfd0',TEAL if won else GOLD if n==ui.get('number_focus') else '#c0ae82',3 if won else 2 if n==ui.get('number_focus') else 1)
        text(cv,x+tw/2,y+th/2,n,14,INK if live else '#a8aa98','center',True)
        if not live:cv.create_line(x+7,y+th/2,x+tw-7,y+th/2,fill='#a8aa98')
        if can:ui['number_hits'].append((*rect,'number',n))
    for p in range(4):
        x=bx+p*bw/4;rect=(x,h-50,x+bw/4-4,h-23)
        box(cv,rect,'#d9c695' if p==page else '#e9dfc6','#c1ab77')
        text(cv,(rect[0]+rect[2])/2,h-36,f'{p*25+1}—{p*25+25}',8,INK,'center',p==page)
        ui['number_hits'].append((*rect,'page',p))
    text(cv,12,h-11,'点牌提交 · 方向键选牌，Enter确认 · 灰牌已排除',8,'#75806e')


def click(ui,x,y):
    for rect in ui.get('number_hits',[]):
        if not hit(rect[:4],x,y):continue
        if rect[4]=='page':ui['number_page']=rect[5];ui.get('repaint',lambda:None)()
        else:choose(ui,rect[5])
        return


WEB_JS=r"""
const NumberTable=(()=>{
 function el(tag,cls,value){const e=document.createElement(tag);e.className=cls||'';if(value!=null)e.textContent=value;return e;}
 function art(i,label){const e=el('span','number-art');e.style.backgroundPosition=(i%2*100)+'% '+(Math.floor(i/2)*100)+'%';e.setAttribute('role','img');e.setAttribute('aria-label',label);return e;}
 function member(s){const r=state.gst&&state.gst.room||{};return (r.players||Object.keys(s.scores||{}).map(Number)).includes(state.uid)&&!(r.spectators||[]).includes(state.uid);}
 function allowed(s,n){const r=state.gst&&state.gst.room||{};return r.status==='playing'&&member(s)&&(s.status==='await_secret'?s.owner_uid===state.uid&&n>=1&&n<=100:s.status==='playing'&&n>=s.low&&n<=s.high);}
 function render(box,s){
  const r=state.gst&&state.gst.room||{},context=JSON.stringify([state.groom,r.round,s.round,state.uid]),own=member(s)&&s.owner_uid===state.uid;if(state.numberContext!==context){state.numberContext=context;state.numberPage=0;}
  const captured={room:state.gst&&state.gst.room,round:state.gst&&state.gst.room&&state.gst.room.round,uid:state.uid,token:state.token,rid:state.groom};const current=()=>state.gst&&state.gst.room===captured.room&&state.gst.state===s&&state.gst.room.round===captured.round&&state.uid===captured.uid&&state.token===captured.token&&state.groom===captured.rid;
  let page=state.numberPage||0;if(s.status==='playing'&&(page*25+25<s.low||page*25+1>s.high))page=Math.floor((s.low-1)/25);if(s.status==='round_end'&&s.secret!=null)page=Math.floor((s.secret-1)/25);
  const root=el('section','number-table');root.append(el('h3','','秘数社 / 猜数字'),el('p','number-hint',s.status==='await_secret'?(own?'选择一个数字锁入密匣':'等待出题者锁入数字'):s.status==='round_end'?'命中 '+s.secret+' · '+gnick(s.correct_uid)+' +1分':'点数字牌猜测 · 合法区间 '+s.low+'—'+s.high));
  const range=el('div','number-range');range.append(el('b','',String(s.low)),el('b','',String(s.high)));const track=el('div','number-track'),fill=el('i');fill.style.left=((s.low-1)/99*100)+'%';fill.style.width=((s.high-s.low)/99*100)+'%';track.append(fill);range.append(track);root.append(range);
  if(s.last_guess)root.append(el('p','number-hint',s.last_guess.val+' '+({low:'偏低 ↑',high:'偏高 ↓',hit:'命中 ✓'})[s.last_guess.dir]));
  const layout=el('div','number-layout'),role=el('aside','number-role');const portrait=art(own?0:1,own?'出题者':'解谜者');portrait.style.backgroundSize='307.6923% 200%';portrait.style.backgroundPosition=(own?'12.963%':'87.037%')+' 0%';role.append(portrait,art(2,'密封数字匣'),el('b','',own?'出题席':member(s)?'玩家席':'旁观席'),el('small','','我的积分 '+((s.scores||{})[state.uid]||0)));layout.append(role);
  const side=el('div','number-side'),board=el('div','number-board');board.setAttribute('aria-label','可点的1到100数字牌');for(let i=0;i<25;i++){const n=page*25+i+1,live=s.status==='await_secret'||n>=s.low&&n<=s.high,won=s.status==='round_end'&&n===s.secret,b=el('button','number-card'+(!live?' excluded':'')+(won?' hit':''),String(n));b.type='button';b.dataset.value=n;b.disabled=!allowed(s,n);b.setAttribute('aria-label',(s.status==='await_secret'?'密封数字 ':'猜数字 ')+n);b.onclick=()=>{if(current()&&state.numberContext===context&&allowed(s,n))gameAPI('action',{room_id:state.groom,action:{[s.status==='await_secret'?'secret':'guess']:n}});};board.append(b);}side.append(board);
  const tabs=el('div','number-tabs');for(let p=0;p<4;p++){const b=el('button',p===page?'chosen':'',String(p*25+1)+'—'+String(p*25+25));b.type='button';b.dataset.page=p;b.onclick=()=>{state.numberPage=p;renderGamePanel();};tabs.append(b);}side.append(tabs);layout.append(side);root.append(layout,el('small','number-hint','点牌直接提交 · 灰牌已排除 · 原生Tab/Enter可用'));box.append(root);
 }
 return {render};
})();
"""

WEB_CSS=r"""
#gmain:has(.number-table){max-height:calc(90vh - 145px)}.number-table{background:#f5efdf;color:#33494b;padding:12px;border:1px solid #c7b68f;border-radius:10px}.number-table h3{margin:0;font-size:18px}.number-hint{display:block;font-size:11px;margin:8px 0 12px;color:#716d5e}.number-range{position:relative;display:flex;justify-content:space-between;gap:20px;padding-bottom:18px;color:#356e69;font-size:20px}.number-track{position:absolute;left:0;right:0;bottom:3px;height:7px;background:#d9d0b7;border-radius:4px}.number-track i{position:absolute;top:0;height:100%;background:#356e69;border-radius:4px;min-width:3px}.number-layout{display:grid;grid-template-columns:30% 1fr;gap:12px;align-items:start}.number-art{display:block;aspect-ratio:1;background:url('/game-art/arcade-numbers.webp');background-size:200% 200%}.number-role{min-width:0;position:relative}.number-role>.number-art:first-child{aspect-ratio:.65;border:1px solid #b99853}.number-role>.number-art:nth-child(2){width:60%;margin:-35px auto 6px;position:relative}.number-role b,.number-role small{display:block;font-size:11px;margin-top:6px}.number-board{display:grid;grid-template-columns:repeat(5,1fr);gap:5px}#gmain .number-card{aspect-ratio:1;min-width:0;padding:0;background:#fffcf0;color:#33494b;border:1px solid #c0ae82;box-shadow:1px 2px 0 #c8bc9f;border-radius:3px;font-size:18px}#gmain .number-card.excluded{background:#dfdfd0;color:#a8aa98;text-decoration:line-through}#gmain .number-card.hit{background:#eed08d;color:#356e69;outline:2px solid #356e69}.number-card:disabled{opacity:1;cursor:default}.number-tabs{display:grid;grid-template-columns:repeat(4,1fr);gap:3px;margin-top:12px}#gmain .number-tabs button{background:#e9dfc6;color:#33494b;border:1px solid #c1ab77;border-radius:3px;padding:5px 0;font-size:10px;box-shadow:none}#gmain .number-tabs button.chosen{background:#d9c695}.number-table button:focus-visible{outline:3px solid #60405d;outline-offset:2px}@media(max-width:420px){.number-table{padding:8px}.number-layout{grid-template-columns:26% 1fr;gap:8px}.number-board{gap:4px}#gmain .number-card{font-size:16px}.number-tabs{gap:2px}#gmain .number-tabs button{font-size:8px}.number-role b,.number-role small{font-size:10px}}
"""
