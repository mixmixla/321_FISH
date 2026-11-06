# 花砖物语 · 二次元彩釉工坊

ANIME-TABLES-20261106 v1.1 使用内置 ImageGen 原创重绘，风格为清晰日系动画赛璐璐。五种实体花砖保留真实色键；大厅封面为成年美少女陶艺师和可辨识的五块砖。未改变砖数、墙色循环、评分或动作协议。

## 唯一源、精确映射与重建

- 唯一美术源：[assets/source/glaze-atlas.png](assets/source/glaze-atlas.png)，384×256 RGB PNG，3列×2行，每格128×128。
- SHA256：`4ef6bebb035139cd9bc235278dda896729c7ff6053ff9dd43b4ef861b1060f28`；113,960 bytes。
- 0-based行优先索引：0=`b` 蓝浪，1=`r` 红花，2=`y` 黄日，3=`w` 白叶，4=`k` 黑金八角星，5=无纹浅青釉桌垫。与 `sprites._PANELS` 一一对应。
- 引擎墙色循环仍是 `r,w,b,y,k`，不能把图集行优先顺序当作墙色顺序。
- 保持原22个资源键及尺寸；`sprites.py` 从同一图集裁出五种砖、淡化空墙格、裁圆计分棋子，其他盘/筹码/地板/轨道继续由既有artkit生成。
- 玩家板只用第六格内侧材质，不烧入格线、槽、名字、分数、按钮；两端从真状态绘制这些结构及命中区。
- `assets/*.png` 与 `_art.py` 同次生成；Tk/Web共用 `_art.ASSETS`。运行时无需ImageGen或外部图库。
- 大厅封面：[cover-azul.webp](../../assets/boardgame/gallery/cover-azul.webp)，768×384 RGB WebP，69,978 bytes，quality85。

```powershell
& 'D:/Project/321_FISH/.venv/Scripts/python.exe' -m boardgames.azul.sprites
```

`test_glaze_atlas_rebuilds_both_runtime_and_packaged_pngs` 校验源、包内PNG和内嵌字节相等；板材低对比检查继续保留。

## 最终提示词组（内置 ImageGen）

**图集**：`stylized-concept; production ceramic tile texture atlas; exact three equal columns by two equal rows, six square cells, landscape 3:2, edge-to-edge hard boundaries, no gaps or labels. Refined Japanese 2D cel animation, crisp bold outlines, flat rich glaze, simple elegant highlights. Strict row-major: cobalt blue ground with large ivory curling wave; cinnabar red with large ivory five-petal flower/gold center; golden yellow with dark-brown round sun and eight broad rays; warm ivory-white with dark-sage three-leaf sprig; near-black midnight with warm gold eight-point star; plain pale mint/ivory mat with faint soft glaze sheen, no motif/grid/slots/rows/borders/symbols. Perfect top-down square faces; small bevel only at extreme outer edges. Large centered unique silhouettes readable at20px. No tiny ornament, mini-tile mosaic, perspective, hands/people, text/numbers/logos/watermarks, photographs or painterly noise.`

**封面**：`stylized-concept; wide2:1 original game-lobby cover; beautiful adult female ceramic artist with teal eyes, warm chestnut shoulder-length hair/navy ribbon, ivory blouse and sage-green apron, fully clothed, smiling gently with paintbrush and unpainted spare square. Exactly five prominent real glazed square tiles in foreground: blue/ivory curling wave; red/ivory five-petal flower/gold center; yellow/dark-brown sun; white/dark-sage three-leaf sprig; black/gold eight-point star. Five tiles in a gently curved row with slight perspective, motifs unobscured. Bright sunlit ceramic workshop, plain pottery shelves, central85percent crop safety. Fine crisp Japanese bishoujo cel animation with two-tone shadows, distinct feminine adult face. No men, text/digits/logos/watermarks/UI/grids/frames, photorealism, engraving, painterly texture, chibi or extra motif tiles.`

原图集1536×1024等比缩至384×256；封面适配768×384。代码仅做裁切/缩放/资源出包，没有代替ImageGen重画花纹或人物。

## 实体与操作

- 桌面点工厂/中央的真实花砖只做预选，再点本人花纹行或地板提交。保留原拖拽。真实 `click → drag/down → drag/up` 顺序共用锁，每手只发一个take和一个place/floor。
- 主入口移除旧「溢出地板」动作排，不再经文本输入取砖或落砖。键盘在同一实物画布使用：←→选砖，↑↓选落点，Enter落砖，Esc取消；选择过程不发动作。网页沿用原生按钮/可访问落点，页面无旧输入表单。
- 选中绑定房间/账号/快照；最终提交拒绝旧房、旧状态、其它游戏、非本人回合。一次性take/place配对允许take ACK刚替换快照时完成匹配的落砖，随后即删除。
- 原工厂/中央色键和行/地板命中区仍由同一几何生成；满行、异色行、已占墙色不可落。
- 首次玩家筹按 `marker_uid` 显示在中央或持有者板/地板说明区；有空位时地板总数含该筹，地板满7格时只在板头保留先手归属，不虚构第八格。显示本轮先手与下轮先手。归属提示不伪造它在地板中的原始插入顺序。
- 上墙仍只发生在轮末，格位按引擎拉丁方 `(color_index + row) % 5`，空墙淡纹与已上墙实砖分层。
