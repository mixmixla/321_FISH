"""Physical polyomino tray, real 20x20 anchors and seat characters for Blokus."""
WEB_JS = r"""
const BoardsBlokus=(()=>{
 const node=(tag,cls,value)=>{const e=document.createElement(tag);e.className=cls;if(value!=null)e.textContent=value;return e};
 const parse=shape=>(shape||[]).map(v=>v.split(',').map(Number));
 const active=s=>{const r=(state.gst||{}).room||{};return s.winner_uid==null&&s.turn_uid===state.uid&&(s.players||[]).includes(state.uid)&&
   (r.players||s.players||[]).includes(state.uid)&&!(r.spectators||[]).includes(state.uid)&&(!r.status||r.status==='playing')};
 function placement(s,uid,piece,oi,row,col){
  const source=((s.pieces||{})[piece]||[])[oi];if(!source)return {cells:[],ok:false};
  const cells=parse(source).map(([r,c])=>[r+row,c+col]),n=s.size||20,b=s.board;
  if(cells.some(([r,c])=>r<0||r>=n||c<0||c>=n||b[r][c]!=null))return {cells,ok:false};
  if(!((s.placed||{})[uid]))return {cells,ok:cells.some(([r,c])=>(r===0||r===n-1)&&(c===0||c===n-1))};
  const own=(r,c)=>r>=0&&r<n&&c>=0&&c<n&&b[r][c]===uid;
  const edge=cells.some(([r,c])=>[[1,0],[-1,0],[0,1],[0,-1]].some(([dr,dc])=>own(r+dr,c+dc)));
  const corner=cells.some(([r,c])=>[[1,1],[1,-1],[-1,1],[-1,-1]].some(([dr,dc])=>own(r+dr,c+dc)));
  return {cells,ok:corner&&!edge};
 }
 function shape(cells,color){
  const e=node('span','bk-shape'),points=parse(cells),rows=Math.max(...points.map(p=>p[0]))+1,cols=Math.max(...points.map(p=>p[1]))+1;
  e.innerHTML='<svg viewBox="0 0 '+cols*10+' '+rows*10+'" aria-hidden="true">'+points.map(([r,c])=>'<rect x="'+c*10+'" y="'+r*10+'" width="10" height="10" fill="'+color+'" stroke="white" stroke-width=".6"/>').join('')+'</svg>';return e;
 }
 function paint(box,s){
  const room=(state.gst||{}).room||{},token=state.token,key=JSON.stringify([state.groom,room.round,state.uid]);
  if(!state.boardsBlokus||state.boardsBlokus.key!==key)state.boardsBlokus={key,piece:null,oi:0};
  const round=room.round,ui=state.boardsBlokus,me=state.uid,players=s.players||[],colors=s.colors||['#e05555','#3f6fe0','#3ba55d','#e8b93c'],bag=(s.has_piece||{})[me]||[],cat=s.pieces||{};
  if(!bag.includes(ui.piece)){ui.piece=bag[0]||null;ui.oi=0}const orientations=cat[ui.piece]||[];ui.oi=orientations.length?ui.oi%orientations.length:0;
  const current=()=>state.uid===me&&state.token===token&&state.boardsBlokus===ui&&state.groom===room.room_id&&(state.gst||{}).room===room&&(state.gst||{}).room.round===round&&(state.gst||{}).state===s&&active(s)&&root.isConnected&&box.isConnected;
  const send=a=>{if(current())gameAPI('action',{room_id:room.room_id,action:a})};
  const root=node('section','bk-root');root.tabIndex=0;root.setAttribute('aria-label','角斗士棋棋盘，R旋转所选拼块');box.appendChild(root);
  const header=node('div','bk-header');header.append(node('strong','','角斗士棋 · 拼筑工坊'),node('span','',s.winner_uid!=null?gnick(s.winner_uid)+' 获胜':(players.includes(me)?'你的拼块':'观战')+' · 轮到 '+gnick(s.turn_uid)));root.appendChild(header);
  const seats=node('div','bk-seats');root.appendChild(seats);players.forEach((u,i)=>{
   const seat=node('div','bk-seat'+(u===s.turn_uid&&s.winner_uid==null?' bk-active':''));seat.style.borderColor=colors[i];
   const image=node('div','bk-face'),crop=node('div','bk-portrait');crop.style.backgroundPosition=(i%2?'100%':'0%')+' '+(i<2?'0%':'100%');image.appendChild(crop);image.dataset.artIndex=i;
   const name=node('div','bk-name',u===me?'你':gnick(u));name.style.color=colors[i];name.appendChild(node('small','',(s.placed||{})[u]+'格 · '+((s.has_piece||{})[u]||[]).length+'块余'));
   seat.append(image,name);seats.appendChild(seat);
  });
  const layout=node('div','bk-layout'),board=node('div','bk-board'),tray=node('div','bk-tray');root.appendChild(layout);layout.append(board,tray);
  const n=s.size||20,ownColor=colors[players.indexOf(me)]||'#788895',cells=[];
  const preview=(r,c)=>{const p=placement(s,me,ui.piece,ui.oi,r,c);cells.forEach(e=>e.classList.remove('bk-preview','bk-blocked'));
   p.cells.forEach(([y,x])=>{if(y>=0&&y<n&&x>=0&&x<n)cells[y*n+x].classList.add(p.ok?'bk-preview':'bk-blocked')});return p};
  for(let r=0;r<n;r++)for(let c=0;c<n;c++){
   const u=s.board[r][c],e=node('button','bk-cell');e.dataset.row=r;e.dataset.col=c;e.title='棋格 '+(r+1)+'行 '+(c+1)+'列';e.setAttribute('aria-label',e.title);
   if(u!=null){e.style.background=colors[players.indexOf(u)];e.classList.add('bk-occupied');}
   const legal=active(s)&&placement(s,me,ui.piece,ui.oi,r,c).ok;e.disabled=!legal;
   if(legal)e.classList.add('bk-legal');e.onpointerenter=()=>preview(r,c);
   e.onclick=()=>{if(e.isConnected&&current()&&placement(s,me,ui.piece,ui.oi,r,c).ok)send({op:'place',piece:ui.piece,oi:ui.oi,x:r,y:c})};
   board.appendChild(e);cells.push(e);
  }
  for(const [r,c] of s.last_move||[])if(cells[r*n+c])cells[r*n+c].classList.add('bk-last');
  const selected=node('div','bk-selected');tray.appendChild(selected);
  if(ui.piece){selected.append(shape(orientations[ui.oi],ownColor),node('span','',ui.piece+' · '+(ui.oi+1)+'/'+orientations.length));}
  const inventory=node('div','bk-inventory');tray.appendChild(inventory);bag.forEach(piece=>{const b=node('button','bk-tile'+(piece===ui.piece?' bk-picked':''));b.dataset.piece=piece;b.title=piece;b.setAttribute('aria-label','选择拼块 '+piece);b.disabled=!active(s);
   b.appendChild(shape(cat[piece][0],ownColor));b.onclick=()=>{if(b.isConnected&&current()){ui.piece=piece;ui.oi=0;renderGamePanel()}};inventory.appendChild(b)});
  if(!players.includes(me))tray.appendChild(node('div','bk-observer','观战 · 只读'));
  const actions=node('div','bk-actions');root.appendChild(actions);
  const rotate=node('button','bk-rotate','↻ 换向');rotate.dataset.rotate='true';rotate.disabled=!active(s)||!ui.piece;
  const turn=()=>{if(current()&&orientations.length){ui.oi=(ui.oi+1)%orientations.length;renderGamePanel()}};rotate.onclick=()=>{if(rotate.isConnected)turn()};
  const pass=node('button','bk-pass','跳过 ↪');pass.dataset.pass='true';pass.disabled=!active(s);pass.onclick=()=>{if(pass.isConnected)send({op:'pass'})};actions.append(rotate,pass);
  root.onkeydown=e=>{if(e.target===root&&e.key.toLowerCase()==='r'&&!e.ctrlKey&&!e.altKey&&!e.metaKey){e.preventDefault();turn()}};
  root.appendChild(node('div','bk-help',s.winner_uid!=null?'剩余格数最少者胜 · 对局结束':active(s)?'点真实拼块 → 换向 → 点金色落点 · 同边不可接，角对角相连':players.includes(me)?'等待对手拼筑':'观战中 · 只读棋盘'));
 }
 return {paint,placement};
})();
Object.assign(GRENDER,{blokus:BoardsBlokus.paint});
"""
WEB_CSS = r"""
#gmain:has(.bk-root){max-height:calc(90vh - 150px)}
.bk-root{max-width:710px;box-sizing:border-box;background:#eff3ee;padding:10px;margin:auto;color:#293c36;border-radius:12px}.bk-header{display:flex;justify-content:space-between;gap:6px;align-items:center}.bk-header span{font-size:11px}
.bk-seats{display:flex;gap:6px;margin:8px 0}.bk-seat{flex:1;min-width:0;display:flex;gap:6px;border:1px solid;border-radius:8px;padding:3px;background:#fff}.bk-seat.bk-active{outline:2px solid #d4a428}.bk-face{width:46px;height:46px;flex-shrink:0;overflow:hidden;position:relative;border-radius:5px}.bk-portrait{width:100%;aspect-ratio:1;background:url('/game-art/blokus-artisans.webp');background-size:200% 200%;position:absolute;top:50%;transform:translateY(-50%)}.bk-name{font-size:12px;font-weight:700;align-self:center;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.bk-name small{display:block;font-size:10px;color:#687b70;font-weight:400}
.bk-layout{display:grid;grid-template-columns:minmax(0,1fr) 170px;gap:12px;align-items:start}.bk-board{display:grid;grid-template-columns:repeat(20,minmax(0,1fr));aspect-ratio:1;background:#c2ccbf;border:2px solid #7d907e;gap:1px;touch-action:manipulation}
#gmain .bk-root button.bk-cell{box-sizing:border-box;aspect-ratio:1;min-width:0;min-height:0;padding:0;border:0;border-radius:0;background:#f9fbf4;position:relative;box-shadow:none;transform:none;opacity:1}
#gmain .bk-root button.bk-cell.bk-occupied{box-shadow:inset 1px 1px 0 #ffffff70,inset -1px -1px 0 #00000020}
.bk-cell.bk-legal:after{content:'';position:absolute;inset:30%;background:#b78b16;border-radius:50%}#gmain .bk-root button.bk-cell.bk-preview{box-shadow:inset 0 0 0 2px #d4a428;background:#f1d87e}#gmain .bk-root button.bk-cell.bk-blocked{box-shadow:inset 0 0 0 2px #bd4052}.bk-cell.bk-last{outline:2px solid #d4a428;outline-offset:-2px;z-index:1}
.bk-selected{height:52px;display:flex;gap:6px;align-items:center;font-size:11px;margin-bottom:6px}.bk-shape{display:flex;align-items:center;justify-content:center;height:32px;width:42px;pointer-events:none}.bk-shape svg{max-height:100%;max-width:100%;display:block}.bk-selected .bk-shape{height:46px;width:54px}
.bk-inventory{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:4px}#gmain .bk-root button.bk-tile{min-height:38px;min-width:0;padding:3px;display:flex;align-items:center;justify-content:center;background:#fff;border:1px solid #b9c9b9;border-radius:5px;box-shadow:none;opacity:1}#gmain .bk-root button.bk-tile.bk-picked{background:#f6e6a2;border:2px solid #b78b16}.bk-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:8px}#gmain .bk-root button.bk-rotate,#gmain .bk-root button.bk-pass{padding:6px 14px;min-height:34px;border:1px solid #91aa99;border-radius:7px;background:#dfeadd;color:#345a43;box-shadow:none}#gmain .bk-root button:disabled{cursor:default}.bk-help{text-align:center;color:#687b70;font-size:11px;margin-top:7px}
@media(max-width:600px){.bk-root{padding:6px}.bk-header{flex-wrap:wrap}.bk-header strong{font-size:14px}.bk-seats{gap:4px}.bk-face{width:36px;height:36px}.bk-seat{gap:3px}.bk-name{font-size:10px}.bk-name small{font-size:9px}.bk-layout{grid-template-columns:1fr;gap:5px}.bk-tray{display:grid;grid-template-columns:48px minmax(0,1fr);gap:5px}.bk-selected{height:100%;display:flex;flex-direction:column;justify-content:center;font-size:9px;gap:3px}.bk-selected .bk-shape{width:40px;height:40px}.bk-inventory{grid-template-columns:repeat(7,minmax(0,1fr));gap:3px}#gmain .bk-root button.bk-tile{padding:2px;min-height:32px}.bk-tile .bk-shape{height:26px;width:30px}.bk-actions{margin-top:6px}.bk-help{font-size:10px}}
"""
