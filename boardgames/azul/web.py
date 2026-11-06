# -*- coding: utf-8 -*-
"""Azul 网页渲染片段：由共用 web 外壳经注册表注入页面的 GRENDER。

- 自包含语句：Object.assign(GRENDER,{azul(box,s){...}});
- 版面按 spec §8：CSS grid 五分区（信息条 / 左工厂列 / 中玩家板行 / 右计分环
  / 底部动作条），位图经 bgImg() 复用与桌面端同一批素材
  （azul_wall_bg / azul_plate(_center) / azul_board / azul_tile_* / azul_wall_cell_*
  / azul_track_ring / azul_marker_* / azul_chip）。
- 修掉「只画自己一块板」：遍历 s.players，每人一块板，自己加 .me 高亮类。
- 动作契约 take/place/floor 不变。
- 约束：本串为 Python raw 三引号字符串，内部不得出现未转义三引号；
  拼接 HTML 属性一律用双引号属性或无引号，禁止在单引号属性里嵌单引号。
"""

WEB_JS = r"""
Object.assign(GRENDER,{
azul(box,s){
  box.appendChild(gTitle("azul","花砖物语 · 拼花"));
  const CC=s.colors||{};
  const COLORS=["r","w","b","y","k"];
  const MARKERS="rwbyk";
  const CTS_CLS={r:"r",w:"w",b:"b",y:"y",k:"k"};
  // 墙空格应有色：引擎拉丁方 _wall_col(ci,row)=(ci+row)%5 ⇒ 格 (r,c) 应为 COLORS[(c-r)%5]
  const wallColor=(r,c)=>COLORS[(((c-r)%5)+5)%5];
  // 取砖热区：每片砖带 data-azsrc（工厂碗序号 / center）与 data-azcol（色键）。
  // src 为空表示只是展示（花纹行里的砖），不参与拖拽。
  const azTile=(t,src)=>{
    const c=(t&&t.c)?t.c:t;
    const ds=(src==null)?"":" data-azsrc='"+src+"'";
    const u=BG["azul_tile_"+c];
    if(u)return "<img class='aztile' data-azcol='"+c+"'"+ds+" src='"+u+"' title='"+CC[c]+"' style='width:20px;height:20px;vertical-align:middle;margin:1px' alt=''>";
    return "<span class='vtile aztile "+(CTS_CLS[c]||"w")+"' data-azcol='"+c+"'"+ds+" title='"+CC[c]+"'>"+CC[c]+"</span>";};
  const azSource=(tiles,src)=>COLORS.filter(c=>tiles.some(t=>(t.c||t)===c)).map(c=>{
    const n=tiles.filter(t=>(t.c||t)===c).length;
    return "<button type='button' class='azpick' data-azsrc='"+src+"' data-azcol='"+c
      +"' aria-label='"+(src==="center"?"中央池":"工厂 "+(+src+1))+"，"+CC[c]+"色 "+n+" 块'>"
      +azTile(c)+"<span>"+CC[c]+" ×"+n+"</span></button>";
  }).join("");
  const players=s.players||[];
  const score=s.score||{},rowsAll=s.rows||{},wallAll=s.wall||{},floorAll=s.floor||{};
  const floorTilesAll=s.floor_tiles||{};
  const marker={};players.forEach((u,i)=>{marker[String(u)]=MARKERS[i%MARKERS.length]});
  const me=state.uid;
  const nickOf=u=>gnick(u);

  // 底：深色桌面（azul_wall_bg 平铺）+ grid 容器
  const d=document.createElement("div");
  d.className="azgrid";
  d.style.cssText=bgImg("azul_wall_bg")+"background-size:160px 160px;background-repeat:repeat;"
    +"padding:6px;border-radius:var(--r1)";

  // 1) 信息条：第 N 轮 · 回合 → 谁 · 袋剩 + 各玩家分数筹码（自己高亮）
  const chips=players.map(u=>("<span class='azchip'>"
    +"<img src='"+(BG["azul_chip"]||"")+"' alt=''>"
    +"<span"+(u===me?" class='azme'":"")+">"+esc(nickOf(u))+" "+(score[String(u)]||0)+"</span></span>")).join("");
  d.innerHTML="<div class='azinfo'>第 "+s.round+" 轮 · 回合 → "+esc(nickOf(s.turn_uid))
    +"　🧱 袋剩 "+s.bag
    +(s.start_uid!=null?"　⭐先手 "+esc(nickOf(s.start_uid)):"")
    +"　"+chips+"</div>";

  // 2) 左列：工厂盘（azul_plate）+ 中央池（azul_plate_center）
  const plates=(s.offers||[]).map((b,i)=>b.length
    ?("<span class='azplate' style='"+bgImg("azul_plate")+"'>"+azSource(b,i)+"</span>")
    :"<span class='azempty'>[碗"+(i+1)+"空]</span>").join("");
  const center=azSource(s.center||[],"center");
  d.innerHTML+="<div class='azleft'><div class='gsec'>工厂盘</div>"+plates
    +"<div class='gsec'>中央池</div><span class='azplate azplate-c' style='"+bgImg("azul_plate_center")+"'>"
    +(center||"<span class='azempty'>（空）</span>")+"</span></div>";

  // 3) 中部：所有玩家板（自己大板高亮、对手缩略）
  const boards=players.map(u=>{
    const rows=rowsAll[String(u)]||{},wall=wallAll[String(u)]||{};
    const mine=(u===me);
    let left="";
    for(let r=0;r<5;r++){
      const row=rows[String(r)]||[];
      const k=Math.min(row.length,r+1);
      let slots="";
      for(let i=0;i<r+1;i++){
        const idx=i-(r+1-k);          // 右对齐：砖只出现在最右 k 格
        slots+=(idx>=0&&idx<k)
          ?"<span class='azslot'>"+azTile(row[idx])+"</span>"
          :"<span class='azslot azslot-e'></span>";
      }
      left+="<div class='azrow"+(mine?" azdrop":"")+"'"+(mine?" data-azdrop='"+r+"'":"")+">"
        +"<span class='azrowcap'>"+(r+1)+"</span><span class='azrowslots'>"+slots+"</span>"
        +(mine?"<span class='azrowhint'></span>":"")+"</div>";
    }
    let wallHtml="";
    for(let r=0;r<5;r++){
      wallHtml+="<div class='azwrow'>";
      for(let c=0;c<5;c++){
        const v=wall[r+","+c];
        wallHtml+=v
          ?"<div class='azwcell' title='"+CC[v]+"' style='"+bgImg("azul_tile_"+v)+"'></div>"
          :"<div class='azwcell' style='"+bgImg("azul_wall_cell_"+wallColor(r,c))+"'></div>";
      }
      wallHtml+="</div>";
    }
    const floorTiles=(floorTilesAll[String(u)]||[]).map(t=>azTile(t)).join("");
    const floorLine=mine
      ?"<div class='azfloor azdrop' data-azdrop='-1'>"
       +"<span>地板</span><span class='azfloors'>"+floorTiles+"</span><span class='azrowhint'></span>"
       +"<b>"+(floorAll[String(u)]||0)+"</b></div>":"";
    return "<div class='azboard"+(mine?" me":"")+"' style='"+bgImg("azul_board")+"'>"
      +"<div class='azbhead'>"+esc(nickOf(u))+"<span class='azbs'>"+(score[String(u)]||0)+"</span>"
      +(mine?"":"<span class='azbf'>地板 "+(floorAll[String(u)]||0)+"</span>")+"</div>"
      +"<div class='azbbody'><div>"+left+"</div><div>"+wallHtml+"</div></div>"+floorLine+"</div>";
  }).join("");
  d.innerHTML+="<div class='azboards'><div class='gsec'>玩家板</div>"+boards+"</div>";

  // 4) 右侧：圆形计分轨（azul_track_ring）+ 31 刻度 + 各玩家棋子 + 分数清单
  const ang=v=>-Math.PI/2+(v/30)*2*Math.PI;
  let ticks="";
  for(let i=0;i<=30;i++){
    const a=ang(i),heavy=(i%5===0),ri=30,ro=heavy?42:37;
    const x0=50+ri*Math.cos(a),y0=50+ri*Math.sin(a),x1=50+ro*Math.cos(a),y1=50+ro*Math.sin(a);
    ticks+="<line x1='"+x0+"' y1='"+y0+"' x2='"+x1+"' y2='"+y1+"' stroke='"
      +(heavy?"#cfe0ee":"#6e90ae")+"' stroke-width='"+(heavy?"1.6":"1")+"'/>";
  }
  const stops=players.map(u=>{
    const v=Math.max(0,Math.min(30,+score[String(u)]||0)),a=ang(v);
    const x=(50+36*Math.cos(a)).toFixed(1),y=(50+36*Math.sin(a)).toFixed(1);
    const mine=(u===me);
    const mk=BG["azul_marker_"+marker[String(u)]];
    return (mine?"<circle cx='"+x+"' cy='"+y+"' r='6' fill='none' stroke='#ffd977' stroke-width='1.6'/>":"")
      +(mk?"<image href='"+mk+"' x='"+(x-5.2)+"' y='"+(y-5.2)+"' width='10.4' height='10.4'/>"
         :"<circle cx='"+x+"' cy='"+y+"' r='4.5' fill='"+(mine?"#ffd977":"#8fb6ce")
         +"' stroke='#101e2c' stroke-width='1'/>");
  }).join("");
  const list=players.map(u=>"<div class='azsl"+(u===me?" me":"")+"'>"+esc(nickOf(u))
    +"　"+(score[String(u)]||0)+"</div>").join("");
  d.innerHTML+="<div class='azright'><div class='gsec'>计分轨（0–30）</div>"
    +"<div class='azringw' style='"+bgImg("azul_track_ring")+"'>"
    +"<svg viewBox='0 0 100 100' class='azring'>"+ticks+stops+"</svg></div>"
    +"<div class='azslist'>"+list+"</div></div>";

  // 5) 地板 / 分数行
  d.innerHTML+="<div class='azfoot'>地板："+(floorAll[String(me)]||0)+"　分："+(score[String(me)]||0)+"</div>";
  box.appendChild(d);

  // 6) 点颜色预选 → 点行提交；鼠标仍可从来源拖到行。
  // 预选不发 take。一次提交跨 SSE 重绘共享锁；后续 place 只发往捕获的房间/账号。
  const room=state.gst&&state.gst.room;
  const key={room:state.groom,uid:me,token:state.token,gameRound:room&&room.round,round:s.round};
  const active=s.turn_uid===me&&s.winner_uid==null&&room&&room.room_id===state.groom
    &&room.game==="azul"&&room.status==="playing"
    &&players.includes(me);
  let move=state.azulMove;
  if(!active||!move||Object.keys(key).some(k=>move[k]!==key[k])){
    move=Object.assign({pick:null,busy:false,message:""},key);state.azulMove=move;
  }
  // 恢复只认新的公开快照，不把 game_private 引起的同快照重绘当作同步完成。
  if(move.recover&&move.recoverSnapshot!==state.gst){
    move.recover=false;move.busy=false;move.message="";
  }
  const current=()=>{
    const st=state.gst,r=st&&st.room,live=st&&st.state;
    return state.azulMove===move&&state.groom===key.room&&state.uid===me&&state.token===key.token
      &&r&&r.room_id===key.room&&r.game==="azul"&&r.status==="playing"&&r.round===key.gameRound
      &&live&&live.round===key.round&&live.turn_uid===me&&live.winner_uid==null;
  };
  const canInput=()=>active&&current()&&d.isConnected&&!move.busy;
  const rowsMe=rowsAll[String(me)]||{},wallMe=wallAll[String(me)]||{};
  const rowReason=(r,col)=>{
    const row=rowsMe[String(r)]||[];
    if(row.length>=r+1)return "已满";
    if(row.length&&row[0]!==col)return "颜色不符";
    const ci=COLORS.indexOf(col);
    if(ci<0)return "颜色无效";
    return wallMe[r+","+((ci+r)%5)]!=null?"墙上已有此色":"";
  };
  const canRow=(r,col)=>!rowReason(r,col);
  const sourceCount=(src,col)=>{
    const tiles=src==="center"?(s.center||[]):((s.offers||[])[+src]||[]);
    return tiles.filter(t=>(t.c||t)===col).length;
  };
  const pending=active&&Array.isArray(s.pending)&&s.pending.length
    ?{col:s.pending[0],n:s.pending.length,pending:true}:null;
  if(pending)move.pick=null;
  if(move.pick&&sourceCount(move.pick.src,move.pick.col)!==move.pick.n)move.pick=null;
  const selected=()=>pending||move.pick;
  const tip=document.createElement("div");tip.className="aztip";
  tip.setAttribute("role","status");tip.setAttribute("aria-live","polite");
  d.querySelector(".azinfo").after(tip);
  const bar=document.createElement("div");bar.className="azactions";
  const cancel=document.createElement("button");cancel.type="button";cancel.className="gbtn";
  cancel.textContent="取消选择";
  cancel.onclick=()=>{if(canInput()&&!pending){move.pick=null;move.message="";refresh()}};
  const sync=document.createElement("button");sync.type="button";sync.className="gbtn";
  sync.textContent="刷新状态";
  const requestSync=()=>{
    if(!current()||move.syncing)return;
    move.syncing=true;move.refresh();
    gameAPI("sync",{room_id:key.room},true).catch(()=>{}).finally(()=>{
      move.syncing=false;if(current())move.refresh();
    });
  };
  sync.onclick=requestSync;bar.append(cancel,sync);tip.after(bar);
  const refresh=()=>{
    const pick=selected(),enabled=canInput();
    tip.textContent=move.message||(move.busy?"正在提交这一手…":!active?"等待其他玩家行动"
      :pick?(pick.pending?"已取":(pick.src==="center"?"中央池":"工厂 "+(+pick.src+1))+"：取")
        +CC[pick.col]+"色 "+pick.n+" 块。点自己的花纹行或地板完成这一手。"
        +(!pick.pending&&pick.src==="center"&&s.marker_uid==null?"另拿先手标记，占地板 1 格。":"")
      :"先点工厂盘或中央池的一种颜色，再点自己的花纹行或地板。也可用鼠标拖动。");
    cancel.hidden=!move.pick||!!pending;cancel.disabled=!enabled;
    sync.hidden=!move.recover;sync.disabled=!!move.syncing;
    d.querySelectorAll("[data-azsrc]").forEach(t=>{
      const chosen=!!pick&&!pick.pending&&t.dataset.azsrc===pick.src&&t.dataset.azcol===pick.col;
      t.classList.toggle("azchosen",chosen);t.setAttribute("aria-pressed",String(chosen));
      t.disabled=!enabled||!!pending;
    });
    d.querySelectorAll("[data-azdrop]").forEach(z=>{
      const r=+z.dataset.azdrop,reason=pick&&r>=0?rowReason(r,pick.col):"";
      const ok=!!pick&&!reason;
      z.classList.toggle("azok",ok&&enabled);z.classList.toggle("azbad",!!pick&&!!reason);
      z.setAttribute("role","button");z.tabIndex=ok&&enabled?0:-1;
      z.setAttribute("aria-disabled",String(!ok||!enabled));
      const fill=pick&&r>=0?Math.min(pick.n,Math.max(0,r+1-(rowsMe[String(r)]||[]).length)):0;
      const hint=!pick?"":reason?reason:r<0?"全部 "+pick.n+" 块到地板"
        :"入行 "+fill+" · 溢出 "+(pick.n-fill);
      z.querySelector(".azrowhint").textContent=hint;
      z.setAttribute("aria-label",(r<0?"地板":"第 "+(r+1)+" 行")+(hint?"，"+hint:"，先选颜色"));
    });
  };
  move.refresh=refresh;
  const recover=()=>{
    if(!current())return;
    move.busy=true;move.pick=null;move.recover=true;move.recoverSnapshot=state.gst;
    move.message="这手尚未确认，正在刷新；已取的砖可继续落位。";
    move.refresh();requestSync();
  };
  const submit=async r=>{
    const pick=selected();
    if(!canInput()||!pick||(r>=0&&!canRow(r,pick.col)))return;
    move.busy=true;move.message="";move.refresh();
    try{
      if(!pick.pending){
        const x=await gameAPI("action",{room_id:key.room,action:{op:"take",src:pick.src,col:pick.col}});
        if(!current())return;
        if(!x||!x.ok){recover();return}
      }
      if(!current())return;
      const live=state.gst.state,held=live.pending;
      if(held&&held.length&&(held.length!==pick.n||held.some(c=>c!==pick.col))){recover();return}
      // 正常 take 的 SSE 可能已重绘，也可能还没到；HTTP 成功后只续发一次。
      const x=await gameAPI("action",{room_id:key.room,
        action:r<0?{op:"floor"}:{op:"place",row:r}});
      if(current()&&(!x||!x.ok))recover();
    }catch(_e){recover()}
  };
  d.addEventListener("click",e=>{
    if(suppressClick){suppressClick=false;return}
    if(!canInput())return;
    const t=e.target.closest("[data-azsrc]");
    if(t&&!pending){
      const src=t.dataset.azsrc,col=t.dataset.azcol;
      move.pick=move.pick&&move.pick.src===src&&move.pick.col===col?null:{src,col,n:sourceCount(src,col)};
      move.message="";refresh();return;
    }
    const z=e.target.closest("[data-azdrop]");if(z)submit(+z.dataset.azdrop);
  });
  d.addEventListener("keydown",e=>{
    const z=e.target.closest("[data-azdrop]");
    if(z&&(e.key==="Enter"||e.key===" ")){e.preventDefault();submit(+z.dataset.azdrop)}
    if(e.key==="Escape")cancel.click();
  });
  const colCss={r:"#D2534F",w:"#F0F0F0",b:"#4A7DE0",y:"#E0B33C",k:"#3A3A3A"};
  const ghost=document.createElement("div");ghost.className="azghost";d.appendChild(ghost);
  let drag=null,suppressClick=false;
  const endDrag=()=>{
    drag=null;ghost.style.display="none";
    d.querySelectorAll(".azsel").forEach(z=>z.classList.remove("azsel"));
  };
  d.addEventListener("pointerdown",e=>{
    const t=e.target.closest("[data-azsrc]");
    if(e.pointerType!=="mouse"||e.button!==0||!t||!canInput()||pending)return;
    drag={src:t.dataset.azsrc,col:t.dataset.azcol,x:e.clientX,y:e.clientY,moved:false};
  });
  d.addEventListener("pointermove",e=>{
    if(!drag||!canInput())return;
    if(!drag.moved&&Math.hypot(e.clientX-drag.x,e.clientY-drag.y)<7)return;
    e.preventDefault();drag.moved=true;
    move.pick={src:drag.src,col:drag.col,n:sourceCount(drag.src,drag.col)};refresh();
    ghost.style.background=colCss[drag.col];ghost.style.display="block";
    ghost.style.left=(e.clientX-13)+"px";ghost.style.top=(e.clientY-13)+"px";
    try{d.setPointerCapture(e.pointerId)}catch(_e){}
    const el=document.elementFromPoint(e.clientX,e.clientY),z=el&&el.closest("[data-azdrop]");
    d.querySelectorAll(".azsel").forEach(x=>x.classList.remove("azsel"));
    if(z&&d.contains(z)&&z.classList.contains("azok"))z.classList.add("azsel");
  });
  d.addEventListener("pointerup",e=>{
    if(!drag)return;
    const moved=drag.moved;endDrag();if(!moved)return;
    suppressClick=true;setTimeout(()=>{suppressClick=false},0);
    const el=document.elementFromPoint(e.clientX,e.clientY),z=el&&el.closest("[data-azdrop]");
    if(z&&d.contains(z))submit(+z.dataset.azdrop);
  });
  d.addEventListener("pointercancel",endDrag);
  refresh();

},
});
"""

WEB_CSS = r"""
.azgrid{display:grid;grid-template-columns:minmax(110px,1fr) minmax(0,2.6fr) minmax(140px,1fr);
  grid-template-areas:"info info info" "tip tip tip" "actions actions actions" "left boards right";gap:8px;align-items:start}
.azinfo{grid-area:info;font-size:11px;color:#e8f0f6;border-radius:var(--r1);padding:4px 8px}
.azleft{grid-area:left}
.azboards{grid-area:boards;display:flex;flex-wrap:wrap;gap:8px;align-items:flex-start}
.azright{grid-area:right}
.azfoot{grid-column:1/-1;font-size:11px;color:#cfe0ee;margin-top:4px}
.azchip{display:inline-flex;align-items:center;gap:3px;margin:0 4px}
.azchip img{width:14px;height:14px}
.azchip .azme,.azsl.me{color:#ffd977;font-weight:700}
.azplate{display:inline-flex;align-items:center;justify-content:center;border-radius:50%;
  flex-wrap:wrap;gap:4px;padding:8px;margin:3px;min-width:36px;min-height:36px;max-width:100%;box-sizing:border-box}
.azplate-c{display:flex;border-radius:12px}
.azpick{display:inline-flex;align-items:center;justify-content:center;gap:3px;min-width:56px;min-height:44px;
  padding:4px;color:#172b3b;background:#edf3f7;border:1px solid #7291aa;border-radius:6px;
  font-size:12px;cursor:grab;touch-action:manipulation;user-select:none}
.azpick:disabled{cursor:default;opacity:.6}
.azpick.azchosen{outline:3px solid #ffd977;background:#fff1ba}
.azpick img{pointer-events:none;-webkit-user-drag:none}
.azempty{color:#cfe0ee;font-size:11px}
.azboard{flex:1 1 250px;max-width:560px;border-radius:var(--r1);padding:6px 8px;
  min-width:0;box-sizing:border-box;display:flex;flex-direction:column;gap:4px;box-shadow:0 2px 6px rgba(0,0,0,.35)}
.azboard.me{box-shadow:0 0 0 2px #E0B33C,0 2px 8px rgba(0,0,0,.45)}
.azbhead{font-size:11px;color:#2b3a46;font-weight:700;display:flex;gap:8px}
.azbs{color:#8a6d1f}
.azbf{color:#7a5a4a;font-weight:400}
.azbbody{display:flex;gap:10px;justify-content:space-between}
.azrow{display:flex;align-items:center;gap:4px;margin:1px 0}
.azboard.me .azrow{display:grid;grid-template-columns:14px 110px;gap:0 4px;min-height:48px;box-sizing:border-box}
.azboard.me .azwrow{height:49px;align-items:center}
.azrowhint{font-size:11px;line-height:16px;color:#253e4c}
.azrow .azrowhint{grid-column:1/-1;text-align:right}
.azrowcap{width:14px;text-align:center;color:#5a6b78;font-size:10px}
.azrowslots{display:inline-flex;width:110px;justify-content:flex-end}
.azslot{display:inline-block;width:20px;height:20px;margin:1px;vertical-align:middle}
.azslot-e{background:rgba(0,0,0,.06);border-radius:3px}
.azwrow{display:flex}
.azwcell{width:22px;height:22px;margin:1px;border-radius:3px}
.azringw{position:relative;width:150px;height:150px;margin:2px auto;border-radius:50%}
.azring{position:absolute;inset:0;width:100%;height:100%}
.azslist{font-size:11px;color:#e8f0f6;margin-top:4px}
.azsl{padding:1px 2px}
/* 拖拽取砖：可抓砖 + 可落行/地板高亮 + 跟随指针的幽灵砖 */
.aztile{vertical-align:middle}
.azdrop{border-radius:4px;outline:1px dashed transparent;outline-offset:1px;
  transition:outline-color .1s,background .1s;touch-action:manipulation;cursor:pointer}
.azdrop[aria-disabled=true]{cursor:default}
.azdrop:focus-visible,.azpick:focus-visible{outline:3px solid #ffd977}
.azdrop.azok{outline-color:#7fe0a8;background:rgba(127,224,168,.14)}
.azdrop.azbad{opacity:.55}
.azdrop.azsel{outline-style:solid;outline-color:#FFD977;background:rgba(255,217,119,.22)}
.azfloor{display:flex;align-items:center;gap:8px;margin-top:5px;padding:3px 8px;
  min-height:44px;flex-wrap:wrap;box-sizing:border-box;border-radius:4px;background:rgba(0,0,0,.10);font-size:11px;color:#5a6b78}
.azfloor b{color:#8a6d1f}
.azfloors{display:inline-flex;align-items:center;gap:1px}
.azghost{position:fixed;width:26px;height:26px;border-radius:50%;pointer-events:none;
  border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.45);z-index:99;display:none}
.aztip{grid-area:tip;font-size:13px;line-height:1.6;color:#f3f7fa;background:#1c3349;
  padding:8px;border-radius:6px;min-height:58px;box-sizing:border-box}
.azactions{grid-area:actions;display:flex;gap:8px;flex-wrap:wrap;min-height:44px}
.azactions button{min-height:44px}
.azactions button[hidden]{display:none}
@media (max-width:820px){.azgrid{grid-template-columns:1fr;
  grid-template-areas:"info" "tip" "actions" "left" "boards" "right"}
  .aztip{min-height:100px}.azboards{min-width:0}.azboard.me{order:-1}.azboards>.gsec{order:-2;flex-basis:100%}}
"""
