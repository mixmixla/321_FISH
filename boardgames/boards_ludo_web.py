"""Cloud-island map: forty state-driven SVG stops and physical aircraft."""
WEB_JS = r"""
const BoardsLudo=(()=>{
 const colors=['#bf3546','#2764c9','#18866c','#d59a21'],W=1000,H=760,NS='http://www.w3.org/2000/svg';
 const node=(tag,cls,value)=>{const e=document.createElement(tag);e.className=cls;if(value!=null)e.textContent=value;return e};
 const svg=(tag,attrs={})=>{const e=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));return e};
 const ring=(i,w=W,h=H)=>{i=((i%40)+40)%40;const side=Math.floor(i/10),t=(i%10)/10,a=[[.31,.27],[.69,.27],[.69,.73],[.31,.73]][side],b=[[.5,.02],[.97,.5],[.5,.98],[.03,.5]][side],c=[[.31,.27],[.69,.27],[.69,.73],[.31,.73]][(side+1)%4];return [w*((1-t)**2*a[0]+2*(1-t)*t*b[0]+t*t*c[0]),h*((1-t)**2*a[1]+2*(1-t)*t*b[1]+t*t*c[1])]};
 const parking=(pi,idx)=>{const [x,y]=[[.17,.235],[.83,.235],[.83,.815],[.17,.815]][pi],p=Math.min(W/14,H/10.5);return [x*W+(idx%2-.5)*p,y*H+(Math.floor(idx/2)-.5)*p]};
 const can=s=>{const r=(state.gst||{}).room||{};return s.turn_uid===state.uid&&s.winner_uid==null&&!(s.common||{}).ended&&(s.players||[]).includes(state.uid)&&(r.players||s.players||[]).includes(state.uid)&&!(r.spectators||[]).includes(state.uid)&&(!r.status||r.status==='playing')};
 const moves=s=>{if(!can(s)||s.dice==null)return [];const start=(s.starts||{})[state.uid]||0;return ((s.positions||{})[state.uid]||[]).flatMap((v,i)=>(v===-1&&s.dice===6)||(Number.isInteger(v)&&v>=0&&((v-start+40)%40)+s.dice<=40)?[i]:[])};
 function paint(box,s){
  const uid=state.uid,token=state.token,room=(state.gst||{}).room,roomId=state.groom,round=(room||{}).round,players=s.players||[],positions=s.positions||{},legal=moves(s);
  const current=()=>state.uid===uid&&state.token===token&&state.groom===roomId&&(state.gst||{}).room===room&&room.room_id===roomId&&room.round===round&&(state.gst||{}).state===s&&can(s)&&root.isConnected&&box.isConnected;
  const send=a=>{if(current()&&!(a.op==='roll'&&s.dice!=null)&&!(a.op==='move'&&!moves(s).includes(a.idx)))gameAPI('action',{room_id:roomId,action:a})};
  const root=node('section','ld-root');box.appendChild(root);root.tabIndex=0;root.setAttribute('aria-label','飞行棋云岛航线，R掷骰，1到4选机');
  const header=node('div','ld-header');header.append(node('strong','','飞行棋 · 云岛航线'),node('span','',s.winner_uid!=null?gnick(s.winner_uid)+' 四机到达':(players.includes(uid)?'':'观战 · ')+(s.turn_uid===uid?'你行动':gnick(s.turn_uid)+'行动')));root.appendChild(header);
  const stage=node('div','ld-stage'),board=svg('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':'四机场、四起飞口与40步闭合云端航线'});root.appendChild(stage);stage.appendChild(board);
  board.appendChild(svg('image',{href:'/game-art/ludo-cloud-airports.webp',width:W,height:H,preserveAspectRatio:'xMidYMid slice'}));
  const line=(points,color,width=6,dash)=>{if(points.length<2)return;const e=svg('polyline',{points:points.map(p=>p.join(',')).join(' '),fill:'none',stroke:color,'stroke-width':width,'stroke-linecap':'round','stroke-linejoin':'round','pointer-events':'none'});if(dash)e.setAttribute('stroke-dasharray',dash);board.appendChild(e);return e};
  const route=Array.from({length:121},(_,i)=>ring(i/3));line(route,'#388aa7',44);line(route,'#fff6da',34);line(route,'#c7b878',2,'4 12');
  for(let i=0;i<40;i++){const [x,y]=ring(i),g=svg('g',{'data-stall':i}),col=colors[Math.floor(i/10)];
   const marker=i%10===0?svg('circle',{cx:x,cy:y,r:22,fill:col,stroke:'#fff4c6','stroke-width':4}):svg('path',{d:`M${x},${y-12} ${x+12},${y} ${x},${y+12} ${x-12},${y}Z`,fill:i%5===0?col:'#fffdf1',stroke:col,'stroke-width':2});
   g.appendChild(marker);const title=svg('title');title.textContent='航线第'+(i+1)+'站';g.appendChild(title);board.appendChild(g);
   if(i%10===0){const t=svg('text',{x,y:y+9,'text-anchor':'middle',fill:'#fffdf2','font-size':34,'font-weight':'bold'});t.textContent='»';g.appendChild(t)}
  }
  players.forEach((u,pi)=>{const [cx,cy]=[[.17,.235],[.83,.235],[.83,.815],[.17,.815]][pi],x=cx*W,y=cy*H;
   const portrait=svg('svg',{x:x-23,y:y-109,width:46,height:46,viewBox:'0 0 1 1',overflow:'hidden','data-art-index':pi});portrait.appendChild(svg('image',{href:'/game-art/ludo-aviators.webp',width:2,height:2,x:-(pi%2),y:-Math.floor(pi/2)}));board.appendChild(portrait);
   if(u===s.turn_uid&&s.winner_uid==null)board.appendChild(svg('path',{d:`M${x+30} ${y-105}l20 18-20 18Z`,fill:'#ffda4e',stroke:'#946521','stroke-width':2}));
   const label=svg('text',{x,y:y+95,'text-anchor':'middle',fill:colors[pi],'font-size':23,'font-weight':'bold','paint-order':'stroke',stroke:'#fff8de','stroke-width':4});label.textContent=u===uid?'你':gnick(u).slice(0,6);board.appendChild(label);
  });
  function plane(x,y,pi,idx,{enabled=false,done=false,ghost=false,u=null}={}){
   const g=svg('g',{transform:`translate(${x} ${y}) scale(1.15)`,class:'ld-plane'+(enabled?' ld-legal':'')+(ghost?' ld-ghost':''),'data-uid':u,'data-plane':idx,role:ghost?'img':'button',tabindex:enabled?0:-1,'aria-disabled':String(!enabled),'aria-label':gnick(u)+' '+(idx+1)+'号飞机'+(done?' 已完成':'')});g.disabled=!enabled;
   g.appendChild(svg('circle',{r:36,fill:enabled?'#ffe289':'transparent',stroke:enabled||ghost?'#ce9124':'transparent','stroke-width':4,...(ghost?{'stroke-dasharray':'6 5'}:{})}));
   const d='M0 -32 7 -4 32 8 32 16 7 8 6 21 14 27 14 32 -14 32 -14 27 -6 21 -7 8 -32 16 -32 8 -7 -4Z';
   g.appendChild(svg('path',{d,transform:'translate(4 4)',fill:'#527b86',opacity:.45}));
   g.appendChild(svg('path',{d,fill:ghost?'#fffef1':colors[pi],stroke:'#fff8da','stroke-width':3}));g.appendChild(svg('path',{d:'M0 -26V23',stroke:'#fffdf1','stroke-width':10}));
   g.appendChild(svg('ellipse',{cx:0,cy:-15,rx:4,ry:7,fill:'#24435c'}));const number=svg('text',{x:0,y:16,'text-anchor':'middle','font-size':23,'font-weight':'bold',fill:ghost?colors[pi]:'#233c51'});number.textContent=idx+1;g.appendChild(number);
   if(done){g.appendChild(svg('circle',{cx:24,cy:25,r:15,fill:'#ebffe8',stroke:'#25815d','stroke-width':2}));const tick=svg('text',{x:24,y:33,'text-anchor':'middle','font-size':23,fill:'#25815d'});tick.textContent='✓';g.appendChild(tick)}
   if(!ghost){g.onclick=()=>{if(enabled&&g.isConnected)send({op:'move',idx})};g.onkeydown=e=>{if(enabled&&g.isConnected&&(e.key==='Enter'||e.key===' ')){e.preventDefault();send({op:'move',idx})}}}board.appendChild(g);return g;
  }
  const groups={};players.forEach((u,pi)=>(positions[u]||[]).forEach((v,idx)=>{const enabled=u===uid&&legal.includes(idx);if(v===-1||v==='FIN'){const [x,y]=parking(pi,idx);plane(x,y,pi,idx,{enabled,done:v==='FIN',u})}else if(Number.isInteger(v)){(groups[v]||=[]).push({u,pi,idx,enabled})}}));
  Object.entries(groups).forEach(([stall,tokens])=>{const [x,y]=ring(Number(stall)),cols=Math.ceil(Math.sqrt(tokens.length)),rows=Math.ceil(tokens.length/cols);tokens.forEach((p,k)=>plane(x+(k%cols-(cols-1)/2)*42,y+(Math.floor(k/cols)-(rows-1)/2)*42,p.pi,p.idx,p))});
  let caption='掷出6起飞';const pick=legal.length?legal[0]:null;
  if(pick!=null){const pi=players.indexOf(uid),v=positions[uid][pick],start=(s.starts||{})[uid]||0;let trail,dest;
   if(v===-1){dest=ring(start);trail=[parking(pi,pick),dest];caption=(pick+1)+'号 · 起飞'}else{const fin=((v-start+40)%40)+s.dice===40;trail=Array.from({length:s.dice+1},(_,i)=>ring(v+i));dest=fin?parking(pi,pick):trail.at(-1);if(fin)trail.push(dest);caption=(pick+1)+'号 · 前进'+s.dice+'格'+(fin?' · 到达':'')}
   line(trail,'#f8d247',7,'9 7');plane(...dest,pi,pick,{ghost:true,u:uid});
  }else if(s.last_move){const lm=s.last_move;if(lm.from_stall!=null&&lm.steps)line(Array.from({length:lm.steps+1},(_,i)=>ring(lm.from_stall+i)),'#ffe173',9);caption=(lm.idx+1)+'号 · '+(lm.takeoff?'已起飞':'已前进'+(lm.steps||'')+'格')}
  const die=node('button','ld-die');die.dataset.roll='true';die.disabled=!can(s)||s.dice!=null;die.setAttribute('aria-label','掷骰');
  const face=svg('svg',{viewBox:'0 0 64 64',class:'ld-pips'});face.appendChild(svg('rect',{x:2,y:2,width:60,height:60,rx:10,fill:'#fffdf2',stroke:'#345775','stroke-width':3}));const value=s.dice==null?s.last_roll:s.dice;
  const pips={1:[[32,32]],2:[[18,18],[46,46]],3:[[18,18],[32,32],[46,46]],4:[[18,18],[46,18],[18,46],[46,46]],5:[[18,18],[46,18],[32,32],[18,46],[46,46]],6:[[18,16],[46,16],[18,32],[46,32],[18,48],[46,48]]};
  if(value)(pips[value]||[]).forEach(([cx,cy])=>face.appendChild(svg('circle',{cx,cy,r:5,fill:'#25465b'})));else{const t=svg('text',{x:32,y:44,'text-anchor':'middle','font-size':34,fill:'#345775'});t.textContent='?';face.appendChild(t)}
  die.append(face,node('span','',s.dice==null?'掷骰 · R':'骰值 '+s.dice));die.onclick=()=>{if(die.isConnected)send({op:'roll'})};stage.append(die,node('div','ld-travel',caption));
  const skip=node('button','ld-skip','↪');skip.title='结束回合';skip.setAttribute('aria-label','结束回合');skip.disabled=!can(s);skip.onclick=()=>{if(skip.isConnected)send({op:'skip'})};stage.appendChild(skip);
  const help=node('div','ld-help',s.winner_uid!=null?'四架飞机全部到达 · 对局结束':can(s)?'点飞机起飞/前进 · R掷骰 · 1–4选机':players.includes(uid)?'等待对手机队行动':'观战中 · 只读棋盘');root.appendChild(help);
  root.onkeydown=e=>{if(e.target!==root||e.ctrlKey||e.metaKey||e.altKey)return;if(e.key.toLowerCase()==='r'){e.preventDefault();send({op:'roll'})}else if(/^[1-4]$/.test(e.key)){e.preventDefault();send({op:'move',idx:Number(e.key)-1})}};
 }
 return {paint,ring,moves};
})();
Object.assign(GRENDER,{ludo:BoardsLudo.paint});
"""
WEB_CSS = r"""
#gmain:has(.ld-root){max-height:calc(90vh - 150px)}.ld-root{max-width:760px;margin:auto;color:#21475b;background:#bde8f2;border-radius:10px;overflow:hidden}.ld-header{display:flex;align-items:center;justify-content:space-between;gap:6px;padding:7px 10px;font-size:12px}.ld-header span{font-size:11px}.ld-stage{position:relative;line-height:0}.ld-stage>svg{width:100%;display:block;aspect-ratio:1000/760}.ld-plane.ld-legal{cursor:pointer}.ld-plane:focus-visible{outline:none;filter:drop-shadow(0 0 8px #ffd731)}.ld-ghost{pointer-events:none;opacity:.85}#gmain .ld-root button.ld-die{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);background:transparent;border:0;padding:0;color:#294c66;box-shadow:none;display:flex;align-items:center;flex-direction:column;gap:6px;cursor:pointer;border-radius:8px;font-size:11px;line-height:1.2}#gmain .ld-root button.ld-die:disabled{opacity:1;cursor:default;color:#294c66;background:transparent}.ld-pips{width:clamp(48px,6vw,72px);height:clamp(48px,6vw,72px);filter:drop-shadow(4px 5px 0 #45758b80)}.ld-travel{position:absolute;top:66%;left:50%;transform:translateX(-50%);font-size:12px;font-weight:700;line-height:1.2;color:#234d65;white-space:nowrap;text-shadow:0 1px #e9fbff}#gmain .ld-root button.ld-skip{position:absolute;right:10px;bottom:10px;border:1px solid #819d7b;border-radius:50%;background:#edf4d8;color:#426d56;padding:0;width:32px;height:32px;line-height:1;font-size:23px;box-shadow:none}.ld-help{padding:7px 10px;font-size:11px;line-height:1.3;background:#d8f0f4;text-align:center}.ld-root:focus-visible{outline:2px solid #c99325;outline-offset:-2px}@media(max-width:420px){.ld-header{padding:6px;font-size:12px}.ld-header span{font-size:10px}.ld-travel{font-size:10px;top:68%}.ld-help{font-size:10px;padding:6px}.ld-pips{width:48px;height:48px}}
"""
