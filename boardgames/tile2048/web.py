# -*- coding: utf-8 -*-
"""2048 网页渲染：四向按钮 + 手机滑动，共享 ``move/dir`` 动作契约。"""

WEB_JS = r"""
Object.assign(GRENDER,{
  tile2048(box,s){
    box.appendChild(gTitle("tile2048","2048 · 方块合成"));
    const values=(s.board||[]).map(r=>Array.isArray(r)?r:[]);
    while(values.length<4)values.push([]);
    const board=values.slice(0,4).map(r=>r.slice(0,4).concat([0,0,0,0]).slice(0,4));
    const done=s.status==="won"||s.status==="lost"||s.winner_uid!=null;
    const room=state.gst&&state.gst.room;
    const active=!done&&room&&room.status==="playing"&&(s.turn_uid==null||s.turn_uid===state.uid)
      &&(s.players||[]).includes(state.uid);
    const root=document.createElement("div");root.className="t2048-root";
    const info=document.createElement("div");info.className="t2048-info";
    const score=document.createElement("span");score.className="t2048-score";
    score.innerHTML="<small>分数</small><b>"+(Number(s.score)||0)+"</b>";
    const note=document.createElement("span");note.className="t2048-note";
    note.textContent=s.status==="won"?"🏆 达成 2048！":(s.status==="lost"?"💥 无路可走":"向任意方向滑动或点击按钮");
    info.append(note,score);root.appendChild(info);

    const grid=document.createElement("div");grid.className="t2048-grid";
    grid.setAttribute("role","grid");grid.setAttribute("aria-label","2048 棋盘");
    const stages=[2,4,8,16,32,64,128,256,512,1024,2048];
    board.forEach((row,y)=>row.forEach((value,x)=>{
      const cell=document.createElement("div");cell.className="t2048-cell";
      cell.setAttribute("role","gridcell");
      const n=Number(value)||0;
      if(n){cell.classList.add("has-tile");cell.dataset.value=String(n);
        const stage=stages.indexOf(n);if(stage>=0)cell.dataset.stage=String(stage);
        cell.textContent=String(n);
        cell.setAttribute("aria-label",String(n)+" 方块，第 "+(y+1)+" 行第 "+(x+1)+" 列");}
      else cell.setAttribute("aria-label","空格，第 "+(y+1)+" 行第 "+(x+1)+" 列");
      grid.appendChild(cell);
    }));
    root.appendChild(grid);

    const dirs=[
      ["up","↑ 上"],["left","← 左"],["down","↓ 下"],["right","→ 右"]
    ];
    const send=dir=>{if(active)gameAPI("action",{room_id:state.groom,action:{op:"move",dir:dir}})};
    const controls=document.createElement("div");controls.className="t2048-controls";
    dirs.forEach(([dir,label])=>{const b=document.createElement("button");b.type="button";
      b.className="t2048-btn";b.dataset.dir=dir;b.textContent=label;b.disabled=!active;
      b.setAttribute("aria-label","向"+label.slice(2)+"移动");b.onclick=()=>send(dir);controls.appendChild(b);});
    root.appendChild(controls);

    // touch-action:none is limited to the board, so swiping it never scrolls the page;
    // the rest of the game panel remains normally scrollable on a small screen.
    let startX=null,startY=null;
    grid.addEventListener("touchstart",e=>{
      if(!active||e.touches.length!==1)return;
      startX=e.touches[0].clientX;startY=e.touches[0].clientY;e.preventDefault();
    },{passive:false});
    grid.addEventListener("touchend",e=>{
      if(startX===null||!active)return;
      const t=e.changedTouches[0],dx=t.clientX-startX,dy=t.clientY-startY;
      startX=startY=null;e.preventDefault();
      if(Math.max(Math.abs(dx),Math.abs(dy))<24)return;
      send(Math.abs(dx)>Math.abs(dy)?(dx>0?"right":"left"):(dy>0?"down":"up"));
    },{passive:false});
    grid.addEventListener("touchcancel",()=>{startX=startY=null},{passive:true});
    box.appendChild(root);
  }
});
"""


WEB_CSS = r"""
.t2048-root{width:100%;max-width:430px;min-width:0;box-sizing:border-box;margin:0 auto;padding:8px 6px;color:#edf4f8}
.t2048-info{display:flex;align-items:center;gap:8px;min-width:0;min-height:42px;margin-bottom:8px}
.t2048-note{flex:1;font-size:13px;line-height:1.45;color:#2f4757;background:#edf4f7;
  border:1px solid #bfd1dc;border-radius:8px;padding:6px 9px}
.t2048-score{display:flex;flex-direction:column;align-items:center;justify-content:center;
  min-width:72px;padding:4px 10px;border-radius:9px;background:#1e3b52;border:1px solid #4f7591}
.t2048-score small{font-size:10px;color:#afc1d1}.t2048-score b{font-size:18px;color:#ffd166;line-height:1.1}
.t2048-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;padding:7px;
  background:#14283a;border:2px solid #456a84;border-radius:12px;touch-action:none;
  user-select:none;-webkit-user-select:none;box-sizing:border-box;min-width:0;width:100%;max-width:410px;margin:0 auto}
.t2048-cell{aspect-ratio:1;min-width:0;display:flex;align-items:center;justify-content:center;border-radius:8px;
  background:#203a50;color:#f4f7fb;font-size:clamp(17px,6vw,31px);font-weight:800;line-height:1}
.t2048-cell.has-tile{background:#f5e9d0;color:#3d3022;box-shadow:inset 0 -2px 0 rgba(0,0,0,.12)}
.t2048-cell[data-value="4"]{background:#f4d7a4}.t2048-cell[data-value="8"]{background:#f6b26b;color:#fff}
.t2048-cell[data-value="16"]{background:#f28c63;color:#fff}.t2048-cell[data-value="32"]{background:#ed705b;color:#fff}
.t2048-cell[data-value="64"]{background:#e6534e;color:#fff}.t2048-cell[data-value="128"]{background:#e9c764;color:#fff}
.t2048-cell[data-value="256"]{background:#e2bd45;color:#fff}.t2048-cell[data-value="512"]{background:#d9b635;color:#fff}
.t2048-cell[data-value="1024"]{background:#c99e32;color:#fff;font-size:clamp(14px,4.6vw,25px)}
.t2048-cell[data-value="2048"]{background:#b8862d;color:#fff;box-shadow:0 0 0 2px #ffd166,0 0 16px rgba(255,209,102,.65)}
.t2048-cell.has-tile{background-image:url("/game-art/tile2048-atlas.webp");background-size:400% 300%;
  background-repeat:no-repeat;text-shadow:0 2px 4px #061321,0 0 2px #061321}
.t2048-cell[data-stage="0"]{background-position:0% 0%}.t2048-cell[data-stage="1"]{background-position:33.3333% 0%}
.t2048-cell[data-stage="2"]{background-position:66.6667% 0%}.t2048-cell[data-stage="3"]{background-position:100% 0%}
.t2048-cell[data-stage="4"]{background-position:0% 50%}.t2048-cell[data-stage="5"]{background-position:33.3333% 50%}
.t2048-cell[data-stage="6"]{background-position:66.6667% 50%}.t2048-cell[data-stage="7"]{background-position:100% 50%}
.t2048-cell[data-stage="8"]{background-position:0% 100%}.t2048-cell[data-stage="9"]{background-position:33.3333% 100%}
.t2048-cell[data-stage="10"]{background-position:66.6667% 100%}
.t2048-controls{display:grid;grid-template-columns:repeat(3,minmax(62px,1fr));gap:7px;
  max-width:280px;margin:10px auto 2px}
.t2048-btn{min-height:42px;border:1px solid #6687a0;border-radius:8px;background:#203f57;color:#f7fbff;
  font-size:14px;font-weight:700;cursor:pointer;touch-action:manipulation}
.t2048-btn:first-child{grid-column:2}.t2048-btn:nth-child(2){grid-column:1;grid-row:2}
.t2048-btn:nth-child(3){grid-column:2;grid-row:2}.t2048-btn:nth-child(4){grid-column:3;grid-row:2}
.t2048-btn:hover:not(:disabled),.t2048-btn:focus-visible{background:#2f5c79;border-color:#ffd166;outline:2px solid #ffd166;outline-offset:1px}
.t2048-btn:disabled{opacity:.5;cursor:default}
@media (max-width:560px){.t2048-root{padding-inline:0}.t2048-grid{gap:5px;padding:5px}.t2048-controls{gap:5px;margin-top:8px}}
"""
