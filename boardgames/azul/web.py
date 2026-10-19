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
    ?("<span class='azplate' style='"+bgImg("azul_plate")+"'>"+b.map(t=>azTile(t,i)).join("")+"</span>")
    :"<span class='azempty'>[碗"+(i+1)+"空]</span>").join("");
  const center=(s.center||[]).map(t=>azTile(t,"center")).join("");
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
        +"<span class='azrowcap'>"+(r+1)+"</span><span class='azrowslots'>"+slots+"</span></div>";
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
    const floorTiles=(floorTilesAll[String(u)]||[]).map(azTile).join("");
    const floorLine=mine
      ?"<div class='azfloor azdrop' data-azdrop='-1' title='拖到这里＝全部溢出地板'>"
       +"<span>地板（拖到这里溢出）</span><span class='azfloors'>"+floorTiles+"</span>"
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

  // 6) 拖拽取砖（契约不变：take 先、place/floor 再）
  //    从工厂盘 / 中央池抓起一片砖，拖到自己的花纹行或地板线松手即出牌。
  //    落点先按引擎同一规则本地预检，非法落点整手取消，不发动作。
  const rowsMe=rowsAll[String(me)]||{},wallMe=wallAll[String(me)]||{};
  const canRow=(r,col)=>{
    const row=rowsMe[String(r)]||[];
    if(row.length&&row[0]!==col)return false;
    const ci=COLORS.indexOf(col);
    if(ci<0)return false;
    const v=wallMe[r+","+((ci+r)%5)];
    return v==null||v==="";
  };
  const canDrag=()=>s.turn_uid===me&&s.winner_uid==null;
  const colCss={r:"#D2534F",w:"#F0F0F0",b:"#4A7DE0",y:"#E0B33C",k:"#3A3A3A"};
  const ghost=document.createElement("div");
  ghost.className="azghost";ghost.style.display="none";
  d.appendChild(ghost);
  let drag=null;
  const clearMark=()=>{d.querySelectorAll(".azok,.azbad,.azsel").forEach(x=>
    x.classList.remove("azok","azbad","azsel"))};
  const endDrag=()=>{drag=null;ghost.style.display="none";clearMark()};
  d.addEventListener("pointerdown",e=>{
    const t=e.target.closest?e.target.closest("[data-azsrc]"):null;
    if(!t||!canDrag())return;
    e.preventDefault();
    drag={src:t.getAttribute("data-azsrc"),col:t.getAttribute("data-azcol")};
    d.querySelectorAll("[data-azdrop]").forEach(z=>{
      const r=+z.getAttribute("data-azdrop");
      z.classList.add((r<0||canRow(r,drag.col))?"azok":"azbad");
    });
    ghost.style.background=colCss[drag.col]||"#888";
    ghost.style.display="block";
    ghost.style.left=(e.clientX-13)+"px";ghost.style.top=(e.clientY-13)+"px";
    try{d.setPointerCapture(e.pointerId)}catch(_e){}
  });
  d.addEventListener("pointermove",e=>{
    if(!drag)return;
    ghost.style.left=(e.clientX-13)+"px";ghost.style.top=(e.clientY-13)+"px";
    const el=document.elementFromPoint(e.clientX,e.clientY);
    const z=el&&el.closest?el.closest("[data-azdrop]"):null;
    d.querySelectorAll(".azsel").forEach(x=>x.classList.remove("azsel"));
    if(z&&z.classList.contains("azok"))z.classList.add("azsel");
  });
  const drop=e=>{
    if(!drag)return;
    const dd=drag;drag=null;
    ghost.style.display="none";
    const el=document.elementFromPoint(e.clientX,e.clientY);
    const z=el&&el.closest?el.closest("[data-azdrop]"):null;
    const r=z?+z.getAttribute("data-azdrop"):null;
    const ok=(r!==null)&&(r<0||canRow(r,dd.col));
    clearMark();
    if(!ok)return;
    gameAPI("action",{room_id:state.groom,action:{op:"take",src:dd.src,col:dd.col}})
      .then(x=>{if(x&&x.ok)gameAPI("action",{room_id:state.groom,
        action:(r<0?{op:"floor"}:{op:"place",row:r})});});
  };
  d.addEventListener("pointerup",drop);
  d.addEventListener("pointercancel",endDrag);
  if(s.turn_uid!==me){box.appendChild(gBtn("⏸ 等待他行动",null,true));return}
  const tip=document.createElement("div");
  tip.className="aztip";
  tip.textContent="拖动：从工厂盘 / 中央池抓起花砖，拖到自己的花纹行或地板线松手";
  box.appendChild(tip);
  const bar=document.createElement("div");
  bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:4px";
  bar.appendChild(gBtn("🌀 溢出地板",{op:"floor"}));
  box.appendChild(bar);
},
});
"""

WEB_CSS = r"""
.azgrid{display:grid;grid-template-columns:minmax(110px,1fr) minmax(0,2.6fr) minmax(140px,1fr);
  grid-template-areas:"info info info" "left boards right";gap:8px;align-items:start}
.azinfo{grid-area:info;font-size:11px;color:#e8f0f6;border-radius:var(--r1);padding:4px 8px}
.azleft{grid-area:left}
.azboards{grid-area:boards;display:flex;flex-wrap:wrap;gap:8px;align-items:flex-start}
.azright{grid-area:right}
.azfoot{grid-column:1/-1;font-size:11px;color:#cfe0ee;margin-top:4px}
.azchip{display:inline-flex;align-items:center;gap:3px;margin:0 4px}
.azchip img{width:14px;height:14px}
.azchip .azme,.azsl.me{color:#ffd977;font-weight:700}
.azplate{display:inline-flex;align-items:center;justify-content:center;border-radius:50%;
  padding:10px;margin:3px;min-width:36px;min-height:36px}
.azplate-c{display:flex}
.azempty{color:#cfe0ee;font-size:11px}
.azboard{flex:1 1 250px;max-width:560px;border-radius:var(--r1);padding:6px 8px;
  display:flex;flex-direction:column;gap:4px;box-shadow:0 2px 6px rgba(0,0,0,.35)}
.azboard.me{box-shadow:0 0 0 2px #E0B33C,0 2px 8px rgba(0,0,0,.45)}
.azbhead{font-size:11px;color:#2b3a46;font-weight:700;display:flex;gap:8px}
.azbs{color:#8a6d1f}
.azbf{color:#7a5a4a;font-weight:400}
.azbbody{display:flex;gap:10px}
.azrow{display:flex;align-items:center;gap:4px;margin:1px 0}
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
.aztile{cursor:grab;touch-action:none}
.azdrop{border-radius:4px;outline:1px dashed transparent;outline-offset:1px;
  transition:outline-color .1s,background .1s}
.azdrop.azok{outline-color:#7fe0a8;background:rgba(127,224,168,.14)}
.azdrop.azbad{opacity:.55}
.azdrop.azsel{outline-style:solid;outline-color:#FFD977;background:rgba(255,217,119,.22)}
.azfloor{display:flex;align-items:center;gap:8px;margin-top:5px;padding:3px 8px;
  border-radius:4px;background:rgba(0,0,0,.10);font-size:11px;color:#5a6b78}
.azfloor b{color:#8a6d1f}
.azfloors{display:inline-flex;align-items:center;gap:1px}
.azghost{position:fixed;width:26px;height:26px;border-radius:50%;pointer-events:none;
  border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.45);z-index:99;display:none}
.aztip{font-size:11px;color:var(--dim);margin-top:6px}
@media (max-width:820px){.azgrid{grid-template-columns:1fr;
  grid-template-areas:"info" "left" "boards" "right"}}
"""
