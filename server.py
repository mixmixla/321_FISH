# -*- coding: utf-8 -*-
"""hub 服务器：crypto 握手 / 在线名单 / 聊天（公聊+私聊+群聊）/ 服务器历史（内存环形保留）/
心跳踢人 / 审计日志（落盘仅元数据，不存聊天正文）。

网页端聊天由 web.py 提供（同一 Hub / ChatBus，SSE 长连接），与 TCP 客户端互通。
运行：`python run.py server`；网页端在 http://<本机IP>:9529/（口令见 config.WEB_PASSWORD）。
"""
import os
import re
import secrets
import socket
import sys
import threading
import time
import hashlib
import ipaddress
import http.client
import ssl
from collections import defaultdict, deque
from html.parser import HTMLParser
from urllib.parse import urlparse
import json
import copy

from config import ADMIN_NICK, CFG, DRAFT_TTL, MAX_NICK_LEN, enable_crashlog
from crypto import HandshakeError, server_handshake
from protocol import MsgType, ProtocolError
from filexfer import TransferMeta, XferStatus
from games_pkg import GAME_META, GAME_TYPES
from games_pkg.base import GameRuleError
from games_pkg.rooms import RoomManager, RoomStatus
import audit as audit_mod
import auth
import stickers
import bots as _bots
import cloud_history as cloud_history_mod


def _now() -> float:
    return time.time()


PWD_MAX = 64                 # R47：昵称密码最大长度（明文，PBKDF2 后存储）


# ---------- R26D 链接预览（服务器出网抓取，自动；SSRF 防护 + 大小/时长上限） ----------
_URL_RE = re.compile(r"https?://[^\s<>\"']+")


def _is_private_ip(host: str) -> bool:
    """SSRF 黑名单：私网/环回/链路本地/组播/保留地址一律拒绝出网。"""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True          # 解析不出 IP 当作不安全
    # is_global 同时排除 CGNAT、文档网段及其它非公网特殊地址；下面的
    # 显式字段保留语义，覆盖不同 Python 版本对 is_global 的细节差异。
    return (not ip.is_global or ip.is_private or ip.is_loopback
            or ip.is_link_local or ip.is_multicast
            or ip.is_unspecified or ip.is_reserved)


class _MetaParser(HTMLParser):
    """提取 <title> 与 meta(og:title/description/image, description)。"""

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.og: dict = {}
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            prop = (a.get("property") or a.get("name") or "").strip().lower()
            content = (a.get("content") or "").strip()
            if prop in ("og:title", "og:description", "og:image", "og:url",
                        "description") and content:
                self.og.setdefault(prop, content)

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title + data).strip()

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False


def _parse_meta(html: str, url: str, cfg) -> dict:
    """从 HTML 提取元数据（无 og 时降级 title/空描述），title 截断。"""
    p = _MetaParser()
    try:
        p.feed(html[:cfg.preview_max_bytes])
    except Exception as e:            # HTML 畸形不致命，降级 title，但留日志
        print(f"[preview] 解析失败: {e!r}", file=sys.stderr)
    title = (p.og.get("og:title") or p.title or "").strip()
    desc = (p.og.get("og:description") or p.og.get("description") or "").strip()
    image = p.og.get("og:image") or ""
    if image.startswith("//"):
        image = "https:" + image
    elif image.startswith("/"):
        parsed = urlparse(url)
        image = f"{parsed.scheme}://{parsed.netloc}{image}"
    parsed = urlparse(url)
    return {"title": title[:cfg.preview_title_max],
            "desc": desc[:cfg.preview_title_max],
            "image": image, "domain": parsed.netloc, "url": url}


def _preview_public_addr(hostname: str, port: int):
    """Resolve one preview host once and return a fixed public sockaddr.

    Every answer must be public.  Rejecting a mixed DNS answer is deliberate:
    selecting only its public member would leave a resolver-controlled private
    address available for a later connection attempt.  The returned sockaddr
    is passed to a raw socket, so the connect path does not resolve ``hostname``
    a second time (DNS rebinding protection).
    """
    infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    if not infos:
        raise OSError("preview host has no addresses")
    public = []
    for family, socktype, proto, _canonname, sockaddr in infos:
        address = sockaddr[0]
        if _is_private_ip(address):
            raise OSError("preview host resolves to a non-public address")
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        public.append((family, socktype, proto, sockaddr, address))
    if not public:
        raise OSError("preview host has no supported public address")
    return public[0]


def _preview_socket(address_info, timeout):
    """Open a socket to an already-resolved address without another DNS lookup."""
    family, socktype, proto, sockaddr, _address = address_info
    sock = socket.socket(family, socktype, proto)
    try:
        sock.settimeout(timeout)
        sock.connect(sockaddr)
    except Exception:
        sock.close()
        raise
    return sock


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection whose TCP connect uses the one checked DNS answer."""

    def __init__(self, host, port, address_info, *, timeout):
        super().__init__(host, port, timeout=timeout)
        self._preview_address_info = address_info

    def connect(self):
        self.sock = _preview_socket(self._preview_address_info, self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Pinned HTTPS connection retaining hostname-based SNI/certificate checks."""

    def __init__(self, host, port, address_info, *, timeout):
        context = ssl.create_default_context()
        super().__init__(host, port, timeout=timeout, context=context)
        self._preview_address_info = address_info

    def connect(self):
        raw = _preview_socket(self._preview_address_info, self.timeout)
        try:
            # ``self.host`` is the URL hostname, so SNI and certificate
            # verification still target the original name, not the pinned IP.
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


def _preview_host_header(hostname: str, port: int, scheme: str) -> str:
    """Format Host without credentials and with correct IPv6 brackets."""
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    default = 443 if scheme == "https" else 80
    return host if port == default else f"{host}:{port}"


def _preview_target(parsed) -> str:
    """Return an origin-form request target, excluding fragments/userinfo."""
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    return target


def fetch_preview(url: str, cfg) -> dict | None:
    """抓取单条链接的预览元数据，失败/SSRF/超限静默降级为 ``None``。

    只允许公网 HTTP/HTTPS。DNS 结果必须全部是公网地址，并且 TCP 连接
    固定到本次检查过的 IP；HTTPS 仍以原始 hostname 做 SNI 和证书校验。
    直接使用 ``http.client`` 也意味着环境代理不会绕过这套地址策略。
    为避免未检查的跳转，预览默认拒绝任何 3xx 响应（代价是部分带跳转
    的页面没有预览；后续如需支持应逐跳解析并重复上述检查）。
    """
    conn = None
    try:
        parsed = urlparse(str(url or ""))
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https") or not parsed.hostname:
            return None
        # 不允许 userinfo：它会让展示 Host、证书名和实际 URL 语义分叉。
        if parsed.username is not None or parsed.password is not None:
            return None
        try:
            hostname = parsed.hostname
            port = parsed.port or (443 if scheme == "https" else 80)
        except (TypeError, ValueError):
            return None
        if not hostname or not 1 <= int(port) <= 65535:
            return None
        address_info = _preview_public_addr(hostname, int(port))
        host_header = _preview_host_header(hostname, int(port), scheme)
        if scheme == "https":
            conn = _PinnedHTTPSConnection(hostname, int(port), address_info,
                                          timeout=cfg.preview_timeout)
        else:
            conn = _PinnedHTTPConnection(hostname, int(port), address_info,
                                         timeout=cfg.preview_timeout)
        conn.request("GET", _preview_target(parsed), headers={
            "Host": host_header,
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8,*/*;q=0.1",
        })
        resp = conn.getresponse()
        # No implicit redirect: the next URL must be parsed/resolved/connected
        # independently to keep redirect SSRF and rebinding checks explicit.
        if 300 <= resp.status < 400:
            return None
        if resp.status < 200 or resp.status >= 300:
            return None
        ctype = resp.getheader("Content-Type", "") or ""
        if ctype and "html" not in ctype and "text/" not in ctype \
                and "xhtml" not in ctype:
            return None
        length_header = resp.getheader("Content-Length") or ""
        try:
            length = int(length_header or 0)
        except (TypeError, ValueError):
            return None
        if length > cfg.preview_max_bytes:
            return None
        data = bytearray()
        while len(data) < cfg.preview_max_bytes:
            chunk = resp.read(min(65536, cfg.preview_max_bytes - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if not data:
            return None
    except Exception as e:            # SSRF/超时/网络错误静默降级，但留日志便于排障
        print(f"[preview] 抓取失败 {url!r}: {e!r}", file=sys.stderr)
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    text = bytes(data).decode("utf-8", errors="ignore")
    return _parse_meta(text, url, cfg)


class ChatBus:
    """频道历史环形缓冲 + 全局单调 seq（客户端靠 seq 去重/排序）"""

    def __init__(self, maxlen: int) -> None:
        self._lock = threading.RLock()
        self._channels = defaultdict(lambda: deque(maxlen=maxlen))
        self._seq = 0
        # R66：seq → (channel_key, msg) 索引，使 find/discard 从 O(全部消息) 降为 O(1)。
        # 维护点：publish(含 maxlen 淘汰)/purge/discard/clear_all/clear_uid/reindex
        self._by_seq: dict = {}

    @staticmethod
    def key(channel: str, uid: int, to) -> str:
        if channel == "public":
            return "all"
        if channel == "private":
            a, b = sorted((uid, to))
            return f"private:{a}:{b}"
        return f"group:{to}"

    def publish(self, msg: dict) -> dict:
        """打上 seq 并入历史；返回带 seq 的消息副本"""
        with self._lock:
            self._seq += 1
            msg = dict(msg)
            msg["seq"] = self._seq
            key = self.key(msg["channel"], msg["uid"], msg.get("to"))
            dq = self._channels[key]
            if dq.maxlen is not None and len(dq) >= dq.maxlen:
                old = dq[0]                     # 环形淘汰：同步摘掉索引里的旧项
                self._by_seq.pop(old.get("seq"), None)
            dq.append(msg)
            self._by_seq[msg["seq"]] = (key, msg)
            return msg

    def reindex(self) -> None:
        """按当前频道内容重建 seq 索引（恢复快照后调用）。"""
        with self._lock:
            self._by_seq.clear()
            for key, dq in self._channels.items():
                for m in dq:
                    s = m.get("seq")
                    if s is not None:
                        self._by_seq[s] = (key, m)

    def history(self, key: str, limit: int | None = None) -> list:
        with self._lock:
            dq = self._channels.get(key)
            if not dq:
                return []
            items = list(dq)
            return items if limit is None else items[-limit:]

    def purge(self, channel: str, uid: int, to, until_seq: int) -> int:
        """R14 会话清理：丢弃该频道 seq<=until_seq 的消息；返回删除条数。"""
        key = self.key(channel, uid, to)
        with self._lock:
            dq = self._channels.get(key)
            if not dq:
                return 0
            keep = deque((m for m in dq if m.get("seq", 0) > until_seq),
                         maxlen=dq.maxlen)
            removed = len(dq) - len(keep)
            for m in dq:
                if m.get("seq", 0) <= until_seq:
                    self._by_seq.pop(m.get("seq"), None)
            self._channels[key] = keep
            return removed

    def find(self, seq: int):
        """按全局 seq 定位消息；返回 (channel_key, msg)；找不到返回 (None, None)。"""
        with self._lock:
            hit = self._by_seq.get(seq)
            return (None, None) if hit is None else hit

    def discard(self, seq: int) -> bool:
        """R14 阅后即焚：只丢弃指定 seq 这一条消息，不影响同会话更早消息。"""
        with self._lock:
            hit = self._by_seq.pop(seq, None)
            if hit is None:
                return False
            key, msg = hit
            dq = self._channels.get(key)
            if dq is not None:
                try:
                    dq.remove(msg)
                except ValueError:
                    pass
            return True

    def clear_all(self) -> int:
        """R53 管理员清空全部历史：清空所有频道缓冲；返回删除条数。
        seq 保持单调递增（不重置），避免新旧消息 seq 冲突。"""
        with self._lock:
            total = sum(len(dq) for dq in self._channels.values())
            self._channels.clear()
            self._by_seq.clear()
            return total

    def clear_uid(self, uid: int) -> int:
        """R53 管理员清空某 uid 的全部消息（跨全部频道）；返回删除条数。"""
        with self._lock:
            removed = 0
            for key, dq in list(self._channels.items()):
                keep = deque((m for m in dq if m.get("uid") != uid),
                             maxlen=dq.maxlen)
                removed += len(dq) - len(keep)
                for m in dq:
                    if m.get("uid") == uid:
                        self._by_seq.pop(m.get("seq"), None)
                if keep:
                    self._channels[key] = keep
                else:
                    self._channels.pop(key, None)
            return removed


class Session:
    """一条在线会话（tcp 或 web）；send 是发帧回调，不能阻塞在 Hub 锁内"""

    def __init__(self, uid: int, nick: str, stype: str, peer_ip: str, send) -> None:
        self.uid = uid
        self.nick = nick
        self.type = stype          # "tcp" | "web"
        self.peer_ip = peer_ip
        self.send = send           # callable(payload_dict) -> None
        self.close_conn = lambda: None      # 踢人时由服务器主动关连接
        self.last_seen = _now()
        self.closed = False
        self.is_admin = False       # 只由服务器凭据校验成功后授予

    def touch(self) -> None:
        self.last_seen = _now()


class Hub:
    def __init__(self, cfg=None, audit_dir: str | None = None,
                 heartbeat_timeout: float | None = None,
                 web_idle_timeout: float | None = None,
                 web_password: str | None = None,
                 store_dir: str | None = None) -> None:
        self.cfg = cfg or CFG
        self._hb_timeout = (heartbeat_timeout if heartbeat_timeout is not None
                            else self.cfg.heartbeat_timeout)
        self._web_idle = (web_idle_timeout if web_idle_timeout is not None
                          else self.cfg.web_idle_timeout)
        self._web_password = (web_password if web_password is not None
                              else self.cfg.web_password)
        # 部署侧凭据，不允许缺省/空配置回退到公开密码。
        admin_nick = getattr(self.cfg, "admin_nick", ADMIN_NICK)
        if (not isinstance(admin_nick, str) or not admin_nick.strip()
                or len(admin_nick.strip()) > MAX_NICK_LEN):
            raise ValueError(f"管理员昵称配置无效（须为 1–{MAX_NICK_LEN} 字符）")
        self._admin_nick = admin_nick.strip()
        # 更换登录标识后也保留旧标识，避免普通用户冒充旧管理员。
        self._reserved_admin_nicks = {ADMIN_NICK, self._admin_nick}
        admin_pwd = getattr(self.cfg, "admin_pwd", "")
        self._admin_pwd_hash = (auth.make(admin_pwd)
                                if isinstance(admin_pwd, str) and admin_pwd.strip()
                                else None)
        self._zombie_web_idle = getattr(self.cfg, "zombie_web_idle", 30.0)
        self.lock = threading.RLock()
        self.sessions = {}          # uid -> 代表会话（在线集按 uid 唯一；任一端在线即在线）
        self._uid_clients = {}      # uid -> set[Session]（同一 uid 的全部在线会话，多端并存）
        self.nick_to_uid = {}
        self.web_tokens = {}        # token -> 已认证的 Web Session（不能借同 uid 的其它端续权）
        self.groups = {}            # gid -> {gid,name,owner,members:{uid:nick}}
        # R55-7 群邀请码防爆破：ip -> [失败时间戳...]（滑动窗口限速）
        self._invite_fails: dict = {}
        self._uid_seq = 1
        self._gid_seq = 1
        self.bus = ChatBus(self.cfg.server_history_max)
        self.stickers = stickers.STICKER_PACK
        # R35 贴纸商店：uid -> set(pack_id)（订阅状态，welcome 带回；内存态）
        self.sticker_subs: dict = {}
        # R35 内置 Bots：提醒待发队列（sweeper 到期推送）
        self.bot_reminders: list = []
        # R37 加密云历史：uid -> {"blob": bytes, "ts": float}（服务器只存密文；
        # 落盘 web_files_dir/cloud/{uid}.bin，重启保留，服务器无法解密）
        self.cloud: dict = {}
        self.cloud_dir = os.path.join(self.cfg.web_files_dir, "cloud")
        os.makedirs(self.cloud_dir, exist_ok=True)
        self._cloud_load_disk()
        self.xfers = {}             # file_id -> 传输记录（中转/直连状态权威）
        self.rooms = RoomManager(GAME_TYPES)   # 游戏房间（服务器权威）
        self.reads = {}             # convo_key -> {uid: max_read_seq}（已读回执）
        self.pins = {}              # convo_key -> {seq,nick,text,sticker,ts}（消息置顶快照）
        self._burn = {}             # seq -> {channel,uid,to,ts,pend:{uid}}（阅后即焚，全体读到后删）
        # R29B 草稿同步：(uid, key) -> {text, ts}（内存短留；单 uid 单会话，换端登录 welcome 带回）
        self._drafts: dict = {}
        self._voice = {}            # seq -> WAV bytes（语音消息二进制体，内存短留，TTL 清理）
        self._voice_ts = {}         # seq -> 收帧时间（配合 TTL 清理）
        # R72 多人语音房名册：room -> {uid: {"port": int}}（纯内存、不落盘；空房即删）
        self.voice_rooms: dict = {}
        # R72 视频留言：seq -> VMA1 bytes（内存短留，TTL 与语音消息同档）
        self._vmemo = {}
        self._vmemo_ts = {}
        # R25A typing：uid -> 上次 typing 帧时间（限速 1s/人，防刷屏）
        self._typing_ts = {}
        # R67 nudge：uid -> 上次 nudge 帧时间（限速 5s/人，防骚扰刷屏）
        self._nudge_ts = {}
        # R68 shake：uid -> 上次窗口抖动帧时间（限速 10s/人，防骚扰）
        self._shake_ts = {}
        # R25B 已知用户：uid -> {nick, last_online}（断线保留，供「最后上线」展示）
        self.known = {}
        # R50 屏蔽名单：uid -> set(被屏蔽 uid)（服务器权威，拦截私聊收发与密聊/语音）
        self.blocks: dict = {}
        # R51 服务器权威定时消息：uid -> {rid: {channel,to,text,fire_at,created}}（到点由 sweeper 发出）
        self.scheds: dict = {}
        # R26A 投票：seq -> {channel,to,uid,question,options,end,votes:{uid:idx}}（服务器权威聚合）
        self._polls = {}
        # R26D 链接预览：url -> (ts, meta) 缓存（TTL）/ in-flight 去重（后台线程出网）
        self._preview_cache: dict = {}
        self._preview_inflight: set = set()
        self._preview_lock = threading.Lock()
        # R23 网页端文件存储（fid = uuid4().hex；<fid> 二进制 + <fid>.json 元数据）
        self.web_files = os.path.join(self.cfg.web_files_dir)
        os.makedirs(self.web_files, exist_ok=True)
        # R30C 自定义贴纸：code -> {code,label,ext}（图片落盘 stickers/ 目录，随 R16 持久化）
        self.custom_stickers: dict = {}
        self.sticker_dir = os.path.join(self.cfg.web_files_dir, "stickers")
        os.makedirs(self.sticker_dir, exist_ok=True)
        # R64 自定义包元数据：pack -> {"cover": ext|""}（封面本体落盘 stickers/_covers/）
        self.pack_meta: dict = {}
        self.pack_cover_dir = os.path.join(self.sticker_dir, "_covers")
        try:
            os.makedirs(self.pack_cover_dir, exist_ok=True)
        except OSError:
            pass
        # R52 头像：uid -> ext 记在 known[uid]["avatar"]，图片本体落盘 avatars/{uid}.{ext}
        self.avatar_dir = os.path.join(self.cfg.web_files_dir, "avatars")
        os.makedirs(self.avatar_dir, exist_ok=True)
        # 朋友圈：pid -> post；图文动态全服时间轴（图片本体落盘 moments/，快照只存元数据）
        self.moments: dict = {}
        self._pid_seq = 0
        self.moment_dir = os.path.join(self.cfg.web_files_dir, "moments")
        os.makedirs(self.moment_dir, exist_ok=True)
        self.moment_covers: dict = {}      # uid -> {mode:"preset"|"img", preset:int|None, ext:str|None}
        self.cover_dir = os.path.join(self.moment_dir, "covers")
        try:
            os.makedirs(self.cover_dir, exist_ok=True)
        except OSError:
            pass
        self._COVER_EXTS = ("png", "jpg", "jpeg", "webp", "gif", "bmp")
        self._COVER_MAX = 2 * 1024 * 1024
        self._COVER_PRESETS = 6
        # 群文件库：gid -> [ {fid,name,size,ts,uid,nick} ]（二进制落盘 group_files/{gid}/{fid}）
        self.group_files: dict = {}
        self.group_files_dir = os.path.join(self.cfg.web_files_dir, "group_files")
        os.makedirs(self.group_files_dir, exist_ok=True)
        self._gf_seq = 0            # 群文件 fd 自增号（分发唯一 fid）
        # R69B6/B7 群待办/接龙/签到：gid -> [ {tid,text,mode,uid,ts,done:{uid:ts},assignee,closed} ]
        self.tasks: dict = {}
        self._task_seq = 0          # 群任务自增号（分发唯一 tid）
        # R70H 摸鱼排行榜：game_name -> {uid: 累计积分}（opt-in 上报，默认关闭；入快照持久化）
        self._fish: dict = {}
        # R16 全状态持久化：仅当显式传入 store_dir 才启用（现有测试不传 → 行为不变）
        self.store = None
        self._persist_interval = self.cfg.persist_interval
        self._persist_last = 0.0
        self._persist_dirty = False
        # R65：以"内容指纹"替代常驻的第二份全量快照做无变更判定。
        # 旧实现把整份 _snapshot_state() 再深拷贝常驻、并用递归 dict 比较判定相等：
        # 内存翻倍、大状态下比较慢。改为只保留一次 md5(json) 摘要（32 字节字符串），
        # 比较退化为字符串比对。指纹仅在 worker / flush 真正 save 成功后推进，
        # 失败则留旧值（避免把失败写当已落盘而漏掉兜底重写）。
        self._persist_fp = None
        # 异步落盘：dump+写盘挪到后台 worker，连接线程只做浅拷贝快照（latest-wins）
        self._persist_lock = threading.Lock()
        self._persist_pending = False
        self._persist_slot = None
        self._persist_slot_fp = None
        self._persist_wake = threading.Event()
        self._persist_closing = False
        self._persist_worker_thread = None
        if store_dir:
            from server_store import ServerStore
            self.store = ServerStore(os.path.join(store_dir, "state.json"))
        self._restore(self.store.load() if self.store else {})
        # R35 内置 Bots：注册进 known（type=bot，永远在线；uid 900+ 高位段）。
        # 必须在 _restore 之后（restore 会整体替换 known，注册放前面会被抹掉）
        for _b in _bots.BOTS:
            self.known[_b.uid] = {"nick": _b.nick, "last_online": _now(),
                                  "type": "bot"}
        self.audit = audit_mod.AuditLog(audit_dir or self.cfg.audit_dir,
                                        self.cfg.audit_keep_days)

    # ---------- R16 全状态持久化 ----------
    def _snapshot_state(self) -> dict:
        """抓取全部需持久化状态为可 JSON 序列化 dict（两把锁顺序取、不嵌套）。

        返回的必须是"私有快照"：绝不与 handler 正在原地修改的 live 状态共享可变引用。
        否则后台 worker 写盘 / last-saved 无变更对比会被后来的原地变更污染，导致：
          - 落盘内容与真实历史不一致；
          - “无变更”误判为相等而漏写（数据丢失）。

        逐层独立性的保证依据：
          - channels：deque → list；每条消息既会原地改 text/deleted，也可能被附加
            reactions/poll/preview/comments 等子结构，故按条 deepcopy。
          - known/reads/pins/burn：外层 dict 新建、内层“值 dict”也新建（会被原地写）。
            reads 在已读回执处 reads[key][uid]=ts 原地更新；known 在 last_online/签名/
            隐身/头像/pwd 处原地改值；pins/burn 值也统一复制以兜底。
          - polls：值 dict 中的 votes（p.votes[uid]=option）与 options 会原地变，单独复制。
          - moments：post 会被原处 append comments，值按 deepcopy。
          - groups：按字段拼接全新 dict（members/mutes 新建、admins sorted 新列表）；
            member 值若为 dict 则浅复制（其键为整值替换，无原地子改）。
          - 其余字典型（nick_to_uid/drafts/scheds/…）均按值新建新 dict，无常驻原地改动。
        """
        with self.bus._lock:
            seq = self.bus._seq
            channels = {k: [copy.deepcopy(m) for m in dq]
                        for k, dq in self.bus._channels.items()}
        with self.lock:
            def _copy_member_val(v):
                return {kk: (dict(vv) if isinstance(vv, dict) else vv)
                        for kk, vv in v.items()}
            return {
                "bus": {"seq": seq, "channels": channels},
                "uid_seq": self._uid_seq,
                "gid_seq": self._gid_seq,
                "nick_to_uid": dict(self.nick_to_uid),
                "groups": {
                    str(gid): {
                        "gid": g["gid"], "name": g["name"], "owner": g["owner"],
                        "admins": sorted(g["admins"]),
                        "members": _copy_member_val(g["members"]),
                        "mutes": dict(g.get("mutes") or {}),
                        "announce": g.get("announce", ""),
                        "announce_mode": g.get("announce_mode", 0),  # C9①：仅公告说话模式
                        "invite": g.get("invite", ""),   # R28：邀请码
                        "kind": g.get("kind", ""),       # R26B：频道标记
                        "public": g.get("public", 0),    # R54：公开群标记
                        "slow": int(g.get("slow") or 0),   # R70D：群慢速档位（秒，0=关闭）
                    } for gid, g in self.groups.items()},
                "reads": {k: dict(v) for k, v in self.reads.items()},
                "pins": {k: dict(v) for k, v in self.pins.items()},
                "burn": {k: dict(v) for k, v in self._burn.items()},
                "known": {k: dict(v) for k, v in self.known.items()},  # R25B：已知用户
                "blocks": {str(k): sorted(v) for k, v in self.blocks.items()},  # R50
                "polls": {k: dict(v, votes=dict(v.get("votes") or {}),
                                  options=list(v.get("options") or []))
                          for k, v in self._polls.items()},   # R26A：投票权威状态
                "drafts": {f"{u}|{k}": dict(d) for (u, k), d in self._drafts.items()},  # R29B
                "scheds": {str(u): {rid: dict(r) for rid, r in mine.items()}
                           for u, mine in self.scheds.items()},  # R51：定时消息队列
                "custom_stickers": {k: dict(v) for k, v in self.custom_stickers.items()},
                "sticker_pack_meta": {k: dict(v) for k, v in self.pack_meta.items()},  # R64
                "group_files": {str(gid): [dict(r) for r in records]          # 群文件元数据
                                for gid, records in self.group_files.items()},
                "gf_seq": self._gf_seq,
                "tasks": {str(gid): [dict(t, done=dict(t.get("done") or {}))  # R69B6/B7
                                     for t in recs]
                          for gid, recs in self.tasks.items()},
                "task_seq": self._task_seq,
                "fish_board": {str(g): {str(u): int(v) for u, v in sc.items()}
                               for g, sc in self._fish.items()},   # R70H 摸鱼排行榜
                "moments": {pid: copy.deepcopy(post)
                            for pid, post in self.moments.items()},   # 朋友圈元数据
                "moment_covers": {str(u): dict(v) for u, v in self.moment_covers.items()},
                "pid_seq": self._pid_seq,
            }

    def _restore(self, state: dict) -> None:
        """从快照恢复内存态；逐项容错，坏数据跳过该项不崩 Hub。"""
        if not isinstance(state, dict):
            return
        try:
            b = state.get("bus") or {}
            self.bus._seq = int(b.get("seq", 0))
            for k, items in (b.get("channels") or {}).items():
                dq = self.bus._channels[k]
                dq.clear()
                dq.extend(items)
            self.bus.reindex()          # R66：按恢复后的频道内容重建 seq 索引
        except Exception:
            pass
        try:
            self._uid_seq = int(state.get("uid_seq", self._uid_seq))
            self._gid_seq = int(state.get("gid_seq", self._gid_seq))
        except Exception:
            pass
        try:
            self.nick_to_uid = {str(k): int(v) for k, v
                                in (state.get("nick_to_uid") or {}).items()}
        except Exception:
            pass
        try:
            for gid, g in (state.get("groups") or {}).items():
                grp = dict(g)
                grp["gid"] = int(gid)
                grp["admins"] = set(grp.get("admins") or [])
                grp["members"] = dict(grp.get("members") or {})
                grp.setdefault("mutes", {})
                grp.setdefault("announce", "")
                grp.setdefault("announce_mode", 0)   # C9①：仅公告说话模式（旧数据缺省关闭）
                grp.setdefault("invite", "")           # R28：邀请码（旧数据缺省）
                grp.setdefault("kind", "")           # R26B：频道标记（旧数据缺省普通群）
                grp.setdefault("public", 0)          # R54：公开标记（旧数据缺省私有）
                grp.setdefault("slow", 0)            # R70D：群慢速档位（旧数据缺省关闭）
                self.groups[int(gid)] = grp
        except Exception:
            pass
        try:
            self.reads = {str(k): dict(v) for k, v
                          in (state.get("reads") or {}).items()}
        except Exception:
            pass
        try:
            self.pins = dict(state.get("pins") or {})
        except Exception:
            pass
        try:
            self._burn = {int(k): dict(v) for k, v
                          in (state.get("burn") or {}).items()}
        except Exception:
            pass
        try:
            self.known = {int(k): dict(v) for k, v
                          in (state.get("known") or {}).items()}
        except Exception:
            pass
        try:
            # R50：屏蔽名单恢复（值为 uid 列表）
            self.blocks = {}
            for k, v in (state.get("blocks") or {}).items():
                if k.isdigit() and isinstance(v, list):
                    self.blocks[int(k)] = {int(x) for x in v if isinstance(x, int)}
        except Exception:
            pass
        try:
            # R26A：投票权威状态恢复（votes 键转 int；坏数据跳过）
            self._polls = {int(k): dict(v) for k, v
                           in (state.get("polls") or {}).items()}
            for p in self._polls.values():
                v = p.get("votes")
                if not isinstance(v, dict):
                    p["votes"] = {}
                    continue
                # R70C：uid 键还原为 int，选项统一成 list（兼容 R26 旧的 int 形状）
                p["votes"] = {
                    (int(k) if str(k).lstrip("-").isdigit() else k):
                    ([int(x) for x in val] if isinstance(val, (list, tuple))
                     else ([int(val)] if isinstance(val, int) else []))
                    for k, val in v.items()}
        except Exception:
            pass
        try:
            # R29B：草稿恢复（键 (uid,key) 序列化为 "uid|key"；坏数据跳过）
            self._drafts = {}
            for k, v in (state.get("drafts") or {}).items():
                uid_s, _, key = k.partition("|")
                if uid_s.isdigit() and key and isinstance(v, dict):
                    self._drafts[(int(uid_s), key)] = {"text": str(v.get("text") or ""),
                                                       "ts": float(v.get("ts") or 0)}
        except Exception:
            pass
        try:
            # R51：定时消息队列恢复（key 为 uid 字符串；坏记录跳过）
            self.scheds = {}
            for k, mine in (state.get("scheds") or {}).items():
                if not k.isdigit() or not isinstance(mine, dict):
                    continue
                recs = {}
                for rid, r in mine.items():
                    if not isinstance(r, dict) or not r.get("text"):
                        continue
                    try:
                        fire_at = float(r.get("fire_at") or 0)
                    except (TypeError, ValueError):
                        continue
                    if fire_at <= time.time():      # 重启后已到点项不再补发
                        continue
                    recs[str(rid)] = {"channel": str(r.get("channel") or "public"),
                                      "to": r.get("to"), "text": str(r["text"]),
                                      "fire_at": fire_at,
                                      "created": float(r.get("created") or 0)}
                if recs:
                    self.scheds[int(k)] = recs
        except Exception:
            pass
        try:
            # 朋友圈恢复：pid -> post；键/字段容错，坏记录跳过
            self.moments = {}
            for k, p in (state.get("moments") or {}).items():
                if not isinstance(p, dict):
                    continue
                try:
                    pid = int(k)
                except (TypeError, ValueError):
                    continue
                self.moments[pid] = {
                    "pid": pid,
                    "uid": int(p.get("uid") or 0),
                    "nick": str(p.get("nick") or ""),
                    "text": str(p.get("text") or ""),
                    "ts": float(p.get("ts") or 0),
                    "images": list(p.get("images") or []),
                    "likes": [int(u) for u in (p.get("likes") or []) if isinstance(u, int)],
                    "comments": list(p.get("comments") or []),
                }
            self._pid_seq = int(state.get("pid_seq") or (max(self.moments, default=0)))
        except Exception:
            pass
        try:
            # 群文件元数据恢复：gid -> 记录列表；本体仍在磁盘 group_files/ 目录
            self.group_files = {}
            for gid_s, records in (state.get("group_files") or {}).items():
                if not gid_s.isdigit() or not isinstance(records, list):
                    continue
                gid = int(gid_s)
                recs = []
                for r in records:
                    if not isinstance(r, dict) or not r.get("fid") or not r.get("name"):
                        continue
                    try:
                        recs.append({"fid": str(r["fid"]), "name": str(r["name"]),
                                     "size": int(r.get("size") or 0),
                                     "ts": float(r.get("ts") or 0),
                                     "uid": int(r.get("uid") or 0),
                                     "nick": str(r.get("nick") or "")})
                    except (TypeError, ValueError):
                        continue
                if recs:
                    self.group_files[gid] = recs
            try:
                self._gf_seq = int(state.get("gf_seq") or self._gf_seq)
            except (TypeError, ValueError):
                pass
        except Exception:
            pass
        try:
            # R69B6/B7 群任务恢复：gid -> 任务列表；逐条容错，坏条目跳过
            self.tasks = {}
            for gid_s, recs in (state.get("tasks") or {}).items():
                if not str(gid_s).isdigit() or not isinstance(recs, list):
                    continue
                gid = int(gid_s)
                items = []
                for t in recs:
                    if not isinstance(t, dict):
                        continue
                    try:
                        tid = int(t["tid"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    text = str(t.get("text") or "")[:self.cfg.chat_text_max]
                    if not text:
                        continue
                    mode = t.get("mode") if t.get("mode") in ("todo", "relay",
                                                              "checkin") else "todo"
                    done = {}
                    for u, ts in (t.get("done") or {}).items():
                        try:
                            done[int(u)] = float(ts)
                        except (TypeError, ValueError):
                            continue
                    try:
                        assignee = int(t.get("assignee") or 0)
                    except (TypeError, ValueError):
                        assignee = 0
                    items.append({"tid": tid, "text": text, "mode": mode,
                                  "uid": int(t.get("uid") or 0),
                                  "ts": float(t.get("ts") or 0),
                                  "done": done, "assignee": assignee,
                                  "closed": int(t.get("closed") or 0)})
                if items:
                    self.tasks[gid] = items
            try:
                self._task_seq = int(state.get("task_seq") or 0)
            except (TypeError, ValueError):
                pass
        except Exception:
            pass
        try:
            # R70H 摸鱼排行榜恢复：game -> {uid: 分数}；坏记录跳过
            self._fish = {}
            for g, sc in (state.get("fish_board") or {}).items():
                if not isinstance(sc, dict):
                    continue
                board = {}
                for u, v in sc.items():
                    try:
                        board[int(u)] = int(v)
                    except (TypeError, ValueError):
                        continue
                if board:
                    self._fish[str(g)] = board
        except Exception:
            pass
        try:
            # 朋友圈封面恢复：uid -> {mode,preset,ext}；坏记录跳过
            self.moment_covers = {}
            for k, v in (state.get("moment_covers") or {}).items():
                if not isinstance(v, dict):
                    continue
                try:
                    uid = int(k)
                except (TypeError, ValueError):
                    continue
                mode = "img" if v.get("mode") == "img" else "preset"
                item = {"mode": mode,
                        "preset": int(v.get("preset") or 0),
                        "ext": str(v.get("ext") or "") or None}
                if mode == "img" and (not item["ext"]
                                      or item["ext"].lower() not in self._COVER_EXTS
                                      or not os.path.exists(self._cover_path(uid))):
                    continue          # 图片丢失 → 当作未设置，走默认封面
                self.moment_covers[uid] = item
        except Exception:
            pass
        try:
            # R64 自定义贴纸清单 + 包元数据恢复：清单只认磁盘上仍有图的条目；
            # 封面记录若文件已丢失则按「无封面」处理（不拖垮整表）。
            self.custom_stickers = {}
            for k, v in (state.get("custom_stickers") or {}).items():
                if not isinstance(v, dict):
                    continue
                code = str(v.get("code") or k or "")
                ext = str(v.get("ext") or "png").lower().strip(". ")
                if ext not in self._STICKER_EXTS:
                    continue
                if not os.path.exists(os.path.join(self.sticker_dir, f"{code}.{ext}")):
                    continue          # 图片丢失 → 丢弃该条，避免死引用
                try:
                    order = int(v.get("order") or 0)
                except (TypeError, ValueError):
                    order = 0
                self.custom_stickers[code] = {
                    "code": code, "label": str(v.get("label") or "")[:16],
                    "pack": str(v.get("pack") or "")[:16], "ext": ext,
                    "order": order}
            self.pack_meta = {}
            for k, v in (state.get("sticker_pack_meta") or {}).items():
                if not isinstance(v, dict):
                    continue
                ext = str(v.get("cover") or "").lower().strip(". ")
                pack = str(k)
                if not ext or ext not in self._STICKER_EXTS:
                    continue
                if not os.path.exists(self._pack_cover_path(pack, ext)):
                    continue
                self.pack_meta[pack] = {"cover": ext}
        except Exception:
            pass

    @staticmethod
    def _state_fingerprint(state: dict) -> str:
        """状态内容指纹（md5(规范化 JSON)）：替代常驻快照做"无变更"判定。
        state 由 _snapshot_state() 产出，已保证可 JSON 序列化（default=str 兜底）。"""
        try:
            blob = json.dumps(state, sort_keys=True, ensure_ascii=False,
                              default=str)
        except (TypeError, ValueError):
            blob = repr(state)
        return hashlib.md5(blob.encode("utf-8", "replace")).hexdigest()

    def _persist(self, force: bool = False) -> None:
        """节流写盘：窗口内合并突发变更，dump+写盘交给后台 worker（latest-wins）。
        无 store 时为空操作；force=True 恒写（关键变更同步落盘，返回即已持久）。

        R65：以内容指纹（md5(json)）判定无变更——不再常驻第二份全量快照、
        不做递归 dict 深比较。指纹仅在真正 save 成功后推进（失败留旧值，供 flush 兜底）。"""
        if self.store is None:
            return
        if not force:
            now = time.time()
            if now - self._persist_last < self._persist_interval:
                self._persist_dirty = True        # 仍在窗口内，稍后 sweeper 兜底
                return
        state = self._snapshot_state()            # 昂贵的全量私有快照——锁外构建
        fp = self._state_fingerprint(state)
        # 无新变更：指纹与最近一次"成功落盘"一致 → 不重建写盘（协调重复调用场景）
        if not force and self._persist_fp is not None and fp == self._persist_fp:
            # R66：推进节流时钟，否则下一次 _persist() 会再次重建全量快照
            # （如 _on_group_invite_get 等"无实际变更也调用"的路径）
            self._persist_last = time.time()
            self._persist_dirty = False
            return
        if force:
            # 关键变更（清空/解散/删号/Tombstone 等）：同步落盘，调用返回即已持久
            self._persist_sync(state, fp)
            return
        self._persist_last = time.time()
        self._persist_dirty = False
        self._ensure_persist_worker()
        with self._persist_lock:
            self._persist_slot = state            # 覆盖旧槽，latest-wins
            self._persist_slot_fp = fp
            self._persist_pending = True
            self._persist_wake.set()

    def _persist_sync(self, state: dict, fp: str) -> None:
        """同步落盘（force 关键变更 / 关停兜底）：先丢弃后台未写的旧槽，
        避免 worker 稍后用旧快照覆盖本次写（latest-wins 不被回退）。
        调用方须在锁外（避免锁序自锁风险）。"""
        self._persist_last = time.time()
        self._persist_dirty = False
        with self._persist_lock:
            self._persist_slot = None
            self._persist_slot_fp = None
            self._persist_pending = False
        try:
            self.store.save(state)
            with self._persist_lock:
                self._persist_fp = fp
        except Exception as e:            # 落盘失败：记审计告警 + stderr，避免静默丢数据
            try:
                self.audit.log(type="persist_error",
                               reason=f"同步落盘失败: {e!r}")
            except Exception:
                pass
            print(f"[persist] 同步落盘失败: {e!r}", file=sys.stderr)

    def _ensure_persist_worker(self) -> None:
        """懒启动后台落盘线程（daemon）。"""
        if self._persist_worker_thread is not None and \
                self._persist_worker_thread.is_alive():
            return
        self._persist_worker_thread = threading.Thread(
            target=self._persist_worker, name="persist-worker", daemon=True)
        self._persist_worker_thread.start()

    def _persist_worker(self) -> None:
        """后台循环：等唤醒 → 取最新槽 → 锁外 store.save（ServerStore._lock 保证单写），
        成功落盘后才推进 _persist_fp（失败则留旧值，供 flush 兜底重写）。"""
        while True:
            self._persist_wake.wait()
            if self._persist_closing and not self._persist_pending:
                break
            self._persist_wake.clear()
            with self._persist_lock:
                if not self._persist_pending:
                    continue                     # 空唤醒，继续等
                state = self._persist_slot
                fp = self._persist_slot_fp
                self._persist_pending = False
                self._persist_slot = None
            try:
                self.store.save(state)
                with self._persist_lock:
                    self._persist_fp = fp
            except Exception as e:            # 落盘失败：记审计告警，避免静默丢数据
                try:
                    self.audit.log(type="persist_error",
                                   reason=f"后台落盘失败: {e!r}")
                except Exception:
                    pass
                print(f"[persist] 后台落盘失败: {e!r}", file=sys.stderr)

    def _persist_flush(self) -> None:
        """强制立即写盘（关停兜底 / sweeper 兜底）：合并为一次同步构建+落盘，
        不再先异步 force 一次、又 _snapshot_state 一次（修复重复写）。
        无条件写最后状态：不依赖 dirty/compare，关停必然兜底不丢；
        仅当无 store 时空操作。"""
        if self.store is None:
            return
        state = self._snapshot_state()          # 锁外构建私有快照
        self._persist_sync(state, self._state_fingerprint(state))

    # ---------- 基础 ----------
    def _snapshot_sessions(self) -> list:
        """全部在线会话快照（含同 uid 多端，逐 Session 展开，供广播/清扫）。"""
        with self.lock:
            out = []
            for clients in self._uid_clients.values():
                out.extend(clients)
            return out

    def _is_invisible(self, uid: int) -> bool:
        """该 uid 是否开启隐身（服务器权威，known 持久）。"""
        with self.lock:
            return bool((self.known.get(uid) or {}).get("invisible"))

    def _roster(self, viewer: int | None = None) -> list:
        """在线名单。隐身用户在非管理员/非本人的其它会话中不可见。
        R69C9：附带 viewer 对每个 uid 的备注名（本人视角）。"""
        with self.lock:
            admin = self._is_admin_uid(viewer) if viewer else False
            v = viewer or 0
            remarks = (self.known.get(v, {}) or {}).get("remarks") or {}
            return [{"uid": s.uid, "nick": s.nick, "type": s.type,
                     "last_online": self.known.get(s.uid, {}).get("last_online", 0),
                     "sign": self.known.get(s.uid, {}).get("sign", ""),     # R52
                     "avatar": self.known.get(s.uid, {}).get("avatar", ""), # R52
                     "status": self.known.get(s.uid, {}).get("status", "") or "online",  # R68 在线状态
                     "remark": remarks.get(str(s.uid), ""),                # R69C9 备注名
                     "invisible": bool(self.known.get(s.uid, {}).get("invisible"))}  # R56B 隐身标记(管理员可见)
                    for s in sorted(self.sessions.values(), key=lambda s: s.uid)
                    if not (self._is_invisible(s.uid) and not admin and s.uid != v)]

    def _known_list(self, viewer: int | None = None) -> list:
        """R25B 已知用户全量（在线/离线都有，供客户端展示最后上线）。
        nick 以 known 记录为准；隐身用户对非管理员/非本人隐藏。
        R69C9：附带 viewer 对每个 uid 的备注名（本人视角，他人不可见）。"""
        with self.lock:
            admin = (self._is_admin_uid(viewer) if viewer
                     else False)  # 与 _roster 一致的隐身过滤
            v = viewer or 0
            remarks = (self.known.get(v, {}) or {}).get("remarks") or {}
            return [{"uid": uid, "nick": (self.sessions[uid].nick
                                          if uid in self.sessions
                                          else (info.get("nick") or f"用户{uid}")),
                     "last_online": info.get("last_online", 0),
                     "type": info.get("type", ""),
                     "sign": info.get("sign", ""),      # R52
                     "avatar": info.get("avatar", ""),
                     "status": info.get("status", "") or "online",   # R68 在线状态
                     "remark": remarks.get(str(uid), ""),          # R69C9 备注名
                     "invisible": bool(info.get("invisible"))}  # R58 隐身标记（管理员可看）
                    for uid, info in sorted(self.known.items())
                    if not (info.get("invisible") and not admin and uid != v)]

    def _admin_users(self) -> list:
        """R58：系统管理员全量账号（在线/离线都有），供管理面板管理所有账户。
        与 _roster（仅在线）不同，离线账户也在其中；online 区分当前是否在线。"""
        with self.lock:
            online = set(self.sessions.keys())
            return [{"uid": uid,
                     "nick": (self.sessions[uid].nick if uid in self.sessions
                              else (info.get("nick") or f"用户{uid}")),
                     "online": uid in online,
                     "last_online": info.get("last_online", 0),
                     "type": info.get("type", "user"),
                     "sign": info.get("sign", ""),
                     "avatar": info.get("avatar", ""),
                     "invisible": bool(info.get("invisible"))}
                    for uid, info in sorted(self.known.items())]

    def _known_names(self) -> dict:
        """已注册用户快照 {uid: {nick,...}}（锁内拷贝，供超管按 uid/昵称解析）。"""
        with self.lock:
            return {u: dict(info) for u, info in self.known.items()}

    def _is_admin_uid(self, uid: int) -> bool:
        """R54：该 uid 当前是否已认证的管理员会话。"""
        s = self.sessions.get(uid)
        return bool(s and s.is_admin)

    def _group_list(self, viewer_uid: int | None = None) -> list:
        """群列表（按查看者过滤，R54）：viewer 为 None 返回全量（兼容旧调用）；
        否则仅返回公开群 + 已加入群 + 管理员可见的全部群（含私有）。"""
        with self.lock:
            return [{"gid": g["gid"], "name": g["name"], "owner": g["owner"],
                     "admins": sorted(g["admins"]),
                     "member_count": len(g["members"]),
                     "member_max": self.cfg.group_max_members,   # R28：上限提示
                     "has_announce": bool(g.get("announce")),
                     "kind": g.get("kind", ""),          # R26B："" 普通群 / "channel" 频道
                     "public": g.get("public", 0),        # R54：公开群标记
                     "slow": int(g.get("slow") or 0)}   # R70D：群慢速档位
                    for g in sorted(self.groups.values(), key=lambda g: g["gid"])
                    if viewer_uid is None or g.get("public")
                    or viewer_uid in g["members"]
                    or self._is_admin_uid(viewer_uid)]

    def _convo_list(self, uid: int) -> list:
        """网页端会话列表：该用户参与过的私聊会话（另一端 uid/昵称/最后时间/未读数）。
        未读 = 历史环形缓冲内「非自己且 seq 大于已读线」的消息条数（近似，截断后只算留档部分）。
        先取 reads 快照再进 bus 锁，避免锁嵌套。"""
        with self.lock:
            reads = dict(self.reads)
        convos = {}
        with self.bus._lock:
            for key, dq in self.bus._channels.items():
                if not key.startswith("private:"):
                    continue
                _p, sa, sb = key.split(":")
                a, b = int(sa), int(sb)
                if uid not in (a, b):
                    continue
                other = b if uid == a else a
                last = None
                unread = 0
                read_seq = (reads.get(key) or {}).get(uid, 0)
                for m in dq:
                    if m.get("uid") != uid and m.get("seq", 0) > read_seq:
                        unread += 1
                    last = m
                if last is None:
                    continue
                nick = ""
                for m in reversed(dq):
                    if m.get("uid") == other:
                        nick = m.get("nick", "")
                        break
                convos[other] = {"uid": other,
                                 "nick": nick or f"用户{other}",
                                 "last_ts": last.get("ts", 0),
                                 "unread": unread}
        return sorted(convos.values(), key=lambda c: -c["last_ts"])

    # ---------- R23 网页端文件存储 ----------
    def _save_web_file(self, name: str, data: bytes, kind: str) -> dict:
        """保存网页端上传文件：fid = uuid4().hex（不可猜测），返回消息用 file 元数据。"""
        import uuid
        fid = uuid.uuid4().hex
        meta = {"fid": fid, "name": (name or "未命名")[:128],
                "size": len(data), "kind": kind, "ts": round(_now(), 3)}
        with open(os.path.join(self.web_files, fid), "wb") as f:
            f.write(data)
        with open(os.path.join(self.web_files, fid + ".json"), "w",
                  encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        return {k: meta[k] for k in ("fid", "name", "size", "kind")}

    def _web_file_meta(self, fid: str) -> dict | None:
        """按 fid 读元数据；fid 需为 32 位 hex，防路径穿越。"""
        if not (isinstance(fid, str) and re.fullmatch(r"[0-9a-f]{32}", fid)):
            return None
        path = os.path.join(self.web_files, fid + ".json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def _web_file_path(self, fid: str) -> str | None:
        if not (isinstance(fid, str) and re.fullmatch(r"[0-9a-f]{32}", fid)):
            return None
        path = os.path.join(self.web_files, fid)
        return path if os.path.isfile(path) else None

    def group_detail(self, gid: int, viewer_uid: int):
        """网页端用的群详情：成员 + 各自角色/禁言状态 + 当前用户角色。
        viewer 非成员返回 {"member":False} 便于 web 提示可加入。"""
        g = self.groups.get(gid)
        if not g:
            return None
        # R54：私有群对非成员（非管理员）视为不存在，不泄露群信息
        if not g.get("public") and viewer_uid not in g["members"] \
                and not self._is_admin_uid(viewer_uid):
            return None
        now = _now()
        members = []
        for uid, nick in sorted(g["members"].items()):
            mu = g["mutes"].get(uid, 0)
            members.append({"uid": uid, "nick": nick,
                            "role": self._group_role(g, uid),
                            "muted": mu > now, "muted_until": round(mu - now, 1) if mu > now else 0,
                            "online": uid in self.sessions,      # R68：群成员在线状态列表
                            "status": ((self.known.get(uid) or {}).get("status") or "online")
                                      if uid in self.sessions else "offline",   # R68：在线/离开/忙碌/离线
                            "invisible": bool((self.known.get(uid) or {}).get("invisible"))})  # R57
        return {"gid": g["gid"], "name": g["name"], "owner": g["owner"],
                "announce": g.get("announce", ""),
                "announce_mode": g.get("announce_mode", 0),   # C9①：仅公告说话模式
                "slow": int(g.get("slow") or 0),          # R70D：群慢速档位（秒）
                "kind": g.get("kind", ""),                 # R26B：频道标记
                "member_max": self.cfg.group_max_members,  # R28：上限提示
                "my_role": self._group_role(g, viewer_uid),
                "member": viewer_uid in g["members"],
                "members": members}

    def _error(self, sess: Session, code: str, text: str) -> None:
        try:
            sess.send({"t": "error", "code": code, "text": text})
        except Exception:
            pass

    def _broadcast(self, payload: dict) -> None:
        for s in self._snapshot_sessions():
            try:
                s.send(payload)
            except Exception:
                pass

    def _broadcast_system(self, text: str) -> None:
        self._broadcast({"t": "system", "text": text, "ts": round(_now(), 3)})

    def _broadcast_roster(self) -> None:
        """在线/已知名单按查看者过滤发送（隐身用户对非管理员/非本人隐藏）。"""
        for s in self._snapshot_sessions():
            try:
                s.send({"t": "roster", "online": self._roster(s.uid),
                        "known": self._known_list(s.uid)})
            except Exception:
                pass        # R25B：含离线最后上线,逐会话可见名单

    def _broadcast_group_list(self) -> None:
        """R54：群列表按查看者过滤——逐会话发送各自的可见群列表。"""
        for s in self._snapshot_sessions():
            try:
                s.send({"t": "group_list", "groups": self._group_list(s.uid)})
            except Exception:
                pass

    # ---------- R50 屏蔽名单 ----------
    def _blocked(self, uid: int) -> set:
        """uid 的屏蔽集合（快照，锁内拷贝）。"""
        with self.lock:
            return set(self.blocks.get(uid) or ())

    def _is_blocked_by(self, who: int, by: int) -> bool:
        """who 是否被 by 屏蔽（服务器权威：blocks[by] 记录了 by 拉黑的名单）。"""
        with self.lock:
            return who in (self.blocks.get(by) or ())

    def _broadcast_block_list(self, uid: int) -> None:
        """把我的屏蔽名单推给本账号全部会话（桌面+网页端）。"""
        lst = sorted(self._blocked(uid))
        for s in self._snapshot_sessions():
            if s.uid == uid:
                try:
                    s.send({"t": MsgType.BLOCK_LIST.value, "blocked": lst})
                except Exception:
                    pass

    def _on_block_set(self, sess: Session, header: dict) -> None:
        """设置/取消屏蔽：on=True 屏蔽 target / False 解除。防自屏蔽与 bot。"""
        try:
            target = int(header.get("target"))
        except (TypeError, ValueError):
            self._error(sess, "target", "缺少目标用户")
            return
        on = bool(header.get("on", True))
        if target == sess.uid:
            self._error(sess, "self", "不能屏蔽自己")
            return
        if on and _bots.is_bot(target):
            self._error(sess, "bot", "机器人无需屏蔽")
            return
        with self.lock:
            cur = self.blocks.setdefault(sess.uid, set())
            if on:
                cur.add(target)
            else:
                cur.discard(target)
                if not cur:
                    self.blocks.pop(sess.uid, None)
        self._broadcast_block_list(sess.uid)
        self.audit.log(type="block_set" if on else "block_unset",
                       uid=sess.uid, target=target)
        self._persist()

    def _on_block_list(self, sess: Session) -> None:
        """回帧我的屏蔽名单（重连/换端时客户端主动拉一次对齐）。"""
        try:
            sess.send({"t": MsgType.BLOCK_LIST.value,
                       "blocked": sorted(self._blocked(sess.uid))})
        except Exception:
            pass

    # ---------- R51 服务器权威定时消息 ----------

    def _sched_payload(self, uid: int) -> list:
        """我的待发定时消息列表（按 fire_at 升序，锁内快照）。"""
        with self.lock:
            mine = self.scheds.get(uid) or {}
            items = [{"rid": rid, "channel": r["channel"], "to": r.get("to"),
                      "text": r.get("text", ""), "fire_at": r["fire_at"],
                      "created": r.get("created", 0)}
                     for rid, r in sorted(mine.items(), key=lambda kv: kv[1]["fire_at"])]
            return items

    def _send_sched_list(self, sess: Session, uid: int) -> None:
        """回帧我的待发列表（创建/取消/拉取后调用）。"""
        try:
            sess.send({"t": MsgType.SCHED_LIST.value,
                       "items": self._sched_payload(uid)})
        except Exception:
            pass

    def _on_sched_set(self, sess: Session, header: dict) -> None:
        """创建定时消息：校验频道/文本/时间，入服务器队列并持久化。

        服务器权威：客户端离线也会到点发出（sweeper 每轮扫到期项）。
        """
        channel = header.get("channel") or "public"
        if channel not in ("public", "private", "group"):
            self._error(sess, "channel", "未知频道")
            return
        text = (header.get("text") or "").strip()
        if not text:
            self._error(sess, "empty", "定时消息不能为空")
            return
        if len(text) > self.cfg.chat_text_max:
            self._error(sess, "long", "消息过长")
            return
        try:
            fire_at = float(header.get("fire_at") or 0)
        except (TypeError, ValueError):
            self._error(sess, "fire_at", "缺少发送时间")
            return
        if fire_at <= _now():
            self._error(sess, "past", "发送时间必须晚于当前")
            return
        if fire_at > _now() + 86400 * 7:
            self._error(sess, "far", "最多定时 7 天")
            return
        to = header.get("to")
        if channel == "private":
            try:
                to = int(to)
            except (TypeError, ValueError):
                self._error(sess, "to", "缺少目标用户")
                return
            if to == sess.uid:
                self._error(sess, "to", "不能定时发给收藏夹")
                return
            if not self._known_uid(to):
                self._error(sess, "offline", "对方不存在或从未上线")
                return
            if self._is_blocked_by(sess.uid, to):
                self._error(sess, "blocked", "你已被对方屏蔽，定时消息不会送达")
                return
        elif channel == "group":
            g = self.groups.get(to)
            if not g or sess.uid not in g["members"]:
                self._error(sess, "group", "不在该群或群不存在")
                return
        rid = os.urandom(4).hex()
        rec = {"channel": channel, "to": to, "text": text,
               "fire_at": fire_at, "created": _now()}
        with self.lock:
            self.scheds.setdefault(sess.uid, {})[rid] = rec
        self._send_sched_list(sess, sess.uid)
        self.audit.log(type="sched_set", uid=sess.uid, channel=channel,
                       to=to, fire_at=fire_at)
        self._persist()

    def _on_sched_cancel(self, sess: Session, header: dict) -> None:
        """取消我的某条定时消息（rid）。"""
        rid = str(header.get("rid") or "")
        if not rid:
            self._error(sess, "rid", "缺少 rid")
            return
        with self.lock:
            mine = self.scheds.get(sess.uid)
            if mine and rid in mine:
                del mine[rid]
        self._send_sched_list(sess, sess.uid)
        self.audit.log(type="sched_cancel", uid=sess.uid, rid=rid)
        self._persist()

    def _on_sched_list(self, sess: Session) -> None:
        """拉取我的待发列表（重连/换端对齐）。"""
        self._send_sched_list(sess, sess.uid)

    def _sweep_scheds(self, now: float | None = None) -> None:
        """sweeper 每轮调用：到点的定时消息以创建者身份入频道历史并广播。

        在 Hub.lock 之外收集到期项（防锁内发帧阻塞），逐个以服务器身份投递。
        """
        now = _now() if now is None else now
        due = []
        with self.lock:
            for uid, mine in list(self.scheds.items()):
                if not mine:
                    continue
                ripe = [(rid, r) for rid, r in list(mine.items())
                        if r["fire_at"] <= now]
                for rid, _r in ripe:
                    mine.pop(rid, None)
                due.extend((uid, rid, r) for rid, r in ripe)
                if not mine:
                    self.scheds.pop(uid, None)
        for uid, rid, r in due:
            # 校验发送时刻仍有效（私聊目标未拉黑我/群成员身份以到点为准）
            if not self._sched_still_valid(uid, r):
                continue
            nick = (self.known.get(uid) or {}).get("nick") or f"用户{uid}"
            msg = {"t": "chat", "channel": r["channel"], "uid": uid,
                   "nick": nick, "ts": round(_now(), 3)}
            if r["text"]:
                msg["text"] = r["text"]
            if r["channel"] == "private":
                msg["to"] = r["to"]
            elif r["channel"] == "group":
                g = self.groups.get(r["to"])
                if g:
                    msg["to"] = r["to"]
                    msg["group_name"] = g["name"]
            msg = self.bus.publish(msg)
            self._route(msg)
            self.audit.log(type="sched_fire", uid=uid, seq=msg["seq"],
                           channel=r["channel"], to=msg.get("to"))
            self._persist()

    def _known_uid(self, uid: int) -> bool:
        """该 uid 是否已知用户（注册过/在会话中）。"""
        with self.lock:
            return uid in self.sessions or uid in self.known

    def _sched_still_valid(self, uid: int, r: dict) -> bool:
        """到点校验：私聊目标是否已拉黑我；群聊我是否仍是成员。"""
        if r["channel"] == "private" and r.get("to") is not None:
            if self._is_blocked_by(uid, r["to"]):
                return False
        elif r["channel"] == "group":
            g = self.groups.get(r.get("to"))
            if not g or uid not in g["members"]:
                return False
        return True

    # ---------- 注册 / 注销 ----------
    def _release_zombie(self, nick: str) -> None:
        """R47-A1：同名「僵尸会话」活性复查，死亡即释放。

        浏览器刷新/崩溃后 SSE 断开并不注销，web 会话要等 web_idle（5 分钟）
        才被清扫，期间同名重登被拒（锁名窗口）。活会话不会误伤：
        - web：SSE 每 15s 必 touch（推送或 keep-alive ping），30s 无 touch = 死；
        - tcp：心跳 45s 无收包本就该踢（清扫器 1s 内会做，这里兜底同步释放）。
        unregister 带 min_idle 复查，锁内原子防「检查后复活」竞态。
        """
        with self.lock:
            old_uid = self.nick_to_uid.get(nick)
            old = self.sessions.get(old_uid) if old_uid is not None else None
            if old is None:
                return
            limit = self._zombie_web_idle if old.type == "web" else self._hb_timeout
            zombie = (_now() - old.last_seen) > limit
        if zombie:
            self.unregister(old, "zombie", min_idle=limit)

    def _attach(self, sess: Session) -> bool:
        """登记会话并推送 welcome；恒返回 True（同账号允许多端并存，不再拒绝重复昵称）。

        R12fix：昵称→uid 映射在断线后保留（unregister 不再删除），同名重连
        复用原 uid——私聊/群/历史/草稿等 uid 对 key 在客户端重启后仍对齐。
        R批次③：改为「同 uid 多端并存」——同一账号桌面+网页（甚至多标签）
        不再互顶下线，而是共享同一 uid 的在线集（sessions 存代表会话；
        _uid_clients 存该 uid 全部在线会话，广播按 uid 命中全部端）。
        R47-A1：同名但为僵尸会话（断线未及清扫）先释放再放行。
        """
        self._release_zombie(sess.nick)      # R47-A1：先做僵尸释放（锁外）
        with self.lock:
            old_uid = self.nick_to_uid.get(sess.nick)
            if old_uid is not None:
                sess.uid = old_uid                # 复用历史 uid（跨重连稳定）
            else:
                sess.uid = self._uid_seq
                self._uid_seq += 1
            was_online = sess.uid in self.sessions   # 是否已有其它端在线
            self._uid_clients.setdefault(sess.uid, set()).add(sess)
            self.sessions[sess.uid] = sess            # 最近会话作代表（在线集仍按 uid 唯一）
            self.nick_to_uid[sess.nick] = sess.uid
            # R25B：登记已知用户（保留旧 last_online，跨重连/断线不丢）
            # R47-B：pwd 同样保留（登录校验依赖，重建字典不得丢）
            # R52：sign/avatar 同样保留（换端重登不得丢资料）
            prev = self.known.get(sess.uid)
            self.known[sess.uid] = {"nick": sess.nick,
                                    "last_online": (prev or {}).get("last_online", 0)}
            for _k in ("pwd", "sign", "avatar", "invisible", "status", "remarks"):  # R56 含隐身持久；R68 含在线状态；R69C9 含备注名
                if (prev or {}).get(_k):
                    self.known[sess.uid][_k] = prev[_k]
        sess.send({
            "t": "welcome", "uid": sess.uid, "nick": sess.nick,
            "is_admin": sess.is_admin,                       # R53：管理员标识
            "invisible": bool(self.known.get(sess.uid, {}).get("invisible")), # R56 隐身
            "status": self.known.get(sess.uid, {}).get("status", "") or "online",  # R68 我的在线状态
            "sign": self.known.get(sess.uid, {}).get("sign", ""),       # R52 我
            "avatar": self.known.get(sess.uid, {}).get("avatar", ""),   # R52 我
            "roster": self._roster(sess.uid), "groups": self._group_list(sess.uid),
            "stickers": self.stickers, "history": self.bus.history("all"),
            "custom_stickers": self._custom_list(),   # R30C：自定义贴纸清单
            "sticker_pack_meta": self._pack_meta_payload(),   # R64：包封面元数据
            "sticker_subs": self._sticker_subs_for(sess.uid),  # R35：贴纸订阅
            "known": self._known_list(sess.uid),          # R25B：已知用户（含离线，供最后上线）
            "saved": self.bus.history(f"private:{sess.uid}:{sess.uid}"),  # R25C：收藏夹历史
            "pins": self._pins_for(sess),
            "drafts": self._drafts_for(sess.uid),  # R29B：草稿同步（换端带回全部草稿）
            "blocked": sorted(self._blocked(sess.uid)),  # R50：屏蔽名单（客户端登录对齐）
            "scheds": self._sched_payload(sess.uid),     # R51：我的待发定时消息
        })
        self.audit.log(type="login", uid=sess.uid, nick=sess.nick,
                       peer=sess.peer_ip, via=sess.type)
        self._persist()                              # R16：uid/nick_to_uid 变化落盘
        self._broadcast_roster()
        if not was_online:                           # 仅当首个端上线时才广播「已上线」
            self._broadcast_system(f"{sess.nick} 已上线"
                                   + ("（网页端）" if sess.type == "web" else ""))
        return True

    def login_web(self, nick: str, peer_ip: str,
                  password: str = "") -> tuple:
        """网页端登录：建 web 会话 + 发 token；返回 (session, token) 或 (None, err)。

        R47-B：昵称已设密码则校验 password（错/缺一律拒）；未设密码且带了
        password → 登录成功后绑定（claim，先到先得）。"""
        nick = (nick or "").strip()[:MAX_NICK_LEN]
        if not nick:
            return None, "昵称不能为空"
        err = self._pwd_check_for_login(nick, password)
        if err:
            return None, err
        sess = Session(0, nick, "web", peer_ip,
                       send=self._make_web_send())
        # 只有通过部署凭据校验才能到达这里。
        # 须在 _attach（发送 welcome 帧）之前赋值，否则 welcome 的 is_admin 恒为 False。
        sess.is_admin = (nick == self._admin_nick)
        self._attach(sess)                  # 同账号多端并存：登记不再失败
        if password and not sess.is_admin:
            self._pwd_claim(sess.uid, password)
        token = secrets.token_hex(16)
        with self.lock:
            self.web_tokens[token] = sess
        return sess, token

    # ---------- R47-B：昵称可选密码 ----------
    def _pwd_check_for_login(self, nick: str, password: str) -> str | None:
        """登录期昵称密码校验。返回错误文案或 None（通过）。

        已设密码：password 必须匹配（PBKDF2 校验在锁外做，避免占 Hub 锁）；
        未设密码：放行（带密码时由调用方在 attach 成功后 claim 绑定）。
        管理员标识始终保留；未配置部署凭据时不降级为普通账号。"""
        if nick in self._reserved_admin_nicks:
            if nick != self._admin_nick or not self._admin_pwd_hash:
                return "管理员登录未启用，请联系服务器部署者"
            if not auth.verify(password, self._admin_pwd_hash):
                return "管理员密码错误"
            return None
        with self.lock:
            uid = self.nick_to_uid.get(nick)
            stored = ((self.known.get(uid) or {}).get("pwd")
                      if uid is not None else None)
        if stored:
            if not password:
                return "该昵称已设密码，请输入密码"
            if not auth.verify(password, stored):
                return "密码错误"
        return None

    def _pwd_store(self, uid: int, stored: str | None) -> None:
        """known[uid]['pwd'] 写入/清除（R16 落盘随 _persist）。"""
        with self.lock:
            info = self.known.get(uid)
            if info is None:
                return
            if stored:
                info["pwd"] = stored
            else:
                info.pop("pwd", None)
        self._persist()

    def _pwd_claim(self, uid: int, password: str) -> None:
        """登录时带了密码且该昵称未设密码 → 绑定（先到先得）。"""
        with self.lock:
            info = self.known.get(uid)
            if not info or info.get("pwd"):
                return
        self._pwd_store(uid, auth.make(password))
        self.audit.log(type="pwd_claim", uid=uid)

    def set_password(self, uid: int, old: str, new: str) -> str | None:
        """R47-B：设置/修改/清除昵称密码（需已登录身份）。返回错误文案或 None。

        - 未设密码：new 非空=绑定；new 空=报「尚未设置密码」；
        - 已设密码：old 必须匹配；new 空=清除。
        管理员凭据由部署侧管理，拒绝通过普通账号接口修改/清除。"""
        with self.lock:
            info = self.known.get(uid)
            if info is None:
                return "用户不存在"
            if info.get("nick") in self._reserved_admin_nicks:
                return "管理员凭据由服务器配置管理，不可修改"
            stored = info.get("pwd")
        if stored and not auth.verify(old, stored):
            return "旧密码错误"
        if not new:
            if not stored:
                return "尚未设置密码"
            self._pwd_store(uid, None)
            self.audit.log(type="pwd_change", uid=uid, action="clear")
            return None
        if len(new) > PWD_MAX:
            return f"密码过长（≤{PWD_MAX} 字符）"
        self._pwd_store(uid, auth.make(new))
        self.audit.log(type="pwd_change", uid=uid,
                       action="change" if stored else "set")
        return None

    def _on_set_pwd(self, sess: Session, header: dict) -> None:
        """R47-B：TCP 设置/修改/清除昵称密码（帧头 old/new）。"""
        old = str(header.get("old") or "")
        new = str(header.get("new") or "")
        had = bool((self.known.get(sess.uid) or {}).get("pwd"))
        err = self.set_password(sess.uid, old, new)
        if err:
            self._error(sess, "pwd_set", err)   # R47：区别于登录密码错误码，避免客户端误弹登录框
            return
        if not new:
            text = "✅ 昵称密码已清除，登录不再需要密码"
        elif had:
            text = "✅ 昵称密码已修改"
        else:
            text = "✅ 昵称密码已设置，下次登录需输入"
        sess.send({"t": "system", "text": text})

    # ---------- R52 头像与个性签名 ----------
    def _avatar_known(self, uid: int) -> str:
        """uid 当前头像 ext（无则 ""）。锁内读。"""
        with self.lock:
            return str((self.known.get(uid) or {}).get("avatar") or "")

    def _avatar_file(self, uid: int, ext: str) -> str:
        """头像文件路径（ext 已白名单校验；无则空串）。"""
        if not ext:
            return ""
        safe = "".join(ch for ch in ext.lower() if ch.isalnum())
        return os.path.join(self.avatar_dir, f"{uid}.{safe}")

    def _group_avatar_file(self, gid: int, ext: str) -> str:
        """R9H：群头像落盘路径（复用 avatar_dir，`g<gid>.<ext>` 前缀区分用户文件）。"""
        safe = "".join(ch for ch in str(ext).lower() if ch.isalnum())
        return os.path.join(self.avatar_dir, f"g{gid}.{safe}")

    def _on_avatar_set(self, sess: Session, header: dict, body: bytes) -> None:
        """R52：上传/更换头像（header: ext；body=图片字节 ≤1MB）。"""
        ext = str(header.get("ext") or "").lower().lstrip(".")
        if ext not in self.cfg.avatar_exts:
            self._error(sess, "avatar", "不支持的图片格式")
            return
        if not body or len(body) > self.cfg.avatar_max_bytes:
            self._error(sess, "avatar", "头像大小超出上限（1MB）")
            return
        uid = sess.uid
        # 原子落盘（先写临时文件再替换；旧 ext 文件一并清理）
        old_ext = self._avatar_known(uid)
        try:
            path = self._avatar_file(uid, ext)
            tmp = path + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(body)
            os.replace(tmp, path)
        except OSError as exc:
            self._error(sess, "avatar", f"头像保存失败: {exc}")
            return
        if old_ext and old_ext != ext:
            try:
                os.remove(self._avatar_file(uid, old_ext))
            except OSError:
                pass
        with self.lock:
            self.known.setdefault(uid, {})["avatar"] = ext
        self._persist()
        self._broadcast_roster()
        sess.send({"t": MsgType.AVATAR_DATA.value, "uid": uid, "ext": ext}, body)

    def _on_avatar_del(self, sess: Session) -> None:
        """R52：删除头像。"""
        uid = sess.uid
        old_ext = self._avatar_known(uid)
        if old_ext:
            try:
                os.remove(self._avatar_file(uid, old_ext))
            except OSError:
                pass
        with self.lock:
            (self.known.get(uid) or {}).pop("avatar", None)
        self._persist()
        self._broadcast_roster()
        sess.send({"t": MsgType.AVATAR_DATA.value, "uid": uid, "ext": ""})

    def _on_avatar_get(self, sess: Session, header: dict) -> None:
        """R52：拉取指定 uid 头像（服务器单播 AVATAR_DATA；无头像 ext=""）。"""
        try:
            uid = int(header.get("uid"))
        except (TypeError, ValueError):
            self._error(sess, "avatar", "参数错误")
            return
        ext = self._avatar_known(uid)
        if ext:
            path = self._avatar_file(uid, ext)
            try:
                with open(path, "rb") as fh:
                    data = fh.read()
                sess.send({"t": MsgType.AVATAR_DATA.value, "uid": uid, "ext": ext}, data)
                return
            except OSError:
                pass
        sess.send({"t": MsgType.AVATAR_DATA.value, "uid": uid, "ext": ""})

    def _on_sign_set(self, sess: Session, header: dict) -> None:
        """R52：设置个性签名（服务器权威，广播 roster 全员同步）。"""
        sign = str(header.get("sign") or "").strip()[:self.cfg.sign_max_len]
        with self.lock:
            self.known.setdefault(sess.uid, {})["sign"] = sign
        self._persist()
        self._broadcast_roster()

    def _on_status_set(self, sess: Session, header: dict) -> None:
        """R68：在线状态（online/away/busy）。服务器权威持久，广播 roster 全员同步；
        与隐身为正交维度（隐身控制「是否出现在名单」，状态控制「出现在名单时的点色」）。"""
        status = str(header.get("status") or "").strip().lower()
        if status not in ("online", "away", "busy"):
            self._error(sess, "status", "状态无效")
            return
        with self.lock:
            self.known.setdefault(sess.uid, {})["status"] = status
        self._persist()
        self._broadcast_roster()
        try:
            sess.send({"t": "status_ack", "status": status})
        except Exception:
            pass

    def _on_remark_set(self, sess: Session, header: dict) -> None:
        """R69C9：设置/清除好友备注名（本人视角，按 owner 持久化，remark 空=清除）。
        备注只对本人生效：写入 known[sess.uid]["remarks"][uid] 后重播 roster，
        各会话按查看者视角拿到自己的备注，互不串号。"""
        try:
            target = int(header.get("uid"))
        except (TypeError, ValueError):
            self._error(sess, "remark", "目标用户无效")
            return
        remark = str(header.get("remark") or "").strip()[:24]
        with self.lock:
            info = self.known.setdefault(sess.uid, {})
            rems = info.get("remarks")
            if not isinstance(rems, dict):
                rems = {}
            if remark:
                rems[str(target)] = remark
            else:
                rems.pop(str(target), None)
            if rems:
                info["remarks"] = rems
            else:
                info.pop("remarks", None)
        self._persist()
        self._broadcast_roster()
        try:
            sess.send({"t": MsgType.REMARK_ACK.value,
                       "uid": target, "remark": remark})
        except Exception:
            pass

    def _on_invis_set(self, sess: Session, header: dict) -> None:
        """R56：隐身上线开关。服务器权威持久；回帧 invis_ack 让本人确认，
        并重放 `_broadcast_roster` 让各会话按查看者视角刷新名单。"""
        on = bool(header.get("on"))
        with self.lock:
            self.known.setdefault(sess.uid, {})["invisible"] = on
        self._persist()
        self._broadcast_roster()
        try:
            sess.send({"t": "invis_ack", "on": on})
        except Exception:
            pass

    def _on_admin_invis_set(self, sess: Session, header: dict) -> None:
        """R56B：系统管理员强制某用户显身/隐身（超管 override）。
        同 INV_SET 一样服务器权威持久并重放名单；额外审计记录操作人。"""
        if not sess.is_admin:
            self._error(sess, "forbid", "仅系统管理员可执行")
            return
        uid = self._alias_to_uid(self._known_names(), header.get("uid"))
        if uid is None:
            self._error(sess, "uid", "目标 uid/昵称 无效")
            return
        on = bool(header.get("on"))
        with self.lock:
            self.known.setdefault(uid, {})["invisible"] = on
        self._persist()
        self._broadcast_roster()
        nick = (self.known.get(uid) or {}).get(
            "nick") or self.nick_to_uid.get(uid) or f"用户{uid}"
        # 通知目标本人（若在线）以校准其 UI 开关
        tgt = self.sessions.get(uid)
        if tgt is not None:
            try:
                tgt.send({"t": "invis_ack", "on": on})
            except Exception:
                pass
        self.audit.log(type="admin_force_invis", target=uid, target_nick=nick,
                       on=on, actor=sess.uid)
        print(f"[admin][隐身/显身] {sess.nick} 将 @{nick} 设为 "
              + ("隐身" if on else "显身"))
        self._broadcast_system(f"系统管理员已让 @{nick} "
                               + ("隐身" if on else "恢复正常可见"))

    def _make_web_send(self):
        """R49：网页会话推送 = SSE 连接级 fanout。

        旧实现整个会话共用一个队列、由唯一 SSE 连接 drain——页面刷新时旧
        EventSource 未断/多开标签页会多消费者竞争同一队列，帧被随机"偷走"
        （网页端偶发收不到 game_state 的根因）。现改为：每条 SSE 连接注册
        自己的队列；无连接时帧进预连接缓冲，attach 时搬运（welcome/roster
        等先于 SSE 建立的帧不丢），detach 后回到缓冲。"""
        import queue
        q = queue.Queue(maxsize=256)          # 预连接缓冲（无 SSE 连接时）
        conns: set = set()
        lock = threading.Lock()
        _dropped = [0]                        # [0]=期间丢弃帧数（缓冲满/单连接满），简单观测掉队

        def send(payload, body: bytes = b""):
            item = (payload, body)
            with lock:
                targets = list(conns)
                if not targets:
                    try:
                        q.put_nowait(item)
                    except queue.Full:
                        # 预连接缓冲满：丢弃最旧帧、保留最新，避免掉队消息优先于新帧
                        _dropped[0] += 1
                        try:
                            q.get_nowait()
                        except queue.Empty:
                            pass
                        try:
                            q.put_nowait(item)
                        except queue.Full:
                            pass
                    return
            for cq in targets:                # 锁外广播：单连接满不影响其他连接
                try:
                    cq.put_nowait(item)
                except queue.Full:
                    _dropped[0] += 1

        def attach(cq) -> None:
            with lock:
                while True:                   # 搬运预连接缓冲（锁内，与 send 互斥）
                    try:
                        cq.put_nowait(q.get_nowait())
                    except queue.Empty:
                        break
                    except queue.Full:
                        break
                conns.add(cq)

        def detach(cq) -> None:
            with lock:
                conns.discard(cq)

        send.dropped = lambda: _dropped[0]    # 观测入口：返回累计丢弃帧数
        send.q = q                            # 兼容保留（调试探针/旧引用）
        send.attach = attach
        send.detach = detach
        return send

    def session_by_token(self, token: str) -> Session | None:
        with self.lock:
            sess = self.web_tokens.get(token)
            if sess is None:
                return None
            if not self._session_is_active(sess):
                self.web_tokens.pop(token, None)
                return None
            return sess

    def unregister(self, sess: Session, reason: str,
                   min_idle: float | None = None) -> None:
        """注销（一个）在线会话。min_idle 非 None 时（R47-A1 僵尸释放路径）：
        仅当该会话闲置已超过 min_idle 才执行——锁内复查，防止误踢复活会话。
        R批次③：同 uid 多端并存——仅当该 uid 最后一个会话离线时才真正
        「下线」（更新 last_online、退群、广播已下线）。
        本会话的 Web token 每次注销都撤销，不能借其它在线端继续使用。"""
        dissolved = []
        with self.lock:
            clients = self._uid_clients.get(sess.uid)
            if not clients or sess not in clients:
                return
            if min_idle is not None and (_now() - sess.last_seen) <= min_idle:
                return                       # 已复活：不踢，让登录方按活会话拒绝
            clients.discard(sess)
            for tok, token_sess in list(self.web_tokens.items()):
                if token_sess is sess:
                    del self.web_tokens[tok]
            is_last = not clients
            if is_last:
                # 最后一个端离线：从在线集移除、补代表、记录 last_online
                del self._uid_clients[sess.uid]
                if self.sessions.get(sess.uid) is sess:
                    del self.sessions[sess.uid]
                else:                        # 代表是别的会话（异常兜底）
                    self.sessions.pop(sess.uid, None)
                # R25B：断线记录最后上线时间（known 保留 nick，供离线展示）
                # R47-B：pwd 必须随 known 保留，否则注销一次后密码丢失
                prev = self.known.get(sess.uid) or {}
                self.known[sess.uid] = {"nick": sess.nick,
                                        "last_online": _now()}
                if prev.get("pwd"):
                    self.known[sess.uid]["pwd"] = prev["pwd"]
                # R12fix：保留 nick→uid 映射（断线不删），同名重连复用同一 uid
                for tok, token_sess in list(self.web_tokens.items()):
                    if token_sess.uid == sess.uid:
                        del self.web_tokens[tok]
                for gid, g in list(self.groups.items()):
                    if sess.uid in g["members"]:
                        del g["members"][sess.uid]
                        g["admins"].discard(sess.uid)
                        g["mutes"].pop(sess.uid, None)
                        if not g["members"]:
                            dissolved.append(gid)
                        elif g["owner"] == sess.uid:
                            # 转让群主：优先管理员，其次最早成员；前群主不当管理员
                            cands = [u for u in g["members"] if u in g["admins"]]
                            if not cands:
                                cands = list(g["members"])
                            new_owner = cands[0]
                            g["owner"] = new_owner
                            g["admins"].discard(new_owner)
            elif self.sessions.get(sess.uid) is sess:
                # 仍有其它端在线但本会话是代表 → 换一个仍在线者作代表
                self.sessions[sess.uid] = next(iter(clients))
        for gid in dissolved:
            with self.lock:
                self.groups.pop(gid, None)
                self.voice_rooms.pop(f"group:{gid}", None)   # R72：群解散连同语音房名册
        sess.closed = True
        self.audit.log(type="logout", uid=sess.uid, nick=sess.nick,
                       reason=reason, via=sess.type)
        for other, payload in self._drop_xfers_of(sess.uid):
            self._send_to(other, payload)
        self._broadcast_roster()
        if self.sessions.get(sess.uid) is None:          # 本 uid 已完全离线
            self._broadcast_system(f"{sess.nick} 已下线")
            self._drop_voice_rooms(sess.uid)             # R72：离线即退出所有语音房
        self._broadcast_group_list()
        affected = self.rooms.on_disconnect(sess.uid)
        for rid in affected:
            room = self.rooms.room_for(rid)
            if room:
                self._send_room_state(room, events=["有玩家离开房间"])
        if affected:
            self._broadcast_game_list()

    def _session_is_active(self, sess: Session) -> bool:
        """判断会话是否仍属于 Hub。

        已注销会话会被标记 closed；真实在线会话必须仍在该 uid 的在线集，
        或仍是 ``sessions`` 中的代表。没有任何 Hub 注册记录的对象一律拒绝，
        防止已断开的 TCP 读循环在 close_conn 生效前继续提交消息。
        """
        with self.lock:
            if getattr(sess, "closed", False):
                return False
            clients = self._uid_clients.get(sess.uid)
            return ((clients is not None and sess in clients)
                    or self.sessions.get(sess.uid) is sess
                    # 一些历史测试替身在 attach 后会改写 uid；仍以对象
                    # 身份确认它确实留在 Hub 的代表映射里。
                    or any(candidate is sess
                           for candidate in self.sessions.values()))

    # ---------- 消息分发 ----------
    def dispatch(self, sess: Session, header: dict, body: bytes = b"") -> bool:
        """处理一帧；返回 False 表示应断开连接"""
        t = header.get("t")
        if sess.uid == 0:
            if t == MsgType.HELLO.value:
                return self._on_hello(sess, header)
            self._error(sess, "auth", "请先发送 hello 登录")
            return False
        if not self._session_is_active(sess):
            # close_conn 可能尚未来得及终止底层读循环；拒绝该帧，避免被删账号
            # 继续借用旧 TCP 会话发消息。已 closed 的会话不再回写错误帧。
            if not getattr(sess, "closed", False):
                self._error(sess, "auth", "会话已失效")
            return False
        if t == MsgType.PING.value:
            sess.send({"t": "pong"})
        elif t == MsgType.BLOCK_SET.value:
            self._on_block_set(sess, header)      # R50：屏蔽/解除
        elif t == MsgType.BLOCK_LIST.value:
            self._on_block_list(sess)             # R50：拉取我的屏蔽名单
        elif t == MsgType.SCHED_SET.value:
            self._on_sched_set(sess, header)      # R51：服务器权威定时消息
        elif t == MsgType.SCHED_CANCEL.value:
            self._on_sched_cancel(sess, header)   # R51：取消定时消息
        elif t == MsgType.SCHED_LIST.value:
            self._on_sched_list(sess)             # R51：拉取我的待发列表
        elif t == MsgType.CHAT.value:
            self._on_chat(sess, header)
        elif t == MsgType.TYPING.value:
            self._on_typing(sess, header)
        elif t == MsgType.NUDGE.value:
            self._on_nudge(sess, header)
        elif t == MsgType.SHAKE.value:
            self._on_shake(sess, header)
        elif t == MsgType.STATUS_SET.value:
            self._on_status_set(sess, header)     # R68：在线状态（在线/离开/忙碌）
        elif t == MsgType.REMARK_SET.value:
            self._on_remark_set(sess, header)     # R69C9：好友备注名（本人视角）
        elif t == MsgType.POLL.value:
            self._on_poll_create(sess, header)
        elif t == MsgType.POLL_VOTE.value:
            self._on_poll_vote(sess, header)
        elif t == MsgType.MSG_EDIT.value:
            self._on_edit(sess, header)
        elif t == MsgType.MSG_DEL.value:
            self._on_del(sess, header)
        elif t == MsgType.REACTION.value:
            self._on_reaction(sess, header)
        elif t == MsgType.READ.value:
            self._on_read(sess, header)
        elif t == MsgType.READ_DETAIL.value:
            self._on_read_detail(sess, header)
        elif t == MsgType.MSG_READERS.value:
            self._on_msg_readers(sess, header)
        elif t == MsgType.PIN.value:
            self._on_pin(sess, header)
        elif t == MsgType.PURGE.value:
            self._on_purge(sess, header)
        elif t == MsgType.DRAFT_SET.value:
            self._on_draft_set(sess, header)      # R29B：草稿同步
        elif t == MsgType.HISTORY.value:
            self._on_history(sess, header)
        elif t == MsgType.THREAD_FETCH.value:
            self._on_thread_fetch(sess, header)   # R34：话题回复拉取
        elif t == MsgType.GROUP_CREATE.value:
            self._on_group_create(sess, header)
        elif t == MsgType.GROUP_JOIN.value:
            self._on_group_join(sess, header)
        elif t == MsgType.GROUP_LEAVE.value:
            self._on_group_leave(sess, header)
        elif t == MsgType.GROUP_KICK.value:
            self._on_group_kick(sess, header)
        elif t == MsgType.GROUP_MUTE.value:
            self._on_group_mute(sess, header)
        elif t == MsgType.GROUP_SLOW.value:
            self._on_group_slow(sess, header)
        elif t == MsgType.GROUP_SET_ADMIN.value:
            self._on_group_set_admin(sess, header)
        elif t == MsgType.GROUP_ANNOUNCE.value:
            self._on_group_announce(sess, header)
        elif t == MsgType.GROUP_ANN_MODE.value:
            self._on_group_ann_mode(sess, header)
        elif t == MsgType.GROUP_INVITE_GET.value:
            self._on_group_invite_get(sess, header)
        elif t == MsgType.GROUP_JOIN_INVITE.value:
            self._on_group_join_invite(sess, header)
        elif t == MsgType.GROUP_RENAME.value:
            self._on_group_rename(sess, header)
        elif t == MsgType.GROUP_ABOUT.value:
            self._on_group_about(sess, header)                # R9H：群简介
        elif t == MsgType.GROUP_AVATAR_SET.value:
            self._on_group_avatar_set(sess, header, body)     # R9H：群头像上传
        elif t == MsgType.GROUP_AVATAR_DEL.value:
            self._on_group_avatar_del(sess, header)           # R9H：清空群头像
        elif t == MsgType.GROUP_AVATAR_GET.value:
            self._on_group_avatar_get(sess, header)           # R9H：拉取群头像
        elif t == MsgType.GROUP_FILE_LIST.value:
            self._on_group_file_list(sess, header)            # 群文件列表
        elif t == MsgType.GROUP_FILE_UPLOAD_START.value:
            self._on_group_file_upload_start(sess, header)    # 群文件上传起始
        elif t == MsgType.GROUP_FILE_UPLOAD.value:
            self._on_group_file_upload(sess, header, body)    # 群文件块
        elif t == MsgType.GROUP_FILE_UPLOAD_DONE.value:
            self._on_group_file_upload_done(sess, header)     # 群文件收尾
        elif t == MsgType.GROUP_FILE_DEL.value:
            self._on_group_file_del(sess, header)             # 删群文件
        elif t == MsgType.GROUP_FILE_GET.value:
            self._on_group_file_get(sess, header)             # 下载群文件
        elif t == MsgType.TASK_ADD.value:
            self._on_task_add(sess, header)                   # R69B6/B7 发起任务
        elif t == MsgType.TASK_DO.value:
            self._on_task_do(sess, header)                    # 参与/打卡
        elif t == MsgType.TASK_LIST.value:
            self._on_task_list(sess, header)                  # 拉取清单
        elif t == MsgType.TASK_DEL.value:
            self._on_task_del(sess, header)                   # 关闭任务
        elif t == MsgType.VOICE.value:
            self._on_voice(sess, header, body)
        elif t == MsgType.VMEMO.value:
            self._on_vmemo(sess, header, body)                # R72 圆形视频留言
        elif t == MsgType.GEO_LIVE.value:
            self._on_geo_live(sess, header)                   # R72 实时位置刷新
        elif t == MsgType.GEO_STOP.value:
            self._on_geo_stop(sess, header)                   # R72 停止位置共享
        elif t == MsgType.STICKER_LIST.value:
            sess.send({"t": "sticker_list", "stickers": self.stickers,
                       "custom_stickers": self._custom_list(),
                       "sticker_pack_meta": self._pack_meta_payload()})
        elif t == MsgType.STICKER_CUSTOM_ADD.value:
            self._on_sticker_custom_add(sess, header, body)   # R30C
        elif t == MsgType.STICKER_CUSTOM_DEL.value:
            self._on_sticker_custom_del(sess, header)         # R30C
        elif t == MsgType.STICKER_CUSTOM_GET.value:
            self._on_sticker_custom_get(sess, header)         # R30C
        elif t == MsgType.STICKER_PACK_RENAME.value:          # R64 贴纸包深化
            self._on_sticker_pack_rename(sess, header)
        elif t == MsgType.STICKER_PACK_DEL.value:
            self._on_sticker_pack_del(sess, header)
        elif t == MsgType.STICKER_PACK_COVER.value:
            self._on_sticker_pack_cover(sess, header, body)
        elif t == MsgType.STICKER_PACK_COVER_GET.value:
            self._on_sticker_pack_cover_get(sess, header)
        elif t == MsgType.STICKER_REORDER.value:
            self._on_sticker_reorder(sess, header)
        elif t == MsgType.STICKER_SHOP.value:
            self._on_sticker_shop(sess, header)               # R35 贴纸商店
        elif t == MsgType.STICKER_SUB.value:
            self._on_sticker_sub(sess, header)                # R35 订阅/退订包
        elif t == MsgType.E2EE_PUB.value:
            self._on_e2ee_pub(sess, header)                   # R36 密聊握手
        elif t == MsgType.E2EE_PUB_ACK.value:
            self._on_e2ee_pub_ack(sess, header)               # R36 密聊握手应答
        elif t == MsgType.E2EE_CHAT.value:
            self._on_e2ee_chat(sess, header, body)            # R36 密聊透传
        elif t == MsgType.E2EE_GROUP.value:
            self._on_e2ee_group(sess, header, body)           # R36 群密聊透传
        elif t == MsgType.E2EE_SK_DIST.value:
            self._on_e2ee_sk_dist(sess, header)               # R36 sender key 分发
        elif t == MsgType.E2EE_SK_REQ.value:
            self._on_e2ee_sk_req(sess, header)                # R36 密钥补发请求
        elif t == MsgType.CALL_RING.value:
            self._on_call_ring(sess, header)                  # R38 语音信令
        elif t == MsgType.CALL_ACCEPT.value:
            self._on_call_simple(sess, header, MsgType.CALL_ACCEPT.value)
        elif t == MsgType.CALL_REJECT.value:
            self._on_call_simple(sess, header, MsgType.CALL_REJECT.value)
        elif t == MsgType.CALL_READY.value:
            self._on_call_ready(sess, header)                 # R38 回填 ip 转发
        elif t == MsgType.CALL_END.value:
            self._on_call_simple(sess, header, MsgType.CALL_END.value)
        elif t == MsgType.ROOM_JOIN.value:
            self._on_room_join(sess, header)                  # R72 语音房入房
        elif t == MsgType.ROOM_LEAVE.value:
            self._on_room_leave(sess, header)                 # R72 语音房退房
        elif t == MsgType.ROOM_ADDR.value:
            self._on_room_addr(sess, header)                  # R72 上报 UDP 端口
        elif t == MsgType.CLOUD_PUT.value:
            self._on_cloud_put(sess, header, body)            # R37 云历史上传
        elif t == MsgType.CLOUD_GET.value:
            self._on_cloud_get(sess)                          # R37 云历史拉取
        elif t == MsgType.FILE_OFFER.value:
            self._on_file_offer(sess, header)
        elif t == MsgType.FILE_ACCEPT.value:
            self._on_file_accept(sess, header)
        elif t == MsgType.FILE_REJECT.value:
            self._on_file_reject(sess, header)
        elif t == MsgType.FILE_LISTEN.value:
            self._on_file_listen(sess, header)
        elif t == MsgType.FILE_DIRECT_OK.value:
            self._on_file_direct_ok(sess, header)
        elif t == MsgType.FILE_DATA.value:
            self._on_file_data(sess, header, body)
        elif t == MsgType.FILE_CHUNK_ACK.value:
            self._on_file_chunk_ack(sess, header)
        elif t == MsgType.FILE_VERIFY.value:
            self._on_file_verify(sess, header)
        elif t == MsgType.FILE_CANCEL.value:
            self._on_file_cancel(sess, header)
        elif t == MsgType.GAME_LIST.value:
            sess.send(self._game_list_payload())
        elif t == MsgType.GAME_CREATE.value:
            self._on_game_create(sess, header)
        elif t == MsgType.GAME_JOIN.value:
            self._on_game_join(sess, header, spectate=False)
        elif t == MsgType.GAME_SPECTATE.value:
            self._on_game_join(sess, header, spectate=True)
        elif t == MsgType.GAME_LEAVE.value:
            self._on_game_leave(sess, header)
        elif t == MsgType.GAME_START.value:
            self._on_game_start(sess, header)
        elif t == MsgType.GAME_ACTION.value:
            self._on_game_action(sess, header)
        elif t == MsgType.GAME_SYNC.value:
            self._on_game_sync(sess, header)      # R49：补拉房间状态
        elif t == MsgType.FISH_SCORE.value:
            self._on_fish_score(sess, header)     # R70H：上报摸鱼积分（opt-in）
        elif t == MsgType.FISH_BOARD.value:
            self._on_fish_board_get(sess, header)  # R70H：拉取排行榜
        elif t == MsgType.SET_PWD.value:
            self._on_set_pwd(sess, header)            # R47：昵称密码
        elif t == MsgType.AVATAR_SET.value:
            self._on_avatar_set(sess, header, body)   # R52：上传头像
        elif t == MsgType.AVATAR_DEL.value:
            self._on_avatar_del(sess)                 # R52：删除头像
        elif t == MsgType.AVATAR_GET.value:
            self._on_avatar_get(sess, header)         # R52：拉取头像
        elif t == MsgType.SIGN_SET.value:
            self._on_sign_set(sess, header)           # R52：设置个性签名
        elif t == MsgType.ADMIN_KICK.value:
            self._on_admin_kick(sess, header)         # R53：管理员踢人下线
        elif t == MsgType.CLEAR_ALL.value:
            self._on_admin_clear_all(sess)            # R53：管理员清空全部记录
        elif t == MsgType.CLEAR_UID.value:
            self._on_admin_clear_uid(sess, header)    # R53：管理员清空指定用户消息
        elif t == MsgType.ADMIN_GROUPS.value:
            self._on_admin_groups(sess)               # 管理员：群目录+成员花名册
        elif t == MsgType.ADMIN_GROUP_SET.value:
            self._on_admin_group_set(sess, header)    # 管理员：增删成员/解散群
        elif t == MsgType.ADMIN_USER_GET.value:
            self._on_admin_user_get(sess, header)     # 管理员：查某人信息+所属群
        elif t == MsgType.ADMIN_USER_DEL.value:
            self._on_admin_user_del(sess, header)     # 管理员：清除用户（删除账号）
        elif t == MsgType.INV_SET.value:
            self._on_invis_set(sess, header)          # R56：隐身上线开关
        elif t == MsgType.ADMIN_INVIS_SET.value:
            self._on_admin_invis_set(sess, header)    # R56B：管理员强制显身/隐身
        elif t == MsgType.MOMENT_PUBLISH.value:
            self._on_moment_publish(sess, header, body)   # 朋友圈：发图文动态
        elif t == MsgType.MOMENT_LIKE.value:
            self._on_moment_like(sess, header)            # 朋友圈：点赞/取消
        elif t == MsgType.MOMENT_COMMENT.value:
            self._on_moment_comment(sess, header)         # 朋友圈：评论
        elif t == MsgType.MOMENT_DEL.value:
            self._on_moment_del(sess, header)             # 朋友圈：删除自己的动态
        elif t == MsgType.MOMENT_FEED.value:
            self._on_moment_feed(sess)                    # 朋友圈：拉全量时间轴
        elif t == MsgType.MOMENT_IMG_GET.value:
            self._on_moment_img_get(sess, header)         # 朋友圈：拉动态图片
        elif t == MsgType.MOMENT_COVER_SET.value:
            self._on_moment_cover_set(sess, header, body) # 朋友圈：设封面（预设/上传）
        elif t == MsgType.MOMENT_COVER_GET.value:
            self._on_moment_cover_get(sess)               # 朋友圈：拉我的封面
        elif t == MsgType.MOMENT_COVER_DEL.value:
            self._on_moment_cover_del(sess)               # 朋友圈：恢复默认封面
        elif t == MsgType.PADDING.value:
            pass
        elif t == MsgType.HELLO.value:
            self._error(sess, "dup", "重复登录")
            return False
        else:
            self._error(sess, "unknown", f"未知消息类型: {t}")
        return True

    def _on_hello(self, sess: Session, header: dict) -> bool:
        nick = (header.get("nick") or "").strip()[:MAX_NICK_LEN]
        if not nick:
            self._error(sess, "nick", "昵称不能为空")
            return False
        pwd = str(header.get("pwd") or "")     # R47-B：可选昵称密码
        err = self._pwd_check_for_login(nick, pwd)
        if err:
            self._error(sess, "pwd", err)      # 客户端据此弹密码框
            return False
        sess.nick = nick
        # 只有通过部署凭据校验才能到达这里。
        # 须在 _attach（发送 welcome 帧）之前赋值，否则 welcome 的 is_admin 恒为 False。
        sess.is_admin = (nick == self._admin_nick)
        self._attach(sess)                  # 同账号多端并存：登记不再失败
        if pwd and not sess.is_admin:
            self._pwd_claim(sess.uid, pwd)
        return True

    # ---------- R59 富文本：白名单清洗（只透传有限种类，防 UI 注入） ----------
    _RICH_KINDS = ("plain", "mention", "link", "hashtag", "bold", "italic",
                   "code", "spoiler")

    def _san_rich(self, raw, text: str) -> list | None:
        """把客户端 rich（[[text,kind,href],...]）白名单清洗后返回；无/畸形 → None。

        仅接受允许种类、文本非空，href 仅允许 http(s)/www 链接。旧端无 rich → None。
        """
        if not isinstance(raw, list) or not text:
            return None
        out = []
        for item in raw:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            t = str(item[0])
            k = str(item[1])
            if not t or k not in self._RICH_KINDS:
                continue
            href = ""
            if len(item) > 2 and item[2]:
                hs = str(item[2]).strip()
                hs = hs if hs.lower().startswith(("http://", "https://", "www.")) else ""
                href = hs
            out.append([t, k, href])
        return out if out else None

    def _san_geo(self, raw) -> dict:
        """R72 位置卡片清洗：坐标非法则整体丢弃（返回 {}）；其余字段截断归一。

        实时共享的 expire 被夹在 [now+5min, now+1h]，防对端伪造「永久共享」。
        """
        if not isinstance(raw, dict):
            return {}
        try:
            lat = float(raw.get("lat"))
            lon = float(raw.get("lon"))
        except (TypeError, ValueError):
            return {}
        if not (abs(lat) <= 90.0 and abs(lon) <= 180.0):
            return {}
        geo = {"lat": round(lat, 6), "lon": round(lon, 6)}
        name = raw.get("name")
        if isinstance(name, str) and name.strip():
            geo["name"] = name.strip()[:self.cfg.geo_name_max]
        if raw.get("live"):
            geo["live"] = 1
            now = _now()
            try:
                exp = float(raw.get("expire") or 0.0)
            except (TypeError, ValueError):
                exp = 0.0
            geo["expire"] = round(min(max(exp, now + self.cfg.geo_live_ttl), now + 3600.0), 3)
            sid = raw.get("session")
            if isinstance(sid, str) and sid.strip():
                geo["session"] = sid.strip()[:32]
        return geo

    def _on_chat(self, sess: Session, header: dict) -> None:
        channel = header.get("channel") or "public"
        if channel not in ("public", "private", "group"):
            self._error(sess, "channel", "未知频道")
            return
        text = (header.get("text") or "").strip()
        sticker = (header.get("sticker") or "").strip()
        f = header.get("file")          # R23 网页端图片/文件消息：{fid,name,size,kind}
        if isinstance(f, dict):
            meta = self._web_file_meta(str(f.get("fid") or ""))
            if not meta:
                self._error(sess, "file", "文件不存在或已过期")
                return
            f = {k: meta[k] for k in ("fid", "name", "size", "kind")}
        else:
            f = None
        # R71 联系人名片：header 带 card={uid,nick} → 白名单化（只留 uid/nick，且须两者齐全）。
        # 放在 empty 校验之前：纯名片消息（无文本/贴纸/文件）也应合法（对齐微信名片）。
        # 头像不随帧下发——接收端按 uid 走 AVATAR_GET 取图，免得帧体膨胀 + 伪造头像。
        card = {}
        _c = header.get("card")
        if isinstance(_c, dict):
            _cu = _c.get("uid")
            if isinstance(_cu, bool):               # bool 是 int 子类，先剔除
                _cu = None
            if isinstance(_cu, str) and _cu.isdigit():
                _cu = int(_cu)
            _cn = _c.get("nick")
            if isinstance(_cu, int) and isinstance(_cn, str) and _cn.strip():
                card = {"uid": _cu, "nick": _cn.strip()[:MAX_NICK_LEN]}
        # R72 位置卡片：header 带 geo={lat,lon,name,live,expire,session} → 白名单清洗。
        # 与 card 同款：非法经纬度整体丢弃（不拒整条消息），保证「位置」永远只是附带信息。
        geo = self._san_geo(header.get("geo"))
        if (not text and not sticker and not f and not header.get("fwd_seqs")
                and not card and not geo):
            self._error(sess, "empty", "消息不能为空")
            return
        if len(text) > self.cfg.chat_text_max:
            self._error(sess, "long", "消息过长")
            return
        if sticker and not stickers.is_valid(sticker):
            self._error(sess, "sticker", "未知表情")
            return
        msg = {"t": "chat", "channel": channel, "uid": sess.uid,
               "nick": sess.nick, "ts": round(_now(), 3)}
        if text:
            msg["text"] = text
        r59 = self._san_rich(header.get("rich"), text)     # R59：富文本段（白名单）
        if r59:
            msg["rich"] = r59
        if sticker:
            msg["sticker"] = sticker
        if f:
            msg["file"] = f
        reply = header.get("reply")
        if isinstance(reply, dict):          # C4 引用回复：客户端附快照，服务器透传
            safe = {k: reply.get(k) for k in ("nick", "text", "seq")
                    if reply.get(k) is not None}
            if safe.get("nick") or safe.get("text"):
                msg["reply"] = safe
        fwd = header.get("forward")
        if isinstance(fwd, dict):            # R13 转发：客户端附原消息快照，服务器透传
            safe = {k: fwd.get(k) for k in ("nick", "text", "sticker", "seq")
                    if fwd.get(k) is not None}
            if safe.get("nick") or safe.get("text"):
                msg["forward"] = safe
        # R64 合并转发：客户端只提交「源会话 + 源消息 seq」，条目一律由服务器
        # 按真实历史聚合（客户端无从伪造昵称/正文）；源会话同样过权限校验。
        fwd_seqs = header.get("fwd_seqs")
        if isinstance(fwd_seqs, list) and fwd_seqs:
            src = header.get("fwd_from")
            src = src if isinstance(src, dict) else {}
            s_ch = src.get("type")
            if s_ch not in ("public", "private", "group"):
                s_ch = "public"
            s_to = (src.get("uid") if s_ch == "private"
                    else src.get("gid") if s_ch == "group" else None)
            skey = self._history_key(sess, s_ch, s_to)
            pool = {}
            if skey:
                pool = {m.get("seq"): m for m in self.bus.history(skey)}
            safe_items = []
            for s in fwd_seqs[:30]:          # 条数硬上限（与客户端一致）
                if isinstance(s, bool) or not isinstance(s, int):
                    continue
                m = pool.get(s)
                if not m:
                    continue                  # 源消息不可见/不存在 → 跳过
                si = {"nick": str(m.get("nick") or "?")[:MAX_NICK_LEN],
                      "text": str(m.get("text") or "")[:200]}   # 单条文本上限
                if m.get("ts") is not None:
                    si["ts"] = m["ts"]
                if si["text"]:
                    safe_items.append(si)
            if safe_items:
                msg["fp"] = {"n": len(safe_items), "items": safe_items}
        if not text and not sticker and not f and not card and "fp" not in msg:
            self._error(sess, "empty", "消息不能为空")   # 纯 fp 但过滤后为空同样拒绝
            return
        if channel == "private":
            to = header.get("to")
            to = int(to) if isinstance(to, int) else None
            if to is None:
                try:
                    to = int(header.get("to"))
                except (TypeError, ValueError):
                    to = None
            # R35 Bots：私聊发往 bot → 拦截处理（bot 不在 sessions，正常路径会误报 offline）
            if to is not None and _bots.is_bot(to):
                self._bot_dispatch(sess, header, to)
                return
            # R50 屏蔽：目标把我拉黑 → 拒收（仅私聊；群内发言不受个人屏蔽影响）
            if to is not None and to != sess.uid and self._is_blocked_by(sess.uid, to):
                self._error(sess, "blocked", "你已被对方屏蔽，消息未送达")
                return
            # R25C 收藏夹「发给自己」：to==自己 视为收藏夹消息，无需对方在线
            # R63 离线留言：仅当目标是【非会话且从未登记】的未知 uid 才拒绝；
            # 对离线好友（_known_uid 为真，曾登录登记过）放行，消息照常 publish
            # 进 bus 历史；私聊历史 key 双向归一化，对方上线拉该会话历史即可看到。
            if to is None:
                self._error(sess, "offline", "对方不在线")
                return
            if to != sess.uid and not self._known_uid(to):
                self._error(sess, "offline", "对方不在线")
                return
            msg["to"] = to
        elif channel == "group":
            gid = header.get("to")
            g = self.groups.get(gid)
            if not g or sess.uid not in g["members"]:
                self._error(sess, "group", "不在该群或群不存在")
                return
            # R26B 频道广播：仅创建者可发言（成员只读）
            # R71：只拦「发贴」——带 thread_root 的回复放行，交给下文 thread_root 校验
            # （根消息须属本频道 key 且非嵌套）；非创建者无法在频道内造根消息，
            # 故放开后也只能评论创建者的贴，不会越权发贴。
            if (g.get("kind") == "channel" and sess.uid != g["owner"]
                    and header.get("thread_root") is None):
                self._error(sess, "readonly", "频道仅创建者可发言")
                return
            # C8：禁言检查（mutes: uid -> 禁言截止时间；过期条目惰性视为已解禁）
            mute_until = g["mutes"].get(sess.uid)
            if mute_until is not None and _now() < mute_until:
                self._error(sess, "muted", "你已被禁言，无法在群内发言")
                return
            msg["to"] = gid
            msg["group_name"] = g["name"]
            # C9① 仅公告说话模式：非群主/管理员只能发「公告引用互动」——
            # 即回复引用置顶公告那条消息（pins["group:{gid}"].seq）；普通正文一律拒绝。
            if g.get("announce_mode"):
                with self.lock:
                    pinsnap = self.pins.get(f"group:{gid}") or {}
                if self._group_role(g, sess.uid) not in ("owner", "admin"):
                    ann_seq = pinsnap.get("seq")
                    rply = msg.get("reply") or {}
                    if ann_seq is None or rply.get("seq") != ann_seq:
                        self._error(sess, "announce_only",
                                    "本群为仅公告说话模式，普通成员只能回复引用公告")
                        return
            # R70D 群慢速模式：非 owner/管理员在档位内二次发言被拒（禁言>仅公告>慢速）
            slow = int(g.get("slow") or 0)
            # R71：话题回复豁免慢速（慢速防主频道刷屏；频道评论属异步讨论）
            if (slow > 0 and header.get("thread_root") is None
                    and self._group_role(g, sess.uid) not in ("owner", "admin")):
                now = _now()
                with self.lock:
                    if self.groups.get(gid) is not g:
                        return
                    last = (g.get("slow_last") or {}).get(sess.uid, 0)
                    if now - last < slow:
                        self._error(sess, "slow", "群慢速模式，请稍后再发")
                        return
                    g.setdefault("slow_last", {})[sess.uid] = now
            # R14 群 @提及 & @全员：按成员昵称匹配 @token，产出被提及 uid 集合
            with self.lock:
                members = dict(g["members"])
            if "@" in text:
                # 识别 @全体/@全员/@所有人 → 群内全员广播（带 everyone 通知标记）
                if re.search(r"@\s*(全体|全员|所有人)", text):
                    msg["everyone"] = True
                compact = text.replace(" ", "").replace("　", "")
                mentioned = []
                for mu, mnick in members.items():
                    if mnick and ("@" + mnick.replace(" ", "").replace("　", "")) in compact:
                        mentioned.append(mu)
                if mentioned:
                    msg["mentions"] = mentioned
        # R26C 静默发送：header 带 silent → 消息透传标记（接收端免通知，未读照常）
        if header.get("silent"):
            msg["silent"] = True
        # R70E 消息伪装：header 带 disguise（白名单风格）→ 仅透传外观标记，数据/搜索仍走原文
        dis = header.get("disguise")
        if dis:
            if dis not in self.cfg.disguise_styles:
                self._error(sess, "disguise", "未知的伪装风格")
                return
            msg["disguise"] = dis
        # R70G 忙碌自动回复：header 带 auto → 透传标记（接收端据此不再触发自动回复，防环路）
        if header.get("auto"):
            msg["auto"] = True
        # R14 阅后即焚：header 带 burn → 消息透传标记（Web/桌面接收端据此渲染 🔥）
        if header.get("burn"):
            msg["burn"] = True
        # R71 联系人名片：白名单化后的 {uid,nick} 透传（校验见上文 empty 校验处）
        if card:
            msg["card"] = card
        # R72 位置卡片：白名单化后的 {lat,lon,name,live,expire,session} 透传
        if geo:
            msg["geo"] = geo
        # R34 群内话题：header 带 thread_root（根消息 seq）→ 校验同频道存在且非嵌套后透传
        tr = header.get("thread_root")
        if tr is not None:
            try:
                tr_i = int(tr)
            except (TypeError, ValueError):
                self._error(sess, "thread", "thread_root 无效")
                return
            key = ChatBus.key(channel, sess.uid, msg.get("to"))
            _k, root = self.bus.find(tr_i)
            if root is None or _k != key:
                self._error(sess, "thread", "话题根消息不存在或不在本频道")
                return
            if root.get("thread_root"):
                self._error(sess, "thread", "不支持在话题回复内再开话题")
                return
            msg["thread_root"] = tr_i
        msg = self.bus.publish(msg)
        self._route(msg)
        # R26D 链接预览：先投递 chat，再补发 preview（缓存命中时同步、否则后台抓取），
        # 保证客户端按 chat → preview 顺序收帧，本地历史/渲染一致。
        if text and not msg.get("preview"):
            m = _URL_RE.search(text)
            if m:
                self._maybe_fetch_preview(m.group(0).rstrip(".,;:!?）)]}"), msg)
        # R14 阅后即焚：全部收件方读到后由服务器删除（含发送方，发送方视为已读）
        if header.get("burn") and msg.get("channel") in ("public", "private", "group"):
            # 锁内修改共享 _burn：多连接线程并发发 burn，防丢失
            with self.lock:
                recp = {u for u, _s in self._chan_recipients(
                    msg["channel"], msg.get("uid"), msg.get("to"))}
                recp.discard(sess.uid)
                self._burn[msg["seq"]] = {"channel": msg["channel"], "uid": msg.get("uid"),
                                          "to": msg.get("to"), "ts": msg.get("ts", _now()),
                                          "pend": recp}
        self.audit.log(type="chat", uid=sess.uid, nick=sess.nick, channel=channel,
                       to=msg.get("to"), seq=msg["seq"], length=len(text))
        self._persist()                              # R16：消息/阅后即焚落盘

    # ---------- R35 内置 Bots ----------
    def _bot_dispatch(self, sess: Session, header: dict, bot_uid: int) -> None:
        """R35 Bots：私聊发往 bot → 用户消息正常入历史/路由（发送方看到回显），
        再由 bot 解析命令并经 bot_say 回复；不走 offline 校验、无阅后即焚/话题。"""
        bot = _bots.BOT_BY_UID.get(bot_uid)
        if bot is None:
            return
        text = (header.get("text") or "").strip()
        msg = self.bus.publish({"t": "chat", "channel": "private", "uid": sess.uid,
                                "nick": sess.nick, "ts": round(_now(), 3),
                                "to": bot_uid, "text": text})
        self._route(msg)
        self.audit.log(type="bot", uid=sess.uid, nick=sess.nick, to=bot_uid,
                       seq=msg["seq"], length=len(text))
        try:
            replies = bot.handle(self, msg) or []
        except Exception as e:                        # bot 命令解析异常不致命
            replies = [f"（{bot.nick} 出错了：{e}）"]
        for r in replies:
            # R46：bot 回复可为 str 或 (text, kb) 元组（kb=inline 键盘）
            if isinstance(r, tuple) and len(r) == 2:
                self.bot_say(bot, sess.uid, r[0], kb=r[1])
            else:
                self.bot_say(bot, sess.uid, r)

    def bot_say(self, bot, to_uid: int, text: str, kb=None) -> None:
        """R35：bot 以私聊身份回复（bus.publish 入历史 + 正常路由，
        对客户端就是一条普通 CHAT 私聊，无需感知 bot 协议）。
        R46：kb=inline 键盘（[[{t,c}],...]），仅是消息上的可选字段。"""
        msg = {"t": "chat", "channel": "private", "uid": bot.uid,
               "nick": bot.nick, "ts": round(_now(), 3),
               "to": to_uid, "text": text}
        if kb:                                        # R46：键盘随消息走（历史/快照天然保留）
            msg["kb"] = kb
        msg = self.bus.publish(msg)
        self._route(msg)
        self._persist()

    def _on_typing(self, sess: Session, header: dict) -> None:
        """R25A 正在输入：校验频道成员后广播给应收方（不落历史、不入审计）。
        限速 1s/人：仅转发该 uid 每秒最多一帧，防客户端 bug 刷屏。"""
        channel = header.get("channel") or "public"
        if channel not in ("public", "private", "group"):
            return                                   # 非法频道静默忽略
        now = _now()
        with self.lock:
            if now - self._typing_ts.get(sess.uid, 0.0) < 1.0:
                return                               # 限速：忽略高频帧
            self._typing_ts[sess.uid] = now
            if channel == "private":
                to = header.get("to")
                try:
                    to = int(to)
                except (TypeError, ValueError):
                    return
                if to != sess.uid and self.sessions.get(to) is None:
                    return                           # 对方不在线不广播
            elif channel == "group":
                g = self.groups.get(header.get("to"))
                if not g or sess.uid not in g["members"]:
                    return
                to = g["gid"]
            else:
                to = None
        for _u, s in self._chan_recipients(channel, sess.uid, to):
            if s.uid == sess.uid:
                continue                             # 不把 typing 回给自己
            try:
                s.send({"t": MsgType.TYPING.value, "channel": channel,
                        "uid": sess.uid, "nick": sess.nick, "to": to,
                        "ts": round(now, 3)})
            except Exception:
                pass

    def _on_nudge(self, sess: Session, header: dict) -> None:
        """R67 拍一拍：校验频道成员后广播给应收方（含被拍者，不含拍者；不入历史、不入审计）。
        限速 5s/人：仅转发该 uid 每 5 秒最多一帧，防骚扰刷屏。"""
        channel = header.get("channel") or "public"
        if channel not in ("public", "private", "group"):
            return                                   # 非法频道静默忽略
        now = _now()
        with self.lock:
            if now - self._nudge_ts.get(sess.uid, 0.0) < 5.0:
                return                               # 限速：忽略高频帧
            self._nudge_ts[sess.uid] = now
            if channel == "private":
                to = header.get("to")
                try:
                    to = int(to)
                except (TypeError, ValueError):
                    return
                if to != sess.uid and self.sessions.get(to) is None:
                    return                           # 对方不在线不广播（同 typing）
            elif channel == "group":
                g = self.groups.get(header.get("to"))
                if not g or sess.uid not in g["members"]:
                    return
                to = g["gid"]
            else:
                to = None
        target = header.get("target")
        try:
            target = int(target) if target is not None else None
        except (TypeError, ValueError):
            target = None
        # target_nick：群内取成员表，其余取 known；无则回退 "用户{uid}"
        target_nick = ""
        if target is not None:
            if channel == "group" and to is not None:
                g = self.groups.get(to)
                target_nick = (g or {}).get("members", {}).get(target, "") or \
                    (self.known.get(target) or {}).get("nick", "")
            else:
                target_nick = (self.known.get(target) or {}).get("nick", "")
            if not target_nick:
                target_nick = f"用户{target}"
        for _u, s in self._chan_recipients(channel, sess.uid, to):
            if s.uid == sess.uid:
                continue                             # 不把 nudge 回给自己（发送端本地乐观渲染）
            try:
                s.send({"t": MsgType.NUDGE.value, "channel": channel,
                        "uid": sess.uid, "nick": sess.nick, "to": to,
                        "target": target, "target_nick": target_nick,
                        "ts": round(now, 3)})
            except Exception:
                pass

    def _on_shake(self, sess: Session, header: dict) -> None:
        """R68 窗口抖动：校验频道成员后广播给应收方（不含发送者；不入历史、不入审计）。
        限速 10s/人：仅转发该 uid 每 10 秒最多一帧，防骚扰。"""
        channel = header.get("channel") or "public"
        if channel not in ("public", "private", "group"):
            return                                   # 非法频道静默忽略
        now = _now()
        with self.lock:
            if now - self._shake_ts.get(sess.uid, 0.0) < 10.0:
                return                               # 限速：忽略高频帧
            self._shake_ts[sess.uid] = now
            if channel == "private":
                to = header.get("to")
                try:
                    to = int(to)
                except (TypeError, ValueError):
                    return
                if to != sess.uid and self.sessions.get(to) is None:
                    return                           # 对方不在线不广播
            elif channel == "group":
                g = self.groups.get(header.get("to"))
                if not g or sess.uid not in g["members"]:
                    return
                to = g["gid"]
            else:
                to = None
        for _u, s in self._chan_recipients(channel, sess.uid, to):
            if s.uid == sess.uid:
                continue                             # 不回给自己（发送端本地提示）
            try:
                s.send({"t": MsgType.SHAKE.value, "channel": channel,
                        "uid": sess.uid, "nick": sess.nick, "to": to,
                        "ts": round(now, 3)})
            except Exception:
                pass

    def _poll_member(self, p: dict, uid: int) -> bool:
        """投票人是否属于该投票所在频道（投票前权限校验）。"""
        ch = p.get("channel")
        if ch == "public":
            return True
        if ch == "private":
            return uid in (p.get("uid"), p.get("to"))
        g = self.groups.get(p.get("to"))
        return bool(g and uid in g["members"])

    def _on_poll_create(self, sess: Session, header: dict) -> None:
        """R26A 发起投票：校验频道/成员/禁言（复用 _on_chat 规则），poll 作为独立
        消息类型入频道历史；服务器登记权威票数聚合（_polls[seq]，入 R16 快照）。"""
        channel = header.get("channel") or "public"
        if channel not in ("public", "private", "group"):
            self._error(sess, "channel", "未知频道")
            return
        question = (header.get("question") or "").strip()
        if not question:
            self._error(sess, "empty", "投票问题不能为空")
            return
        if len(question) > self.cfg.poll_question_max:
            question = question[:self.cfg.poll_question_max]
        raw_opts = header.get("options")
        if not isinstance(raw_opts, list) or len(raw_opts) < 2:
            self._error(sess, "poll", "至少需要两个选项")
            return
        opts = [str(o).strip()[:self.cfg.poll_option_len] for o in raw_opts]
        opts = [o for o in opts if o]
        if len(opts) < 2:
            self._error(sess, "poll", "选项不能为空")
            return
        if len(opts) > self.cfg.poll_options_max:
            opts = opts[:self.cfg.poll_options_max]
        # R70C：匿名 / 多选 / 测验（测验必须显式给正确项，且仅存服务端不随消息下发）
        anonymous = bool(header.get("anonymous"))
        multi = bool(header.get("multi"))
        quiz = bool(header.get("quiz"))
        correct = None
        if quiz:
            try:
                correct = int(header.get("correct"))
            except (TypeError, ValueError):
                self._error(sess, "poll", "测验需指定正确选项")
                return
            if correct < 0 or correct >= len(opts):
                self._error(sess, "poll", "正确选项越界")
                return
        msg = {"t": MsgType.POLL.value, "channel": channel, "uid": sess.uid,
               "nick": sess.nick, "ts": round(_now(), 3),
               "poll": {"question": question, "options": opts, "votes": {},
                        "end": round(_now() + self.cfg.poll_default_ttl, 3),
                        "anonymous": anonymous, "multi": multi, "quiz": quiz}}
        if channel == "private":
            to = header.get("to")
            try:
                to = int(to)
            except (TypeError, ValueError):
                self._error(sess, "offline", "对方不在线")
                return
            if self.sessions.get(to) is None:
                self._error(sess, "offline", "对方不在线")
                return
            # R50 屏蔽：目标把我拉黑 → 拒收（与私聊文本一致）
            if to != sess.uid and self._is_blocked_by(sess.uid, to):
                self._error(sess, "blocked", "你已被对方屏蔽，投票未送达")
                return
            msg["to"] = to
        elif channel == "group":
            gid = header.get("to")
            g = self.groups.get(gid)
            if not g or sess.uid not in g["members"]:
                self._error(sess, "group", "不在该群或群不存在")
                return
            if g.get("kind") == "channel" and sess.uid != g["owner"]:
                self._error(sess, "readonly", "频道仅创建者可发言")
                return
            mute_until = g["mutes"].get(sess.uid)
            if mute_until is not None and _now() < mute_until:
                self._error(sess, "muted", "你已被禁言，无法发起投票")
                return
            msg["to"] = gid
            msg["group_name"] = g["name"]
        msg = self.bus.publish(msg)
        with self.lock:
            self._polls[msg["seq"]] = {"channel": msg["channel"], "to": msg.get("to"),
                                       "uid": msg["uid"], "question": question,
                                       "options": opts, "end": msg["poll"]["end"],
                                       "votes": {}, "anonymous": anonymous,
                                       "multi": multi, "quiz": quiz,
                                       "correct": correct, "revealed": False}
        self._route(msg)
        self.audit.log(type="poll", uid=sess.uid, nick=sess.nick, channel=channel,
                       to=msg.get("to"), seq=msg["seq"], length=len(question))
        self._persist()                              # R16：投票权威状态落盘

    def _on_poll_vote(self, sess: Session, header: dict) -> None:
        """R26A 投票/改票：服务器权威聚合，一人一票（重复投=改票），截止后拒绝。"""
        try:
            seq = int(header.get("seq"))
            option = int(header.get("option"))
        except (TypeError, ValueError):
            self._error(sess, "poll", "参数错误")
            return
        with self.lock:
            p = self._polls.get(seq)
            if p is None:
                self._error(sess, "expired", "投票已不在服务器历史中")
                return
            if _now() >= p["end"]:
                self._error(sess, "ended", "投票已结束")
                return
            if option < 0 or option >= len(p["options"]):
                self._error(sess, "poll", "选项无效")
                return
            if not self._poll_member(p, sess.uid):
                self._error(sess, "forbid", "不在该频道，无法投票")
                return
            if p.get("multi"):                       # R70C：多选 toggle（再点取消）
                cur = p["votes"].get(sess.uid) or []
                if isinstance(cur, int):
                    cur = [cur]
                cur = [int(x) for x in cur]
                if option in cur:
                    cur.remove(option)
                else:
                    cur.append(option)
                if cur:
                    p["votes"][sess.uid] = sorted(cur)
                else:
                    p["votes"].pop(sess.uid, None)
            else:                                    # 单选：覆盖式，统一存 list
                p["votes"][sess.uid] = [option]
            votes = dict(p["votes"])
            anon = bool(p.get("anonymous"))
            reveal = bool(p.get("quiz")) and _now() >= p["end"]
        if not anon:                                 # 匿名绝不落 bus（回放会泄露）
            self._poll_msg_set_votes(seq, votes, bool(p.get("multi")))
        self._route_poll_state(seq, p, reveal=reveal)
        self._persist()                              # R16：票数变更落盘

    def _poll_msg_set_votes(self, seq: int, votes: dict, multi: bool = False) -> bool:
        """R70C：把权威票数写回频道历史消息（仅非匿名；匿名不落 bus 以免回放泄露）。
        单选非匿名沿用 R26 旧形状 votes:{uid:idx}，多选为 uid:[idx..]（兼容历史重放）。"""
        with self.bus._lock:
            _key, msg = self.bus.find(seq)
            if msg is None or not isinstance(msg.get("poll"), dict):
                return False
            msg["poll"]["votes"] = self._poll_votes_wire(votes, multi)
            return True

    def _poll_votes_wire(self, votes: dict, multi: bool) -> dict:
        """R70C：内部 votes（uid→[idx]）转线上形状——单选给 int，多选给 list。"""
        out = {}
        for u, v in (votes or {}).items():
            idxs = list(v) if isinstance(v, (list, tuple)) else [v]
            idxs = [int(x) for x in idxs]
            out[str(u)] = (idxs if multi else (idxs[0] if idxs else 0))
        return out

    def _poll_counts(self, p: dict) -> list:
        """R70C：按服务端私有 votes（uid->[idx]）聚合计票（容忍旧的 int 形状）。"""
        counts = [0] * len(p.get("options") or [])
        for idxs in (p.get("votes") or {}).values():
            if isinstance(idxs, int):
                idxs = [idxs]
            for vi in (idxs or []):
                try:
                    vi = int(vi)
                except (TypeError, ValueError):
                    continue
                if 0 <= vi < len(counts):
                    counts[vi] += 1
        return counts

    def _route_poll_state(self, seq: int, p: dict, reveal: bool = False) -> None:
        """R70C 广播权威票数。匿名投票**绝不广播** uid→选项，只广播计数 +
        按人单播本人 mine；测验在 reveal（已结束）前不下发 correct。"""
        counts = self._poll_counts(p)
        base = {"t": MsgType.POLL_STATE.value, "seq": seq, "channel": p["channel"],
                "uid": p["uid"], "to": p.get("to"), "counts": counts,
                "total": sum(counts), "end": p.get("end")}
        if p.get("quiz") and reveal:
            base["correct"] = int(p.get("correct") or 0)
        if p.get("anonymous"):
            self._route(dict(base))
            for uid, idxs in (p.get("votes") or {}).items():
                if isinstance(idxs, int):
                    idxs = [idxs]
                self._send_uid(uid, dict(base, mine=[int(x) for x in (idxs or [])]))
        else:
            # 非匿名：沿用 R26 线上形状 votes:{uid:idx}（多选为 uid:[idx..]）
            base["votes"] = self._poll_votes_wire(p.get("votes") or {},
                                                  bool(p.get("multi")))
            self._route(base)

    def _send_uid(self, uid: int, payload: dict) -> None:
        """按 uid 单播到该用户的全部在线会话（桌面+网页多端并存）。"""
        with self.lock:
            clients = list(self._uid_clients.get(uid, ()))
        for s in clients:
            try:
                s.send(payload)
            except Exception:
                pass

    def _sweep_polls(self, now: float) -> None:
        """R70C：投票到点后揭示测验答案（每场只广播一次）。"""
        due = []
        with self.lock:
            for seq, p in self._polls.items():
                if p.get("quiz") and not p.get("revealed") and now >= (p.get("end") or 0):
                    p["revealed"] = True
                    due.append((seq, dict(p)))
        for seq, p in due:
            self._route_poll_state(seq, p, reveal=True)

    # ---------- R26D 链接预览（后台抓取，事件补发） ----------
    def _maybe_fetch_preview(self, url: str, msg: dict) -> None:
        """缓存命中（TTL 内）直接补发；否则登记 in-flight 并起后台线程抓取。
        单条消息只预览首个 URL；失败/SSRF 静默降级，不出错误事件。"""
        now = _now()
        with self._preview_lock:
            hit = self._preview_cache.get(url)
            if hit is not None and now - hit[0] <= self.cfg.preview_ttl:
                if hit[1] is not None:
                    self._preview_ready(msg["seq"], url, hit[1])
                return
            if url in self._preview_inflight:
                return
            self._preview_inflight.add(url)
        threading.Thread(target=self._fetch_preview_worker,
                         args=(url, msg["seq"], msg.get("channel"),
                               msg.get("uid"), msg.get("to")),
                         daemon=True, name="preview-fetch").start()

    def _fetch_preview_worker(self, url: str, seq: int, channel: str,
                              uid: int, to) -> None:
        """后台线程：出网抓取（绝不占用 Hub 锁 / dispatch 线程）。"""
        try:
            meta = fetch_preview(url, self.cfg)
        except Exception:
            meta = None
        with self._preview_lock:
            self._preview_inflight.discard(url)
            self._preview_cache[url] = (_now(), meta)
        if meta is not None:
            self._preview_ready(seq, url, meta)

    def _preview_ready(self, seq: int, url: str, meta: dict) -> None:
        """抓取完成：原地附到原消息（历史/两端渲染一致），并广播 preview 事件。"""
        with self.bus._lock:
            _key, msg = self.bus.find(seq)
            if msg is None or "preview" in msg:
                return
            msg["preview"] = meta
            ch, muid, mto = msg["channel"], msg["uid"], msg.get("to")
        self._route({"t": MsgType.PREVIEW.value, "seq": seq, "preview": meta,
                     "channel": ch, "uid": muid, "to": mto})
        self._persist()                              # 预览元数据入快照（无正文隐私风险）

    def _on_voice(self, sess: Session, header: dict, body: bytes) -> None:
        """语音消息：复用文本聊天的频道校验/禁言/成员归属，二进制 WAV 体随广播透传。
        body 仅内存短留（TTL 清理），不入持久化（重启后播放不可用，仅留墓碑）。"""
        channel = header.get("channel") or "public"
        if channel not in ("public", "private", "group"):
            self._error(sess, "channel", "未知频道")
            return
        try:
            duration = max(0.0, min(float(header.get("duration") or 0.0),
                                    self.cfg.voice_max_dur))
        except (TypeError, ValueError):
            duration = 0.0
        msg = {"t": "chat", "channel": channel, "uid": sess.uid,
               "nick": sess.nick, "ts": round(_now(), 3),
               "voice": True, "duration": round(duration, 1)}
        if channel == "private":
            to = header.get("to")
            try:
                to = int(to)
            except (TypeError, ValueError):
                to = None
            if to is None or self.sessions.get(to) is None:
                self._error(sess, "offline", "对方不在线")
                return
            # R50 屏蔽：目标把我拉黑 → 拒收（与私聊文本一致）
            if to != sess.uid and self._is_blocked_by(sess.uid, to):
                self._error(sess, "blocked", "你已被对方屏蔽，语音未送达")
                return
            msg["to"] = to
        elif channel == "group":
            gid = header.get("to")
            g = self.groups.get(gid)
            if not g or sess.uid not in g["members"]:
                self._error(sess, "group", "不在该群或群不存在")
                return
            # R26B 频道广播：仅创建者可发语音（成员只读）
            if g.get("kind") == "channel" and sess.uid != g["owner"]:
                self._error(sess, "readonly", "频道仅创建者可发言")
                return
            mute_until = g["mutes"].get(sess.uid)
            if mute_until is not None and _now() < mute_until:
                self._error(sess, "muted", "你已被禁言，无法在群内发语音")
                return
            msg["to"] = gid
            msg["group_name"] = g["name"]
        msg = self.bus.publish(msg)
        raw = bytes(body) if body else b""
        if raw:
            with self.lock:
                self._voice[msg["seq"]] = raw
                self._voice_ts[msg["seq"]] = _now()
        # 锁外带宽带广播：bin 体随每帧透传给应收会话
        for _u, s in self._chan_recipients(msg["channel"], msg["uid"],
                                           msg.get("to")):
            try:
                s.send(msg, raw)
            except Exception:
                pass
        self.audit.log(type="voice", uid=sess.uid, nick=sess.nick,
                       channel=channel, to=msg.get("to"), seq=msg["seq"],
                       duration=duration)
        self._persist()                              # R16：语音消息列表（无 body）落盘

    def _on_vmemo(self, sess: Session, header: dict, body: bytes) -> None:
        """R72 圆形视频留言：复用语音消息的频道校验/只读/禁言，VMA1 容器随广播透传。
        body 仅内存短留（TTL 清理），不入持久化（重启后播放不可用，仅留墓碑）。"""
        channel = header.get("channel") or "public"
        if channel not in ("public", "private", "group"):
            self._error(sess, "channel", "未知频道")
            return
        raw = bytes(body) if body else b""
        if not raw:
            self._error(sess, "empty", "视频留言内容为空")
            return
        if len(raw) > self.cfg.vmemo_max_bytes:
            self._error(sess, "big", "视频留言过大")
            return
        try:
            duration = max(0.0, min(float(header.get("duration") or 0.0),
                                    self.cfg.vmemo_max_dur))
        except (TypeError, ValueError):
            duration = 0.0
        msg = {"t": "chat", "channel": channel, "uid": sess.uid,
               "nick": sess.nick, "ts": round(_now(), 3),
               "vmemo": True, "duration": round(duration, 1)}
        if channel == "private":
            to = header.get("to")
            try:
                to = int(to)
            except (TypeError, ValueError):
                to = None
            if to is None or self.sessions.get(to) is None:
                self._error(sess, "offline", "对方不在线")
                return
            if to != sess.uid and self._is_blocked_by(sess.uid, to):
                self._error(sess, "blocked", "你已被对方屏蔽，视频留言未送达")
                return
            msg["to"] = to
        elif channel == "group":
            gid = header.get("to")
            g = self.groups.get(gid)
            if not g or sess.uid not in g["members"]:
                self._error(sess, "group", "不在该群或群不存在")
                return
            if g.get("kind") == "channel" and sess.uid != g["owner"]:
                self._error(sess, "readonly", "频道仅创建者可发言")
                return
            mute_until = g["mutes"].get(sess.uid)
            if mute_until is not None and _now() < mute_until:
                self._error(sess, "muted", "你已被禁言，无法在群内发视频留言")
                return
            msg["to"] = gid
            msg["group_name"] = g["name"]
        msg = self.bus.publish(msg)
        with self.lock:
            self._vmemo[msg["seq"]] = raw
            self._vmemo_ts[msg["seq"]] = _now()
        for _u, s in self._chan_recipients(msg["channel"], msg["uid"],
                                           msg.get("to")):
            try:
                s.send(msg, raw)
            except Exception:
                pass
        self.audit.log(type="vmemo", uid=sess.uid, nick=sess.nick,
                       channel=channel, to=msg.get("to"), seq=msg["seq"],
                       duration=duration, size=len(raw))
        self._persist()                              # R16：视频留言列表（无 body）落盘

    def _geo_target(self, sess: Session, header: dict):
        """实时位置/停止共享的频道校验 → (channel, to) 或 None（非法静默忽略）。"""
        channel = header.get("channel") or "public"
        if channel not in ("public", "private", "group"):
            return None
        if channel == "private":
            try:
                to = int(header.get("to"))
            except (TypeError, ValueError):
                return None
            if to != sess.uid and self.sessions.get(to) is None:
                return None
            if to != sess.uid and self._is_blocked_by(sess.uid, to):
                return None
            return channel, to
        if channel == "group":
            g = self.groups.get(header.get("to"))
            if not g or sess.uid not in g["members"]:
                return None
            return channel, g["gid"]
        return channel, None

    def _geo_broadcast(self, sess: Session, channel: str, to, payload: dict) -> None:
        """广播给应收方（不含自己；请求方本地已先行渲染）。"""
        for _u, s in self._chan_recipients(channel, sess.uid, to):
            if s.uid == sess.uid:
                continue
            try:
                s.send(payload)
            except Exception:
                pass

    def _on_geo_live(self, sess: Session, header: dict) -> None:
        """R72 实时位置刷新：校验频道成员后广播（不入历史、不入审计，同 typing 待遇）。"""
        tgt = self._geo_target(sess, header)
        if tgt is None:
            return
        channel, to = tgt
        geo = self._san_geo(header.get("geo"))
        if not geo or not geo.get("live"):
            return
        payload = {"t": MsgType.GEO_LIVE.value, "channel": channel,
                   "uid": sess.uid, "nick": sess.nick, "ts": round(_now(), 3),
                   "geo": geo}
        if to is not None:
            payload["to"] = to
        self._geo_broadcast(sess, channel, to, payload)

    def _on_geo_stop(self, sess: Session, header: dict) -> None:
        """R72 停止位置共享：广播让对端摘掉「共享中」标记（不入历史）。"""
        tgt = self._geo_target(sess, header)
        if tgt is None:
            return
        channel, to = tgt
        payload = {"t": MsgType.GEO_STOP.value, "channel": channel,
                   "uid": sess.uid, "nick": sess.nick, "ts": round(_now(), 3)}
        sid = header.get("session")
        if isinstance(sid, str) and sid.strip():
            payload["session"] = sid.strip()[:32]
        if to is not None:
            payload["to"] = to
        self._geo_broadcast(sess, channel, to, payload)

    def _conv_key(self, channel: str, uid: int, to) -> str:
        """回执/置顶用的稳定会话键（与客户端 _pin_key 同约定：public 用 'public'）。"""
        if channel == "public":
            return "public"
        if channel == "private":
            a, b = sorted((int(uid), int(to or 0)))
            return f"private:{a}:{b}"
        return f"group:{int(to)}"

    def _chan_recipients(self, channel: str, uid: int, to) -> list:
        """某频道的应收会话（锁内收集，调用方锁外发帧）。

        R批次③：按 uid 判定应收，再展开该 uid 的**全部在线会话**（桌面+网页
        多端并存）——因此新消息/已读/输入中/事件会按 uid 投递到目标端全部分身，
        保证一端已读另一端不再显示未读的跨端一致。"""
        with self.lock:
            if channel == "public":
                targets = list(self.sessions.keys())
            elif channel == "private":
                targets = [u for u in self.sessions
                           if u in (int(uid), int(to))]
            else:
                g = self.groups.get(to)
                members = g["members"] if g else {}
                # R54：管理员非成员也可接收所有群消息（含私有群）
                targets = [u for u in self.sessions
                           if u in members or self._is_admin_uid(u)]
            out = []
            for u in targets:
                for s in self._uid_clients.get(u, ()):
                    out.append((u, s))
            return out

    def _chan_member(self, sess: Session, msg: dict) -> bool:
        """消息频道成员判定（回应/置顶前校验权限）。"""
        ch = msg.get("channel")
        if ch == "public":
            return True
        if ch == "private":
            return sess.uid in (msg.get("uid"), msg.get("to"))
        if ch == "group":
            g = self.groups.get(msg.get("to"))
            # R54：管理员非成员也可回应/置顶群消息
            return bool(g and (sess.uid in g["members"] or sess.is_admin))
        return False

    def _route(self, msg: dict) -> None:
        """投递到应收会话（锁内只收集，锁外发帧）"""
        for _u, s in self._chan_recipients(msg["channel"], msg["uid"], msg.get("to")):
            try:
                s.send(msg)
            except Exception:
                pass

    def _on_edit(self, sess: Session, header: dict) -> None:
        """C3 编辑消息：仅本人可改，改 stored msg 原文并广播 edit 事件。"""
        try:
            seq = int(header.get("seq"))
        except (TypeError, ValueError):
            self._error(sess, "seq", "缺少 seq")
            return
        text = (header.get("text") or "").strip()
        if not text:
            self._error(sess, "empty", "消息不能为空")
            return
        if len(text) > self.cfg.chat_text_max:
            self._error(sess, "long", "消息过长")
            return
        with self.bus._lock:
            _key, msg = self.bus.find(seq)
        if msg is None:
            self._error(sess, "expired", "消息已不在服务器历史中")
            return
        if msg.get("uid") != sess.uid:
            self._error(sess, "forbid", "只能编辑自己的消息")
            return
        if isinstance(msg.get("poll"), dict):      # R26A：投票消息结构固定，禁编辑
            self._error(sess, "poll", "投票消息不可编辑")
            return
        if msg.get("deleted"):
            self._error(sess, "dup", "消息已撤回，无法编辑")
            return
        if msg.get("file") or msg.get("sticker") or msg.get("fp"):
            self._error(sess, "forbid", "只能编辑文本消息")
            return
        # R70B：编辑前把旧版本快照入 edits（旧正文 + 旧富文本），
        # 单条截断 edit_history_len、最多 edit_history_max 条（超出丢最旧）。
        old_snap = {"ts": round(_now(), 3),
                    "text": str(msg.get("text") or "")[:self.cfg.edit_history_len]}
        if isinstance(msg.get("rich"), list):
            old_snap["rich"] = msg["rich"]
        edits = msg.get("edits")
        if not isinstance(edits, list):
            edits = []
        edits.append(old_snap)
        if len(edits) > self.cfg.edit_history_max:
            del edits[:len(edits) - self.cfg.edit_history_max]
        msg["edits"] = edits
        msg["text"] = text                     # 原地改（存储与后续历史加载一致）
        r59 = self._san_rich(header.get("rich"), text)     # R59：编辑同步富文本
        if r59:
            msg["rich"] = r59
        else:
            msg.pop("rich", None)                 # 编辑为纯文本 → 清掉旧富文本
        msg["edited"] = True
        route_ev = {"t": MsgType.MSG_EDIT.value, "seq": seq,
                    "channel": msg["channel"], "uid": msg["uid"],
                    "to": msg.get("to"), "nick": msg["nick"], "text": text,
                    "edits": edits}                # R70B：随事件下发历史版本
        if r59:
            route_ev["rich"] = r59
        self._route(route_ev)
        self.audit.log(type="msg_edit", uid=sess.uid, seq=seq, length=len(text))
        self._persist()                              # R16：编辑后的权威消息落盘

    def _on_del(self, sess: Session, header: dict) -> None:
        """C3 撤回消息：默认仅本人可删；私聊 scope=both 时双方均可删。

        权限矩阵：
          - 本人：任何频道都可删（scope 无约束）
          - 非本人：仅当私聊消息且 scope=both 且请求者为对端时才放行
          - R53 管理员：任何频道、任何人的消息都可删（最高清理权限）
        """
        try:
            seq = int(header.get("seq"))
        except (TypeError, ValueError):
            self._error(sess, "seq", "缺少 seq")
            return
        scope = header.get("scope") or "self"
        if scope not in ("self", "both"):
            self._error(sess, "scope", "未知删除范围")
            return
        with self.bus._lock:
            _key, msg = self.bus.find(seq)
        if msg is None:
            self._error(sess, "expired", "消息已不在服务器历史中")
            return
        is_owner = msg.get("uid") == sess.uid
        if not is_owner and not sess.is_admin:      # R53：管理员可撤任何人消息
            is_private = msg.get("channel") == "private"
            is_peer = msg.get("to") == sess.uid
            if not (scope == "both" and is_private and is_peer):
                self._error(sess, "forbid", "只能撤回自己的消息")
                return
        if msg.get("deleted"):
            self._error(sess, "dup", "消息已撤回")
            return
        msg["deleted"] = True                  # 墓碑保留 seq，历史/seq 连续
        msg["text"] = ""
        self._route({"t": MsgType.MSG_DEL.value, "seq": seq,
                     "channel": msg["channel"], "uid": msg["uid"],
                     "to": msg.get("to"), "nick": msg["nick"]})
        self.audit.log(type="msg_del", uid=sess.uid, seq=seq, scope=scope)
        self._persist()                              # R16：撤回 tombstone 落盘

    # ---------- R53 服务器管理员（最高清理权限） ----------
    def _on_admin_kick(self, sess: Session, header: dict) -> None:
        """管理员踢人下线：unregister 目标会话并关闭其连接（桌面端断线重连除外，
        密码类操作靠登录校验兜底）。"""
        if not sess.is_admin:
            self._error(sess, "forbid", "仅管理员可执行")
            return
        raw = header.get("uid")
        if isinstance(raw, int) or str(raw).lstrip('-').isdigit():
            uid = int(raw)
        else:
            # 按昵称踢人：服务器权威解析已知用户
            uid = self._alias_to_uid(self._known_names(), raw)
        if uid is None:
            self._error(sess, "uid", "目标 uid/昵称 无效")
            return
        if uid == sess.uid:
            self._error(sess, "uid", "不能踢自己")
            return
        with self.lock:
            tsess = self.sessions.get(uid)
        if tsess is None:
            self._error(sess, "offline", "该用户不在线")
            return
        nick = tsess.nick
        try:
            tsess.send({"t": MsgType.ERROR.value, "code": "kicked",
                        "text": "已被管理员强制下线"})
        except Exception:
            pass
        self.unregister(tsess, "admin_kick")
        tsess.close_conn()
        self._broadcast_system(f"管理员已将 {nick} 强制下线")
        self.audit.log(type="admin_kick", uid=sess.uid, target=uid,
                       target_nick=nick)
        print(f"[admin][踢下线] {sess.nick} 将 @{nick}(uid={uid}) 强制下线")

    # ---------- 系统管理员群目录 + 增删成员 + 解散群 ----------
    def _admin_groups_payload(self) -> dict:
        """管理员（超管）专用：全量群目录，含每个群的成员花名册。
        与普通 `_group_list`（只给可见群的摘要）不同：此接口不经任何权限过滤，
        且带 members 明细，仅供 `sess.is_admin` 调用。"""
        with self.lock:
            groups = []
            for g in sorted(self.groups.values(), key=lambda g: g["gid"]):
                groups.append({
                    "gid": g["gid"], "name": g["name"], "owner": g["owner"],
                    "admins": sorted(g["admins"]),
                    "kind": g.get("kind", ""),
                    "public": g.get("public", 0),
                    "member_count": len(g["members"]),
                    "member_max": self.cfg.group_max_members,
                    "members": [{"uid": u, "nick": n,
                                 # R57：管理员群成员花名册带隐身标记（仅超管可看）
                                 "invisible": bool((self.known.get(u) or {})
                                                   .get("invisible"))}
                                for u, n in sorted(g["members"].items())],
                })
        return {"t": MsgType.ADMIN_GROUPS_ROSTER.value, "groups": groups}

    def _on_admin_groups(self, sess: Session) -> None:
        """管理员拉取群目录：超管可看全部群及其成员清单。"""
        if not sess.is_admin:
            self._error(sess, "forbid", "仅系统管理员可执行")
            return
        sess.send(self._admin_groups_payload())

    @staticmethod
    def _alias_to_uid(known: dict, key) -> int | None:
        """按 uid 或已知昵称（existing/key）解析目标 uid。仅管理员入参宽容处理。"""
        try:
            return int(key)
        except (TypeError, ValueError):
            pass
        if isinstance(key, str):
            for u, rec in known.items():
                if rec.get("nick") == key:
                    return u
        return None

    def _on_admin_group_set(self, sess: Session, header: dict) -> None:
        """系统管理员：向任意群加/移成员，或直接解散群（超管 override，无视群内权限）。
        add   → 把 header.uid / 已知昵称 加入该群，更新群态；
        remove→ 把某成员移出（若为群主自动转让；若移空则解散）；
        dissolve → 直接删除该群，全员列表同步刷新。"""
        if not sess.is_admin:
            self._error(sess, "forbid", "仅系统管理员可执行")
            return
        gid = header.get("gid")
        op = (header.get("op") or "").strip().lower()
        g = self.groups.get(gid)
        if not g or not isinstance(gid, int):
            self._error(sess, "group", "群不存在或 gid 非法")
            return
        gname = g["name"]
        if op == "dissolve":
            with self.lock:
                if self.groups.get(gid) is not g:
                    return
                del self.groups[gid]
            self._persist(force=True)
            self._broadcast_system(f"系统管理员已解散群「{gname}」")
            self._broadcast_group_list()
            self.audit.log(type="admin_group_dissolve", gid=gid, name=gname,
                           actor=sess.uid)
            return

        uid = self._alias_to_uid(self._known_names(), header.get("uid"))
        if uid is None:
            self._error(sess, "uid", "目标 uid/昵称 无效")
            return
        cur = g.get("members", {}).get(uid)
        if op == "add":
            if cur is not None:
                self._error(sess, "member", "该用户已在群中")
                return
            if len(g["members"]) >= self.cfg.group_max_members:
                self._error(sess, "full", f"群已满（{len(g['members'])}/{self.cfg.group_max_members}）")
                return
            nick = self._append_nick_for_uid(uid, header.get("nick"))
            with self.lock:
                if self.groups.get(gid) is not g:
                    return
                g["members"][uid] = nick
                g["mutes"].pop(uid, None)          # 重入群：清残留禁言
            self._persist()                        # 锁外持久化：避免锁序自锁风险
            self._send_group_state(gid, text=f"系统管理员将 {nick} 加入群聊")
            self._broadcast_group_list()
            self.audit.log(type="admin_group_add", gid=gid, name=gname,
                           target=uid, target_nick=nick, actor=sess.uid)
            return
        if op == "remove":
            if cur is None:
                self._error(sess, "member", "该用户不在群中")
                return
            dissolved = False
            with self.lock:
                if self.groups.get(gid) is not g:
                    return
                nick = g["members"].pop(uid)
                g["admins"].discard(uid)
                if not g["members"]:
                    del self.groups[gid]
                    dissolved = True
                elif g["owner"] == uid:
                    g["owner"] = next(iter(g["members"]))
            self._persist(force=dissolved)         # 锁外持久化：避免锁序自锁风险
            if dissolved:
                self._broadcast_system(f"系统管理员已解散群「{gname}」")
            else:
                self._send_group_state(gid, text=f"系统管理员将 {nick} 移出群聊")
            self._broadcast_group_list()
            self.audit.log(type="admin_group_remove", gid=gid, name=gname,
                           target=uid, target_nick=nick, actor=sess.uid)
            return
        self._error(sess, "op", f"未知操作：{op}")

    def _admin_user_payload(self, target) -> dict | None:
        """系统管理员：构建某人信息+所属群载荷（target 为 uid 或已知昵称）。
        目标无效返回 None。"""
        uid = self._alias_to_uid(self._known_names(), target)
        if uid is None:
            return None
        nick = self._append_nick_for_uid(uid, None)
        online = uid in self.sessions
        with self.lock:
            groups = []
            for g in sorted(self.groups.values(), key=lambda x: x["gid"]):
                if uid in g["members"]:
                    role = "owner" if g["owner"] == uid else \
                        ("admin" if uid in g["admins"] else "member")
                    groups.append({"gid": g["gid"], "name": g["name"], "role": role})
        return {"t": MsgType.ADMIN_USER_INFO.value, "uid": uid, "nick": nick,
                "online": online, "groups": groups,
                "invisible": self._is_invisible(uid)}  # R57：管理员可见隐身态

    def _on_admin_user_get(self, sess: Session, header: dict) -> None:
        """系统管理员：查某人信息+所属全部群（uid 或已知昵称均可）。"""
        if not sess.is_admin:
            self._error(sess, "forbid", "仅系统管理员可执行")
            return
        payload = self._admin_user_payload(header.get("uid"))
        if payload is None:
            self._error(sess, "uid", "目标 uid/昵称 无效")
            return
        sess.send(payload)
        self.audit.log(type="admin_user_get", uid=sess.uid, target=payload["uid"],
                       target_nick=payload["nick"])

    def _append_nick_for_uid(self, uid: int, nick):
        """优先用入参 nick；否则用在线会话或已知名单的昵称；都没有则保底 uid。"""
        s = self.sessions.get(uid)
        if s and s.nick:
            return s.nick
        known = self._known_names().get(uid)
        if known and known.get("nick"):
            return known["nick"]
        return nick or f"用户{uid}"

    def _on_admin_clear_all(self, sess: Session) -> None:
        """管理员清空全部聊天记录：清空服务器全部频道缓冲并广播 CLEARED，
        各客户端据此清空本地历史。seq 不重置，避免新旧消息 seq 冲突。"""
        if not sess.is_admin:
            self._error(sess, "forbid", "仅管理员可执行")
            return
        removed = self.bus.clear_all()
        self._persist(force=True)                 # 清空后立即落盘，防重启回放旧记录
        self._broadcast({"t": MsgType.CLEARED.value, "all": True})
        self._broadcast_system(f"管理员已清空全部聊天记录（{removed} 条）")
        self.audit.log(type="admin_clear_all", uid=sess.uid, removed=removed)
        print(f"[admin][清空全局] {sess.nick} 清空全部聊天记录（{removed} 条）")

    def _on_admin_clear_uid(self, sess: Session, header: dict) -> None:
        """管理员清空指定用户全部消息（跨全部频道），广播 CLEARED uid。"""
        if not sess.is_admin:
            self._error(sess, "forbid", "仅管理员可执行")
            return
        try:
            uid = int(header.get("uid"))
        except (TypeError, ValueError):
            self._error(sess, "uid", "缺少 uid")
            return
        with self.lock:
            nick = (self.known.get(uid) or {}).get("nick") or f"用户{uid}"
        removed = self.bus.clear_uid(uid)
        self._persist(force=True)
        self._broadcast({"t": MsgType.CLEARED.value, "uid": uid})
        self._broadcast_system(f"管理员已清空用户 {nick} 的全部消息（{removed} 条）")
        self.audit.log(type="admin_clear_uid", uid=sess.uid, target=uid,
                       removed=removed)
        print(f"[admin][清空用户] {sess.nick} 清空 @{nick}(uid={uid}) 消息（{removed} 条）")

    def _admin_del_remove_groups(self, uid: int) -> int:
        """把 uid 从服务器全部群成员中移除；返回因此解散的群数。
        群主被移出时自动转让给剩余成员，移空即解散该群。锁内执行。"""
        dissolved = 0
        with self.lock:
            for gid, g in list(self.groups.items()):
                if uid not in g["members"]:
                    continue
                g["members"].pop(uid, None)
                g["admins"].discard(uid)
                g["mutes"].pop(uid, None)
                if not g["members"]:
                    del self.groups[gid]
                    dissolved += 1
                elif g["owner"] == uid:
                    g["owner"] = next(iter(g["members"]))
        return dissolved

    def _on_admin_user_del(self, sess: Session, header: dict) -> None:
        """管理员清除用户（删除账号）：
        1) 从全部群移除成员（群主自动转让，移空即解散）；
        2) 清空其跨全部频道的聊天消息；
        3) 从已知账号 known 删除（离线账号一并移除、不可再登录）；
        4) 若在线则强制下线。
        不可清除自己（当前管理员）。"""
        if not sess.is_admin:
            self._error(sess, "forbid", "仅系统管理员可执行")
            return
        uid = self._alias_to_uid(self._known_names(), header.get("uid"))
        if uid is None:
            self._error(sess, "uid", "目标 uid/昵称 无效")
            return
        if uid == sess.uid:
            self._error(sess, "uid", "不能清除自己")
            return
        nick = self._append_nick_for_uid(uid, None)
        dissolved = self._admin_del_remove_groups(uid)      # 1) 移出全部群
        removed = self.bus.clear_uid(uid)                   # 2) 清空消息
        # 同一 uid 可以同时有桌面端、网页端和多个网页标签。只下线
        # sessions 中的代表会话会留下其它端，须撤销所有端及其 token。
        # 先在锁内拍快照并撤销全部 token，再逐个注销，避免遍历时修改在线集。
        with self.lock:
            targets = list(self._uid_clients.get(uid, ()))
            representative = self.sessions.get(uid)
            if representative is not None and representative not in targets:
                targets.append(representative)
            for token, token_sess in list(self.web_tokens.items()):
                if token_sess.uid == uid:
                    del self.web_tokens[token]
        for target in targets:                               # 3) 全部在线端强制下线
            try:
                target.send({"t": MsgType.ERROR.value, "code": "deleted",
                             "text": "你的账号已被管理员删除"})
            except Exception:
                pass
            self.unregister(target, "admin_del")
            try:
                target.close_conn()
            except Exception:
                pass
        with self.lock:
            # unregister 会重建 known 条目记录 last_online，故须在其后再删除账号
            self.known.pop(uid, None)                       # 4) 删除账号
        self._persist(force=True)
        self._broadcast({"t": MsgType.CLEARED.value, "uid": uid})
        self._broadcast_group_list()
        self._broadcast_system(f"系统管理员已清除用户 {nick} 的账号")
        self.audit.log(type="admin_user_del", uid=sess.uid, target=uid,
                       target_nick=nick, removed=removed, dissolved=dissolved)
        print(f"[admin][删除账号] {sess.nick} 清除 @{nick}(uid={uid})："
              f"清消息 {removed} 条，解散群 {dissolved} 个，已从 known 移除")

    def _on_reaction(self, sess: Session, header: dict) -> None:
        """R13 表情回应：对 seq 消息加/摘 emoji，广播全网 reactions 状态。"""
        try:
            seq = int(header.get("seq"))
        except (TypeError, ValueError):
            self._error(sess, "seq", "缺少 seq")
            return
        emoji = (header.get("emoji") or "").strip()[:8]
        if not emoji:
            self._error(sess, "emoji", "缺少表情")
            return
        on = bool(header.get("on", True))
        with self.bus._lock:
            _key, msg = self.bus.find(seq)
        if msg is None:
            self._error(sess, "expired", "消息已不在服务器历史中")
            return
        if not self._chan_member(sess, msg):
            self._error(sess, "forbid", "不在该频道，无法回应")
            return
        if msg.get("deleted"):
            self._error(sess, "dead", "消息已撤回，无法回应")
            return
        reactions = msg.setdefault("reactions", {})
        bucket = reactions.setdefault(emoji, {})
        me = str(sess.uid)
        if on:
            bucket[me] = _now()
        else:
            bucket.pop(me, None)
            if not reactions.get(emoji):
                reactions.pop(emoji, None)
        for _u, s in self._chan_recipients(msg["channel"], msg.get("uid"),
                                           msg.get("to")):
            try:
                s.send({"t": MsgType.REACTION.value, "seq": seq,
                        "channel": msg["channel"], "uid": msg.get("uid"),
                        "to": msg.get("to"), "nick": msg.get("nick"),
                        "reactions": reactions,
                        # R33②：增量字段（actor=操作者，供网页端 DOM 级加/摘单药丸）
                        "emoji": emoji, "actor": sess.uid, "on": on})
            except Exception:
                pass
        self.audit.log(type="reaction", uid=sess.uid, seq=seq, emoji=emoji, on=on)
        self._persist()                              # R16：回应后的权威消息落盘

    def _on_read(self, sess: Session, header: dict) -> None:
        """R13 已读回执：记录 uid 在某会话读到的最远 seq，广播给会话参与者。"""
        try:
            seq = int(header.get("seq"))
        except (TypeError, ValueError):
            self._error(sess, "seq", "缺少 seq")
            return
        channel = header.get("channel") or "public"
        to = header.get("to")
        key = self._conv_key(channel, sess.uid, to)
        # 锁内修改共享 reads/_burn：多连接线程并发回执需串行化，防丢失更新
        with self.lock:
            reads = self.reads.setdefault(key, {})
            if reads.get(sess.uid, 0) >= seq:      # 幂等：只前进不回退
                return
            reads[sess.uid] = seq
            for _u, s in self._chan_recipients(channel, sess.uid, to):
                try:
                    s.send({"t": MsgType.READ.value, "channel": channel, "key": key,
                            "uid": sess.uid, "to": to, "seq": seq})
                except Exception:
                    pass
            # R14 阅后即焚：本会话所有 burn 消息若所有待读目标方已读到其 seq → 服务器删除并广播 del
            for bseq, br in list(self._burn.items()):
                if br["channel"] != channel or not self._burn_same_convo(br, sess.uid, to):
                    continue
                if bseq <= seq and self._burn_ready(br, reads, bseq):
                    self._burn_finish(bseq, br)
            self._burn_ttl_sweep()
        self._persist()                              # R16：reads/burn 变化落盘

    def _readers_for(self, key: str, uid: int):
        """R33③ 已读详情数据（含权限校验）：有权 → [{uid,nick,seq}]；无权 → None。
        权限：public 任意成员；private 需为会话双方；group 需为群成员。"""
        ok = key == "public"
        if not ok and key.startswith("private:"):
            try:
                a, b = key.split(":")[1:3]
                ok = uid in (int(a), int(b))
            except (ValueError, TypeError):
                ok = False
        if not ok and key.startswith("group:"):
            try:
                g = self.groups.get(int(key.split(":", 1)[1]))
            except (ValueError, TypeError):
                g = None
            # R54：管理员非成员也可查群已读
            ok = bool(g and (uid in g["members"] or self._is_admin_uid(uid)))
        if not ok:
            return None
        readers = self.reads.get(key) or {}
        lst = []
        for u, seq in readers.items():
            try:
                uid_i = int(u)
            except (TypeError, ValueError):
                continue
            info = self.known.get(uid_i) or {}
            lst.append({"uid": uid_i,
                        "nick": info.get("nick") or f"用户{uid_i}",
                        "seq": seq})
        lst.sort(key=lambda d: d["uid"])
        return lst

    def _on_read_detail(self, sess: Session, header: dict) -> None:
        """R33③ 已读详情：单播回某会话全部已读成员 [{uid,nick,seq}]。"""
        key = str(header.get("key") or "")
        lst = self._readers_for(key, sess.uid)
        if lst is None:
            self._error(sess, "forbid", "无权查看该会话已读详情")
            return
        try:
            sess.send({"t": MsgType.READ_DETAIL.value, "key": key,
                       "readers": lst})
        except Exception:
            pass

    def _on_msg_readers(self, sess: Session, header: dict) -> None:
        """C9② 群@已读 by N 逐人统计：某群消息 seq → 已读成员数 / 群总数 / 未读成员。

        复用 R33 的 reads[key][uid]=最远已读 seq 数据结构：某 seq 已读成员集 =
        该会话全部已读记录里 seq≥目标 seq 的成员（读到更远即代表看到了本条）。
        members=[{uid,nick}] 已读；unread=[{uid,nick}] 未读；count/total 供 UI 显示 N/M。
        """
        key = str(header.get("key") or "")
        try:
            seq = int(header.get("seq") or 0)
        except (TypeError, ValueError):
            self._error(sess, "seq", "seq 无效")
            return
        if not key.startswith("group:"):
            self._error(sess, "key", "仅群会话支持逐人已读统计")
            return
        try:
            gid = int(key.split(":", 1)[1])
        except (TypeError, ValueError):
            self._error(sess, "key", "key 无效")
            return
        g = self.groups.get(gid)
        if not g or (sess.uid not in g["members"] and not self._is_admin_uid(sess.uid)):
            self._error(sess, "forbid", "无权查看该群已读统计")
            return
        with self.lock:
            readers = self.reads.get(key) or {}
            members = dict(g["members"])
        read_members, unread_members = [], []
        for u, nick in sorted(members.items()):
            if readers.get(u, 0) >= seq:
                read_members.append({"uid": u, "nick": nick})
            else:
                unread_members.append({"uid": u, "nick": nick})
        try:
            sess.send({"t": MsgType.MSG_READERS.value, "key": key, "seq": seq,
                       "count": len(read_members), "total": len(members),
                       "members": read_members, "unread": unread_members})
        except Exception:
            pass

    # ---------- R36 E2EE 密聊（服务器纯透传：不解析、不存储、审计只记元数据） ----------

    def _e2ee_target(self, sess: Session, to):
        """校验 E2EE 目标在线且为桌面会话（网页端不参与端到端加密），返回会话或 None。"""
        # R50：被对方屏蔽 → 密聊/语音通道一并拒（与私聊一致）
        if sess.type != "tcp":
            self._error(sess, "e2ee", "密聊为端到端加密，仅桌面端支持")
            return None
        try:
            to = int(to)
        except (TypeError, ValueError):
            self._error(sess, "to", "缺少目标用户")
            return None
        with self.lock:
            tsess = self.sessions.get(to)
            if tsess is None or tsess.type != "tcp":
                self._error(sess, "offline", "对方不在线或端不支持密聊")
                return None
        if self._is_blocked_by(sess.uid, to):
            self._error(sess, "blocked", "你已被对方屏蔽，无法发起密聊/通话")
            return None
        return tsess

    def _on_e2ee_pub(self, sess: Session, header: dict) -> None:
        """1v1 握手第一步：把发起者身份公钥单播给目标（服务器不见私钥）。
        R42：rs=发起方握手随机盐（服务器不解析，纯透传）。"""
        tsess = self._e2ee_target(sess, header.get("to"))
        if tsess is None:
            return
        try:
            tsess.send({"t": MsgType.E2EE_PUB.value, "from": sess.uid,
                        "pub": str(header.get("pub") or ""),
                        "nonce": str(header.get("nonce") or ""),
                        "rs": str(header.get("rs") or "")})
        except Exception:
            pass
        self.audit.log(type="e2ee_handshake", uid=sess.uid, to=tsess.uid)

    def _on_e2ee_pub_ack(self, sess: Session, header: dict) -> None:
        """1v1 握手第二步：应答方身份公钥单播回发起者。
        R42：rs=应答方随机盐 / rv=协议版本 / dup=并发握手去重标记（纯透传）。"""
        tsess = self._e2ee_target(sess, header.get("to"))
        if tsess is None:
            return
        try:
            fwd = {"t": MsgType.E2EE_PUB_ACK.value, "from": sess.uid,
                   "pub": str(header.get("pub") or ""),
                   "nonce": str(header.get("nonce") or ""),
                   "rs": str(header.get("rs") or "")}
            if header.get("rv"):
                fwd["rv"] = 2
            if header.get("dup"):
                fwd["dup"] = 1
            tsess.send(fwd)
        except Exception:
            pass
        self.audit.log(type="e2ee_handshake", uid=sess.uid, to=tsess.uid)

    def _on_e2ee_chat(self, sess: Session, header: dict, body: bytes) -> None:
        """1v1 密聊正文：密文原样转发（不进 bus 历史、不落盘、无 seq）。"""
        tsess = self._e2ee_target(sess, header.get("to"))
        if tsess is None:
            return
        try:
            tsess.send({"t": MsgType.E2EE_CHAT.value, "from": sess.uid}, body)
        except Exception:
            pass
        self.audit.log(type="e2ee_chat", uid=sess.uid, to=tsess.uid, length=len(body))

    def _on_e2ee_group(self, sess: Session, header: dict, body: bytes) -> None:
        """群密聊正文：密文原样广播给群内其他在线成员（不进历史）。"""
        if sess.type != "tcp":           # R50：网页端一律禁入 E2EE
            self._error(sess, "e2ee", "密聊为端到端加密，仅桌面端支持")
            return
        try:
            gid = int(header.get("gid"))
            epoch = int(header.get("epoch") or 0)
        except (TypeError, ValueError):
            self._error(sess, "gid", "缺少群号")
            return
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "forbid", "不在该群，无法发密聊")
            return
        for u, s in self._chan_recipients("group", sess.uid, gid):
            if u == sess.uid:
                continue
            try:
                s.send({"t": MsgType.E2EE_GROUP.value, "gid": gid,
                        "epoch": epoch, "from": sess.uid}, body)
            except Exception:
                pass
        self.audit.log(type="e2ee_group", uid=sess.uid, gid=gid, length=len(body))

    def _on_e2ee_sk_dist(self, sess: Session, header: dict) -> None:
        """sender key 分发：envelopes=[{to,ct(hex)}] 拆成单信封逐个单播；
        目标离线则丢弃该信封（对方上线后经 SK_REQ 补齐）。"""
        if sess.type != "tcp":           # R50：网页端不参与群密聊
            self._error(sess, "e2ee", "密聊为端到端加密，仅桌面端支持")
            return
        try:
            gid = int(header.get("gid"))
            epoch = int(header.get("epoch") or 0)
        except (TypeError, ValueError):
            self._error(sess, "gid", "缺少群号")
            return
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "forbid", "不在该群，无法分发密钥")
            return
        envs = header.get("envelopes")
        if not isinstance(envs, list) or not envs or len(envs) > 256:
            self._error(sess, "envelopes", "信封列表非法")
            return
        for e in envs:
            if not isinstance(e, dict) or "to" not in e:
                continue
            try:
                to = int(e["to"])
            except (TypeError, ValueError):
                continue
            if to == sess.uid:
                continue
            with self.lock:
                tsess = self.sessions.get(to)
                ok = tsess is not None and tsess.type == "tcp" and to in g["members"]
            if not ok:
                continue
            try:
                tsess.send({"t": MsgType.E2EE_SK_DIST_ONE.value, "gid": gid,
                            "epoch": epoch, "from": sess.uid,
                            "ct": str(e.get("ct") or "")})
            except Exception:
                pass
        self.audit.log(type="e2ee_sk_dist", uid=sess.uid, gid=gid, count=len(envs))

    def _on_e2ee_sk_req(self, sess: Session, header: dict) -> None:
        """离线成员上线补发请求：广播给群内其他在线成员（各成员自行回发信封）。"""
        if sess.type != "tcp":           # R50：网页端不参与群密聊
            self._error(sess, "e2ee", "密聊为端到端加密，仅桌面端支持")
            return
        try:
            gid = int(header.get("gid"))
        except (TypeError, ValueError):
            self._error(sess, "gid", "缺少群号")
            return
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "forbid", "不在该群")
            return
        for u, s in self._chan_recipients("group", sess.uid, gid):
            if u == sess.uid:
                continue
            try:
                s.send({"t": MsgType.E2EE_SK_REQ.value, "gid": gid, "from": sess.uid})
            except Exception:
                pass
        self.audit.log(type="e2ee_sk_req", uid=sess.uid, gid=gid)

    # ---------- R37 加密云历史（服务器只存密文 blob，解不出内容） ----------

    def _cloud_load_disk(self) -> None:
        """启动时从 cloud/ 目录恢复密文备份（损坏文件跳过）。"""
        try:
            for fn in os.listdir(self.cloud_dir):
                if not fn.endswith(".bin") or not fn[:-4].isdigit():
                    continue
                path = os.path.join(self.cloud_dir, fn)
                try:
                    with open(path, "rb") as f:
                        blob = f.read()
                    if blob:
                        self.cloud[int(fn[:-4])] = {
                            "blob": blob, "ts": os.path.getmtime(path)}
                except (OSError, ValueError):
                    continue
        except OSError:
            pass

    def _on_cloud_put(self, sess: Session, header: dict, body: bytes) -> None:
        """上传：body=客户端 AES-GCM 密文 blob（服务器不解析）。按 uid 存最新一份。"""
        blob = bytes(body or b"")
        if not blob or len(blob) > cloud_history_mod.CLOUD_BLOB_MAX:
            self._error(sess, "cloud",
                        f"备份大小无效（上限 {cloud_history_mod.CLOUD_BLOB_MAX} 字节）")
            return
        ts = _now()
        self.cloud[sess.uid] = {"blob": blob, "ts": ts}
        path = os.path.join(self.cloud_dir, f"{sess.uid}.bin")
        try:
            with open(path, "wb") as f:
                f.write(blob)
        except OSError:
            pass                                  # 落盘失败仍保留内存份
        try:
            sess.send({"t": MsgType.CLOUD_DONE.value, "size": len(blob), "ts": ts})
        except Exception:
            pass
        self.audit.log(type="cloud_put", uid=sess.uid, size=len(blob))

    def _on_cloud_get(self, sess: Session) -> None:
        """拉取：回本账号密文 blob（无备份时 size=0 空 body）。"""
        rec = self.cloud.get(sess.uid)
        blob = rec["blob"] if rec else b""
        try:
            sess.send({"t": MsgType.CLOUD_DATA.value,
                       "size": len(blob),
                       "ts": float(rec.get("ts") or 0) if rec else 0}, blob)
        except Exception:
            pass
        self.audit.log(type="cloud_get", uid=sess.uid, size=len(blob))

    def _burn_same_convo(self, br: dict, uid: int, to) -> bool:
        if br["channel"] == "public":
            return True
        if br["channel"] == "private":
            return uid in (br["uid"], br["to"])
        return br["channel"] == "group" and br["to"] == to

    def _burn_ready(self, br: dict, reads: dict, burn_seq: int) -> bool:
        """阅后即焚删除条件：所有待读目标方都读到 >= burn_seq。"""
        if not br["pend"]:
            return True
        return all(reads.get(u, 0) >= burn_seq for u in br["pend"])

    def _burn_finish(self, seq: int, br: dict) -> None:
        """广播 del 并清理服务器历史/内存（阅后即焚删除）。"""
        with self.lock:                               # 锁内操纵共享 _burn/bus
            self._burn.pop(seq, None)
            with self.bus._lock:
                _key, msg = self.bus.find(seq)
            for _u, s in self._chan_recipients(br["channel"], br["uid"], br["to"]):
                try:
                    s.send({"t": MsgType.MSG_DEL.value, "seq": seq,
                            "channel": br["channel"], "uid": br["uid"], "to": br["to"],
                            "burn": True})
                except Exception:
                    pass
            if msg is not None:
                self.bus.discard(seq)
            self.audit.log(type="burn", uid=br["uid"], seq=seq)
        self._persist()                              # R16：阅后即焚删除落盘

    def _burn_ttl_sweep(self) -> None:
        """阅后即焚兜底：长期没人读到也删除，防删不掉堆积（惰性触发）。"""
        now = _now()
        for bseq, br in list(self._burn.items()):
            if now - br.get("ts", now) > self.cfg.burn_ttl:
                self._burn_finish(bseq, br)

    def _on_purge(self, sess: Session, header: dict) -> None:
        """R14 会话清理：丢弃该频道 seq<=until_seq 的消息并广播，供客户端删历史。"""
        channel = header.get("channel") or "public"
        to = header.get("to")
        try:
            until_seq = int(header.get("until_seq"))
        except (TypeError, ValueError):
            self._error(sess, "seq", "缺少 until_seq")
            return
        # 权限：必须在该频道内才能清理
        if channel == "public":
            pass
        elif channel == "group":
            g = self.groups.get(to)
            if not g or sess.uid not in g["members"]:
                self._error(sess, "forbid", "不在该群，无法清理")
                return
        elif channel == "private":
            if sess.uid not in (int(header.get("uid") or 0), int(to or 0)):
                self._error(sess, "forbid", "不在该会话，无法清理")
                return
        else:
            self._error(sess, "channel", "未知频道")
            return
        removed = self.bus.purge(channel, sess.uid, to, until_seq)
        key = self._conv_key(channel, sess.uid, to)
        for _u, s in self._chan_recipients(channel, sess.uid, to):
            try:
                s.send({"t": MsgType.PURGE.value, "channel": channel, "key": key,
                        "uid": sess.uid, "to": to, "until_seq": until_seq,
                        "removed": removed})
            except Exception:
                pass
        self.audit.log(type="purge", uid=sess.uid, channel=channel,
                       to=to, until_seq=until_seq, removed=removed)
        self._persist()                              # R16：清理后历史落盘

    # ---------- R29B 草稿同步 ----------
    def _on_draft_set(self, sess: Session, header: dict) -> None:
        """R29B 草稿同步：按 (uid,key) 存服务器内存（空文本=清除）。
        单 uid 单会话（防双开顶号）→ 无需中继广播；换端登录时随 welcome 带回。"""
        channel = header.get("channel") or "public"
        if channel not in ("public", "private", "group"):
            return
        text = str(header.get("text") or "").strip()[:4000]
        key = self._conv_key(channel, sess.uid, header.get("to"))
        with self.lock:
            if text:
                self._drafts[(sess.uid, key)] = {"text": text, "ts": _now()}
            else:
                self._drafts.pop((sess.uid, key), None)
        self._persist()                              # R16：草稿变化也落盘（服务器重启不丢）

    def _drafts_for(self, uid: int) -> list:
        """R29B：返回该 uid 全部草稿 [{key,text,ts}]（惰性清过期，防内存堆积）。"""
        now = _now()
        out, drop = [], []
        with self.lock:
            for (u, key), d in self._drafts.items():
                if u != uid:
                    continue
                if now - d.get("ts", 0) > DRAFT_TTL:
                    drop.append((u, key))
                    continue
                out.append({"key": key, "text": d["text"],
                            "ts": round(d.get("ts", now), 3)})
            for k in drop:
                self._drafts.pop(k, None)
        return out

    # ---------- R30C 自定义表情包 ----------
    _STICKER_EXTS = ("png", "jpg", "jpeg", "gif", "webp", "bmp", "json")  # R38C: json=Lottie 动画贴纸

    def _custom_list(self) -> list:
        """自定义贴纸清单（按 code 排序，保证所有端一致）。"""
        with self.lock:
            return [dict(self.custom_stickers[c])
                    for c in sorted(self.custom_stickers)]

    def _broadcast_sticker_list(self) -> None:
        """贴纸清单变化后向全部在线会话广播（桌面端缓存图片 + 刷新面板；网页端刷列表）。"""
        payload = {"t": "sticker_list", "stickers": self.stickers,
                   "custom_stickers": self._custom_list(),
                   "sticker_pack_meta": self._pack_meta_payload()}   # R64 包封面元数据
        for s in self._snapshot_sessions():      # 同 uid 多端都收到
            s.send(payload)

    # ---------- R64 贴纸包深化：包封面 / 包管理 / 包内排序 ----------
    def _pack_cover_path(self, pack: str, ext: str) -> str:
        """包封面文件名由包名 md5 派生（包名可为中文/空格，避免直接做文件名）。"""
        h = hashlib.md5(("pack:" + str(pack)).encode("utf-8")).hexdigest()[:16]
        return os.path.join(self.pack_cover_dir, f"{h}.{ext}")

    def _pack_meta_payload(self) -> dict:
        """包封面元数据（只带 ext，不含字节；客户端缺图时按需拉取）。"""
        with self.lock:
            return {k: dict(v) for k, v in self.pack_meta.items()}

    @staticmethod
    def _valid_pack_name(pack: str) -> bool:
        return bool(pack) and len(pack) <= 16 and all(
            ch.isalnum() or ch in "_- " for ch in pack)

    def _on_sticker_pack_rename(self, sess: Session, header: dict) -> None:
        """重命名自定义包：包内贴纸改挂新包名，封面随迁。"""
        old = str(header.get("old") or "").strip()[:16]
        new = str(header.get("new") or "").strip()[:16]
        if not self._valid_pack_name(new):
            self._error(sess, "sticker", "包名需为 1~16 位中英文/数字/空格/_-")
            return
        if not old or old == new:
            return
        err = ""
        with self.lock:
            codes = [c for c, v in self.custom_stickers.items()
                     if (v.get("pack") or "") == old]
            if not codes:
                err = "包不存在或没有贴纸"
            elif any((v.get("pack") or "") == new
                     for v in self.custom_stickers.values()):
                err = "同名贴纸包已存在"
            else:
                meta = dict(self.pack_meta.get(old) or {})
                moved = False
                if meta.get("cover"):
                    try:                       # 先把封面文件搬到新名，再改状态
                        os.replace(self._pack_cover_path(old, meta["cover"]),
                                   self._pack_cover_path(new, meta["cover"]))
                        moved = True
                    except OSError:
                        moved = False
                for c in codes:
                    self.custom_stickers[c]["pack"] = new
                self.pack_meta.pop(old, None)
                if moved:
                    self.pack_meta[new] = meta
        if err:                                    # 出锁后再回错误帧，避免持锁写 socket
            self._error(sess, "sticker", err)
            return
        self._persist()
        self._broadcast_sticker_list()
        self.audit.log(type="sticker_pack_rename", uid=sess.uid, nick=sess.nick,
                       old=old, new=new, n=len(codes))

    def _on_sticker_pack_del(self, sess: Session, header: dict) -> None:
        """删除自定义包（连包内贴纸与封面一并清除）。"""
        pack = str(header.get("pack") or "").strip()[:16]
        if not pack:
            return
        with self.lock:
            codes = [c for c, v in self.custom_stickers.items()
                     if (v.get("pack") or "") == pack]
            metas = [self.custom_stickers.pop(c) for c in codes]
            meta = self.pack_meta.pop(pack, None)
        for m in metas:
            try:
                os.remove(os.path.join(self.sticker_dir,
                                       f"{m['code']}.{m.get('ext')}"))
            except OSError:
                pass
        if meta and meta.get("cover"):
            try:
                os.remove(self._pack_cover_path(pack, meta["cover"]))
            except OSError:
                pass
        self._persist()
        self._broadcast_sticker_list()
        self.audit.log(type="sticker_pack_del", uid=sess.uid, nick=sess.nick,
                       pack=pack, n=len(codes))

    def _on_sticker_pack_cover(self, sess: Session, header: dict, body: bytes) -> None:
        """设置/清除包封面：body 为空=清除；否则按扩展名白名单落盘并更新元数据。"""
        pack = str(header.get("pack") or "").strip()[:16]
        if not pack:
            return
        with self.lock:
            has_pack = any((v.get("pack") or "") == pack
                           for v in self.custom_stickers.values())
            old = dict(self.pack_meta.get(pack) or {})
        if not body:
            with self.lock:
                self.pack_meta.pop(pack, None)
            if old.get("cover"):
                try:
                    os.remove(self._pack_cover_path(pack, old["cover"]))
                except OSError:
                    pass
            self._persist()
            self._broadcast_sticker_list()
            self.audit.log(type="sticker_pack_cover_del", uid=sess.uid,
                           nick=sess.nick, pack=pack)
            return
        if not has_pack:
            self._error(sess, "sticker", "包不存在或没有贴纸")
            return
        ext = str(header.get("ext") or "").lower().strip(". ")
        if ext not in self._STICKER_EXTS:
            self._error(sess, "sticker", "仅支持 png/jpg/jpeg/gif/webp/bmp")
            return
        if len(body) > self.cfg.sticker_max_bytes:
            self._error(sess, "sticker",
                        f"封面超过 {self.cfg.sticker_max_bytes // 1024}KB 上限")
            return
        if old.get("cover") and old["cover"] != ext:
            try:
                os.remove(self._pack_cover_path(pack, old["cover"]))
            except OSError:
                pass
        try:
            with open(self._pack_cover_path(pack, ext), "wb") as f:
                f.write(body)
        except OSError:
            self._error(sess, "sticker", "封面保存失败")
            return
        with self.lock:
            self.pack_meta[pack] = {"cover": ext}
        self._persist()
        self._broadcast_sticker_list()
        self.audit.log(type="sticker_pack_cover", uid=sess.uid, nick=sess.nick,
                       pack=pack, size=len(body))

    def _on_sticker_pack_cover_get(self, sess: Session, header: dict) -> None:
        """拉取包封面：单播回 body（客户端落缓存后渲染导航条缩略图）。"""
        pack = str(header.get("pack") or "").strip()[:16]
        with self.lock:
            meta = dict(self.pack_meta.get(pack) or {})
        ext = str(meta.get("cover") or "")
        if not ext:
            self._error(sess, "sticker", "该包暂无封面")
            return
        try:
            with open(self._pack_cover_path(pack, ext), "rb") as f:
                data = f.read()
        except OSError:
            self._error(sess, "sticker", "封面读取失败")
            return
        sess.send({"t": "sticker_pack_cover_data", "pack": pack, "ext": ext}, data)

    def _on_sticker_reorder(self, sess: Session, header: dict) -> None:
        """包内排序：把某条贴纸在包内上移/下移/置顶/置底，随后重排 order。"""
        code = str(header.get("code") or "").strip()
        direction = str(header.get("dir") or "").strip().lower()
        if direction not in ("up", "down", "top", "bottom"):
            self._error(sess, "sticker", "排序方向非法")
            return
        with self.lock:
            meta = self.custom_stickers.get(code)
            if not meta:
                missing = True
            else:
                missing = False
                pack = meta.get("pack") or ""
                codes = [c for _o, c in sorted(
                    (int(v.get("order") or 0), c)
                    for c, v in self.custom_stickers.items()
                    if (v.get("pack") or "") == pack)]
                if code in codes:
                    i = codes.index(code)
                    if direction == "up" and i > 0:
                        codes[i - 1], codes[i] = codes[i], codes[i - 1]
                    elif direction == "down" and i < len(codes) - 1:
                        codes[i + 1], codes[i] = codes[i], codes[i + 1]
                    elif direction == "top":
                        codes.insert(0, codes.pop(i))
                    elif direction == "bottom":
                        codes.append(codes.pop(i))
                    for idx, c in enumerate(codes):
                        self.custom_stickers[c]["order"] = idx
        if missing:                       # 出锁后再回错误帧，避免持锁写 socket
            self._error(sess, "sticker", "贴纸不存在")
            return
        self._persist()
        self._broadcast_sticker_list()
        self.audit.log(type="sticker_reorder", uid=sess.uid, nick=sess.nick,
                       code=code, dir=direction)

    def _on_sticker_custom_add(self, sess: Session, header: dict, body: bytes) -> None:
        """R30C 上传自定义贴纸：code/label/ext 走 header，图片字节走 body。
        校验：短码合法、扩展名白名单、大小上限；成功后落盘 + 广播新清单。"""
        code = str(header.get("code") or "").strip()
        label = str(header.get("label") or "").strip()[:16]
        pack = str(header.get("pack") or "").strip()[:16]
        ext = str(header.get("ext") or "").lower().strip(". ")
        if not stickers.is_valid_custom_code(code):
            self._error(sess, "sticker", "短码需为 1~24 位字母/数字/下划线")
            return
        if pack and not all(ch.isalnum() or ch in "_- " for ch in pack):
            self._error(sess, "sticker", "包名仅支持中英文/数字/空格/_-")
            return
        if ext not in self._STICKER_EXTS:
            self._error(sess, "sticker", "仅支持 png/jpg/jpeg/gif/webp/bmp")
            return
        if not body:
            self._error(sess, "sticker", "图片内容为空")
            return
        if len(body) > self.cfg.sticker_max_bytes:
            self._error(sess, "sticker",
                        f"图片超过 {self.cfg.sticker_max_bytes // 1024}KB 上限")
            return
        path = os.path.join(self.sticker_dir, f"{code}.{ext}")
        old = self.custom_stickers.get(code)
        if old and old.get("ext") != ext:
            try:
                os.remove(os.path.join(self.sticker_dir,
                                       f"{code}.{old.get('ext')}"))
            except OSError:
                pass
        try:
            with open(path, "wb") as f:
                f.write(body)
        except OSError:
            self._error(sess, "sticker", "图片保存失败")
            return
        with self.lock:
            n = sum(1 for v in self.custom_stickers.values()
                    if (v.get("pack") or "") == pack)
            self.custom_stickers[code] = {"code": code, "label": label,
                                          "pack": pack, "ext": ext,
                                          "order": n}   # R64：新贴纸排在包尾
        self._persist()
        self._broadcast_sticker_list()
        self.audit.log(type="sticker_custom_add", uid=sess.uid, nick=sess.nick,
                       code=code, size=len(body))

    # ---------- 朋友圈（图文动态时间轴；全服广播 + 快照持久化） ----------
    def _feed_sorted(self) -> list:
        """时间轴按 pid 倒序（新的在前）。"""
        return [dict(p) for _, p in sorted(self.moments.items(), reverse=True)]

    def _broadcast_moment(self, payload: dict) -> None:
        for s in self._snapshot_sessions():       # 同 uid 多端都收到动态广播
            try:
                s.send(payload)
            except Exception:
                pass

    def _on_moment_publish(self, sess: Session, header: dict, body: bytes) -> None:
        """R59 发布图文动态：header 带 text/n_imgs/exts；body=每图[u32 长度+字节]依次拼接。"""
        text = str(header.get("text") or "").strip()[:2000]
        if not text and not body:
            self._error(sess, "moment", "动态内容为空")
            return
        raw_ex = header.get("exts") or []
        if isinstance(raw_ex, str):
            raw_ex = [raw_ex]
        exts = [str(x).lower().strip(". ") for x in raw_ex[:9]]
        # 解析内嵌多图
        imgs = []
        pos, ok = 0, True
        for _ in exts:
            if pos + 4 > len(body):
                ok = False
                break
            ln = int.from_bytes(body[pos:pos + 4], "big")
            pos += 4
            if pos + ln > len(body):
                ok = False
                break
            imgs.append(body[pos:pos + ln])
            pos += ln
        if not ok:
            self._error(sess, "moment", "动态图片数据不完整")
            return
        with self.lock:
            self._pid_seq += 1
            pid = self._pid_seq
            post = {"pid": pid, "uid": sess.uid, "nick": sess.nick, "text": text,
                    "ts": round(time.time(), 3), "images": [], "likes": [], "comments": []}
            for i, blob in enumerate(imgs):
                ext = (exts[i] if i < len(exts) and exts[i] in self._STICKER_EXTS else "jpg")
                fn = f"{pid}_{i}.{ext}"
                try:
                    with open(os.path.join(self.moment_dir, fn), "wb") as f:
                        f.write(blob)
                    post["images"].append(fn)
                except OSError:
                    pass
            self.moments[pid] = post
        self._persist()
        self._broadcast_moment({"t": "moment_new", "post": post})
        self.audit.log(type="moment_publish", uid=sess.uid, nick=sess.nick,
                       pid=pid, n_img=len(post["images"]), text=text[:60])

    def _on_moment_like(self, sess: Session, header: dict) -> None:
        pid = int(header.get("pid") or 0)
        want = bool(header.get("on"))
        with self.lock:
            post = self.moments.get(pid)
            if not post:
                self._error(sess, "moment", "动态不存在")
                return
            likes = list(post.get("likes") or [])
            if want:
                if sess.uid not in likes:
                    likes.append(sess.uid)
            else:
                likes = [u for u in likes if u != sess.uid]
            post["likes"] = likes
            snap = dict(post)
        self._persist()
        self._broadcast_moment({"t": "moment_update", "pid": pid, "post": snap})

    def _on_moment_comment(self, sess: Session, header: dict) -> None:
        pid = int(header.get("pid") or 0)
        cmt = str(header.get("text") or "").strip()[:500]
        if not cmt:
            self._error(sess, "moment", "评论为空")
            return
        # 楼中楼：header 可选 rep_uid / rep_nick（被回复者的 uid/昵称）
        rep = None
        rep_uid = header.get("rep_uid")
        rep_nick = str(header.get("rep_nick") or "").strip()[:50]
        if rep_uid is not None or rep_nick:
            try:
                rep = {"uid": int(rep_uid) if rep_uid is not None else None,
                       "nick": rep_nick}
            except (TypeError, ValueError):
                rep = None
        with self.lock:
            post = self.moments.get(pid)
            if not post:
                self._error(sess, "moment", "动态不存在")
                return
            item = {"uid": sess.uid, "nick": sess.nick, "text": cmt,
                    "ts": round(time.time(), 3)}
            if rep:
                item["rep"] = rep
            post.setdefault("comments", []).append(item)
            snap = dict(post)
        self._persist()
        self._broadcast_moment({"t": "moment_update", "pid": pid, "post": snap})

    def _on_moment_del(self, sess: Session, header: dict) -> None:
        """删除动态：服务端强制校验作者=本人（越权回 error）。"""
        pid = int(header.get("pid") or 0)
        with self.lock:
            post = self.moments.get(pid)
            if not post:
                self._error(sess, "moment", "动态不存在")
                return
            if post.get("uid") != sess.uid:
                self._error(sess, "moment", "只能删除自己的动态")
                return
            images = [str(fn) for fn in (post.get("images") or [])]
            self.moments.pop(pid, None)
            # 只删除本动态独占且位于 moments 根目录内的文件。即使旧状态中
            # 出现重复文件名，也不能误删仍被其它动态引用的图片。
            remaining_images = {
                str(fn)
                for other in self.moments.values()
                for fn in (other.get("images") or [])
            }
            paths = [self._moment_image_path(fn)
                     for fn in images
                     if fn not in remaining_images]
        for path in paths:
            if not path:
                continue
            try:
                os.remove(path)
            except OSError:
                pass
        self._persist()
        self._broadcast_moment({"t": "moment_update", "pid": pid, "post": None})
        self.audit.log(type="moment_del", uid=sess.uid, nick=sess.nick, pid=pid)

    def _on_moment_feed(self, sess: Session) -> None:
        with self.lock:
            posts = self._feed_sorted()
        sess.send({"t": "moment_feed", "posts": posts})

    def _moment_image_path(self, fn: str) -> str | None:
        """返回 moments 根目录下的安全图片路径；非法/越界名称返回 None."""
        fn = str(fn or "")
        base = os.path.basename(fn)
        if base != fn or "." not in base:
            return None
        root = os.path.realpath(self.moment_dir)
        path = os.path.realpath(os.path.join(root, base))
        try:
            if os.path.commonpath((root, path)) != root:
                return None
        except ValueError:                # 不同盘符等异常路径
            return None
        return path

    def _moment_image_active(self, fn: str) -> bool:
        """在 Hub 锁内确认文件名仍被现存动态引用。"""
        base = str(fn or "")
        if self._moment_image_path(base) is None:
            return False
        with self.lock:
            return any(base in (post.get("images") or [])
                       for post in self.moments.values())

    def _on_moment_img_get(self, sess: Session, header: dict) -> None:
        """按文件名回当前动态图片字节（防路径穿越：仅允许 moments 目录内文件）。"""
        fn = str(header.get("fn") or "")
        base = os.path.basename(fn)
        if base != fn or "." not in base:
            self._error(sess, "moment", "非法文件名")
            return
        if not self._moment_image_active(base):
            self._error(sess, "moment", "图片不存在")
            return
        path = self._moment_image_path(base)
        if path is None:
            self._error(sess, "moment", "非法文件名")
            return
        try:
            with open(path, "rb") as f:
                blob = f.read()
        except OSError:
            self._error(sess, "moment", "图片不存在")
            return
        sess.send({"t": "moment_data", "fn": base,
                   "ext": base.rsplit(".", 1)[-1].lower()}, body=blob)

    # ----- 朋友圈封面（每人一个：预设渐变 / 上传图片，本体落盘 covers/{uid}.{ext}） -----
    def _cover_path(self, uid: int) -> str:
        return os.path.join(self.cover_dir, f"{uid}.jpg")

    def _cover_meta(self, uid: int) -> dict | None:
        c = self.moment_covers.get(uid)
        if not c:
            return None
        return dict(c)

    def _on_moment_cover_set(self, sess: Session, header: dict, body: bytes) -> None:
        """预设：header{preset:n}；上传：header{ext} + body=图片字节（≤2MB）。"""
        uid = sess.uid
        preset = header.get("preset")
        if preset is not None:
            try:
                n = int(preset)
            except (TypeError, ValueError):
                self._error(sess, "moment", "非法预设封面")
                return
            if not 0 <= n < self._COVER_PRESETS:
                self._error(sess, "moment", "预设封面序号越界")
                return
            # 上传图片切换预设时清掉旧图片
            old = self.moment_covers.pop(uid, None)
            if old and old.get("mode") == "img":
                try:
                    os.remove(self._cover_path(uid))
                except OSError:
                    pass
            with self.lock:
                self.moment_covers[uid] = {"mode": "preset", "preset": n,
                                           "ext": None}
            self._persist()
            self._broadcast_moment({"t": "moment_cover", "uid": uid,
                                    "cover": self._cover_meta(uid)})
            self.audit.log(type="moment_cover_preset", uid=uid, nick=sess.nick,
                           preset=n)
            return
        # 上传图片封面
        ext = str(header.get("ext") or "").lower().strip(". ")
        if ext not in self._COVER_EXTS or not body:
            self._error(sess, "moment", "封面图片为空或格式不支持")
            return
        if len(body) > self._COVER_MAX:
            self._error(sess, "moment", "封面图片不能超过 2MB")
            return
        try:
            with open(self._cover_path(uid), "wb") as f:
                f.write(body)
        except OSError:
            self._error(sess, "moment", "封面保存失败")
            return
        with self.lock:
            self.moment_covers[uid] = {"mode": "img", "preset": None,
                                       "ext": ext}
        self._persist()
        self._broadcast_moment({"t": "moment_cover", "uid": uid,
                                "cover": self._cover_meta(uid)})
        self.audit.log(type="moment_cover_img", uid=uid, nick=sess.nick,
                       ext=ext, size=len(body))

    def _on_moment_cover_get(self, sess: Session) -> None:
        """回我的封面：img 模式附带图片字节（body）。"""
        uid = sess.uid
        meta = self._cover_meta(uid)
        if meta and meta.get("mode") == "img":
            try:
                with open(self._cover_path(uid), "rb") as f:
                    blob = f.read()
            except OSError:
                blob = b""
            if blob:
                sess.send({"t": "moment_cover", "uid": uid, "cover": meta},
                          body=blob)
                return
            meta = None
        sess.send({"t": "moment_cover", "uid": uid, "cover": meta})

    def _on_moment_cover_del(self, sess: Session) -> None:
        """恢复默认封面：清掉本用户封面设置与图片文件。"""
        uid = sess.uid
        with self.lock:
            old = self.moment_covers.pop(uid, None)
        if old and old.get("mode") == "img":
            try:
                os.remove(self._cover_path(uid))
            except OSError:
                pass
        self._persist()
        self._broadcast_moment({"t": "moment_cover", "uid": uid, "cover": None})
        self.audit.log(type="moment_cover_del", uid=uid, nick=sess.nick)

    def _on_sticker_custom_del(self, sess: Session, header: dict) -> None:
        """R30C 删除自定义贴纸（局域网互信：登录即可删）。"""
        code = str(header.get("code") or "").strip()
        meta = self.custom_stickers.get(code)
        if not meta:
            self._error(sess, "sticker", "贴纸不存在")
            return
        try:
            os.remove(os.path.join(self.sticker_dir,
                                   f"{code}.{meta.get('ext')}"))
        except OSError:
            pass
        with self.lock:
            self.custom_stickers.pop(code, None)
        self._persist()
        self._broadcast_sticker_list()
        self.audit.log(type="sticker_custom_del", uid=sess.uid, nick=sess.nick,
                       code=code)

    def _on_sticker_custom_get(self, sess: Session, header: dict) -> None:
        """R30C 拉取贴纸图片：单播回 body（客户端落缓存后渲染）。"""
        code = str(header.get("code") or "").strip()
        meta = self.custom_stickers.get(code)
        if not meta:
            self._error(sess, "sticker", "贴纸不存在")
            return
        path = os.path.join(self.sticker_dir, f"{code}.{meta.get('ext')}")
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            self._error(sess, "sticker", "图片读取失败")
            return
        sess.send({"t": "sticker_custom_data", "code": code,
                   "ext": meta.get("ext")}, data)

    # ---------- R35 贴纸商店 ----------
    def _sticker_subs_for(self, uid: int) -> list:
        """当前订阅列表（未自选过 → 默认订阅 DEFAULT_SUBS）。"""
        with self.lock:
            return sorted(self.sticker_subs.get(uid) or stickers.DEFAULT_SUBS)

    def _on_sticker_shop(self, sess: Session, header: dict) -> None:
        """R35 贴纸商店：回商店目录（内置包合集）+ 当前订阅。"""
        sess.send({"t": "sticker_shop_list", "packs": stickers.shop_catalog(),
                   "subs": self._sticker_subs_for(sess.uid)})

    def _on_sticker_sub(self, sess: Session, header: dict) -> None:
        """R35 订阅/退订包：校验 pack_id → 更新订阅状态（内存态，welcome 带回），
        回帧带全量订阅（客户端直接覆盖本地 prefs）。"""
        pack_id = str(header.get("pack_id") or "").strip()
        on = bool(header.get("on"))
        if not stickers.valid_pack_id(pack_id):
            self._error(sess, "pack", "未知表情包")
            return
        with self.lock:
            subs = set(self.sticker_subs.get(sess.uid) or stickers.DEFAULT_SUBS)
            if on:
                subs.add(pack_id)
            else:
                subs.discard(pack_id)
            self.sticker_subs[sess.uid] = sorted(subs)
        self.audit.log(type="sticker_sub", uid=sess.uid, nick=sess.nick,
                       pack=pack_id, on=on)
        sess.send({"t": "sticker_sub", "pack_id": pack_id, "on": on,
                   "subs": sorted(subs)})

    def _on_pin(self, sess: Session, header: dict) -> None:
        """R13 消息置顶：会话级单条置顶（on=True 置顶 / False 取消），广播快照。"""
        try:
            seq = int(header.get("seq"))
        except (TypeError, ValueError):
            self._error(sess, "seq", "缺少 seq")
            return
        on = bool(header.get("on", True))
        with self.bus._lock:
            _key, msg = self.bus.find(seq)
        if msg is None:
            self._error(sess, "expired", "消息已不在服务器历史中")
            return
        if not self._chan_member(sess, msg):
            self._error(sess, "forbid", "不在该频道，无法置顶")
            return
        key = self._conv_key(msg["channel"], msg["uid"], msg.get("to"))
        # 锁内修改共享 pins：置顶快照为跨线程共享，需串行化
        with self.lock:
            if on:
                self.pins[key] = {"seq": seq, "nick": msg.get("nick"),
                                  "text": msg.get("text", ""),
                                  "sticker": msg.get("sticker", ""),
                                  "ts": msg.get("ts", 0)}
            else:
                self.pins.pop(key, None)
            snap = dict(self.pins.get(key) or {})
        for _u, s in self._chan_recipients(msg["channel"], msg["uid"],
                                           msg.get("to")):
            try:
                s.send({"t": MsgType.PIN.value, "channel": msg["channel"],
                        "key": key, "uid": msg.get("uid"), "to": msg.get("to"),
                        "seq": seq, "on": on, "msg": snap})
            except Exception:
                pass
        self.audit.log(type="pin", uid=sess.uid, seq=seq, on=on)

    def _pins_for(self, sess: Session) -> list:
        """该用户可见的置顶（public 恒可见；private 仅两端；group 仅成员）。
        每条含 key 供客户端直接写入 self.pins。"""
        with self.lock:
            out = []
            for key, p in self.pins.items():
                if key == "public":
                    out.append(dict(p, key=key))
                elif key.startswith("private:"):
                    parts = key.split(":")
                    if len(parts) == 3 and sess.uid in (int(parts[1]), int(parts[2])):
                        out.append(dict(p, key=key))
                elif key.startswith("group:"):
                    try:
                        gid = int(key.split(":", 1)[1])
                    except ValueError:
                        continue
                    g = self.groups.get(gid)
                    # R54：管理员非成员也可见群置顶
                    if g and (sess.uid in g["members"] or sess.is_admin):
                        out.append(dict(p, key=key))
            return out

    def _history_key(self, sess: Session, channel: str, to) -> str | None:
        if channel == "public":
            return "all"
        if channel == "private":
            to = int(to) if isinstance(to, int) else None
            # R63：放宽拦截——to==自己（收藏夹/发给自己）允许读写该会话历史
            # （旧对象仍只拦 to==None/to==0 公共侧，不破坏既有访问控制）
            if to is None or to == 0:
                return None
            return ChatBus.key("private", sess.uid, to)
        if channel == "group":
            g = self.groups.get(to)
            # R54：管理员非成员也可拉群历史（含私有群）
            if not g or (sess.uid not in g["members"] and not sess.is_admin):
                return None
            return f"group:{to}"
        return None

    def _on_history(self, sess: Session, header: dict) -> None:
        channel = header.get("channel") or "public"
        to = header.get("to")
        key = self._history_key(sess, channel, to)
        if key is None:
            self._error(sess, "deny", "无权限查看该频道历史")
            return
        sess.send({"t": "history", "channel": channel, "to": to,
                   "msgs": [self._san_poll(m, sess.uid) for m in self.bus.history(key)]})

    def _san_poll(self, m: dict, viewer: int) -> dict:
        """R70C：历史回放按观众裁剪投票字段——匿名不泄露 uid→选项（只回本人 mine），
        测验未结束不下发 correct。其余消息原样返回（不复制，避免多余开销）。"""
        poll = m.get("poll")
        if not isinstance(poll, dict):
            return m
        p = self._polls.get(m.get("seq")) or {}
        anon = bool(poll.get("anonymous"))
        quiz = bool(poll.get("quiz"))
        revealed = bool(p.get("revealed")) or _now() >= float(poll.get("end") or 0)
        if not anon and not (quiz and not revealed):
            return m
        out = dict(m)
        np = dict(poll)
        if anon:
            np.pop("votes", None)
            mine = (p.get("votes") or {}).get(viewer)
            np.pop("mine", None)
            if mine is not None:
                if isinstance(mine, int):
                    mine = [mine]
                np["mine"] = [int(x) for x in mine]
        if quiz and revealed and p.get("correct") is not None:
            np["correct"] = int(p["correct"])       # 已结束：答案可在历史中揭示
        out["poll"] = np
        return out

    def _on_thread_fetch(self, sess: Session, header: dict) -> None:
        """R34 群内话题：拉取某根消息的全部话题回复（按频道环形过滤，含权限校验）。"""
        channel = header.get("channel") or "public"
        to = header.get("to")
        key = self._history_key(sess, channel, to)
        if key is None:
            self._error(sess, "deny", "无权限查看该话题")
            return
        try:
            root = int(header.get("root_seq"))
        except (TypeError, ValueError):
            self._error(sess, "thread", "root_seq 无效")
            return
        msgs = [m for m in self.bus.history(key) if m.get("thread_root") == root]
        sess.send({"t": MsgType.THREAD_HISTORY.value, "channel": channel,
                   "to": to, "root_seq": root, "msgs": msgs})

    # ---------- R38 1v1 语音对讲信令（服务器只搭桥：校验在线+回填 ip，音频 UDP 不经服务器） ----------
    def _on_call_ring(self, sess: Session, header: dict) -> None:
        """主叫发起：目标不在线直接回 END 让主叫快速失败（不占服务器状态）。"""
        tsess = self._e2ee_target(sess, header.get("to"))
        if tsess is None:
            sess.send({"t": MsgType.CALL_END.value, "from": sess.uid,
                       "reason": "对方不在线"})
            return
        tsess.send({"t": MsgType.CALL_RING.value, "from": sess.uid,
                    "nick": sess.nick})
        self.audit.log(type="call_ring", uid=sess.uid, to=tsess.uid)

    def _on_call_ready(self, sess: Session, header: dict) -> None:
        """主叫上报 UDP 端口：回填主叫 ip（服务器视角）转发被叫，随后退出信令。"""
        tsess = self._e2ee_target(sess, header.get("to"))
        if tsess is None:
            return
        try:
            port = int(header.get("port") or 0)
        except (TypeError, ValueError):
            port = 0
        if port <= 0 or port > 65535:
            return
        tsess.send({"t": MsgType.CALL_READY.value, "from": sess.uid,
                    "ip": sess.peer_ip, "port": port,
                    **({"vcap": 1} if header.get("vcap") else {})})

    def _on_call_simple(self, sess: Session, header: dict, mtype: str) -> None:
        """ACCEPT/REJECT/END：校验在线后转发（reason 透传给对端）。"""
        tsess = self._e2ee_target(sess, header.get("to"))
        if tsess is None:
            return                          # 对端已离线：其通话状态由超时/断线自行清理
        payload = {"t": mtype, "from": sess.uid}
        reason = str(header.get("reason") or "").strip()
        if reason:
            payload["reason"] = reason[:100]
        # R45 视频能力随 ACCEPT 协商（老客户端无此字段，自然缺省）
        if mtype == MsgType.CALL_ACCEPT.value and header.get("vcap"):
            payload["vcap"] = 1
        tsess.send(payload)
        self.audit.log(type="call_signal", uid=sess.uid, to=tsess.uid,
                       text=mtype.rsplit("_", 1)[-1])

    # ---------- R72 多人语音房（mesh：服务器只发名册/地址，音频 UDP 不经服务器） ----------
    _ROOM_PUBLIC = "public"

    def _room_key_ok(self, sess: Session, room) -> str | None:
        """校验房间键 → 规范化键或 None。room="public" 任意可进；
        room="group:<gid>" 须为该群成员（语音频道即挂在群上）。"""
        if not isinstance(room, str) or not room.strip():
            return None
        r = room.strip()[:64]
        if r == self._ROOM_PUBLIC:
            return r
        if r.startswith("group:"):
            try:
                gid = int(r[6:])
            except (TypeError, ValueError):
                return None
            g = self.groups.get(gid)
            if not g or sess.uid not in g["members"]:
                return None
            return f"group:{gid}"
        return None

    def _room_state_payload(self, room: str) -> dict:
        """构造 ROOM_STATE 名册（调用方持 self.lock）。"""
        members = self.voice_rooms.get(room) or {}
        out = []
        for u in sorted(members):
            s = self.sessions.get(u)
            nick = (s.nick if s else (self.known.get(u) or {}).get("nick")
                    or f"用户{u}")
            out.append({"uid": u, "nick": nick,
                        "port": int(members[u].get("port") or 0)})
        return {"t": MsgType.ROOM_STATE.value, "room": room,
                "count": len(out), "max": self.cfg.voice_room_max,
                "members": out}

    def _room_broadcast(self, room: str, payload: dict, exclude=None) -> None:
        """把 payload 投给房内全部在线会话 + 网页端只读观察者（锁内收集，锁外发帧）。

        R72：网页端无法加入 UDP mesh，但应能通过 SSE 实时看到「谁在语音房」
        （侧栏只读徽标）。公聊房 → 所有 web 在线者都看得到；群聊房 → 群成员中的
        web 在线者可见。不计入 voice_room_max 人数上限。"""
        with self.lock:
            members = self.voice_rooms.get(room) or {}
            member_uids = set(members.keys())
            # 房内 TCP 会话（已在语音房的桌面端）
            tcp_targets = []
            for u in member_uids:
                if exclude is not None and u == exclude:
                    continue
                s = self.sessions.get(u)
                if s is not None:
                    tcp_targets.append(s)
            # R72：网页端只读观察者
            web_observers = []
            if room == self._ROOM_PUBLIC:
                for uid, sess in self.sessions.items():
                    if uid in member_uids:
                        continue
                    if exclude is not None and uid == exclude:
                        continue
                    if sess.type == "web":
                        web_observers.append(sess)
            elif room.startswith("group:"):
                try:
                    gid = int(room[6:])
                except (TypeError, ValueError):
                    gid = None
                g = self.groups.get(gid) if gid else None
                if g:
                    for uid in g["members"]:
                        if uid in member_uids:
                            continue
                        if exclude is not None and uid == exclude:
                            continue
                        s = self.sessions.get(uid)
                        if s and s.type == "web":
                            web_observers.append(s)
        for s in tcp_targets:
            try:
                s.send(payload)
            except Exception:
                pass
        for s in web_observers:
            try:
                s.send(payload)
            except Exception:
                pass

    def _room_drop(self, room: str, uid: int) -> bool:
        """把 uid 摘出语音房并广播名册；空房删除键。返回是否确有变化。"""
        with self.lock:
            members = self.voice_rooms.get(room)
            if not members or uid not in members:
                return False
            del members[uid]
            if members:
                payload = self._room_state_payload(room)
            else:
                self.voice_rooms.pop(room, None)
                payload = None
        if payload is not None:
            self._room_broadcast(room, payload)
        return True

    def _drop_voice_rooms(self, uid: int) -> None:
        """断线/完全离线：把该 uid 从所有语音房摘除。"""
        with self.lock:
            rooms = [r for r, m in self.voice_rooms.items() if uid in m]
        for r in rooms:
            self._room_drop(r, uid)

    def _on_room_join(self, sess: Session, header: dict) -> None:
        """入房：校验房间键 + 人数上限 → 登记 → 广播名册 → 单播在房者地址。

        网页端不支持入房（浏览器无法参与 UDP mesh），只通过 /api/room 只读查看，
        因此 cfg.voice_room_max 天然只算桌面端。
        """
        if sess.type == "web":
            self._error(sess, "room", "网页端不支持加入语音房（只读可见）")
            return
        room = self._room_key_ok(sess, header.get("room"))
        if room is None:
            self._error(sess, "room", "语音房不存在或无权进入")
            return
        with self.lock:
            members = self.voice_rooms.setdefault(room, {})
            d = members.get(sess.uid)
            if d is None:
                if len(members) >= self.cfg.voice_room_max:
                    self._error(sess, "room_full",
                                f"语音房已满（{self.cfg.voice_room_max} 人）")
                    return
                d = members[sess.uid] = {"ip": sess.peer_ip, "port": 0}
            else:
                d["ip"] = sess.peer_ip
            peers = [{"uid": u, "ip": m.get("ip") or "", "port": int(m.get("port") or 0)}
                     for u, m in members.items()
                     if u != sess.uid and m.get("port")]
            state = self._room_state_payload(room)
        self._room_broadcast(room, state)
        sess.send({"t": MsgType.ROOM_PEERS.value, "room": room, "peers": peers})
        self.audit.log(type="room_join", uid=sess.uid, nick=sess.nick, room=room)

    def _on_room_addr(self, sess: Session, header: dict) -> None:
        """上报本机 UDP 端口：记录 + 回填服务器视角 ip，广播给房内其他人打洞。"""
        room = self._room_key_ok(sess, header.get("room"))
        if room is None:
            return
        try:
            port = int(header.get("port") or 0)
        except (TypeError, ValueError):
            port = 0
        if port <= 0 or port > 65535:
            return
        with self.lock:
            members = self.voice_rooms.get(room)
            if not members or sess.uid not in members:
                return
            members[sess.uid]["port"] = port
            members[sess.uid]["ip"] = sess.peer_ip
        self._room_broadcast(room, {"t": MsgType.ROOM_ADDR.value, "room": room,
                                    "uid": sess.uid, "ip": sess.peer_ip,
                                    "port": port}, exclude=sess.uid)

    def _on_room_leave(self, sess: Session, header: dict) -> None:
        """退房：移除 + 广播名册；空房删除键。"""
        room = self._room_key_ok(sess, header.get("room"))
        if room is None:
            return
        if not self._room_drop(room, sess.uid):
            return
        self.audit.log(type="room_leave", uid=sess.uid, nick=sess.nick, room=room)

    # ---------- 文件传输（服务器协商；直连建立后服务器停用中转） ----------
    def _send_to(self, uid: int, payload: dict, body: bytes = b"") -> None:
        s = self.sessions.get(uid)
        if s is None:
            return
        try:
            s.send(payload, body)
        except Exception:
            pass

    def _on_file_offer(self, sess: Session, header: dict) -> None:
        fid = str(header.get("file_id") or "").strip()
        to = header.get("to")
        size = int(header.get("size") or 0)
        md5 = str(header.get("md5") or "")
        filename = str(header.get("filename") or "").strip()[:255]
        caption = str(header.get("caption") or "")[:2000]   # R32B3 图片说明文字
        if not fid or not filename or size <= 0 or len(md5) != 32:
            self._error(sess, "file", "文件参数不完整")
            return
        if size > self.cfg.file_max_size:
            self._error(sess, "file", f"文件超过大小上限（{size} 字节）")
            return
        with self.lock:
            recv = self.sessions.get(to)
            if recv is None:
                self._error(sess, "offline", "对方不在线")
                return
            if fid in self.xfers:
                self._error(sess, "dup", "传输已存在")
                return
            self.xfers[fid] = TransferMeta(
                file_id=fid, filename=filename, size=size,
                chunk_size=self.cfg.chunk_size, md5=md5,
                sender_uid=sess.uid, receiver_uid=to,
                status=XferStatus.OFFERING.value,
                sender_nick=sess.nick, sender_ip=sess.peer_ip,
            )
        self._send_to(to, {"t": "file_offer", "file_id": fid, "filename": filename,
                           "size": size, "md5": md5, "from_uid": sess.uid,
                           "from_nick": sess.nick, "sender_ip": sess.peer_ip,
                           "caption": caption})
        sess.send({"t": "file_progress", "file_id": fid, "state": "waiting",
                   "text": "等待对方接受…"})
        self.audit.log(type="file_offer", uid=sess.uid, to=to, file_id=fid,
                       name=filename, size=size)

    def _on_file_accept(self, sess: Session, header: dict) -> None:
        fid = str(header.get("file_id") or "")
        with self.lock:
            rec = self.xfers.get(fid)
            if not rec or rec.receiver_uid != sess.uid \
                    or rec.status != XferStatus.OFFERING.value:
                self._error(sess, "file", "传输不存在或已结束")
                return
            rec.status = XferStatus.ACCEPTED.value
            if self.sessions.get(rec.sender_uid) is None:
                self._error(sess, "offline", "发送方已离线")
                return
            recv_ip = sess.peer_ip
            acked = [int(i) for i in (header.get("acked") or [])]
            sender_ip, filename, size, md5 = (rec.sender_ip, rec.filename,
                                              rec.size, rec.md5)
        self._send_to(rec.sender_uid, {"t": "file_accept", "file_id": fid,
                                       "receiver_ip": recv_ip, "acked": acked})
        sess.send({"t": "file_accept", "file_id": fid, "sender_ip": sender_ip,
                   "filename": filename, "size": size, "md5": md5, "acked": acked})
        self.audit.log(type="file_accept", uid=sess.uid, file_id=fid)

    def _on_file_reject(self, sess: Session, header: dict) -> None:
        fid = str(header.get("file_id") or "")
        with self.lock:
            rec = self.xfers.pop(fid, None)
            if not rec or rec.receiver_uid != sess.uid:
                return
            sender_uid = rec.sender_uid
        self._send_to(sender_uid, {"t": "file_reject", "file_id": fid,
                                   "text": "对方拒绝了文件"})
        self.audit.log(type="file_reject", uid=sess.uid, file_id=fid)

    def _on_file_listen(self, sess: Session, header: dict) -> None:
        fid = str(header.get("file_id") or "")
        port = int(header.get("port") or 0)
        with self.lock:
            rec = self.xfers.get(fid)
            if not rec or rec.sender_uid != sess.uid or port <= 0:
                print(f"[DBG][srv] file_listen rejected fid={fid} port={port} "
                      f"sender={sess.uid}", flush=True)
                return
            rec.sender_port = port
            recv_uid, ip = rec.receiver_uid, rec.sender_ip
        print(f"[DBG][srv] file_listen ok fid={fid} port={port} -> uid={recv_uid} "
              f"ip={ip}", flush=True)
        self._send_to(recv_uid, {"t": "file_direct", "file_id": fid,
                                 "ip": ip, "port": port})

    def _on_file_direct_ok(self, sess: Session, header: dict) -> None:
        fid = str(header.get("file_id") or "")
        with self.lock:
            rec = self.xfers.get(fid)
            if rec and rec.sender_uid == sess.uid:
                rec.direct = True

    def _on_file_data(self, sess: Session, header: dict, body: bytes) -> None:
        fid = str(header.get("file_id") or "")
        index = int(header.get("index", -1))
        with self.lock:
            rec = self.xfers.get(fid)
            if not rec or rec.sender_uid != sess.uid or index < 0:
                return
            recv_uid, direct = rec.receiver_uid, rec.direct
            rec.created_at = _now()          # 中转活动时间戳，供闲置超时清理
        if not direct:
            self._send_to(recv_uid, {"t": "file_data", "file_id": fid,
                                     "index": index}, body)

    def _on_file_chunk_ack(self, sess: Session, header: dict) -> None:
        fid = str(header.get("file_id") or "")
        index = int(header.get("index", -1))
        with self.lock:
            rec = self.xfers.get(fid)
            if not rec or rec.receiver_uid != sess.uid or index < 0:
                return
            sender_uid = rec.sender_uid
        self._send_to(sender_uid, {"t": "file_chunk_ack", "file_id": fid,
                                   "index": index})

    def _on_file_verify(self, sess: Session, header: dict) -> None:
        fid = str(header.get("file_id") or "")
        ok = bool(header.get("ok"))
        with self.lock:
            rec = self.xfers.pop(fid, None)
            if not rec or rec.receiver_uid != sess.uid:
                return
            sender_uid = rec.sender_uid
        self._send_to(sender_uid, {"t": "file_verify", "file_id": fid, "ok": ok})
        self.audit.log(type="file_done", file_id=fid, ok=ok)

    def _on_file_cancel(self, sess: Session, header: dict) -> None:
        fid = str(header.get("file_id") or "")
        with self.lock:
            rec = self.xfers.pop(fid, None)
            if not rec:
                return
            other = (rec.receiver_uid if rec.sender_uid == sess.uid
                     else rec.sender_uid)
        self._send_to(other, {"t": "file_cancel", "file_id": fid,
                              "text": "传输已取消"})

    def _drop_xfers_of(self, uid: int) -> list:
        """会话下线时取消其相关传输；返回 [(other_uid, payload), ...] 待锁外通知"""
        notes = []
        with self.lock:
            for fid, rec in list(self.xfers.items()):
                if rec.sender_uid == uid or rec.receiver_uid == uid:
                    del self.xfers[fid]
                    other = (rec.receiver_uid if rec.sender_uid == uid
                             else rec.sender_uid)
                    if other != uid:
                        notes.append((other, {"t": "file_cancel", "file_id": fid,
                                              "text": "对方已离线，传输取消"}))
        return notes

    def _sweep_stale_xfers(self) -> None:
        """清理超时的传输记录（offer 超期 + 中转/直连长期闲置，防僵尸泄漏）。
        活动中的文件每块转发都会刷新 created_at，故不至于误删大文件传输。"""
        now = _now()
        stale = []
        with self.lock:
            for fid, rec in list(self.xfers.items()):
                if now - rec.created_at > self.cfg.file_grace_seconds:
                    del self.xfers[fid]
                    stale.append(rec)
        for rec in stale:
            note = {"t": "file_cancel", "file_id": rec.file_id,
                    "text": "等待接受超时，传输已取消"}
            self._send_to(rec.sender_uid, note)
            self._send_to(rec.receiver_uid, note)

    def _sweep_stale_voice(self) -> None:
        """清理超龄的语音二进制体（仅内存，避免累积，见 VOICE_TTL）；
        R72 视频留言容器同档 TTL 一并淘汰。"""
        with self.lock:
            now = _now()
            if self._voice:
                self._voice = {seq: b for seq, b in self._voice.items()
                               if now - self._voice_ts.get(seq, now) <= self.cfg.voice_ttl}
            if self._vmemo:
                self._vmemo = {seq: b for seq, b in self._vmemo.items()
                               if now - self._vmemo_ts.get(seq, now) <= self.cfg.vmemo_ttl}
        if not self._voice:          # 全部清空时顺带清时间戳表
            self._voice_ts.clear()
        if not self._vmemo:
            self._vmemo_ts.clear()

    # ---------- 群聊 ----------
    def _on_group_create(self, sess: Session, header: dict) -> None:
        name = (header.get("name") or "").strip()[:self.cfg.group_name_max]
        if not name:
            self._error(sess, "name", "群名不能为空")
            return
        with self.lock:
            if any(g["name"] == name for g in self.groups.values()):
                self._error(sess, "dup", "群名已存在")
                return
            gid = self._gid_seq
            self._gid_seq += 1
            self.groups[gid] = {"gid": gid, "name": name, "owner": sess.uid,
                                "members": {sess.uid: sess.nick},
                                "admins": set(), "mutes": {}, "announce": "", "slow": 0,
                                "avatar": "", "about": "",   # R9H：群头像/简介
                                "invite": "",          # R28：邀请码（群主/管理员取）
                                "kind": ("forum" if header.get("forum")
                                         else ("channel" if header.get("broadcast") else "")),
                                "public": 1 if header.get("public") else 0}  # R54：公开群
            _kind = self.groups[gid].get("kind")
        _text = ("论坛频道已创建" if _kind == "forum"
                 else ("频道已创建" if _kind == "channel" else "群已创建"))
        self._send_group_state(gid, text=_text)
        self._broadcast_group_list()
        self.audit.log(type="group_create", uid=sess.uid, nick=sess.nick,
                       gid=gid, name=name)

    def _on_group_join(self, sess: Session, header: dict) -> None:
        gid = header.get("gid")
        g = self.groups.get(gid)
        if not g:
            self._error(sess, "group", "群不存在")
            return
        if sess.uid in g["members"]:
            self._error(sess, "group", "已在群中")
            return
        if not g.get("public") and not sess.is_admin:
            self._error(sess, "private", "该群为私有群，需凭邀请码加入")
            return
        if len(g["members"]) >= self.cfg.group_max_members:
            self._error(sess, "full", f"群已满（{len(g['members'])}/{self.cfg.group_max_members}）")
            return
        with self.lock:
            if self.groups.get(gid) is not g or sess.uid in g["members"]:
                return
            g["members"][sess.uid] = sess.nick
        self._send_group_state(gid, text=f"{sess.nick} 加入群聊")
        self._broadcast_group_list()
        self.audit.log(type="group_join", uid=sess.uid, nick=sess.nick, gid=gid)

    def _on_group_leave(self, sess: Session, header: dict) -> None:
        gid = header.get("gid")
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "group", "不在该群")
            return
        dissolved = False
        with self.lock:
            if self.groups.get(gid) is not g:
                return
            del g["members"][sess.uid]
            if not g["members"]:
                del self.groups[gid]
                dissolved = True
            elif g["owner"] == sess.uid:
                g["owner"] = next(iter(g["members"]))
        if dissolved:
            self._broadcast_system(f"群「{g['name']}」已解散")
            with self.lock:                                  # R72：群解散连同语音房名册
                self.voice_rooms.pop(f"group:{gid}", None)
        else:
            self._send_group_state(gid, text=f"{sess.nick} 已退群")
            self._room_drop(f"group:{gid}", sess.uid)        # R72：退群即退出该群语音房
        self._broadcast_group_list()
        self.audit.log(type="group_leave", uid=sess.uid, nick=sess.nick,
                       gid=gid, dissolved=dissolved)

    # ---------- C8 群管理：踢人 / 禁言 / 设撤管理员 ----------
    def _group_role(self, g: dict, uid: int) -> str:
        """return "owner" | "admin" | "member" | ""（非成员）"""
        if uid not in g["members"]:
            return ""
        if g["owner"] == uid:
            return "owner"
        if uid in g["admins"]:
            return "admin"
        return "member"

    def _on_group_kick(self, sess: Session, header: dict) -> None:
        gid = header.get("gid")
        target = header.get("target")
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "group", "不在该群或群不存在")
            return
        with self.lock:
            if self.groups.get(gid) is not g:
                return
            role = self._group_role(g, sess.uid)
            if role not in ("owner", "admin"):
                self._error(sess, "perm", "无管理权限")
                return
            if target not in g["members"]:
                self._error(sess, "member", "成员不在该群")
                return
            tgt_role = self._group_role(g, target)
            if tgt_role == "owner" or (role == "admin" and tgt_role == "admin"):
                self._error(sess, "perm", "没有权限操作该成员")
                return
            nick = g["members"].pop(target)
            g["admins"].discard(target)
            g["mutes"].pop(target, None)
            dissolved = not g["members"]
        self._broadcast_group_list()
        if dissolved:
            self._broadcast_system(f"群「{g['name']}」已解散")
        else:
            self._send_group_state(gid, text=f"{sess.nick} 将 {nick} 移出群聊")
        self._room_drop(f"group:{gid}", target)              # R72：踢人连同移出该群语音房
        st = self.sessions.get(target)
        if st:
            try:
                st.send({"t": "error", "code": "kicked",
                         "text": f"你已被移出群「{g['name']}」"})
            except Exception:
                pass
        self.audit.log(type="group_kick", uid=sess.uid, gid=gid,
                       target=target, target_nick=nick)

    def _on_group_mute(self, sess: Session, header: dict) -> None:
        gid = header.get("gid")
        target = header.get("target")
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "group", "不在该群或群不存在")
            return
        dur = header.get("duration")
        if dur is None:
            dur = self.cfg.group_mute_default
        try:
            dur = int(dur)
        except (TypeError, ValueError):
            self._error(sess, "duration", "时长不合法")
            return
        if dur < 0:
            self._error(sess, "duration", "时长不能为负")
            return
        with self.lock:
            if self.groups.get(gid) is not g:
                return
            role = self._group_role(g, sess.uid)
            if role not in ("owner", "admin"):
                self._error(sess, "perm", "无管理权限")
                return
            if target not in g["members"]:
                self._error(sess, "member", "成员不在该群")
                return
            if g["owner"] == target:
                self._error(sess, "perm", "不能对群主操作")
                return
            nick = g["members"][target]
            if dur > 0:
                g["mutes"][target] = _now() + dur
                act = "mute"
            else:
                g["mutes"].pop(target, None)
                act = "unmute"
        self._broadcast_group_list()
        verb = f"禁言 {nick}" if act == "mute" else f"解除 {nick} 的禁言"
        if act == "mute" and dur:
            verb += f"（{int(dur // 60)} 分钟）"
        self._send_group_state(gid, text=f"{sess.nick} 已{verb}")
        st = self.sessions.get(target)
        if st and act == "mute":
            try:
                st.send({"t": "error", "code": "muted",
                         "text": f"你在群「{g['name']}」已被禁言"
                                 f"（{int(dur // 60)} 分钟）"})
            except Exception:
                pass
        self.audit.log(type="group_mute", gid=gid, actor=sess.uid,
                       target=target, duration=dur if act == "mute" else 0)

    def _on_group_slow(self, sess: Session, header: dict) -> None:
        """R70D 群慢速模式：设置群内发言最小间隔（秒，0=关闭）。群主/管理员可改。"""
        gid = header.get("gid")
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "group", "不在该群或群不存在")
            return
        try:
            sec = int(header.get("seconds") or 0)
        except (TypeError, ValueError):
            self._error(sess, "seconds", "档位不合法")
            return
        if sec < 0 or sec not in tuple(self.cfg.group_slow_options):
            self._error(sess, "seconds", "不支持的慢速档位")
            return
        with self.lock:
            if self.groups.get(gid) is not g:
                return
            if self._group_role(g, sess.uid) not in ("owner", "admin"):
                self._error(sess, "perm", "无管理权限")
                return
            g["slow"] = sec
            g["slow_last"] = {}                     # 换档清历史节流记录（仅内存）
        self._broadcast_group_list()
        verb = (f"开启群慢速模式（{sec} 秒）" if sec > 0 else "关闭群慢速模式")
        self._send_group_state(gid, text=f"{sess.nick} 已{verb}")
        self.audit.log(type="group_slow", gid=gid, actor=sess.uid, seconds=sec)

    def _on_group_set_admin(self, sess: Session, header: dict) -> None:
        gid = header.get("gid")
        target = header.get("target")
        enable = bool(header.get("enable", True))
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "group", "不在该群或群不存在")
            return
        with self.lock:
            if self.groups.get(gid) is not g:
                return
            if g["owner"] != sess.uid:
                self._error(sess, "perm", "仅群主可设置管理员")
                return
            if target not in g["members"]:
                self._error(sess, "member", "成员不在该群")
                return
            if target == g["owner"]:
                self._error(sess, "perm", "群主无需设为管理员")
                return
            nick = g["members"][target]
            if enable:
                g["admins"].add(target)
            else:
                g["admins"].discard(target)
        self._broadcast_group_list()
        verb = "设为管理员" if enable else "取消管理员资格"
        self._send_group_state(gid, text=f"{sess.nick} 将 {nick} {verb}")
        self.audit.log(type="group_set_admin", gid=gid, actor=sess.uid,
                       target=target, enable=enable)

    def _on_group_announce(self, sess: Session, header: dict) -> None:
        """设/清除群公告（群主/管理员；空文本=清除）。广播 group_state 带 announce。"""
        gid = header.get("gid")
        announce = (header.get("text") or "").strip()
        if len(announce) > self.cfg.chat_text_max:
            announce = announce[:self.cfg.chat_text_max]
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "group", "不在该群或群不存在")
            return
        with self.lock:
            if self.groups.get(gid) is not g:
                return
            role = self._group_role(g, sess.uid)
            if role not in ("owner", "admin"):
                self._error(sess, "perm", "仅群主/管理员可设置公告")
                return
            g["announce"] = announce
        self._persist()                             # 锁外持久化：避免锁序自锁风险
        verb = f"发布公告「{announce[:16]}」" if announce else "已清除群公告"
        self._send_group_state(gid, text=f"{sess.nick} {verb}")
        self.audit.log(type="group_announce", gid=gid, actor=sess.uid,
                       nick=sess.nick)

    def _on_group_ann_mode(self, sess: Session, header: dict) -> None:
        """C9① 群「仅公告说话模式」开关（群主/管理员）。

        开启后普通成员在群内只能发「公告引用互动」（引用置顶公告那条消息），
        不能发普通正文；群主/管理员不受限。广播 group_state 带 announce_mode。
        """
        gid = header.get("gid")
        on = bool(header.get("on"))
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "group", "不在该群或群不存在")
            return
        with self.lock:
            if self.groups.get(gid) is not g:
                return
            if self._group_role(g, sess.uid) not in ("owner", "admin"):
                self._error(sess, "perm", "仅群主/管理员可切换仅公告说话模式")
                return
            g["announce_mode"] = int(bool(on))
        self._persist()                             # 锁外持久化：避免锁序自锁风险
        verb = "开启" if on else "关闭"
        self._send_group_state(gid, text=f"{sess.nick} {verb}了「仅公告说话」模式")
        self.audit.log(type="group_ann_mode", gid=gid, actor=sess.uid,
                       on=on)

    # ---------- R28 群管理补全：邀请码 / 凭码入群 / 群改名 ----------
    def _on_group_invite_get(self, sess: Session, header: dict) -> None:
        """群主/管理员获取群邀请码（无则生成 8 位大写十六进制；只单播回请求者，不广播）。"""
        gid = header.get("gid")
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "group", "不在该群或群不存在")
            return
        with self.lock:
            if self.groups.get(gid) is not g:
                return
            role = self._group_role(g, sess.uid)
            if role not in ("owner", "admin"):
                self._error(sess, "perm", "仅群主/管理员可获取邀请码")
                return
            if not g["invite"]:
                g["invite"] = secrets.token_hex(4).upper()
            code = g["invite"]
        self._persist()                             # 锁外持久化：避免锁序自锁风险
        try:
            sess.send({"t": MsgType.GROUP_INVITE.value, "gid": gid, "code": code})
        except Exception:
            pass
        self.audit.log(type="group_invite_get", gid=gid, actor=sess.uid,
                       nick=sess.nick)

    def _on_group_join_invite(self, sess: Session, header: dict) -> None:
        """凭邀请码入群（任何人；码无效/已在群/满员分别报错）。"""
        # R55-7 邀请码防爆破：同 IP 60s 内失败 ≥5 次 → 直接拒绝
        now = _now()
        fails = [ts for ts in self._invite_fails.get(sess.peer_ip, [])
                 if now - ts < 60]
        if len(fails) >= 5:
            self._error(sess, "flood", "尝试过于频繁，请稍后再试")
            return
        code = (header.get("code") or "").strip().upper()
        if not code:
            fails.append(now)
            self._invite_fails[sess.peer_ip] = fails
            self._error(sess, "invite", "邀请码不能为空")
            return
        g = None
        for cand in self.groups.values():
            if cand.get("invite") == code:
                g = cand
                break
        if g is None:
            fails.append(now)
            self._invite_fails[sess.peer_ip] = fails
            self._error(sess, "invite", "邀请码无效")
            return
        self._invite_fails.pop(sess.peer_ip, None)   # 成功 → 清账
        gid = g["gid"]
        if sess.uid in g["members"]:
            self._error(sess, "group", "已在群中")
            return
        if len(g["members"]) >= self.cfg.group_max_members:
            self._error(sess, "full",
                        f"群已满（{len(g['members'])}/{self.cfg.group_max_members}）")
            return
        with self.lock:
            g = self.groups.get(gid)
            if not g or sess.uid in g["members"]:
                return
            if len(g["members"]) >= self.cfg.group_max_members:
                self._error(sess, "full",
                            f"群已满（{len(g['members'])}/{self.cfg.group_max_members}）")
                return
            g["members"][sess.uid] = sess.nick
        self._send_group_state(gid, text=f"{sess.nick} 凭邀请码加入群聊")
        self._broadcast_group_list()
        self.audit.log(type="group_join_invite", uid=sess.uid, nick=sess.nick,
                       gid=gid)

    def _on_group_rename(self, sess: Session, header: dict) -> None:
        """群主/管理员改群名：非空/长度截断/全局重名（排除自身）。"""
        gid = header.get("gid")
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "group", "不在该群或群不存在")
            return
        name = (header.get("name") or "").strip()[:self.cfg.group_name_max]
        if not name:
            self._error(sess, "name", "群名不能为空")
            return
        with self.lock:
            if self.groups.get(gid) is not g:
                return
            role = self._group_role(g, sess.uid)
            if role not in ("owner", "admin"):
                self._error(sess, "perm", "仅群主/管理员可改群名")
                return
            if any(g2["name"] == name for g2 in self.groups.values()
                   if g2["gid"] != gid):
                self._error(sess, "dup", "群名已存在")
                return
            g["name"] = name
        self._persist()                             # 锁外持久化：避免锁序自锁风险
        self._send_group_state(gid, text=f"{sess.nick} 将群改名为「{name}」")
        self._broadcast_group_list()
        self.audit.log(type="group_rename", gid=gid, actor=sess.uid,
                       nick=sess.nick, name=name)

    def _on_group_about(self, sess: Session, header: dict) -> None:
        """R9H：群主/管理员改群简介（≤cfg.group_about_max 字，空=清除）。"""
        gid = header.get("gid")
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "group", "不在该群或群不存在")
            return
        about = (str(header.get("about") or "").strip()
                 [:self.cfg.group_about_max])
        with self.lock:
            if self.groups.get(gid) is not g:
                return
            role = self._group_role(g, sess.uid)
            if role not in ("owner", "admin"):
                self._error(sess, "perm", "仅群主/管理员可改群简介")
                return
            g["about"] = about
        self._persist()
        self._send_group_state(gid, text=f"{sess.nick} 更新了群简介")
        self._broadcast_group_list()
        self.audit.log(type="group_about", gid=gid, actor=sess.uid,
                       nick=sess.nick, about=about)

    def _on_group_avatar_set(self, sess: Session, header: dict, body: bytes) -> None:
        """R9H：群主/管理员上传群头像（header: gid/ext；body=图片字节 ≤1MB）。"""
        gid = header.get("gid")
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "group", "不在该群或群不存在")
            return
        ext = str(header.get("ext") or "").lower().lstrip(".")
        if ext not in self.cfg.avatar_exts:
            self._error(sess, "avatar", "不支持的图片格式")
            return
        if not body or len(body) > self.cfg.avatar_max_bytes:
            self._error(sess, "avatar", "头像大小超出上限（1MB）")
            return
        with self.lock:
            if self.groups.get(gid) is not g:
                return
            if self._group_role(g, sess.uid) not in ("owner", "admin"):
                self._error(sess, "perm", "仅群主/管理员可换群头像")
                return
        old_ext = g.get("avatar", "")
        try:
            path = self._group_avatar_file(gid, ext)
            tmp = path + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(body)
            os.replace(tmp, path)
        except OSError as exc:
            self._error(sess, "avatar", f"群头像保存失败: {exc}")
            return
        if old_ext and old_ext != ext:
            try:
                os.remove(self._group_avatar_file(gid, old_ext))
            except OSError:
                pass
        with self.lock:
            g["avatar"] = ext
        self._persist()
        self._send_group_state(gid, text=f"{sess.nick} 更换了群头像")
        self._broadcast_group_list()
        # 回执给上传者本人：GROUP_AVATAR_DATA 清零（组内其余成员走 group_state 后按需拉取）
        sess.send({"t": MsgType.GROUP_AVATAR_DATA.value, "gid": gid, "ext": ext}, body)
        self.audit.log(type="group_avatar", gid=gid, actor=sess.uid,
                       nick=sess.nick, ext=ext)

    def _on_group_avatar_del(self, sess: Session, header: dict) -> None:
        """R9H：群主/管理员清空群头像（header: gid → 回 GROUP_AVATAR_DATA ext=""）。"""
        try:
            gid = int(header.get("gid"))
        except (TypeError, ValueError):
            self._error(sess, "avatar", "参数错误")
            return
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "group", "不在该群或群不存在")
            return
        with self.lock:
            if self.groups.get(gid) is not g:
                return
            if self._group_role(g, sess.uid) not in ("owner", "admin"):
                self._error(sess, "perm", "仅群主/管理员可清空群头像")
                return
            old_ext = g.get("avatar", "")
            g["avatar"] = ""
        self._persist()
        if old_ext:
            try:
                os.remove(self._group_avatar_file(gid, old_ext))
            except OSError:
                pass
        self._send_group_state(gid, text=f"{sess.nick} 清空了群头像")
        self._broadcast_group_list()
        # 回执给操作者：GROUP_AVATAR_DATA 清空缓存
        sess.send({"t": MsgType.GROUP_AVATAR_DATA.value, "gid": gid, "ext": ""})
        self.audit.log(type="group_avatar_del", gid=gid, actor=sess.uid,
                       nick=sess.nick)

    def _on_group_avatar_get(self, sess: Session, header: dict) -> None:
        """R9H：拉取群头像（服务器单播 GROUP_AVATAR_DATA；无头像 ext=""）。"""
        try:
            gid = int(header.get("gid"))
        except (TypeError, ValueError):
            self._error(sess, "avatar", "参数错误")
            return
        g = self.groups.get(gid)
        ext = g.get("avatar", "") if g else ""
        if ext:
            try:
                with open(self._group_avatar_file(gid, ext), "rb") as fh:
                    data = fh.read()
                sess.send({"t": MsgType.GROUP_AVATAR_DATA.value, "gid": gid,
                           "ext": ext}, data)
                return
            except OSError:
                pass
        sess.send({"t": MsgType.GROUP_AVATAR_DATA.value, "gid": gid, "ext": ""})

    # ---------- 群文件库（独立于 1v1 文件传输 FileManager） ----------
    def _gf_records(self, gid: int) -> list:
        """群文件记录列表（引用，调用方需持锁或有稳定 gid）。"""
        return self.group_files.setdefault(gid, [])

    def _gf_write_dir(self, gid: int) -> str:
        """群文件落盘目录（惰性建）。"""
        d = os.path.join(self.group_files_dir, str(gid))
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
        return d

    def _gf_send_list(self, sess: Session, gid: int) -> None:
        """把某群文件列表回给会话（body=JSON 数组）。"""
        with self.lock:
            records = [dict(r) for r in self._gf_records(gid)]
        bodies = json.dumps(records, ensure_ascii=False).encode("utf-8")
        sess.send({"t": MsgType.GROUP_FILE_LIST_RES.value, "gid": gid}, bodies)

    def _gf_broadcast(self, gid: int, text: str) -> None:
        """群文件变更 → 组内广播通知（老客户端按普通广播忽略，不崩）。"""
        with self.lock:
            g = self.groups.get(gid)
            if not g:
                return
            targets = list(g["members"])
        payload = {"t": MsgType.GROUP_FILE_NOTIFY.value, "gid": gid, "text": text}
        for u in targets:
            s = self.sessions.get(u)
            if s:
                try:
                    s.send(payload)
                except Exception:
                    pass

    def _on_group_file_list(self, sess: Session, header: dict) -> None:
        """群文件列表（仅群成员可查）。"""
        try:
            gid = int(header.get("gid"))
        except (TypeError, ValueError):
            self._error(sess, "group_file", "参数错误")
            return
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "group_file", "不在该群或群不存在")
            return
        self._gf_send_list(sess, gid)

    def _on_group_file_upload_start(self, sess: Session, header: dict) -> None:
        """上传起始：校验成员+名字+大小，分配 fid，建空档，回 INFO（off=0）。"""
        try:
            gid = int(header.get("gid"))
            size = int(header.get("size") or 0)
        except (TypeError, ValueError):
            self._error(sess, "group_file", "参数错误")
            return
        name = str(header.get("name") or "").strip()
        if not name or len(name) > 120 or "\u0000" in name:
            self._error(sess, "group_file", "文件名非法")
            return
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "group_file", "不在该群或群不存在")
            return
        if size <= 0 or size > self.cfg.group_file_max_bytes:
            self._error(sess, "group_file",
                        f"文件大小超限（0~{self.cfg.group_file_max_bytes // 1024 // 1024}MB）")
            return
        with self.lock:
            if self.groups.get(gid) is not g or sess.uid not in g["members"]:
                return
            self._gf_seq += 1
            fid = str(self._gf_seq)
            rec = {"fid": fid, "name": name, "size": size, "ts": time.time(),
                   "uid": sess.uid, "nick": sess.nick}
            self._gf_records(gid).append(rec)
            self._gf_uploading = getattr(self, "_gf_uploading", {})
            self._gf_uploading[fid] = 0     # off = 已写字节
        self._persist()
        sess.send({"t": MsgType.GROUP_FILE_UPLOAD_INFO.value,
                   "gid": gid, "fid": fid, "off": 0})

    def _on_group_file_upload(self, sess: Session, header: dict, body: bytes) -> None:
        """上传数据块：按 header.off 顺序写盘（off 应等于已写字节）。"""
        try:
            gid = int(header.get("gid"))
            off = int(header.get("off") or 0)
        except (TypeError, ValueError):
            self._error(sess, "group_file", "参数错误")
            return
        fid = str(header.get("fid") or "")
        if not body:
            self._error(sess, "group_file", "空数据块")
            return
        error = None
        complete = False
        with self.lock:
            g = self.groups.get(gid)
            if not g or sess.uid not in g["members"]:
                error = "不在该群或群不存在"
            else:
                rec = next((r for r in self._gf_records(gid)
                            if r["fid"] == fid), None)
                if not rec:
                    error = "文件不存在"
                elif rec.get("uid") != sess.uid:
                    error = "无权写入该文件"
                else:
                    self._gf_uploading = getattr(self, "_gf_uploading", {})
                    cur = self._gf_uploading.get(fid)
                    if cur is None:
                        error = "请先发起上传"
                    elif off != cur:
                        error = "上传块乱序"
                    else:
                        nxt = cur + len(body)
                        if nxt > rec["size"]:
                            error = "数据超长"
                        else:
                            try:
                                path = os.path.join(self._gf_write_dir(gid), fid)
                                # 校验、写入和推进偏移必须处在同一把锁内，
                                # 防止并发会话/伪造者篡改同一上传。
                                actual = (os.path.getsize(path)
                                          if os.path.exists(path) else 0)
                                if actual != cur:
                                    error = "上传文件状态异常"
                                else:
                                    mode = "r+b" if os.path.exists(path) else "wb"
                                    with open(path, mode) as fh:
                                        fh.seek(cur)
                                        fh.write(body)
                                    self._gf_uploading[fid] = nxt
                                    complete = nxt == rec["size"]
                            except OSError:
                                error = "写入失败"
        if error:
            self._error(sess, "group_file", error)
            return
        if complete:
            # 保留 size 偏移直到 DONE，兼容桌面端“最后一块后再发收尾帧”。
            self._persist()

    def _on_group_file_upload_done(self, sess: Session, header: dict) -> None:
        """上传收尾：确认字节数=size，广播组内，回列表。"""
        try:
            gid = int(header.get("gid"))
            off = int(header.get("off") or 0)
        except (TypeError, ValueError):
            self._error(sess, "group_file", "参数错误")
            return
        fid = str(header.get("fid") or "")
        error = None
        abort = False
        with self.lock:
            g = self.groups.get(gid)
            if not g or sess.uid not in g["members"]:
                error = "不在该群或群不存在"
            else:
                rec = next((r for r in self._gf_records(gid)
                            if r["fid"] == fid), None)
                if not rec:
                    error = "文件不存在"
                elif rec.get("uid") != sess.uid:
                    error = "无权完成该文件上传"
                else:
                    self._gf_uploading = getattr(self, "_gf_uploading", {})
                    cur = self._gf_uploading.get(fid)
                    if cur is None:
                        error = "请先发起上传"
                    elif off != cur:
                        error = "上传块乱序"
                    else:
                        path = os.path.join(self._gf_write_dir(gid), fid)
                        try:
                            actual = (os.path.getsize(path)
                                      if os.path.exists(path) else 0)
                        except OSError:
                            actual = 0
                        if actual != rec["size"] or off != rec["size"]:
                            error = f"大小不符（{actual}/{rec['size']}）"
                            abort = True
                        else:
                            self._gf_uploading.pop(fid, None)
        if error:
            self._error(sess, "group_file", error)
            if abort:
                self._gf_abort(gid, fid)
            return
        self._persist()
        self._gf_broadcast(gid, f"{sess.nick} 上传了群文件「{rec['name']}」")
        self._gf_send_list(sess, gid)

    def _gf_abort(self, gid: int, fid: str) -> None:
        """清理不完整上传：删记录与残档。"""
        with self.lock:
            recs = self._gf_records(gid)
            kept = [r for r in recs if r["fid"] != fid]
            if len(kept) != len(recs):
                self.group_files[gid] = kept
            self._gf_uploading = getattr(self, "_gf_uploading", {})
            self._gf_uploading.pop(fid, None)
        try:
            os.remove(os.path.join(self._gf_write_dir(gid), fid))
        except OSError:
            pass
        self._persist()

    def _on_group_file_del(self, sess: Session, header: dict) -> None:
        """删除群文件：本人/群主/管理员可删。"""
        try:
            gid = int(header.get("gid"))
        except (TypeError, ValueError):
            self._error(sess, "group_file", "参数错误")
            return
        fid = str(header.get("fid") or "")
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "group_file", "不在该群或群不存在")
            return
        rec = next((r for r in self._gf_records(gid) if r["fid"] == fid), None)
        if not rec:
            self._error(sess, "group_file", "文件不存在")
            return
        if rec.get("uid") != sess.uid and self._group_role(g, sess.uid) not in ("owner", "admin"):
            self._error(sess, "perm", "仅上传者或群主/管理员可删除")
            return
        name = rec.get("name", "")
        with self.lock:
            recs = self._gf_records(gid)
            self.group_files[gid] = [r for r in recs if r["fid"] != fid]
            self._gf_uploading = getattr(self, "_gf_uploading", {})
            self._gf_uploading.pop(fid, None)
        try:
            os.remove(os.path.join(self._gf_write_dir(gid), fid))
        except OSError:
            pass
        self._persist()
        self._gf_broadcast(gid, f"群文件「{name}」已被删除")
        self._gf_send_list(sess, gid)
        self.audit.log(type="group_file_del", gid=gid, actor=sess.uid,
                       nick=sess.nick, fid=fid)

    def _on_group_file_get(self, sess: Session, header: dict) -> None:
        """下载群文件：仅群成员可下载；按 64KB 块回 GROUP_FILE_DATA。"""
        try:
            gid = int(header.get("gid"))
        except (TypeError, ValueError):
            self._error(sess, "group_file", "参数错误")
            return
        fid = str(header.get("fid") or "")
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "group_file", "不在该群或群不存在")
            return
        rec = next((r for r in self._gf_records(gid) if r["fid"] == fid), None)
        if not rec:
            self._error(sess, "group_file", "文件不存在")
            return
        path = os.path.join(self._gf_write_dir(gid), fid)
        try:
            with open(path, "rb") as fh:
                while True:
                    chunk = fh.read(self.cfg.chunk_size)
                    if not chunk:
                        break
                    last = fh.tell() >= rec["size"]
                    sess.send({"t": MsgType.GROUP_FILE_DATA.value,
                               "gid": gid, "fid": fid,
                               "off": fh.tell() - len(chunk),
                               "more": 0 if last else 1}, chunk)
                    if last:
                        break
        except OSError:
            self._error(sess, "group_file", "读取失败")

    def _send_group_state(self, gid: int, text: str = "") -> None:
        # 锁内快照、锁外发送：避免与成员进出/掉线清理并发改字典
        with self.lock:
            g = self.groups.get(gid)
            if not g:
                return
            payload = {"t": "group_state", "gid": gid, "name": g["name"],
                       "owner": g["owner"], "admins": sorted(g["admins"]),
                       "kind": g.get("kind", ""),       # R72："" 普通群 / "channel" 频道 / "forum" 论坛
                       "mutes": dict(g["mutes"]),
                       "announce": g.get("announce", ""),
                       "announce_mode": g.get("announce_mode", 0),  # C9①：仅公告说话模式
                       "slow": int(g.get("slow") or 0),         # R70D：群慢速档位（秒）
                       "avatar": g.get("avatar", ""),         # R9H：群头像 ext（""=无）
                       "about": g.get("about", ""),           # R9H：群简介
                       "members": [{"uid": u, "nick": n,
                                    "invisible": bool((self.known.get(u) or {})
                                                      .get("invisible"))}   # R57
                                   for u, n in sorted(g["members"].items())],
                       "text": text}
            targets = list(g["members"])
        for u in targets:
            s = self.sessions.get(u)
            if s:
                try:
                    s.send(payload)
                except Exception:
                    pass

    # ---------- R69B6/B7 群待办 / 接龙 / 签到（TASK_*，权威在服务器 tasks） ----------
    _TASK_MODES = ("todo", "relay", "checkin")
    _TASK_MAX = 100                 # 单群任务条数上限（防无界增长）

    def _find_task(self, gid: int, tid) -> dict | None:
        """按 tid 在群任务清单内查找（找不到/非法返回 None）。"""
        try:
            tid = int(tid)
        except (TypeError, ValueError):
            return None
        for r in self.tasks.get(gid) or []:
            if r.get("tid") == tid:
                return r
        return None

    def _send_task_state(self, gid: int, text: str = "",
                         only: int | None = None) -> None:
        """锁内快照任务清单、锁外发送；only=uid 单播，否则群内全员广播。"""
        with self.lock:
            g = self.groups.get(gid)
            if not g:
                return
            recs = self.tasks.get(gid) or []
            payload = {"t": "task_state", "gid": gid, "text": text,
                       "tasks": [{"tid": r["tid"], "text": r["text"],
                                  "mode": r["mode"], "uid": r["uid"],
                                  "ts": r["ts"],
                                  "done": {str(u): v
                                           for u, v in (r.get("done") or {}).items()},
                                  "assignee": r.get("assignee") or 0,
                                  "closed": r.get("closed") or 0}
                                 for r in recs]}
            targets = [only] if only is not None else list(g["members"])
        for u in targets:
            s = self.sessions.get(u)
            if s:
                try:
                    s.send(payload)
                except Exception:
                    pass

    def _on_task_add(self, sess: Session, header: dict) -> None:
        """发起群任务（待办/接龙/签到）；仅群成员；指派对象须在群内。"""
        gid = header.get("gid")
        text = (header.get("text") or "").strip()
        mode = header.get("mode")
        mode = mode if mode in self._TASK_MODES else "todo"
        if not text:
            self._error(sess, "task", "内容不能为空")
            return
        text = text[:self.cfg.chat_text_max]
        try:
            assignee = int(header.get("assignee") or 0)
        except (TypeError, ValueError):
            assignee = 0
        with self.lock:
            g = self.groups.get(gid)
            if not g or sess.uid not in g["members"]:
                self._error(sess, "group", "不在该群或群不存在")
                return
            if assignee and assignee not in g["members"]:
                assignee = 0                  # 指派对象不在群 → 退化为公开任务
            self._task_seq += 1
            rec = {"tid": self._task_seq, "text": text, "mode": mode,
                   "uid": sess.uid, "ts": time.time(), "done": {},
                   "assignee": assignee, "closed": 0}
            recs = self.tasks.setdefault(gid, [])
            recs.append(rec)
            if len(recs) > self._TASK_MAX:     # 先裁已关闭的最旧项，再裁最旧项
                over = len(recs) - self._TASK_MAX
                for r in [r for r in recs if r.get("closed")][:over]:
                    recs.remove(r)
                del recs[:max(0, len(recs) - self._TASK_MAX)]
            tid = rec["tid"]
        self._persist()                        # 锁外持久化
        label = {"todo": "待办", "relay": "接龙", "checkin": "签到"}[mode]
        self._send_task_state(gid, text=f"{sess.nick} 发起{label}「{text[:16]}」")
        self.audit.log(type="group_task_add", gid=gid, actor=sess.uid,
                       tid=tid, mode=mode)

    def _on_task_do(self, sess: Session, header: dict) -> None:
        """参与/打卡（on=0 撤销）；指派任务仅被指派人可操作。"""
        gid = header.get("gid")
        on = bool(header.get("on", True))
        with self.lock:
            g = self.groups.get(gid)
            if not g or sess.uid not in g["members"]:
                self._error(sess, "group", "不在该群或群不存在")
                return
            rec = self._find_task(gid, header.get("tid"))
            if rec is None:
                self._error(sess, "task", "任务不存在或已删除")
                return
            if rec.get("closed"):
                self._error(sess, "task", "该任务已关闭")
                return
            if rec.get("assignee") and rec["assignee"] != sess.uid:
                self._error(sess, "perm", "该任务已指派给他人")
                return
            done = rec.setdefault("done", {})
            if on:
                done.setdefault(sess.uid, time.time())
            else:
                done.pop(sess.uid, None)
            mode = rec.get("mode")
            ttext = str(rec.get("text") or "")[:16]
        self._persist()
        verb = {"relay": "接龙", "checkin": "打卡"}.get(mode, "完成")
        act = verb if on else ("撤销" + verb)
        self._send_task_state(gid, text=f"{sess.nick} {act}「{ttext}」")

    def _on_task_list(self, sess: Session, header: dict) -> None:
        """拉取群任务清单（单播回请求者）。"""
        gid = header.get("gid")
        g = self.groups.get(gid)
        if not g or sess.uid not in g["members"]:
            self._error(sess, "group", "不在该群或群不存在")
            return
        self._send_task_state(gid, only=sess.uid)

    def _on_task_del(self, sess: Session, header: dict) -> None:
        """关闭/删除群任务（发起人 / 群主 / 管理员）。"""
        gid = header.get("gid")
        with self.lock:
            g = self.groups.get(gid)
            if not g or sess.uid not in g["members"]:
                self._error(sess, "group", "不在该群或群不存在")
                return
            rec = self._find_task(gid, header.get("tid"))
            if rec is None:
                self._error(sess, "task", "任务不存在或已删除")
                return
            if rec.get("uid") != sess.uid and \
                    self._group_role(g, sess.uid) not in ("owner", "admin"):
                self._error(sess, "perm", "仅发起人/群主/管理员可关闭任务")
                return
            self.tasks[gid] = [r for r in (self.tasks.get(gid) or []) if r is not rec]
            ttext = str(rec.get("text") or "")[:16]
            tid = rec.get("tid")
        self._persist()
        self._send_task_state(gid, text=f"{sess.nick} 关闭了「{ttext}」")
        self.audit.log(type="group_task_del", gid=gid, actor=sess.uid, tid=tid)

    # ---------- 游戏房间（服务器权威，客户端只渲染快照） ----------
    def _game_list_payload(self) -> dict:
        return {"t": "game_list", "games": [
            {"name": n, "label": m["label"], "min": m["min"], "max": m["max"],
             "desc": m.get("desc", ""), "rules": m.get("rules", "")}
            for n, m in GAME_META.items()],
            "rooms": self.rooms.list_rooms()}

    def _broadcast_game_list(self) -> None:
        self._broadcast(self._game_list_payload())

    def _room_nick(self, uid: int) -> str:
        s = self.sessions.get(uid)
        return s.nick if s else f"玩家{uid}"

    def _send_room_state(self, room, events=None) -> None:
        """给房间成员发当前状态：公开快照 + 各自私密投递 + 事件行。

        锁内快照（含玩家/观战/对局状态），锁外发送——避免与入座/掉线/开局并发。
        """
        with self.rooms.lock:
            payload = {"t": "game_state", "room_id": room.room_id,
                       "room": room.summary(), "state": None,
                       "events": list(events or []), "ts": round(_now(), 3)}
            priv_map = {}
            if room.status == RoomStatus.PLAYING and room.gs is not None:
                payload["state"] = room.gs.snapshot()
                for u in room.members:
                    priv = room.gs.private(u)
                    if priv:
                        priv_map[u] = priv
            targets = list(room.members)
            # R49：uid→昵称映射（桌面端可忽略；网页端无 roster 全量，房间渲染需要）
            payload["nicks"] = {u: self._room_nick(u) for u in targets}
        for u in targets:
            s = self.sessions.get(u)
            if s is None:
                continue
            try:
                s.send(payload)
                if u in priv_map:
                    s.send({"t": "game_private", "room_id": room.room_id,
                            "state": priv_map[u]})
            except Exception:
                pass

    def _finish_game(self, room, ended: dict) -> None:
        """对局结算：置 ENDED 广播，3 秒后自动回大厅（保留玩家与跨轮分数）"""
        with self.rooms.lock:
            room.status = RoomStatus.ENDED
        self.audit.log(type="game_end", room_id=room.room_id,
                       game=room.game_name, detail=ended.get("detail", ""))
        self._send_room_state(room, events=[f"🏁 本局结束：{ended.get('detail', '')}"])

        def _reset():
            with self.rooms.lock:
                if room.status == RoomStatus.ENDED:
                    room.status = RoomStatus.CREATED
                    room.gs = None
            self._send_room_state(room, events=["对局已结束，可再次开始"])

        threading.Timer(3.0, _reset, daemon=True).start()

    def _on_game_create(self, sess: Session, header: dict) -> None:
        game = (header.get("game") or "").strip()
        try:
            room = self.rooms.create(sess.uid, game)
        except GameRuleError as exc:
            self._error(sess, "game", str(exc))
            return
        self.audit.log(type="game_create", uid=sess.uid, nick=sess.nick,
                       room_id=room.room_id, game=game)
        self._broadcast_game_list()
        self._send_room_state(room, events=["房间已创建，等待玩家加入"])

    def _on_game_join(self, sess: Session, header: dict, spectate: bool) -> None:
        room_id = str(header.get("room_id") or "")
        try:
            room = (self.rooms.spectate(sess.uid, room_id) if spectate
                    else self.rooms.join(sess.uid, room_id))
        except GameRuleError as exc:
            self._error(sess, "game", str(exc))
            return
        self.audit.log(type="game_spectate" if spectate else "game_join",
                       uid=sess.uid, nick=sess.nick, room_id=room_id)
        self._broadcast_game_list()
        verb = "观战" if spectate else "加入"
        self._send_room_state(room, events=[f"{sess.nick} {verb}房间"])

    def _on_game_leave(self, sess: Session, header: dict) -> None:
        room_id = str(header.get("room_id") or "")
        self.rooms.leave(sess.uid, room_id)
        self.audit.log(type="game_leave", uid=sess.uid, nick=sess.nick,
                       room_id=room_id)
        self._broadcast_game_list()
        room = self.rooms.room_for(room_id)
        if room:
            self._send_room_state(room, events=[f"{sess.nick} 离开房间"])

    def _on_game_start(self, sess: Session, header: dict) -> None:
        room_id = str(header.get("room_id") or "")
        try:
            room = self.rooms.start(sess.uid, room_id)
        except GameRuleError as exc:
            self._error(sess, "game", str(exc))
            return
        self.audit.log(type="game_start", uid=sess.uid, nick=sess.nick,
                       room_id=room_id, game=room.game_name)
        self._broadcast_game_list()
        self._send_room_state(room, events=["对局开始！"])

    def _on_game_sync(self, sess: Session, header: dict) -> None:
        """R49：重进房间/页面刷新后补拉一次状态（成员或观战者；幂等广播）。"""
        room_id = str(header.get("room_id") or "")
        room = self.rooms.room_for(room_id)
        if not room or sess.uid not in room.members:
            self._error(sess, "game", "你不在该房间")
            return
        self._send_room_state(room)

    def _on_game_action(self, sess: Session, header: dict) -> None:
        room_id = str(header.get("room_id") or "")
        action = header.get("action")
        if not isinstance(action, dict):
            self._error(sess, "game", "动作格式错误")
            return
        try:
            lines = self.rooms.handle_action(sess.uid, room_id, action)
        except GameRuleError as exc:
            self._error(sess, "game", str(exc))
            return
        room = self.rooms.room_for(room_id)
        if not room:
            return
        self.audit.log(type="game_action", uid=sess.uid, nick=sess.nick,
                       room_id=room_id, action=str(action)[:120])
        self._send_room_state(room, events=list(lines))
        if room.status == RoomStatus.PLAYING and room.gs is not None:
            ended = room.gs.ended()
            if ended:
                self._finish_game(room, ended)

    # ---------- R70H 摸鱼排行榜（opt-in，默认关闭） ----------
    def _fish_board_nick(self, uid: int) -> str:
        s = self.sessions.get(uid)
        if s is not None:
            return s.nick
        return (self.known.get(uid) or {}).get("nick") or f"用户{uid}"

    def _fish_board_payload(self, game: str) -> dict:
        """排行榜载荷：按分数降序（同分 uid 升序），仅昵称 + 分数（隐私最小化）。"""
        with self.lock:
            board = dict(self._fish.get(game) or {})
        entries = sorted(board.items(), key=lambda kv: (-kv[1], kv[0]))
        entries = entries[:max(1, int(self.cfg.fish_board_top))]
        return {"t": MsgType.FISH_BOARD.value, "game": game,
                "entries": [{"uid": u, "nick": self._fish_board_nick(u),
                             "score": int(sc)} for u, sc in entries],
                "ts": round(_now(), 3)}

    def _broadcast_fish_board(self, game: str) -> None:
        self._broadcast(self._fish_board_payload(game))

    def _on_fish_score(self, sess: Session, header: dict) -> None:
        """累加本会话摸鱼积分并广播该游戏排行榜；服务器开关关闭则静默忽略。"""
        if not self.cfg.fish_board_enabled:
            return
        game = str(header.get("game") or "").strip()[:64]
        if not game:
            self._error(sess, "fish", "缺少游戏名")
            return
        try:
            score = int(header.get("score") or 0)
        except (TypeError, ValueError):
            return
        if score <= 0:
            return
        score = min(score, int(self.cfg.fish_board_score_max))   # 防刷：单次上报夹取上限
        with self.lock:
            board = self._fish.setdefault(game, {})
            board[sess.uid] = board.get(sess.uid, 0) + score
        self.audit.log(type="fish_score", uid=sess.uid, nick=sess.nick,
                       game=game, score=score)
        self._broadcast_fish_board(game)

    def _on_fish_board_get(self, sess: Session, header: dict) -> None:
        """拉取某游戏当前排行榜（单播；开关关闭时回空榜，不泄露任何数据）。"""
        game = str(header.get("game") or "").strip()[:64]
        if not game:
            self._error(sess, "fish", "缺少游戏名")
            return
        if not self.cfg.fish_board_enabled:
            sess.send({"t": MsgType.FISH_BOARD.value, "game": game,
                       "entries": [], "ts": round(_now(), 3)})
            return
        sess.send(self._fish_board_payload(game))


# ==================== TCP 服务 ====================

def _handle_tcp(hub: Hub, conn: socket.socket, addr) -> None:
    peer_ip = addr[0]
    try:
        # 半开连接防护（握手期）：加密握手本身无超时，恶意客户端只发混淆前缀
        # 后卡住会让 _recv_exact 永久阻塞泄漏线程，握手前先设短超时兜底
        try:
            conn.settimeout(hub.cfg.handshake_timeout)
        except OSError:
            pass
        chan = server_handshake(conn)
    except (HandshakeError, OSError):
        try:
            conn.close()
        except OSError:
            pass
        return
    sess = Session(0, "", "tcp", peer_ip, send=lambda p, b=b"": chan.send_frame(p, b))
    sess.close_conn = lambda: conn.close()
    try:
        # 半开连接防护：客户端既不发数据也不断开时，recv 需有超时，
        # 否则该线程在 recv_frame 永久阻塞泄漏（框架自身用 select/sockfile 兼容超时）
        try:
            conn.settimeout(hub.cfg.tcp_idle_seconds)
        except OSError:
            pass
        while True:
            header, body = chan.recv_frame()
            sess.touch()
            if not hub.dispatch(sess, header, body):
                break
    except (ProtocolError, OSError, ValueError, HandshakeError):
        pass
    finally:
        hub.unregister(sess, "disconnect")
        try:
            conn.close()
        except OSError:
            pass


def _lan_ip() -> str:
    """探测本机局域网出口 IP（UDP connect 仅查路由表不发包）。

    用于启动提示：0.0.0.0 只是监听通配符，浏览器访问不了，
    必须打印 127.0.0.1 / 局域网 IP 才能直接点。完全断网回落 127.0.0.1。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def serve(hub: Hub, port: int | None = None, stop: threading.Event | None = None,
          start_web: bool = True) -> threading.Event:
    """启动 TCP accept 循环（阻塞，Ctrl+C 退出）；默认同时起网页端线程"""
    stop = stop or threading.Event()
    port = port if port is not None else hub.cfg.tcp_port
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(128)
    srv.settimeout(0.5)
    hub.audit.log(type="server_start", port=port)

    web_https = os.environ.get("MOYU_WEB_HTTPS", "1") != "0"   # P0：默认自签 HTTPS
    if start_web:
        import web
        web_thread = threading.Thread(target=web.serve,
                                      args=(hub, None, stop, web_https),
                                      daemon=True)
        web_thread.start()

    sweeper = threading.Thread(target=_sweeper_loop, args=(hub, stop), daemon=True)
    sweeper.start()
    game_ticker = threading.Thread(target=_game_tick_loop, args=(hub, stop), daemon=True)
    game_ticker.start()

    try:
        import discovery
        from config import APP_NAME
        _bcast = discovery.DiscoveryBroadcaster(hub.cfg, name=APP_NAME, stop=stop)
        _bcast.start()
    except Exception:
        pass          # UDP 广播失败不影响 TCP 主服务

    scheme = "https" if web_https else "http"
    tip = "（自签证书，浏览器首次访问点「继续前往」即可）" if web_https else ""
    lan = _lan_ip()
    print(f"[服务器] TCP 监听 0.0.0.0:{port}，网页端 {scheme}://{lan}:{hub.cfg.web_port}/{tip}")
    print(f"        本机访问可用 {scheme}://127.0.0.1:{hub.cfg.web_port}/，"
          f"局域网其他机器用 {scheme}://{lan}:{hub.cfg.web_port}/")
    if not hub._admin_pwd_hash:
        print("[服务器] 管理员登录未启用；请在部署环境设置 MOYU_ADMIN_PASSWORD 后重启。")
    while not stop.is_set():
        try:
            conn, addr = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        try:
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        threading.Thread(target=_handle_tcp, args=(hub, conn, addr), daemon=True).start()
    srv.close()
    hub.audit.log(type="server_stop")
    return stop


def _sweeper_loop(hub: Hub, stop: threading.Event) -> None:
    interval = max(0.2, hub.cfg.sweep_interval)
    while not stop.wait(interval):
        now = _now()
        stale = []
        with hub.lock:
            for s in list(hub._snapshot_sessions()):     # 含同 uid 多端，逐端心跳/闲置判定
                limit = hub._hb_timeout if s.type == "tcp" else hub._web_idle
                if now - s.last_seen > limit:
                    stale.append(s)
        for s in stale:
            if s.type == "tcp":
                try:
                    s.send({"t": "system", "text": "心跳超时，服务器已断开连接"})
                except Exception:
                    pass
            hub.unregister(s, "timeout")
            s.close_conn()
        hub._sweep_stale_xfers()
        hub._sweep_stale_voice()
        hub._sweep_scheds(now)          # R51：服务器权威定时消息到点投递
        hub._sweep_polls(now)           # R70C：投票到点揭示测验答案
        try:
            _bots.sweep_reminders(hub)      # R35：提醒 bot 到点推送
        except Exception:
            pass
        if hub._persist_dirty or hub._persist_pending:
            # R16：仅在确有窗口内积压或后台待写时才兜底落盘；空闲跳过全量重建+写盘
            # （关停时 main() 仍无条件 _persist_flush，保证最后状态必落盘）。
            hub._persist_flush()


def _game_tick_loop(hub: Hub, stop: threading.Event) -> None:
    """游戏房间定时推进：超时/自动下一轮/结算回大厅"""
    interval = max(0.1, hub.cfg.game_auto_tick)
    while not stop.wait(interval):
        now = _now()
        with hub.rooms.lock:
            rooms = list(hub.rooms.rooms.values())
        for room in rooms:
            if room.status == RoomStatus.PLAYING and room.gs is not None:
                try:
                    lines = room.gs.tick(now)
                    if lines:
                        hub._send_room_state(room, events=list(lines))
                    ended = room.gs.ended()
                    if ended:
                        hub._finish_game(room, ended)
                except Exception:
                    pass


def main() -> int:
    enable_crashlog()                        # R48：崩溃堆栈常开写 crash.log
    for _s in (sys.stdout, sys.stderr):      # windowed 打包下二者可能为 None（无控制台）
        try:
            if _s is not None:
                _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    hub = Hub(store_dir=CFG.persistence_dir)   # R16：启用全状态持久化
    stop = threading.Event()

    # 服务器常驻托盘：防误关。pystray 缺失时返回 None，照常起服。
    tray = None
    _tray_stop = threading.Event()
    stop_set = stop.set
    def _server_quit():
        _tray_stop.set()
        stop_set()
    try:
        from widgets.server_tray import start_server_tray, _console_hwnd, _set_console_visible
        scheme = "https" if os.environ.get("MOYU_WEB_HTTPS", "1") != "0" else "http"
        home = f"{scheme}://127.0.0.1:{hub.cfg.web_port}/"
        tray = start_server_tray(_server_quit, home_url=home)
        if tray is not None:
            # 常驻后台：默认隐藏控制台，任务栏不再被服务器独占，杜绝误点关闭。
            # 服务器仍在后台运行；需查看/退出请用右下角托盘（左键图标或右键菜单）。
            print("[服务器] 已常驻右下角托盘（控制台自动隐藏，以免误关）"
                  "；如需管理可从托盘菜单操作。")
            _set_console_visible(False)
    except Exception:
        tray = None

    try:
        serve(hub, stop=stop)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        try:
            _tray_stop.wait(0.3)                       # 给托盘线程一点收尾时间
            if tray is not None:
                tray.stop()
        except Exception:
            pass
        hub._persist_flush()                    # R16：关停前强制落盘
        hub._persist_closing = True
        hub._persist_wake.set()                 # 唤醒后台线程退出（daemon 容错，不卡退出）
        t = hub._persist_worker_thread
        if t is not None and t.is_alive():
            t.join(timeout=1)
        hub.audit.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
