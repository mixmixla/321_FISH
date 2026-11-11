"""Junqi counters: portrait, exact formal rank, side and direct move in one object."""
WEB_CSS = r"""
#gmain:has(.jq-table){max-height:none;flex:1 1 auto;min-height:0}
#gpanel .card:has(.jq-table){height:96vh;max-height:96vh}
body.hasBgArt #gpanel .card:has(.jq-table){background:#e5e9eb}
#gpanel .card:has(.jq-table) #glog{max-height:8vh}
.jq-table{max-width:800px;margin:auto;color:#344e60}.jq-header{background:#223b51;color:#fff2d1;border-radius:10px;padding:10px 14px;margin-bottom:10px}.jq-header strong{font-size:18px}.jq-header p{font-size:13px;margin:5px 0 0;color:#d8e4ed}
.jq-layout{display:flex;align-items:flex-start;justify-content:center;gap:18px}.jq-wrap{flex:1;min-width:0;max-width:min(510px,calc(85vh - 230px))}.jq-cols{display:grid;grid-template-columns:repeat(5,1fr);text-align:center;font:11px sans-serif;margin-bottom:3px}
.jq-board{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));border:5px solid #435d68;background:#c8d7d7;box-shadow:0 4px 15px #223b5130}
.jq-table .jq-board button.jq-cell{position:relative;aspect-ratio:2;border:1px solid #8a9c9f;border-radius:0;background:#c8d7d7;padding:3px;box-shadow:none;min-width:0;min-height:0;overflow:hidden;cursor:pointer;touch-action:manipulation}
.jq-table .jq-board button.jq-cell.bottom{background:#dce3cf}.jq-table .jq-board button.jq-cell:hover,.jq-table .jq-board button.jq-cell:active{transform:none;opacity:1}
.jq-counter{position:absolute;inset:5%;background:#fff3df;border:2px solid var(--jq-side);box-shadow:1px 2px 0 #263b4560;box-sizing:border-box;display:flex;align-items:center}
.jq-art{width:50%;height:100%;flex:none;background-image:url('/game-art/junqi-officers.webp');background-size:400% 300%;background-repeat:no-repeat}
.jq-rank{flex:1;text-align:center;font:bold clamp(10px,3vw,18px) sans-serif;color:var(--jq-side);white-space:nowrap}.jq-locked{position:absolute;bottom:0;right:2px;font-size:8px;color:#7e6b52}
.jq-table .jq-board button.jq-cell[data-selected=true]{outline:3px solid #f9bd31;outline-offset:-3px;z-index:2}.jq-table .jq-board button.jq-cell[data-legal=true]{outline:3px dashed #dd9a0a;outline-offset:-4px;z-index:1}.jq-table .jq-board button.jq-cell[data-last=true]{box-shadow:inset 0 0 0 3px #e39c2c}.jq-table .jq-board button.jq-cell:focus-visible{outline:3px solid #7257b5;outline-offset:-3px;z-index:3}
.jq-help{text-align:center;font-size:12px;margin-top:8px}.jq-rules{font-size:12px;line-height:1.7;margin-top:8px;background:#d6e1e5;padding:8px;border-radius:8px}.jq-inspect{width:150px;flex:none}.jq-preview{width:150px;height:150px;background-image:url('/game-art/junqi-officers.webp');background-size:400% 300%;border:2px solid var(--jq-side);box-sizing:border-box}.jq-inspect p{font-size:13px;text-align:center}
@media(max-width:650px){.jq-inspect{display:flex;width:100%;align-items:center;gap:12px;margin-top:8px}.jq-preview{width:76px;height:76px;flex:none}.jq-inspect p{font-size:12px}.jq-header strong{font-size:16px}.jq-layout{gap:0;flex-wrap:wrap}.jq-wrap{max-width:100%;flex-basis:100%}}
"""

WEB_JS = r"""
Object.assign(GRENDER,{
junqi(box,s){
 const names=['军旗','地雷','炸弹','工兵','排长','连长','营长','团长','旅长','师长','军长','司令'],colours=['#b7414b','#2b6291'];
 const owner=v=>v>=40?1:0,rank=v=>v>=40?v-40:v-10;
 const uid=state.uid,rid=state.groom,room=state.gst&&state.gst.room,round=room&&room.round,seat=(s.players||[]).indexOf(uid),token=state.token,privateFrame=state.gpriv;
 const active=()=>state.token===token&&state.gpriv===privateFrame&&state.uid===uid&&state.groom===rid&&state.gst&&state.gst.room===room&&state.gst.state===s&&state.gst.room.round===round&&room.status==='playing'&&seat>=0&&(room.players||[]).includes(uid)&&!(room.spectators||[]).includes(uid)&&s.turn_uid===uid&&s.winner_uid==null;
 const context=rid+':'+round+':junqi';if(state.junqiContext!==context||!active()){state.gsel=null;state.junqiContext=context;}
 const sel=state.gsel,legal=sel?gLegalTos(sel[0],sel[1]):[];
 const el=(tag,cls,text)=>{const e=document.createElement(tag);e.className=cls;if(text!=null)e.textContent=text;return e;};
 const root=el('section','jq-table');box.appendChild(root);const header=el('div','jq-header');root.appendChild(header);
 header.appendChild(el('strong','','军棋 · 学院战术桌'));header.appendChild(el('p','jq-identity',(seat<0?'旁观者 · 只读':seat===0?'你执红方':'你执蓝方')+' · '+(s.winner_uid!=null?gnick(s.winner_uid)+' 获胜':active()?'轮到你':'等待 '+gnick(s.turn_uid))));
 const layout=el('div','jq-layout');root.appendChild(layout);const wrap=el('div','jq-wrap');layout.appendChild(wrap);
 const coords=el('div','jq-cols');for(const c of 'ABCDE')coords.appendChild(el('span','',c));wrap.appendChild(coords);
 const grid=el('div','jq-board');grid.setAttribute('role','group');grid.setAttribute('aria-label','军棋五列十行明棋棋盘');wrap.appendChild(grid);const buttons=[];
 let selectedRank=11,selectedOwner=Math.max(0,seat);if(sel&&s.board[sel[1]]&&s.board[sel[1]][sel[0]]){selectedRank=rank(s.board[sel[1]][sel[0]]);selectedOwner=owner(s.board[sel[1]][sel[0]]);}
 for(let y=0;y<10;y++)for(let x=0;x<5;x++){
  const code=s.board[y][x],side=owner(code),r=rank(code);const b=el('button','jq-cell'+(y>=5?' bottom':''));b.type='button';b.dataset.x=x;b.dataset.y=y;b.setAttribute('aria-disabled',String(!active()));
  b.dataset.selected=!!(sel&&sel[0]===x&&sel[1]===y);b.dataset.legal=legal.some(p=>p[0]===x&&p[1]===y);b.dataset.last=!!(s.last_move&&s.last_move[1][0]===x&&s.last_move[1][1]===y);
  const label=String.fromCharCode(65+x)+(y+1)+' '+(code?(side===0?'红方':'蓝方')+names[r]+(r<2?' 不可移动':''):'空位');b.setAttribute('aria-label',label);b.title=label;
  if(code){const counter=el('span','jq-counter');counter.style.setProperty('--jq-side',colours[side]);const art=el('span','jq-art');art.style.backgroundPosition=(r%4/3*100)+'% '+(Math.floor(r/4)/2*100)+'%';counter.append(art,el('span','jq-rank',names[r]));if(r<2)counter.appendChild(el('span','jq-locked','◆'));b.appendChild(counter);}
  b.onclick=()=>{if(!b.isConnected||!active())return;
   if(code&&side===seat){if(r<2)return;state.gsel=sel&&sel[0]===x&&sel[1]===y?null:[x,y];renderGamePanel();return;}
   if(!sel||!gLegalTos(sel[0],sel[1]).some(p=>p[0]===x&&p[1]===y))return;
   const action={fx:sel[0],fy:sel[1],tx:x,ty:y};state.gsel=null;gameAPI('action',{room_id:rid,action});};
  b.onkeydown=e=>{if(e.key==='Escape'){state.gsel=null;renderGamePanel();return;}const d={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];if(!d)return;const nx=x+d[0],ny=y+d[1];if(nx>=0&&nx<5&&ny>=0&&ny<10){e.preventDefault();buttons[ny*5+nx].focus();}};
  grid.appendChild(b);buttons.push(b);
 }
 const events={eat:'吃子成功',beaten:'进攻棋子阵亡',trade:'双方兑子',mine_clear:'工兵挖雷',win:'扛旗获胜',move:'阵线推进'};
 wrap.appendChild(el('div','jq-help',events[(s.last_event||{}).kind]||'点己方军棋 → 金色落点 · 军旗/地雷不可动'));
 const inspect=el('aside','jq-inspect'),portrait=el('div','jq-preview');portrait.style.setProperty('--jq-side',colours[selectedOwner]);portrait.style.backgroundPosition=(selectedRank%4/3*100)+'% '+(Math.floor(selectedRank/4)/2*100)+'%';inspect.append(portrait,el('p','',names[selectedRank]),el('p','',selectedRank===0?'不可移动 · 守护军旗':selectedRank===1?'不可移动 · 工兵可挖':selectedRank===2?'接触双方同归':selectedRank===3?'可以挖地雷':'军衔比较 · 同级兑子'));layout.appendChild(inspect);
 const rules=el('details','jq-rules');rules.append(el('summary','','行棋规则'),el('p','','本版为休闲明棋：相邻一步，无铁路与行营。双方各25子，军衔司令至工兵依次降低；同级兑子，炸弹双方同归，只有工兵可挖地雷。进攻更高军衔会阵亡，扛起对方军旗获胜。'));root.appendChild(rules);
}
});
"""
