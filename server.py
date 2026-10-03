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
import math
import http.client
import ssl
from collections import defaultdict, deque
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse
import json
import copy
import uuid
import tempfile

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
import server_store as server_store_mod


def _now() -> float:
    return time.time()


PWD_MAX = 64                 # R47：昵称密码最大长度（明文，PBKDF2 后存储）

# 正常注销/同 UID 换端时需要保留的 known 持久资料。Session、token 等运行态
# 不属于该清单；字段即使是空字符串或 False 也要保持其原有值。
_KNOWN_PROFILE_FIELDS = ("pwd", "sign", "avatar", "invisible", "status",
                         "remarks")


@dataclass(frozen=True)
class CommitReceipt:
    """运行态真实 bytes receipt；不包含第二份快照正文，也不落盘。"""

    length: int | None
    sha256: str | None
    capture_request_seq: int | None
    origin: str
    operation_ids: tuple[str, ...] = ()

    @property
    def content_sha256(self) -> str | None:
        return self.sha256

    @property
    def digest(self) -> str | None:
        return self.sha256

    @property
    def ops(self) -> tuple[str, ...]:
        return self.operation_ids

    def __getitem__(self, key):
        if key == "length":
            return self.length
        if key in ("sha256", "content_sha256", "digest"):
            return self.sha256
        if key == "capture_request_seq":
            return self.capture_request_seq
        if key == "origin":
            return self.origin
        if key in ("operation_ids", "ops"):
            return self.operation_ids
        raise KeyError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


class _ResourceError(RuntimeError):
    """有限资源接口的可报告错误；不包含正文、路径或凭据。"""

    def __init__(self, code: str, result: dict | None = None,
                 message: str = "资源操作未完成") -> None:
        super().__init__(message)
        self.code = code
        self.result = result


_RESOURCE_NEW_FIELDS = {
    "resource_manifest_version", "resource_owner_uid",
    "resource_operation_id", "content_length", "content_sha256",
}
_RESOURCE_MANIFEST_FIELDS = {
    "fid", "name", "size", "kind", "ts", *_RESOURCE_NEW_FIELDS,
}
_RESOURCE_KINDS = {"cloud", "web_file"}
_RESOURCE_OP_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")


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
        self._offline_notice_records: dict = {}  # uid -> {text,state=pending|cancelled}
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
        # CC-02C：bot/Agent/提醒来源上下文，仅运行态，不进入聊天正文或 Store。
        self._bot_contexts: dict = {}
        # R37 加密云历史：uid -> {"blob": bytes, "ts": float}（服务器只存密文；
        # 落盘 web_files_dir/cloud/{uid}.bin，重启保留，服务器无法解密）
        self.cloud: dict = {}
        self.cloud_dir = os.path.join(self.cfg.web_files_dir, "cloud")
        os.makedirs(self.cloud_dir, exist_ok=True)
        # CC-02C RESOURCE：运行态资源 registry。它不是 Store 快照，也不保存
        # 正文/路径；latest_permit 与 current_readable_index 必须分开，后续
        # C 可以阻止旧 failed op 重试，但 pending/failed/unknown 不能遮掉
        # 尚未被新已证版本替换的旧可读内容。
        self._resource_lock = threading.RLock()
        self._resource_ops: dict[str, dict] = {}
        self._resource_keys: dict[tuple[str, str], dict] = {}
        self._resource_fid_ops: dict[str, str] = {}
        self._resource_order_seq = 0
        self._resource_max_active = 16
        self._resource_max_terminal = 64
        self._resource_manifest_version = 1
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
        # CC-02A-RETIRE-CORE M1：退役 UID 的最小持久占位；活跃 known 中不保留
        # 退役 UID，nick_to_uid 仍保留以禁止同名/同 UID 重新认领。
        self.retired: dict = {}
        self._retire_ops: dict = {}       # uid -> 运行态 status/op_id（不落盘）
        self._retired_schema_invalid = False
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
        self._resource_stage_dir = os.path.join(self.web_files, ".resource_stage")
        os.makedirs(self._resource_stage_dir, exist_ok=True)
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
        # 内存翻倍、大状态下比较慢。改为只保留一次严格 JSON bytes SHA-256 摘要，
        # 比较退化为字符串比对。指纹仅在 worker / flush 真正 save 成功后推进，
        # 失败则留旧值（避免把失败写当已落盘而漏掉兜底重写）。
        self._persist_fp = None
        self._persist_request_seq = 0
        # 异步落盘：dump+写盘挪到后台 worker，连接线程只做浅拷贝快照（latest-wins）
        self._persist_lock = threading.Lock()
        # actual writer 的唯一顺序锁。槽位只作唤醒，真正写入前必须重新捕获
        # 当前完整状态，避免旧 worker/force capture 覆盖退役后的新快照。
        self._persist_writer_lock = threading.Lock()
        self._persist_pending = False
        self._persist_slot = None
        self._persist_slot_fp = None
        self._persist_wake = threading.Event()
        self._persist_closing = False
        self._persist_worker_thread = None
        # CC-02B：运行态 receipt/未决候选；不写入 state.json，不保存第二份
        # 全量快照。未决候选只保留真实 bytes 标识和有限退役上下文，直到
        # strict read 能够解释或下一次受控提交完成。
        self._persist_receipt = None
        self._persist_unresolved = None
        self._persist_inflight = None
        self._persist_last_result = None
        self._persist_success_evidence = {}
        self._persist_known_shas = set()
        if store_dir:
            from server_store import ServerStore
            self.store = ServerStore(os.path.join(store_dir, "state.json"))
            self.store._bind_hub_writer(self._bound_store_save)
        self._restore(self.store.load() if self.store else {})
        # CLOUD 扫描早于身份恢复是启动顺序既有事实；只有在 _restore 完成
        # 后才把非退役 UID 放入当前可读 index，合法退役 JSON 过滤私有访问。
        self._resource_filter_cloud_after_restore()
        if self.store is not None:
            try:
                loaded = self.store.read_bytes_result()
                if (getattr(loaded, "status", None) == "bytes"
                        and isinstance(getattr(loaded, "payload", None), bytes)
                        and isinstance(getattr(loaded, "sha256", None), str)):
                    strict_state = self._strict_state_from_bytes(loaded.payload)
                    strict_retired = strict_state.get("retired") or {}
                    source_valid = (isinstance(strict_retired, dict)
                                    and not self._retired_schema_invalid)
                    if source_valid and self.retired:
                        for uid, record in self.retired.items():
                            raw = strict_retired.get(str(uid))
                            if raw != record:
                                source_valid = False
                                break
                    if source_valid:
                        self._persist_known_shas.add(loaded.sha256)
                        if self.retired:
                            for uid in self.retired:
                                op = self._retire_ops.get(uid)
                                if isinstance(op, dict):
                                    op["origin"] = "restored_valid_json"
                            self._persist_receipt = CommitReceipt(
                                origin="restored_valid_json", sha256=None,
                                length=None, capture_request_seq=None,
                                operation_ids=tuple(
                                    str(record.get("operation_id"))
                                    for record in self.retired.values()
                                    if isinstance(record, dict)
                                    and isinstance(record.get("operation_id"), str)))
                    elif self.retired:
                        for uid in self.retired:
                            op = self._retire_ops.get(uid)
                            if isinstance(op, dict):
                                op.update({
                                    "status": "unknown",
                                    "origin": None,
                                    "content_sha256": None,
                                    "content_length": None,
                                    "failed_stage": "restore",
                                    "error_code": "strict_source_invalid",
                                    "retryable": False,
                                })
                else:
                    for uid in self.retired:
                        op = self._retire_ops.get(uid)
                        if isinstance(op, dict):
                            op.update({
                                "status": "unknown", "origin": None,
                                "content_sha256": None,
                                "content_length": None,
                                "failed_stage": "restore",
                                "error_code": "strict_source_invalid",
                                "retryable": False,
                            })
            except Exception:
                if self.retired:
                    for uid in self.retired:
                        op = self._retire_ops.get(uid)
                        if isinstance(op, dict):
                            op.update({
                                "status": "unknown", "origin": None,
                                "content_sha256": None,
                                "content_length": None,
                                "failed_stage": "restore",
                                "error_code": "strict_source_invalid",
                                "retryable": False,
                            })
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
        with self.lock:
            with self.bus._lock:
                seq = self.bus._seq
                channels = {k: [copy.deepcopy(m) for m in dq]
                            for k, dq in self.bus._channels.items()}
            def _copy_member_val(v):
                return {kk: (dict(vv) if isinstance(vv, dict) else vv)
                        for kk, vv in v.items()}
            return copy.deepcopy({
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
                        "announce_mode": g.get("announce_mode", 0),
                        "invite": g.get("invite", ""),
                        "kind": g.get("kind", ""),
                        "public": g.get("public", 0),
                        "slow": int(g.get("slow") or 0),
                    } for gid, g in self.groups.items()},
                "reads": {k: dict(v) for k, v in self.reads.items()},
                "pins": {k: dict(v) for k, v in self.pins.items()},
                "burn": {k: dict(v, pend=sorted(v.get("pend") or []))
                         for k, v in self._burn.items()},
                "known": {k: copy.deepcopy(v) for k, v in self.known.items()},
                "retired": {str(k): {"nick": str(v["nick"]),
                                      "retired_at": v["retired_at"],
                                      "operation_id": str(v["operation_id"])}
                            for k, v in self.retired.items()},
                "blocks": {str(k): sorted(v) for k, v in self.blocks.items()},
                "polls": {k: dict(v, votes=dict(v.get("votes") or {}),
                                  options=list(v.get("options") or []))
                          for k, v in self._polls.items()},
                "drafts": {f"{u}|{k}": dict(d)
                            for (u, k), d in self._drafts.items()},
                "scheds": {str(u): {rid: dict(r) for rid, r in mine.items()}
                           for u, mine in self.scheds.items()},
                "custom_stickers": {k: dict(v) for k, v in self.custom_stickers.items()},
                "sticker_pack_meta": {k: dict(v) for k, v in self.pack_meta.items()},
                "group_files": {str(gid): [dict(r) for r in records]
                                for gid, records in self.group_files.items()},
                "gf_seq": self._gf_seq,
                "tasks": {str(gid): [dict(t, done=dict(t.get("done") or {}))
                                     for t in recs]
                          for gid, recs in self.tasks.items()},
                "task_seq": self._task_seq,
                "fish_board": {str(g): {str(u): int(v) for u, v in sc.items()}
                               for g, sc in self._fish.items()},
                "moments": {pid: copy.deepcopy(post)
                            for pid, post in self.moments.items()},
                "moment_covers": {str(u): dict(v) for u, v in self.moment_covers.items()},
                "pid_seq": self._pid_seq,
            })

    @staticmethod
    def _restore_identity_int(value) -> int:
        """把快照中的 UID/GID 身份值严格规范化为正整数。

        JSON object key 只能是字符串，因此兼容 ``"12"``；布尔值、浮点数、
        空白/符号形式及其它类型都拒绝，避免把非法身份带入授权判断。
        """
        if isinstance(value, bool):
            raise ValueError("bool is not an identity integer")
        if isinstance(value, int):
            result = value
        elif (isinstance(value, str) and value
              and all("0" <= ch <= "9" for ch in value)):
            result = int(value)
        else:
            raise ValueError("invalid identity integer")
        if result <= 0:
            raise ValueError("identity integer must be positive")
        return result

    @staticmethod
    def _restore_uid_map(raw: dict, value_kind: str) -> dict:
        """严格恢复 UID 键映射；归一化冲突直接拒绝整个映射。"""
        if not isinstance(raw, dict):
            raise ValueError("identity map must be an object")
        out = {}
        for raw_uid, raw_value in raw.items():
            uid = Hub._restore_identity_int(raw_uid)
            if uid in out:
                raise ValueError("identity key normalization conflict")
            if value_kind == "nick":
                if not isinstance(raw_value, str):
                    raise ValueError("member nick must be a string")
                value = raw_value
            elif value_kind == "mute":
                try:
                    finite = math.isfinite(float(raw_value))
                except (TypeError, OverflowError, ValueError):
                    finite = False
                if (isinstance(raw_value, bool)
                        or not isinstance(raw_value, (int, float))
                        or not finite):
                    raise ValueError("mute deadline must be finite number")
                value = raw_value
            else:
                raise ValueError("unknown identity map value kind")
            out[uid] = value
        return out

    @staticmethod
    def _restore_uid_list(raw) -> set:
        """严格恢复 admins 等 UID 集合；重复归一化键按非法处理。"""
        if not isinstance(raw, list):
            raise ValueError("identity list must be an array")
        out = set()
        for raw_uid in raw:
            uid = Hub._restore_identity_int(raw_uid)
            if uid in out:
                raise ValueError("identity list normalization conflict")
            out.add(uid)
        return out

    @staticmethod
    def _restore_read_seq(value) -> int:
        """恢复 reads 游标；布尔/浮点/负数都不是有效序号。"""
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("invalid read sequence")
        return value

    def _restore_group(self, raw_gid, raw_group: dict) -> tuple[int, dict]:
        """恢复一个群；身份/授权结构任一异常即拒绝整个群。"""
        gid = self._restore_identity_int(raw_gid)
        if not isinstance(raw_group, dict):
            raise ValueError("group must be an object")
        if "gid" in raw_group:
            embedded_gid = self._restore_identity_int(raw_group["gid"])
            if embedded_gid != gid:
                raise ValueError("group gid mismatch")
        if "owner" not in raw_group:
            raise ValueError("group owner missing")
        owner = self._restore_identity_int(raw_group["owner"])
        if "members" not in raw_group:
            raise ValueError("group members missing")
        members = self._restore_uid_map(raw_group["members"], "nick")
        admins = self._restore_uid_list(raw_group.get("admins", []))
        mutes = self._restore_uid_map(raw_group.get("mutes", {}), "mute")
        if owner not in members or not admins.issubset(members):
            raise ValueError("group role is not a member")
        if not set(mutes).issubset(members):
            raise ValueError("group mute target is not a member")
        group = dict(raw_group)
        group["gid"] = gid
        group["owner"] = owner
        group["admins"] = admins
        group["members"] = members
        group["mutes"] = mutes
        group.setdefault("announce", "")
        group.setdefault("announce_mode", 0)   # C9①：仅公告说话模式（旧数据缺省关闭）
        group.setdefault("invite", "")         # R28：邀请码（旧数据缺省）
        group.setdefault("kind", "")           # R26B：频道标记（旧数据缺省普通群）
        group.setdefault("public", 0)           # R54：公开标记（旧数据缺省私有）
        group.setdefault("slow", 0)             # R70D：群慢速档位（旧数据缺省关闭）
        return gid, group

    def _restore(self, state: dict) -> None:
        """从快照恢复内存态；身份映射严格规范化，坏记录 fail closed。"""
        if not isinstance(state, dict):
            return
        self._retired_schema_invalid = False
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
            raw_groups = state.get("groups") or {}
            if not isinstance(raw_groups, dict):
                raise ValueError("groups must be an object")
            # 先记录每个归一化 GID 的唯一来源；"1"/"01" 等冲突会让该
            # GID 的所有候选一起失效，不能由字典遍历顺序决定授权结果。
            grouped = {}
            conflicted = set()
            for raw_gid, raw_group in raw_groups.items():
                try:
                    gid = self._restore_identity_int(raw_gid)
                except (TypeError, ValueError):
                    continue
                if gid in grouped:
                    grouped[gid] = None
                    conflicted.add(gid)
                    continue
                try:
                    parsed_gid, parsed_group = self._restore_group(
                        raw_gid, raw_group)
                    grouped[parsed_gid] = parsed_group
                except (TypeError, ValueError):
                    grouped[gid] = None
            self.groups = {gid: group for gid, group in grouped.items()
                           if gid not in conflicted and group is not None}
        except Exception:
            self.groups = {}
        try:
            raw_reads = state.get("reads") or {}
            if not isinstance(raw_reads, dict):
                raise ValueError("reads must be an object")
            restored_reads = {}
            for key, raw_map in raw_reads.items():
                if not isinstance(key, str) or not isinstance(raw_map, dict):
                    continue
                try:
                    read_map = {}
                    for raw_uid, raw_seq in raw_map.items():
                        uid = self._restore_identity_int(raw_uid)
                        if uid in read_map:
                            raise ValueError("read UID normalization conflict")
                        read_map[uid] = self._restore_read_seq(raw_seq)
                except (TypeError, ValueError):
                    # 一个会话的 UID map 有坏项时整份会话 reads 拒绝，不能
                    # 选择更大的游标或留下部分状态造成误读/误焚。
                    continue
                restored_reads[key] = read_map
            self.reads = restored_reads
        except Exception:
            self.reads = {}
        try:
            self.pins = dict(state.get("pins") or {})
        except Exception:
            pass
        try:
            self._burn = {}
            for k, v in (state.get("burn") or {}).items():
                if not isinstance(v, dict):
                    continue
                rec = dict(v)
                pend = rec.get("pend") or []
                rec["pend"] = set(pend) if isinstance(pend, (list, tuple, set)) else set()
                self._burn[int(k)] = rec
        except Exception:
            pass
        try:
            self.known = {int(k): dict(v) for k, v
                          in (state.get("known") or {}).items()}
        except Exception:
            pass
        # CC-02A-RETIRE-CORE M1：新字段严格恢复。旧快照没有该字段时保持
        # “未知”，不能从 known/nick_to_uid 缺失推断退役；新字段非法则本进程
        # 进入 fail-closed 身份状态，避免宽松恢复后重新授权。
        try:
            raw_retired = state.get("retired", {})
            if raw_retired is None:
                raw_retired = {}
            if not isinstance(raw_retired, dict):
                raise ValueError("retired must be an object")
            restored_retired = {}
            for raw_uid, raw_rec in raw_retired.items():
                uid = self._restore_identity_int(raw_uid)
                if uid in restored_retired or uid in _bots.BOT_BY_UID:
                    raise ValueError("retired UID collision")
                if not isinstance(raw_rec, dict):
                    raise ValueError("retired record must be an object")
                if set(raw_rec) != {"nick", "retired_at", "operation_id"}:
                    raise ValueError("retired record fields are not minimal")
                nick = raw_rec.get("nick")
                retired_at = raw_rec.get("retired_at")
                operation_id = raw_rec.get("operation_id")
                if (not isinstance(nick, str) or not nick.strip()
                        or not isinstance(operation_id, str)
                        or not operation_id.strip()
                        or isinstance(retired_at, bool)
                        or not isinstance(retired_at, (int, float))):
                    raise ValueError("invalid retired record")
                try:
                    if not math.isfinite(float(retired_at)):
                        raise ValueError("retired_at is not finite")
                except (TypeError, ValueError, OverflowError):
                    raise ValueError("invalid retired_at")
                mapped = self.nick_to_uid.get(nick)
                if mapped != uid or uid in self.known:
                    raise ValueError("retired identity conflicts with active state")
                if any(name != nick and mapped_uid == uid
                       for name, mapped_uid in self.nick_to_uid.items()):
                    raise ValueError("retired UID has conflicting nick mapping")
                restored_retired[uid] = {
                    "nick": nick,
                    "retired_at": retired_at,
                    "operation_id": operation_id,
                }
            self.retired = restored_retired
            self._retire_ops = {
                uid: {"status": "confirmed", "operation_id": rec["operation_id"],
                      "target_uid": uid, "target_nick": rec["nick"],
                      "origin": None,
                      "content_sha256": None, "content_length": None,
                      "retryable": False}
                for uid, rec in restored_retired.items()
            }
        except Exception:
            self.retired = {}
            self._retire_ops = {}
            self._retired_schema_invalid = True
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
        """状态内容指纹取严格 JSON bytes SHA-256，替代常驻快照做无变更判定。
        state 由 _snapshot_state() 产出；严格编码失败直接传播。"""
        encoded = server_store_mod.encode_state(state)
        return encoded.sha256

    def _persist_request(self) -> int:
        with self._persist_lock:
            self._persist_request_seq += 1
            return self._persist_request_seq

    def _persist_queue_trigger(self, fp: str | None = None) -> None:
        self._ensure_persist_worker()
        with self._persist_lock:
            self._persist_slot = None
            self._persist_slot_fp = None
            self._persist_pending = True
            self._persist_wake.set()

    @staticmethod
    def _normalize_save_result(result, encoded):
        """把 typed seam 或历史 bool hook 统一成显式 SaveResult。"""
        if isinstance(result, server_store_mod.SaveResult):
            return result
        length = encoded.length
        digest = encoded.sha256
        if type(result) is bool:
            return server_store_mod.SaveResult(
                "committed" if result else "not_committed",
                "compat_save", None if result else "save_failed",
                not result, length, digest)
        return server_store_mod.SaveResult(
            "not_committed", "compat_save", "invalid_save_result",
            False, length, digest)

    def _bound_store_save(self, kind, _state):
        """活动 Hub 的兼容 Store.save/save_bytes 入口。

        外部旧调用只触发同一 writer 的 fresh capture；传入的旧 snapshot 或
        bytes 不会成为第二条写入路径。``save_bytes`` 调用返回本次 typed
        result，旧 ``save`` 调用仍返回 bool。
        """
        if self.store is None:
            if kind == "bytes":
                return server_store_mod.SaveResult(
                    "not_committed", "hub", "store_disabled", False, 0, None)
            return False
        self._persist_request()
        before_result = self._persist_last_result
        with self._persist_writer_lock:
            with self._persist_lock:
                capture_seq = self._persist_request_seq
            try:
                ok = self._commit_current_snapshot(capture_seq, force=True)
            except Exception as exc:
                ok = False
                self._persist_inflight = None
                with self._persist_lock:
                    self._persist_dirty = True
                self._persist_last_result = server_store_mod.SaveResult(
                    "not_committed", "capture", type(exc).__name__,
                    False, 0, None)
        if kind == "bytes":
            result = self._persist_last_result
            if (not isinstance(result, server_store_mod.SaveResult)
                    or result is before_result
                    or (ok and result.effect != "committed")
                    or (not ok and result.effect == "committed")):
                receipt = self._persist_receipt
                if ok:
                    result = server_store_mod.SaveResult(
                        "committed", "hub", None, False,
                        receipt.length if isinstance(receipt, CommitReceipt) else 0,
                        receipt.sha256 if isinstance(receipt, CommitReceipt) else None)
                else:
                    result = server_store_mod.SaveResult(
                        "uncertain" if self._persist_unresolved else "not_committed",
                        "hub", "unknown_pending" if self._persist_unresolved
                        else "commit_not_confirmed", False, 0, None)
                self._persist_last_result = result
            return server_store_mod.SaveResult(
                result.effect, result.stage, result.error_code,
                result.retryable, result.length, result.sha256)
        return bool(ok)

    def _store_commit(self, encoded):
        """通过现有 Store private bytes seam 绑定唯一 writer。"""
        try:
            permit = getattr(self.store, "_hub_write_permit", None)
            save_fn = getattr(self.store, "save")
            native_save = (getattr(save_fn, "__func__", None)
                           is server_store_mod.ServerStore.save)
            save_generation = getattr(self.store, "_save_generation", None)
            if permit is None:
                result = save_fn(encoded)
            else:
                with permit():
                    result = save_fn(encoded)
        except Exception:
            return server_store_mod.SaveResult(
                "uncertain", "compat_save", "save_exception",
                False, encoded.length, encoded.sha256)
        if (native_save
                and save_generation is not None
                and getattr(self.store, "_save_generation", None) != save_generation
                and isinstance(getattr(self.store, "_last_save_result", None),
                               server_store_mod.SaveResult)):
            return self.store._last_save_result
        return self._normalize_save_result(result, encoded)

    @staticmethod
    def _uid_key_present(mapping, uid: int) -> bool:
        if not isinstance(mapping, dict):
            return False
        return any(key == uid or key == str(uid) for key in mapping)

    @staticmethod
    def _uid_value(value, uid: int) -> bool:
        return value == uid or value == str(uid)

    def _retire_candidates_for_state(self, state: dict) -> list[dict]:
        """只从 captured state 取得 operation 来源，live state 仅用于选 op。"""
        with self.lock:
            pending = [
                (int(uid), dict(op))
                for uid, op in self._retire_ops.items()
                if isinstance(op, dict)
                and op.get("status") in ("pending", "failed")
            ]
        records = state.get("retired") if isinstance(state, dict) else None
        records = records if isinstance(records, dict) else {}
        out = []
        for uid, op in pending:
            record = records.get(str(uid), records.get(uid))
            out.append({
                "uid": uid,
                "operation_id": op.get("operation_id"),
                "target_nick": op.get("target_nick"),
                "record": record,
            })
        return out

    def _capture_persist_state(self) -> tuple[dict, list[dict]]:
        """Capture state and its op metadata under one Hub→bus boundary."""
        with self.lock:
            state = self._snapshot_state()
            candidates = self._retire_candidates_for_state(state)
            return state, candidates

    def _retirement_retry_waiting(self) -> bool:
        """unknown 退役状态在对账前暂停全部 writer。"""
        with self.lock:
            for uid, op in self._retire_ops.items():
                if not isinstance(op, dict) or op.get("status") != "unknown":
                    continue
                record = self.retired.get(uid)
                if (isinstance(record, dict)
                        and record.get("operation_id") == op.get("operation_id")):
                    return True
        return False

    def _failed_retry_preflight(self, candidates: list[dict]) -> bool:
        """失败 op 仅在权威盘面可证为本进程已知合法前序时重试。"""
        failed = []
        with self.lock:
            for candidate in candidates:
                op = self._retire_ops.get(candidate.get("uid"))
                if isinstance(op, dict) and op.get("status") == "failed":
                    failed.append(candidate)
        if not failed:
            return True
        try:
            read = self.store.read_bytes_result()
            if getattr(read, "status", None) != "bytes":
                return False
            payload = getattr(read, "payload", None)
            actual_sha = getattr(read, "sha256", None)
            if not isinstance(payload, bytes) or actual_sha not in self._persist_known_shas:
                return False
            state = self._strict_state_from_bytes(payload)
            if not self._verify_reconcile_state(state):
                return False
        except (OSError, UnicodeError, TypeError, ValueError, OverflowError):
            return False
        return all(self._predecessor_status(state, candidate) == "predecessor"
                   for candidate in failed)

    def _validate_retirement_candidate(self, state: dict,
                                       candidate: dict) -> tuple[bool, str | None]:
        """验证 captured state 的有限 CORE 清理，不读取 live 状态。"""
        uid = candidate.get("uid")
        operation_id = candidate.get("operation_id")
        nick = candidate.get("target_nick")
        records = state.get("retired") if isinstance(state, dict) else None
        record = records.get(str(uid), records.get(uid)) if isinstance(records, dict) else None
        if (not isinstance(record, dict)
                or set(record) != {"nick", "retired_at", "operation_id"}
                or record.get("nick") != nick
                or record.get("operation_id") != operation_id):
            return False, "retirement_record"
        if isinstance(records, dict):
            for raw_uid, other in records.items():
                if (not isinstance(other, dict)
                        or (other.get("nick") == nick
                            and not self._uid_value(raw_uid, uid))):
                    return False, "retirement_conflict"
        nick_map = state.get("nick_to_uid")
        if not isinstance(nick_map, dict) or not self._uid_value(nick_map.get(nick), uid):
            return False, "nick_mapping"
        for name, mapped in nick_map.items():
            if name != nick and self._uid_value(mapped, uid):
                return False, "nick_mapping_conflict"

        known = state.get("known") or {}
        if self._uid_key_present(known, uid):
            return False, "known_residual"
        drafts = state.get("drafts") or {}
        if isinstance(drafts, dict) and any(
                isinstance(key, str) and key.startswith(f"{uid}|")
                for key in drafts):
            return False, "draft_residual"
        scheds = state.get("scheds") or {}
        if self._uid_key_present(scheds, uid):
            return False, "sched_residual"
        blocks = state.get("blocks") or {}
        if self._uid_key_present(blocks, uid):
            return False, "block_residual"
        reads = state.get("reads") or {}
        if isinstance(reads, dict):
            for readers in reads.values():
                if self._uid_key_present(readers, uid):
                    return False, "read_residual"

        groups = state.get("groups") or {}
        if isinstance(groups, dict):
            for group in groups.values():
                if not isinstance(group, dict):
                    return False, "group_invalid"
                if self._uid_value(group.get("owner"), uid):
                    return False, "group_owner_residual"
                admins = group.get("admins") or []
                if uid in admins or str(uid) in admins:
                    return False, "group_admin_residual"
                if self._uid_key_present(group.get("members"), uid):
                    return False, "group_member_residual"
                if self._uid_key_present(group.get("mutes"), uid):
                    return False, "group_mute_residual"

        bus = state.get("bus") or {}
        channels = bus.get("channels") if isinstance(bus, dict) else {}
        if isinstance(channels, dict):
            for messages in channels.values():
                for message in messages or ():
                    if isinstance(message, dict) and self._uid_value(message.get("uid"), uid):
                        return False, "bus_message_residual"
        burn = state.get("burn") or {}
        if isinstance(burn, dict):
            for burn_record in burn.values():
                if isinstance(burn_record, dict) and self._uid_value(burn_record.get("uid"), uid):
                    return False, "burn_residual"
        return True, None

    @staticmethod
    def _strict_state_from_bytes(payload: bytes) -> dict:
        """严格解析权威 bytes；重复键和 NaN 常量均拒绝。"""
        def reject_constant(value):
            raise ValueError(f"invalid JSON constant: {value}")

        def reject_duplicate(pairs):
            out = {}
            for key, value in pairs:
                if key in out:
                    raise ValueError("duplicate JSON object key")
                out[key] = value
            return out

        text = payload.decode("utf-8")
        value = json.loads(text, parse_constant=reject_constant,
                           object_pairs_hook=reject_duplicate)
        if not isinstance(value, dict):
            raise ValueError("state root must be object")
        # Parsed JSON escapes can contain a Python surrogate even though the
        # raw file bytes were valid UTF-8.  Reject that value without
        # re-encoding it or replacing the actual file digest.
        server_store_mod._validate_json_value(value, set())
        return value

    def _verify_reconcile_state(self, state: dict) -> bool:
        """校验对账所需的现有身份/核心容器结构，宁可保守 unknown。"""
        dict_fields = (
            "nick_to_uid", "known", "retired", "groups", "reads", "pins",
            "burn", "blocks", "polls", "drafts", "scheds",
            "custom_stickers", "sticker_pack_meta", "group_files", "tasks",
            "fish_board", "moments", "moment_covers",
        )
        for field in dict_fields:
            if field in state and not isinstance(state[field], dict):
                return False
        nick_map = state.get("nick_to_uid") or {}
        for name, uid in nick_map.items():
            if not isinstance(name, str):
                return False
            try:
                self._restore_identity_int(uid)
            except (TypeError, ValueError):
                return False
        known = state.get("known") or {}
        for raw_uid, value in known.items():
            try:
                self._restore_identity_int(raw_uid)
            except (TypeError, ValueError):
                return False
            if not isinstance(value, dict):
                return False
        retired = state.get("retired") or {}
        for raw_uid, record in retired.items():
            try:
                retired_uid = self._restore_identity_int(raw_uid)
            except (TypeError, ValueError):
                return False
            if retired_uid in _bots.BOT_BY_UID:
                return False
            if (not isinstance(record, dict)
                    or set(record) != {"nick", "retired_at", "operation_id"}
                    or not isinstance(record.get("nick"), str)
                    or not record.get("nick", "").strip()
                    or not isinstance(record.get("operation_id"), str)
                    or not record.get("operation_id", "").strip()
                    or isinstance(record.get("retired_at"), bool)
                    or not isinstance(record.get("retired_at"), (int, float))):
                return False
            try:
                if not math.isfinite(float(record.get("retired_at"))):
                    return False
            except (TypeError, ValueError, OverflowError):
                return False
            if (not self._uid_value(nick_map.get(record.get("nick")), retired_uid)
                    or self._uid_key_present(known, retired_uid)):
                return False
        groups = state.get("groups") or {}
        for raw_gid, group in groups.items():
            try:
                self._restore_group(raw_gid, group)
            except (TypeError, ValueError, KeyError):
                return False
        reads = state.get("reads") or {}
        for readers in reads.values():
            if not isinstance(readers, dict):
                return False
            for raw_uid, seq in readers.items():
                try:
                    self._restore_identity_int(raw_uid)
                    self._restore_read_seq(seq)
                except (TypeError, ValueError):
                    return False
        blocks = state.get("blocks") or {}
        for raw_uid, targets in blocks.items():
            try:
                self._restore_identity_int(raw_uid)
            except (TypeError, ValueError):
                return False
            if not isinstance(targets, list):
                return False
            try:
                for target in targets:
                    self._restore_identity_int(target)
            except (TypeError, ValueError):
                return False
        bus = state.get("bus") or {}
        if not isinstance(bus, dict):
            return False
        channels = bus.get("channels", {})
        if not isinstance(channels, dict):
            return False
        if any(not isinstance(messages, list) for messages in channels.values()):
            return False
        if any(not isinstance(message, dict)
               for messages in channels.values() for message in messages):
            return False
        burn = state.get("burn") or {}
        if any(not isinstance(record, dict) for record in burn.values()):
            return False
        return True

    def _predecessor_status(self, state: dict, candidate: dict) -> str:
        """区分可解释的无 op 前序与同 op/异 op 冲突。"""
        uid = candidate.get("uid")
        nick = candidate.get("target_nick")
        op_id = candidate.get("operation_id")
        records = state.get("retired") or {}
        record = records.get(str(uid), records.get(uid)) if isinstance(records, dict) else None
        if isinstance(record, dict):
            if (record.get("operation_id") == op_id
                    and record.get("nick") == nick):
                return "same_op"
            return "conflict"
        if isinstance(records, dict):
            for raw_uid, value in records.items():
                if isinstance(value, dict) and value.get("nick") == nick:
                    return "conflict"
                if self._uid_value(raw_uid, uid):
                    return "conflict"
        nick_map = state.get("nick_to_uid") or {}
        if not self._uid_value(nick_map.get(nick), uid):
            return "conflict"
        for name, mapped in nick_map.items():
            if name != nick and self._uid_value(mapped, uid):
                return "conflict"
        return "predecessor"

    def _update_retirement_result(self, candidate: dict, *, status: str,
                                  origin: str | None = None,
                                  sha256: str | None = None,
                                  length: int | None = None,
                                  failed_stage: str | None = None,
                                  error_code: str | None = None,
                                  retryable: bool = False) -> None:
        uid = candidate.get("uid")
        operation_id = candidate.get("operation_id")
        with self.lock:
            op = self._retire_ops.get(uid)
            if not isinstance(op, dict) or op.get("operation_id") != operation_id:
                return
            if op.get("status") == "confirmed" and status != "confirmed":
                return
            op.update({
                "status": status,
                "target_uid": uid,
                "target_nick": candidate.get("target_nick"),
                "origin": origin if status == "confirmed" else None,
                "content_sha256": sha256 if status == "confirmed" else None,
                "content_length": length if status == "confirmed" else None,
                "failed_stage": failed_stage,
                "error_code": error_code,
                "retryable": bool(retryable) if status == "failed" else False,
            })

    def _ack_commit(self, state: dict, encoded, result,
                    capture_seq: int,
                    captured_candidates: list[dict] | None = None) -> bool:
        """统一处理 writer/flush/worker receipt，confirmed 单调。"""
        candidates = (list(captured_candidates)
                      if captured_candidates is not None
                      else self._retire_candidates_for_state(state))
        if result.effect == "committed":
            for candidate in candidates:
                valid, reason = self._validate_retirement_candidate(state, candidate)
                if not valid:
                    self._update_retirement_result(
                        candidate, status="failed", failed_stage="verify",
                        error_code=reason or "retirement_verify_failed",
                        retryable=False)
                else:
                    self._update_retirement_result(
                        candidate, status="confirmed", origin="written",
                        sha256=encoded.sha256, length=encoded.length)
                    self._persist_success_evidence.setdefault(
                        candidate["operation_id"], set()).add(encoded.sha256)
        elif result.effect == "uncertain":
            for candidate in candidates:
                self._update_retirement_result(
                    candidate, status="unknown", failed_stage=result.stage,
                    error_code=result.error_code, retryable=False)
            self._persist_unresolved = {
                "sha256": encoded.sha256,
                "length": encoded.length,
                "capture_request_seq": capture_seq,
                "candidates": [dict(candidate) for candidate in candidates],
            }
        else:
            for candidate in candidates:
                self._update_retirement_result(
                    candidate, status="failed", failed_stage=result.stage,
                    error_code=result.error_code,
                    retryable=(result.retryable is True))
        self._persist_last_result = result
        return result.effect == "committed"

    def _reconcile_persist_unknown(self) -> str:
        """对账未决候选；返回 confirmed/failed/blocked/none。"""
        unresolved = self._persist_unresolved
        if not unresolved:
            return "none"
        try:
            read = self.store.read_bytes_result()
        except Exception:
            return "blocked"
        if getattr(read, "status", None) != "bytes":
            return "blocked"
        payload = getattr(read, "payload", None)
        if not isinstance(payload, bytes):
            return "blocked"
        try:
            state = self._strict_state_from_bytes(payload)
        except (UnicodeError, TypeError, ValueError, OverflowError, RecursionError):
            return "blocked"
        if not self._verify_reconcile_state(state):
            return "blocked"
        candidates = unresolved.get("candidates") or []
        actual_sha = getattr(read, "sha256", None)
        if not candidates:
            if actual_sha == unresolved.get("sha256"):
                length = getattr(read, "length", len(payload))
                self._persist_receipt = CommitReceipt(
                    origin="reconciled_current_json", sha256=actual_sha,
                    length=length,
                    capture_request_seq=unresolved.get("capture_request_seq"))
                with self._persist_lock:
                    self._persist_fp = actual_sha
                self._persist_known_shas.add(actual_sha)
                self._persist_unresolved = None
                self._persist_last_result = server_store_mod.SaveResult(
                    "committed", "reconcile", None, False, length, actual_sha)
                return "confirmed"
            if actual_sha in self._persist_known_shas:
                self._persist_unresolved = None
                self._persist_last_result = server_store_mod.SaveResult(
                    "not_committed", "reconcile", "known_predecessor",
                    True, getattr(read, "length", len(payload)), actual_sha)
                return "failed"
            return "blocked"
        validity = [
            (candidate, self._validate_retirement_candidate(state, candidate))
            for candidate in candidates
        ]
        length = getattr(read, "length", len(payload))
        operation_ids = tuple(
            candidate.get("operation_id") for candidate, _ in validity
            if isinstance(candidate.get("operation_id"), str))
        all_valid = all(valid for _candidate, (valid, _reason) in validity)
        current_candidate = (all_valid
                             and actual_sha == unresolved.get("sha256"))
        known_successor = (all_valid and all(
            actual_sha in self._persist_success_evidence.get(
                candidate.get("operation_id"), set())
            for candidate, _ in validity))
        if current_candidate or known_successor:
            for candidate, _ in validity:
                self._update_retirement_result(
                    candidate, status="confirmed", origin="reconciled_current_json",
                    sha256=actual_sha, length=length)
            self._persist_receipt = CommitReceipt(
                origin="reconciled_current_json", sha256=actual_sha,
                length=length,
                capture_request_seq=unresolved.get("capture_request_seq"),
                operation_ids=operation_ids)
            with self._persist_lock:
                self._persist_fp = actual_sha
            self._persist_known_shas.add(actual_sha)
            self._persist_unresolved = None
            self._persist_last_result = server_store_mod.SaveResult(
                "committed", "reconcile", None, False, length, actual_sha)
            return "confirmed"
        known_predecessor = (actual_sha in self._persist_known_shas and all(
            self._predecessor_status(state, candidate) == "predecessor"
            for candidate, _ in validity))
        if known_predecessor:
            for candidate, _ in validity:
                self._update_retirement_result(
                    candidate, status="failed", failed_stage="reconcile",
                    error_code="known_predecessor", retryable=True)
            self._persist_unresolved = None
            self._persist_last_result = server_store_mod.SaveResult(
                "not_committed", "reconcile", "known_predecessor",
                True, length, actual_sha)
            return "failed"
        return "blocked"

    def _commit_current_snapshot(self, capture_seq: int,
                                 *, force: bool = False) -> bool:
        """writer lock 内 fresh capture → verify/encode → single Store seam。"""
        unresolved = self._persist_unresolved
        unresolved_has_retirement = bool(
            unresolved and unresolved.get("candidates"))
        reconciled = self._reconcile_persist_unknown()
        if reconciled == "blocked":
            with self._persist_lock:
                self._persist_dirty = True
            return False
        if unresolved_has_retirement and reconciled in ("failed", "confirmed"):
            # A known predecessor makes the old retirement attempt retryable,
            # but must not let this same ordinary/flush writer publish the
            # still-live tombstone.  Only the explicit same-op retry may set
            # it pending again; a confirmed current JSON is already durable.
            with self._persist_lock:
                changed = self._persist_request_seq != capture_seq
                self._persist_dirty = changed or reconciled == "failed"
            return reconciled == "confirmed"
        if self._retirement_retry_waiting():
            with self._persist_lock:
                self._persist_dirty = True
            return False
        state, candidates = self._capture_persist_state()
        if not self._failed_retry_preflight(candidates):
            with self._persist_lock:
                self._persist_dirty = True
            return False
        for candidate in candidates:
            valid, reason = self._validate_retirement_candidate(state, candidate)
            if not valid:
                self._persist_last_result = server_store_mod.SaveResult(
                    "not_committed", "verify", reason or "retirement_verify_failed",
                    False, 0, None)
                self._update_retirement_result(
                    candidate, status="failed", failed_stage="verify",
                    error_code=reason or "retirement_verify_failed",
                    retryable=False)
                with self._persist_lock:
                    self._persist_dirty = True
                return False
        try:
            encoded = server_store_mod.encode_state(state)
        except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError) as exc:
            self._persist_last_result = server_store_mod.SaveResult(
                "not_committed", "encode", type(exc).__name__,
                False, 0, None)
            for candidate in candidates:
                self._update_retirement_result(
                    candidate, status="failed", failed_stage="encode",
                    error_code=type(exc).__name__, retryable=False)
            with self._persist_lock:
                self._persist_dirty = True
            return False
        with self._persist_lock:
            known_fp = self._persist_fp
        if (not force and known_fp is not None
                and encoded.sha256 == known_fp):
            with self._persist_lock:
                changed = self._persist_request_seq != capture_seq
                self._persist_dirty = changed
            if changed and not self._persist_closing:
                self._persist_queue_trigger()
            return True
        self._persist_inflight = {
            "sha256": encoded.sha256,
            "length": encoded.length,
            "capture_request_seq": capture_seq,
            "candidates": [dict(candidate) for candidate in candidates],
        }
        result = self._store_commit(encoded)
        ack_candidates = list(candidates)
        try:
            committed = self._ack_commit(
                state, encoded, result, capture_seq, ack_candidates)
        except Exception:
            # The bytes may already have been replaced even when receipt/ack
            # construction failed.  Preserve the captured candidates as
            # unknown so the next query can reconcile the authority.
            for candidate in ack_candidates:
                self._update_retirement_result(
                    candidate, status="unknown", failed_stage="ack",
                    error_code="ack_exception", retryable=False)
            self._persist_unresolved = {
                "sha256": encoded.sha256,
                "length": encoded.length,
                "capture_request_seq": capture_seq,
                "candidates": [dict(candidate) for candidate in ack_candidates],
            }
            self._persist_inflight = None
            result = server_store_mod.SaveResult(
                "uncertain", "ack", "ack_exception", False,
                encoded.length, encoded.sha256)
            self._persist_last_result = result
            with self._persist_lock:
                self._persist_dirty = True
            return False
        if committed:
            self._persist_inflight = None
            with self._persist_lock:
                self._persist_fp = encoded.sha256
                changed = self._persist_request_seq != capture_seq
                self._persist_dirty = changed
            self._persist_receipt = CommitReceipt(
                origin="written", sha256=encoded.sha256,
                length=encoded.length, capture_request_seq=capture_seq,
                operation_ids=tuple(candidate.get("operation_id")
                                    for candidate in candidates
                                    if isinstance(candidate.get("operation_id"), str)))
            self._persist_known_shas.add(encoded.sha256)
            self._persist_unresolved = None
            if changed and not self._persist_closing:
                self._persist_queue_trigger()
            return True
        self._persist_inflight = None
        with self._persist_lock:
            self._persist_dirty = True
        return False

    def _persist(self, force: bool = False) -> bool | None:
        """节流写盘：窗口内合并突发变更，dump+写盘交给后台 worker（latest-wins）。
        无 store 时为空操作；force=True 恒写（关键变更同步落盘，返回即已持久）。

        R65：以严格 bytes 内容指纹判定无变更——不再常驻第二份全量快照、
        不做递归 dict 深比较。指纹仅在真正 save 成功后推进（失败留旧值，供 flush 兜底）。"""
        if self.store is None:
            return None
        request_seq = self._persist_request()
        if force:
            return self._persist_sync(_request_seq=request_seq)
        now = time.time()
        if now - self._persist_last < self._persist_interval:
            with self._persist_lock:
                self._persist_dirty = True
            return None
        self._persist_last = time.time()
        with self._persist_lock:
            self._persist_dirty = True
        self._persist_queue_trigger()
        return None

    def _persist_sync(self, _old_state=None, _old_fp=None,
                      _request_seq: int | None = None) -> bool:
        """同步 actual writer（force/关停兜底）。

        旧参数仅保留兼容调用形状，永不直接写入；拿到唯一 writer lock 后
        重新捕获当前状态，再进行 dump/flush/fsync/replace。调用方必须在
        Hub 锁外进入本方法。
        """
        self._persist_last = time.time()
        if _request_seq is None:
            _request_seq = self._persist_request()
        with self._persist_lock:
            self._persist_slot = None
            self._persist_slot_fp = None
            self._persist_pending = False
        with self._persist_writer_lock:
            with self._persist_lock:
                capture_seq = self._persist_request_seq
            try:
                return self._commit_current_snapshot(capture_seq, force=True)
            except Exception as exc:
                self._persist_inflight = None
                with self._persist_lock:
                    self._persist_dirty = True
                self._persist_last_result = server_store_mod.SaveResult(
                    "not_committed", "capture", type(exc).__name__,
                    False, 0, None)
                return False

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
                self._persist_pending = False
                self._persist_slot = None
            with self._persist_writer_lock:
                with self._persist_lock:
                    capture_seq = self._persist_request_seq
                try:
                    self._commit_current_snapshot(capture_seq)
                except Exception as exc:
                    self._persist_inflight = None
                    with self._persist_lock:
                        self._persist_dirty = True
                    self._persist_last_result = server_store_mod.SaveResult(
                        "not_committed", "capture", type(exc).__name__,
                        False, 0, None)

    def _persist_flush(self) -> None:
        """强制立即写盘（关停兜底 / sweeper 兜底）：合并为一次同步构建+落盘，
        不再先异步 force 一次、又 _snapshot_state 一次（修复重复写）。
        无条件写最后状态：不依赖 dirty/compare，关停必然兜底不丢；
        仅当无 store 时空操作。"""
        if self.store is None:
            return
        return self._persist_sync()

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

    # ---------- CC-02C RESOURCE：运行态结果/attempt/文件资格 ----------
    @staticmethod
    def _resource_public_result(ctx: dict) -> dict:
        """只导出有限资源结果字段，不携带正文、路径或凭据。"""
        keys = ("resource_operation_id", "resource_owner_uid", "kind",
                "resource_key", "status", "io_effect", "visibility",
                "stage", "error_code", "length", "sha256", "origin",
                "retryable")
        return {k: copy.deepcopy(ctx.get(k)) for k in keys}

    def _resource_visibility_locked(self, ctx: dict) -> str:
        if (ctx.get("owner_uid") in self.retired
                and ctx.get("kind") == "cloud"):
            return "withdrawn"
        key = (ctx.get("kind"), str(ctx.get("resource_key")))
        rec = self._resource_keys.get(key) or {}
        current = rec.get("current_readable_index")
        if ctx.get("status") == "confirmed":
            if current is not None and current.get("operation_id") == ctx.get(
                    "resource_operation_id"):
                return "available"
            if current is not None and current.get("operation_id") is not None:
                return "superseded"
            if ctx.get("visibility") == "withdrawn":
                return "withdrawn"
        if ctx.get("status") == "pending":
            return "pending"
        if ctx.get("status") == "unknown":
            # A pending/unknown replacement does not erase the last confirmed
            # readable index.  Its own result remains unresolved.
            return "pending"
        if rec.get("latest_permit", {}).get("operation_id") not in (
                None, ctx.get("resource_operation_id")):
            if current is not None and current.get("operation_id") is not None:
                return "superseded"
        return ctx.get("visibility") or "unavailable"

    def _resource_finalize_locked(self, ctx: dict, *, status: str,
                                  io_effect: str, stage: str | None = None,
                                  error_code: str | None = None,
                                  origin: str | None = None,
                                  length: int | None = None,
                                  sha256: str | None = None,
                                  retryable: bool | None = None,
                                  current_index: dict | None = None) -> dict:
        """Update one attempt under Hub + resource registry locks."""
        ctx["status"] = status
        ctx["io_effect"] = io_effect
        ctx["stage"] = stage
        ctx["error_code"] = error_code
        ctx["origin"] = origin
        if length is not None:
            ctx["length"] = length
        if sha256 is not None:
            ctx["sha256"] = sha256
        if retryable is not None:
            ctx["retryable"] = bool(retryable)
        if status == "failed":
            self._resource_order_seq += 1
            ctx["_failed_order"] = self._resource_order_seq
        if status == "pending":
            ctx["visibility"] = "pending"
        elif status in ("failed", "unknown"):
            ctx["visibility"] = "pending" if status == "unknown" else "unavailable"
        if status != "pending":
            ctx["_executing"] = False
        if current_index is not None:
            key = (ctx["kind"], str(ctx["resource_key"]))
            rec = self._resource_keys.setdefault(key, {})
            old = rec.get("current_readable_index")
            if old is not None and old.get("operation_id") != ctx.get(
                    "resource_operation_id"):
                old_ctx = self._resource_ops.get(old.get("operation_id"))
                if old_ctx is not None and old_ctx.get("status") == "confirmed":
                    old_ctx["visibility"] = "superseded"
            rec["current_readable_index"] = copy.deepcopy(current_index)
        ctx["visibility"] = self._resource_visibility_locked(ctx)
        self._resource_trim_terminal_locked(ctx.get("owner_uid"),
                                            protected={ctx.get(
                                                "resource_operation_id")})
        return self._resource_public_result(ctx)

    def _resource_trim_terminal_locked(self, owner_uid: int | None,
                                       protected: set[str] | None = None) -> None:
        """有界淘汰终态结果；pending/unknown 与 latest/current 不得淘汰。"""
        if owner_uid is None:
            return
        protected = protected or set()
        terminal = [ctx for ctx in self._resource_ops.values()
                    if ctx.get("owner_uid") == owner_uid
                    and ctx.get("status") in ("confirmed", "failed")
                    and ctx.get("resource_operation_id") not in protected]
        excess = len(terminal) - int(self._resource_max_terminal)
        if excess <= 0:
            return
        for ctx in terminal[:excess]:
            op = ctx.get("resource_operation_id")
            pair = (ctx.get("kind"), str(ctx.get("resource_key")))
            rec = self._resource_keys.get(pair) or {}
            latest = (rec.get("latest_permit") or {}).get("operation_id")
            current = (rec.get("current_readable_index") or {}).get(
                "operation_id")
            cloud_pin = (ctx.get("kind") == "cloud"
                         and op in {latest, current})
            if op in protected or cloud_pin:
                continue
            self._resource_ops.pop(op, None)
            if ctx.get("kind") == "web_file":
                if self._resource_fid_ops.get(str(ctx.get("resource_key"))) == op:
                    self._resource_fid_ops.pop(str(ctx.get("resource_key")), None)

    def _resource_validate_identity(self, kind: str, key, identity: dict) -> tuple[str, dict]:
        if kind not in _RESOURCE_KINDS:
            raise ValueError("未知资源类型")
        if kind == "cloud":
            if isinstance(key, bool):
                raise ValueError("cloud UID 无效")
            key = int(key)
            if key <= 0:
                raise ValueError("cloud UID 无效")
        else:
            if not (isinstance(key, str) and re.fullmatch(r"[0-9a-f]{32}", key)):
                raise ValueError("fid 无效")
        if not isinstance(identity, dict):
            raise ValueError("资源输入身份无效")
        identity = copy.deepcopy(identity)
        sha = identity.get("payload_sha256")
        length = identity.get("content_length")
        if not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha)):
            raise ValueError("资源摘要无效")
        if isinstance(length, bool) or not isinstance(length, int) or length < 0:
            raise ValueError("资源长度无效")
        return str(key), identity

    def _resource_begin(self, sess: Session, kind: str, key,
                        payload_identity: dict, *,
                        resource_operation_id: str | None = None) -> dict:
        """原子绑定 owner/kind/op/key/输入身份并预留 quota。

        返回的 dict 本身就是当前 attempt context；重复 pending 调用返回同一
        对象，confirmed/unknown 只可查询，failed 仅在仍是 latest permit 时重开
        attempt。磁盘/网络 IO 一律由调用方在锁外完成。
        """
        key_s, identity = self._resource_validate_identity(kind, key,
                                                            payload_identity)
        provided_op = resource_operation_id is not None
        op = resource_operation_id
        if op is None:
            op = secrets.token_hex(16)
        if not (isinstance(op, str) and _RESOURCE_OP_RE.fullmatch(op)):
            raise ValueError("resource_operation_id 无效")
        owner = int(getattr(sess, "uid", 0) or 0)
        if owner <= 0:
            raise PermissionError("资源 owner 无效")
        pair = (kind, key_s)
        with self.lock:
            with self._resource_lock:
                if self._retired_schema_invalid or owner in self.retired:
                    raise PermissionError("资源 owner 已退役")
                existing = self._resource_ops.get(op)
                if existing is None and provided_op:
                    # An explicit id is a retry/query handle, never a way to
                    # invent an old operation.  New logical requests omit it
                    # and receive one atomically here.
                    raise _ResourceError("unknown_operation", None,
                                         "未知资源操作号")
                if existing is not None:
                    same = (existing.get("owner_uid") == owner
                            and existing.get("kind") == kind
                            and str(existing.get("resource_key")) == key_s
                            and existing.get("payload_identity") == identity)
                    if not same:
                        raise PermissionError("resource_operation_id 输入不匹配")
                    if existing.get("status") in ("pending", "unknown",
                                                    "confirmed"):
                        return existing
                    permit = (self._resource_keys.get(pair) or {}).get(
                        "latest_permit") or {}
                    if not existing.get("retryable", False):
                        raise _ResourceError(
                            "retry_forbidden",
                            self._resource_public_result(existing),
                            "该失败资源操作不可重试")
                    permit_ctx = self._resource_ops.get(permit.get(
                        "operation_id")) if permit.get("operation_id") else None
                    failed_order = int(existing.get("_begin_order") or 0)
                    newer_confirmed = (permit_ctx is not None
                                       and permit_ctx.get("status") in (
                                           "pending", "unknown", "confirmed")
                                       and int(permit_ctx.get("_begin_order") or 0)
                                       > failed_order)
                    if permit.get("operation_id") != op and newer_confirmed:
                        latest_ctx = self._resource_ops.get(
                            permit.get("operation_id"))
                        if latest_ctx is not None and latest_ctx.get("status") in (
                                "pending", "unknown", "confirmed"):
                            existing["visibility"] = "superseded"
                            raise _ResourceError(
                                "superseded",
                                self._resource_public_result(existing),
                                "旧资源操作已被后续许可取代")
                    # failed + same latest permit = explicit retry.  Claim
                    # quota before replacing the context so an older callback
                    # keeps an immutable attempt snapshot.
                    active = sum(1 for item in self._resource_ops.values()
                                 if item.get("owner_uid") == owner
                                 and item.get("status") in ("pending", "unknown"))
                    if active >= int(self._resource_max_active):
                        raise PermissionError("资源操作配额已满")
                    attempt = int(existing.get("attempt") or 0) + 1
                    retry_ctx = copy.deepcopy(existing)
                    self._resource_order_seq += 1
                    retry_ctx.update({
                        "attempt": attempt,
                        "attempt_id": f"{op}:{attempt}",
                        "status": "pending", "io_effect": "uncertain",
                        "visibility": "pending", "stage": "begin",
                        "error_code": None, "origin": None,
                        "retryable": True, "_executing": False,
                        "_executor_token": None,
                        "_query_count": 0, "_fenced": False,
                        "_begin_order": self._resource_order_seq,
                        "_failed_order": None,
                    })
                    self._resource_ops[op] = retry_ctx
                    return retry_ctx
                rec = self._resource_keys.setdefault(pair, {})
                active = sum(1 for item in self._resource_ops.values()
                             if item.get("owner_uid") == owner
                             and item.get("status") in ("pending", "unknown"))
                if active >= int(self._resource_max_active):
                    raise PermissionError("资源操作配额已满")
                attempt = 1
                self._resource_order_seq += 1
                ctx = {
                    "resource_operation_id": op,
                    "resource_owner_uid": owner,
                    "owner_uid": owner,
                    "kind": kind,
                    "resource_key": key_s,
                    "payload_identity": identity,
                    "attempt": attempt,
                    "attempt_id": f"{op}:{attempt}",
                    "status": "pending",
                    "io_effect": "uncertain",
                    "visibility": "pending",
                    "stage": "begin",
                    "error_code": None,
                    "length": identity.get("content_length"),
                    "sha256": identity.get("payload_sha256"),
                    "origin": None,
                    "retryable": True,
                    "_executing": False,
                    "_executor_token": None,
                    "_query_count": 0,
                    "_fenced": False,
                    "_begin_order": self._resource_order_seq,
                    "_failed_order": None,
                }
                self._resource_ops[op] = ctx
                if kind == "web_file":
                    self._resource_fid_ops[key_s] = op
                return ctx

    def _resource_claim_executor(self, ctx: dict) -> bool:
        """Claim the sole executor for a pending attempt before staging IO."""
        with self.lock:
            with self._resource_lock:
                current = self._resource_ops.get(ctx.get(
                    "resource_operation_id"))
                if (current is not ctx or current.get("status") != "pending"
                        or current.get("_executing")):
                    return False
                current["_executing"] = True
                current["_executor_token"] = secrets.token_hex(16)
                return True

    def _resource_filter_cloud_after_restore(self) -> None:
        """把启动扫描的 opaque bytes 变成有限访问事实，不伪造旧 op 回执。"""
        with self.lock:
            with self._resource_lock:
                for uid, rec in list(self.cloud.items()):
                    if uid <= 0 or uid in self.retired or self._retired_schema_invalid:
                        self.cloud.pop(uid, None)
                        continue
                    blob = bytes(rec.get("blob") or b"")
                    if not blob:
                        self.cloud.pop(uid, None)
                        continue
                    key = ("cloud", str(uid))
                    self._resource_keys[key] = {
                        "current_readable_index": {
                            "operation_id": None,
                            "owner_uid": uid,
                            "kind": "cloud",
                            "resource_key": str(uid),
                            "length": len(blob),
                            "sha256": hashlib.sha256(blob).hexdigest(),
                            "origin": "restored_resource",
                        }
                    }

    def _resource_withdraw_owner(self, uid: int) -> None:
        """t0 资源屏障：撤私有 cloud 可见 index、取消提醒，不删物理 bytes。"""
        with self.lock:
            with self._resource_lock:
                self._resource_withdraw_owner_locked(uid)

    def _resource_withdraw_owner_locked(self, uid: int) -> None:
        self.cloud.pop(uid, None)
        for key, rec in self._resource_keys.items():
            if key[0] != "cloud" and not any(
                    ctx.get("owner_uid") == uid and
                    (ctx.get("kind"), str(ctx.get("resource_key"))) == key
                    for ctx in self._resource_ops.values()):
                continue
            current = rec.get("current_readable_index")
            if current is not None and current.get("owner_uid") == uid:
                current["visibility"] = "withdrawn"
                rec["current_readable_index"] = current
            for ctx in self._resource_ops.values():
                if ctx.get("owner_uid") != uid:
                    continue
                ctx["_fenced"] = True
                if ctx.get("status") == "confirmed":
                    ctx["visibility"] = "withdrawn"
                elif ctx.get("status") in ("pending", "unknown"):
                    ctx["visibility"] = "withdrawn"

    def _resource_stage_bytes(self, data: bytes, suffix: str) -> str:
        os.makedirs(self._resource_stage_dir, exist_ok=True)
        fd, path = tempfile.mkstemp(prefix="resource-", suffix=suffix,
                                    dir=self._resource_stage_dir)
        raw_fd = fd
        try:
            with os.fdopen(fd, "wb") as stream:
                raw_fd = None
                view = memoryview(bytes(data))
                total = 0
                while total < len(view):
                    n = stream.write(view[total:])
                    if n is None or n <= 0:
                        raise OSError("resource short write")
                    total += n
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            if raw_fd is not None:
                try:
                    os.close(raw_fd)
                except OSError:
                    pass
            try:
                os.unlink(path)
            except OSError:
                pass
            raise
        return path

    def _resource_reconcile(self, ctx: dict) -> dict:
        """锁外严格读未知候选，再以当前 attempt 身份补结果。"""
        kind = ctx.get("kind")
        key = str(ctx.get("resource_key"))
        expected = ctx.get("sha256")
        expected_len = ctx.get("length")
        attempt_id = ctx.get("attempt_id")
        matched = False
        reconciled_blob = None
        observed_len = None
        observed_sha = None
        try:
            if kind == "cloud":
                path = os.path.join(self.cloud_dir, f"{int(key)}.bin")
                with open(path, "rb") as stream:
                    raw = stream.read()
                reconciled_blob = bytes(raw)
                observed_len = len(raw)
                observed_sha = hashlib.sha256(raw).hexdigest()
                matched = (len(raw) == expected_len
                           and observed_sha == expected)
            elif kind == "web_file":
                meta, raw = self._read_web_resource(key)
                if raw is not None:
                    observed_len = len(raw)
                    observed_sha = hashlib.sha256(raw).hexdigest()
                matched = bool(meta and raw is not None
                               and meta.get("resource_operation_id") ==
                               ctx.get("resource_operation_id")
                               and meta.get("resource_owner_uid") ==
                               ctx.get("owner_uid")
                               and meta.get("content_length") == expected_len
                               and meta.get("content_sha256") == expected
                               and len(raw) == expected_len
                               and hashlib.sha256(raw).hexdigest() == expected)
        except (OSError, ValueError, TypeError, OverflowError):
            matched = False
        with self.lock:
            with self._resource_lock:
                current = self._resource_ops.get(
                    ctx.get("resource_operation_id"))
                if current is None:
                    raise LookupError("resource result unavailable")
                if current is not ctx or current.get("attempt_id") != attempt_id:
                    return self._resource_public_result(current)
                if current.get("status") != "unknown":
                    return self._resource_public_result(current)
                if matched:
                    idx = {"operation_id": current["resource_operation_id"],
                           "owner_uid": current["owner_uid"],
                           "kind": current["kind"],
                           "resource_key": current["resource_key"],
                           "length": current.get("length"),
                           "sha256": current.get("sha256"),
                           "origin": "reconciled_current_resource"}
                    if kind == "cloud" and not current.get("_fenced") \
                            and current.get("owner_uid") not in self.retired:
                        if reconciled_blob is not None:
                            self.cloud[int(key)] = {
                                "blob": reconciled_blob, "ts": _now(),
                            }
                    if current.get("_fenced"):
                        current["visibility"] = "withdrawn"
                    return self._resource_finalize_locked(
                        current, status="confirmed", io_effect="uncertain",
                        stage="reconcile", origin="reconciled_current_resource",
                        current_index=idx)
                rec = self._resource_keys.get(
                    (current.get("kind"), str(current.get("resource_key")))) or {}
                predecessor = rec.get("current_readable_index") or {}
                if (observed_len is not None
                        and observed_len == predecessor.get("length")
                        and observed_sha == predecessor.get("sha256")
                        and predecessor.get("operation_id") !=
                        current.get("resource_operation_id")):
                    return self._resource_finalize_locked(
                        current, status="failed", io_effect="not_committed",
                        stage="reconcile", error_code="known_predecessor",
                        retryable=True)
                # A missing/invalid read is deliberately still unknown.  A
                # later explicit query may explain it; it never auto-writes.
                current["_query_count"] = int(current.get("_query_count") or 0) + 1
                return self._resource_public_result(current)

    def _resource_query(self, sess: Session, resource_operation_id: str,
                        *, explicit_owner: int | None = None) -> dict:
        if not (isinstance(resource_operation_id, str)
                and _RESOURCE_OP_RE.fullmatch(resource_operation_id)):
            raise LookupError("resource result unavailable")
        with self.lock:
            with self._resource_lock:
                ctx = self._resource_ops.get(resource_operation_id)
                if ctx is None:
                    raise LookupError("resource result unavailable")
                owner = int(explicit_owner) if explicit_owner is not None else int(
                    getattr(sess, "uid", 0) or 0)
                if not getattr(sess, "is_admin", False) and owner != int(
                        getattr(sess, "uid", 0) or 0):
                    raise PermissionError("无资源查询权限")
                if ctx.get("owner_uid") != owner:
                    raise PermissionError("无资源查询权限")
                if ctx.get("owner_uid") in self.retired and not getattr(
                        sess, "is_admin", False):
                    raise PermissionError("资源 owner 已退役")
                if ctx.get("status") == "unknown":
                    snapshot = ctx
                else:
                    ctx["visibility"] = self._resource_visibility_locked(ctx)
                    return self._resource_public_result(ctx)
        return self._resource_reconcile(snapshot)

    def _resource_summary(self, owner_uid: int) -> dict:
        with self._resource_lock:
            ops = [self._resource_public_result(ctx)
                   for ctx in self._resource_ops.values()
                   if ctx.get("owner_uid") == owner_uid]
        limit = int(self._resource_max_terminal)
        ops = ops[-limit:] if limit else []
        return {"resource_owner_uid": owner_uid, "scope": "runtime",
                "operations": ops}

    def _resource_file_commit(self, ctx: dict, payload: bytes,
                              meta: dict | None = None) -> dict:
        """Stage bytes/manifest, C, publish, then record D_resource."""
        kind = ctx.get("kind")
        if kind not in _RESOURCE_KINDS:
            raise ValueError("未知资源类型")
        if ctx.get("status") != "pending":
            raise _ResourceError("resource_pending",
                                 self._resource_public_result(ctx))
        if not ctx.get("_executing") and not self._resource_claim_executor(ctx):
            raise _ResourceError("resource_pending",
                                 self._resource_public_result(ctx))
        attempt_id = ctx.get("attempt_id")
        executor_token = ctx.get("_executor_token")
        if not isinstance(attempt_id, str) or not isinstance(executor_token, str):
            raise _ResourceError("stale_attempt",
                                 self._resource_public_result(ctx))
        raw = bytes(payload or b"")
        length = len(raw)
        digest = hashlib.sha256(raw).hexdigest()
        if length != ctx.get("length") or digest != ctx.get("sha256"):
            with self.lock:
                with self._resource_lock:
                    self._resource_finalize_locked(
                        ctx, status="failed", io_effect="not_committed",
                        stage="identity", error_code="payload_mismatch",
                        retryable=True)
            raise _ResourceError("payload_mismatch",
                                 self._resource_public_result(ctx))
        if kind == "web_file":
            fid = str(ctx["resource_key"])
            own_fid = self._resource_fid_ops.get(fid) == ctx.get(
                "resource_operation_id") and not ctx.get("_fid_conflict")
            if ((os.path.exists(os.path.join(self.web_files, fid))
                 or os.path.exists(os.path.join(self.web_files, fid + ".json")))
                    and not own_fid):
                with self.lock:
                    with self._resource_lock:
                        self._resource_finalize_locked(
                            ctx, status="failed", io_effect="not_committed",
                            stage="begin", error_code="fid_conflict",
                            retryable=False)
                        ctx["_fid_conflict"] = True
                raise _ResourceError("fid_conflict",
                                     self._resource_public_result(ctx))
        body_stage = None
        meta_stage = None
        target_body = None
        target_meta = None
        replace_attempted = False
        meta_replace_attempted = False
        pre_body_same = False
        pre_meta_same = False
        pre_body_identity = None
        try:
            body_stage = self._resource_stage_bytes(raw, ".body")
            if kind == "cloud":
                target_body = os.path.join(self.cloud_dir,
                                           f"{int(ctx['resource_key'])}.bin")
            else:
                fid = str(ctx["resource_key"])
                target_body = os.path.join(self.web_files, fid)
                safe = {"fid": fid, "name": str((meta or {}).get("name")
                                                  or "未命名")[:128],
                        "size": length, "kind": (meta or {}).get("kind") or "file",
                        "ts": round(_now(), 3),
                        "resource_manifest_version": self._resource_manifest_version,
                        "resource_owner_uid": ctx["owner_uid"],
                        "resource_operation_id": ctx["resource_operation_id"],
                        "content_length": length,
                        "content_sha256": digest}
                encoded = json.dumps(safe, ensure_ascii=False, allow_nan=False,
                                     separators=(",", ":")).encode("utf-8")
                meta_stage = self._resource_stage_bytes(encoded, ".json")
                target_meta = os.path.join(self.web_files, fid + ".json")
            try:
                if target_body and os.path.isfile(target_body):
                    stat = os.stat(target_body)
                    pre_body_identity = (getattr(stat, "st_ino", None),
                                         getattr(stat, "st_mtime_ns", None),
                                         getattr(stat, "st_size", None))
                    with open(target_body, "rb") as stream:
                        pre_body_same = (hashlib.sha256(stream.read()).hexdigest()
                                         == digest)
                if target_meta and os.path.isfile(target_meta):
                    with open(target_meta, "rb") as stream:
                        pre_meta_same = bool(stream.read())
            except OSError:
                pre_body_same = False
                pre_meta_same = False
            # Final C is ordered with t0 by the same Hub memory boundary.
            with self.lock:
                with self._resource_lock:
                    current = self._resource_ops.get(
                        ctx.get("resource_operation_id"))
                    permit = (self._resource_keys.get(
                        (kind, str(ctx["resource_key"]))) or {}).get(
                            "latest_permit") or {}
                    permit_op = permit.get("operation_id")
                    permit_ctx = self._resource_ops.get(permit_op) \
                        if permit_op else None
                    permit_is_newer_confirmed = (
                        permit_op not in (None, ctx.get("resource_operation_id"))
                        and permit_ctx is not None
                        and permit_ctx.get("status") == "confirmed"
                        and int(permit_ctx.get("_begin_order") or 0)
                        > int(ctx.get("_begin_order") or 0))
                    newer_in_flight = (
                        permit_op not in (None, ctx.get(
                            "resource_operation_id"))
                        and permit_ctx is not None
                        and (permit_ctx.get("status") in ("pending", "unknown")
                             or permit_is_newer_confirmed))
                    if newer_in_flight:
                        if permit_is_newer_confirmed:
                            self._resource_finalize_locked(
                                ctx, status="failed", io_effect="not_committed",
                                stage="permit", error_code="superseded",
                                retryable=False)
                            raise _ResourceError(
                                "superseded", self._resource_public_result(ctx),
                                "旧资源发布许可已被后续 C 取代")
                        self._resource_finalize_locked(
                            ctx, status="failed", io_effect="not_committed",
                            stage="permit", error_code="resource_busy",
                            retryable=True)
                        raise _ResourceError(
                            "resource_busy", self._resource_public_result(ctx),
                            "同一资源仍有较早发布在途")
                    if current is not ctx:
                        ctx.update({"status": "failed",
                                    "io_effect": "not_committed",
                                    "stage": "permit",
                                    "error_code": "stale_attempt",
                                    "retryable": False,
                                    "_executing": False})
                        raise _ResourceError(
                            "stale_attempt", self._resource_public_result(ctx),
                            "迟到资源执行结果已丢弃")
                    if (current.get("status") != "pending"
                            or current.get("_fenced")
                            or ctx.get("owner_uid") in self.retired):
                        ctx["_fenced"] = True
                        self._resource_finalize_locked(
                            ctx, status="failed", io_effect="not_committed",
                            stage="permit", error_code="owner_fenced",
                            retryable=False)
                        raise _ResourceError("owner_fenced",
                                             self._resource_public_result(ctx))
                    # This is the actual C point.  A later C supersedes the
                    # previous readable index; merely beginning/staging an op
                    # does not steal the permit from an earlier stage.
                    self._resource_keys.setdefault(
                        (kind, str(ctx["resource_key"])), {})[
                            "latest_permit"] = {
                                "operation_id": ctx["resource_operation_id"],
                                "attempt": ctx["attempt"]}
            # Publish body first, manifest last.  No Hub/registry lock is held.
            replace_attempted = True
            os.replace(body_stage, target_body)
            body_stage = None
            if meta_stage is not None:
                meta_replace_attempted = True
                replace_attempted = True
                os.replace(meta_stage, target_meta)
                meta_stage = None
        except _ResourceError:
            raise
        except Exception as exc:
            # If replace may have happened before an injected acknowledgement
            # error, classify as unknown and require a later strict query.
            uncertain = False
            try:
                if replace_attempted and target_body and os.path.isfile(target_body):
                    post_stat = os.stat(target_body)
                    post_body_identity = (getattr(post_stat, "st_ino", None),
                                          getattr(post_stat, "st_mtime_ns", None),
                                          getattr(post_stat, "st_size", None))
                    with open(target_body, "rb") as stream:
                        observed = stream.read()
                    body_matches = (len(observed) == length
                                    and hashlib.sha256(observed).hexdigest() == digest)
                    changed_after_attempt = (pre_body_identity is None
                                             or pre_body_identity !=
                                             post_body_identity)
                    uncertain = body_matches and (
                        not pre_body_same or changed_after_attempt)
                    if kind == "web_file" and not meta_replace_attempted:
                        # Body publication without a manifest attempt is a
                        # known partial effect: failed/not_committed, with an
                        # orphan body that remains unservable.
                        uncertain = False
                    elif kind == "web_file" and meta_replace_attempted:
                        # Metadata replace was attempted; target proof must
                        # include a valid candidate manifest as well.
                        try:
                            with open(target_meta, "rb") as stream:
                                observed_meta = self._json_load_strict(stream.read())
                            uncertain = body_matches and isinstance(observed_meta, dict) \
                                and observed_meta.get("resource_manifest_version") == \
                                self._resource_manifest_version \
                                and observed_meta.get("fid") == str(
                                    ctx.get("resource_key")) \
                                and observed_meta.get("resource_owner_uid") == \
                                ctx.get("owner_uid") \
                                and observed_meta.get("resource_operation_id") == \
                                ctx.get("resource_operation_id") \
                                and observed_meta.get("content_length") == length \
                                and observed_meta.get("content_sha256") == digest
                        except (OSError, ValueError, TypeError, UnicodeDecodeError):
                            uncertain = False
                    elif kind == "web_file" and pre_meta_same:
                        uncertain = False
            except OSError:
                pass
            with self.lock:
                with self._resource_lock:
                    self._resource_finalize_locked(
                        ctx, status="unknown" if uncertain else "failed",
                        io_effect="uncertain" if uncertain else "not_committed",
                        stage="manifest" if meta_stage is not None and
                        target_meta else "body",
                        error_code=type(exc).__name__.lower(),
                        retryable=not uncertain)
            raise _ResourceError("resource_unknown" if uncertain else "resource_io",
                                 self._resource_public_result(ctx), str(exc))
        finally:
            for staged in (body_stage, meta_stage):
                if staged:
                    try:
                        os.unlink(staged)
                    except OSError:
                        pass
        index = {"operation_id": ctx["resource_operation_id"],
                 "owner_uid": ctx["owner_uid"], "kind": kind,
                 "resource_key": str(ctx["resource_key"]), "length": length,
                 "sha256": digest, "origin": "written"}
        with self.lock:
            with self._resource_lock:
                current = self._resource_ops.get(ctx["resource_operation_id"])
                permit = (self._resource_keys.get(
                    (kind, str(ctx["resource_key"]))) or {}).get(
                        "latest_permit") or {}
                valid_executor = (
                    current is ctx
                    and current.get("status") == "pending"
                    and current.get("attempt_id") == attempt_id
                    and current.get("_executor_token") == executor_token
                    and current.get("_executing")
                    and permit.get("operation_id") ==
                    ctx.get("resource_operation_id")
                    and permit.get("attempt") == ctx.get("attempt"))
                if not valid_executor:
                    if current is not ctx:
                        ctx["status"] = "failed"
                        ctx["io_effect"] = "not_committed"
                        ctx["stage"] = "finalize"
                        ctx["error_code"] = "stale_attempt"
                        ctx["retryable"] = False
                        raise _ResourceError(
                            "stale_attempt", self._resource_public_result(ctx),
                            "迟到资源执行结果已丢弃")
                    self._resource_finalize_locked(
                        ctx, status="failed", io_effect="not_committed",
                        stage="finalize", error_code="stale_executor",
                        retryable=False)
                    raise _ResourceError(
                        "stale_attempt", self._resource_public_result(ctx),
                        "资源执行者已失效")
                result = self._resource_finalize_locked(
                    current, status="confirmed", io_effect="committed",
                    stage="finalize", origin="written", length=length,
                    sha256=digest, retryable=False, current_index=index)
                if kind == "cloud" and not current.get("_fenced") \
                        and current.get("owner_uid") not in self.retired:
                    self.cloud[int(current["resource_key"])] = {
                        "blob": bytes(raw), "ts": _now(),
                    }
                if current.get("_fenced") or current.get("owner_uid") in self.retired:
                    current["visibility"] = "withdrawn"
                    result = self._resource_public_result(current)
        return result

    # ---------- R23 网页端文件存储 ----------
    def _save_web_file(self, name: str, data: bytes, kind: str,
                       *, sess: Session | None = None,
                       resource_operation_id: str | None = None) -> dict:
        """保存 Web 文件；带 Session 时走 RESOURCE 双文件发布。"""
        safe_name = (name or "未命名").replace("\\", "/").split("/")[-1][:128]
        if sess is None:
            # 既有内部调用兼容路径；新 Web 上传总是带认证 Session，避免
            # legacy helper 伪造新 owner/op manifest。
            fid = uuid.uuid4().hex
            meta = {"fid": fid, "name": safe_name, "size": len(data),
                    "kind": kind, "ts": round(_now(), 3)}
            with open(os.path.join(self.web_files, fid), "wb") as stream:
                stream.write(bytes(data))
            with open(os.path.join(self.web_files, fid + ".json"), "w",
                       encoding="utf-8") as stream:
                json.dump(meta, stream, ensure_ascii=False)
            return {k: meta[k] for k in ("fid", "name", "size", "kind")}
        payload = bytes(data or b"")
        op = resource_operation_id
        if op is not None and not _RESOURCE_OP_RE.fullmatch(str(op)):
            raise _ResourceError("invalid_operation")
        if op is not None:
            with self.lock:
                with self._resource_lock:
                    if str(op) not in self._resource_ops:
                        raise _ResourceError("unknown_operation", None,
                                             "未知资源操作号")
        # Exact known-op retry reuses its original fid; a new op gets a new fid.
        if op and op in self._resource_ops:
            old = self._resource_ops[op]
            fid = str(old.get("resource_key"))
        else:
            fid = uuid.uuid4().hex
        identity = {"payload_sha256": hashlib.sha256(payload).hexdigest(),
                    "content_length": len(payload), "name": safe_name,
                    "kind": kind}
        ctx = self._resource_begin(sess, "web_file", fid, identity,
                                   resource_operation_id=op)
        if ctx.get("status") == "confirmed":
            with self.lock:
                with self._resource_lock:
                    ctx["visibility"] = self._resource_visibility_locked(ctx)
                    result = self._resource_public_result(ctx)
            if result.get("visibility") != "available":
                raise _ResourceError("superseded", result,
                                     "旧 Web 资源操作已被后续版本取代")
            return {"fid": fid, "name": safe_name, "size": len(payload),
                    "kind": kind, "resource": result}
        if ctx.get("status") in ("unknown", "pending"):
            if ctx.get("status") == "unknown":
                raise _ResourceError("resource_unknown",
                                     self._resource_public_result(ctx))
            if not self._resource_claim_executor(ctx):
                raise _ResourceError("resource_pending",
                                     self._resource_public_result(ctx))
        result = self._resource_file_commit(
            ctx, payload, {"name": safe_name, "kind": kind})
        return {"fid": fid, "name": safe_name, "size": len(payload),
                "kind": kind, "resource": result}

    @staticmethod
    def _json_load_strict(raw: bytes | str):
        seen = set()

        def pairs(items):
            out = {}
            for key, value in items:
                if key in seen:
                    raise ValueError("duplicate JSON key")
                seen.add(key)
                out[key] = value
            return out

        if isinstance(raw, bytes):
            text = raw.decode("utf-8")
        elif isinstance(raw, str):
            text = raw
        else:
            raise ValueError("manifest is not text")
        return json.loads(text, object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(
                              ValueError(f"non-finite JSON: {value}")))

    def _read_web_resource(self, fid: str) -> tuple[dict | None, bytes | None]:
        if not (isinstance(fid, str) and re.fullmatch(r"[0-9a-f]{32}", fid)):
            return None, None
        meta_path = os.path.join(self.web_files, fid + ".json")
        body_path = os.path.join(self.web_files, fid)
        try:
            with open(meta_path, "rb") as stream:
                raw_meta = stream.read()
            meta = self._json_load_strict(raw_meta)
            if not isinstance(meta, dict):
                return None, None
            if not os.path.isfile(body_path):
                return None, None
            with open(body_path, "rb") as stream:
                raw_body = stream.read()
        except (OSError, ValueError, UnicodeDecodeError, TypeError):
            return None, None
        timestamp = meta.get("ts")
        try:
            valid_timestamp = (not isinstance(timestamp, bool)
                               and isinstance(timestamp, (int, float))
                               and math.isfinite(float(timestamp)))
        except OverflowError:
            # JSON integers are unbounded; an unreadable timestamp makes the
            # manifest ineligible, rather than aborting CHAT or HTTP readers.
            valid_timestamp = False
        if not valid_timestamp:
            return None, None
        if set(meta).intersection(_RESOURCE_NEW_FIELDS):
            if (set(meta) != _RESOURCE_MANIFEST_FIELDS
                    or type(meta.get("resource_manifest_version")) is not int
                    or meta.get("resource_manifest_version") !=
                    self._resource_manifest_version
                    or not isinstance(meta.get("fid"), str)
                    or meta.get("fid") != fid
                    or not isinstance(meta.get("name"), str)
                    or meta.get("kind") not in ("image", "file")
                    or isinstance(meta.get("size"), bool)
                    or not isinstance(meta.get("size"), int)
                    or meta.get("size") < 0
                    or isinstance(meta.get("resource_owner_uid"), bool)
                    or not isinstance(meta.get("resource_owner_uid"), int)
                    or meta.get("resource_owner_uid") <= 0
                    or not (isinstance(meta.get("resource_operation_id"), str)
                            and _RESOURCE_OP_RE.fullmatch(
                                meta.get("resource_operation_id")))
                    or meta.get("content_length") != len(raw_body)
                    or isinstance(meta.get("content_length"), bool)
                    or not isinstance(meta.get("content_length"), int)
                    or meta.get("size") != len(raw_body)
                    or not (isinstance(meta.get("content_sha256"), str)
                            and re.fullmatch(r"[0-9a-f]{64}",
                                             meta.get("content_sha256")))
                    or meta.get("content_sha256") !=
                    hashlib.sha256(raw_body).hexdigest()):
                return None, None
        else:
            if (set(meta) != {"fid", "name", "size", "kind", "ts"}
                    or meta.get("fid") != fid
                    or not isinstance(meta.get("name"), str)
                    or meta.get("kind") not in ("image", "file")
                    or isinstance(meta.get("size"), bool)
                    or not isinstance(meta.get("size"), int)
                    or meta.get("size") < 0
                    or meta.get("size") != len(raw_body)):
                return None, None
        return meta, raw_body

    def _web_file_meta(self, fid: str) -> dict | None:
        """读取并验证 legacy/new manifest 及实际 body；坏新格式不降级。"""
        meta, raw = self._read_web_resource(fid)
        if meta is None or raw is None:
            return None
        if set(meta).intersection(_RESOURCE_NEW_FIELDS):
            # 完整 manifest 可在新进程恢复访问事实，但不重建旧 op receipt。
            with self.lock:
                with self._resource_lock:
                    runtime_op = self._resource_fid_ops.get(str(fid))
                    runtime_ctx = (self._resource_ops.get(runtime_op)
                                   if runtime_op else None)
                    if runtime_ctx is not None:
                        if (runtime_ctx.get("status") != "confirmed"
                                or runtime_ctx.get("resource_operation_id") !=
                                meta.get("resource_operation_id")
                                or runtime_ctx.get("owner_uid") !=
                                meta.get("resource_owner_uid")
                                or (runtime_ctx.get("payload_identity") or {}).get(
                                    "name") != meta.get("name")
                                or (runtime_ctx.get("payload_identity") or {}).get(
                                    "kind") != meta.get("kind")
                                or runtime_ctx.get("length") !=
                                meta.get("content_length")
                                or runtime_ctx.get("sha256") !=
                                meta.get("content_sha256")):
                            return None
                    key = ("web_file", str(fid))
                    rec = self._resource_keys.setdefault(key, {})
                    rec.setdefault("current_readable_index", {
                        "operation_id": meta["resource_operation_id"],
                        "owner_uid": meta["resource_owner_uid"],
                        "kind": "web_file", "resource_key": fid,
                        "length": len(raw),
                        "sha256": meta["content_sha256"],
                        "origin": "restored_resource",
                    })
        return meta

    def _web_file_path(self, fid: str) -> str | None:
        if not (isinstance(fid, str) and re.fullmatch(r"[0-9a-f]{32}", fid)):
            return None
        path = os.path.join(self.web_files, fid)
        return path if os.path.isfile(path) else None

    def _web_file_read(self, sess: Session, fid: str, meta: dict) -> bytes:
        """C_read：先捕获身份/资格，再锁外读取不可变响应 bytes。"""
        with self.lock:
            if getattr(sess, "uid", 0) in self.retired \
                    or self._retired_schema_invalid:
                raise PermissionError("resource owner retired")
            path = self._web_file_path(fid)
        if not path:
            raise OSError("file missing")
        with open(path, "rb") as stream:
            data = stream.read()
        if len(data) != meta.get("size"):
            raise OSError("file length changed")
        if set(meta).intersection(_RESOURCE_NEW_FIELDS):
            if hashlib.sha256(data).hexdigest() != meta.get("content_sha256"):
                raise OSError("file digest changed")
        return bytes(data)

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

    def _error(self, sess: Session, code: str, text: str, **extra) -> None:
        try:
            payload = {"t": "error", "code": code, "text": text}
            resource = extra.get("resource")
            if isinstance(resource, dict):
                payload["resource"] = self._resource_public_result(resource)
            sess.send(payload)
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

    def _offline_notice_before_snapshot(self, uid: int, text: str) -> None:
        """离线通知收件人快照前的受控栅栏（生产路径为空操作）。"""
        return None

    def _broadcast_offline_notice(self, uid: int, nick: str) -> None:
        """提交 UID 下线通知；校验与收件人快照在同一锁临界区完成。"""
        text = f"{nick} 已下线"
        rec = {"text": text, "state": "pending"}
        with self.lock:
            if self._uid_clients.get(uid):
                return
            self._offline_notice_records[uid] = rec
        try:
            self._offline_notice_before_snapshot(uid, text)
            payload = {"t": "system", "text": text, "ts": round(_now(), 3)}
            with self.lock:
                current = self._offline_notice_records.get(uid)
                if (current is not rec or rec.get("state") == "cancelled"
                        or self._uid_clients.get(uid)):
                    if current is rec:
                        self._offline_notice_records.pop(uid, None)
                    return
                recipients = [s for clients in self._uid_clients.values()
                              for s in clients]
                self._offline_notice_records.pop(uid, None)
            for sess in recipients:
                try:
                    sess.send(payload)
                except Exception:
                    pass
        finally:
            with self.lock:
                if self._offline_notice_records.get(uid) is rec:
                    self._offline_notice_records.pop(uid, None)

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
        if self._retire_error(sess):
            return
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
        rejected = False
        with self.lock:
            rejected = (self._uid_retired_locked(sess.uid)
                        or self._uid_retired_locked(target))
            if not rejected:
                cur = self.blocks.setdefault(sess.uid, set())
                if on:
                    cur.add(target)
                else:
                    cur.discard(target)
                    if not cur:
                        self.blocks.pop(sess.uid, None)
        if rejected:
            self._error(sess, "retired", "账号已退役或目标已退役")
            return
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
        if self._retire_error(sess):
            return
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
            with self.lock:
                target_retired = self._uid_retired_locked(to)
            if target_retired:
                self._error(sess, "retired", "目标账号已退役")
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
        rejected = False
        with self.lock:
            rejected = self._uid_retired_locked(sess.uid)
            if not rejected and channel == "private":
                rejected = self._uid_retired_locked(int(to))
            if not rejected:
                self.scheds.setdefault(sess.uid, {})[rid] = rec
        if rejected:
            self._error(sess, "retired", "账号已退役或目标已退役")
            return
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
        if self._retire_error(sess):
            return
        with self.lock:
            rejected = self._uid_retired_locked(sess.uid)
            if not rejected:
                mine = self.scheds.get(sess.uid)
                if mine and rid in mine:
                    del mine[rid]
        if rejected:
            self._error(sess, "retired", "账号已退役")
            return
        self._send_sched_list(sess, sess.uid)
        self.audit.log(type="sched_cancel", uid=sess.uid, rid=rid)
        self._persist()

    def _on_sched_list(self, sess: Session) -> None:
        """拉取我的待发列表（重连/换端对齐）。"""
        self._send_sched_list(sess, sess.uid)

    def _sweep_scheds(self, now: float | None = None) -> None:
        """sweeper 每轮调用：到点的定时消息以创建者身份入频道历史并广播。

        Hub.lock 内只收集/最终提交内存，逐个以服务器身份的网络投递在锁外。
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
            # 已摘出的 due 也必须在最终 publish C 重新检查退役；t0 与此
            # 短内存边界互斥，发送/审计/持久化仍在锁外。
            with self.lock:
                target_uid = r.get("to") if r.get("channel") == "private" else None
                if (self._uid_retired_locked(uid)
                        or (target_uid is not None
                            and self._uid_retired_locked(int(target_uid)))):
                    continue
                msg = self.bus.publish(msg)
            self._route(msg)
            self.audit.log(type="sched_fire", uid=uid, seq=msg["seq"],
                           channel=r["channel"], to=msg.get("to"))
            self._persist()

    # ---------- CC-02C RESOURCE：提醒队列最终 bot C ----------
    def _bot_reminder_enqueue(self, owner_uid: int, due: float, text: str,
                              bot_uid: int) -> bool:
        """在 Hub 短锁内入队；提醒仍为运行态，不进入 Store。"""
        try:
            owner_uid = int(owner_uid)
            due = float(due)
        except (TypeError, ValueError, OverflowError):
            return False
        if owner_uid <= 0 or not isinstance(text, str) or not text:
            return False
        with self.lock:
            if self._retired_schema_invalid or self._uid_retired_locked(owner_uid):
                return False
            self.bot_reminders.append({"uid": owner_uid, "due": due,
                                       "text": text[:self.cfg.chat_text_max],
                                       "bot_uid": int(bot_uid)})
        return True

    def _bot_reminder_take_due(self, now: float | None = None) -> list[dict]:
        now = _now() if now is None else float(now)
        with self.lock:
            due = [dict(r) for r in self.bot_reminders
                   if float(r.get("due", 0)) <= now]
            if due:
                self.bot_reminders = [r for r in self.bot_reminders
                                      if float(r.get("due", 0)) > now]
            return due

    def _bot_reminder_cancel_owner(self, owner_uid: int) -> None:
        with self.lock:
            self.bot_reminders = [r for r in self.bot_reminders
                                  if r.get("uid") != owner_uid]

    def _bot_reminder_cancel_owner_locked(self, owner_uid: int) -> None:
        self.bot_reminders = [r for r in self.bot_reminders
                              if r.get("uid") != owner_uid]

    def _known_uid(self, uid: int) -> bool:
        """该 uid 是否已知用户（注册过/在会话中）。"""
        with self.lock:
            return uid in self.sessions or uid in self.known

    # ---------- CC-02A-RETIRE-CORE：M1 身份屏障 ----------
    def _uid_retired_locked(self, uid: int) -> bool:
        """调用方已持有 Hub.lock 时判断 UID 是否永久退役/被 fence。"""
        return uid in self.retired

    def _retire_error(self, sess: Session, *, target_uid: int | None = None) -> bool:
        """锁外向调用方报告退役/损坏身份屏障；返回是否应拒绝本次写入。"""
        with self.lock:
            blocked = self._retired_schema_invalid
            if target_uid is not None:
                blocked = blocked or self._uid_retired_locked(int(target_uid))
            blocked = blocked or self._uid_retired_locked(int(getattr(sess, "uid", 0)))
        if blocked:
            self._error(sess, "retired", "账号已退役或身份状态不可用")
        return blocked

    def _resolve_uid_for_admin(self, raw) -> int | None:
        """管理员目标解析：保留 retired 的 nick→UID 查询能力。"""
        try:
            if isinstance(raw, bool):
                raise ValueError
            uid = int(raw)
            return uid if uid > 0 else None
        except (TypeError, ValueError, OverflowError):
            pass
        if not isinstance(raw, str):
            return None
        with self.lock:
            mapped = self.nick_to_uid.get(raw.strip())
            if mapped is not None:
                return int(mapped)
            for uid, info in self.known.items():
                if info.get("nick") == raw:
                    return uid
            for uid, info in self.retired.items():
                if info.get("nick") == raw:
                    return uid
        return None

    def _retirement_payload(self, uid: int) -> dict | None:
        """ADMIN_USER_INFO 的最小退役状态；不暴露密码/session/token。"""
        with self.lock:
            rec = self.retired.get(uid)
            op = self._retire_ops.get(uid)
            if rec is None and op is None:
                return None
            if rec is not None:
                nick = rec.get("nick", "")
                op_id = rec.get("operation_id", "")
            else:
                nick = op.get("target_nick", "")
                op_id = op.get("operation_id", "")
            status = (op or {}).get("status") or ("confirmed" if rec else "unknown")
            origin = (op or {}).get("origin")
            if origin not in {"written", "reconciled_current_json",
                              "restored_valid_json"}:
                origin = None
            content_sha256 = (op or {}).get("content_sha256")
            content_length = (op or {}).get("content_length")
            out = {"status": status, "operation_id": op_id,
                   "target_uid": uid, "target_nick": nick,
                   "target_revision": None, "committed_revision": None,
                   "content_sha256": content_sha256 if status == "confirmed" else None,
                   "content_length": content_length if status == "confirmed" else None,
                   "origin": origin if status == "confirmed" else None,
                   "failed_stage": None,
                   "error_code": None,
                   "retryable": False}
            if op:
                for key in ("failed_stage", "error_code", "retryable"):
                    if key in op:
                        out[key] = op[key]
            return out

    def _retirement_operation_id(self, uid: int) -> str | None:
        """Read the runtime operation id without triggering disk reconcile."""
        with self.lock:
            op = self._retire_ops.get(uid)
            if isinstance(op, dict) and isinstance(op.get("operation_id"), str):
                return op["operation_id"]
            record = self.retired.get(uid)
            if isinstance(record, dict) and isinstance(record.get("operation_id"), str):
                return record["operation_id"]
        return None

    def _sched_still_valid(self, uid: int, r: dict) -> bool:
        """到点校验：私聊目标是否已拉黑我；群聊我是否仍是成员。"""
        with self.lock:
            if self._uid_retired_locked(uid):
                return False
            target_uid = r.get("to") if r.get("channel") == "private" else None
            if target_uid is not None and self._uid_retired_locked(int(target_uid)):
                return False
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
        reject = None
        with self.lock:
            if self._retired_schema_invalid:
                reject = "身份状态不可用，拒绝登录"
            old_uid = self.nick_to_uid.get(sess.nick)
            if reject is None and (old_uid in self.retired or any(
                    rec.get("nick") == sess.nick for rec in self.retired.values())):
                reject = "该昵称对应的 UID 已永久退役"
            if reject is None and old_uid is not None:
                sess.uid = old_uid
            elif reject is None:
                while (self._uid_seq in self.retired
                       or self._uid_seq in self.known
                       or self._uid_seq in _bots.BOT_BY_UID):
                    self._uid_seq += 1
                sess.uid = self._uid_seq
                self._uid_seq += 1
            was_online = sess.uid in self.sessions
            self._uid_clients.setdefault(sess.uid, set()).add(sess)
            self.sessions[sess.uid] = sess
            self.nick_to_uid[sess.nick] = sess.uid
            notice = self._offline_notice_records.get(sess.uid)
            if notice is not None and notice.get("state") == "pending":
                notice["state"] = "cancelled"
            prev = self.known.get(sess.uid)
            self.known[sess.uid] = {"nick": sess.nick,
                                    "last_online": (prev or {}).get("last_online", 0)}
            for _k in _KNOWN_PROFILE_FIELDS:
                if prev is not None and _k in prev:
                    self.known[sess.uid][_k] = copy.deepcopy(prev[_k])
        if reject is not None:
            self._error(sess, "retired", reject)
            return False
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
        with self.lock:
            if self._retired_schema_invalid or self._uid_retired_locked(sess.uid):
                sess.closed = True
                return False
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
        if not self._attach(sess):           # t0 可能在最终 attach 前建立 fence
            return None, "该昵称对应的 UID 已永久退役"
        if password and not sess.is_admin:
            if not self._pwd_claim(sess.uid, password):
                return None, "该账号已退役或登录已失效"
        token = secrets.token_hex(16)
        with self.lock:
            if (self._retired_schema_invalid
                    or self._uid_retired_locked(sess.uid)
                    or sess.closed):
                return None, "该账号已退役或登录已失效"
            self.web_tokens[token] = sess
        with self.lock:
            if not self._session_is_active(sess):
                self.web_tokens.pop(token, None)
                return None, "该账号已退役或登录已失效"
        return sess, token

    # ---------- R47-B：昵称可选密码 ----------
    def _pwd_check_for_login(self, nick: str, password: str) -> str | None:
        """登录期昵称密码校验。返回错误文案或 None（通过）。

        已设密码：password 必须匹配（PBKDF2 校验在锁外做，避免占 Hub 锁）；
        未设密码：放行（带密码时由调用方在 attach 成功后 claim 绑定）。
        管理员标识始终保留；未配置部署凭据时不降级为普通账号。"""
        with self.lock:
            if self._retired_schema_invalid:
                return "身份状态不可用，拒绝登录"
            if (nick in self.nick_to_uid
                    and self.nick_to_uid.get(nick) in self.retired):
                return "该昵称对应的 UID 已永久退役"
            if any(rec.get("nick") == nick for rec in self.retired.values()):
                return "该昵称对应的 UID 已永久退役"
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

    def _pwd_store(self, uid: int, stored: str | None) -> bool:
        """known[uid]['pwd'] 写入/清除（R16 落盘随 _persist）。"""
        with self.lock:
            if self._uid_retired_locked(uid):
                return False
            info = self.known.get(uid)
            if info is None:
                return False
            if stored:
                info["pwd"] = stored
            else:
                info.pop("pwd", None)
        self._persist()
        return True

    def _pwd_claim(self, uid: int, password: str) -> bool:
        """登录时带了密码且该昵称未设密码 → 绑定（先到先得）。"""
        with self.lock:
            if self._uid_retired_locked(uid):
                return False
            info = self.known.get(uid)
            if not info:
                return False
            if info.get("pwd"):
                return True
        if not self._pwd_store(uid, auth.make(password)):
            return False
        self.audit.log(type="pwd_claim", uid=uid)
        return True

    def set_password(self, uid: int, old: str, new: str) -> str | None:
        """R47-B：设置/修改/清除昵称密码（需已登录身份）。返回错误文案或 None。

        - 未设密码：new 非空=绑定；new 空=报「尚未设置密码」；
        - 已设密码：old 必须匹配；new 空=清除。
        管理员凭据由部署侧管理，拒绝通过普通账号接口修改/清除。"""
        with self.lock:
            if self._retired_schema_invalid or self._uid_retired_locked(uid):
                return "账号已退役或身份状态不可用"
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
            if not self._pwd_store(uid, None):
                return "账号已退役或身份状态不可用"
            self.audit.log(type="pwd_change", uid=uid, action="clear")
            return None
        if len(new) > PWD_MAX:
            return f"密码过长（≤{PWD_MAX} 字符）"
        if not self._pwd_store(uid, auth.make(new)):
            return "账号已退役或身份状态不可用"
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
        if self._retire_error(sess):
            return
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
            rejected = self._uid_retired_locked(uid)
            if not rejected:
                self.known.setdefault(uid, {})["avatar"] = ext
        if rejected:
            try:
                os.remove(path)
            except OSError:
                pass
            self._error(sess, "retired", "账号已退役")
            return
        self._persist()
        self._broadcast_roster()
        sess.send({"t": MsgType.AVATAR_DATA.value, "uid": uid, "ext": ext}, body)

    def _on_avatar_del(self, sess: Session) -> None:
        """R52：删除头像。"""
        if self._retire_error(sess):
            return
        uid = sess.uid
        old_ext = self._avatar_known(uid)
        if old_ext:
            try:
                os.remove(self._avatar_file(uid, old_ext))
            except OSError:
                pass
        with self.lock:
            rejected = self._uid_retired_locked(uid)
            if not rejected:
                (self.known.get(uid) or {}).pop("avatar", None)
        if rejected:
            self._error(sess, "retired", "账号已退役")
            return
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
        if self._retire_error(sess):
            return
        sign = str(header.get("sign") or "").strip()[:self.cfg.sign_max_len]
        with self.lock:
            rejected = self._uid_retired_locked(sess.uid)
            if not rejected:
                self.known.setdefault(sess.uid, {})["sign"] = sign
        if rejected:
            self._error(sess, "retired", "账号已退役")
            return
        self._persist()
        self._broadcast_roster()

    def _on_status_set(self, sess: Session, header: dict) -> None:
        """R68：在线状态（online/away/busy）。服务器权威持久，广播 roster 全员同步；
        与隐身为正交维度（隐身控制「是否出现在名单」，状态控制「出现在名单时的点色」）。"""
        if self._retire_error(sess):
            return
        status = str(header.get("status") or "").strip().lower()
        if status not in ("online", "away", "busy"):
            self._error(sess, "status", "状态无效")
            return
        with self.lock:
            rejected = self._uid_retired_locked(sess.uid)
            if not rejected:
                self.known.setdefault(sess.uid, {})["status"] = status
        if rejected:
            self._error(sess, "retired", "账号已退役")
            return
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
        if self._retire_error(sess):
            return
        try:
            target = int(header.get("uid"))
        except (TypeError, ValueError):
            self._error(sess, "remark", "目标用户无效")
            return
        remark = str(header.get("remark") or "").strip()[:24]
        with self.lock:
            rejected = (self._uid_retired_locked(sess.uid)
                        or self._uid_retired_locked(target))
            if not rejected:
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
        if rejected:
            self._error(sess, "retired", "账号已退役或目标已退役")
            return
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
        if self._retire_error(sess):
            return
        on = bool(header.get("on"))
        with self.lock:
            rejected = self._uid_retired_locked(sess.uid)
            if not rejected:
                self.known.setdefault(sess.uid, {})["invisible"] = on
        if rejected:
            self._error(sess, "retired", "账号已退役")
            return
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
            rejected = (self._retired_schema_invalid
                        or self._uid_retired_locked(uid))
            if not rejected:
                self.known.setdefault(uid, {})["invisible"] = on
                nick = (self.known.get(uid) or {}).get(
                    "nick") or self.nick_to_uid.get(uid) or f"用户{uid}"
        if rejected:
            self._error(sess, "retired", "账号已退役或目标已退役")
            return
        self._persist()
        self._broadcast_roster()
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
                # R25B：断线记录最后上线时间（known 保留 nick，供离线展示）。
                # 既有资料字段与 pwd 一并保留；Session/token 等运行对象不落盘。
                if not self._uid_retired_locked(sess.uid):
                    prev = self.known.get(sess.uid) or {}
                    self.known[sess.uid] = {"nick": sess.nick,
                                            "last_online": _now()}
                    for _k in _KNOWN_PROFILE_FIELDS:
                        if _k in prev:
                            self.known[sess.uid][_k] = copy.deepcopy(prev[_k])
                # R12fix：保留 nick→uid 映射（断线不删），同名重连复用同一 uid
                for tok, token_sess in list(self.web_tokens.items()):
                    if token_sess.uid == sess.uid:
                        del self.web_tokens[tok]
                if not self._uid_retired_locked(sess.uid):
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
                group = self.groups.get(gid)
                if group and group.get("members"):
                    continue
                self.groups.pop(gid, None)
                self.voice_rooms.pop(f"group:{gid}", None)   # R72：群解散连同语音房名册
        sess.closed = True
        self.audit.log(type="logout", uid=sess.uid, nick=sess.nick,
                       reason=reason, via=sess.type)
        for other, payload in self._drop_xfers_of(sess.uid):
            self._send_to(other, payload)
        self._broadcast_roster()
        if self.sessions.get(sess.uid) is None:          # 本 uid 已完全离线
            self._broadcast_offline_notice(sess.uid, sess.nick)
            self._drop_voice_rooms(sess.uid)             # R72：离线即退出所有语音房
        self._broadcast_group_list()
        self._disconnect_rooms_of(sess.uid)

    def _session_is_active(self, sess: Session) -> bool:
        """判断会话是否仍属于 Hub。

        已注销会话会被标记 closed；真实在线会话必须仍在该 uid 的在线集，
        或仍是 ``sessions`` 中的代表。没有任何 Hub 注册记录的对象一律拒绝，
        防止已断开的 TCP 读循环在 close_conn 生效前继续提交消息。
        """
        with self.lock:
            if getattr(sess, "closed", False):
                return False
            if self._retired_schema_invalid or self._uid_retired_locked(sess.uid):
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
            self._on_cloud_get(sess, header)                   # R37 云历史拉取
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
        if not self._attach(sess):           # 同账号多端并存；退役 fence 仍拒绝
            return False
        if pwd and not sess.is_admin:
            if not self._pwd_claim(sess.uid, pwd):
                return False
        with self.lock:
            if self._retired_schema_invalid or self._uid_retired_locked(sess.uid):
                return False
            return self._session_is_active(sess)

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
        if self._retire_error(sess):
            return
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
            with self.lock:
                target_retired = self._uid_retired_locked(to)
            if target_retired:
                self._error(sess, "retired", "目标账号已退役")
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
        rejected = False
        with self.lock:
            rejected = self._uid_retired_locked(sess.uid)
            target_uid = msg.get("to") if msg.get("channel") == "private" else None
            if target_uid is not None:
                rejected = rejected or self._uid_retired_locked(int(target_uid))
            if not rejected:
                msg = self.bus.publish(msg)
                if header.get("burn") and msg.get("channel") in ("public", "private", "group"):
                    recp = {u for u, _s in self._chan_recipients(
                        msg["channel"], msg.get("uid"), msg.get("to"))}
                    recp.discard(sess.uid)
                    self._burn[msg["seq"]] = {
                        "channel": msg["channel"], "uid": msg.get("uid"),
                        "to": msg.get("to"), "ts": msg.get("ts", _now()),
                        "pend": recp}
        if rejected:
            self._error(sess, "retired", "账号已退役或目标已退役")
            return
        self._route(msg)
        # R26D 链接预览：先投递 chat，再补发 preview（缓存命中时同步、否则后台抓取），
        # 保证客户端按 chat → preview 顺序收帧，本地历史/渲染一致。
        if text and not msg.get("preview"):
            m = _URL_RE.search(text)
            if m:
                self._maybe_fetch_preview(m.group(0).rstrip(".,;:!?）)]}"), msg)
        self.audit.log(type="chat", uid=sess.uid, nick=sess.nick, channel=channel,
                       to=msg.get("to"), seq=msg["seq"], length=len(text))
        self._persist()                              # R16：消息/阅后即焚落盘

    # ---------- R35 内置 Bots ----------
    def _bot_dispatch(self, sess: Session, header: dict, bot_uid: int) -> None:
        """R35 Bots：私聊发往 bot → 用户消息正常入历史/路由（发送方看到回显），
        再由 bot 解析命令并经 bot_say 回复；不走 offline 校验、无阅后即焚/话题。"""
        with self.lock:
            rejected = (self._uid_retired_locked(sess.uid)
                        or self._uid_retired_locked(bot_uid))
        if rejected:
            self._error(sess, "retired", "账号已退役或目标已退役")
            return
        bot = _bots.BOT_BY_UID.get(bot_uid)
        if bot is None:
            return
        text = (header.get("text") or "").strip()
        with self.lock:
            rejected = self._uid_retired_locked(sess.uid)
            if not rejected:
                msg = self.bus.publish({"t": "chat", "channel": "private", "uid": sess.uid,
                                        "nick": sess.nick, "ts": round(_now(), 3),
                                        "to": bot_uid, "text": text})
        if rejected:
            self._error(sess, "retired", "账号已退役")
            return
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
                self.bot_say(bot, sess.uid, r[0], kb=r[1],
                            owner_uid=sess.uid, source_kind="bot_command",
                            request_seq=msg.get("seq"))
            else:
                self.bot_say(bot, sess.uid, r, owner_uid=sess.uid,
                            source_kind="bot_command",
                            request_seq=msg.get("seq"))

    def bot_say(self, bot, to_uid: int, text: str, kb=None, *,
                owner_uid: int | None = None, source_kind: str | None = None,
                request_seq: int | None = None) -> bool:
        """R35：bot 以私聊身份回复（bus.publish 入历史 + 正常路由，
        对客户端就是一条普通 CHAT 私聊，无需感知 bot 协议）。
        R46：kb=inline 键盘（[[{t,c}],...]），仅是消息上的可选字段。
        RESOURCE：owner/target 在最终 bus C 复查；迟到 worker 不能越过
        t0 产生新的 BOT 作者历史。"""
        try:
            to_uid = int(to_uid)
            owner_uid = to_uid if owner_uid is None else int(owner_uid)
        except (TypeError, ValueError):
            return False
        msg = {"t": "chat", "channel": "private", "uid": bot.uid,
               "nick": bot.nick, "ts": round(_now(), 3),
               "to": to_uid, "text": text}
        if kb:                                        # R46：键盘随消息走（历史/快照天然保留）
            msg["kb"] = kb
        with self.lock:
            if (self._retired_schema_invalid
                    or self._uid_retired_locked(owner_uid)
                    or self._uid_retired_locked(to_uid)):
                return False
            msg = self.bus.publish(msg)
            self._bot_contexts[msg["seq"]] = {
                "owner_uid": owner_uid, "actor_uid": int(bot.uid),
                "target_uid": to_uid, "source_kind": source_kind,
                "request_seq": request_seq,
            }
        self._route(msg)
        try:
            self._persist()
        except Exception:
            pass
        return True

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
        cached = None
        cache_hit = False
        with self._preview_lock:
            hit = self._preview_cache.get(url)
            if hit is not None and now - hit[0] <= self.cfg.preview_ttl:
                cache_hit = True
                cached = hit[1]
            elif url in self._preview_inflight:
                return
            else:
                self._preview_inflight.add(url)
        # Cache callback must not run while _preview_lock is held: it may take
        # Hub/bus locks and route/persist outside those locks.
        if cache_hit:
            if cached is None:
                return
            self._preview_ready(msg["seq"], url, cached,
                                expected={"seq": msg.get("seq"),
                                          "url": url,
                                          "channel": msg.get("channel"),
                                          "uid": msg.get("uid"),
                                          "to": msg.get("to")})
            return
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
            self._preview_ready(seq, url, meta,
                                expected={"seq": seq, "url": url,
                                          "channel": channel, "uid": uid,
                                          "to": to})

    def _preview_ready(self, seq: int, url: str, meta: dict,
                       *, expected: dict | None = None) -> None:
        """最终 Hub→bus C：只补当前仍匹配的原消息并捕获事件副本。"""
        expected = expected if isinstance(expected, dict) else {}
        route_ev = None
        with self.lock:
            if self._retired_schema_invalid:
                return
            expected_uid = expected.get("uid")
            expected_to = expected.get("to")
            if expected_uid is not None and self._uid_retired_locked(int(expected_uid)):
                return
            if expected.get("channel") == "private" and expected_to is not None \
                    and self._uid_retired_locked(int(expected_to)):
                return
            with self.bus._lock:
                _key, msg = self.bus.find(seq)
                if msg is None or "preview" in msg or msg.get("deleted"):
                    return
                if expected.get("seq") not in (None, seq):
                    return
                if expected.get("url") not in (None, url):
                    return
                if expected_uid is not None and msg.get("uid") != expected_uid:
                    return
                if expected.get("channel") is not None \
                        and msg.get("channel") != expected.get("channel"):
                    return
                if expected_to is not None and msg.get("to") != expected_to:
                    return
                current_text = str(msg.get("text") or "")
                match = _URL_RE.search(current_text)
                current_url = (match.group(0).rstrip(".,;:!?）)]}")
                              if match else "")
                if current_url != url:
                    return
                msg["preview"] = copy.deepcopy(meta)
                ch, muid, mto = msg["channel"], msg["uid"], msg.get("to")
                route_ev = {"t": MsgType.PREVIEW.value, "seq": seq,
                            "preview": copy.deepcopy(meta),
                            "channel": ch, "uid": muid, "to": mto}
        if route_ev is None:
            return
        self._route(route_ev)
        try:
            self._persist()                          # 预览元数据入快照（无正文隐私风险）
        except Exception:
            pass

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
        # The find, permission/state check, mutation and event snapshot share
        # one short bus lock.  Routing/audit/persist stay outside it.
        with self.bus._lock:
            _key, msg = self.bus.find(seq)
            if msg is None:
                reason = ("expired", "消息已不在服务器历史中")
                route_ev = None
            elif msg.get("uid") != sess.uid:
                reason = ("forbid", "只能编辑自己的消息")
                route_ev = None
            elif isinstance(msg.get("poll"), dict):
                reason = ("poll", "投票消息不可编辑")
                route_ev = None
            elif msg.get("deleted"):
                reason = ("dup", "消息已撤回，无法编辑")
                route_ev = None
            elif msg.get("file") or msg.get("sticker") or msg.get("fp"):
                reason = ("forbid", "只能编辑文本消息")
                route_ev = None
            else:
                reason = None
                old_snap = {"ts": round(_now(), 3),
                            "text": str(msg.get("text") or "")[
                                :self.cfg.edit_history_len]}
                if isinstance(msg.get("rich"), list):
                    old_snap["rich"] = copy.deepcopy(msg["rich"])
                edits = msg.get("edits")
                if not isinstance(edits, list):
                    edits = []
                edits = list(edits)
                edits.append(old_snap)
                if len(edits) > self.cfg.edit_history_max:
                    del edits[:len(edits) - self.cfg.edit_history_max]
                msg["edits"] = edits
                msg["text"] = text
                r59 = self._san_rich(header.get("rich"), text)
                if r59:
                    msg["rich"] = r59
                else:
                    msg.pop("rich", None)
                msg["edited"] = True
                route_ev = {"t": MsgType.MSG_EDIT.value, "seq": seq,
                            "channel": msg["channel"], "uid": msg["uid"],
                            "to": msg.get("to"), "nick": msg["nick"],
                            "text": text, "edits": copy.deepcopy(edits)}
                if r59:
                    route_ev["rich"] = copy.deepcopy(r59)
        if reason is not None:
            self._error(sess, *reason)
            return
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
                reason = ("expired", "消息已不在服务器历史中")
                route_ev = None
            else:
                is_owner = msg.get("uid") == sess.uid
                allowed = is_owner or sess.is_admin
                if not allowed:
                    is_private = msg.get("channel") == "private"
                    is_peer = msg.get("to") == sess.uid
                    allowed = scope == "both" and is_private and is_peer
                if not allowed:
                    reason = ("forbid", "只能撤回自己的消息")
                    route_ev = None
                elif msg.get("deleted"):
                    reason = ("dup", "消息已撤回")
                    route_ev = None
                else:
                    reason = None
                    msg["deleted"] = True
                    msg["text"] = ""
                    route_ev = {"t": MsgType.MSG_DEL.value, "seq": seq,
                                "channel": msg["channel"], "uid": msg["uid"],
                                "to": msg.get("to"), "nick": msg["nick"]}
        if reason is not None:
            self._error(sess, *reason)
            return
        self._route(route_ev)
        self.audit.log(type="msg_del", uid=sess.uid, seq=seq, scope=scope)
        self._persist()                              # R16：撤回 tombstone 落盘

    # ---------- R53 服务器管理员（最高清理权限） ----------
    def _kick_targets(self, uid: int) -> list[Session]:
        """在同一锁内提交 UID 全端撤权，返回锁外通知/清理目标。

        ``sessions`` 只是代表端；撤权集合必须来自 ``_uid_clients``，并以
        代表端作异常兜底。closed 标记和 Web token 删除与集合抓取同属 t0，
        使 t0 后的 dispatch/token 解析立即失效；网络通知、连接关闭和
        unregister 留在锁外，且 unregister 的 UID 资源复查保护后续重登。
        """
        with self.lock:
            targets = list(self._uid_clients.get(uid, ()))
            representative = self.sessions.get(uid)
            if representative is not None and representative not in targets:
                targets.append(representative)
            if not targets:
                return []
            for target in targets:
                target.closed = True
            for token, token_sess in list(self.web_tokens.items()):
                if token_sess.uid == uid:
                    del self.web_tokens[token]
            return targets

    def _on_admin_kick(self, sess: Session, header: dict) -> None:
        """管理员踢目标 UID 当前全部端下线；允许之后重新认证。"""
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
        targets = self._kick_targets(uid)
        if not targets:
            self._error(sess, "offline", "该用户不在线")
            return
        nick = targets[0].nick
        for target in targets:
            try:
                target.send({"t": MsgType.ERROR.value, "code": "kicked",
                             "text": "已被管理员强制下线"})
            except Exception:
                pass
            self.unregister(target, "admin_kick")
            try:
                target.close_conn()
            except Exception:
                pass
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
        if (self.store is not None and self._persist_unresolved
                and not self._persist_inflight):
            # 查询路径先在 writer 边界内做一次只读 reconcile；不持 Hub
            # 锁等待磁盘，也不因查询隐式创建新 operation/写入。
            with self._persist_writer_lock:
                self._reconcile_persist_unknown()
        uid = self._resolve_uid_for_admin(target)
        if uid is None:
            return None
        with self.lock:
            retired = self.retired.get(uid)
            nick = ((retired or {}).get("nick")
                    or (self.known.get(uid) or {}).get("nick")
                    or self._append_nick_for_uid(uid, None))
            online = uid in self.sessions and uid not in self.retired
            groups = []
            for g in sorted(self.groups.values(), key=lambda x: x["gid"]):
                if uid in g["members"]:
                    role = "owner" if g["owner"] == uid else \
                        ("admin" if uid in g["admins"] else "member")
                    groups.append({"gid": g["gid"], "name": g["name"], "role": role})
            invisible = self._is_invisible(uid) if not retired else False
        payload = {"t": MsgType.ADMIN_USER_INFO.value, "uid": uid, "nick": nick,
                   "online": online, "groups": groups,
                   "invisible": invisible}  # R57：管理员可见隐身态
        retirement = self._retirement_payload(uid)
        if retirement is not None:
            payload["retirement"] = retirement
        resources = self._resource_summary(uid)
        if resources.get("operations"):
            payload["resources"] = resources
        return payload

    def _on_admin_user_get(self, sess: Session, header: dict) -> None:
        """系统管理员：查某人信息+所属全部群（uid 或已知昵称均可）。"""
        if not sess.is_admin:
            self._error(sess, "forbid", "仅系统管理员可执行")
            return
        expected = header.get("operation_id")
        if expected is not None:
            target_uid = self._resolve_uid_for_admin(header.get("uid"))
            if target_uid is None:
                self._error(sess, "uid", "目标 uid/昵称 无效")
                return
            actual = self._retirement_operation_id(target_uid)
            if not isinstance(expected, str) or expected != actual:
                self._error(sess, "operation_id", "退役操作号不匹配")
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

    def _retry_retirement_persistence(self, sess: Session, uid: int,
                                      nick: str, op_id: str) -> None:
        """Retry a failed same-op commit without repeating t0 cleanup."""
        pending = self._admin_user_payload(uid)
        if pending is not None:
            try:
                sess.send(pending)
            except Exception:
                pass
        ok = self._persist(force=True)
        with self.lock:
            op = self._retire_ops.setdefault(uid, {"operation_id": op_id})
            if op.get("status") == "pending":
                last = self._persist_last_result
                committed_sha = (last.sha256
                                 if isinstance(last, server_store_mod.SaveResult)
                                 and last.effect == "committed" else None)
                committed_len = (last.length
                                 if isinstance(last, server_store_mod.SaveResult)
                                 and last.effect == "committed" else None)
                op.update({"status": "confirmed" if ok else "failed",
                           "target_uid": uid, "target_nick": nick,
                           "origin": "written" if ok else None,
                           "content_sha256": committed_sha if ok else None,
                           "content_length": committed_len if ok else None,
                           "retryable": False if ok else True,
                           "failed_stage": None if ok else "store.save",
                           "error_code": None if ok else "persist_failed"})
            status = op.get("status")
        final = self._admin_user_payload(uid)
        if final is not None:
            try:
                sess.send(final)
            except Exception:
                pass
        with self.lock:
            status = (self._retire_ops.get(uid) or {}).get("status", status)
        if status == "confirmed":
            self._broadcast({"t": MsgType.CLEARED.value, "uid": uid})
            self._broadcast_system(f"系统管理员已退役用户 {nick}（UID 保留，不可重新认领）")
        self.audit.log(type="admin_user_del", uid=sess.uid, target=uid,
                       target_nick=nick, removed=0, dissolved=0,
                       operation_id=op_id, status=status)
        print(f"[admin][退役账号] {sess.nick} 重试 @{nick}(uid={uid})：状态={status}")

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
        uid = self._resolve_uid_for_admin(header.get("uid"))
        if uid is None:
            self._error(sess, "uid", "目标 uid/昵称 无效")
            return
        expected = header.get("operation_id")
        if expected is not None:
            actual = self._retirement_operation_id(uid)
            if not isinstance(expected, str) or expected != actual:
                self._error(sess, "operation_id", "退役操作号不匹配")
                return
        if uid == sess.uid:
            self._error(sess, "uid", "不能清除自己")
            return
        if self.store is None:
            self._error(sess, "store_required", "退役需要已启用的持久化 Store")
            return
        with self.lock:
            protected_bot = uid in _bots.BOT_BY_UID
            protected_admin = any(s.is_admin and s.uid == uid
                                  for s in self._snapshot_sessions())
        if protected_bot:
            self._error(sess, "uid", "系统机器人身份不可退役")
            return
        if protected_admin:
            self._error(sess, "uid", "当前认证管理员身份不可退役")
            return
        with self.lock:
            existing_rec = self.retired.get(uid)
            candidate_nick = ((existing_rec or {}).get("nick")
                              or (self.known.get(uid) or {}).get("nick")
                              or self.nick_to_uid.get(uid)
                              or f"用户{uid}")
            mapped_uid = self.nick_to_uid.get(candidate_nick)
        if mapped_uid not in (None, uid):
            self._error(sess, "uid", "昵称映射与目标 UID 冲突")
            return
        # unknown 的显式重试必须先做只读对账；读失败/坏结构/冲突时
        # 保持 unknown，不得先把运行态改成 pending 再尝试新写。
        if self._persist_unresolved and not self._persist_inflight:
            with self._persist_writer_lock:
                self._reconcile_persist_unknown()
            if self._persist_unresolved:
                payload = self._admin_user_payload(uid)
                if payload is not None:
                    try:
                        sess.send(payload)
                    except Exception:
                        pass
                return
        with self.lock:
            existing_op = self._retire_ops.get(uid)
            already_confirmed = bool(self.retired.get(uid)
                                     and existing_op
                                     and existing_op.get("status") == "confirmed")
        if already_confirmed:
            payload = self._admin_user_payload(uid)
            if payload is not None:
                try:
                    sess.send(payload)
                except Exception:
                    pass
            return
        if existing_op and self.retired.get(uid):
            existing_status = existing_op.get("status")
            if existing_status in ("pending", "unknown"):
                payload = self._admin_user_payload(uid)
                if payload is not None:
                    try:
                        sess.send(payload)
                    except Exception:
                        pass
                return
            if existing_status == "failed":
                retry_nick = self.retired[uid]["nick"]
                retry_op_id = self.retired[uid]["operation_id"]
                self._retire_ops[uid] = {
                    "status": "pending", "operation_id": retry_op_id,
                    "target_uid": uid, "target_nick": retry_nick,
                }
                self._retry_retirement_persistence(
                    sess, uid, retry_nick, retry_op_id)
                return

        # 生成/复用同 UID 的幂等操作号；t0 只做内存状态提交，所有通知、
        # 连接关闭、资源清理和持久化均留在屏障之外。
        with self.lock:
            old = self.retired.get(uid)
            if old is not None:
                nick = old["nick"]
                op_id = old["operation_id"]
            else:
                nick = candidate_nick
                mapped_uid = self.nick_to_uid.get(nick)
                if mapped_uid is None:
                    self.nick_to_uid[nick] = uid
                op_id = secrets.token_hex(16)
                self.retired[uid] = {"nick": nick, "retired_at": _now(),
                                     "operation_id": op_id}
            self._retire_ops[uid] = {
                "status": "pending", "operation_id": op_id,
                "target_uid": uid, "target_nick": nick,
            }
            targets = list(self._uid_clients.get(uid, ()))
            representative = self.sessions.get(uid)
            if representative is not None and representative not in targets:
                targets.append(representative)
            for token, token_sess in list(self.web_tokens.items()):
                if token_sess.uid == uid:
                    del self.web_tokens[token]
            for target in targets:
                target.closed = True
            self._uid_clients.pop(uid, None)
            self.sessions.pop(uid, None)
            self.known.pop(uid, None)
            self._drafts = {k: v for k, v in self._drafts.items()
                            if k[0] != uid}
            self.scheds.pop(uid, None)
            self.blocks.pop(uid, None)
            for key, readers in list(self.reads.items()):
                readers.pop(uid, None)
                if not readers:
                    self.reads.pop(key, None)
            self._offline_notice_records.pop(uid, None)
            self._typing_ts.pop(uid, None)
            self._nudge_ts.pop(uid, None)
            self._shake_ts.pop(uid, None)
            self.sticker_subs.pop(uid, None)
            self._resource_withdraw_owner_locked(uid)
            self._bot_reminder_cancel_owner_locked(uid)
            for bseq, burn in list(self._burn.items()):
                if burn.get("uid") == uid:
                    self._burn.pop(bseq, None)
            dissolved = self._admin_del_remove_groups(uid)
            removed = self.bus.clear_uid(uid)
            self._bot_contexts = {
                seq: ctx for seq, ctx in self._bot_contexts.items()
                if ctx.get("owner_uid") != uid and ctx.get("target_uid") != uid
            }
        for target in targets:
            try:
                target.send({"t": MsgType.ERROR.value, "code": "deleted",
                             "text": "你的账号已被管理员退役"})
            except Exception:
                pass
            try:
                target.close_conn()
            except Exception:
                pass
        for other, payload in self._drop_xfers_of(uid):
            self._send_to(other, payload)
        self._drop_voice_rooms(uid)
        self._disconnect_rooms_of(uid)
        self._broadcast_roster()
        self._broadcast_group_list()
        pending = self._admin_user_payload(uid)
        if pending is not None:
            try:
                sess.send(pending)
            except Exception:
                pass
        ok = self._persist(force=True)
        with self.lock:
            op = self._retire_ops.setdefault(uid, {"operation_id": op_id})
            # _commit_current_snapshot/_ack_commit 已按 typed effect 写入
            # pending/failed/unknown/confirmed；这里只补旧 hook 没有候选时
            # 的兼容状态，不能把 unknown 或 confirmed 降级成 failed。
            if op.get("status") == "pending":
                last = self._persist_last_result
                committed_sha = (last.sha256
                                 if isinstance(last, server_store_mod.SaveResult)
                                 and last.effect == "committed" else None)
                committed_len = (last.length
                                 if isinstance(last, server_store_mod.SaveResult)
                                 and last.effect == "committed" else None)
                op.update({"status": "confirmed" if ok else "failed",
                           "target_uid": uid, "target_nick": nick,
                           "origin": "written" if ok else None,
                           "content_sha256": committed_sha if ok else None,
                           "content_length": committed_len if ok else None,
                           "retryable": False if ok else True,
                           "failed_stage": None if ok else "store.save",
                           "error_code": None if ok else "persist_failed"})
            retire_status = op.get("status")
        final = self._admin_user_payload(uid)
        if final is not None:
            try:
                sess.send(final)
            except Exception:
                pass
        with self.lock:
            retire_status = (self._retire_ops.get(uid) or {}).get("status",
                             retire_status)
        if retire_status == "confirmed":
            self._broadcast({"t": MsgType.CLEARED.value, "uid": uid})
            self._broadcast_system(f"系统管理员已退役用户 {nick}（UID 保留，不可重新认领）")
        self.audit.log(type="admin_user_del", uid=sess.uid, target=uid,
                       target_nick=nick, removed=removed, dissolved=dissolved,
                       operation_id=op_id, status=retire_status)
        print(f"[admin][退役账号] {sess.nick} 处理 @{nick}(uid={uid})："
              f"清消息 {removed} 条，状态={retire_status}")

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
        if self._retire_error(sess):
            return
        try:
            seq = int(header.get("seq"))
        except (TypeError, ValueError):
            self._error(sess, "seq", "缺少 seq")
            return
        channel = header.get("channel") or "public"
        to = header.get("to")
        key = self._conv_key(channel, sess.uid, to)
        # 只在 Hub 锁内更新 reads，并收集锁外通知计划；发送、审计、
        # burn 清理与持久化都不得阻塞 Hub 锁。
        with self.lock:
            if self._uid_retired_locked(sess.uid):
                rejected = True
            else:
                rejected = False
                reads = self.reads.setdefault(key, {})
                if reads.get(sess.uid, 0) >= seq:
                    return
                reads[sess.uid] = seq
                read_targets = list(self._chan_recipients(channel, sess.uid, to))
                burn_ready = [
                    bseq for bseq, br in list(self._burn.items())
                    if br["channel"] == channel
                    and self._burn_same_convo(br, sess.uid, to)
                    and bseq <= seq and self._burn_ready(br, reads, bseq)
                ]
        if rejected:
            self._error(sess, "retired", "账号已退役")
            return
        payload = {"t": MsgType.READ.value, "channel": channel, "key": key,
                   "uid": sess.uid, "to": to, "seq": seq}
        for _u, target in read_targets:
            try:
                target.send(payload)
            except Exception:
                pass
        for bseq in burn_ready:
            self._burn_finish(bseq)
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
        """上传 opaque cloud bytes；C 与实际 replace/receipt 分离。"""
        blob = bytes(body or b"")
        if not blob or len(blob) > cloud_history_mod.CLOUD_BLOB_MAX:
            self._error(sess, "cloud",
                        f"备份大小无效（上限 {cloud_history_mod.CLOUD_BLOB_MAX} 字节）")
            return
        announced = header.get("size")
        if announced is not None and (
                isinstance(announced, bool) or not isinstance(announced, int)
                or announced != len(blob)):
            self._error(sess, "cloud", "备份长度与声明不一致")
            return
        op = header.get("resource_operation_id")
        identity = {"payload_sha256": hashlib.sha256(blob).hexdigest(),
                    "content_length": len(blob)}
        try:
            ctx = self._resource_begin(
                sess, "cloud", sess.uid, identity,
                resource_operation_id=op if op is not None else None)
            if ctx.get("status") == "confirmed":
                with self.lock:
                    with self._resource_lock:
                        ctx["visibility"] = self._resource_visibility_locked(ctx)
                        result = self._resource_public_result(ctx)
                if result.get("visibility") != "available":
                    raise _ResourceError("superseded", result,
                                         "旧 cloud 操作已被后续版本取代")
                try:
                    sess.send({"t": MsgType.CLOUD_DONE.value, "size": len(blob),
                               "ts": _now(), "resource": result})
                except Exception:
                    pass
                return
            if ctx.get("status") in ("unknown", "pending"):
                if ctx.get("status") == "unknown":
                    raise _ResourceError("resource_unknown",
                                         self._resource_public_result(ctx))
                if not self._resource_claim_executor(ctx):
                    raise _ResourceError("resource_pending",
                                         self._resource_public_result(ctx))
            result = self._resource_file_commit(ctx, blob)
            if result.get("status") != "confirmed":
                raise _ResourceError("resource_pending", result)
            try:
                sess.send({"t": MsgType.CLOUD_DONE.value, "size": len(blob),
                           "ts": _now(), "resource": result})
            except Exception:
                # A confirmed resource remains confirmed; response failure is
                # deliberately not folded back into the resource result.
                pass
            try:
                self.audit.log(type="cloud_put", uid=sess.uid, size=len(blob),
                               resource_operation_id=result.get(
                                   "resource_operation_id"))
            except Exception:
                pass
        except _ResourceError as exc:
            result = exc.result or {}
            self._error(sess, exc.code, "云资源未完成", resource=result)
        except (PermissionError, ValueError) as exc:
            self._error(sess, "cloud", str(exc))

    def _on_cloud_get(self, sess: Session, header: dict | None = None) -> None:
        """拉取当前已证 cloud bytes；resource query 只回有限结果。"""
        header = header if isinstance(header, dict) else {}
        query = header.get("resource_query") or header.get(
            "resource_operation_id")
        if query:
            explicit_owner = header.get("resource_owner_uid")
            if explicit_owner is not None:
                if not sess.is_admin or isinstance(explicit_owner, bool):
                    self._error(sess, "resource_forbid", "无资源查询权限")
                    return
                try:
                    explicit_owner = int(explicit_owner)
                except (TypeError, ValueError):
                    self._error(sess, "resource_unavailable", "资源 owner 无效")
                    return
            try:
                result = self._resource_query(
                    sess, str(query), explicit_owner=explicit_owner)
            except (LookupError, PermissionError, ValueError):
                self._error(sess, "resource_unavailable", "资源结果不可用")
                return
            if result.get("status") != "confirmed" \
                    or result.get("visibility") != "available":
                self._error(sess, "resource_pending", "资源结果尚未可读",
                            resource=result)
                return
            try:
                sess.send({"t": MsgType.CLOUD_DONE.value,
                           "size": result.get("length") or 0,
                           "resource": result})
            except Exception:
                pass
            return
        with self.lock:
            if self._retired_schema_invalid or self._uid_retired_locked(sess.uid):
                rec = None
            else:
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

    def _burn_finish(self, seq: int, br: dict | None = None) -> None:
        """锁内只提交 burn/bus 内存清理，通知和审计均在锁外。"""
        with self.lock:
            current = self._burn.pop(seq, None)
            if br is None:
                br = current
            if br is None:
                return
            _key, msg = self.bus.find(seq)
            if msg is not None:
                self.bus.discard(seq)
            recipients = self._chan_recipients(br["channel"], br["uid"], br["to"])
        payload = {"t": MsgType.MSG_DEL.value, "seq": seq,
                   "channel": br["channel"], "uid": br["uid"],
                   "to": br["to"], "burn": True}
        for _u, target in recipients:
            try:
                target.send(payload)
            except Exception:
                pass
        self.audit.log(type="burn", uid=br["uid"], seq=seq)
        self._persist()                              # R16：阅后即焚删除落盘

    def _burn_ttl_sweep(self) -> None:
        """阅后即焚兜底：长期没人读到也删除，防删不掉堆积（惰性触发）。"""
        now = _now()
        with self.lock:
            expired = [bseq for bseq, br in self._burn.items()
                       if now - br.get("ts", now) > self.cfg.burn_ttl]
        for bseq in expired:
            self._burn_finish(bseq)

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
        if self._retire_error(sess):
            return
        channel = header.get("channel") or "public"
        if channel not in ("public", "private", "group"):
            return
        text = str(header.get("text") or "").strip()[:4000]
        key = self._conv_key(channel, sess.uid, header.get("to"))
        rejected = False
        with self.lock:
            rejected = self._uid_retired_locked(sess.uid)
            if not rejected:
                if text:
                    self._drafts[(sess.uid, key)] = {"text": text, "ts": _now()}
                else:
                    self._drafts.pop((sess.uid, key), None)
        if rejected:
            self._error(sess, "retired", "账号已退役")
            return
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

    def _drop_voice_rooms_locked(self, uid: int) -> list:
        """锁内摘除 uid，返回待锁外广播的 (room, payload) 列表。"""
        if self._uid_clients.get(uid):
            return []
        notes = []
        for room, members in list(self.voice_rooms.items()):
            if uid not in members:
                continue
            del members[uid]
            if members:
                notes.append((room, self._room_state_payload(room)))
            else:
                self.voice_rooms.pop(room, None)
        return notes

    def _drop_voice_rooms(self, uid: int) -> None:
        """断线/完全离线：把该 uid 从所有语音房摘除。"""
        with self.lock:
            notes = self._drop_voice_rooms_locked(uid)
        for room, payload in notes:
            self._room_broadcast(room, payload)

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
            rec = self.xfers.get(fid)
            if not rec or rec.receiver_uid != sess.uid:
                return
            self.xfers.pop(fid, None)
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
            rec = self.xfers.get(fid)
            if not rec or rec.receiver_uid != sess.uid:
                return
            self.xfers.pop(fid, None)
            sender_uid = rec.sender_uid
        self._send_to(sender_uid, {"t": "file_verify", "file_id": fid, "ok": ok})
        self.audit.log(type="file_done", file_id=fid, ok=ok)

    def _on_file_cancel(self, sess: Session, header: dict) -> None:
        fid = str(header.get("file_id") or "")
        with self.lock:
            rec = self.xfers.get(fid)
            if not rec or sess.uid not in (rec.sender_uid, rec.receiver_uid):
                return
            self.xfers.pop(fid, None)
            other = (rec.receiver_uid if rec.sender_uid == sess.uid
                     else rec.sender_uid)
        self._send_to(other, {"t": "file_cancel", "file_id": fid,
                              "text": "传输已取消"})

    def _drop_xfers_of(self, uid: int) -> list:
        """会话下线时取消其相关传输；返回 [(other_uid, payload), ...] 待锁外通知"""
        notes = []
        with self.lock:
            # 旧 Session 的注销可能在锁外清理阶段遇到同 UID 重登；
            # 新端已加入时，旧端不得清理新端建立的传输。
            if self._uid_clients.get(uid):
                return notes
            for fid, rec in list(self.xfers.items()):
                if rec.sender_uid == uid or rec.receiver_uid == uid:
                    del self.xfers[fid]
                    other = (rec.receiver_uid if rec.sender_uid == uid
                             else rec.sender_uid)
                    if other != uid:
                        notes.append((other, {"t": "file_cancel", "file_id": fid,
                                              "text": "对方已离线，传输取消"}))
        return notes

    def _disconnect_rooms_of(self, uid: int) -> list:
        """仅在 uid 仍完全离线时执行游戏房间掉线清理。"""
        with self.lock:
            if self._uid_clients.get(uid):
                return []
            # Hub 锁保护 UID 离线复查；detail 只修改 RoomManager 内存。
            details = self.rooms.on_disconnect_detail(uid)
        affected = []
        for detail in details:
            room = detail.get("room")
            affected.append(detail.get("room_id"))
            if room is None or detail.get("closed"):
                continue
            events = list(detail.get("events") or ["有玩家离开房间"])
            if detail.get("ended"):
                self._finish_game(room, detail["ended"], events,
                                  expected_gs=detail.get("gs"),
                                  expected_round=detail.get("round_no"))
            else:
                self._send_room_state(room, events=events,
                                      expected_gs=detail.get("gs"),
                                      expected_round=detail.get("round_no"))
        if affected:
            self._broadcast_game_list()
        return affected

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

    def _game_state_payload(self, room, events=None, expected_gs=None,
                            expected_round=None, expected_status=None):
        """锁内构造公开/私密快照；调用方负责锁外发送。"""
        with self.rooms.lock:
            if (expected_gs is not None and room.gs is not expected_gs) \
                    or (expected_round is not None and room.round_no != expected_round) \
                    or (expected_status is not None and room.status != expected_status):
                return None
            payload = {"t": "game_state", "room_id": room.room_id,
                       "room": room.summary(), "state": None,
                       "events": list(events or []), "ts": round(_now(), 3)}
            priv_map = {}
            if room.gs is not None and room.status in (RoomStatus.PLAYING,
                                                        RoomStatus.ENDED):
                payload["state"] = room.gs.snapshot()
                if room.status == RoomStatus.PLAYING:
                    for u in room.members:
                        priv = room.gs.private(u)
                        if priv:
                            priv_map[u] = priv
            targets = list(room.members)
            # R49：uid→昵称映射（桌面端可忽略；网页端无 roster 全量，房间渲染需要）
            payload["nicks"] = {u: self._room_nick(u) for u in targets}
        return payload, priv_map, targets

    def _send_room_state(self, room, events=None, expected_gs=None,
                         expected_round=None, expected_status=None) -> bool:
        """给房间成员发当前状态：公开快照 + 各自私密投递 + 事件行。"""
        snapshot = self._game_state_payload(
            room, events, expected_gs=expected_gs,
            expected_round=expected_round, expected_status=expected_status)
        if snapshot is None:
            return False
        payload, priv_map, targets = snapshot
        with self.lock:
            sessions = [(u, s) for u in targets
                        for s in self._uid_clients.get(u, ())]
            if not sessions:
                sessions = [(u, self.sessions.get(u)) for u in targets
                            if self.sessions.get(u) is not None]
        for u, s in sessions:
            try:
                s.send(payload)
                if u in priv_map:
                    s.send({"t": "game_private", "room_id": room.room_id,
                            "state": priv_map[u]})
            except Exception:
                pass
        return True

    def _send_game_leave_ack(self, sess: Session, detail: dict,
                             events: list[str]) -> None:
        """单播离房确认；room 成员已不含 sess.uid，空房用 room=None。"""
        room = detail.get("room")
        if detail.get("closed") or room is None:
            payload = {"t": MsgType.GAME_STATE.value,
                       "room_id": detail.get("room_id"), "room": None,
                       "state": None, "events": list(events),
                       "ts": round(_now(), 3), "nicks": {}}
            with self.lock:
                sessions = list(self._uid_clients.get(sess.uid, ()))
                if not sessions and self.sessions.get(sess.uid) is not None:
                    sessions = [self.sessions[sess.uid]]
            for target in sessions:
                target.send(payload)
            return
        snapshot = self._game_state_payload(
            room, events, expected_gs=detail.get("gs"),
            expected_round=detail.get("round_no"))
        if snapshot is None:
            payload = {"t": MsgType.GAME_STATE.value,
                       "room_id": detail.get("room_id"), "room": None,
                       "state": None, "events": list(events),
                       "ts": round(_now(), 3), "nicks": {}}
            priv_map = {}
        else:
            payload, priv_map, _targets = snapshot
        with self.lock:
            sessions = list(self._uid_clients.get(sess.uid, ()))
            if not sessions and self.sessions.get(sess.uid) is not None:
                sessions = [self.sessions[sess.uid]]
        for target in sessions:
            try:
                target.send(payload)
                if target.uid in priv_map:
                    target.send({"t": MsgType.GAME_PRIVATE.value,
                                 "room_id": room.room_id,
                                 "state": priv_map[target.uid]})
            except Exception:
                pass

    def _finish_game(self, room, ended: dict, events=None,
                     expected_gs=None, expected_round=None) -> bool:
        """对局结算：置 ENDED 广播，3 秒后自动回大厅（保留玩家与跨轮分数）"""
        with self.rooms.lock:
            if self.rooms.rooms.get(room.room_id) is not room \
                    or room.status != RoomStatus.PLAYING \
                    or (expected_gs is not None and room.gs is not expected_gs) \
                    or (expected_round is not None and room.round_no != expected_round):
                return False
            captured_gs = room.gs
            captured_round = room.round_no
            room.status = RoomStatus.ENDED
        self.audit.log(type="game_end", room_id=room.room_id,
                       game=room.game_name, detail=ended.get("detail", ""))
        lines = list(events or [])
        lines.append(f"🏁 本局结束：{ended.get('detail', '')}")
        self._send_room_state(room, events=lines, expected_gs=captured_gs,
                              expected_round=captured_round,
                              expected_status=RoomStatus.ENDED)
        self._broadcast_game_list()

        def _reset():
            with self.rooms.lock:
                if self.rooms.rooms.get(room.room_id) is not room \
                        or room.status != RoomStatus.ENDED \
                        or room.gs is not captured_gs \
                        or room.round_no != captured_round:
                    return
                room.status = RoomStatus.CREATED
                room.gs = None
            self._broadcast_game_list()
            self._send_room_state(room, events=["对局已结束，可再次开始"],
                                  expected_round=captured_round,
                                  expected_status=RoomStatus.CREATED)

        timer = threading.Timer(3.0, _reset)
        timer.daemon = True
        timer.start()
        return True

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
        detail = self.rooms.leave_detail(sess.uid, room_id)
        room = detail.get("room")
        events = list(detail.get("events") or [])
        if not events:
            events = [f"{sess.nick} 离开房间"]
        self.audit.log(type="game_leave", uid=sess.uid, nick=sess.nick,
                       room_id=room_id)
        if room is not None and detail.get("ended") and not detail.get("closed"):
            self._finish_game(room, detail["ended"], events,
                              expected_gs=detail.get("gs"),
                              expected_round=detail.get("round_no"))
        elif room is not None and not detail.get("closed"):
            self._send_room_state(room, events=events,
                                  expected_gs=detail.get("gs"),
                                  expected_round=detail.get("round_no"))
        self._broadcast_game_list()
        self._send_game_leave_ack(sess, detail, events)

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
        with self.rooms.lock:
            captured_room = self.rooms.room_for(room_id)
            captured_gs = (captured_room.gs if captured_room is not None else None)
            captured_round = (captured_room.round_no
                              if captured_room is not None else None)
        try:
            lines = self.rooms.handle_action(sess.uid, room_id, action)
        except GameRuleError as exc:
            self._error(sess, "game", str(exc))
            return
        room = self.rooms.room_for(room_id)
        if not room:
            return
        with self.rooms.lock:
            if (self.rooms.rooms.get(room_id) is not captured_room
                    or room.gs is not captured_gs
                    or room.round_no != captured_round
                    or room.status != RoomStatus.PLAYING):
                return
        self.audit.log(type="game_action", uid=sess.uid, nick=sess.nick,
                       room_id=room_id, action=str(action)[:120])
        self._send_room_state(room, events=list(lines),
                              expected_gs=captured_gs,
                              expected_round=captured_round,
                              expected_status=RoomStatus.PLAYING)
        if room.status == RoomStatus.PLAYING and room.gs is not None:
            ended = captured_gs.ended() if captured_gs is not None else None
            if ended:
                self._finish_game(room, ended, expected_gs=captured_gs,
                                  expected_round=captured_round)

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


def _lan_ip(bind_host: str | None = None) -> str:
    """探测本机局域网出口 IP（UDP connect 仅查路由表不发包）。

    用于启动提示：0.0.0.0 只是监听通配符，浏览器访问不了，
    必须打印 127.0.0.1 / 局域网 IP 才能直接点。完全断网回落 127.0.0.1。

    REL-01：显式 loopback（以及其它显式 bind 地址）直接回显，不做
    8.8.8.8 路由探测。只有历史默认的 wildcard bind 需要推导一个可访问
    的提示地址。
    """
    host = str(bind_host or "0.0.0.0").strip()
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        parsed = None
    if parsed is not None and (parsed.is_loopback or not parsed.is_unspecified):
        return host
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
    bind_host = getattr(hub.cfg, "bind_host", "0.0.0.0")
    srv.bind((bind_host, port))
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

    if getattr(hub.cfg, "discovery_enabled", True):
        try:
            import discovery
            from config import APP_NAME
            _bcast = discovery.DiscoveryBroadcaster(hub.cfg, name=APP_NAME, stop=stop)
            _bcast.start()
        except Exception:
            pass          # UDP 广播失败不影响 TCP 主服务

    scheme = "https" if web_https else "http"
    tip = "（自签证书，浏览器首次访问点「继续前往」即可）" if web_https else ""
    lan = _lan_ip(bind_host)
    print(f"[服务器] TCP 监听 {bind_host}:{port}，网页端 {scheme}://{lan}:{hub.cfg.web_port}/{tip}")
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
            rooms = [(room, room.gs, room.round_no)
                     for room in hub.rooms.rooms.values()
                     if room.status == RoomStatus.PLAYING and room.gs is not None]
        for room, captured_gs, captured_round in rooms:
            if captured_gs is not None:
                try:
                    lines = captured_gs.tick(now)
                    with hub.rooms.lock:
                        current = (hub.rooms.rooms.get(room.room_id) is room
                                   and room.gs is captured_gs
                                   and room.round_no == captured_round
                                   and room.status == RoomStatus.PLAYING)
                    if lines and current:
                        hub._send_room_state(room, events=list(lines),
                                             expected_gs=captured_gs,
                                             expected_round=captured_round,
                                             expected_status=RoomStatus.PLAYING)
                    ended = captured_gs.ended()
                    if ended:
                        hub._finish_game(room, ended,
                                         expected_gs=captured_gs,
                                         expected_round=captured_round)
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
    if CFG.tray_enabled:
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
