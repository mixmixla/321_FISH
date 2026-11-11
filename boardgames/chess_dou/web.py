"""DOM buttons keep native touch, Tab, Enter and Space semantics."""
WEB_CSS = r"""
#gmain:has(.dou-table){max-height:none;flex:1 1 auto;min-height:0}
#gpanel .card:has(.dou-table){height:96vh;max-height:96vh}
body.hasBgArt #gpanel .card:has(.dou-table){background:#edf3e8}
#gpanel .card:has(.dou-table) #glog{max-height:8vh}
.dou-table{max-width:860px;margin:auto;color:#294b3d}
.dou-heading{background:#173e37;color:#fff2d0;border-radius:10px;padding:10px 14px;margin-bottom:10px}
.dou-heading strong{font-size:18px}.dou-heading p{margin:4px 0 0;color:#e0eddd;font-size:13px}
.dou-layout{display:flex;gap:18px;justify-content:center;align-items:flex-start}
.dou-board-wrap{width:min(100%,490px);max-width:calc(70vh - 250px);flex:1;min-width:0}
.dou-coordinates{display:grid;grid-template-columns:repeat(7,1fr);text-align:center;font:11px sans-serif;margin-bottom:3px}
.dou-board{position:relative;display:grid;grid-template-columns:repeat(7,minmax(0,1fr));border:2px solid #709279;box-shadow:0 5px 18px #173e3720;background-image:url('/game-art/dou-terrain.webp');background-size:200% 200%;background-position:0 0}
.dou-table .dou-board button.dou-cell{position:relative;z-index:1;aspect-ratio:1;border:1px solid #76967a;background:transparent;padding:0;min-width:0;border-radius:0;cursor:pointer;touch-action:manipulation;overflow:hidden}
.dou-table .dou-board button.dou-cell:hover,.dou-table .dou-board button.dou-cell:active{transform:none;opacity:1}
.dou-river{position:absolute;pointer-events:none;background-image:url('/game-art/dou-terrain.webp');background-size:200% 200%;background-position:100% 0}
.dou-table .dou-board button.dou-cell:focus-visible{z-index:3;outline:3px solid #1645c1;outline-offset:-3px}
.dou-table .dou-board button.dou-cell[data-selected=true]{z-index:2;box-shadow:inset 0 0 0 4px #ffbd2e}
.dou-portrait{position:absolute;inset:4%;background-image:url('/game-art/dou-beastgirls.webp');background-size:400% 200%;border:2px solid var(--dou-side);box-sizing:border-box}
.dou-ground{position:absolute;inset:0;background-image:url('/game-art/dou-terrain.webp');background-size:200% 200%;pointer-events:none}
.dou-piece-label{position:absolute;bottom:4%;left:4%;right:4%;background:var(--dou-side);color:white;font:bold clamp(8px,2.4vw,12px)/1.3 sans-serif;text-align:center;pointer-events:none}
.dou-terrain{position:absolute;top:0;left:0;background:#fff0ba;font:bold 10px sans-serif;color:var(--dou-side);padding:1px 3px}
.dou-table .dou-board button.dou-cell.has-piece .dou-terrain{position:absolute;top:0;left:0;background:#fff0ba;color:#59452a;font-size:9px;z-index:1}
.dou-table .dou-board button.dou-cell.trap{outline:2px dashed var(--dou-side);outline-offset:-4px}
.dou-table .dou-board button.dou-cell.den .dou-terrain{color:white;background:var(--dou-side)}
.dou-table .dou-board button.dou-cell[data-last=true]::after{content:'';position:absolute;inset:1px;border:2px solid #ed951e;pointer-events:none}
.dou-table .dou-board button.dou-cell[data-legal=true]::before{content:'';position:absolute;z-index:2;inset:34%;border:2px solid #254e38;border-radius:100%;background:#fbe294;pointer-events:none}
.dou-aside{width:190px;flex:none;font-size:13px;line-height:1.8}.dou-aside img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:10px}
.dou-rules{font-size:12px;line-height:1.7;margin-top:8px;background:#e8f0df;padding:8px;border-radius:8px}.dou-help{font-size:12px;text-align:center;margin-top:8px}
@media(max-width:650px){.dou-aside{display:none}.dou-layout{gap:0}.dou-table{padding:0}.dou-heading strong{font-size:16px}}
"""

WEB_JS = r"""
Object.assign(GRENDER,{
dou(box,s){
  const names=['鼠','猫','狗','狼','豹','虎','狮','象'], colours=['#bc454b','#256f99'];
  const players=s.players||[], seat=players.indexOf(state.uid);
  const sideOf=v=>v>=11?1:0, rankOf=v=>v>=11?v-10:v;
  const room=state.gst&&state.gst.room;
  const renderedUid=state.uid, renderedRoom=state.groom, renderedRound=room&&room.round, renderedToken=state.token, renderedPrivate=state.gpriv;
  const active=()=>state.token===renderedToken&&state.gpriv===renderedPrivate&&state.uid===renderedUid&&state.groom===renderedRoom&&state.gst&&state.gst.room===room&&state.gst.room.round===renderedRound
    &&state.gst.state===s&&state.groom&&room&&room.status==='playing'
    &&(room.players||[]).includes(state.uid)&&!(room.spectators||[]).includes(state.uid)
    &&seat>=0&&s.turn_uid===state.uid&&s.winner_uid==null;
  const key=String(state.groom)+':'+String(room&&room.round)+':dou';
  if(state.douContext!==key){state.gsel=null;state.douContext=key;}
  if(!active())state.gsel=null;
  const root=document.createElement('div');root.className='dou-table';box.appendChild(root);
  const heading=document.createElement('div');heading.className='dou-heading';
  const title=document.createElement('strong');title.textContent='斗兽棋 · 兽娘森境';heading.appendChild(title);
  const info=document.createElement('p');info.className='dou-identity';
  info.textContent=(seat<0?'旁观者 · 只读':(seat===0?'你执红方':'你执蓝方'))+' · '+
    (s.winner_uid!=null?gnick(s.winner_uid)+' 获胜':active()?'轮到你':'等待 '+gnick(s.turn_uid));
  heading.appendChild(info);root.appendChild(heading);
  const layout=document.createElement('div');layout.className='dou-layout';root.appendChild(layout);
  const wrap=document.createElement('div');wrap.className='dou-board-wrap';layout.appendChild(wrap);
  const coordinates=document.createElement('div');coordinates.className='dou-coordinates';
  for(const col of 'ABCDEFG'){const e=document.createElement('span');e.textContent=col;coordinates.appendChild(e);}wrap.appendChild(coordinates);
  const grid=document.createElement('div');grid.className='dou-board';grid.setAttribute('role','group');grid.setAttribute('aria-label','斗兽棋七列九行棋盘');wrap.appendChild(grid);
  const rivers=[];let previous=new Map();
  for(let y=0;y<9;y++){
    const current=new Map();let x=0;
    while(x<7){if(!(s.water&&s.water[y]&&s.water[y][x])){x++;continue;}
      const start=x;while(x<7&&s.water[y][x])x++;const key=start+','+(x-start);
      let r=previous.get(key);if(r)r.h++;else{r={x:start,y,w:x-start,h:1};rivers.push(r);}current.set(key,r);}
    previous=current;
  }
  for(const r of rivers){const river=document.createElement('span');river.className='dou-river';
    river.style.cssText='left:'+r.x/7*100+'%;top:'+r.y/9*100+'%;width:'+r.w/7*100+'%;height:'+r.h/9*100+'%';grid.appendChild(river);}
  const dens=new Map(Object.entries(s.dens||{'0':[3,0],'1':[3,8]}).map(([side,pos])=>[pos.join(','),+side]));
  const traps=new Map();for(const [side,squares] of Object.entries(s.traps||{}))for(const pos of squares)traps.set(pos.join(','),+side);
  const sel=state.gsel, legal=sel?gLegalTos(sel[0],sel[1]):[];
  const buttons=[];
  for(let y=0;y<9;y++)for(let x=0;x<7;x++){
    const pos=x+','+y, code=s.board[y][x], rank=rankOf(code), side=sideOf(code), water=!!(s.water&&s.water[y]&&s.water[y][x]);
    const den=dens.get(pos), trap=traps.get(pos), terrainSide=den!=null?den:trap;
    const b=document.createElement('button');b.type='button';b.className='dou-cell'+(water?' water':'')+(trap!=null?' trap':'')+(den!=null?' den':'')+(code?' has-piece':'');
    b.dataset.x=x;b.dataset.y=y;b.style.setProperty('--dou-side',colours[terrainSide==null?side:terrainSide]);
    b.dataset.selected=!!(sel&&sel[0]===x&&sel[1]===y);b.dataset.legal=legal.some(p=>p[0]===x&&p[1]===y);
    b.dataset.last=!!(s.last_move&&s.last_move[1][0]===x&&s.last_move[1][1]===y);
    const terrain=den!=null?'营':trap!=null?'陷':'';
    const label=String.fromCharCode(65+x)+(y+1)+' '+(code?((side===0?'红方':'蓝方')+' '+names[rank-1]+' 等级'+rank):water?'河流':'空地')+(terrain?' '+(terrainSide===0?'红方':'蓝方')+terrain:'');
    b.setAttribute('aria-label',label);b.title=label;b.setAttribute('aria-disabled',String(!active()));
    if(den!=null||trap!=null){const ground=document.createElement('span');ground.className='dou-ground';
      const tile=den!=null?3:2;ground.style.backgroundPosition=(tile%2*100)+'% '+(Math.floor(tile/2)*100)+'%';b.appendChild(ground);}
    if(code){
      const art=document.createElement('span');art.className='dou-portrait';art.style.setProperty('--dou-side',colours[side]);
      art.style.backgroundPosition=(((rank-1)%4)/3*100)+'% '+(Math.floor((rank-1)/4)*100)+'%';b.appendChild(art);
      const caption=document.createElement('span');caption.className='dou-piece-label';caption.style.setProperty('--dou-side',colours[side]);caption.textContent=names[rank-1]+' '+rank;b.appendChild(caption);
    }
    if(terrain){const t=document.createElement('span');t.className='dou-terrain';t.textContent=terrain;b.appendChild(t);}
    b.onclick=()=>{
      if(!b.isConnected||!active())return;
      if(code&&side===seat){state.gsel=sel&&sel[0]===x&&sel[1]===y?null:[x,y];renderGamePanel();return;}
      if(!sel)return;
      if(!gLegalTos(sel[0],sel[1]).some(p=>p[0]===x&&p[1]===y))return;
      const action={fx:sel[0],fy:sel[1],tx:x,ty:y};state.gsel=null;
      gameAPI('action',{room_id:state.groom,action});
    };
    b.onkeydown=e=>{const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];
      if(e.key==='Escape'){state.gsel=null;renderGamePanel();return;}
      if(!delta)return;const nx=x+delta[0],ny=y+delta[1];if(nx>=0&&nx<7&&ny>=0&&ny<9){e.preventDefault();buttons[ny*7+nx].focus();}};
    grid.appendChild(b);buttons.push(b);
  }
  const help=document.createElement('div');help.className='dou-help';help.textContent='点己方兽娘 → 金色落点 · 红/蓝边框表阵营';wrap.appendChild(help);
  const aside=document.createElement('aside');aside.className='dou-aside';
  const cover=document.createElement('img');cover.src='/game-art/cover-dou.webp';cover.alt='八位森境兽娘';aside.appendChild(cover);
  const guide=document.createElement('div');guide.textContent='鼠1 · 猫2 · 狗3 · 狼4 · 豹5 · 虎6 · 狮7 · 象8';aside.appendChild(guide);layout.appendChild(aside);
  const rules=document.createElement('details');rules.className='dou-rules';
  const summary=document.createElement('summary');summary.textContent='行棋规则';rules.appendChild(summary);
  const ruleText=document.createElement('p');ruleText.textContent=(s.rules_variant||'双河 / 狮虎横纵跳河 / 同级可吃')+'。仅鼠入河，鼠能吃象，象不能吃鼠，水陆不能互吃。虚线陷阱属对应阵营，敌人在其中等级归零。红营 D1、蓝营 D9，占敌营获胜。';rules.appendChild(ruleText);root.appendChild(rules);
}
});
"""
