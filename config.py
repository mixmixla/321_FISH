# -*- coding: utf-8 -*-
"""321 · 局域网摸鱼助手 —— 集中配置（CFG 单例）"""
import os
import sys
import traceback
from dataclasses import dataclass, field

APP_NAME = "内部办公助手"          # 对外显示的"无害"名称，绝不出现"摸鱼/聊天"字样
PROTOCOL_VERSION = 1

# ---- 网络 ----
TCP_PORT = int(os.environ.get("MOYU_TCP_PORT", "9527"))     # 可改高位非常规端口，减少指纹
UDP_PORT = int(os.environ.get("MOYU_UDP_PORT", "9528"))     # 自动发现广播端口
UDP_BROADCAST_INTERVAL = 3.0                                # 服务器广播间隔（秒）
UDP_CANDIDATE_TTL = 10.0                                    # 客户端候选服务器过期（秒）
HEARTBEAT_INTERVAL = 15.0                                   # 客户端 ping 间隔
HEARTBEAT_TIMEOUT = 45.0                                    # 服务器 45s 无收包踢人
ZOMBIE_WEB_IDLE = 30.0               # R47：web 会话 30s 无 touch 视为僵尸（登录同名时立即释放；
                                     # 活会话 SSE 每 15s 必 touch，不会误伤）
CLIENT_IDLE_TIMEOUT = 60.0                                  # 客户端 60s 无帧判断线
RECONNECT_BASE = 1.0                                        # 重连退避基数
RECONNECT_MAX = 10.0                                        # 重连退避上限

# ---- 封帧防护 ----
MAX_HEADER_BYTES = 64 * 1024
MAX_BODY_BYTES = 1 * 1024 * 1024   # 1MB（文件块 64KB 远低于此）

# ---- 加密层 ----
OBFUSCATE_PREFIX_LEN = 64          # 混淆前缀长度（模仿 MTProto obfuscated2 首段）
PAD_TO = 256                        # JSON 体随机填充对齐（反指纹）
PADDING_MIN = 32                    # 每次最少随机填充字节

# ---- 文件传输 ----
CHUNK_SIZE = 64 * 1024              # 64KB 块
FILE_ACK_TIMEOUT = 10.0             # ACK 超时重发
FILE_MAX_RETRY = 3                  # 单块最大重发次数
FILE_DIRECT_TIMEOUT = 3.0           # P2P 直连握手/连接超时（失败自动回退服务器中转）
FILE_GRACE_SECONDS = 600            # 服务器"等待接受"的 offer 记录超时清理（防僵尸泄漏）
TCP_IDLE_SECONDS = 600             # 半开 TCP 连接读超时：客户端不发数据也不断开时回收线程
HANDSHAKE_TIMEOUT = 10.0           # 加密握手读超时：防半开客户端只发混淆前缀后卡住，泄漏服务器线程
FILE_MAX_SIZE = 4 * 1024 ** 3       # 单文件接收大小上限（4GB，防恶意超大 offer 撑爆磁盘）
DOWNLOADS_DIR = "downloads"         # 接收端下载目录（相对用户目录）

# ---- 游戏 ----
GAME_AUTO_TICK = 0.5                # 服务器游戏定时推进 tick（秒）
GUESS_NUM_ROUND_GAP = 3.0           # 猜数字局间间隔
RPS_COLLECT_TIMEOUT = 15.0          # 石头剪刀布提交超时
UNO_TARGET_SCORE = 100              # UNO 先到该分赢得比赛
UNO_ENFORCE_WILD4 = True            # 万能+4 限手中无当前色才可出（房规开关）
SPY_WORD_PAIRS = 24                 # 谁是卧底内置词组数量

# ---- 快速隐藏 ----
HOTKEY_MODS = 0x1 | 0x2             # MOD_ALT | MOD_CONTROL
HOTKEY_VK = 0x48                    # H 键
HOTKEY_ID = 0x1337
BOSS_TITLE_POOL = [
    "部门预算表_2026Q3.xlsx - Excel",
    "年度绩效汇总_v7.xlsx - Excel",
    "周报数据透视_0926.xlsx - Excel",
]
BOSS_ALIVE_INTERVAL = 3.0           # 假工作窗"活"更新间隔
# R69A：多套伪装皮肤（老板键一键轮换；标题池随机取一个像真的文件名）
BOSS_SKINS = ("excel", "vscode", "terminal", "ppt", "mail")
BOSS_SKIN_LABELS = {
    "excel": "📊 假 Excel",
    "vscode": "🧩 假 VS Code",
    "terminal": "⌨ 假 PowerShell",
    "ppt": "📽 假 PowerPoint",
    "mail": "✉ 假 Outlook",
}
BOSS_SKIN_TITLES = {
    "excel": BOSS_TITLE_POOL,
    "vscode": [
        "app.py - 项目A - Visual Studio Code",
        "server.py - 项目A - Visual Studio Code",
        "index.ts - 前端工程 - Visual Studio Code",
    ],
    "terminal": [
        "管理员: Windows PowerShell",
        "Windows PowerShell",
        "命令提示符",
    ],
    "ppt": [
        "Q3经营分析.pptx - PowerPoint",
        "产品规划_v4.pptx - PowerPoint",
        "述职汇报_终版.pptx - PowerPoint",
    ],
    "mail": [
        "收件箱 - Outlook",
        "邮件 - Outlook",
        "已发送邮件 - Outlook",
    ],
}

# ---- R46 伪装包：主窗/托盘/任务栏标题预设（"" = 关闭伪装用默认名） ----
CAMO_PRESETS = [
    ("关闭", ""),
    ("Excel", "Book1 - Excel"),
    ("记事本", "无标题 - 记事本"),
    ("计算器", "计算器"),
]

# ---- 聊天与历史 ----
SERVER_HISTORY_MAX = 300            # 服务器每频道内存环形保留条数（内容不落盘，到期自然淘汰）
CHAT_TEXT_MAX = 2000                # 单条消息文本上限（字符）
BURN_TTL = 600                      # 阅后即焚兜底：单条消息最长存活秒数（无人读到也删）
DRAFT_TTL = 86400                   # R29B 草稿同步：服务器内存草稿最长保留秒数（24h，与投票默认期同级）
WEB_PORT = int(os.environ.get("MOYU_WEB_PORT", "9529"))     # 网页端聊天端口
WEB_PASSWORD = os.environ.get("MOYU_WEB_PASSWORD", "")      # 网页端访问口令（空=局域网免密）
WEB_IDLE_TIMEOUT = 300.0            # 网页会话 5 分钟无请求判定离线
GROUP_MAX_MEMBERS = 64              # 单群人数上限
GROUP_NAME_MAX = 16                 # 群名长度上限
GROUP_ABOUT_MAX = 80                # R9H 群简介长度上限（字符）
GROUP_MUTE_DEFAULT = 600            # 群内一键禁言默认时长（秒，10 分钟）
VOICE_MAX_DUR = 30.0                # 单条语音最长时长（秒，超长截断）
VOICE_TTL = 600                     # 服务器内存中语音二进制体保留秒数（过期后仅墓碑）
WEB_FILE_MAX = 20 * 1024 * 1024     # 网页端单文件上传上限（20MB，防撑爆磁盘）
WEB_FILES_DIR = "web_files"         # 网页端文件存储目录（相对运行目录）
STICKER_MAX_BYTES = 512 * 1024      # R30C 自定义贴纸单张图片上限（512KB，防撑爆）
GROUP_FILE_MAX_BYTES = 32 * 1024 * 1024   # 群文件库单文件上限（32MB，防撑爆磁盘）

# ---- R71 语音转写内置（vosk + 中文小模型随包）----
STT_MODEL_SUBDIR = os.path.join("models", "vosk")   # 内置模型在包内/用户目录下的相对路径
STT_MODEL_DEFAULT = "vosk-model-small-cn-0.22"      # 随包中文小模型（~40MB）
STT_MODEL_URL = "https://alphacephei.com/vosk/models"   # 模型下载页（供提示文案引用）

# ---- R72 多人语音房 / 位置共享 / 圆形视频留言 ----
VOICE_ROOM_MAX = 6                  # 单语音房人数上限（mesh 全互联，端口数 = N-1）
GEO_NAME_MAX = 64                   # 位置卡片地点名长度上限（字符）
GEO_LIVE_INTERVAL = 30.0            # 实时位置刷新间隔（秒）
GEO_LIVE_TTL = 300.0               # 实时共享最长时长（秒，5 分钟）
VMEMO_MAX_BYTES = 900 * 1024        # 单条视频留言容器上限（900KB，防撑爆内存）
VMEMO_TTL = 600                     # 服务器内存中视频留言二进制体保留秒数（同语音消息）
VMEMO_MAX_DUR = 5.0                 # 视频留言最长时长（秒，超长截断）
VMEMO_MAX_FPS = 8                   # 视频留言帧率上限（帧/秒）

# ---- R52 头像与个人资料（昵称=登录标识不可改）----
AVATAR_MAX_BYTES = 1024 * 1024      # 头像单张图片上限（1MB，防撑爆磁盘）
AVATAR_EXTS = ("png", "jpg", "jpeg", "gif", "webp", "bmp")
SIGN_MAX_LEN = 60                   # 个性签名最大长度（字符）

# ---- R53 服务器管理员（最高清理权限；昵称/密码固定，不可被占用或修改）----
ADMIN_NICK = "L57"                  # 管理员昵称（登录标识）
ADMIN_PWD = "L57"                   # 管理员密码（固定；登录时强制校验，其他人无法冒用）

# ---- 审计 ----
AUDIT_DIR = "audit"                 # 审计日志目录（相对运行目录；exe 运行时落到用户目录）
AUDIT_KEEP_DAYS = 7                 # 按天轮转，仅保留最近 N 天（留底复盘）
SWEEP_INTERVAL = 1.0                # 服务器心跳清扫间隔（秒）

# ---- 服务器全状态持久化（R16：重启不丢）----
PERSISTENCE_DIR = "server_state"    # 全状态快照目录（单文件 state.json 原子替换）
PERSIST_INTERVAL = 0.2              # 变更写盘节流窗口（秒）：合并突发写

# ---- 投票（R26A）----
POLL_OPTIONS_MAX = 10               # 单投票最多选项数
POLL_OPTION_LEN = 64                # 单个选项最长字符
POLL_QUESTION_MAX = 200             # 投票问题最长字符
POLL_DEFAULT_TTL = 86400            # 投票默认截止时长（秒，24h 后自动结束）

# ---- 链接预览（R26D，服务器出网拉取）----
PREVIEW_TIMEOUT = 3.0               # 单次抓取超时（秒）
PREVIEW_MAX_BYTES = 512 * 1024      # 抓取响应体上限（防撑爆内存）
PREVIEW_TTL = 3600                  # URL 预览缓存时长（秒）
PREVIEW_TITLE_MAX = 200             # title/description 截断长度

# ---- 客户端 ----
WINDOW_W, WINDOW_H = 820, 620       # 聊天主窗（Apple 风格加宽加高，留更多白）
MINI_W, MINI_H = 180, 36            # 迷你条尺寸
CHAT_HISTORY_MAX = 500              # 聊天消息内存上限
FONT_FAMILY = "Segoe UI"            # Apple SF Pro 的 Windows 最近似字体
FONT_SIZE = 10                       # Apple 风格略大字号（原 9pt 偏小）
MAX_NICK_LEN = 20


def _log_dir() -> str:
    """日志/下载目录：exe 运行时取可写用户目录，脚本运行时取项目目录"""
    if getattr(sys, "frozen", False):
        base = os.path.join(os.path.expanduser("~"), "moeyu_helper")
        os.makedirs(base, exist_ok=True)
        return base
    return os.path.dirname(os.path.abspath(__file__))


def crash_log_path() -> str:
    """R48：原生崩溃/卡死堆栈日志路径（与历史/下载同级的可写目录）"""
    return os.path.join(_log_dir(), "crash.log")


_crash_log_fh = None              # 持有文件对象防 GC 关闭（faulthandler 需要 fd 存活）
_MAX_CRASH_LOG = 4 * 1024 * 1024  # crash.log 轮转阈值：超过后归档为 crash.log.1


def _open_crash():
    """打开 crash.log（追加）；超过阈值先轮转，防止长期运行无限膨胀。"""
    global _crash_log_fh
    path = crash_log_path()
    try:
        if os.path.exists(path) and os.path.getsize(path) > _MAX_CRASH_LOG:
            old = path + ".1"
            if os.path.exists(old):
                os.remove(old)
            os.replace(path, old)              # 同目录原子轮转
    except Exception:
        pass
    _crash_log_fh = open(path, "a", encoding="utf-8", errors="replace")


def _crash_write(text: str) -> None:
    """向 crash.log 追加一行；_crash_log_fh 未开则由 enable_crashlog 兜底开启"""
    global _crash_log_fh
    try:
        if _crash_log_fh is None or _crash_log_fh.closed:
            _open_crash()
        _crash_log_fh.write(text)
        _crash_log_fh.flush()
    except Exception:
        pass


def bootlog(msg: str) -> None:
    """启动里程碑日志：crash.log 里带 [boot] 标记，便于判断 exe 起没起来、卡在哪段"""
    _crash_write(f"[boot] {msg}\n")


def enable_crashlog() -> None:
    """R48：启动日志。原生崩溃（访问违例/断言/fatal 信号）用 faulthandler 堆栈
    追加写 crash.log；同时兜底 Python 未捕获异常与 Tk 回调异常也写进去——
    --windowed 打包下 sys.stdout 为 None，异常会被静默吞掉导致"双击没反应"，
    有这条 traceback 才能定位。任何异常静默不影响启动。"""
    global _crash_log_fh
    try:
        import faulthandler
        if _crash_log_fh is None or _crash_log_fh.closed:
            _open_crash()
        faulthandler.enable(file=_crash_log_fh, all_threads=True)
        _crash_write(f"[boot] enable_crashlog pid={os.getpid()}\n")

        def _hook(exc_type, exc, tb):
            _crash_write("".join(traceback.format_exception(exc_type, exc, tb)))

        sys.excepthook = _hook
        try:                                     # --windowed 下 Tk 回调异常同样落盘
            import tkinter
            tkinter.Tk.report_callback_exception = staticmethod(_hook)
        except Exception:
            pass
    except Exception:
        pass


@dataclass
class Cfg:
    """全局配置单例"""
    tcp_port: int = TCP_PORT
    udp_port: int = UDP_PORT
    udp_broadcast_interval: float = UDP_BROADCAST_INTERVAL
    udp_candidate_ttl: float = UDP_CANDIDATE_TTL
    chunk_size: int = CHUNK_SIZE
    downloads_dir: str = field(default_factory=lambda: os.path.join(_log_dir(), DOWNLOADS_DIR))
    file_direct_timeout: float = FILE_DIRECT_TIMEOUT
    file_ack_timeout: float = FILE_ACK_TIMEOUT
    file_max_retry: int = FILE_MAX_RETRY
    file_grace_seconds: float = FILE_GRACE_SECONDS
    tcp_idle_seconds: float = TCP_IDLE_SECONDS
    handshake_timeout: float = HANDSHAKE_TIMEOUT
    file_max_size: int = FILE_MAX_SIZE
    # 聊天/群聊/网页端
    server_history_max: int = SERVER_HISTORY_MAX
    chat_text_max: int = CHAT_TEXT_MAX
    burn_ttl: float = BURN_TTL
    draft_ttl: float = DRAFT_TTL        # R29B：服务器内存草稿保留时长（秒）
    web_port: int = WEB_PORT
    web_password: str = WEB_PASSWORD
    web_idle_timeout: float = WEB_IDLE_TIMEOUT
    group_max_members: int = GROUP_MAX_MEMBERS
    group_name_max: int = GROUP_NAME_MAX
    group_about_max: int = GROUP_ABOUT_MAX           # R9H 群简介最大长度
    voice_max_dur: float = VOICE_MAX_DUR
    voice_ttl: float = VOICE_TTL
    group_mute_default: int = GROUP_MUTE_DEFAULT
    web_file_max: int = WEB_FILE_MAX
    web_files_dir: str = field(default_factory=lambda: os.path.join(_log_dir(), WEB_FILES_DIR))
    sticker_max_bytes: int = STICKER_MAX_BYTES   # R30C 自定义贴纸单张图片上限
    group_file_max_bytes: int = GROUP_FILE_MAX_BYTES   # 群文件库单文件上限
    avatar_max_bytes: int = AVATAR_MAX_BYTES     # R52 头像单张图片上限
    avatar_exts: tuple = AVATAR_EXTS              # R52 头像格式白名单
    sign_max_len: int = SIGN_MAX_LEN             # R52 个性签名最大长度
    admin_nick: str = ADMIN_NICK                 # R53 管理员昵称（登录标识）
    admin_pwd: str = ADMIN_PWD                   # R53 管理员密码（固定）
    # R72 多人语音房 / 位置共享 / 圆形视频留言
    voice_room_max: int = VOICE_ROOM_MAX         # 单语音房人数上限（mesh 全互联）
    geo_name_max: int = GEO_NAME_MAX             # 位置卡片地点名长度上限
    geo_live_interval: float = GEO_LIVE_INTERVAL  # 实时位置刷新间隔（秒）
    geo_live_ttl: float = GEO_LIVE_TTL           # 实时共享最长时长（秒）
    vmemo_max_bytes: int = VMEMO_MAX_BYTES       # 视频留言容器上限
    vmemo_ttl: float = VMEMO_TTL                 # 视频留言内存保留秒数
    vmemo_max_dur: float = VMEMO_MAX_DUR         # 视频留言最长时长（秒）
    vmemo_max_fps: int = VMEMO_MAX_FPS           # 视频留言帧率上限
    # 客户端本地历史
    chat_history_max: int = CHAT_HISTORY_MAX
    # 心跳/重连
    heartbeat_interval: float = HEARTBEAT_INTERVAL
    reconnect_base: float = RECONNECT_BASE
    reconnect_max: float = RECONNECT_MAX
    # 心跳/审计
    heartbeat_timeout: float = HEARTBEAT_TIMEOUT
    zombie_web_idle: float = ZOMBIE_WEB_IDLE   # R47：同名登录时僵尸 web 会话判定阈值
    sweep_interval: float = SWEEP_INTERVAL
    audit_dir: str = field(default_factory=lambda: os.path.join(_log_dir(), AUDIT_DIR))
    audit_keep_days: int = AUDIT_KEEP_DAYS
    # 服务器全状态持久化（R16）
    persistence_dir: str = field(
        default_factory=lambda: os.path.join(_log_dir(), PERSISTENCE_DIR))
    persist_interval: float = PERSIST_INTERVAL
    # 投票（R26A）
    poll_options_max: int = POLL_OPTIONS_MAX
    poll_option_len: int = POLL_OPTION_LEN
    poll_question_max: int = POLL_QUESTION_MAX
    poll_default_ttl: float = POLL_DEFAULT_TTL
    # 链接预览（R26D）
    preview_timeout: float = PREVIEW_TIMEOUT
    preview_max_bytes: int = PREVIEW_MAX_BYTES
    preview_ttl: float = PREVIEW_TTL
    preview_title_max: int = PREVIEW_TITLE_MAX
    # R70 剧透 / 编辑历史 / 群慢速 / 伪装 / 打码 / 自动回复 / 排行榜
    spoiler_enabled: bool = True            # R70A 剧透文字总开关（本地渲染）
    edit_history_max: int = 20              # R70B 单条消息保留的历史版本上限
    edit_history_len: int = 2000            # R70B 单版本快照截断长度
    group_slow_options: tuple = (0, 5, 10, 30, 60, 300)   # R70D 群慢速档位（秒）
    disguise_styles: tuple = ("code", "log", "excel")     # R70E 消息伪装风格
    guard_words_default: tuple = ()         # R70F 敏感词默认词表（空=用户自配）
    guard_hours_default: str = ""           # R70F 打码生效时段（空=全天；如 "9-18"）
    auto_reply_cooldown: float = 600.0      # R70G 忙碌自动回复对端冷却（秒）
    fish_board_enabled: bool = False        # R70H 摸鱼排行榜（opt-in，默认关闭）
    fish_board_top: int = 10                # R70H 排行榜展示条数上限
    fish_board_score_max: int = 1000        # R70H 单次上报积分上限（防刷，累加前夹取）
    # 游戏房间定时推进
    game_auto_tick: float = GAME_AUTO_TICK

    # 便捷常量（只读，勿改）
    @property
    def max_header_bytes(self) -> int:
        return MAX_HEADER_BYTES

    @property
    def max_body_bytes(self) -> int:
        return MAX_BODY_BYTES


CFG = Cfg()
