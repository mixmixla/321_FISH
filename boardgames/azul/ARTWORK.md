# 彩釉工坊 · 花砖物语美术

ARCADE-20261106 v1.1 的原创 ImageGen 位图资源。使用内置 `image_gen` 工具实际生成一张 3×2 图集，2026-11-06 定稿。五块印花依次为蓝白海浪、朱红五瓣花、金黄日轮、象牙白叶枝、近黑几何星；第六块是无文字、无格线的浅青釉面桌垫。不是用绘图代码替代生成图。

## 唯一源与重建

- 唯一美术源：[assets/source/glaze-atlas.png](assets/source/glaze-atlas.png)，384×256 RGB PNG（3列×2行，每格128px）。保留生成图缩小后的必要版本，不附大原图或候选图。
- 源 SHA256：`7fc198844e2b7fa69e5ebcc70efcca08598618bbaa0b035d99aa72413bdc32a8`。
- 保持原有 22 个资源键与尺寸；`sprites.py` 裁出印花、淡化空墙格、裁圆计分棋子，并沿用 artkit 制作盘、筹码、地板槽及低对比无缝桌面。它没有重画这五种生成印花。
- 玩家板只使用第六面板的内侧材质，不带铭牌、花纹行、墙格、地板格或按钮；这些实际结构、文字和命中区由 Tk/Web 实时绘制。
- `assets/*.png` 和 `_art.py` 为同一次出包的优化 PNG；桌面与 Web 都使用 `_art.ASSETS`。运行时无需图像服务或图集加载，不增加共享入口或打包框架。

在项目根目录，使用项目 Python 执行：

```powershell
& 'D:/Project/321_FISH/.venv/Scripts/python.exe' -m boardgames.azul.sprites
```

生成器离线重建所有 22 张 PNG 和内嵌模块。`test_glaze_atlas_rebuilds_both_runtime_and_packaged_pngs` 验证源、包内文件、内嵌数据完全一致；`assets/source/` 同时被既有隔离门禁的静态资源规则收集。

## 最终生成提示（内置工具，非 CLI）

```text
Use case: stylized-concept. Asset type: production raster source atlas for an original ceramic board game called 彩釉工坊.
Create ONE clean landscape 3:2 image atlas, exactly 3 columns by 2 rows of equal SQUARE full-bleed panels, no gaps, no margins. Six panels touch edge to edge. Every panel seen perfectly orthographically from directly above, flat 2D production material, no perspective.
Top left: rich cobalt BLUE glazed ceramic with one large bold IVORY curling ocean wave, thick elegant print, nearly fills square, recognizable silhouette at 20 pixels.
Top middle: deep vermilion RED glazed ceramic with one large IVORY five-petal blossom, round petals, thick simple clear print, recognizable at 20 pixels.
Top right: warm golden YELLOW glazed ceramic with one large dark umber SUN DISC and eight broad short triangular rays, thick clear silhouette, recognizable at 20 pixels.
Bottom left: warm IVORY glazed ceramic with one large dark petrol green curved LEAF sprig, three broad leaves, thick clean silhouette, recognizable at 20 pixels.
Bottom middle: near-BLACK midnight glazed ceramic with one large pale cool ivory four-point GEOMETRIC STAR / interlocking diamond, thick bold distinct silhouette, recognizable at 20 pixels.
Bottom right: a completely CLEAN pale warm celadon-ivory glazed ceramic tabletop / player's mat material with very subtle cloudlike glaze pooling and tiny sparse kiln speckles. Uniform quiet surface from edge to edge; this panel has NO motif, NO lines, NO grooves, NO borders, NO slots, NO grid or UI.
All five motif panels have matching handmade glazed ceramic character, a tiny amount of tactile glaze pooling, soft material gleam, luxurious restrained artisan finish. The five motifs must be strongly different outlines. Central prints are broad solid shapes, not ornate or fine detailed. The colors occupy the entire square, including corners. Every panel's face extends to its exact rectangle edges. No shadows outside panels; no tile bevels or cutout outlines. We will crop panels and draw real tile boundaries in the game.
ABSOLUTELY NO text, numbers, typography, labels, watermarks, buttons, gameboard diagrams, fake grid cells, repeating mini tiles, objects or decorative frames. Exactly SIX panels, first five are original ceramic prints, final panel is blank quiet glazed mat material.
```
