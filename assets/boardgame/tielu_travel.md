# 铁路旅行地图素材

`tielu_travel.jpg` 和 `gallery/cover-tielu.webp` 于2026-11-06使用 Codex 内置 ImageGen 全新生成，无参考图。地图采用明快、细腻、清晰轮廓的原创日系动画风景；封面采用原创成年女性列车长、空白车票及海岸旅行列车。运行中的桌面与网页共用同一张地图，线路和数据继续由真实状态绘制。

交付地图为1280×853 JPEG（350576字节），封面768×384 WebP。原始PNG保留在本机Codex生成目录；项目只保留压缩交付图。地图内不预画铁路、线路、城市节点、文字、车票数字和归属，宽阔浅色中央用于叠加15条真实线路。缺图仍回退原纸色棋盘。

两端实际节点归一坐标如下，风景只是提示，节点、命中区与规则端点为权威：

| ID | 城市 | x | y | 邻近地貌 |
| --- | --- | ---: | ---: | --- |
| 0 | 港口 | .16 | .23 | 海湾及小港 |
| 1 | 河城 | .42 | .19 | 河流及小村 |
| 2 | 山城 | .72 | .20 | 蓝灰山地 |
| 3 | 雪镇 | .88 | .43 | 雪岭 |
| 4 | 沙堡 | .77 | .76 | 沙丘及小堡 |
| 5 | 雾谷 | .46 | .76 | 雾谷 |
| 6 | 林郡 | .18 | .75 | 松林 |
| 7 | 金矿 | .10 | .49 | 赭色岩地 |

地图完整提示词：

> Use case: stylized-concept. Asset: original JAPANESE ANIME background illustration for a playable railway journey map; landscape 3:2, 1536x1024. New hand-drawn cel animation background, luminous clean pastel colors, sharp delicate contours, warm sunlight, detailed picturesque small landscape motifs. Top-down gently oblique illustrated geography with NO horizon, no large perspective foreground. The entire region is one continuous traversable land area. Place tiny evocative landmarks near these normalized positions, without defining city nodes: a vivid turquoise SEA BAY and small sailing harbor upper-left around (16%,23%); a clear soft RIVER and tiny terracotta roof village upper-middle around (42%,19%); layered blue-gray MOUNTAINS upper-right around (72%,20%); a SNOWY MOUNTAIN ridge far-right around (88%,43%); pastel peach DESERT HILLS and tiny adobe fortress lower-right around (77%,76%); misty pale lavender VALLEY lower-center around (46%,76%); rich but small PINE WOODLAND lower-left around (18%,75%); a few ochre rocky mineral OUTCROPS western edge around (10%,49%). Attractive distinctive anime scenery, lively but tasteful. CRITICAL gameplay composition: the broad CENTRAL 65% must be SPACIOUS, PALE, LIGHT low-contrast mint grassland and cream valleys with very sparse detail so fifteen different colored train routes can be drawn over it. Landscape detail concentrated on perimeter, no central buildings, no dark dense forest in center. Edge-to-edge, no border, no paper texture. Absolutely NO railway tracks, NO trains, NO roads, NO connecting lines, NO routes, NO node circles, NO city markers, NO labels, NO letters, numbers, logos, title, watermark, compass, legend, grid, cards, counters, interface or people. Pure scenic background only. Preserve clear flat geography for code to draw actual rules.

封面完整提示词：

> Use case: stylized-concept. A beautiful ORIGINAL ANIME BISHOUJO illustration for a railway board game lobby cover. Landscape 2:1 full-bleed, no frame. Foreground left: a charming clearly YOUNG ADULT FEMALE train conductor age 24, bright green eyes, flowing chestnut hair in a practical side braid, elegant navy conductor cap and navy uniform jacket with brass details, white shirt and teal neck scarf, friendly confident smile. She is holding TWO clearly recognizable PLAIN rectangular train tickets at chest level (simple blank cream ticket stock, no writing or numbers). Correct hands and anatomy. Behind and to the right: a vivid teal-and-cream vintage passenger TRAIN travels on a graceful stone viaduct above a sparkling coastal bay, distant small harbor village and forested mountains. Fine clean Japanese cel animation line art, luminous sunny sky, crisp contours, nuanced but simple cel shadows, beautiful character design, animated feature-film polish, warm inviting travel mood. Face and tickets and train readable at 768x384. No male characters, no other people, no existing IP characters. Absolutely NO text, letters, numbers, logos, watermark, rules icons, game interface or card frames.

## 实物牌桌 · 票卡与目的站

内置 ImageGen 原画。五色票和检票员用 3 列 × 2 行方格；行优先为红色蒸汽机车、黄色有轨电车、绿色通勤列车、蓝色特快、紫色卧铺列车、女性检票员。提示要求中央突出不同车头的剪影和主色，票面文字和张数由程序追加。五张只能从盲抽车票堆取得，检票员用于目的票牌堆或桌边。

城市邮票用 4 列 × 2 行方格，按规则城市号排列，提示要求在缩小的旅行邮票中也能认出单一标志。上排为港口灯塔和白船、河城石桥、山城缆车、雪镇木车站；下排为沙堡砂岩塔、雾谷高架、林郡林间瞭望台、金矿井架与矿车。两端分别用目的票的 a、b 选图，票值、持牌数量、连接印章、车厢节数和归属均来自当前牌局。

输出为 assets/boardgame/gallery/tielu-coach-cards.webp（1152×768）及 tielu-stations.webp（1024×512）。实盘只由玩家点线路查看花费，再确认认领。按颜色点手牌可查看同色线路，点私人目的票标出两座车站。
