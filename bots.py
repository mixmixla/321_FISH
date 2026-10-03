# -*- coding: utf-8 -*-
"""R35 内置 Bots：骰子 / 回声 / 提醒（纯标准库，服务器进程内运行）。

- BotDef.uid 使用 900+ 高位段，与真实用户 uid（1 起自增）隔离；
  老客户端把 bot 消息当普通 CHAT 渲染（无需升级）
- Hub 侧把 bot 注册进 known/roster（type="bot"，永远在线）；
  dispatch 拦截发往 bot 的私聊 → 命令解析 → bot 经 bus.publish 正常回复
- 提醒 bot：解析「HH:MM 内容」，由 Hub sweeper 到期推送（内存态，重启失效）
- R46：命令注册表（commands）+ inline 键盘（kb）——bot 回复可携带按钮行
  [{t:标签,c:指令}]，客户端点按钮=向 bot 发送 c 文本；kb 只是 CHAT 消息
  上的可选字段，随历史/路由/R16 快照自然走，帧协议零改动，老客户端
  忽略未知字段照常渲染文本。
"""
import random
import re
import time

BOT_UID_BASE = 900            # bot 高位段起点（真实 uid 从 1 自增，永不冲突）

_RE_DICE = re.compile(r"[dD](\d{1,4})")            # 支持 "d20" / "2d20"（取后者面数）
_RE_ROLL = re.compile(r"(?:掷骰|摇骰|骰子|roll)\s*([dD]?\d{0,4})")
_RE_REMIND = re.compile(r"^(\d{1,2}):(\d{2})\s+(.+)$")   # 「HH:MM 内容」


def kb_rows(buttons, per_row: int = 3) -> list:
    """按钮列表 → 分行键盘 [[{t,c},...],...]（TG 风格，t=标签 c=点击发送的指令）。"""
    buttons = [(str(t), str(c)) for t, c in buttons]
    return [[{"t": t, "c": c} for t, c in buttons[i:i + per_row]]
            for i in range(0, len(buttons), per_row)]


def help_kb(bot) -> list | None:
    """bot 的「帮助」键盘：每个注册命令一枚按钮（点=发送该命令）。"""
    if not bot.commands:
        return None
    return kb_rows([(cmd, cmd) for cmd, _d in bot.commands])


class BotDef:
    def __init__(self, uid: int, nick: str, desc: str, handle,
                 commands: list | None = None):
        self.uid = uid
        self.nick = nick
        self.desc = desc
        self.handle = handle            # handle(hub, msg) -> list[str | (str, kb)]
        self.commands = [(str(c), str(d)) for c, d in (commands or [])]


def _handle_dice(hub, msg: dict) -> list:
    text = (msg.get("text") or "").strip()
    if text in ("帮助", "help", "?", "？"):
        return [("🎲 点下方按钮掷骰，或直接发送「骰子 / d20 / d100」",
                 help_kb(BOT_DICE))]
    m = _RE_DICE.fullmatch(text)                  # 「d20」整条即骰指令
    if m:
        faces = max(2, min(1000, int(m.group(1))))
    else:
        m = _RE_ROLL.search(text)
        faces = 6
        if m and m.group(1):
            dm = _RE_DICE.fullmatch(m.group(1))
            if dm:
                faces = max(2, min(1000, int(dm.group(1))))
    roll = random.randint(1, faces)
    return [f"🎲 {msg.get('nick', '?')} 掷出了 {roll} / {faces}"]


def _handle_echo(hub, msg: dict) -> list:
    text = (msg.get("text") or "").strip()
    if not text or text == "帮助":
        return [("回声机器人：把你说的话原样说一遍（内容不出本机）",
                 help_kb(BOT_ECHO))]
    return [f"🔁 {text}"]


def _handle_remind(hub, msg: dict) -> list:
    text = (msg.get("text") or "").strip()
    m = _RE_REMIND.match(text)
    if not m:
        return [("提醒助手：发送「HH:MM 内容」设置提醒（如「14:30 开会」），"
                 "或点下方按钮示例", help_kb(BOT_REMIND))]
    hh, mm, note = int(m.group(1)), int(m.group(2)), m.group(3).strip()
    if not (0 <= hh <= 23 and 0 <= mm <= 59) or not note:
        return [("提醒助手：时间格式不对，示例「14:30 开会」",
                 help_kb(BOT_REMIND))]
    now = time.localtime()
    due = time.mktime((now.tm_year, now.tm_mon, now.tm_mday, hh, mm, 0, 0, 0, -1))
    if due <= time.time():
        due += 86400                     # 已过 → 明天同一时间
    enqueue = getattr(hub, "_bot_reminder_enqueue", None)
    if enqueue is not None:
        enqueue(msg["uid"], due, note, BOT_REMIND.uid)
    else:
        hub.bot_reminders.append({"uid": msg["uid"], "due": due, "text": note,
                                  "bot_uid": BOT_REMIND.uid})
    return [f"⏰ 已设置提醒：{time.strftime('%H:%M', time.localtime(due))} {note}"]


BOT_DICE = BotDef(BOT_UID_BASE + 1, "骰子娘", "发「骰子」或「d20」掷骰",
                  _handle_dice,
                  commands=[("骰子", "掷一枚 d6"), ("d20", "掷一枚 d20"),
                            ("d100", "掷一枚 d100")])
BOT_ECHO = BotDef(BOT_UID_BASE + 2, "回声机器人", "原样复读你说的话",
                  _handle_echo,
                  commands=[("帮助", "用法说明")])
BOT_REMIND = BotDef(BOT_UID_BASE + 3, "提醒助手", "发「HH:MM 内容」定时提醒",
                    _handle_remind,
                    commands=[("帮助", "用法说明"), ("9:00 站会", "示例：定时提醒")])

BOTS = [BOT_DICE, BOT_ECHO, BOT_REMIND]

# 阶段④：Agent 助手（把 324 的深度研究/编码能力以 MCP 接进聊天）。
# 懒加载 get_agent_bot() 打破与 agent_bot 的环形依赖；324 不在时优雅降级。
try:
    from agent_bot import get_agent_bot    # noqa: F401
    BOTS.append(get_agent_bot())
except Exception:
    pass                                   # 无 324 → 不注册 Agent bot

BOT_BY_UID = {b.uid: b for b in BOTS}


def is_bot(uid) -> bool:
    try:
        return int(uid) in BOT_BY_UID
    except (TypeError, ValueError):
        return False


def sweep_reminders(hub) -> None:
    """由 Hub sweeper 周期调用：到点提醒 → bot 经 bus.publish 推给用户。"""
    now = time.time()
    take_due = getattr(hub, "_bot_reminder_take_due", None)
    if take_due is not None:
        due = take_due(now)
    else:
        due = [r for r in hub.bot_reminders if r["due"] <= now]
        if not due:
            return
        hub.bot_reminders = [r for r in hub.bot_reminders if r["due"] > now]
    if not due:
        return
    for r in due:
        bot = BOT_BY_UID.get(r["bot_uid"])
        if bot:
            hub.bot_say(bot, r["uid"], f"⏰ 提醒：{r['text']}",
                        owner_uid=r["uid"], source_kind="reminder")
