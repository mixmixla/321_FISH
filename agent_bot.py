# -*- coding: utf-8 -*-
"""324 Agent 宿主 Bot（阶段④）：把 04_mcp_im 的 MCP 工具接进聊天。

接入方式：向 bots.py 提供 `get_agent_bot()` 单例（BotDef）。命令：
  - `研究…` → research_resolve（① 深度研究）
  - `写代码…` → coding_run（③ 迷你 Coding Agent）
  - `帮助` / `?` → inline 键盘
执行放后台线程避免阻塞收包循环；结果经 hub.bot_say 以私聊回传（含 inline 键盘）。

纯标准库约束：宿主侧只 import subprocess/json/threading/pathlib——真正依赖官方
`mcp` 的是 ④ 的 server 子进程（stdio transport），本文件只负责拉起并消费。若
324 项目目录不存在，bot 优雅降级为提示消息，不影响聊天。

注意：为避免与 bots.py 环形导入（bots 需要本模块的 bot，本模块又要用 bots 的
BotDef/help_kb），这里不在模块顶层 import bots，全部经 `get_agent_bot()` 懒加载；
bots.py 也只在自身加载到最末时再取 bot。
"""
import sys
import threading
import traceback
from pathlib import Path


def _bots():
    import bots   # 懒加载，打破 bots↔agent_bot 环形依赖
    return bots


def _has_adapter() -> bool:
    try:
        import importlib
        importlib.import_module("04_mcp_im.adapter")
        return True
    except Exception:
        return False


def _adapter_answer(text: str, mock: bool) -> str:
    import importlib
    mod = importlib.import_module("04_mcp_im.adapter")
    return mod.answer(text, mock=mock)


def _label(text: str) -> str:
    return "深度研究" if text.lstrip("/")[:2] in ("研究", "查", "搜索") else "编码任务"


def _dispatch(hub, msg: dict) -> list:
    """研究 / 写代码 / 帮助 三分支；真实指令在后台线程跑。"""
    available = getattr(hub, '_service_available', None)
    if available is not None and not available():
        return ["服务器正在停止，请重新连接后再试。"]
    text = (msg.get("text") or "").strip()
    bot = get_agent_bot()

    if text in ("帮助", "help", "?", "？") or text == "Agent":
        return [("🤖 Agent 助手（阶段④：把深度研究 & 编码能力标准 MCP 化并接入聊天），"
                 "发送「研究/写代码 + 一句话」即触发；点下方按钮试玩",
                 _bots().help_kb(bot))]

    if not (_324_ROOT.exists() and _has_adapter()):
        return [("🤖 检测不到 324 项目（01_deep_research / 03_coding_agent / "
                 "04_mcp_im），Agent 能力不可用；请先配置后重试。")]

    # 立即回一条"开工中"，真实 LLM 执行放后台线程
    arguments = {"hub": hub, "text": msg.get("text", ""),
                 "to_uid": msg.get("uid"), "owner_uid": msg.get("uid"),
                 "source_kind": "agent", "request_seq": msg.get("seq")}
    start = getattr(hub, '_start_worker', None)
    if start is not None:
        if start(_run_async, kwargs=arguments, name='agent-bot') is None:
            return ["服务器正在停止，请重新连接后再试。"]
    else:
        threading.Thread(target=_run_async, kwargs=arguments, daemon=True).start()
    return [f"🤖 收到，正在 {_label(text)}…（结果稍后以消息回传）"]


def _run_async(hub, text: str, to_uid, *, owner_uid=None,
               source_kind="agent", request_seq=None) -> None:
    """后台线程：调 04 的 MCP 工具，结果经 bot_say 回传给发送者。"""
    try:
        result = _adapter_answer(text or "写代码：演示一个加法脚本", _MOCK)
        out = result or "（Agent 返回为空）"
        hub.bot_say(get_agent_bot(), to_uid, out,
                    owner_uid=owner_uid if owner_uid is not None else to_uid,
                    source_kind=source_kind, request_seq=request_seq)
    except Exception:
        hub.bot_say(get_agent_bot(), to_uid,
                    f"🤖 Agent 执行失败：\n{traceback.format_exc()[-600:]}",
                    owner_uid=owner_uid if owner_uid is not None else to_uid,
                    source_kind=source_kind, request_seq=request_seq)


def get_agent_bot():
    """懒加载式单例：返回阶段④的 Agent BotDef（供 bots.py 注册）。"""
    global _BOT_AGENT
    if _BOT_AGENT is None:
        b = _bots()
        _BOT_AGENT = b.BotDef(
            b.BOT_UID_BASE + 9, "Agent助手", "研究/写代码能力（阶段④ MCP 接入）",
            _dispatch,
            commands=[("研究 量子纠缠", "深度研究一个主题"),
                      ("写代码 写一个加法脚本并验证", "跑一遍迷你 Coding Agent"),
                      ("帮助", "用法说明")])
    return _BOT_AGENT


# 324 四件套顶层根（如存在）：learn_demos/324_Agent四件套_网关研究编程MCP
_LEARN = Path(__file__).resolve().parent.parent               # learn_demos
_324_ROOT = _LEARN / "324_Agent四件套_网关研究编程MCP"
_MOCK = not _324_ROOT.exists()
if _324_ROOT.exists():
    sys.path.insert(0, str(_324_ROOT))   # 让 `04_mcp_im` 作为顶层包可 import

_BOT_AGENT = None
