"""A yacht-club dice tray and writable scorebook, with rule-owned previews."""
from boardgames.arcade_halloween import _Scaled, art, box, text, hit
from games_pkg.yahtzee import CATS, CAT_CN

ATLAS="arcade-yacht.webp"
NAVY, PAPER, GOLD, INK = "#1c344b", "#fff7e6", "#bb914a", "#243c52"
PIPS={1:((1,1),),2:((0,0),(2,2)),3:((0,0),(1,1),(2,2)),
      4:((0,0),(2,0),(0,2),(2,2)),5:((0,0),(2,0),(1,1),(0,2),(2,2)),
      6:((0,0),(2,0),(0,1),(2,1),(0,2),(2,2))}


def active(st,ui):
    room=ui.get("room") or {};me=ui.get("me")
    return (ui.get("connected",True) is not False and me in st.get("players",[])
            and me not in room.get("spectators",[]) and st.get("turn_uid")==me
            and st.get("winner_uid") is None and st.get("status")=="playing"
            and room.get("status","playing")=="playing")


def die(cv,x,y,size,value,kept=False):
    box(cv,(x,y,x+size,y+size),"#fffdf1",GOLD if kept else "#c5bc9d",3 if kept else 1)
    for px,py in PIPS.get(value,()):
        cx=x+size*(.24+px*.26);cy=y+size*(.24+py*.26);r=max(1.5,size*.067)
        cv.create_oval(cx-r,cy-r,cx+r,cy+r,fill=INK,outline="")


def paint(cv,st,me,nick,submit,repaint,ui,priv,w,h):
    if h<450:
        paint(_Scaled(cv,h/450),st,me,nick,submit,repaint,ui,priv,w,450)
        ui["yacht_hits"]=[(a,b*h/450,c,d*h/450,kind,value) for a,b,c,d,kind,value in ui["yacht_hits"]]
        return
    ui["yacht_hits"]=[]
    context=(ui.get("_room_context"),st.get("round"),st.get("turn_uid"))
    if ui.get("yacht_context")!=context:ui["yacht_keep"]=set();ui["yacht_context"]=context
    keep=ui.setdefault("yacht_keep",set());members=st.get("players") or []
    owner=ui.get("yacht_owner",me if me in members else st.get("turn_uid"))
    if owner not in members:owner=members[0] if members else None
    ui["yacht_owner"]=owner
    enabled=active(st,ui);ended=st.get("winner_uid") is not None or st.get("status")=="ended"
    box(cv,(0,0,w,h),PAPER,PAPER);box(cv,(0,0,w,54),NAVY,NAVY)
    text(cv,14,19,"航海社 / 快艇骰子",14,PAPER,bold=True)
    message=(nick(st.get("winner_uid"))+" 获胜") if ended else "第 "+str(st.get("round",1))+" 动 · "+("轮到你" if enabled else "轮到 "+nick(st.get("turn_uid")))
    text(cv,14,42,message,9,"#d7c598")
    # Player tabs select whose physical scorebook is open; only mine can be written.
    width=(w-24)/max(1,len(members))
    for i,u in enumerate(members):
        x=12+i*width;rect=(x,61,x+width-4,118)
        box(cv,rect,"#e7dfc6" if u==owner else "#f2ead8",GOLD if u==me else "#cfc5ad",2 if u==owner else 1)
        if width>=95:art(cv,ATLAS,i%2,2,2,(x+3,64,x+42,103))
        text(cv,x+width/2,109,nick(u)[:5]+("·我" if u==me else "")+" "+str((st.get("totals") or {}).get(str(u),0)),8,INK,"center",u==st.get("turn_uid"))
        ui["yacht_hits"].append((*rect,"owner",u))
    tray=(12,128,w-96,250);box(cv,tray,"#24485c","#bca677",3)
    box(cv,(18,135,w-102,243),"#294d61","#587482")
    ds=min(76,(w-122)/5-4);start=(12+w-96-5*ds-4*5)/2
    dice=st.get("dice") or [1]*5
    for i,value in enumerate(dice):
        x=start+i*(ds+5);y=154-(8 if i in keep else 0)
        box(cv,(x+2,y+4,x+ds+2,y+ds+4),'#17364a','#17364a')
        die(cv,x,y,ds,value if st.get("rolled") else None,i in keep)
        if i in keep:text(cv,x+ds/2,141,"保留",8,GOLD,"center",True)
        if enabled and st.get("rolled") and st.get("rolls_left",0)>0:
            ui["yacht_hits"].append((x,y,x+ds,y+ds,"keep",i))
    cup=(w-91,130,w-7,249);art(cv,ATLAS,2,2,2,(w-93,135,w-9,229),contain=True)
    can_roll=enabled and (not st.get("rolled") or st.get("rolls_left",0)>0)
    text(cv,w-49,242,"重掷" if st.get("rolled") else "掷骰",10,INK if can_roll else "#8e958f","center",True)
    if can_roll:ui["yacht_hits"].append((*cup,"roll",None))
    text(cv,14,267,"余 "+str(st.get("rolls_left",0))+" 次重掷 · 点骰面保留，点骰盅掷骰",9,INK)
    scores=(st.get("scores") or {}).get(str(owner),{});upper=sum(scores.get(c) or 0 for c in "123456")
    text(cv,14,288,nick(owner)+"的计分纸"+(" · 点落笔格记分" if owner==me else " · 只读"),10,INK,bold=True)
    text(cv,w-14,288,f"上区 {upper}/63",9,INK,"e")
    paper=(12,301,w-12,h-24);box(cv,(15,304,w-9,h-21),'#c8b68d','#b39c70')
    box(cv,paper,'#fffdf2','#c9b98e')
    middle=w*.47;cv.create_line(middle,305,middle,h-28,fill='#cdbd98')
    for column,subset in enumerate((CATS[:6],CATS[6:])):
        left=18 if column==0 else middle+8;right=middle-8 if column==0 else w-20
        text(cv,left,312,'上区 · 点数' if column==0 else '组合区',8,INK,bold=True)
        rh=(h-344)/len(subset)
        for i,cat in enumerate(subset):
            y=324+i*rh;value=scores.get(cat);writable=enabled and owner==me and st.get('rolled') and value is None
            cv.create_line(left,y+rh-1,right,y+rh-1,fill='#dfd5b9')
            if cat in '123456':
                ds2=min(13,rh-3);die(cv,left,y+1,ds2,int(cat))
            else:
                icon={'three':'•••','four':'••••','house':'3+2','small':'1…4','large':'1…5','yahtzee':'5同','chance':'Σ'}[cat]
                text(cv,left,y+rh/2,icon,7,'#7e735b')
            text(cv,left+27,y+rh/2,CAT_CN[cat],8,INK)
            field=(right-39,y+1,right,y+rh-2)
            if writable:box(cv,field,'#eef1dc','#c8bb92')
            preview=(st.get('preview') or {}).get(cat)
            label=str(value) if value is not None else str(preview) if writable and preview is not None else '·'
            text(cv,right-7,y+rh/2,label,10 if value is not None else 9,INK if value is not None else '#78906a','e',value is not None)
            if writable:ui['yacht_hits'].append((left,y,right,y+rh-1,'score',cat))
    text(cv,14,h-9,'13 分类 · 上区 ≥63 奖励35分 · 已记分为墨迹，浅色为试算',8,'#68776d')


def click(ui,x,y):
    st=ui.get("state") or {}
    for rect in ui.get("yacht_hits",[]):
        if not hit(rect[:4],x,y):continue
        kind,value=rect[4:]
        if kind=="owner":ui["yacht_owner"]=value;ui["repaint"]();return
        if not active(st,ui):return
        if kind=="keep" and st.get("rolled") and st.get("rolls_left",0)>0:
            keep=ui.setdefault("yacht_keep",set());keep.symmetric_difference_update({value});ui["repaint"]()
        elif kind=="roll":
            if not st.get("rolled"):ui["submit"]({"op":"roll"})
            elif st.get("rolls_left",0)>0:ui["submit"]({"op":"reroll","keep":sorted(ui.get("yacht_keep") or ())})
        elif kind=="score" and st.get("rolled") and ui.get("yacht_owner")==ui.get("me") and (st.get("scores") or {}).get(str(ui.get("me")),{}).get(value) is None:
            ui["submit"]({"op":"score","cat":value})
        return


WEB_JS=r"""
const YachtTable=(()=>{
 const cats=['1','2','3','4','5','6','three','four','house','small','large','yahtzee','chance'];
 const names={'1':'1点','2':'2点','3':'3点','4':'4点','5':'5点','6':'6点',three:'三条',four:'四条',house:'葫芦',small:'小顺',large:'大顺',yahtzee:'快艇',chance:'任意'};
 const pips={1:[[1,1]],2:[[0,0],[2,2]],3:[[0,0],[1,1],[2,2]],4:[[0,0],[2,0],[0,2],[2,2]],5:[[0,0],[2,0],[1,1],[0,2],[2,2]],6:[[0,0],[2,0],[0,1],[2,1],[0,2],[2,2]]};
 function el(tag,cls,label){const e=document.createElement(tag);e.className=cls||'';if(label!=null)e.textContent=label;return e;}
 function art(i,label){const e=el('span','yacht-art');e.style.backgroundPosition=(i%2*100)+'% '+(Math.floor(i/2)*100)+'%';e.setAttribute('role','img');e.setAttribute('aria-label',label);return e;}
 function active(s){const room=state.gst&&state.gst.room||{};return (s.players||[]).includes(state.uid)&&!(room.spectators||[]).includes(state.uid)&&s.turn_uid===state.uid&&s.winner_uid==null&&s.status==='playing'&&room.status==='playing';}
 function render(box,s){
  const captured={room:state.gst&&state.gst.room,round:state.gst&&state.gst.room&&state.gst.room.round,uid:state.uid,token:state.token,rid:state.groom};const current=()=>state.gst&&state.gst.room===captured.room&&state.gst.state===s&&state.gst.room.round===captured.round&&state.uid===captured.uid&&state.token===captured.token&&state.groom===captured.rid;
  const context=JSON.stringify([state.groom,s.round,s.turn_uid,state.uid,state.token]);if(state.yachtContext!==context){state.yachtContext=context;state.yachtKeep=[];}const keep=state.yachtKeep||[];
  const members=s.players||[];if(!members.includes(state.yachtOwner))state.yachtOwner=members.includes(state.uid)?state.uid:s.turn_uid;const owner=state.yachtOwner;
  const on=active(s),rolled=!!s.rolled,root=el('section','yacht-table');root.setAttribute('aria-label','航海社 快艇骰子');
  root.append(el('h3','','航海社 / 快艇骰子'),el('p','yacht-hint',s.winner_uid!=null?gnick(s.winner_uid)+' 获胜':'第 '+s.round+' 动 · 轮到 '+gnick(s.turn_uid)));
  const seats=el('div','yacht-seats');members.forEach((u,i)=>{const seat=el('button','yacht-seat'+(u===owner?' chosen':'')+(u===state.uid?' mine':''));seat.type='button';seat.setAttribute('aria-label','查看 '+gnick(u)+' 的计分纸');seat.append(art(i%2,'社团成员'),el('b','',gnick(u)+(u===state.uid?' · 我':'')),el('small','','总分 '+((s.totals||{})[u]||0)));seat.onclick=()=>{state.yachtOwner=u;renderGamePanel();};seats.append(seat);});root.append(seats);
  const tray=el('div','yacht-tray'),dice=el('div','yacht-dice');(s.dice||[]).forEach((v,i)=>{const d=el('button','yacht-die'+(keep.includes(i)?' held':''));d.type='button';d.dataset.index=i;d.dataset.value=rolled?v:0;d.setAttribute('aria-label','第 '+(i+1)+' 枚骰子'+(rolled?' '+v+'点':' 未掷')+(keep.includes(i)?' 已保留':''));d.setAttribute('aria-pressed',String(keep.includes(i)));for(const [x,y] of rolled?(pips[v]||[]):[]){const p=el('i','yacht-pip');p.style.left=(22+x*28)+'%';p.style.top=(22+y*28)+'%';d.append(p);}d.disabled=!on||!rolled||s.rolls_left<=0;d.onclick=()=>{if(!current()||!active(s)||!rolled||s.rolls_left<=0)return;state.yachtKeep=keep.includes(i)?keep.filter(k=>k!==i):[...keep,i];renderGamePanel();};dice.append(d);});
  const cup=el('button','yacht-cup');cup.type='button';cup.dataset.op=rolled?'reroll':'roll';cup.setAttribute('aria-label',rolled?'重掷未保留的骰子':'掷五枚骰子');cup.append(art(2,'骰盅'),el('b','',rolled?'重掷':'掷骰'));cup.disabled=!on||(rolled&&s.rolls_left<=0);cup.onclick=()=>{if(!current()||!active(s))return;if(!rolled)gameAPI('action',{room_id:state.groom,action:{op:'roll'}});else if(s.rolls_left>0)gameAPI('action',{room_id:state.groom,action:{op:'reroll',keep:keep.slice().sort((a,b)=>a-b)}});};tray.append(dice,cup);root.append(tray,el('p','yacht-hint','余 '+(s.rolls_left||0)+' 次重掷 · 点骰子保留，点骰盅掷骰'));
  const scores=(s.scores||{})[owner]||{},upper=['1','2','3','4','5','6'].reduce((n,c)=>n+(scores[c]||0),0);
  root.append(el('h4','',gnick(owner)+'的计分纸 · 上区 '+upper+'/63'));
  const sheet=el('div','yacht-sheet');sheet.setAttribute('aria-label','十三类计分纸');const columns=[el('div','yacht-column'),el('div','yacht-column')];columns[0].append(el('h5','','上区 · 点数'));columns[1].append(el('h5','','组合区'));cats.forEach((c,i)=>{const value=scores[c],can=on&&owner===state.uid&&rolled&&value==null,b=el('button','yacht-cell'+(value!=null?' inked':''));b.type='button';b.dataset.cat=c;b.disabled=!can;const icon=el('i','yacht-cat-icon',i<6?c:({three:'•••',four:'••••',house:'3+2',small:'1…4',large:'1…5',yahtzee:'5同',chance:'Σ'})[c]);b.append(icon,el('span','',names[c]),el('b','',value!=null?String(value):(can&&s.preview&&s.preview[c]!=null?String(s.preview[c]):'·')));b.setAttribute('aria-label',names[c]+(value!=null?' 已记 '+value:can?' 记 '+((s.preview||{})[c]??'?')+' 分':' 未记分'));b.onclick=()=>{if(current()&&active(s)&&owner===state.uid&&rolled&&scores[c]==null)gameAPI('action',{room_id:state.groom,action:{op:'score',cat:c}});};columns[i<6?0:1].append(b);});sheet.append(...columns);root.append(sheet,el('small','yacht-hint','13 分类 · 上区 ≥63 奖励35分 · 墨迹为已记，浅色为试算'));box.append(root);
 }
 return {render};
})();
"""

WEB_CSS=r"""
#gmain .yacht-die{background:#fffdf1;box-shadow:1px 3px 1px #182f40}#gmain .yacht-seat{background:#f7edda;color:#243c52;box-shadow:none}#gmain .yacht-seat.mine{background:#e9e2c8}#gmain .yacht-cup{background:transparent;color:#243c52;box-shadow:none}#gmain .yacht-cell{background:#e8efd9;color:#243c52;box-shadow:none;border-radius:1px}#gmain .yacht-cell:disabled{background:#fffdf3}#gmain:has(.yacht-table){max-height:calc(90vh - 145px)}.yacht-table{padding:15px;background:#fff7e6;color:#243c52;border:1px solid #c6aa70;border-radius:12px}.yacht-table h3{margin:0;font-size:19px}.yacht-table h4{font-size:13px;margin:12px 0 9px}.yacht-hint{display:block;font-size:11px;color:#63746d;margin:7px 0 10px}.yacht-art{display:block;aspect-ratio:1;background:url('/game-art/arcade-yacht.webp');background-size:200% 200%;flex-shrink:0}.yacht-seats{display:flex;gap:7px;overflow:auto;padding:3px}.yacht-seat{border:1px solid #c9b88e;background:#f7edda;color:#243c52;border-radius:6px;padding:5px;display:grid;grid-template-columns:38px auto;gap:3px 6px;min-width:110px;cursor:pointer;font:inherit}.yacht-seat .yacht-art{width:38px;border-radius:4px;grid-row:span 2}.yacht-seat b{font-size:11px;align-self:end}.yacht-seat small{font-size:10px}.yacht-seat.chosen{outline:2px solid #bb914a}.yacht-seat.mine{background:#e9e2c8}.yacht-tray{display:flex;gap:8px;align-items:center;margin-top:12px}.yacht-dice{display:flex;justify-content:space-evenly;align-items:center;gap:6px;flex:1;padding:18px 10px 12px;background:#24485c;border:2px solid #bca677;border-radius:12px;min-width:0}.yacht-die{position:relative;aspect-ratio:1;flex:1;min-width:0;max-width:65px;background:#fffdf1;border:1px solid #c5bc9d;border-radius:9px;box-shadow:1px 3px 1px #182f40;cursor:pointer;padding:0}.yacht-die.held{outline:3px solid #c6a25d;transform:translateY(-7px)}.yacht-die.held:after{content:'保留';position:absolute;font-size:9px;color:#fff1bb;top:-16px;left:0;right:0}.yacht-die:disabled{cursor:default}.yacht-pip{position:absolute;width:12%;height:12%;border-radius:50%;background:#243c52;transform:translate(-50%,-50%)}.yacht-cup{background:none;border:0;padding:0;min-width:57px;max-width:75px;width:15%;font:inherit;color:#243c52;cursor:pointer}.yacht-cup .yacht-art{width:100%}.yacht-cup b{font-size:12px}.yacht-cup:disabled{opacity:.5;cursor:default}.yacht-sheet{display:grid;grid-template-columns:repeat(3,1fr);gap:5px;padding:8px;background:#e6d8b7;border:1px solid #bba26b;border-radius:4px;box-shadow:3px 3px 0 #c8b68d}.yacht-cell{display:flex;align-items:center;justify-content:space-between;background:#e8efd9;color:#243c52;border:1px solid #b89e62;min-height:37px;padding:7px 6px;cursor:pointer;font:inherit;min-width:0}.yacht-cell span{font-size:11px}.yacht-cell b{font-size:13px}.yacht-cell:disabled{background:#fffdf3;border-color:#d2c6a9;cursor:default}.yacht-cell.inked b{font-style:italic;color:#173557}.yacht-table button:focus-visible{outline:3px solid #bd9a4b;outline-offset:2px}@media(max-width:420px){.yacht-table{padding:9px}.yacht-dice{padding:17px 6px 12px;gap:5px}.yacht-cell{padding:6px 4px}.yacht-cell span{font-size:10px}.yacht-cell b{font-size:11px}}
"""

WEB_CSS += r"""
.yacht-dice{min-height:95px;padding:25px 12px 18px;border-width:3px;box-shadow:inset 0 0 0 6px #34576c,inset 0 5px 12px #122c3b}.yacht-die{max-width:78px}.yacht-cup{width:18%;max-width:95px;min-width:63px}.yacht-sheet{display:grid;grid-template-columns:1fr 1.15fr;gap:0;background:#fffdf2;padding:8px 9px;border:1px solid #c9b98e;border-radius:1px;box-shadow:3px 3px 0 #c8b68d}.yacht-column{padding:0 7px;min-width:0}.yacht-column+ .yacht-column{border-left:1px solid #cdbd98}.yacht-column h5{font-size:11px;margin:0 0 7px;font-weight:600;color:#7b6e54}#gmain .yacht-cell{width:100%;display:grid;grid-template-columns:27px 1fr 34px;gap:3px;min-height:25px;padding:2px 0;background:transparent;border:0;border-bottom:1px solid #dfd5b9;color:#243c52;border-radius:0;text-align:left}#gmain .yacht-cell:disabled{background:transparent}.yacht-cell b{display:block;text-align:right;padding:3px 5px;font-size:12px;border:1px solid #c8bb92;background:#eef1dc;font-weight:400;color:#78906a}.yacht-cell:disabled b{background:transparent;border-color:transparent}.yacht-cell.inked b{font-weight:700;color:#173557}.yacht-cell span{font-size:11px}.yacht-cat-icon{font-style:normal;font-size:9px;color:#7e735b}.yacht-table h4{margin:12px 0 7px}@media(max-width:420px){.yacht-dice{min-height:78px;padding:22px 6px 12px}.yacht-column{padding:0 4px}#gmain .yacht-cell{grid-template-columns:23px 1fr 26px}.yacht-cell span{font-size:10px}.yacht-cell b{font-size:11px;padding:3px}.yacht-cat-icon{font-size:8px}.yacht-sheet{padding:7px 4px}}
"""
