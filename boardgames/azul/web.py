# -*- coding: utf-8 -*-
"""Azul 网页渲染片段：由共用 web 外壳经注册表注入页面的 GRENDER。

- 自包含语句：Object.assign(GRENDER,{azul(box,s){...}});
- 版面按 spec §10：azul_table 底 / azul_plate 工厂盘 / azul_boardface 板面 /
  azul_wall_cell_* 空墙印纹 / azul_track 计分轨；动作契约 take/place/floor 不变。
- 约束：本串为 Python raw 三引号字符串，内部不得出现未转义三引号；
  拼接 HTML 属性一律用双引号属性或无引号，禁止在单引号属性里嵌单引号。
"""

WEB_JS = r"""
Object.assign(GRENDER,{
azul(box,s){
  box.appendChild(gTitle("azul","花砖物语 · 拼花"));
  const CC=s.colors||{};
  const COLORS=["r","w","b","y","k"];
  const CTS_CLS={r:"r",w:"w",b:"b",y:"y",k:"k"};
  // 墙空格应有色：引擎拉丁方 _wall_col(ci,row)=(ci+row)%5 ⇒ 格 (r,c) 应为 COLORS[(c-r)%5]
  const wallColor=(r,c)=>COLORS[(((c-r)%5)+5)%5];
  const azTile=t=>{
    const c=(t&&t.c)?t.c:t;
    const u=BG["azul_tile_"+c];
    if(u)return "<img src='"+u+"' title='"+CC[c]+"' style='width:22px;height:22px;vertical-align:middle;margin:1px' alt=''>";
    return "<span class='vtile "+(CTS_CLS[c]||"w")+"' title='"+CC[c]+"'>"+CC[c]+"</span>";};
  const rows=s.rows[state.uid]||{};
  const wall=s.wall[state.uid]||{};
  const sc=s.score||{};

  const d=document.createElement("div");
  // 底：深色桌面（azul_table）
  d.style.cssText=bgImg("azul_table")+"padding:6px;border-radius:var(--r1)";

  // 顶部信息条（沿用计分轨位图）
  d.innerHTML="<div style='"+bgImg("azul_track")+"font-size:11px;color:#e8f0f6;border-radius:var(--r1);padding:3px 8px'>第 "+s.round+" 轮 · 回合 → "
    +esc(gnick(s.turn_uid))+"　🧱 袋剩 "+s.bag+"　"+scoreHTML(sc)+"</div>";

  // 工厂盘：azul_plate 位图 + azul_tile_*
  d.innerHTML+="<div class='gsec'>工厂盘</div><div style='display:flex;flex-wrap:wrap;gap:6px;align-items:center'>"
    +((s.offers||[]).length?(s.offers||[]).map((b,i)=>b.length
      ?("<span title='碗"+(i+1)+"' style='"+bgImg("azul_plate")+"border-radius:50%;padding:12px;display:inline-flex;align-items:center;justify-content:center'>"
        +b.map(azTile).join("")+"</span>")
      :"<span style='color:#cfe0ee'>[碗"+(i+1)+"空]</span>").join(""):"<span style='color:#cfe0ee'>（空）</span>")
    +"</div>";

  // 中央池：独立成盘
  d.innerHTML+="<div class='gsec'>中央池</div>"
    +"<div style='"+bgImg("azul_plate")+"border-radius:50%;padding:12px;display:inline-flex;align-items:center;justify-content:center'>"
    +((s.center||[]).map(azTile).join("")||"<span style='color:#cfe0ee'>（空）</span>")+"</div>";

  // 玩家板：azul_boardface 板面；左 5 花纹行（第 i 行 i+1 格 + 行首容量标），右 5×5 墙
  let left="";
  for(let r=0;r<5;r++){
    const row=rows[String(r)]||[];
    let slots="";
    for(let i=0;i<r+1;i++){
      slots+=(i<row.length)
        ?"<span style='display:inline-block;margin:1px'>"+azTile(row[i])+"</span>"
        :"<span style='display:inline-block;width:22px;height:22px;margin:1px;border-radius:3px;background:rgba(0,0,0,.06);vertical-align:middle'></span>";
    }
    left+="<div style='display:flex;align-items:center;gap:4px;margin:2px 0;font-size:11px;color:#2b3a46'>"
      +"<span style='width:16px;text-align:center;color:#5a6b78'>"+(r+1)+"</span>"
      +"<span style='display:inline-flex'>"+slots+"</span></div>";
  }
  let wallHtml="";
  for(let r=0;r<5;r++){
    wallHtml+="<div style='display:flex'>";
    for(let c=0;c<5;c++){
      const v=wall[r+","+c];
      if(v){
        wallHtml+="<div title='"+CC[v]+"' style='"+bgImg("azul_tile_"+v)+"width:24px;height:24px;margin:1px;border-radius:3px'></div>";
      }else{
        const wc=wallColor(r,c);
        wallHtml+="<div style='"+bgImg("azul_wall_cell_"+wc)+"width:24px;height:24px;margin:1px;border-radius:3px'></div>";
      }
    }
    wallHtml+="</div>";
  }
  d.innerHTML+="<div class='gsec'>我的玩家板</div>"
    +"<div style='"+bgImg("azul_boardface")+"background-size:cover;display:flex;gap:12px;padding:10px;border-radius:var(--r1);box-shadow:0 2px 8px rgba(0,0,0,.35)'>"
    +"<div>"+left+"</div><div>"+wallHtml+"</div></div>";

  // 计分轨：azul_track 位图，0..30 刻度（每 5 格加重）+ 各玩家棋子（自己高亮）
  let ticks="";
  for(let i=0;i<=30;i++){
    const heavy=(i%5===0);
    ticks+="<span style='position:absolute;left:"+(i/30*100)+"%;bottom:0;width:"+(heavy?"2px":"1px")+";height:"+(heavy?"13px":"7px")+";background:"+(heavy?"#cfe0ee":"rgba(207,224,238,.55)")+";transform:translateX(-50%)'></span>";
  }
  const marks=Object.entries(sc).map(([u,v])=>{
    const p=Math.max(0,Math.min(30,+v||0))/30*100;
    const mine=(+u===state.uid);
    return "<span title='"+esc(gnick(+u))+":"+v+"' style='position:absolute;left:"+p+"%;bottom:6px;width:10px;height:10px;border-radius:50%;background:"+(mine?"#ffd977":"#8fb6ce")+";border:1px solid #101e2c;transform:translateX(-50%);z-index:2'></span>";
  }).join("");
  d.innerHTML+="<div class='gsec'>计分轨（0–30）</div>"
    +"<div style='"+bgImg("azul_track")+"position:relative;height:36px;border-radius:var(--r1)'>"+ticks+marks+"</div>";

  // 地板 / 分数行
  d.innerHTML+="<div style='font-size:11px;color:#cfe0ee;margin-top:4px'>地板："+((s.floor[state.uid]||0))+"　分："+(sc[state.uid]||0)+"</div>";
  box.appendChild(d);

  if(s.turn_uid!==state.uid){box.appendChild(gBtn("⏸ 等待他行动",null,true));return}
  const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;align-items:center";
  const S=document.createElement("select");const opt=document.createElement("option");opt.value="center";opt.textContent="中央";S.appendChild(opt);
  (s.offers||[]).forEach((b,i)=>{const o=document.createElement("option");o.value=i;o.textContent="碗"+(i+1);S.appendChild(o)});
  const C=document.createElement("select");
  Object.entries(CC).forEach(([k,v])=>{const o=document.createElement("option");o.value=k;o.textContent=v;C.appendChild(o)});
  const bt=document.createElement("button");bt.className="gbtn go";bt.textContent="🧱 取砖";
  bt.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"take",src:S.value,col:C.value}});
  bar.append(document.createTextNode("取："),S,C,bt);box.appendChild(bar);
  const bar2=document.createElement("div");bar2.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;align-items:center";
  const R=document.createElement("select");[0,1,2,3,4].forEach(r=>{const o=document.createElement("option");o.value=r;o.textContent="第"+(r+1)+"行";R.appendChild(o)});
  const bp=document.createElement("button");bp.className="gbtn";bp.textContent="🪟 落砖";
  bp.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"place",row:R.value}});
  bar2.append(document.createTextNode("落："),R,bp,gBtn("🌀 溢出地板",{op:"floor"}));box.appendChild(bar2);
},
});
"""

WEB_CSS = ""
