# 桌游展示层 BGA 精致度 · 第二批（网页版面重排 + 收尾）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Azul 网页端版面重排为与桌面端同构的 BGA 结构（修掉「只画自己一块板」），删掉第一批的 3 个沿用键，并完成全量回归与双 EXE 打包收尾。

**Architecture:** 网页渲染器 `boardgames/azul/web.py` 的 `azul(box,s)` 从「纵向信息条 + 自己一块板」改为 CSS grid 五分区（信息条 / 左工厂列 / 中玩家板行 / 右计分环 / 底部动作条），逐一轮询 `s.players` 画所有玩家板（自己加高亮类）；位图经 `bgImg()` 复用与桌面端同一批素材。随后删除 `azul_table` / `azul_boardface` / `azul_track` 三键与 `make_legacy_*`，同步 `web.py._BG_ASSET_KEYS` 与两端断言。

**Tech Stack:** Python 3（pyenv）/ Pillow（素材，第一批已完成）/ `web.py` 单文件内联模板里的原生 JS / pytest（逐文件独立进程）/ node（语法门禁）。

**Spec:** `docs/superpowers/specs/2026-10-14-boardgame-bga-fidelity-artkit-design.md` —— **权威**。本计划实现 §8 网页版面与 §9 注明的「第二批」；§10 测试策略给出门禁；§11 给出风险。

**前置（第一批，已在工作区、未提交）：** `boardgames/artkit.py`、`boardgames/geom.py`、`boardgames/shell.py`（新组件）、`boardgames/azul/sprites.py`（25 键）、`boardgames/azul/desktop.py`（BGA 桌面版面）、开发期样张 `.trae/tmp/azul_desktop_preview.png`。

## Global Constraints

（源自 spec §3，逐字；每个任务的要求都隐含包含本节。）

- 全部素材 **Pillow 程序化原创**；仅对标 BGA 的**风格方向**，不复制素材/坐标/色彩采样。
- **不改** `ui_design.design_tokens()` golden digest：`a137658af6f3f9899c2106a0e6020c1b1e6d2569bab462488bb7c42dc0eb4078`。
- **不删** `_GAME_ICON` 既有键；**不破坏** `icon_svg` 字节兼容；**不改**主聊天窗皮肤与其网页 CSS/token。
- 假画布桩下**绝不调用** `ImageTk.PhotoImage(master=cv)`。
- 网页注入后整页 JS 必须语法合法；azul 动作契约 `take/place/floor` 不变。
- 未迁移的 46 款行为与外观**零变化**。
- verify 目标为「**无新增 FAIL**」（本机 Tk 缺 tcl 属环境）。
- **未经用户明确要求不 commit / push。**
- `WEB_JS` 是 Python raw 三引号字符串：内部**不得出现未转义三引号**；拼 HTML 属性一律用双引号属性或无引号，**禁止在单引号属性里嵌单引号**（`bgImg()` 片段本身不含单引号，可安全拼进单引号 `style`）。
- 门禁：`node tests/ux_visual_chat_probe.cjs` 必须输出 `full_script_syntax:true`。
- 本机 pytest **必须逐文件独立进程**（单进程批量跑会在重 Tk 用例上原生崩溃 `0x80000003`）。
- 本机 PowerShell 5：不能用 `&&`；多行 `python -c` 会被破坏（改用临时 `.py` 文件）。
- **不得触碰**兄弟 worktree `…/learn_demos/_wt_boardgame_azul`（分支 `feat/boardgame-packages-azul`）。

---

## 文件结构

| 文件 | 本批动作 | 责任 |
|---|---|---|
| `boardgames/azul/web.py` | 重写 `WEB_JS`、新增 `WEB_CSS` | 网页渲染片段（BGA grid 版面） |
| `web.py`（仓库根） | 改 `_BG_ASSET_KEYS` | 服务端只把需要的键注入 `BG` |
| `boardgames/azul/sprites.py` | 删 3 个 `make_legacy_*` + 3 键 | 素材生成器（25 → 22 键） |
| `boardgames/azul/assets/*.png`、`boardgames/azul/_art.py` | 重生成 | 内嵌素材产物 |
| `tests/test_web_boardgame_assets.py` | 扩展 + 改键名 | 网页端键集/结构标记/契约断言 |
| `tests/test_azul_package_assets.py` | 改键集与计数 | 素材键集/尺寸断言 |
| `tests/test_boardgame_asset_img.py` | 微调 | 桌面渲染缓存键断言 |
| `_azul_web_preview.py`（仓库根） | 新建 | 开发期网页样张（不入库） |

---

## Task 1: Azul 网页版面重排为 BGA 结构（含修「只画一块板」）

**Files:**
- Modify: `boardgames/azul/web.py`（整文件重写 `WEB_JS`；`WEB_CSS` 从 `""` 改为 grid 样式表）
- Modify: `web.py:56-62`（`_BG_ASSET_KEYS` 增补新键，暂**保留** 3 个沿用键）
- Modify: `tests/test_web_boardgame_assets.py`（更新键名断言 + 追加结构断言）

**Interfaces:**
- Consumes（页面已提供，勿重定义）：`bgImg(key,extra)`（`web.py:3930`，返回 `background:url(<无引号 data-URI>) center/100% 100% no-repeat;border:none;` + `extra`）、`GRENDER`、`state`、`state.uid`、`state.groom`、`gTitle(g,label)`、`gBtn(label,action,disabled)`、`esc(s)`、`gnick(uid)`、`scoreHTML(obj)`、`gameAPI(path,body)`、CSS 变量 `--r1`、既有类 `.gsec`。
- Consumes（azul 快照，见 `games_pkg/azul.py:218-233`）：`s.players`（list[int] 座位序）、`s.colors`（色键→中文）、`s.round`、`s.turn_uid`、`s.bag`、`s.offers`（list[list[{c,n}]]）、`s.center`（list[{c,n}]）、`s.rows`（`{str(uid):{str(row):[色键,…]}}`）、`s.wall`（`{str(uid):{"r,c":色键|None}}`）、`s.floor`（`{str(uid):int}`）、`s.score`（`{str(uid):int}`）。
- Produces: `WEB_JS`（**单条自包含语句**，`Object.assign(GRENDER,{azul(box,s){…}});`）、`WEB_CSS`（`azgrid/azboard` 等 `az` 前缀 grid 类）。
- 桌面端同源对照：`boardgames/azul/desktop.py`（`_wall_target(r,c)=COLORS[(c-r)%5]`、`_marker_map(players)` 按座位序轮转 `"rwbyk"`）。**两端要保持一致**。

- [ ] **Step 1: 追加失败测试** 到 `tests/test_web_boardgame_assets.py` 文件末尾

```python
def test_azul_web_layout_renders_all_players_and_grid():
    """BGA 重排：遍历所有玩家板 + grid 结构 + 动作契约不变。"""
    from boardgames.azul import web as azweb
    js = azweb.WEB_JS
    assert "s.players" in js                      # 修「只画一块板」：逐人一块板
    for mark in ("azul_wall_bg", "azul_board", "azul_track_ring", "azul_chip",
                 "azul_marker_", "azul_plate_center", "azgrid", "azboards"):
        assert mark in js, mark
    assert 'op:"take"' in js and 'op:"place"' in js and 'op:"floor"' in js
    assert js.strip().startswith("Object.assign(GRENDER,{")
    assert js.strip().endswith(");")
    css = azweb.WEB_CSS
    assert "grid-template-areas" in css
    assert "azgrid" in css and ".azboard" in css


def test_azul_web_js_compiles_in_node(tmp_path):
    """注入串必须语法合法（node --check）。"""
    import shutil, subprocess
    if shutil.which("node") is None:
        import pytest; pytest.skip("node unavailable")
    from boardgames.azul import web as azweb
    p = tmp_path / "az_js.js"
    p.write_text(azweb.WEB_JS, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
```

并把 `tests/test_web_boardgame_assets.py` 里引用旧键的 3 处断言改名为新键（下方 Step 2 给出确切行）。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_web_boardgame_assets.py -q`
Expected: FAIL —— `test_azul_web_layout_renders_all_players_and_grid` 断言 `"s.players" in js` 失败（旧 `WEB_JS` 只用 `state.uid`）；`test_azul_web_js_compiles_in_node` 通过（旧串本就合法）。

同一次编辑里改这 3 处（否则本步之后的既有用例会红）：
1. `tests/test_web_boardgame_assets.py:13` 的键元组：把 `"azul_table"`→`"azul_wall_bg"`、`"azul_boardface"`→`"azul_board"`、`"azul_track"`→`"azul_track_ring"`，并追加 `"azul_chip", "azul_marker_r", "azul_plate_center"`。
2. `tests/test_web_boardgame_assets.py:40-41` 的 `mark` 元组：`'bgImg("azul_table")'`→`'bgImg("azul_wall_bg")'`、`'bgImg("azul_boardface")'`→`'bgImg("azul_board")'`、`'bgImg("azul_track")'`→`'bgImg("azul_track_ring")'`。
3. `tests/test_web_boardgame_assets.py:70` 的 `for k in ("azul_table","azul_boardface","azul_plate","azul_track")` → `("azul_wall_bg","azul_board","azul_plate","azul_track_ring")`。

- [ ] **Step 3: 实施**

(a) `web.py:56-62`：`_BG_ASSET_KEYS` **增补**（保留 3 个沿用键，Task 2 再删）：
把 `"azul_wall_bg", "azul_board", "azul_plate_center", "azul_track_ring", "azul_chip",` 与 `"azul_marker_r", "azul_marker_w", "azul_marker_b", "azul_marker_y", "azul_marker_k",` 插入元组（`azul_plate`/`azul_tile_*`/`azul_wall_cell_*`/`azul_floor` 已在其中）。

(b) `boardgames/azul/web.py`：整文件替换为下列内容（`WEB_JS` 单条自包含语句 + `WEB_CSS`）。

```python
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
  const azTile=t=>{
    const c=(t&&t.c)?t.c:t;
    const u=BG["azul_tile_"+c];
    if(u)return "<img src='"+u+"' title='"+CC[c]+"' style='width:20px;height:20px;vertical-align:middle;margin:1px' alt=''>";
    return "<span class='vtile "+(CTS_CLS[c]||"w")+"' title='"+CC[c]+"'>"+CC[c]+"</span>";};
  const players=s.players||[];
  const score=s.score||{},rowsAll=s.rows||{},wallAll=s.wall||{},floorAll=s.floor||{};
  const marker={};players.forEach((u,i)=>{marker[String(u)]=MARKERS[i%MARKERS.length]});
  const me=state.uid;
  const nickOf=u=>gnick(u);

  // 底：深色桌面（azul_wall_bg 平铺）+ grid 容器
  const d=document.createElement("div");
  d.className="azgrid";
  d.style.cssText=bgImg("azul_wall_bg","background-size:160px 160px;background-repeat:repeat;")
    +"padding:6px;border-radius:var(--r1)";

  // 1) 信息条：第 N 轮 · 回合 → 谁 · 袋剩 + 各玩家分数筹码（自己高亮）
  const chips=players.map(u=>("<span class='azchip'>"
    +"<img src='"+(BG["azul_chip"]||"")+"' alt=''>"
    +"<span"+(u===me?" class='azme'":"")+">"+esc(nickOf(u))+" "+(score[String(u)]||0)+"</span></span>")).join("");
  d.innerHTML="<div class='azinfo'>第 "+s.round+" 轮 · 回合 → "+esc(nickOf(s.turn_uid))
    +"　🧱 袋剩 "+s.bag+"　"+chips+"</div>";

  // 2) 左列：工厂盘（azul_plate）+ 中央池（azul_plate_center）
  const plates=(s.offers||[]).map((b,i)=>b.length
    ?("<span class='azplate' style='"+bgImg("azul_plate")+"'>"+b.map(azTile).join("")+"</span>")
    :"<span class='azempty'>[碗"+(i+1)+"空]</span>").join("");
  const center=(s.center||[]).map(azTile).join("");
  d.innerHTML+="<div class='azleft'><div class='gsec'>工厂盘</div>"+plates
    +"<div class='gsec'>中央池</div><span class='azplate azplate-c' style='"+bgImg("azul_plate_center")+"'>"
    +(center||"<span class='azempty'>（空）</span>")+"</span></div>";

  // 3) 中部：所有玩家板（自己大板高亮、对手缩略）
  const boards=players.map(u=>{
    const rows=rowsAll[String(u)]||{},wall=wallAll[String(u)]||{};
    let left="";
    for(let r=0;r<5;r++){
      const row=rows[String(r)]||[];
      let slots="";
      for(let i=0;i<r+1;i++){
        slots+=(i<row.length)
          ?"<span class='azslot'>"+azTile(row[i])+"</span>"
          :"<span class='azslot azslot-e'></span>";
      }
      left+="<div class='azrow'><span class='azrowcap'>"+(r+1)+"</span><span class='azrowslots'>"+slots+"</span></div>";
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
    const mine=(u===me);
    return "<div class='azboard"+(mine?" me":"")+"' style='"+bgImg("azul_board")+"'>"
      +"<div class='azbhead'>"+esc(nickOf(u))+"<span class='azbs'>"+(score[String(u)]||0)+"</span>"
      +"<span class='azbf'>地板 "+(floorAll[String(u)]||0)+"</span></div>"
      +"<div class='azbbody'><div>"+left+"</div><div>"+wallHtml+"</div></div></div>";
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

  // 6) 动作条（契约不变：take / place / floor）
  if(s.turn_uid!==me){box.appendChild(gBtn("⏸ 等待他行动",null,true));return}
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
.azrowslots{display:inline-flex}
.azslot{display:inline-block;width:20px;height:20px;margin:1px;vertical-align:middle}
.azslot-e{background:rgba(0,0,0,.06);border-radius:3px}
.azwrow{display:flex}
.azwcell{width:22px;height:22px;margin:1px;border-radius:3px}
.azringw{position:relative;width:150px;height:150px;margin:2px auto;border-radius:50%}
.azring{position:absolute;inset:0;width:100%;height:100%}
.azslist{font-size:11px;color:#e8f0f6;margin-top:4px}
.azsl{padding:1px 2px}
@media (max-width:820px){.azgrid{grid-template-columns:1fr;
  grid-template-areas:"info" "left" "boards" "right"}}
"""
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_web_boardgame_assets.py -q`
Expected: PASS（全部用例，含新增 2 个）。

- [ ] **Step 5: 语法门禁**

Run: `node tests/ux_visual_chat_probe.cjs`
Expected: 输出 JSON 含 `"full_script_syntax":true`。

- [ ] **Step 6: 定向回归（逐文件独立进程）**

```powershell
python -m pytest tests/test_web_boardgame_assets.py -q
python -m pytest tests/test_azul_package_assets.py -q
python -m pytest tests/test_boardgame_asset_img.py -q
python -m pytest tests/test_game_shell_pal.py -q
python -m pytest tests/test_game_shell_wiring.py -q
```
Expected: 全部 PASS（无新增 FAIL）。

- [ ] **Step 7: 收尾（不提交）**

改动留在工作区待评审；**不要** `git add/commit/push`。

---

## Task 2: 删除 3 个沿用键 + `make_legacy_*`，同步键集与两端断言

**Files:**
- Modify: `boardgames/azul/sprites.py`（删 `make_legacy_table` / `make_legacy_boardface` / `make_legacy_track` 与其 3 个 `_build_images` 条目）
- Modify: `web.py:56-62`（`_BG_ASSET_KEYS` 删 `azul_table` / `azul_boardface` / `azul_track`）
- Regenerate: `boardgames/azul/assets/*.png`、`boardgames/azul/_art.py`（`python -m boardgames.azul.sprites`）
- Modify: `tests/test_azul_package_assets.py`（键集 25→22）
- Modify: `tests/test_web_boardgame_assets.py`（追加「旧键已消失」断言）
- Verify（不改）：`tests/test_boardgame_asset_img.py:255-256`

**Interfaces:**
- Consumes：Task 1 已让网页渲染器只引用新键；本任务把旧键的**生成**与**服务**一并移除。
- Produces：`boardgames/azul/_art.py` 的 `ASSETS` 只剩 22 键（键序 `sorted()`）；`boardgames.azul.sprites` 不再导出 `make_legacy_*`。

- [ ] **Step 1: 追加失败测试**

`tests/test_azul_package_assets.py`：
1. 删掉 `_EXPECTED_WH` 第 17 行（`"azul_table": (128, 128), "azul_boardface": (256, 256), "azul_track": (96, 48),`）。
2. 把 `test_azul_assets_expose_exactly_expected_keys` 的 `assert len(_art.ASSETS) == 25` 改为 `== 22`。
3. 把 `test_azul_legacy_web_keys_survive_this_batch`（第 29-33 行）整段替换为：

```python
def test_azul_legacy_web_keys_are_gone():
    """第二批：网页端已改用新键，旧键与其生成函数一并删除。"""
    from boardgames.azul import sprites as sp
    for k in ("azul_table", "azul_boardface", "azul_track"):
        assert k not in _art.ASSETS, k
        assert not hasattr(sp, "make_legacy_" + {"azul_table": "table",
                                                  "azul_boardface": "boardface",
                                                  "azul_track": "track"}[k]), k
```

`tests/test_web_boardgame_assets.py` 末尾追加：

```python
def test_subset_no_longer_serves_legacy_azul_keys():
    html = web._SERVED_PAGE().decode("utf-8")
    bg = _extract_bg_literal(html)
    for k in ("azul_table", "azul_boardface", "azul_track"):
        assert k not in bg, k
    for k in ("azul_wall_bg", "azul_board", "azul_track_ring", "azul_chip", "azul_marker_r"):
        assert k in bg, k
```
（`_extract_bg_literal` 已在文件顶部定义，直接复用。）

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_azul_package_assets.py tests/test_web_boardgame_assets.py -q`
Expected: FAIL —— `len(_art.ASSETS) == 22` 失败（当前 25）；`test_azul_legacy_web_keys_are_gone` 失败（旧键仍在）。

- [ ] **Step 3: 实施**

(a) `boardgames/azul/sprites.py`：删除 `make_legacy_table` / `make_legacy_boardface` / `make_legacy_track` 三个函数整体；`_build_images()` 里删 `"azul_table"` / `"azul_boardface"` / `"azul_track"` 三个条目（保留其余 22）。

(b) `web.py:56-62`：`_BG_ASSET_KEYS` 里删 `"azul_table"`、`"azul_boardface"`、`"azul_track"`（Task 1 已加入的新键保留）。

(c) 重生成素材产物：

```powershell
python -m boardgames.azul.sprites
```
Expected: 打印 `generated 22 azul assets`；`boardgames/azul/assets/` 下 `azul_table.png` / `azul_boardface.png` / `azul_track.png` 三个文件已删除。

- [ ] **Step 4: 跑测试确认通过**

```powershell
python -m pytest tests/test_azul_package_assets.py -q
python -m pytest tests/test_web_boardgame_assets.py -q
python -m pytest tests/test_boardgame_asset_img.py -q
```
Expected: 全部 PASS。`tests/test_boardgame_asset_img.py:255-256`（`assert k not in asked`）无需改动即通过。

- [ ] **Step 5: 语法门禁 + 服务页快照**

```powershell
node tests/ux_visual_chat_probe.cjs
```
Expected: `full_script_syntax:true`。

- [ ] **Step 6: 收尾（不提交）**

改动留在工作区待评审。

---

## Task 3: 网页端开发期样张（静态 HTML 产物）

**Files:**
- Create: `_azul_web_preview.py`（仓库根，下划线前缀，不入库）
- Produce: `.trae/tmp/azul_web_preview.html`

**Interfaces:**
- Consumes：`web._SERVED_PAGE()`（真实注入页，含 `GRENDER` + `BG` + `bgImg`）、azul 快照 schema（同 Task 1）。
- Produces：静态 HTML——供控制方用浏览器子代理截图、交用户目视评审网页端观感。

- [ ] **Step 1: 新建** `_azul_web_preview.py`

```python
# -*- coding: utf-8 -*-
"""开发期网页端样张：把真实的注入页存为静态 HTML，并自动调用 GRENDER.azul(mock)。

用法：python _azul_web_preview.py  →  .trae/tmp/azul_web_preview.html
（随后用临时 http 服务打开该页截图；脚本自身不入库、不参与打包。）
"""
import json
from pathlib import Path

import web

OUT = Path(".trae/tmp/azul_web_preview.html")
COLS = ["r", "w", "b", "y", "k"]


def _wall(filled):
    """按引擎拉丁方 (r,c)->COLS[(c-r)%5] 生成墙快照；filled 为已落格集合。"""
    return {f"{r},{c}": (COLS[(c - r) % 5] if (r, c) in filled else None)
            for r in range(5) for c in range(5)}


def _mock_state():
    return {
        "game": "azul", "status": "playing", "round": 3, "turn_uid": 8,
        "colors": {"r": "红", "w": "白", "b": "蓝", "y": "黄", "k": "黑"},
        "offers": [
            [{"c": "r", "n": 1}, {"c": "b", "n": 1}, {"c": "w", "n": 1}, {"c": "k", "n": 1}],
            [{"c": "y", "n": 1}, {"c": "y", "n": 1}, {"c": "b", "n": 1}],
            [{"c": "r", "n": 1}, {"c": "r", "n": 1}, {"c": "k", "n": 1}],
            [{"c": "w", "n": 1}, {"c": "b", "n": 1}],
            [{"c": "k", "n": 1}, {"c": "y", "n": 1}],
        ],
        "center": [{"c": "w", "n": 1}, {"c": "k", "n": 1}, {"c": "r", "n": 1}],
        "rows": {"7": {"0": ["r"], "1": ["b", "b"], "2": []},
                 "8": {"0": ["y"], "1": []},
                 "9": {"0": []}},
        "wall": {"7": _wall({(0, 0), (1, 1), (2, 2)}),
                 "8": _wall({(0, 0), (1, 1), (2, 2), (3, 3)}),
                 "9": _wall({(0, 0)})},
        "floor": {"7": 1, "8": 0, "9": 2},
        "score": {"7": 5, "8": 12, "9": 3},
        "bag": 21, "players": [7, 8, 9], "winner_uid": None,
    }


def main():
    page = web._SERVED_PAGE().decode("utf-8")
    inject = (
        "<script>window.addEventListener('load',function(){"
        "document.documentElement.setAttribute('data-theme','mist');"
        "document.body.innerHTML='';"
        "var box=document.createElement('div');"
        "box.style.cssText='max-width:1200px;margin:16px auto;background:#16232e;"
        "padding:12px;border-radius:10px';"
        "document.body.appendChild(box);"
        "state.uid=7;state.groom='demo';"
        "GRENDER.azul(box," + json.dumps(_mock_state()) + ");"
        "});</script>"
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page.replace("</body>", inject + "</body>"), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 产样张**

Run: `python _azul_web_preview.py`
Expected: 打印 `wrote .trae/tmp/azul_web_preview.html`；文件存在且 > 300 KB（内嵌素材）。

- [ ] **Step 3: 自检产物包含三处结构**

Run（临时 .py，避免 PowerShell 破坏多行 `-c`）：
```python
import pathlib
h = pathlib.Path(".trae/tmp/azul_web_preview.html").read_text(encoding="utf-8")
assert "GRENDER.azul(box," in h and "azgrid" in h and "azul_track_ring" in h
print("ok")
```
Expected: `ok`。

- [ ] **Step 4: 收尾（不提交）**

仅新增 `_azul_web_preview.py` 与产物 `.trae/tmp/azul_web_preview.html`（后者不入库）。

---

## Task 4: 全量回归 + 双 EXE 打包 + EXE 配对烟雾测试

**Files:**
- Verify only（**不改**源码；若发现回归，回到对应 Task 修）
- Produce: `dist/`（两个 EXE）

**Interfaces:**
- Consumes：Task 1-3 的全部改动。
- Produces：可交付的双 EXE；全量回归「无新增 FAIL」结论。

- [ ] **Step 1: 全量回归（逐文件独立进程）**

Run: `python tests/_run_all.py`
Expected: 末尾汇总 `失败=0 崩溃=0`；对每个 FAIL/CRASH 行，确认其**在第一批基线（当前 HEAD 076e207 未提交改动前）也为 FAIL**（属既有环境项，如 Tk 缺 tcl）才算「无新增 FAIL」。把结果逐行记入报告。

- [ ] **Step 2: 读出两个 EXE 名称与产物路径**

Run: `python -c "import pathlib,re;print([l for l in pathlib.Path('build.py').read_text(encoding='utf-8').splitlines() if 'name=' in l or '.exe' in l][:20])"`
Expected: 打印 build.py 里两个 spec 的 `name=`（把实际名称记进报告）；若 `-c` 在本机被破坏，改用临时 `.py` 文件读取。

- [ ] **Step 3: 打包**

Run: `python build.py`
Expected: 退出码 0；`dist/` 下两个 EXE 生成（把实际字节数记进报告，客户端应约 37 MB、服务端约 16 MB 量级）。

- [ ] **Step 4: EXE 配对运行烟雾测试**

按仓库既有流程（`docs/任务清单.md` 检索「烟雾/EXE 配对」）启动服务端 EXE，再启动客户端 EXE，确认：客户端能连上、能进入 Azul 房间并看到 BGA 版面。

- **启动**：`Start-Process .\dist\<服务端>.exe -PassThru`；记下 `Id`（视为根 PID）。
- **确认监听**：`Test-NetConnection 127.0.0.1 -Port 9529`（HTTPS/9529 为本项目约定端口）。
- **客户端**：`Start-Process .\dist\<客户端>.exe -PassThru`。
- **收尾（关键）**：PyInstaller onefile 会派生**子进程**，`Stop-Process` 只杀引导父进程会留下孤儿占端口。必须**按 PID 杀整棵进程树**：

```powershell
taskkill /T /F /PID <根PID>
```

- **复核**：`Get-Process <服务端进程名> -ErrorAction SilentlyContinue` 应为空（无残留）。

记录：根 PID、监听结果、客户端连接结果、`taskkill` 输出、残留复核结果。

- [ ] **Step 5: 收尾（不提交）**

不改任何源码；不 `git add/commit/push`；`dist/` 为构建产物。

---

## Self-Review

- **Spec 覆盖**
  - §8 网页版面：Task 1（CSS grid 五分区 + 遍历 `s.players` 修「只画一块板」+ 动作契约不变）。
  - §9 第二批：Task 1（网页重排）+ Task 2（删 3 沿用键）+ Task 4（打包、回归）。
  - §10 测试策略：Task 1 扩展 `tests/test_web_boardgame_assets.py`（新键进 `BG`、结构标记、契约字符串不变）+ node 语法门禁；Task 2 同步素材/渲染断言。
  - §11 风险：`azul_board` 由 256² 变 384×288 —— 断言在第一批已改，本批只删旧键。
  - 其余 46 款：本批不触碰其渲染路径（零回归，由 Task 4 全量回归兜底）。
- **占位符扫描**：无 TBD/TODO；每个 Step 均有可执行命令或完整代码。
- **类型一致性**：`s.players` 为 `list[int]`；`s.rows`/`s.wall`/`s.floor`/`s.score` 键均为 `str(uid)`（与 `desktop.py` 的 `str(u)` 取用一致）；色序 `COLORS`/`MARKERS` 与 `desktop.py` 同源；`bgImg()` 片段不含单引号（`test_bg_img_fragment_survives_single_quoted_style_attribute` 锁定）。
- **任务独立性**：Task 1 只让渲染器改用新键（旧键仍在，互不影响）；Task 2 才移除旧键与生成函数；Task 3 只产静态样张；Task 4 只验证与打包。
- **不提交**：每个 Task 以「定向测试/门禁通过 + 改动留工作区待评审」收尾。
