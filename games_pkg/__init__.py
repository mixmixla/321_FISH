# -*- coding: utf-8 -*-
"""游戏注册表：{game_name -> GameClass}，可插拔扩展"""
from games_pkg.base import BaseGame, GameRuleError
from games_pkg.balatro import BalatroGame, BalatroSoloGame
from games_pkg.betrayal import BetrayalGame
from games_pkg.blackjack import BlackjackGame
from games_pkg.calc24 import Calc24Game
from games_pkg.connect4 import Connect4Game
from games_pkg.drawguess import DrawGuessGame
from games_pkg.gomoku import GomokuGame
from games_pkg.guess_number import GuessNumberGame
from games_pkg.matchpairs import MatchPairsGame
from games_pkg.othello import OthelloGame
from games_pkg.rps import RpsGame
from games_pkg.spy import SpyGame
from games_pkg.uno import UnoGame
from games_pkg.kaituo import KaituoGame
from games_pkg.lingdi import LingdiGame
from games_pkg.tielu import TieluGame
from games_pkg.gongfang import GongfangGame
from games_pkg.chengzhu import ChengZhuGame
from games_pkg.gemcity import GemCityGame
from games_pkg.siji import SijiGame
from games_pkg.bolan import BolanGame
from games_pkg.azul import AzulGame
from games_pkg.rummikub import RummikubGame
from games_pkg.yahtzee import YahtzeeGame
from games_pkg.nimmt import NimmtGame
from games_pkg.davinci import DaVinCiGame
from games_pkg.kalah import KalahGame
from games_pkg.lovelove import LoveLoveGame
from games_pkg.halloween import HalloweenGame
from games_pkg.tictactoe import TicTacToeGame
from games_pkg.halma import HalmaGame
from games_pkg.checkers import CheckersGame
from games_pkg.blokus import BlokusGame
from games_pkg.ludo import LudoGame
from games_pkg.xiangqi import XiangQiGame
from games_pkg.chess import ChessGame
from games_pkg.go import GoGame
from games_pkg.shogi import ShogiGame
from games_pkg.junqi import JunqiGame
from games_pkg.dou import DouGame
from games_pkg.onewolf import OneNightWolfGame
from games_pkg.werewolf import WerewolfGame
from games_pkg.avalon import AvalonGame
from games_pkg.liar import LiarGame
from games_pkg.ninja import NinjaNightGame
from games_pkg.coc import CocGame

def _label(name: str) -> str:
    return {
        "guess_number": "猜数字", "gomoku": "五子棋", "rps": "石头剪刀布",
        "spy": "谁是卧底", "uno": "UNO", "blackjack": "21点", "drawguess": "你画我猜",
        "connect4": "四子棋", "othello": "奥赛罗", "calc24": "24点",
        "matchpairs": "抽牌配对", "betrayal": "山屋惊魂",
        "kaituo": "开拓", "lingdi": "领地", "tielu": "铁路",
        "gongfang": "工坊", "chengzhu": "我是城主", "gemcity": "璀璨宝石",
        "siji": "四季物语", "bolan": "波兰大选",
        "azul": "花砖物语", "rummikub": "拉密", "yahtzee": "快艇骰子", "nimmt": "牛头王",
        "davinci": "达芬奇密码", "kalah": "非洲播棋", "lovelove": "情书", "halloween": "德国心脏病",
        "tictactoe": "井字棋", "halma": "跳棋", "checkers": "国际跳棋", "blokus": "角斗士棋", "ludo": "飞行棋",
        "xiangqi": "中国象棋", "chess": "国际象棋", "go": "围棋", "shogi": "将棋",
        "junqi": "军棋", "dou": "斗兽棋",
        "onewolf": "一夜狼人",
        "werewolf": "狼人杀",
        "avalon": "阿瓦隆",
        "liar": "骗子酒馆",
        "ninja": "忍者之夜",
        "coc": "克苏鲁呼唤",
        "balatro": "小丑牌",
        "balatro_solo": "小丑牌·单人",
    }.get(name, name)


def _desc(name: str) -> str:
    """一句话玩法（大厅卡片上展示）"""
    return {
        "guess_number": "出题 1~100，猜中得分",
        "gomoku": "双人对弈，先连五子胜",
        "rps": "三选一互克，人多热闹",
        "spy": "找卧底！描述别暴露",
        "uno": "同色同数出牌，先出完胜",
        "blackjack": "要牌凑 21，别爆牌",
        "drawguess": "画手画图，大家猜词",
        "connect4": "列式落子，先连四子胜",
        "othello": "黑白翻转夹子，子多者胜",
        "calc24": "四张牌加减乘除凑 24",
        "matchpairs": "摸牌配对，王八落败",
        "betrayal": "探索山屋抽预兆，揪出叛徒或逃出生天",
        "kaituo": "掷骰采资源，建路村城凑 10 分",
        "lingdi": "拼板块拓疆，连区放米宝拼高分",
        "tielu": "认领线路连城市，票证结算定胜负",
        "gongfang": "抢工位得资源分，三轮工分最高",
        "chengzhu": "每种板块搭配王冠，比连通区得分",
        "gemcity": "收集宝石购卡，折扣+贵宾冲 15 分",
        "siji": "三季打牌组引擎，产出换胜利点",
        "bolan": "选区投影响力，多方合计分最高",
        "azul": "5色瓷砖取砖拼花墙，行满分最高",
        "rummikub": "拍牌组群或顺，先清空手牌胜",
        "yahtzee": "掷5骰凑分类记分，13项总分最高",
        "nimmt": "暗出牌落列，吞牛头最少者胜",
        "davinci": "数字牌暗藏排列，轮流猜牌值淘汰",
        "kalah": "6 洞播子，末尾收子拼石子最多",
        "lovelove": "递情书逐一出局，只剩一人胜",
        "halloween": "翻牌凑 5 颗同水果拍铃收牌",
        "tictactoe": "九宫格两三连，先连一线胜",
        "halma": "星盘跳子搬家，全队先过线胜",
        "checkers": "斜走斜吃，吃光或无路可走胜",
        "blokus": "角对角拼方块，铺得最满者胜",
        "ludo": "掷骰起飞冲关，先到终点四机胜",
        "xiangqi": "红黑对弈，将死或困毙对方胜",
        "chess": "白先黑后，标准规则将死对方胜",
        "go": "黑白落子围地，目数多者胜",
        "shogi": "吃掉对方玉将即为胜",
        "junqi": "明棋孰强，扛军旗者胜",
        "dou": "八兽相克，占敌营者胜",
        "onewolf": "一夜推理，处决狼人胜",
        "werewolf": "多夜推理，找出狼人",
        "avalon": "组队任务，找出叛军",
        "liar": "扣牌报数，挑战揭穿",
        "ninja": "暗选攻防，同时结算",
        "coc": "KP自由剧情，d100技能检定",
        "balatro": "梭哈牌型闯关，小丑牌加持血战到底",
        "balatro_solo": "单人闯关，chips×mult 双轨计分",
    }.get(name, "")


def _rules(name: str) -> str:
    """规则说明（大厅内嵌展示）"""
    return {
        "guess_number": "房主先出题（1~100 数字），其他人轮流猜；出题人提示“大了/小了”，"
                        "猜中者得 1 分，下一轮换人出题。",
        "gomoku": "两人轮流落子（输入坐标 x,y，从 0 开始），横/竖/斜先连成 5 子者胜；"
                  "对局结束可再来一局。",
        "rps": "每轮同时出拳：✊ 石头赢 ✌️ 剪刀、✌️ 剪刀赢 ✋ 布、✋ 布赢 ✊ 石头；"
               "胜者得 1 分，平局重出。",
        "spy": "每人抽到词（卧底是不同词），轮流描述但不能说出词；每轮投票淘汰疑似卧底，"
               "卧底活到最后或平民被投光则卧底胜。",
        "uno": "按颜色/数字/功能牌出牌，无牌可出就摸一张；先出完所有手牌者得分，多轮累计积分。",
        "blackjack": "轮流要牌(hit)或停牌(stand)，点数尽量接近 21 且不爆；比庄家点数大者胜。",
        "drawguess": "画手用“笔画”输入线段坐标（x1,y1,x2,y2）作画，其他人输入猜词；"
                     "猜中得分，每轮轮换画手。",
        "connect4": "双人对弈，轮流输入列号（0~6）落子，棋子垂直下落；任何方向先连成 4 子者胜，"
                    "棋盘满为平局。",
        "othello": "黑白双方轮流落子（输入 x,y），落子必须能横向/纵向/斜向夹住对方子并翻转；"
                   "无处可落则让过，双方皆无处可落时按棋子多寡定胜负。",
        "calc24": "每轮出 4 张 1~9 的牌，所有人抢先用 + - * / 与括号凑出 24，且必须恰好用尽每张牌；"
                  "先答对者得 1 分，共 5 轮，分高者胜。",
        "matchpairs": "每人发牌先配对弃掉；轮到你就摸下一家一张牌，能配对就弃成对。"
                      "最终只剩 1 张配不成的“王八”，持牌者落败，其余人安全。",
        "betrayal": "探索阶段：每回合按速度移动，首次进入新房间抽牌——事件（随机祸福）/物品（道具）/"
                    "预兆（属性+1 并做惊魂检定：掷 d6 ≤ 已抽预兆数即惊魂降临）。"
                    "惊魂阶段：力量最高者被附身为叛徒（力量+2，身份公开），出口之门显现；"
                    "叛徒击杀全部幸存者获胜；幸存者击杀叛徒，或全员抵达出口之门后点「全员撤离」获胜。"
                    "任意属性归 0 角色死亡，掉线视为死亡。",
        "kaituo": "布局阶段先各放 1 村+1 路再逆向补；主局回合=掷骰(全座按邻接资源地产资源)，"
                  "可用资源建：路{木头,砖}、村{木头,砖,羊,麦}、城{2麦,3矿}，或 4:1 换资源。"
                  "村 1 分、城 2 分、最长路 2 分，先到 10 分者胜。",
        "lingdi": "轮流摸一张板块放到相邻且地型匹配的位置，可放米宝；当连通地型区四周被板块"
                  "围死即按格数结算；牌堆尽则清场结算，总分最高者胜。",
        "tielu": "回合三选一：摸 2 张车票卡、认领一段线路(付对应色的车票卡、获得长度分)、"
                 "抽一张私人票证(终局连通城市加分/否则扣分)。全部线路认领完，按长度分+票证"
                 "结算总分最高者胜。",
        "gongfang": "每轮生成一排工位(含随机奖励分与独占先手位)。回合=把空闲工人放到空位拿分，"
                    "或过牌；全员过牌即本轮结算。3 轮总分最高者胜，每人每轮 2 个工人。",
        "chengzhu": "每人用 1x2 多米诺拼装自己的 5x5 领地，每半有地型与王冠。板块须与自家同地型"
                    "相邻(首板任放)。终局按每片连通地块「格数×王冠总数」计分，总分最高者胜。",
        "gemcity": "回合四选一：取 3 颗异色宝石 / 取 2 颗同色(库≥4) / 保留一张市场卡(得 1 金) / "
                   "购买一张发展卡(永久折扣+分)。手牌满足贵宾需求即邀贵宾+3 分。先到 15 分者"
                   "触发终局，全场各补一回合后总分最高者胜。",
        "siji": "三季各一轮，轮初抓手牌。回合=打一张牌进引擎(付水晶)、或激活引擎一张卡生产资源"
                "(本季一次)、或用 3 金币换 1 胜利点。终局按胜利点+每 2 水晶 1 分+每 3 金币 1 分"
                "结算。",
        "bolan": "在 5 块选区轮流投放影响力棋子；每轮(全体各投 1 枚)结算一次选举，每选区子多"
             "者得该区子数票。弃 2 枚可在某选区翻倍影响力；任一玩家影响力用尽即终局，"
             "累计票数最高者胜。",
        "azul": "每回合每座工厂碗放 4 片瓷砖，轮流从一座碗(或中央)拿取某色的全部瓷砖，再落进"
                "自己 5 排花纹行的空排(每排各色不同)；排满即落一块上墙并按行列连续计分，"
                "积压掉地板计负分，首取中央者多 -1。有玩家拼满整行或瓷砖袋耗尽即终局，"
                "按墙分 - 地板分定胜负(整行+2/整列+7 奖励)，总分最高者胜。",
        "rummikub": "手牌按 1~13 四色两联。同桌规则：三张以上同数异色成「群」，或三张以上同色"
                    "连号成「顺」。回合里可用手牌组新组、或接续桌上任意牌的组首/组尾；首次上牌"
                    "要求一次性放 ≥30 点。可连续出多次，无牌可(愿)出则摸 1 张结束回合。"
                    "谁先清空手牌谁胜。",
        "yahtzee": "每回合掷 5 枚骰子，最多重掷 2 次(可任意保留)，然后挑一个尚未填写的分类记分："
                   "上区 1~6 点(按该面色面累加)、三条/四条(满则求和)、葫芦 25、小顺 30、大顺 40、"
                   "快艇(5同)50、任意(求和)。13 项全填后按总分行最高者胜，上区满 63 加发 35。",
        "nimmt": "104 张牌各带 1~7 个牛头，桌面排 4 列递增。十轮每轮全员暗选一张，按牌面升序"
                 "依次落列：落到「比它小且最接近」的列尾；若比所有列头都小，须吞一整列(负分)并"
                 "自起新列；落列使该列超 6 张则列主吞前 5 张。十轮后牛头最少者胜。",
        "davinci": "每人按数字升序竖一排牌(0~11，另有 2 张黑色反间谍，猜它须按“黑”才中)、露一张。"
                   "轮流摸 1 张(可选明/暗)并按值插位，随后可猜一位对手手牌的数字——猜中该牌翻开(永久"
                   "公开)、猜错则自己刚摸的牌翻开。所有牌被翻开的玩家出局，最后存活者胜。",
        "kalah": "每人 6 洞+右侧库，每洞开局 4 子。轮到选己方 1~6 号洞，取走全部子逆时针逐洞各落"
                 "1 子(跳过对手库)。落进自己库可再走一次；最后落进己方空穴且对侧穴有子，则连同对侧穴"
                 "的子一起收入自己库。某方洞穴全空即终局，剩余子全入对方库，比库中石子数，多者胜。",
        "lovelove": "每个骑士递情书，逐人被淘汰。每人 1 张暗牌，回合摸 1 张再弃 1 张触发效果："
                    "护卫(1)猜中即淘汰、王子(5)令一人弃抽、国王(6)交换手牌、伯爵夫人(7)净有 7+8 须弃、"
                    "公主(8)出局。只剩 1 人胜；牌堆摸玩则比手牌点数，大者胜。",
        "halloween": "桌游为经典“德国心脏病”的慢棋改编：5 种水果、每人一组牌。回合必先翻 1 张上桌，"
                     "某水果累计到恰 5 张即可“拍铃”，收走桌面所有牌计分并再走一次；若没凑齐 5 却不慎"
                     "拍铃则扣 1 分。有人翻完手牌即按收牌张数结算，多者胜。",
        "tictactoe": "3x3 棋盘，两人轮流落子，横/竖/斜先连成一直线者胜；棋盘下满无人连线则平局。",
        "halma": "9x9 星盘，四角各一个营区（2~4 人各占一角）。轮到你就把己方一枚棋子直移一格，"
                 "或隔一颗棋子跳到其后空格（可跳自己或对方子）。目标是把己方全部棋子搬进对角营区，"
                 "全队先抵达对岸者胜——对弈双方相向而行。",
        "checkers": "8x8 棋盘双方各 12 子，只能斜向前进一格、斜跳吃子（休闲版不强制多吃）；"
                    "到达底线升王，王可斜走任意格。把对方子吃光或令其无路可走者胜。",
        "blokus": "20x20 棋盘 2~4 人，轮流放置自己的 21 块角斗方块。首块须触及棋盘一角，之后每块须"
                   "至少一格与己方块「角对角」相连、且不得与己方块同边相邻（只角连）。全部放完或无人"
                   "可放即终局，剩余格子越少者胜——铺得越满越好。",
        "ludo": "4 色各 4 架机，掷骰(1~6)前进，掷 6 才可起飞且可再掷。沿 40 格轨道绕行一圈，"
        "踩着他人就把其送回机棚。先把 4 架机全部飞到终点的玩家胜。",
        "xiangqi": "红方在下、黑方在上，9x10 棋盘。棋子走法：将帅只走九宫内一步、仕走九宫斜格、"
                   "象走田不可过河且塞象眼被挡、马走日忌蹩马腿、车走直线、炮平移被挡时隔山打吃、"
                   "兵/卒过河前只能向前、过河后可横一。任何一步结束不得让己方将帅被将军（含飞将）"
                   "；将死对方或将对方逼到无棋可动即获胜。",
        "chess": "白方先行。兵直进斜吃、首步可两格、可吃过路兵与升变；车/象/后直线/斜线走，"
                  "马走日、王走一格并支持王车易位。任何一步不得让己方王处于被将军；"
                  "将死对方获胜，对方无子可动(不被将)则平局。",
        "go": "9x9 棋盘，黑白轮流在空位落子。相邻同色连成团，团无「气」(贴邻空点)即被提掉；"
               "不允许自杀落点，且禁止立即复原成前一手棋局面的打劫提回。双方都可选择「过」，"
               "连续两次过即终局：按各色子数 + 被该色完全包围的空地目数合计，目数多者胜。",
        "shogi": "9x9。玉将/飞车/角行/金/银/桂/香/步兵。被吃掉的子进入持子，可任一己方回合一手"
                  "打入空位。深入对方后三排时步兵/香/桂/银升为金，飞车成龙、角行成马。"
                  "吃掉对方玉将即获胜。",
        "junqi": "5x10 棋盘分上下两半场，双方各 25 子明棋布阵。军衔：司令>军长>师长>旅长>团长>"
                  "营长>连长>排长>工兵；炸弹与任何子相遇同归于尽；地雷不可动，仅工兵能挖、其余子"
                  "撞地雷牺牲；军旗不可动。每手把己方子（地雷、军旗除外）移相邻一格；占领对方军旗"
                  "格即获胜。",
        "dou": "7x9 棋盘。象>狮>虎>豹>狼>狗>猫>鼠，鼠吃象；狮虎可隔河竖跳（河中有鼠则不可跳）"
                "，鼠可入河。落入敌方陷阱会被弱化（此处简化不启用）。直接冲进对方营（大本营）即"
                "获胜。",
        "onewolf": "一夜终极狼人简化版。开局每人发身份（狼人/预言家/强盗/失眠者/村民）。夜晚预言家"
                    "可偷看一人或中心两张、强盗可与一人换牌并查看自己身份；狼人们互相知晓队友。"
                    "随后全体投票处决一人（平票无人出局）。若所有狼人都被票死则好人胜，否则狼人胜。",
        "werewolf": "经典狼人杀（多夜多日）。身份：预言家(每晚验一人)、狼人(夜晚刀一人)、女巫(解药救一人/"
                    "毒药毒一人，各一次)、猎人(死亡可开枪带走一人，被毒死除外)、村民。"
                    "夜晚按预言家→狼人→女巫顺序行动，天亮结算死伤；白天讨论后全员投票放逐一人。"
                    "狼人全灭则好人胜；存活好人不多于存活狼人则狼人胜。",
        "avalon": "团队任务推理。好人：梅林(开眼知晓所有叛军但须隐藏)、亚瑟忠臣；坏人：刺客、莫德雷德。"
                    "每轮领袖提名团队(成员数按人数定)，全体投票通过/否决(否决换领袖重提)。团队每人秘密出"
                    "任务 成功/失败，一次失败即任务失败。积累 3 次成功：刺客指认梅林，指对则坏人胜；"
                    "积累 3 次失败：坏人直接胜。",
        "liar": "每人手牌为暗牌的 0~9（可重复）。轮流把一张牌扣到桌中央并公开报数——虚报或实报随你。"
                    "下一位可再出牌，也可挑战你上一位的报数：若被挑战的牌真值与报数一致，猜错者喝；"
                    "不一致则报数者被戳穿喝。每人喝满 3 杯出局，最后留在桌上的玩家获胜。",
        "ninja": "每位忍者每轮秘密选择「攻击」(指定一名存活目标) 或「防御」。同时结算："
                    "攻击对象本回合在防御，则攻击者反被反伤 1 血；否则目标掉 1 血；互相攻击则双方皆伤。"
                    "生命 3 格，归零出局。最后存活者获胜。",
        "coc": "克苏鲁呼唤规则判定器。开局每人从 6 张调查员卡选一张（如侦探/医生/记者），注明属性"
               "与常用技能值。房主作为 KP 讲述自由剧情并推进场景，任一玩家可随时用「检定」发起一次"
               " d100 技能判定（输入技能名，取该卡技能值，未知技能按 50 基准）。判定按 COC 表给出"
               " 大成功(≤5)/极难成功(≤20)/困难成功(≤50)/普通成功(≤技能值)/失败/大失败(≥96且>技能值)。"
               "公开快照只公告「谁对什么检定→级别」，你的角色属性与技能值仅自己可见。KP 还可用"
               "「剧情」更新场景文案、用「结束」收尾本局。",
        "balatro": "小丑牌·多人生存版（梭哈摸式）。开局每人在标准 52 张牌库中摸满 8 张，另随机获得 2 张"
               "常驻小丑牌（被动加成，如对子×2 / 同花×3 / 红心+30 等）。轮流行动：可把手牌中任意牌"
               "「选中」加入出战区（每回合最多 5 张）、可「取消选中」、可「弃牌」一张并立即补抽（每回合"
               "最多 3 次，兑现保留/重抽）、凑好牌型后「出牌」结算——按同花/顺子/同花顺/四条/葫芦等"
               "计分并乘以小丑牌加成。每盲注每人最多出牌 2 手，累计筹码 ≥ 盲注目标则过本盲注（回血 5），"
               "否则流血。生命 40 归零出局，打满 8 个盲注或只剩一人时，存活血量最高者获胜。",
        "balatro_solo": "经典单人闯关，贴近原作 Balatro 四机制：①盲注节奏——1 Ante=小盲→大盲→BOSS"
               "三连一组（倍率 1/1.6/2.2），最多 6 组共 18 桥，每桥有专属目标分。②计分链——手牌 8 张，"
               "每盲注选 ≤5 张出战、限出 4 手、可弃牌补抽 ≤3 次；牌型给基础 (chips,mult)，小丑牌叠加成"
               "（牌型类 ×mult / 花色类 +chips），总分 = chips × mult 累加。③强化层——每张牌可挂 版本(箔饰/"
               "全息/多彩)/增强(宝珠/曙光/节庆/琉璃/磐石/钢印)/封印(赤/金/紫) 之一；牌型可用星球升级(+chips/mult)。"
               "④商店经济——开局 4 金币，过关得金币(小盲3/大盲4/Boss6)，两桥之间进商店：买 Joker/消耗品或"
               "刷新。消耗品 2 槽：塔罗改造手牌、星球升牌型、灵体高风险高回报。总分 ≥ 桥目标则过关进商店，"
               "否则扣 1 命（共 3 命）。命归零结束或打通 18 桥获胜。",
    }.get(name, "")


GAME_TYPES = {
    cls.name: cls
    for cls in (GuessNumberGame, GomokuGame, RpsGame, SpyGame, UnoGame,
                BlackjackGame, DrawGuessGame, Connect4Game, OthelloGame,
                Calc24Game, MatchPairsGame, BetrayalGame,
                KaituoGame, LingdiGame, TieluGame, GongfangGame,
                ChengZhuGame, GemCityGame, SijiGame, BolanGame,
                AzulGame, RummikubGame, YahtzeeGame, NimmtGame,
                DaVinCiGame, KalahGame, LoveLoveGame, HalloweenGame,
                TicTacToeGame, HalmaGame, CheckersGame, BlokusGame, LudoGame,
                XiangQiGame, ChessGame, GoGame, ShogiGame,
                JunqiGame, DouGame,
                OneNightWolfGame, WerewolfGame, AvalonGame,
                LiarGame, NinjaNightGame, CocGame, BalatroGame,
                BalatroSoloGame)
}

GAME_META = {
    name: {"min": cls.min_players, "max": cls.max_players, "label": _label(name),
           "desc": _desc(name), "rules": _rules(name)}
    for name, cls in GAME_TYPES.items()
}
