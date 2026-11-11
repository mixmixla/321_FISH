# 小丑牌 · 双人实体牌桌

本包目前只注册多人 `balatro`。单人 `balatro_solo` 的商店、消耗品和22种能力未接入本包，沿用原入口。

## 真实物件与数据

- 扑克由 Tk/DOM 从实际 `hand[].c/s/id` 绘制，T显示为10，红桃/方块红色，黑桃/梅花深色。角色画不覆盖扑克牌花色与点数，不显示机器cid。
- 点手牌选入出战区；点已选牌撤回。点实体弃牌堆进入弃牌模式，再点未入台手牌弃掉并补抽。点结算筹完成实际出牌。
- 去掉多人版旧动作排、手输牌序号和重复私牌字符串。桌面键盘←→选牌、空格选/撤、Delete切换弃牌、Enter结算、Esc取消/退出阅图；Web使用原生可访问按钮。
- 服务端给出目标、剩余弃牌/出牌次数，`private` 标记本人UID/游戏及真实牌型预览。预览不调用随机或计分副作用。
- `last_play` 只包含已实际打出的牌、实际牌型与得分，不包含未打出的手牌；结算后保留在桌面供两人和观战者查看。
- 动作绑定房间、局次、UID、公共/私有帧；旧会话、旧状态、非本人回合与观战不可提交。Joker放大阅图不发游戏动作。

## 原创角色图集

内置 ImageGen 实际生成，原创日系美少女赛璐璐场景。人物均为成年女性；道具体现被动能力。非头部头像贴牌；场景仅用于专属 Joker，普通扑克不使用人物图。

资产：`assets/boardgame/gallery/balatro-jokers-core.webp`，1200×800，4列×2行，385,164 bytes，RGB WebP quality88。原图1536×1024等比优化，无代码重画人物。

| 0-based格 | 正式ID | 名称 | 大型可辨识道具 |
| --- | --- | --- | --- |
| 0 | pair | 对子王 | 红发舞台魔术师与两张同背牌 |
| 1 | flush | 同花狂热 | 蓝发魔术师与五枚同形蓝宝石 |
| 2 | straight | 顺子推进 | 绿发旅法师与五阶递进卡背 |
| 3 | sf | 同花顺神 | 银发星术师与五阶同形蓝宝石 |
| 4 | four | 四条杀神 | 金黑领班与四顶同形金冠 |
| 5 | full | 葫芦压阵 | 紫发魔术师托盘上的三红球、两蓝球 |
| 6 | heart | 红心暖手 | 珊瑚发治疗师、红心晶体与筹码 |
| 7 | spade | 黑桃猎手 | 深青发猎手、弓与黑桃形箭头 |

标题与数值从 `games_pkg.balatro.JOKER_DEFS` 生成；图号由 `catalog.py` 明确映射，Tk与Web共用。Web版本 `anime-jokers-v1`。

封面：`assets/boardgame/gallery/cover-balatro.webp`，768×384，87,634 bytes，quality86；成年女荷官、扑克、牌堆和筹码。封面没有游戏点数或规则文字，不作为对局数据。

## 最终提示词组（内置工具）

**核心八格**：`stylized-concept; original specialty Joker illustration atlas for poker scoring; exact4 equal columns by2 equal rows, portrait3:4 cells on landscape3:2, edge-to-edge, no gaps/borders/type/digits/logos. Refined Japanese bishoujo2D cel animation, clean dark lines, controlled bright colors, eight distinct fully clothed beautiful adult women, three-quarter/full figure narrative scenes with large physical ability props, not avatar headshots. Strict row-major: crimson-haired ivory-red stage magician with TWO matching ivory card backs; cobalt-haired blue magician with FIVE identical sapphire diamonds; green-ponytail traveling mage beside FIVE ascending ivory card-back stairs; silver-haired navy constellation mage presenting FIVE matching sapphire diamonds in ascending stairs; auburn ringmaster with FOUR identical floating gold crowns; lavender magician with THREE red and TWO blue crystal orbs on a tray; coral-haired healer supporting ONE red heart crystal above gold poker chips; dark-teal ranger with bow and prominent black spade-shaped arrowhead. Faces upper third, props dominate foreground, clear at small size. No men, sexualization, playing-card front ranks, typography, photorealism, engraving, painterly texture or chibi.`

**封面**：`stylized-concept; wide2:1 original anime poker-table cover; beautiful adult crimson-haired female stage dealer in tasteful ivory-red magician coat behind green velvet table. Foreground physical objects dominate: large cream cards with simple red hearts/black spades, gold poker-chip stacks, ornate ivory card-back deck and two distinct female specialty performers in a side rack. No typography/letters/digits/fake written rules. Crisp Japanese bishoujo cel animation, warm stage lights/curtains, emerald/ivory/red/gold palette, tasteful fully clothed adult. Central85percent crop safety. No male characters, sexualization, logos/watermarks/UI diagrams, photorealistic skin, engraving, painterly texture or chibi.`
