# 情书 · 二次元宫廷角色牌

- 预览/资产：`lovelove-court.webp`
- 图集：1200×800，严格 4 列×2 行；单格 300×400（约 3:4）
- 最终体积：351,462 bytes（WebP，RGB，quality 88）
- 大厅封面：`cover-lovelove.webp`，768×384，125,604 bytes（quality 86）。
- 来源：Codex 内置 ImageGen 原创日系动画赛璐璐图集，无参考图、无商业角色、无文字/点数。
- 按本轮用户补充，八种正式头衔均由不同的成年美少女/年轻女性演绎；不改变游戏角色名、等级、能力或卡牌数量。
- 桌面 `value - 1` 与网页 `data-art=value - 1` 共用同一图集；网页资源版本 `anime-court-v1`。

名册（严格行优先，0-based 图号；身份文字、数字、能力由 UI 生成）：

| 图号 | 牌值 / 正式角色 | 可辨识人物与物件 | 游戏能力 |
| --- | --- | --- | --- |
| 0 | 1 护卫 | 深青短发、蓝白制服、胸甲、长枪、盘问手势 | 选目标并猜持牌 |
| 1 | 2 牧师 | 银色长发、象牙紫边长袍、打开的圣书、仪杖 | 本人私下查看目标 |
| 2 | 3 男爵 | 赤褐马尾、酒红贵族外套、白领巾、决斗剑 | 比较持牌 |
| 3 | 4 侍女 | 棕色编发、女仆帽、鼠尾草绿裙、银托盘 | 获得保护 |
| 4 | 5 王子 | 蜜金发、开口小冠、蓝白外套、双封蜡信 | 目标弃牌重抽，可选自己 |
| 5 | 6 国王 | 浅金长发、大王冠、翡翠披袍、王座、交换双信 | 交换持牌 |
| 6 | 7 伯爵夫人 | 紫色长发、羽毛宽帽、珍珠、折扇与信封 | 与公主同持必须弃出 |
| 7 | 8 公主 | 玫瑰金长发、宝石冠、白玫瑰裙、胸前单封情书 | 弃出自己出局 |

最终生成提示词组（内置 ImageGen，初版含男性的草稿弃用，未入库）：

1. **角色图集**：`stylized-concept; production role-card sprite atlas; eight distinct beautiful adult anime women, all female, including prince/king/baron/priest titles; exact four equal columns by two equal rows, landscape 3:2, portrait 3:4 cells, edge-to-edge with no gutters/frames/text/numbers/logos. Refined Japanese bishoujo 2D cel animation, expressive feminine faces, fine dark linework, two-tone cel shadows, luminous restrained rose/ivory/gold court; all fully clothed and tasteful. Waist-up to three-quarter with upper-centered faces and headroom. Strict row-major roles and props: navy guard/spear; silver priest/open prayer book/staff; auburn baron/burgundy coat/rapier; brown-braided handmaid/sage apron/silver tray; honey-blond female prince/small coronet/blue coat/two sealed letters; ash-blond female king/large crown/emerald mantle/throne/exchanging letters; violet countess/plum gown/feathered hat/fan/envelope; rose-gold princess/tiara/white-rose gown/love letter held to heart. No men, same-face cast, sexualization, engraving, painterly texture, photorealism or chibi.`
2. **大厅封面**：`stylized-concept; wide 2:1 game lobby cover; three beautiful adult anime women only. Rose-gold-haired princess with jeweled tiara and white-rose high-neck gown holds a wax-sealed love letter to her heart; short dark-teal-haired female guard in navy-ivory breastplate holds an upright spear; honey-blond female prince with navy ribbon, small coronet and blue princely coat offers another sealed letter. Sunlit palace arches, rose vines and courtyard fountain, subtle courtly intrigue. Distinct delicate feminine faces, fully clothed, confident calm expressions, crisp fine linework and two-tone cel shading, luminous rose/ivory/gold. Center grouping within 85 percent for crop safety. No men, text, numbers, logos, watermarks, UI/panels, painterly texture, engraving or photorealism.`

原始生成图集为 1536×1024，等比缩至1200×800；封面等比裁适至768×384。仅作格式/尺寸优化，未用代码改画人物。

操作与隐私：桌面和网页通过角色牌选出牌；护卫通过八种角色图选猜值，目标显示玩家。牧师公开事件只说明查看关系；`private(uid).peek` 仅给行动者、标注“当时查看”。相关玩家出牌/换手/重抽/淘汰/离房或终局会使观察失效，不把旧观察当作当前手牌。
