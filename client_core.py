# -*- coding: utf-8 -*-
"""客户端纯逻辑核心（零 GUI，超时/目录可注入供测试与 GUI 复用）：

- 连接 + crypto 握手 + hello 登录（welcome 带回名单/群列表/表情包/服务器历史）
- 心跳：独立线程按 heartbeat_interval 发 ping，heartbeat_timeout 内无 pong 判死重连
- 断线自动重连：指数退避（reconnect_base→reconnect_max），重连后自动重入已加群
- 聊天：公聊 / 私聊 / 群聊 / 表情包（sticker 字段 + 短代码原样透传）
- 本地历史：按频道内存环形 + JSONL 落盘（客户端本地长期保留，服务器仅内存短留）
- 所有事件推入 self.events（queue.Queue），并回调 on_event（GUI/测试用）

线程模型：
    _reconnector  连接/重连主循环（阻塞在 _connect_once 的 reader.join 内）
    _reader       读帧分发线程（阻塞式读）
    _heartbeat    心跳线程（空闲发 ping；超时判死主动关 socket 触发重连）
"""
import json
import hashlib
import os
import queue
import re
import socket
import sys
import threading
import time
from collections import defaultdict, deque

import cloud_history
from cloud_history import (CloudHistoryError, CLOUD_BLOB_MAX, pack as _cloud_pack,
                           unpack as _cloud_unpack)
from config import CFG
from crypto import HandshakeError, client_handshake
from crypto_e2ee import E2EEEngine, E2EEError, e2ee_channel_key
from file_client import FileManager
from voice_call import CallManager        # R38 1v1 语音对讲
from voice_room import VoiceRoom          # R72 多人语音房
from protocol import MsgType, ProtocolError

_CACHE_KEEP_FILES = 300                   # 语音/贴纸磁盘缓存保留文件数上限（低危配额）

_FILE_TYPES = frozenset({
    MsgType.FILE_OFFER.value, MsgType.FILE_ACCEPT.value, MsgType.FILE_REJECT.value,
    MsgType.FILE_LISTEN.value, MsgType.FILE_DIRECT.value,
    MsgType.FILE_DIRECT_OK.value, MsgType.FILE_DATA.value,
    MsgType.FILE_CHUNK_ACK.value, MsgType.FILE_VERIFY.value,
    MsgType.FILE_PROGRESS.value, MsgType.FILE_CANCEL.value,
})

_CALL_TYPES = frozenset({                 # R38 语音对讲信令（转交通话管理器）
    MsgType.CALL_RING.value, MsgType.CALL_ACCEPT.value, MsgType.CALL_REJECT.value,
    MsgType.CALL_READY.value, MsgType.CALL_END.value,
})


def _now() -> float:
    return time.time()


def _channel_key(channel: str, my_uid: int, to=None) -> str:
    """本地历史频道键：public / private:低uid:高uid / e2ee:低uid:高uid / group:gid"""
    if channel == "public":
        return "public"
    if channel == "private":
        a, b = sorted((int(my_uid), int(to)))
        return f"private:{a}:{b}"
    if channel == "e2ee":
        return e2ee_channel_key(my_uid, int(to))
    return f"group:{int(to)}"


def _default_history_dir() -> str:
    """本地历史目录：exe 运行时取可写用户目录，脚本运行时取项目目录"""
    if getattr(sys, "frozen", False):
        base = os.path.join(os.path.expanduser("~"), "moeyu_helper")
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "history")


def _nick_safe(nick: str) -> str:
    """R35 昵称 → 子目录名安全串（保留中文，替换路径非法字符）"""
    s = re.sub(r'[\\/:*?"<>|]', "_", (nick or "").strip())[:32]
    return s or "default"


def _nick_history_dir(nick: str) -> str:
    """R35 多档案：history/<nick>/ 子目录（历史/语音缓存/自定义贴纸随账号隔离）。

    首启迁移：旧版顶层历史（*.jsonl + voice/ + stickers_custom/）认领进
    首个登录的账号子目录，老用户无感；新账号从空档案开始。"""
    base = _default_history_dir()
    d = os.path.join(base, _nick_safe(nick))
    if os.path.isdir(d):
        return d
    os.makedirs(d, exist_ok=True)
    try:
        for name in os.listdir(base):
            if name.endswith(".jsonl") or name in ("voice", "stickers_custom"):
                try:
                    os.rename(os.path.join(base, name), os.path.join(d, name))
                except OSError:
                    pass
    except OSError:
        pass
    return d


class LocalHistory:
    """频道历史：内存环形（新会话）+ JSONL 落盘（重启恢复，本地长期保留）"""

    def __init__(self, base_dir: str, max_in_mem: int = CFG.chat_history_max) -> None:
        self._dir = os.path.abspath(base_dir)
        self._max = max_in_mem
        self._lock = threading.RLock()
        self._mem = defaultdict(lambda: deque(maxlen=max_in_mem))
        self._fh: dict = {}               # key -> 持久写句柄（避免每消息 open/close）
        self._writes = 0
        self._index: dict = {}            # R39C: key -> [行起始字节偏移,...]（懒加载行号索引）
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, key: str) -> str:
        safe = key.replace(":", "_").replace("/", "_").replace("\\", "_")
        return os.path.join(self._dir, safe + ".jsonl")

    def add(self, key: str, msg: dict) -> None:
        with self._lock:
            self._mem[key].append(msg)
            fh = self._fh.get(key)
            if fh is None or fh.closed:
                fh = open(self._path(key), "a", encoding="utf-8")
                self._fh[key] = fh
            if key in self._index:            # R39C：索引已建则增量记新行偏移
                try:
                    self._index[key].append(fh.tell())
                except (OSError, ValueError):
                    self._index.pop(key, None)   # tell 失败 → 下次整扫重建
            fh.write(json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._writes += 1
            if self._writes % 200 == 0:
                self._flush()

    def _flush(self) -> None:
        for fh in self._fh.values():
            if not fh.closed:
                try:
                    fh.flush()
                except OSError:
                    pass

    def close(self) -> None:
        """冲刷并关闭全部句柄（进程退出/会话关闭时调用）。"""
        with self._lock:
            self._flush()
            for fh in self._fh.values():
                try:
                    fh.close()
                except OSError:
                    pass
            self._fh.clear()

    def load(self, key: str) -> list:
        """内存环形快照（本次会话收到的消息）"""
        with self._lock:
            return list(self._mem[key])

    def thread_msgs(self, key: str, root_seq: int) -> list:
        """R34 群内话题：本地历史中某根消息的全部回复（thread_root==root_seq）。

        与服务器环形过滤同一语义；话题回复与主列表同频道落盘（JSONL 混存），
        重启后话题窗口靠此恢复，无需服务器重放。"""
        with self._lock:
            return [m for m in self._mem[key] if m.get("thread_root") == root_seq]

    def recent_global(self, max_n: int = 12) -> list:
        """R15：跨会话全局最近 max_n 条（按 ts 降序），供全透明黑字模式字幕。
        纯内存遍历 _mem 各频道尾部，返回原始消息 dict，未达到 max_n 则有多少返回多少。"""
        with self._lock:
            got = []
            for key, dq in list(self._mem.items()):
                for m in dq:
                    ts = m.get("ts", 0)
                    if isinstance(ts, str):
                        try:
                            ts = float(ts)
                        except (TypeError, ValueError):
                            ts = 0
                    got.append((ts, m))
            got.sort(key=lambda t: t[0], reverse=True)
            return [m for _, m in got[:max_n]]

    def load_disk(self, key: str) -> list:
        """从磁盘重读（模拟重启后恢复历史）"""
        self._flush()                    # 先冲刷句柄缓冲，读到完整数据
        path = self._path(key)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return [json.loads(line) for line in f if line.strip()]
        except (FileNotFoundError, ValueError):
            return []

    # ---------- R39C 本地历史分段懒加载 ----------

    def _ensure_index(self, key: str) -> list:
        """行号索引（key → 每行起始字节偏移）。首读整扫一遍，之后 O(页) 随机读；
        内存占用 = 8B/行，换翻页零整扫。任何整段重写路径都会先作废索引。"""
        offs = self._index.get(key)
        if offs is not None:
            return offs
        self._flush()
        offs = []
        path = self._path(key)
        try:
            with open(path, "rb") as f:
                pos = 0
                for line in f:
                    offs.append(pos)
                    pos += len(line)
        except OSError:
            offs = []
        self._index[key] = offs
        return offs

    @staticmethod
    def _seq_of(m: dict):
        """消息 seq（容错：旧数据可能是字符串/缺失 → None 由调用方过滤）。"""
        try:
            return int(m.get("seq"))
        except (TypeError, ValueError):
            return None

    def _read_page_at(self, f, key: str, i: int, offs: list) -> dict | None:
        """按索引偏移从已打开句柄读第 i 行并 JSON 解析（损坏行返回 None 不中断）。"""
        start = offs[i]
        end = offs[i + 1] if i + 1 < len(offs) else None
        try:
            f.seek(start)
            raw = f.read(end - start) if end is not None else f.read()
            m = json.loads(raw.decode("utf-8"))
            return m if isinstance(m, dict) else None
        except (OSError, ValueError, UnicodeDecodeError):
            return None

    def page_before(self, key: str, before_seq, n: int = 100) -> list:
        """取 seq<before_seq 的更旧一页（升序返回，最多 n 条，按 seq 去重）。

        从文件尾倒着扫（新→旧），收满 n 条即停——翻旧消息只读 O(页) 行。
        重连回放可能在文件尾留下重复行：倒扫首见即最新内容，天然取新舍旧。
        before_seq 可传 float("inf")（= page_tail 语义，取最新一页）。
        """
        with self._lock:
            self._flush()                     # 追加句柄有缓冲：读前先落盘，防漏最新行
            offs = self._ensure_index(key)
            if not offs:
                return []
            out: list = []
            seen: set = set()
            try:
                limit = float(before_seq)
            except (TypeError, ValueError):
                return []
            try:
                f = open(self._path(key), "rb")
            except OSError:
                return []
            with f:
                for i in range(len(offs) - 1, -1, -1):
                    if len(out) >= n:
                        break
                    m = self._read_page_at(f, key, i, offs)
                    if m is None:
                        continue
                    s = self._seq_of(m)
                    if s is None or s >= limit or s in seen:
                        continue
                    seen.add(s)
                    out.append(m)
            out.reverse()                     # 倒扫收集 → 升序返回
            return out

    def page_tail(self, key: str, n: int = 100) -> list:
        """取最新一页（升序，最多 n 条，按 seq 去重）——会话首开装载用。"""
        return self.page_before(key, float("inf"), n)

    def page_after(self, key: str, after_seq, n: int = 100) -> list:
        """取 seq>after_seq 的更新一页（升序，最多 n 条）——正向窗口用。

        从文件头正向扫，收满 n 条即停（定位旧窗口后的下方向翻页）。
        """
        with self._lock:
            self._flush()                     # 同 page_before：读前先落盘
            offs = self._ensure_index(key)
            if not offs:
                return []
            out: list = []
            seen: set = set()
            try:
                limit = float(after_seq)
            except (TypeError, ValueError):
                return []
            try:
                f = open(self._path(key), "rb")
            except OSError:
                return []
            with f:
                for i in range(len(offs)):
                    if len(out) >= n:
                        break
                    m = self._read_page_at(f, key, i, offs)
                    if m is None:
                        continue
                    s = self._seq_of(m)
                    if s is None or s <= limit or s in seen:
                        continue
                    seen.add(s)
                    out.append(m)
            return out

    def drop(self, key: str) -> None:
        """删除某个会话的本地记录（内存环形 + JSONL 文件；右键菜单「删除记录」）"""
        with self._lock:
            self._mem[key].clear()
            fh = self._fh.pop(key, None)
            if fh is not None and not fh.closed:
                try:
                    fh.close()
                except OSError:
                    pass
            path = self._path(key)
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            self._index.pop(key, None)        # R39C：文件没了，索引作废

    def _invalidate_index(self, key: str) -> None:
        """R39C：JSONL 被整段重写（编辑/撤回/清理/云合并）后行偏移作废。"""
        self._index.pop(key, None)

    def _rewrite(self, key: str, seq: int) -> bool:
        """按 seq 定位内存环形里的消息并整段重写 JSONL（C3 编辑/撤回落盘）。"""
        with self._lock:
            found = any(m.get("seq") == seq for m in self._mem[key])
            if not found:
                return False
            # 关闭旧追加句柄（其文件偏移已失效），重写后下次 add 会重新打开
            fh = self._fh.pop(key, None)
            if fh is not None and not fh.closed:
                try:
                    fh.flush()
                    fh.close()
                except OSError:
                    pass
            path = self._path(key)
            with open(path, "w", encoding="utf-8") as f:
                for m in self._mem[key]:
                    f.write(json.dumps(m, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._invalidate_index(key)       # R39C：重写后行偏移全变
            return True

    def edit_msg_local(self, key: str, seq: int, new_text: str,
                       rich=None, edits=None) -> bool:
        """本地编辑存储中的一条消息（文本+已编辑标记）。
        R70B：edits 为服务器下发的历史版本快照，一并落盘供查看。"""
        with self._lock:
            for m in self._mem[key]:
                if m.get("seq") == seq and not m.get("deleted"):
                    m["text"] = new_text
                    m["edited"] = True
                    m.pop("sticker", None)
                    if rich is not None:
                        m["rich"] = rich
                    else:
                        m.pop("rich", None)
                    if isinstance(edits, list) and edits:
                        m["edits"] = edits
                    return self._rewrite(key, seq)
            return False

    def del_msg_local(self, key: str, seq: int) -> bool:
        """本地撤回存储中的一条消息（留墓碑）。"""
        with self._lock:
            for m in self._mem[key]:
                if m.get("seq") == seq and not m.get("deleted"):
                    m["deleted"] = True
                    m["text"] = ""
                    return self._rewrite(key, seq)
            return False

    def reactions_local(self, key: str, seq: int, reactions: dict) -> bool:
        """本地更新某消息的表情回应（reactions={emoji:{uid:ts}}）并落盘。"""
        with self._lock:
            for m in self._mem[key]:
                if m.get("seq") == seq:
                    if reactions:
                        m["reactions"] = reactions
                    else:
                        m.pop("reactions", None)
                    return self._rewrite(key, seq)
            return False

    def poll_state_local(self, key: str, seq: int, payload: dict) -> bool:
        """R26A/R70C 本地更新某投票消息的票数并落盘。

        payload 为服务器 poll_state：R70C 新形状走 `poll["state"]`
        （counts/total/mine/correct/end，兼容匿名只回本人 mine）；
        旧形状（含 votes）仍按 `poll["votes"]` 落盘，保证历史重放兼容。"""
        with self._lock:
            for m in self._mem[key]:
                if m.get("seq") == seq and isinstance(m.get("poll"), dict):
                    if isinstance(payload, dict) and ("counts" in payload
                                                      or "mine" in payload
                                                      or "correct" in payload):
                        st = m["poll"].setdefault("state", {})
                        for k in ("counts", "total", "mine", "correct", "end"):
                            if k in payload:
                                st[k] = payload[k]
                        if "votes" in payload:       # 非匿名兼容：同步旧形状票数
                            m["poll"]["votes"] = payload["votes"] or {}
                    else:
                        m["poll"]["votes"] = (payload.get("votes")
                                              if isinstance(payload, dict)
                                              else (payload or {}))
                    return self._rewrite(key, seq)
            return False

    def preview_local(self, key: str, seq: int, preview: dict) -> bool:
        """R26D 本地为某消息附链接预览卡片（preview={title,url,...}）并落盘。"""
        with self._lock:
            for m in self._mem[key]:
                if m.get("seq") == seq:
                    m["preview"] = preview
                    return self._rewrite(key, seq)
            return False

    def purge_local(self, key: str, until_seq: int) -> int:
        """R14 会话清理：丢弃该频道 seq<=until_seq 的消息并落盘；返回删除条数。"""
        with self._lock:
            old = list(self._mem[key])
            keep = [m for m in old if m.get("seq", 0) > until_seq]
            removed = len(old) - len(keep)
            if removed <= 0:
                return 0
            self._mem[key] = deque(keep, maxlen=self._mem[key].maxlen)
            fh = self._fh.pop(key, None)
            if fh is not None and not fh.closed:
                try:
                    fh.flush()
                    fh.close()
                except OSError:
                    pass
            with open(self._path(key), "w", encoding="utf-8") as f:
                for m in keep:
                    f.write(json.dumps(m, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._invalidate_index(key)       # R39C：清理重写后行偏移全变
            return removed

    def clear_local_all(self) -> int:
        """R53 管理员清空全部历史：清空内存缓冲并把全部频道 JSONL 文件清空；
        返回删除条数。频道文件保留（空文件），避免历史目录扫描逻辑误判。"""
        with self._lock:
            total = sum(len(dq) for dq in self._mem.values())
            self._mem.clear()
            for fh in self._fh.values():
                if not fh.closed:
                    try:
                        fh.close()
                    except OSError:
                        pass
            self._fh.clear()
            self._index.clear()
            try:
                names = [n for n in os.listdir(self._dir) if n.endswith(".jsonl")]
            except OSError:
                names = []
            for name in names:
                try:
                    with open(os.path.join(self._dir, name), "w", encoding="utf-8"):
                        pass
                except OSError:
                    pass
            return total

    def clear_local_uid(self, uid: int) -> int:
        """R53 管理员清空指定 uid 的全部消息（跨全部频道，内存+落盘同步）；
        返回删除条数。"""
        with self._lock:
            removed = 0
            for key, dq in list(self._mem.items()):
                keep = deque((m for m in dq if m.get("uid") != uid),
                             maxlen=dq.maxlen)
                n = len(dq) - len(keep)
                if n <= 0:
                    continue
                removed += n
                self._mem[key] = keep
                fh = self._fh.pop(key, None)
                if fh is not None and not fh.closed:
                    try:
                        fh.flush()
                        fh.close()
                    except OSError:
                        pass
                with open(self._path(key), "w", encoding="utf-8") as f:
                    for m in keep:
                        f.write(json.dumps(m, ensure_ascii=False,
                                           separators=(",", ":")) + "\n")
                self._invalidate_index(key)
            return removed

    # ---------- R37 加密云历史：导出 / 导入 ----------

    def export_all(self) -> dict:
        """全量本地历史 → {频道键: [msg, ...]}（内存 ∪ 磁盘，指纹去重）。"""
        import glob as _glob
        with self._lock:
            self._flush()
            out: dict = {}
            for key in list(self._mem.keys()):          # 本次会话活跃频道
                msgs = self.load_disk(key)              # 磁盘全量（含更早消息）
                seen = {cloud_history.fingerprint(m) for m in msgs}
                for m in self._mem[key]:                # 补内存环形（去重合并）
                    f = cloud_history.fingerprint(m)
                    if f not in seen:
                        msgs.append(m)
                        seen.add(f)
                out[key] = msgs
            for path in _glob.glob(os.path.join(self._dir, "*.jsonl")):
                fn = os.path.basename(path)[:-len(".jsonl")]
                key = self._key_from_filename(fn)
                if key is None or key in out:
                    continue
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        msgs = [json.loads(line) for line in f if line.strip()]
                except (OSError, ValueError):
                    continue
                if msgs:
                    out[key] = msgs
            return out

    def merge_in(self, channels: dict) -> int:
        """云备份合并进本地（按频道指纹去重，仅追加缺失）；返回新增条数。"""
        added = 0
        with self._lock:
            for key, incoming in (channels or {}).items():
                if not isinstance(incoming, list):
                    continue
                incoming = [m for m in incoming if isinstance(m, dict)]
                if not incoming:
                    continue
                existing = self.load_disk(key)
                before = len(existing)
                cloud_history.merge(existing, incoming)  # 就地追加缺失
                if len(existing) == before:
                    continue
                added += len(existing) - before
                fh = self._fh.pop(key, None)            # 旧句柄偏移失效，先关
                if fh is not None and not fh.closed:
                    try:
                        fh.flush()
                        fh.close()
                    except OSError:
                        pass
                with open(self._path(key), "w", encoding="utf-8") as f:
                    for m in existing:
                        f.write(json.dumps(m, ensure_ascii=False,
                                           separators=(",", ":")) + "\n")
                self._mem[key] = deque(existing, maxlen=self._max)
                self._invalidate_index(key)       # R39C：云合并重写后行偏移全变
        return added

    @staticmethod
    def _key_from_filename(fn: str) -> str | None:
        """安全文件名 → 频道键（_path 的逆映射；键形态仅四种，可精确还原）。"""
        if not fn:
            return None
        if "_" not in fn:
            return fn                                   # public
        head, tail = fn.split("_", 1)
        if head in ("e2ee", "private"):
            return head + ":" + tail.replace("_", ":")
        if head == "group":
            return "group:" + tail.split("_")[0]
        return None                                     # 未知形态：跳过


class ClientCore:
    """局域网摸鱼助手 · 客户端逻辑核心（进程内单实例）"""

    def __init__(self, host: str = "127.0.0.1", port: int | None = None, nick: str = "",
                 pwd: str = "",
                 history_dir: str | None = None,
                 heartbeat_interval: float | None = None,
                 heartbeat_timeout: float | None = None,
                 reconnect_base: float | None = None,
                 reconnect_max: float | None = None,
                 on_event=None) -> None:
        self.host = host
        self.port = port if port is not None else CFG.tcp_port
        self.nick = nick
        self._pwd = str(pwd or "")          # R47-B：昵称密码（内存态，不落盘）
        self.uid: int | None = None
        self.state = "idle"                 # idle|connecting|online|offline
        self.roster: dict = {}              # uid -> {uid,nick,type}
        self.groups: dict = {}              # gid -> {gid,name,owner,admins,member_count}
        self.group_members: dict = {}       # gid -> [{uid,nick},...]
        self.group_admins: dict = {}        # gid -> set(uid)（管理权限）
        self.group_mutes: dict = {}         # gid -> {uid: until_ts}（禁言截止）
        self.group_announces: dict = {}     # gid -> str（群公告文本，空=无）
        self.group_ann_modes: dict = {}     # C9① gid -> bool（仅公告说话模式）
        self.group_slows: dict = {}         # R70D gid -> int（群慢速档位秒数，0=关闭）
        self.group_invites: dict = {}       # R28 gid -> str（服务器单播回的邀请码）
        self.stickers: list = []
        self.sticker_subs: list = []        # R35 已订阅表情包（pack_id 列表，welcome/回帧带回）
        self.sticker_shop: list = []        # R35 商店目录缓存（packs，拉取后更新）
        self.reads: dict = {}           # convo_key -> {uid: max_read_seq}（已读回执）
        self.pins: dict = {}            # convo_key -> {seq,nick,text,sticker,ts}（消息置顶快照）
        self.typing: dict = {}          # R25A convo_key -> {uid: {"nick":str,"ts":float}}（正在输入，3s 过期）
        self.known: dict = {}           # R25B uid -> {nick,last_online}（已知用户，含离线）
        self.blocked: set = set()       # R50 uid 集：我屏蔽/被屏蔽的名单（welcome/block_list 同步）
        self.me: dict = {}              # R52 uid -> {nick,sign,avatar}（我自己的资料）
        self.avatars: dict = {}         # R52 uid -> (ext, bytes)（头像原始字节缓存，防重复请求）
        self.group_avatars: dict = {}   # R9H gid -> (ext, bytes)（群头像原始字节缓存）
        self.is_admin = False           # 管理员标识来自服务器已认证的 welcome
        self._last_typing_sent = 0.0    # R25A 本地 typing 限速（1s/人，服务器亦限速）
        self._last_nudge_sent = 0.0     # R67 本地 nudge 限速（5s/人，服务器亦限速）
        self._last_shake_sent = 0.0     # R68 本地 shake 限速（10s/人，服务器亦限速）
        self.pong_count = 0
        # 游戏
        self.game_meta: dict = {}           # name -> {label,min,max}
        self.game_rooms: list = []          # 房间列表（来自服务器广播）
        self.game_room: dict | None = None  # 我所在房间 summary
        self.game_state: dict | None = None  # 当前房间公开快照
        self.game_private: dict | None = None  # 私密信息（手牌/身份/词面）
        self.game_events = deque(maxlen=200)   # 房间事件行
        self._game_left_rooms: set[str] = set()  # 离房确认后忽略旧帧，显式重入才解除。
        self.fish_board: dict = {}           # R70H game -> [{uid,nick,score}]（排行榜缓存）

        self.events: queue.Queue = queue.Queue(maxsize=16384)
        self._on_event = on_event
        self._hb_interval = heartbeat_interval if heartbeat_interval is not None else CFG.heartbeat_interval
        self._hb_timeout = heartbeat_timeout if heartbeat_timeout is not None else CFG.heartbeat_timeout
        self._rb_base = reconnect_base if reconnect_base is not None else CFG.reconnect_base
        self._rb_max = reconnect_max if reconnect_max is not None else CFG.reconnect_max
        # R35 多档案：未显式指定目录时按昵称分子目录（历史/语音/贴纸缓存随账号隔离）
        if history_dir:
            self._history = LocalHistory(history_dir)
        else:
            self._history = LocalHistory(_nick_history_dir(nick) if nick
                                         else _default_history_dir())
        # R19 语音：接收到的 WAV 落到 history 旁 voice/ 子目录，附在事件 voice_path 上
        self._voice_dir = os.path.join(self._history._dir, "voice")
        os.makedirs(self._voice_dir, exist_ok=True)
        # R72 视频留言：VMA1 容器落盘缓存（与 voice/ 同款配额淘汰）
        self._vmemo_dir = os.path.join(self._history._dir, "vmemo")
        os.makedirs(self._vmemo_dir, exist_ok=True)
        # R30C 自定义贴纸：清单（code -> {code,label,ext}）+ 本地图片缓存 stickers_custom/
        self.custom_stickers: dict = {}
        self._sticker_dir = os.path.join(self._history._dir, "stickers_custom")
        os.makedirs(self._sticker_dir, exist_ok=True)
        # R64 贴纸包深化：包封面元数据 pack->{cover:ext} + 封面本地缓存
        self.sticker_pack_meta: dict = {}
        self._pack_cover_dir = os.path.join(self._sticker_dir, "_covers")
        try:
            os.makedirs(self._pack_cover_dir, exist_ok=True)
        except OSError:
            pass
        # 低危治理：语音/贴纸磁盘缓存设上限，按 mtime 保留最近一批（防长会话无限占盘）
        self._prune_cache_dir(self._voice_dir, _CACHE_KEEP_FILES)
        self._prune_cache_dir(self._sticker_dir, _CACHE_KEEP_FILES)
        # R36 E2EE：引擎（身份密钥对落 history 旁，随多账号隔离）+ 握手/群密聊状态
        self.e2ee = E2EEEngine(self._history._dir)
        self._e2ee_pending: dict = {}       # nonce -> {"to": uid, "ev": Event, "rs": str}（发起端等待）
        self._e2ee_rot_wait: dict = {}      # peer_uid -> Event（R42 轮转发起方等 rt2）
        self._e2ee_groups: set = set()      # 已开启群密聊的 gid（客户端会话态）
        self._e2ee_group_members: dict = {} # gid -> frozenset（上次成员快照，检测变动 re-key）
        self._g_rotating: set = set()       # R44 群 DFSS 自动 re-key 在途标记（防重入）
        self._g_rot_backoff: dict = {}      # gid -> 退避截止时间戳（轮转失败后 60s 内不重试）
        # R37 加密云历史：put/get 同步等待（{"ev": Event, "blob": bytes, "err": str}）
        self._cloud_wait: dict = {}
        # R39B 云同步会话状态：client 注入的采集/应用钩子（core 不持有 UI 态）
        self._conv_provider = None          # callable() -> {key: state} | None
        self._conv_applyer = None           # callable(states) -> None | None
        self.files = FileManager(self)      # 文件传输编排（P2P 搭桥 + 断点续传）
        self.calls = CallManager(self)      # R38 1v1 语音对讲（信令+UDP 音频）
        self.voice_room = VoiceRoom(self)    # R72 多人语音房（mesh 音频，与 calls 互斥）

        self._joined_groups: set = set()    # 断线重连后自动重入
        self._seen_seqs: set = set()        # 服务器全局 seq 去重
        self._send_lock = threading.RLock()  # RLock：群 re-key「切链+分发」同锁原子（R44）
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._conn_alive = threading.Event()
        self._sock = None
        self._chan = None
        self._reader = None
        self._heartbeat = None
        self._reconnector = None
        self._last_pong = 0.0
        self._ever_online = False
        self._manual_login_required = False

    # ---------- 生命周期 ----------
    @property
    def connected(self) -> bool:
        return self.state == "online"

    def start(self) -> "ClientCore":
        """启动连接/重连主循环（异步，不阻塞）"""
        if self.state not in ("idle", "offline"):
            raise RuntimeError("client already running")
        self._stop.clear()
        self._manual_login_required = False  # start is an explicit new login attempt
        self._set_state("connecting")
        self._reconnector = threading.Thread(target=self._run, daemon=True,
                                             name="core-connector")
        self._reconnector.start()
        return self

    def stop(self) -> None:
        """关闭连接与所有线程"""
        self._stop.set()
        sock = self._sock
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        self.files.shutdown()               # 终止所有进行中的文件传输
        self.calls.shutdown()               # R38：终止通话并释放音频/UDP 资源
        self.voice_room.shutdown()           # R72：退出语音房并释放资源
        for t in (self._reader, self._heartbeat, self._reconnector):
            if t is not None and t is not threading.current_thread():
                t.join(timeout=2)
        self._history.close()              # 冲刷并关闭历史句柄（正常退出落盘）
        self._set_state("offline")

    def drop(self) -> None:
        """主动断开底层连接（触发自动重连；GUI「重连」按钮/测试用）"""
        sock = self._sock
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def set_host(self, host: str, port: int | None = None) -> None:
        """切换目标服务器（自动发现/设置面板用）。

        重连线程每轮都会读取 self.host/self.port，改完调用 drop()
        即可按新目标重试。
        """
        if host and host.strip():
            self.host = host.strip()
        if port:
            self.port = port

    def set_password(self, pwd: str) -> None:
        """R47-B：设置昵称密码（服务器要求时由 UI 弹框后调用），随即 drop()
        触发重连，下一轮 hello 自动携带。仅内存态，不落盘。"""
        self._pwd = str(pwd or "")

    def send_set_pwd(self, old: str, new: str) -> None:
        """R47-B：设置/修改/清除昵称密码（new 空=清除；结果走 system/error 帧）。"""
        self._send_frame({"t": MsgType.SET_PWD.value, "old": str(old or ""),
                          "new": str(new or "")})

    # ---------- R52 头像与个性签名 ----------
    def send_avatar_set(self, ext: str, data: bytes) -> None:
        """上传/更换头像（服务器校验格式与大小；回 AVATAR_DATA 即时显示）。"""
        self._send_frame({"t": MsgType.AVATAR_SET.value, "ext": str(ext or "")},
                         body=data)

    def send_avatar_del(self) -> None:
        """删除头像（服务器回 AVATAR_DATA ext=""）。"""
        self._send_frame({"t": MsgType.AVATAR_DEL.value})

    def send_avatar_get(self, uid: int) -> None:
        """请求拉取指定 uid 的头像（服务器单播 AVATAR_DATA；无头像 ext=""）。"""
        self._send_frame({"t": MsgType.AVATAR_GET.value, "uid": int(uid)})

    def send_sign_set(self, sign: str) -> None:
        """设置个性签名（服务器广播 roster，全员同步）。"""
        self._send_frame({"t": MsgType.SIGN_SET.value, "sign": str(sign or "")})

    # ---------- 连接/重连主循环 ----------
    def _run(self) -> None:
        backoff = self._rb_base
        while not self._stop.is_set():
            self._set_state("connecting")
            self._ever_online = False
            ok = False
            try:
                ok = self._connect_once()
            except Exception as exc:
                self._push({"t": "error", "code": "conn", "text": f"连接失败: {exc}"})
            if self._stop.is_set():
                break
            self._set_state("offline")
            if ok:
                backoff = self._rb_base
            if self._stop.wait(backoff):
                break
            backoff = min(backoff * 2, self._rb_max)

    def _connect_once(self) -> bool:
        """建连 + 握手 + 登录，然后阻塞在 reader 上直到断线；返回是否曾在线"""
        sock = socket.create_connection((self.host, self.port), timeout=5)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock = sock
        try:
            chan = client_handshake(sock)
        except (HandshakeError, OSError) as exc:
            sock.close()
            self._sock = None
            raise
        sock.settimeout(None)               # 握手完成后转入阻塞读（心跳线程负责判死）
        with self._lock:
            self._chan = chan
            self._conn_alive.set()
        self._last_pong = _now()
        self._heartbeat = threading.Thread(target=self._heartbeat_loop, daemon=True,
                                           name="core-heartbeat")
        self._heartbeat.start()
        self._reader = threading.Thread(target=self._read_loop, daemon=True,
                                        name="core-reader")
        self._reader.start()
        self._send_frame({"t": MsgType.HELLO.value, "nick": self.nick,
                          **({"pwd": self._pwd} if self._pwd else {})})
        self._reader.join()                 # 阻塞到断线/stop
        self._conn_alive.clear()
        with self._lock:
            self._chan = None
        try:
            sock.close()
        except OSError:
            pass
        self._sock = None
        return self._ever_online

    def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            if self._stop.wait(self._hb_interval):
                break
            if not self._conn_alive.is_set():
                break
            try:
                self._send_frame({"t": MsgType.PING.value})
            except Exception:
                break
            if _now() - self._last_pong > self._hb_timeout:
                # 心跳超时 → 强制关连接（reader 随即退出 → 重连循环接管）
                sock = self._sock
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
                break

    def _read_loop(self) -> None:
        try:
            while not self._stop.is_set():
                header, body = self._chan.recv_frame()
                self._dispatch(header, body)
        except (ProtocolError, OSError, ValueError, HandshakeError, TimeoutError):
            if not self._stop.is_set():
                self._push({"t": "error", "code": "conn", "text": "连接断开，正在重连…"})

    # ---------- 收帧分发 ----------
    def _dispatch(self, h: dict, body: bytes = b"") -> None:
        if getattr(self, "_manual_login_required", False):
            return  # late frames cannot revive the revoked authentication
        t = h.get("t")
        if t == "error" and h.get("code") == "kicked":
            with self._lock:
                self._manual_login_required = True
                self._stop.set()
                self._conn_alive.clear()
                self._chan = None
            sock = self._sock
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    sock.close()
                except OSError:
                    pass
            self._set_state("offline")
            self._push(h)
            return
        if t == MsgType.WELCOME.value:
            self._on_welcome(h)
        elif t == MsgType.ROSTER.value:
            self.roster = {u["uid"]: u for u in h.get("online", [])}
            # R25B：roster 广播同步 known（最后上线实时更新，无需重连）
            # R35：type 字段（bot=内置机器人）随广播同步；R52：sign/avatar 随广播同步
            for u in (h.get("known") or []):
                try:
                    self.known[int(u["uid"])] = {
                        "nick": str(u.get("nick") or f"用户{u['uid']}"),
                        "last_online": float(u.get("last_online") or 0),
                        "type": str(u.get("type") or ""),
                        "sign": str(u.get("sign") or ""),
                        "avatar": str(u.get("avatar") or ""),
                        "status": str(u.get("status") or "online"),  # R68：在线状态
                        "remark": str(u.get("remark") or "")}  # R69C9：本人对 ta 的备注名
                except (KeyError, TypeError, ValueError):
                    continue
            self._push(h)
        elif t == MsgType.CHAT.value:
            if h.get("voice"):
                self._attach_voice(h, body)
            if h.get("vmemo"):
                self._attach_vmemo(h, body)
            self._store_chat(h)
            self._push(h)
        elif t == MsgType.POLL.value:
            self._store_chat(h)                  # R26A：投票消息入历史（含 poll 字段）
            self._push(h)
        elif t == MsgType.POLL_STATE.value:
            self._apply_poll_state(h)            # R26A：票数权威更新落盘
            self._push(h)
        elif t == MsgType.PREVIEW.value:
            self._apply_preview(h)               # R26D：链接预览补发落盘
            self._push(h)
        elif t == MsgType.MSG_EDIT.value:
            self._apply_edit(h)
            self._push(h)
        elif t == MsgType.MSG_DEL.value:
            self._apply_del(h)
            self._push(h)
        elif t == MsgType.REACTION.value:
            self._apply_reaction(h)
            self._push(h)
        elif t == MsgType.READ.value:
            self._apply_read(h)
            self._push(h)
        elif t == MsgType.READ_DETAIL.value:      # R33③：已读详情回帧（服务器单播）
            self._push(h)
        elif t == MsgType.THREAD_HISTORY.value:   # R34：话题回复回帧（服务器单播）
            self._push(h)
        elif t == MsgType.PIN.value:
            self._apply_pin(h)
            self._push(h)
        elif t == MsgType.TYPING.value:
            self._on_typing(h)
            self._push(h)
        elif t == MsgType.NUDGE.value:            # R67 拍一拍：纯瞬时展示事件，不入历史
            self._push(h)
        elif t == MsgType.SHAKE.value:            # R68 窗口抖动：纯瞬时展示事件，不入历史
            self._push(h)
        elif t == MsgType.PURGE.value:
            self._apply_purge(h)
            self._push(h)
        elif t == MsgType.CLEARED.value:
            self._apply_cleared(h)        # R53：管理员清理广播 → 清空本地历史
            self._push(h)
        elif t == MsgType.ADMIN_GROUPS_ROSTER.value:
            self._push(h)                 # 系统管理员：群目录（含成员花名册）单播回帧
        elif t == MsgType.ADMIN_USER_INFO.value:
            self._push(h)                 # 系统管理员：某人信息+所属群 单播回帧
        elif t == MsgType.INV_ACK.value:
            self.me["invisible"] = bool(h.get("on"))   # R56 记录最新隐身态
            self._push(h)                 # 隐身上线回帧：含最新 {on}
        elif t == "status_ack":                      # R68 在线状态回帧：含最新 status
            self.me["status"] = str(h.get("status") or "online")
            self._push(h)
        elif t == MsgType.REMARK_ACK.value:           # R69C9 备注名回帧（服务器权威）
            self._push(h)
        elif t == MsgType.PONG.value:
            self._last_pong = _now()
            self.pong_count += 1
            self._push(h)
        elif t == MsgType.SYSTEM.value:
            self._push(h)
        elif t == MsgType.BLOCK_LIST.value:
            # R50：屏蔽名单同步（重连/换端/变更后服务器推送）
            try:
                self.blocked = {int(x) for x in (h.get("blocked") or [])}
            except (KeyError, TypeError, ValueError):
                self.blocked = set()
            self._push(h)
        elif t == MsgType.GROUP_LIST.value:
            self.groups = {g["gid"]: g for g in h.get("groups", [])}
            for g in self.groups.values():
                self.group_admins[g["gid"]] = set(g.get("admins") or [])
            self._sync_announces_from_groups()
            self._push(h)
        elif t == MsgType.GROUP_STATE.value:
            self._on_group_state(h)
        elif t == MsgType.GROUP_INVITE.value:      # R28：服务器单播回邀请码
            gid = h.get("gid")
            if gid is not None:
                self.group_invites[gid] = h.get("code") or ""
            self._push(h)
        elif t == MsgType.HISTORY.value:
            for m in h.get("msgs", []):
                self._store_chat(m)
            self._push(h)
        elif t == MsgType.STICKER_LIST.value:
            self.stickers = h.get("stickers", []) or []
            self._sync_custom_stickers(h.get("custom_stickers"))     # R64：清单随广播刷新
            self._sync_pack_meta(h.get("sticker_pack_meta"))
            self._push(h)
        elif t == MsgType.STICKER_PACK_COVER_DATA.value:             # R64 包封面回帧
            self._on_sticker_pack_cover_data(h, body)
        elif t == MsgType.STICKER_SHOP_LIST.value:   # R35 贴纸商店目录
            self.sticker_shop = h.get("packs", []) or []
            self.sticker_subs = [str(x) for x in (h.get("subs") or [])]
            self._push(h)
        elif t == MsgType.STICKER_SUB.value:         # R35 订阅/退订回帧（全量订阅）
            self.sticker_subs = [str(x) for x in (h.get("subs") or [])]
            self._push(h)
        elif t == MsgType.GAME_LIST.value:
            self.game_meta = {g["name"]: g for g in h.get("games", [])}
            self.game_rooms = h.get("rooms", []) or []
            self._push(h)
        elif t == MsgType.GAME_STATE.value:
            self._on_game_state(h)
        elif t == MsgType.GAME_PRIVATE.value:
            room = self.game_room or {}
            if (h.get("room_id") == room.get("room_id")
                    and room.get("status") == "playing"):
                self.game_private = h.get("state")
                self._push(h)
        elif t == MsgType.FISH_BOARD.value:          # R70H 排行榜（广播/单播共用同一形状）
            game = str(h.get("game") or "")
            if game:
                self.fish_board[game] = h.get("entries", []) or []
            self._push(h)
        elif t == MsgType.E2EE_PUB.value:
            self._on_e2ee_pub(h)                  # R36 密聊握手（被动方）
        elif t == MsgType.E2EE_PUB_ACK.value:
            self._on_e2ee_pub_ack(h)              # R36 密聊握手应答（发起方收）
        elif t == MsgType.E2EE_CHAT.value:
            self._on_e2ee_chat(h, body)           # R36 1v1 密聊密文
        elif t == MsgType.E2EE_GROUP.value:
            self._on_e2ee_group_msg(h, body)      # R36 群密聊密文
        elif t == MsgType.E2EE_SK_DIST_ONE.value:
            self._on_e2ee_sk_dist_one(h)          # R36 sender key 信封
        elif t == MsgType.E2EE_SK_REQ.value:
            self._on_e2ee_sk_req(h)               # R36 密钥补发请求
        elif t == MsgType.CLOUD_DATA.value:
            self._on_cloud_data(h, body)          # R37 云历史拉取回帧
        elif t == MsgType.CLOUD_DONE.value:
            self._on_cloud_done(h)                # R37 云历史上传回执
        elif t == MsgType.AVATAR_DATA.value:
            self._on_avatar_data(h, body)         # R52 头像回帧（缓存+推事件）
        elif t == MsgType.GROUP_AVATAR_DATA.value:
            self._on_group_avatar_data(h, body)   # R9H 群头像回帧（缓存+推事件）
        elif t == MsgType.MOMENT_DATA.value:
            self._on_moment_data(h, body)         # 朋友圈图片回帧（推事件带 data 字节）
        elif t == MsgType.GROUP_FILE_LIST_RES.value:
            # 群文件列表回帧：body=JSON 数组 → 事件带 records
            try:
                records = json.loads((body or b"").decode("utf-8"))
                records = records if isinstance(records, list) else []
            except Exception:
                records = []
            self._push({"t": "group_file_list", "gid": h.get("gid"),
                        "records": records})
        elif t == MsgType.GROUP_FILE_UPLOAD_INFO.value:
            self._push({"t": "group_file_upload_info",
                        "gid": h.get("gid"), "fid": h.get("fid"),
                        "off": h.get("off") or 0})
        elif t == MsgType.GROUP_FILE_DATA.value:
            # 群文件下载数据块：事件带 bytes 字节
            self._push({"t": "group_file_data", "gid": h.get("gid"),
                        "fid": h.get("fid"), "off": h.get("off") or 0,
                        "more": h.get("more") or 0, "data": bytes(body or b"")})
        elif t == MsgType.GROUP_FILE_NOTIFY.value:
            self._push(h)                        # 群内广播：文件增删（事件 t 保留原名）
        elif t == MsgType.TASK_STATE.value:
            # R69B6/B7 群任务清单（广播或单播回帧）：事件带 tasks/text
            self._push({"t": "task_state", "gid": h.get("gid"),
                        "tasks": h.get("tasks") or [],
                        "text": h.get("text") or ""})
        elif t == MsgType.MOMENT_COVER.value:
            self._on_moment_cover(h, body)        # 朋友圈封面回帧/广播
        elif t in _CALL_TYPES:
            self.calls.handle(t, h)         # R38 语音信令转交通话管理器
        elif t in _FILE_TYPES:
            try:
                self.files.handle(t, h, body)   # 文件传输帧转交编排器
            except Exception as exc:
                import traceback
                traceback.print_exc()
        elif t in (MsgType.ROOM_STATE.value, MsgType.ROOM_PEERS.value,
                   MsgType.ROOM_ADDR.value):
            self.voice_room.handle(t, h)     # R72 语音房信令转交房间管理器
        elif t in (MsgType.GEO_LIVE.value, MsgType.GEO_STOP.value):
            self._push(h)                   # R72 位置实时事件（不入历史，纯瞬时展示）
        else:
            if t == "error" and h.get("code") == "cloud":
                self._on_cloud_error(str(h.get("text") or ""))  # R37 上传/拉取失败
            self._push(h)                   # error / 未知/未来类型原样透传

    def _on_welcome(self, h: dict) -> None:
        self.uid = h["uid"]
        self._ever_online = True
        # R52：我自己的资料（sign/avatar 随 welcome 带回）
        self.me = {"uid": self.uid, "nick": h.get("nick") or self.nick,
                   "sign": str(h.get("sign") or ""),
                   "avatar": str(h.get("avatar") or ""),
                   "invisible": bool(h.get("invisible")),   # R56 隐身上线初始态
                   "status": str(h.get("status") or "online")}   # R68 我的在线状态
        self.is_admin = bool(h.get("is_admin"))   # 管理员标识（服务器授予）
        self.roster = {u["uid"]: u for u in h.get("roster", [])}
        self.groups = {g["gid"]: g for g in h.get("groups", [])}
        for g in self.groups.values():
            self.group_admins[g["gid"]] = set(g.get("admins") or [])
        self._sync_announces_from_groups()
        self.stickers = h.get("stickers", []) or []
        self.sticker_subs = [str(x) for x in (h.get("sticker_subs") or [])]  # R35
        self._sync_custom_stickers(h.get("custom_stickers"))   # R30C：清单 + 预热缓存
        self._sync_pack_meta(h.get("sticker_pack_meta"))       # R64：包封面元数据
        self.pins = {}
        for p in (h.get("pins") or []):
            if p.get("key"):
                self.pins[p["key"]] = p
        # R25B：已知用户（含离线最后上线）；roster 只有在线，离线态靠 known 补
        # R35：type 字段（bot=内置机器人，永远在线）；R52：sign/avatar 字段
        self.known = {}
        for u in (h.get("known") or []):
            try:
                self.known[int(u["uid"])] = {"nick": str(u.get("nick") or f"用户{u['uid']}"),
                                             "last_online": float(u.get("last_online") or 0),
                                             "type": str(u.get("type") or ""),
                                             "sign": str(u.get("sign") or ""),
                                             "avatar": str(u.get("avatar") or ""),
                                             "status": str(u.get("status") or "online"),  # R68
                                             "remark": str(u.get("remark") or ""),  # R69C9 备注名
                                             "invisible": bool(u.get("invisible"))}  # R58 隐身标记(管理员可用)
            except (KeyError, TypeError, ValueError):
                continue
        # R50 屏蔽名单（welcome 带回，登录即对齐）
        try:
            self.blocked = {int(x) for x in (h.get("blocked") or [])}
        except (KeyError, TypeError, ValueError):
            self.blocked = set()
        # R25A：welcome 清空旧 typing（重连后无人在输入）
        self.typing.clear()
        for m in h.get("history", []):      # 服务器公聊历史并入本地（按 seq 去重）
            self._store_chat(m)
        for m in h.get("saved", []):        # R25C 收藏夹历史并入本地（private:uid:uid）
            self._store_chat(m)
        # R29B 草稿同步：服务器带回全部草稿（换端登录恢复输入）
        self.remote_drafts = {}
        for d in (h.get("drafts") or []):
            key = str(d.get("key") or "")
            if key:
                self.remote_drafts[key] = {"text": str(d.get("text") or ""),
                                           "ts": float(d.get("ts") or 0)}
        self._set_state("online")
        self._push({"t": "welcome", "uid": self.uid, "nick": self.nick})
        if self.remote_drafts:
            self._push({"t": "draft",
                        "drafts": [{"key": k, **v} for k, v in self.remote_drafts.items()]})
        for gid in list(self._joined_groups):   # 重连后恢复群身份（群还在则自动重入）
            self._send_frame({"t": MsgType.GROUP_JOIN.value, "gid": gid})
        # R36 重连恢复：群密聊开启态向群内广播 SK_REQ，让在线成员补发 sender key
        for gid in list(self._e2ee_groups):
            if gid in self.groups:
                self._send_frame({"t": MsgType.E2EE_SK_REQ.value, "gid": gid})

    # ---------- R30C 自定义贴纸 ----------
    def _sync_custom_stickers(self, items) -> None:
        """welcome/sticker_list 带回自定义贴纸清单；本地缺图的自动补拉。"""
        self.custom_stickers = {}
        for s in (items or []):
            code = str(s.get("code") or "")
            if code:
                try:
                    order = int(s.get("order") or 0)
                except (TypeError, ValueError):
                    order = 0
                self.custom_stickers[code] = {"code": code,
                                              "label": str(s.get("label") or ""),
                                              "pack": str(s.get("pack") or ""),
                                              "ext": str(s.get("ext") or "png"),
                                              "order": order}
        for code in self.custom_stickers:
            if self.custom_sticker_path(code) is None:
                self.get_custom_sticker(code)

    def _sync_pack_meta(self, meta) -> None:
        """R64：包封面元数据；本地缺图的自动补拉（与自定义贴纸图同一套懒加载范式）。"""
        self.sticker_pack_meta = {}
        for pack, v in (meta or {}).items():
            if not isinstance(v, dict):
                continue
            ext = str(v.get("cover") or "").lower().strip(". ")
            if ext:
                self.sticker_pack_meta[str(pack)] = {"cover": ext}
        for pack in self.sticker_pack_meta:
            if self.pack_cover_path(pack) is None:
                self.get_sticker_pack_cover(pack)

    def _on_sticker_pack_cover_data(self, h: dict, body: bytes) -> None:
        """STICKER_PACK_COVER_DATA：封面字节落缓存目录，推事件让 GUI 刷新导航条。"""
        pack = str(h.get("pack") or "")
        ext = str(h.get("ext") or "").lower().strip(". ")
        if not pack or not ext or not body:
            return
        try:
            with open(os.path.join(self._pack_cover_dir, self._cover_name(pack, ext)),
                      "wb") as f:
                f.write(body)
        except OSError:
            return
        self._push({"t": "sticker_pack_cover_data", "pack": pack})

    def _on_sticker_data(self, h: dict, body: bytes) -> None:
        """STICKER_CUSTOM_DATA：图片字节落缓存目录，推事件让 GUI 刷新贴纸面板。"""
        code = str(h.get("code") or "")
        ext = str(h.get("ext") or "png")
        if not code or not body:
            return
        try:
            with open(os.path.join(self._sticker_dir, f"{code}.{ext}"), "wb") as f:
                f.write(body)
        except OSError:
            return
        self._prune_cache_dir(self._sticker_dir, _CACHE_KEEP_FILES)
        self._push({"t": "sticker_data", "code": code})

    def _on_avatar_data(self, h: dict, body: bytes) -> None:
        """AVATAR_DATA：缓存原始字节，推事件让 GUI 注册图片头像并重绘。"""
        try:
            uid = int(h.get("uid"))
        except (TypeError, ValueError):
            return
        ext = str(h.get("ext") or "")
        if ext and body:
            self.avatars[uid] = (ext, body)
        else:
            self.avatars.pop(uid, None)
        self._push({"t": "avatar_data", "uid": uid, "ext": ext})

    def _on_group_avatar_data(self, h: dict, body: bytes) -> None:
        """GROUP_AVATAR_DATA：缓存群头像原始字节，推事件让 GUI 注册图片并重绘。"""
        try:
            gid = int(h.get("gid"))
        except (TypeError, ValueError):
            return
        ext = str(h.get("ext") or "")
        if ext and body:
            self.group_avatars[gid] = (ext, bytes(body))
        else:
            self.group_avatars.pop(gid, None)
        self._push({"t": "group_avatar_data", "gid": gid, "ext": ext})

    def _on_moment_data(self, h: dict, body: bytes) -> None:
        """朋友圈图片回帧：原样推事件，事件带 data 字节（GUI 解码缩略）。"""
        self._push({"t": "moment_data", "fn": str(h.get("fn") or ""),
                    "ext": str(h.get("ext") or ""), "data": bytes(body or b"")})

    def _on_moment_cover(self, h: dict, body: bytes) -> None:
        """朋友圈封面回帧/广播：cover=None 表示默认；img 模式 body=图片字节。"""
        self._push({"t": "moment_cover", "uid": h.get("uid"),
                    "cover": h.get("cover") or None,
                    "data": bytes(body or b"")})

    def custom_sticker_path(self, code: str) -> str | None:
        """本地缓存里的贴纸图片路径（msg_list 渲染用）；未缓存返回 None。"""
        meta = self.custom_stickers.get(code)
        if not meta:
            return None
        path = os.path.join(self._sticker_dir, f"{code}.{meta.get('ext')}")
        return path if os.path.exists(path) else None

    def _prune_cache_dir(self, d: str, keep: int) -> None:
        """磁盘缓存配额：超过 keep 个文件时按 mtime 删除最旧一批（低危资源治理）。
        历史重放时被精简的旧语音/贴纸文件缺失 → GUI 播放/渲染已做缺省兜底。"""
        try:
            files = [(os.path.getmtime(os.path.join(d, n)), n)
                     for n in os.listdir(d)
                     if os.path.isfile(os.path.join(d, n))]
        except OSError:
            return
        if len(files) <= keep:
            return
        for _mtime, name in sorted(files):            # 最旧在前
            if len(files) <= keep:
                break
            try:
                os.remove(os.path.join(d, name))
            except OSError:
                pass
            files.pop(0)

    def add_custom_sticker(self, code: str, label: str, ext: str,
                           data: bytes, pack: str = "") -> bool:
        """R30C 上传自定义贴纸（图片字节走 body；pack=可选包名，空则归入默认「我的贴纸」）。"""
        return self._send_frame({"t": MsgType.STICKER_CUSTOM_ADD.value,
                                 "code": (code or "").strip(),
                                 "label": (label or "").strip(),
                                 "pack": (pack or "").strip(),
                                 "ext": (ext or "").lower().strip(". ")}, bytes(data))

    def sticker_packs(self) -> dict:
        """R61/R64：自定义贴纸按包分组（{"未分组": {code:meta}, "包名": {...}}），
        包内按 (order, code) 升序（服务端排序权威），包间按包名升序稳定。"""
        groups: dict = {}
        for code in sorted(self.custom_stickers,
                           key=lambda c: (str(self.custom_stickers[c].get("pack") or ""),
                                          int(self.custom_stickers[c].get("order") or 0),
                                          c)):
            meta = self.custom_stickers[code]
            p = (meta.get("pack") or "").strip() or "未分组"
            groups.setdefault(p, {})[code] = meta
        return groups

    @staticmethod
    def _cover_name(pack: str, ext: str) -> str:
        """包封面缓存文件名：与服务器同口径（包名 md5 派生），跨端一致。"""
        h = hashlib.md5(("pack:" + str(pack)).encode("utf-8")).hexdigest()[:16]
        return f"{h}.{ext}"

    def pack_cover_path(self, pack: str) -> str | None:
        """包封面本地缓存路径（导航条缩略图渲染用）；未缓存返回 None。"""
        meta = self.sticker_pack_meta.get(pack)
        if not meta:
            return None
        path = os.path.join(self._pack_cover_dir,
                            self._cover_name(pack, meta.get("cover") or "png"))
        return path if os.path.exists(path) else None

    def del_custom_sticker(self, code: str) -> bool:
        return self._send_frame({"t": MsgType.STICKER_CUSTOM_DEL.value,
                                 "code": (code or "").strip()})

    def get_custom_sticker(self, code: str) -> bool:
        return self._send_frame({"t": MsgType.STICKER_CUSTOM_GET.value,
                                 "code": (code or "").strip()})

    # ---------- R64 贴纸包管理 / 包封面 / 包内排序 ----------
    def rename_sticker_pack(self, old: str, new: str) -> bool:
        return self._send_frame({"t": MsgType.STICKER_PACK_RENAME.value,
                                 "old": (old or "").strip(),
                                 "new": (new or "").strip()})

    def del_sticker_pack(self, pack: str) -> bool:
        return self._send_frame({"t": MsgType.STICKER_PACK_DEL.value,
                                 "pack": (pack or "").strip()})

    def set_sticker_pack_cover(self, pack: str, ext: str, data: bytes) -> bool:
        """上传包封面（字节走 body）；包不存在由服务器拒绝。"""
        return self._send_frame({"t": MsgType.STICKER_PACK_COVER.value,
                                 "pack": (pack or "").strip(),
                                 "ext": (ext or "").lower().strip(". ")},
                                bytes(data))

    def clear_sticker_pack_cover(self, pack: str) -> bool:
        """清除包封面（无 body → 服务器按「清除」处理）。"""
        return self._send_frame({"t": MsgType.STICKER_PACK_COVER.value,
                                 "pack": (pack or "").strip()})

    def get_sticker_pack_cover(self, pack: str) -> bool:
        return self._send_frame({"t": MsgType.STICKER_PACK_COVER_GET.value,
                                 "pack": (pack or "").strip()})

    def reorder_sticker(self, code: str, direction: str) -> bool:
        """包内排序：direction ∈ up/down/top/bottom（服务端重排 order 后广播）。"""
        d = str(direction or "").strip().lower()
        if d not in ("up", "down", "top", "bottom"):
            return False
        return self._send_frame({"t": MsgType.STICKER_REORDER.value,
                                 "code": (code or "").strip(), "dir": d})

    def _on_group_state(self, h: dict) -> None:
        gid = h.get("gid")
        members = h.get("members", [])
        self.group_members[gid] = members
        self.group_admins[gid] = set(h.get("admins") or [])
        self.group_mutes[gid] = {int(k): v for k, v in (h.get("mutes") or {}).items()}
        self.group_announces[gid] = h.get("announce") or ""
        self.group_ann_modes[gid] = bool(h.get("announce_mode"))  # C9①：仅公告说话模式
        self.group_slows[gid] = int(h.get("slow") or 0)   # R70D：群慢速档位（秒）
        # 同步 groups 里的 owner / admins，供 UI 判权
        g = self.groups.get(gid)
        if g:
            g["name"] = h.get("name", g.get("name"))      # R28：改名同步标题
            g["owner"] = h.get("owner", g.get("owner"))
            g["admins"] = sorted(self.group_admins[gid])
            g["member_count"] = len(members)
            g["announce"] = self.group_announces[gid]
            g["announce_mode"] = self.group_ann_modes[gid]   # C9①：仅公告说话模式
            g["slow"] = self.group_slows[gid]                # R70D：群慢速档位
            g["avatar"] = h.get("avatar", g.get("avatar", ""))   # R9H：群头像 ext
            g["about"] = h.get("about", g.get("about", ""))      # R9H：群简介
            g["kind"] = h.get("kind", g.get("kind", ""))    # R72："" / "channel" / "forum"
        mine = self.uid in (m.get("uid") for m in members) if self.uid is not None else False
        if mine:
            self._joined_groups.add(gid)
        else:
            self._joined_groups.discard(gid)   # 被踢/退群/解散后不再自动重入
        # R36 群密聊：成员变动 → 后台自动 re-key；退群/被踢 → 销毁密钥材料
        if gid in self._e2ee_groups:
            if not mine:
                self._e2ee_groups.discard(gid)
                self._e2ee_group_members.pop(gid, None)
                self.e2ee.drop_group(gid)
            else:
                cur = frozenset(int(m["uid"]) for m in members)
                if cur != self._e2ee_group_members.get(gid):
                    threading.Thread(target=self.open_group_e2ee, args=(gid,),
                                     daemon=True, name="e2ee-rekey").start()
        self._push(h)

    def _sync_announces_from_groups(self) -> None:
        """welcome/group_list 全量刷新后，把群摘要里的公告位同步进 announces 表。"""
        self.group_announces.clear()
        for gid, g in self.groups.items():
            self.group_announces[gid] = g.get("announce") or ""

    def send_group_announce(self, gid: int, text: str) -> bool:
        """设/清除群公告（空文本=清除）;权限由服务器校验。"""
        return self._send_frame({"t": MsgType.GROUP_ANNOUNCE.value,
                                 "gid": gid, "text": text})

    def send_group_ann_mode(self, gid: int, on: bool) -> bool:
        """C9① 群"仅公告说话模式"开关（群主/管理员；权限由服务器校验）。"""
        return self._send_frame({"t": MsgType.GROUP_ANN_MODE.value,
                                 "gid": gid, "on": bool(on)})

    def send_group_slow(self, gid: int, seconds: int) -> bool:
        """R70D 设置群慢速档位（0=关闭；群主/管理员，权限由服务器校验）。"""
        return self._send_frame({"t": MsgType.GROUP_SLOW.value,
                                 "gid": gid, "seconds": int(seconds or 0)})

    def get_group_invite(self, gid: int) -> bool:
        """R28 请求群邀请码（群主/管理员；回帧 group_invite 落到 group_invites）。"""
        return self._send_frame({"t": MsgType.GROUP_INVITE_GET.value, "gid": gid})

    def join_group_by_invite(self, code: str) -> bool:
        """R28 凭邀请码入群（不依赖群列表选择）。"""
        return self._send_frame({"t": MsgType.GROUP_JOIN_INVITE.value,
                                 "code": (code or "").strip()})

    def rename_group(self, gid: int, name: str) -> bool:
        """R28 群改名（群主/管理员；权限由服务器校验）。"""
        return self._send_frame({"t": MsgType.GROUP_RENAME.value,
                                 "gid": gid, "name": name})

    # ---------- R9H 群资料：群简介 / 群头像 ----------
    def send_group_about(self, gid: int, about: str) -> bool:
        """设置群简介（空=清除；群主/管理员，服务器校验）。"""
        return self._send_frame({"t": MsgType.GROUP_ABOUT.value,
                                 "gid": gid, "about": str(about or "")})

    def send_group_avatar_set(self, gid: int, ext: str, data: bytes) -> None:
        """上传/更换群头像（服务器校验格式大小权限；回 GROUP_AVATAR_DATA 即时显示）。"""
        self._send_frame({"t": MsgType.GROUP_AVATAR_SET.value,
                          "gid": int(gid), "ext": str(ext or "")}, body=data)

    def send_group_avatar_del(self, gid: int) -> None:
        """清空群头像（群主/管理员；服务器回 GROUP_AVATAR_DATA ext="" 清缓存）。"""
        self._send_frame({"t": MsgType.GROUP_AVATAR_DEL.value, "gid": int(gid)})

    def send_group_avatar_get(self, gid: int) -> None:
        """请求拉取群头像（服务器单播 GROUP_AVATAR_DATA；无头像 ext=""）。"""
        self._send_frame({"t": MsgType.GROUP_AVATAR_GET.value, "gid": int(gid)})

    # ---------- 群文件库（服务端权威，独立于 1v1 文件传输） ----------
    def send_group_file_list(self, gid: int) -> None:
        """请求群文件列表（服务器回 GROUP_FILE_LIST_RES）。"""
        self._send_frame({"t": MsgType.GROUP_FILE_LIST.value, "gid": int(gid)})

    def send_group_file_upload_start(self, gid: int, name: str, size: int) -> None:
        """发起群文件上传（服务器分配 fid 回 INFO）。"""
        self._send_frame({"t": MsgType.GROUP_FILE_UPLOAD_START.value,
                          "gid": int(gid), "name": str(name), "size": int(size)})

    def send_group_file_upload(self, gid: int, fid: str, off: int, data: bytes) -> None:
        """上传群文件数据块（off=已写字节起点）。"""
        self._send_frame({"t": MsgType.GROUP_FILE_UPLOAD.value,
                          "gid": int(gid), "fid": str(fid), "off": int(off)}, body=data)

    def send_group_file_upload_done(self, gid: int, fid: str, off: int) -> None:
        """收尾群文件上传（服务器校验字节数并广播）。"""
        self._send_frame({"t": MsgType.GROUP_FILE_UPLOAD_DONE.value,
                          "gid": int(gid), "fid": str(fid), "off": int(off)})

    def send_group_file_del(self, gid: int, fid: str) -> None:
        """删除群文件（本人/群主/管理员；服务器校验）。"""
        self._send_frame({"t": MsgType.GROUP_FILE_DEL.value,
                          "gid": int(gid), "fid": str(fid)})

    def send_group_file_get(self, gid: int, fid: str) -> None:
        """请求下载群文件（服务器逐块回 GROUP_FILE_DATA）。"""
        self._send_frame({"t": MsgType.GROUP_FILE_GET.value,
                          "gid": int(gid), "fid": str(fid)})

    # ---------- R69B6/B7 群待办 / 接龙 / 签到（服务端权威） ----------
    def send_task_add(self, gid: int, text: str, mode: str = "todo",
                      assignee: int = 0) -> bool:
        """发起群任务（mode=todo|relay|checkin；assignee=0 公开）。"""
        return self._send_frame({"t": MsgType.TASK_ADD.value, "gid": int(gid),
                                 "text": str(text or ""), "mode": str(mode),
                                 "assignee": int(assignee or 0)})

    def send_task_do(self, gid: int, tid: int, on: bool = True) -> bool:
        """参与/打卡（on=False 撤销参与）。"""
        return self._send_frame({"t": MsgType.TASK_DO.value, "gid": int(gid),
                                 "tid": int(tid), "on": 1 if on else 0})

    def send_task_list(self, gid: int) -> bool:
        """请求群任务清单（服务器单播回 TASK_STATE）。"""
        return self._send_frame({"t": MsgType.TASK_LIST.value, "gid": int(gid)})

    def send_task_del(self, gid: int, tid: int) -> bool:
        """关闭群任务（发起人/群主/管理员；权限由服务器校验）。"""
        return self._send_frame({"t": MsgType.TASK_DEL.value, "gid": int(gid),
                                 "tid": int(tid)})

    def _on_game_state(self, h: dict) -> None:
        room = h.get("room")
        rid = str(h.get("room_id") or (room.get("room_id") if isinstance(room, dict) else "") or "")
        current = self.game_room or {}
        current_rid = str(current.get("room_id") or "")
        member = (isinstance(room, dict)
                  and (self.uid in (room.get("players") or [])
                       or self.uid in (room.get("spectators") or [])))
        if not member:
            if not current_rid or rid != current_rid:
                return
            self._game_left_rooms.add(rid)
            self.game_room = self.game_state = self.game_private = None
            self.game_events.clear()
            self._push(h)
            return
        if rid in self._game_left_rooms:
            return
        if (rid != current_rid or room.get("round") != current.get("round")
                or room.get("status") == "created"):
            self.game_private = None
            self.game_events.clear()
        if room.get("status") != "playing":
            self.game_private = None
        self.game_room = room
        self.game_state = h.get("state")
        for line in h.get("events") or []:
            self.game_events.append(line)
        self._push(h)

    def _edit_del_key(self, h: dict) -> str | None:
        """edit/del 事件 → 本地历史频道键（与 _store_chat 同一套映射）。"""
        ch = h.get("channel", "public")
        uid = h.get("uid")
        to = h.get("to")
        if uid is None:
            return None
        if ch == "public":
            return "public"
        if ch == "private":
            a, b = sorted((int(uid), int(to or 0)))
            return f"private:{a}:{b}"
        return f"group:{int(to)}"

    def _apply_edit(self, h: dict) -> None:
        key = self._edit_del_key(h)
        if key is not None:
            self._history.edit_msg_local(key, h.get("seq"), h.get("text", ""),
                                         rich=h.get("rich"),
                                         edits=h.get("edits"))

    def _apply_del(self, h: dict) -> None:
        key = self._edit_del_key(h)
        if key is not None:
            self._history.del_msg_local(key, h.get("seq"))

    def _apply_reaction(self, h: dict) -> None:
        """reaction 事件：把 responses 状态写回本地历史（msg_list 行共享该 dict）。"""
        key = self._edit_del_key(h)
        if key is not None:
            self._history.reactions_local(key, h.get("seq"), h.get("reactions") or {})

    def _apply_poll_state(self, h: dict) -> None:
        """R26A/R70C poll_state 事件：把权威票数写回本地历史（msg_list 行共享该 dict）。"""
        key = self._edit_del_key(h)
        if key is not None:
            self._history.poll_state_local(key, h.get("seq"), h)

    def _apply_preview(self, h: dict) -> None:
        """R26D preview 事件：把服务器抓取的链接预览卡片写回本地历史。"""
        key = self._edit_del_key(h)
        if key is not None:
            self._history.preview_local(key, h.get("seq"), h.get("preview") or {})

    def _apply_read(self, h: dict) -> None:
        """read 事件：记录 uid 在某会话读到的最远 seq。"""
        key, uid, seq = h.get("key"), h.get("uid"), h.get("seq")
        if not key or uid is None or seq is None:
            return
        rd = self.reads.setdefault(key, {})
        if rd.get(uid, 0) < seq:
            rd[uid] = seq

    def _apply_pin(self, h: dict) -> None:
        """pin 事件：更新会话级置顶快照。"""
        key = h.get("key")
        if not key:
            return
        if h.get("on"):
            self.pins[key] = h.get("msg") or {}
        else:
            self.pins.pop(key, None)

    _TYPING_TTL = 3.0            # R25A：typing 状态过期秒数（无新帧自动消失）

    def _on_typing(self, h: dict) -> None:
        """typing 事件：记录某 uid 正在某会话输入（带时间戳，过期惰性清除）。"""
        key = self._edit_del_key(h)
        if key is None or h.get("uid") is None:
            return
        if self.uid is not None and int(h["uid"]) == self.uid:
            return                                   # 忽略自己（服务器本就不回传）
        bucket = self.typing.setdefault(key, {})
        bucket[int(h["uid"])] = {"nick": str(h.get("nick") or f"用户{h['uid']}"),
                                 "ts": time.time()}

    def typing_for(self, key: str) -> list:
        """R25A 取某会话当前正在输入的昵称列表（过期条目就地清除）。"""
        bucket = self.typing.get(key)
        if not bucket:
            return []
        now = time.time()
        alive = [(info["nick"], info["ts"])
                 for info in bucket.values() if now - info["ts"] <= self._TYPING_TTL]
        if not alive:
            self.typing.pop(key, None)
            return []
        alive.sort(key=lambda t: t[1])               # 谁先输入谁在前
        return [nick for nick, _ts in alive]

    def _apply_purge(self, h: dict) -> None:
        """purge 事件：丢弃该会话 seq<=until_seq 的本地历史（会话清理）。"""
        key, until = h.get("key"), h.get("until_seq")
        if not key or until is None:
            return
        try:
            self._history.purge_local(key, int(until))
        except (TypeError, ValueError):
            pass

    def _apply_cleared(self, h: dict) -> None:
        """R53 cleared 事件：服务器权威清理广播 → 同步清空本地历史（内存+落盘）。
        {all: true}=清空全部；{uid: n}=清空该用户全部消息（跨全部频道）。"""
        if h.get("all"):
            self._history.clear_local_all()
        elif h.get("uid") is not None:
            try:
                self._history.clear_local_uid(int(h.get("uid")))
            except (TypeError, ValueError):
                pass

    def _store_chat(self, h: dict) -> None:
        seq = h.get("seq")
        if seq is not None:
            if seq in self._seen_seqs:
                return
            self._seen_seqs.add(seq)
            if len(self._seen_seqs) > 10000:    # 防无限膨胀，只保留最近 5000
                self._seen_seqs = set(list(self._seen_seqs)[-5000:])
        # 频道键取自消息自身的 uid/to 配对（收件人视角的 to 是自己，不能拿 my_uid 配对）
        ch = h.get("channel", "public")
        if ch == "public":
            key = "public"
        elif ch == "e2ee":
            a, b = sorted((int(h["uid"]), int(h.get("to") or 0)))
            key = f"e2ee:{a}:{b}"
        elif ch == "private":
            a, b = sorted((int(h["uid"]), int(h.get("to") or 0)))
            key = f"private:{a}:{b}"
        else:
            key = f"group:{int(h.get('to'))}"
        self._history.add(key, h)

    # ---------- 发送 API ----------
    def _attach_voice(self, h: dict, body: bytes) -> None:
        """收到语音消息：把 WAV 二进制体落盘到 voice/ 并附 voice_path（供 GUI 播放）。
        无 body（历史重放/服务器 TTL 过期）则视为墓碑，不动 voice_path。"""
        if not body:
            return
        seq = h.get("seq")
        # 文件名确定化：优先 seq；无 seq 时用 ts 的标准哈希（进程级 hash() 会漂移，弃用）
        name = f"voice_{seq}.wav" if seq else \
            f"voice_{hashlib.md5(str(h.get('ts', '')).encode()).hexdigest()[:12]}.wav"
        path = os.path.join(self._voice_dir, name)
        try:
            with open(path, "wb") as f:
                f.write(body)
            h["voice_path"] = path
            self._prune_cache_dir(self._voice_dir, _CACHE_KEEP_FILES)
        except OSError:
            h["voice_path"] = ""

    def send_voice(self, channel: str, to, wav: bytes, duration: float = 0.0) -> bool:
        """发送语音消息：body = WAV 字节；channel ∈ public/private/group，权限服务端校验。"""
        return self._send_frame({"t": MsgType.VOICE.value, "channel": channel,
                                 "to": to, "duration": duration}, bytes(wav))

    def _attach_vmemo(self, h: dict, body: bytes) -> None:
        """收到视频留言：把 VMA1 容器落盘到 vmemo/ 并附 vmemo_path（供 GUI 播放）。
        无 body（历史重放/服务器 TTL 过期）则视为墓碑，不动 vmemo_path。"""
        if not body:
            return
        seq = h.get("seq")
        name = f"vmemo_{seq}.vma" if seq else \
            f"vmemo_{hashlib.md5(str(h.get('ts', '')).encode()).hexdigest()[:12]}.vma"
        path = os.path.join(self._vmemo_dir, name)
        try:
            with open(path, "wb") as f:
                f.write(body)
            h["vmemo_path"] = path
            self._prune_cache_dir(self._vmemo_dir, _CACHE_KEEP_FILES)
        except OSError:
            h["vmemo_path"] = ""

    def send_vmemo(self, channel: str, to, blob: bytes,
                   duration: float = 0.0) -> bool:
        """发送视频留言：body = VMA1 容器字节；权限校验同语音消息。"""
        return self._send_frame({"t": MsgType.VMEMO.value, "channel": channel,
                                 "to": to, "duration": duration}, bytes(blob))

    def send_geo_live(self, channel: str, to, geo: dict) -> bool:
        """发送实时位置刷新（不入历史，定时重发由 GUI 负责）。"""
        return self._send_frame({"t": MsgType.GEO_LIVE.value, "channel": channel,
                                 "to": to, "geo": geo})

    def send_geo_stop(self, channel: str, to, session: str = "") -> bool:
        """停止实时位置共享（让对端摘掉标记）。"""
        h = {"t": MsgType.GEO_STOP.value, "channel": channel, "to": to}
        if session:
            h["session"] = session
        return self._send_frame(h)


    def send_chat(self, text: str = "", sticker: str = "", channel: str = "public",
                  to=None, reply: dict | None = None, forward: dict | None = None,
                  burn: bool = False, silent: bool = False,
                  thread_root: int | None = None,
                  fwd_seqs: list | None = None,
                  fwd_from: dict | None = None,
                  rich: list | None = None,
                  disguise: str = "",
                  auto: bool = False,
                  card: dict | None = None,
                  geo: dict | None = None) -> bool:
        header = {"t": MsgType.CHAT.value, "channel": channel}
        if text:
            header["text"] = text
        if rich is not None:
            header["rich"] = rich                 # R59：富文本段（[[text,kind,href],...]）
        if sticker:
            header["sticker"] = sticker
        if reply is not None:
            header["reply"] = reply             # C4 引用回复快照
        if forward is not None:
            header["forward"] = forward         # R13 转发：原消息快照
        if burn:
            header["burn"] = True               # R14 阅后即焚：全部读完即删
        if silent:
            header["silent"] = True             # R26C 静默发送：接收端免通知
        if disguise:
            header["disguise"] = disguise       # R70E 消息伪装：外观风格（code/log/excel）
        if auto:
            header["auto"] = True               # R70G 忙碌自动回复：接收端据此不再触发自动回复
        if card:
            header["card"] = card               # R71 联系人名片：{uid,nick}（服务器白名单化）
        if geo:
            header["geo"] = geo                 # R72 位置共享：{lat,lon,name,...}
        if thread_root is not None:
            header["thread_root"] = int(thread_root)   # R34：话题回复（根消息 seq）
        if fwd_seqs:
            # R64 合并转发：只提交源会话 + 源消息 seq，条目由服务器按真实历史聚合
            header["fwd_seqs"] = list(fwd_seqs)
            if isinstance(fwd_from, dict):
                header["fwd_from"] = dict(fwd_from)
        if to is not None:
            header["to"] = to
        return self._send_frame(header)

    # ---------- 朋友圈（图文动态；对应服务端 moment_* 命令） ----------
    def send_moment_publish(self, text: str = "", image_paths=None) -> bool:
        """发动态：text + 可选多图。读取本地图片拼 body=[u32 长+字节]*，透传服务器落盘广播。"""
        blobs, exts = [], []
        for p in (image_paths or []):
            try:
                with open(p, "rb") as f:
                    blob = f.read()
            except OSError:
                continue
            if not blob:
                continue
            blobs.append(blob)
            exts.append(os.path.splitext(p)[1].lstrip(".").lower() or "jpg")
        body = b"".join(len(b).to_bytes(4, "big") + b for b in blobs)
        header = {"t": "moment_publish", "text": text}
        if exts:
            header["exts"] = exts
        return self._send_frame(header, body)

    def send_moment_like(self, pid: int, on: bool = True) -> bool:
        return self._send_frame({"t": "moment_like", "pid": int(pid), "on": bool(on)})

    def send_moment_comment(self, pid: int, text: str = "",
                            reply_uid=None, reply_nick="") -> bool:
        f = {"t": "moment_comment", "pid": int(pid), "text": str(text)[:500]}
        if reply_uid is not None or (reply_nick or "").strip():
            f["rep_uid"] = reply_uid
            f["rep_nick"] = (reply_nick or "").strip()[:50]
        return self._send_frame(f)

    def send_moment_del(self, pid: int) -> bool:
        return self._send_frame({"t": "moment_del", "pid": int(pid)})

    def send_moment_feed(self) -> bool:
        return self._send_frame({"t": "moment_feed"})

    def send_moment_img_get(self, fn: str) -> bool:
        return self._send_frame({"t": "moment_img_get", "fn": str(fn)})

    def send_moment_cover_set_preset(self, preset: int) -> bool:
        return self._send_frame({"t": "moment_cover_set", "preset": int(preset)})

    def send_moment_cover_set_img(self, path: str) -> bool:
        """上传本地图片为封面（≤2MB，服务端校验）。"""
        try:
            with open(path, "rb") as f:
                blob = f.read()
        except OSError:
            return False
        if not blob:
            return False
        ext = os.path.splitext(path)[1].lstrip(".").lower() or "jpg"
        return self._send_frame({"t": "moment_cover_set", "ext": ext}, blob)

    def send_moment_cover_get(self) -> bool:
        return self._send_frame({"t": "moment_cover_get"})

    def send_moment_cover_del(self) -> bool:
        return self._send_frame({"t": "moment_cover_del"})

    def send_thread_fetch(self, channel: str, to, root_seq: int) -> bool:
        """R34 群内话题：拉取根消息 root_seq 的全部回复（服务器回 THREAD_HISTORY）。"""
        header = {"t": MsgType.THREAD_FETCH.value, "channel": channel,
                  "root_seq": int(root_seq)}
        if to is not None:
            header["to"] = to
        return self._send_frame(header)

    def send_poll(self, channel: str = "public", to=None,
                  question: str = "", options: list | None = None,
                  anonymous: bool = False, multi: bool = False,
                  quiz: bool = False, correct=None) -> bool:
        """R26A/R70C 发起投票：question + options（≥2），可匿名/多选/测验（指定正确项）。"""
        header = {"t": MsgType.POLL.value, "channel": channel,
                  "question": question, "options": list(options or []),
                  "anonymous": bool(anonymous), "multi": bool(multi)}
        if quiz:
            header["quiz"] = True
            header["correct"] = int(correct or 0)
        if to is not None:
            header["to"] = to
        return self._send_frame(header)

    def send_poll_vote(self, seq: int, option: int) -> bool:
        """R26A 投票/改票：对 seq 投票选择 option 索引（重复投=改票）。"""
        return self._send_frame({"t": MsgType.POLL_VOTE.value, "seq": seq,
                                 "option": option})

    def send_reaction(self, seq: int, emoji: str, on: bool = True) -> bool:
        """R13 表情回应：对 seq 消息加/摘（on=False 摘下）emoji。"""
        return self._send_frame({"t": MsgType.REACTION.value, "seq": seq,
                                 "emoji": emoji, "on": on})

    def send_read(self, channel: str, to, seq: int) -> bool:
        """R13 已读回执：报告我在该会话已读到 seq。"""
        header = {"t": MsgType.READ.value, "channel": channel, "seq": seq}
        if to is not None:
            header["to"] = to
        return self._send_frame(header)

    def send_read_detail(self, key: str) -> bool:
        """R33③ 已读详情：请求某会话的已读成员列表（服务器单播回 READ_DETAIL）。"""
        return self._send_frame({"t": MsgType.READ_DETAIL.value, "key": key})

    def send_msg_readers(self, key: str, seq: int) -> bool:
        """C9② 群@已读 by N：请求某条群消息 seq 的已读逐人统计（回帧 MSG_READERS）。"""
        return self._send_frame({"t": MsgType.MSG_READERS.value,
                                 "key": key, "seq": int(seq)})

    def send_typing(self, channel: str = "public", to=None) -> bool:
        """R25A 正在输入：向频道广播 typing 帧（本地 1s/人 限速，服务器亦限速）。"""
        now = time.time()
        if now - self._last_typing_sent < 1.0:
            return False                  # 限速：1s 内只发一帧，防刷屏
        self._last_typing_sent = now
        header = {"t": MsgType.TYPING.value, "channel": channel}
        if to is not None:
            header["to"] = to
        return self._send_frame(header)

    def send_nudge(self, channel: str = "public", to=None, target=None) -> bool:
        """R67 拍一拍：向频道广播 nudge 帧（本地 5s/人 限速，服务器亦限速）。"""
        now = time.time()
        if now - self._last_nudge_sent < 5.0:
            return False                  # 限速：5s 内只发一帧，防骚扰
        self._last_nudge_sent = now
        header = {"t": MsgType.NUDGE.value, "channel": channel, "target": target}
        if to is not None:
            header["to"] = to
        return self._send_frame(header)

    def send_shake(self, channel: str = "public", to=None) -> bool:
        """R68 窗口抖动：向频道广播 shake 帧（本地 10s/人 限速，服务器亦限速）。"""
        now = time.time()
        if now - self._last_shake_sent < 10.0:
            return False                  # 限速：10s 内只发一帧，防骚扰
        self._last_shake_sent = now
        header = {"t": MsgType.SHAKE.value, "channel": channel}
        if to is not None:
            header["to"] = to
        return self._send_frame(header)

    def send_status(self, status: str) -> bool:
        """R68 在线状态：online/away/busy。服务器权威持久并广播 roster。"""
        if status not in ("online", "away", "busy"):
            return False
        return self._send_frame({"t": MsgType.STATUS_SET.value, "status": status})

    def send_remark(self, uid: int, remark: str) -> bool:
        """R69C9 好友备注名：本人视角（服务器按 owner 持久，remark 空=清除）。"""
        return self._send_frame({"t": MsgType.REMARK_SET.value,
                                 "uid": int(uid), "remark": str(remark or "")})

    def display_name(self, uid) -> str:
        """R69C9：展示名优先用本人设置的备注名，无备注回退昵称。"""
        try:
            uid = int(uid)
        except (TypeError, ValueError):
            return str(uid)
        for src in (self.roster.get(uid), self.known.get(uid)):
            if isinstance(src, dict):
                rem = str(src.get("remark") or "").strip()
                if rem:
                    return rem
        for src in (self.roster.get(uid), self.known.get(uid)):
            if isinstance(src, dict) and src.get("nick"):
                return str(src["nick"])
        return f"用户{uid}"

    def send_pin(self, channel: str, to, seq: int, on: bool = True) -> bool:
        """R13 消息置顶：会话级单条置顶/取消。"""
        header = {"t": MsgType.PIN.value, "channel": channel, "seq": seq, "on": on}
        if to is not None:
            header["to"] = to
        return self._send_frame(header)

    def send_purge(self, channel: str, to, until_seq: int) -> bool:
        """R14 会话清理：请求服务器作废 until_seq 之前消息。"""
        header = {"t": MsgType.PURGE.value, "channel": channel,
                  "until_seq": until_seq}
        if to is not None:
            header["to"] = to
        return self._send_frame(header)

    def send_draft(self, channel: str = "public", to=None, text: str = "") -> bool:
        """R29B 草稿同步：把某会话草稿推给服务器（空文本=清除）。
        单 uid 单会话：换端登录时服务器随 welcome 带回全部草稿。"""
        header = {"t": MsgType.DRAFT_SET.value, "channel": channel, "text": text}
        if to is not None:
            header["to"] = to
        return self._send_frame(header)

    # ---------- R36 E2EE 密聊 ----------

    def e2ee_fingerprint(self, peer_uid: int) -> str:
        """与 peer 已建立会话的指纹（emoji 序，人工比对防 MITM；未建立返回空）。"""
        return self.e2ee.peer_fingerprint(int(peer_uid))

    def e2ee_ready(self, peer_uid: int) -> bool:
        """与 peer 的 1v1 密聊会话是否已建立。"""
        return self.e2ee.session_key(int(peer_uid)) is not None

    def start_e2ee(self, to_uid: int, timeout: float = 5.0) -> str | None:
        """发起 1v1 密聊握手（阻塞等对方应答）。成功返回会话指纹，失败 None。

        对方在线时被动方收到 E2EE_PUB 会自动建会话并回 ACK（无需 UI 参与）。
        R42：握手附随机盐 rs 混入根密钥——每次握手根全新，重启不复用旧链。"""
        nonce = os.urandom(8).hex()
        rs = os.urandom(16).hex()
        ev = threading.Event()
        self._e2ee_pending[nonce] = {"to": int(to_uid), "ev": ev, "rs": rs}
        ok = self._send_frame({"t": MsgType.E2EE_PUB.value, "to": int(to_uid),
                               "pub": self.e2ee.identity_pub.hex(), "nonce": nonce,
                               "rs": rs})
        if not ok:
            self._e2ee_pending.pop(nonce, None)
            return None
        if not ev.wait(timeout):
            self._e2ee_pending.pop(nonce, None)
            self._push({"t": "error", "code": "e2ee", "text": "密聊握手超时"})
            return None
        return self.e2ee.peer_fingerprint(int(to_uid))

    def _on_e2ee_pub(self, h: dict) -> None:
        """被动方：收到对方身份公钥 → 建会话 → 回 ACK → 推 e2ee_ready。

        R42：rs 双盐混根；并发重复握手去重——
        - 对方 PUB 到达时我方恰好也在对其握手：nonce 小者做主，败方让位
          （沿用胜方会话，各自 start_e2ee 都能正常返回）；
        - 会话「刚建立且未使用」（10s 内零收发）→ dup-ACK 去重，不覆盖。"""
        try:
            peer = int(h["from"])
            pub = bytes.fromhex(str(h.get("pub") or ""))
            nonce = str(h.get("nonce") or "")
            rs_remote = str(h.get("rs") or "")
        except (KeyError, ValueError):
            return
        # --- 并发去重 1：我方对该 peer 也有进行中的握手 ---
        mine = next(({"nonce": k, **v} for k, v in self._e2ee_pending.items()
                     if v["to"] == peer), None)
        if mine is not None and mine["nonce"] < nonce:   # 我方 nonce 小 → 我方为主
            self._send_frame({"t": MsgType.E2EE_PUB_ACK.value, "to": peer,
                              "pub": self.e2ee.identity_pub.hex(),
                              "nonce": nonce, "dup": 1})
            return                        # 对方收到 dup-ACK 后沿用我方会话
        if mine is not None:              # 让位：对方 nonce 小 → 以对方盐建会话
            self._e2ee_pending.pop(mine["nonce"], None)
            rs_local = os.urandom(16).hex()
            self.e2ee.establish_session(self.uid, peer, pub,
                                        rs_local=rs_local, rs_remote=rs_remote,
                                        legacy_peer=not rs_remote)
            self._send_frame({"t": MsgType.E2EE_PUB_ACK.value, "to": peer,
                              "pub": self.e2ee.identity_pub.hex(), "nonce": nonce,
                              "rs": rs_local, "rv": 2})
            mine["ev"].set()              # 后唤醒：保证 start_e2ee 读得到指纹
            self._push({"t": "e2ee_ready", "peer": peer,
                        "key": e2ee_channel_key(self.uid, peer),
                        "fingerprint": self.e2ee.peer_fingerprint(peer)})
            return
        # --- 并发去重 2：刚握完手（新协议对端）紧接的重复握手 ---
        if self.e2ee.session_fresh(peer):
            self._send_frame({"t": MsgType.E2EE_PUB_ACK.value, "to": peer,
                              "pub": self.e2ee.identity_pub.hex(),
                              "nonce": nonce, "dup": 1})
            return
        rs_local = os.urandom(16).hex()
        self.e2ee.establish_session(self.uid, peer, pub,
                                    rs_local=rs_local, rs_remote=rs_remote,
                                    legacy_peer=not rs_remote)
        self._send_frame({"t": MsgType.E2EE_PUB_ACK.value, "to": peer,
                          "pub": self.e2ee.identity_pub.hex(), "nonce": nonce,
                          "rs": rs_local, "rv": 2})
        self._push({"t": "e2ee_ready", "peer": peer,
                    "key": e2ee_channel_key(self.uid, peer),
                    "fingerprint": self.e2ee.peer_fingerprint(peer)})

    def _on_e2ee_pub_ack(self, h: dict) -> None:
        """发起方：收到应答（nonce 匹配）→ 建会话 → 唤醒阻塞的 start_e2ee。

        R42：rv=2 = 对端为新协议（回带其对端盐）→ 双盐建会话；
        无 rv = 旧版对端 → 双盐缺省（legacy 静态根）；
        dup=1 = 对端告知沿用其已有会话（并发去重）→ 不再覆盖。"""
        try:
            peer = int(h["from"])
            pub = bytes.fromhex(str(h.get("pub") or ""))
        except (KeyError, ValueError):
            return
        nonce = str(h.get("nonce") or "")
        pend = self._e2ee_pending.get(nonce)
        if pend is None or pend["to"] != peer:
            return                      # 陌生 ACK（无匹配 nonce）丢弃
        self._e2ee_pending.pop(nonce, None)
        if h.get("dup"):
            pend["ev"].set()            # 沿用对端已建立会话（并发的胜方会话）
            return
        rs_local = str(pend.get("rs") or "")
        rs_remote = str(h.get("rs") or "") if h.get("rv") else ""
        self.e2ee.establish_session(self.uid, peer, pub,
                                    rs_local=rs_local, rs_remote=rs_remote,
                                    legacy_peer=not h.get("rv"))
        pend["ev"].set()
        self._push({"t": "e2ee_ready", "peer": peer,
                    "key": e2ee_channel_key(self.uid, peer),
                    "fingerprint": self.e2ee.peer_fingerprint(peer)})

    def send_e2ee_chat(self, text: str, to_uid: int, sticker: str = "") -> bool:
        """1v1 密聊发送（R42 链式）：payload 走对称 ratchet 密封——
        每消息独立密钥（HKDF(链, 随机盐)），发送后链步进、旧密钥即弃。
        服务器只见密文；不回发自己 → 本地构造回显（与对方收到的一致）。"""
        to_uid = int(to_uid)
        payload = {"text": text, "sticker": sticker, "ts": _now(), "nick": self.nick}
        try:
            blob = self.e2ee.seal_ratchet(to_uid, payload)
        except E2EEError as exc:
            self._push({"t": "error", "code": "e2ee", "text": f"加密失败: {exc}"})
            return False
        if not self._send_frame({"t": MsgType.E2EE_CHAT.value, "to": to_uid}, blob):
            return False
        msg = {"t": "chat", "channel": "e2ee", "uid": self.uid, "to": to_uid,
               "nick": self.nick, "text": text, "sticker": sticker,
               "ts": payload["ts"], "e2ee": True}
        self._store_chat(msg)
        self._push(msg)
        self._maybe_rotate(to_uid)        # R42：发送计数到期 → 后台 DH 轮转
        return True

    def _on_e2ee_chat(self, h: dict, body: bytes) -> None:
        """1v1 密聊接收（R42 链式解密 + rt1/rt2 轮转控制帧分发）。"""
        try:
            peer = int(h["from"])
        except (KeyError, TypeError, ValueError):
            return
        try:
            payload = self.e2ee.unseal_ratchet(peer, body)
        except E2EEError as exc:
            self._push({"t": "error", "code": "e2ee", "text": f"密聊解密失败: {exc}"})
            return
        rt = payload.get("rt")
        if rt == 1:                       # 被动方：回 rt2（新纪元已在本端生效）
            try:
                blob = self.e2ee.rotate_on_rt1(
                    self.uid, peer, bytes.fromhex(str(payload.get("eph") or "")))
            except (E2EEError, ValueError):
                return
            if blob is not None:
                self._send_frame({"t": MsgType.E2EE_CHAT.value, "to": peer}, blob)
                self._push({"t": "e2ee_rotated", "peer": peer})
            return
        if rt == 2:                       # 发起方：混入新根 → 唤醒轮转线程
            if self.e2ee.rotate_on_rt2(
                    self.uid, peer, bytes.fromhex(str(payload.get("eph") or ""))):
                w = self._e2ee_rot_wait.get(peer)
                if w is not None:
                    w.set()
                self._push({"t": "e2ee_rotated", "peer": peer})
            return
        nick = (self.known.get(peer) or {}).get("nick") or f"用户{peer}"
        msg = {"t": "chat", "channel": "e2ee", "uid": peer, "to": self.uid,
               "nick": nick, "text": str(payload.get("text") or ""),
               "sticker": str(payload.get("sticker") or ""),
               "ts": float(payload.get("ts") or _now()), "e2ee": True}
        self._store_chat(msg)
        self._push(msg)

    # ---------- R42 1v1 密钥轮转 ----------

    def _maybe_rotate(self, peer_uid: int) -> None:
        """发送计数到达 ROTATE_EVERY 且无进行中轮转 → 后台线程发起 DH 轮转。"""
        if not self.e2ee.rotate_due(int(peer_uid)):
            return
        threading.Thread(target=self._rotate_peer, args=(int(peer_uid),),
                         daemon=True, name=f"e2ee-rot-{peer_uid}").start()

    def rotate_e2ee_key(self, peer_uid: int) -> bool:
        """手动触发与 peer 的密钥轮转（菜单入口；返回是否已发起）。"""
        peer = int(peer_uid)
        if not self.e2ee_ready(peer):
            self._push({"t": "error", "code": "e2ee", "text": "密聊会话未建立"})
            return False
        if self.e2ee.is_legacy_peer(peer):
            self._push({"t": "error", "code": "e2ee",
                        "text": "对方是旧版客户端，不支持密钥轮转（对方升级后可用）"})
            return False
        threading.Thread(target=self._rotate_peer, args=(peer,),
                         daemon=True, name=f"e2ee-rot-{peer}").start()
        return True

    def _rotate_peer(self, peer: int, wait: float = 12.0) -> None:
        """轮转执行体：rt1 骑当前发送链发出 → 等 rt2（接收路径回推唤醒）。
        超时放弃（rotate_abort 丢临时私钥）；消息收发不受影响（继续旧链）。"""
        rt1 = self.e2ee.rotate_begin(self.uid, peer)
        if rt1 is None:
            return                        # 已有轮转进行中
        try:
            blob = self.e2ee.seal_ratchet(peer, rt1)
        except E2EEError:
            self.e2ee.rotate_abort(peer)
            return
        ev = threading.Event()
        self._e2ee_rot_wait[peer] = ev
        try:
            if not self._send_frame({"t": MsgType.E2EE_CHAT.value, "to": peer}, blob):
                self.e2ee.rotate_abort(peer)
                return
            ev.wait(wait)
        finally:
            self._e2ee_rot_wait.pop(peer, None)
        if self.e2ee.rotate_pending(peer):
            self.e2ee.rotate_abort(peer)  # 对端无响应：超时兜底

    def open_group_e2ee(self, gid: int, timeout: float = 8.0) -> tuple:
        """开启/轮换群密聊：与无会话成员先补 1v1 握手，全部就绪后
        生成新 epoch 的 sender_key 并经信封分发。返回 (ok, err)。"""
        members = [int(m["uid"]) for m in (self.group_members.get(gid) or [])
                   if m.get("uid") != self.uid]
        if not members:
            return False, "群内没有其他成员"
        pending = []
        for m in members:
            if self.e2ee.session_key(m) is not None:
                continue
            nonce = os.urandom(8).hex()
            rs = os.urandom(16).hex()
            ev = threading.Event()
            self._e2ee_pending[nonce] = {"to": m, "ev": ev, "rs": rs}
            if not self._send_frame({"t": MsgType.E2EE_PUB.value, "to": m,
                                     "pub": self.e2ee.identity_pub.hex(),
                                     "nonce": nonce, "rs": rs}):
                self._e2ee_pending.pop(nonce, None)
                return False, "有成员不在线，无法开启群密聊"
            pending.append((nonce, ev))
        for nonce, ev in pending:
            if not ev.wait(timeout):
                self._e2ee_pending.pop(nonce, None)
                return False, "密聊握手超时"
        # R44 DFSS：切链 + SK_DIST 写 socket 与消息发送同锁——保证接收端
        # 先收新纪元信封、再收该纪元消息（帧序一致，杜绝竞态丢消息）
        with self._send_lock:
            epoch, sk = self.e2ee.new_group_epoch(
                gid, retain_seed=any(m != self.uid and self.e2ee.is_legacy_peer(m)
                                     for m in members))
            envelopes = []
            for m in members:
                k = self.e2ee.session_key(m)
                try:
                    blob = self.e2ee.seal(k, {"sk": sk.hex()})
                except E2EEError as exc:
                    return False, f"密钥封装失败: {exc}"
                envelopes.append({"to": m, "ct": blob.hex()})
            if not self._send_frame({"t": MsgType.E2EE_SK_DIST.value, "gid": gid,
                                     "epoch": epoch, "envelopes": envelopes}):
                return False, "密钥分发失败"
        self._e2ee_groups.add(int(gid))
        self._e2ee_group_members[int(gid)] = frozenset(members + [self.uid])
        return True, ""

    def group_e2ee_on(self, gid: int) -> bool:
        """该群是否已开启密聊（客户端会话态）。"""
        return int(gid) in self._e2ee_groups

    def _on_e2ee_sk_dist_one(self, h: dict) -> None:
        """收到单个 sender key 信封：用与分发者的 1v1 会话密钥解封登记。"""
        try:
            gid = int(h["gid"])
            epoch = int(h.get("epoch") or 0)
            src = int(h["from"])
            ct = bytes.fromhex(str(h.get("ct") or ""))
        except (KeyError, TypeError, ValueError):
            return
        key = self.e2ee.session_key(src)
        if key is None:
            return                      # 未握手无法解封；SK_REQ 流程兜底
        try:
            payload = self.e2ee.unseal(key, ct)
            # R44 DFSS：仅 legacy 发送者保留种子（v1 回退解密依赖）；
            # v2 发送者种子即擦，接收端只留前向链态
            self.e2ee.set_peer_sender_key(
                gid, src, bytes.fromhex(payload["sk"]), epoch,
                retain_seed=self.e2ee.is_legacy_peer(src))
        except (E2EEError, KeyError, ValueError):
            return
        # 被动方语义：收到信封即视为该群密聊已开启（可收可解；发言需自行 open 拿 sender key）
        if gid not in self._e2ee_groups:
            self._e2ee_groups.add(gid)
            members = frozenset(int(m["uid"]) for m in (self.group_members.get(gid) or []))
            if members:
                self._e2ee_group_members[gid] = members

    def _on_e2ee_sk_req(self, h: dict) -> None:
        """密钥补发请求：我开着该群密聊 → 向请求者单发我的 sender key 信封。

        R44 DFSS：种子已擦（纯 v2 组）→ 以全新纪元 re-key 代替补发旧种子
        （旧种子已不可供，新纪元信封即密钥重交付）。"""
        try:
            gid = int(h["gid"])
            src = int(h["from"])
        except (KeyError, TypeError, ValueError):
            return
        if src not in {int(m["uid"]) for m in (self.group_members.get(gid) or [])}:
            return                      # 非本群成员请求 → 忽略（防乱发触发 re-key）
        mine = self.e2ee.my_sender_key(gid)
        if mine is None:
            return
        epoch, sk = mine
        if sk is None:
            if gid not in self._g_rotating:
                self._g_rotating.add(gid)
                threading.Thread(target=self._rotate_group, args=(gid,),
                                 daemon=True, name=f"e2ee-grot-{gid}").start()
            return
        k = self.e2ee.session_key(src)
        if k is None:
            return                      # 与请求者尚未握手（同时上线边角），re-key 时自愈
        try:
            blob = self.e2ee.seal(k, {"sk": sk.hex()})
        except E2EEError:
            return
        self._send_frame({"t": MsgType.E2EE_SK_DIST.value, "gid": gid,
                          "epoch": epoch, "envelopes": [{"to": src, "ct": blob.hex()}]})

    def send_e2ee_group(self, text: str, gid: int, sticker: str = "") -> bool:
        """群密聊发送（R42 链式）：用自己的 sender 链加密（每消息独立密钥，
        接收方按 (gid, from, epoch) 取链解密）。

        混版本兼容：组内任一成员是旧版客户端（legacy_peer）→ 整组降级 v1
        静态 sender key 封装（新版本成员经 v1 回退同样可解）。"""
        gid = int(gid)
        payload = {"text": text, "sticker": sticker, "ts": _now(), "nick": self.nick}
        mine = self.e2ee.my_sender_key(gid)
        if mine is None:
            self._push({"t": "error", "code": "e2ee", "text": "该群未开启密聊"})
            return False
        epoch, sk = mine
        members = self._e2ee_group_members.get(gid) or frozenset()
        mixed_legacy = any(m != self.uid and self.e2ee.is_legacy_peer(m)
                           for m in members)
        if mixed_legacy and sk is None:
            self._push({"t": "error", "code": "e2ee",
                        "text": "该群含旧版成员，密钥轮转后重试"})
            return False
        try:
            if mixed_legacy:
                blob = self.e2ee.seal(sk, payload)      # v1 静态（R36 语义）
            else:
                blob = self.e2ee.seal_group(gid, payload)
        except E2EEError as exc:
            self._push({"t": "error", "code": "e2ee", "text": f"加密失败: {exc}"})
            return False
        if not self._send_frame({"t": MsgType.E2EE_GROUP.value, "gid": gid,
                                 "epoch": epoch}, blob):
            return False
        self._maybe_group_rotate(gid)   # R44 DFSS：计数到期自动 re-key（后台）
        msg = {"t": "chat", "channel": "group", "to": gid, "uid": self.uid,
               "nick": self.nick, "text": text, "sticker": sticker,
               "ts": payload["ts"], "e2ee": True}
        self._store_chat(msg)
        self._push(msg)
        return True

    def _maybe_group_rotate(self, gid: int) -> None:
        """R44 DFSS：群发送计数到达 GROUP_ROTATE_EVERY 且无在途轮转、
        非退避期 → 后台线程 re-key（新纪元 sender key 经 1v1 会话重分发）。"""
        if not self.e2ee.group_rotate_due(int(gid)):
            return
        if gid in self._g_rotating or time.time() < self._g_rot_backoff.get(int(gid), 0):
            return
        self._g_rotating.add(int(gid))
        threading.Thread(target=self._rotate_group, args=(int(gid),),
                         daemon=True, name=f"e2ee-grot-{gid}").start()

    def _rotate_group(self, gid: int) -> None:
        """群 DFSS 轮转执行体：open_group_e2ee 生成新纪元并重分发；
        失败退避 60s（有成员离线/握手超时），消息收发不受影响（继续旧链）。"""
        try:
            ok, err = self.open_group_e2ee(gid)
            if not ok:
                self._g_rot_backoff[int(gid)] = time.time() + 60.0
                self._push({"t": "error", "code": "e2ee",
                            "text": f"群密钥自动轮转失败: {err}"})
        finally:
            self._g_rotating.discard(int(gid))

    def _on_e2ee_group_msg(self, h: dict, body: bytes) -> None:
        """群密聊接收（R42 链式）：按 (gid, 发送者, epoch) 取链解密；
        R44 仅缺 key/缺纪元（no_key）时 SK_REQ 请求补发，重放/篡改静默丢弃
        （防伪造帧触发 SK_REQ → re-key 风暴）。"""
        try:
            gid = int(h["gid"])
            src = int(h["from"])
        except (KeyError, TypeError, ValueError):
            return
        if gid not in self._e2ee_groups:
            return                      # 未开启群密聊 → 静默忽略
        try:
            payload = self.e2ee.unseal_group(gid, src, body)
        except E2EEError as exc:
            if getattr(exc, "code", "") == "no_key":
                self._send_frame({"t": MsgType.E2EE_SK_REQ.value, "gid": gid})
            return
        nick = str(payload.get("nick") or (self.known.get(src) or {}).get("nick")
                   or f"用户{src}")
        msg = {"t": "chat", "channel": "group", "to": gid, "uid": src,
               "nick": nick, "text": str(payload.get("text") or ""),
               "sticker": str(payload.get("sticker") or ""),
               "ts": float(payload.get("ts") or _now()), "e2ee": True}
        self._store_chat(msg)
        self._push(msg)

    # ---------- R37 加密云历史 ----------

    def set_conv_state_hooks(self, provider, applyer) -> None:
        """R39B：注入会话状态采集/应用钩子（云备份打包/恢复时调用）。"""
        self._conv_provider = provider
        self._conv_applyer = applyer

    def cloud_upload(self, password: str) -> tuple[bool, str]:
        """全量本地历史打包加密后上传（服务器只存密文 blob）。阻塞至回执/超时。"""
        if not password:
            return False, "请输入备份口令"
        try:
            channels = self._history.export_all()
            conv = None
            if self._conv_provider is not None:
                try:
                    conv = self._conv_provider() or None
                except Exception:
                    conv = None               # 状态采集失败不阻塞消息备份
            blob = _cloud_pack(channels, self.uid, self.nick, password,
                               conv_states=conv)
        except Exception as exc:
            return False, f"打包失败: {exc}"
        if len(blob) > CLOUD_BLOB_MAX:
            return False, f"备份超过云端上限（{len(blob)} 字节）"
        ev = threading.Event()
        self._cloud_wait["put"] = {"ev": ev, "err": None}
        if not self._send_frame({"t": MsgType.CLOUD_PUT.value,
                                 "size": len(blob), "ts": _now()}, blob):
            self._cloud_wait.pop("put", None)
            return False, "发送失败（未连接）"
        if not ev.wait(15.0):
            self._cloud_wait.pop("put", None)
            return False, "上传超时"
        entry = self._cloud_wait.pop("put", None) or {}
        err = entry.get("err")
        if err:
            return False, err
        n = sum(len(v) for v in channels.values())
        return True, f"已上传 {n} 条消息（{len(blob)} 字节密文）"

    def cloud_restore(self, password: str) -> tuple[bool, str]:
        """从云端拉回密文 blob → 口令解密 → 与本地历史合并（去重）。阻塞至完成。"""
        if not password:
            return False, "请输入备份口令"
        ev = threading.Event()
        self._cloud_wait["get"] = {"ev": ev, "blob": b"", "err": None}
        if not self._send_frame({"t": MsgType.CLOUD_GET.value}):
            self._cloud_wait.pop("get", None)
            return False, "发送失败（未连接）"
        if not ev.wait(15.0):
            self._cloud_wait.pop("get", None)
            return False, "拉取超时"
        entry = self._cloud_wait.pop("get", None) or {}
        if entry.get("err"):
            return False, entry["err"]
        blob = entry.get("blob") or b""
        if not blob:
            return False, "云端没有本账号的备份"
        try:
            data = _cloud_unpack(blob, password)
        except CloudHistoryError as exc:
            return False, str(exc)
        added = self._history.merge_in(data.get("channels") or {})
        extra = ""
        states = data.get("conv_states") or {}      # R39B：会话状态段（旧 blob 为空）
        if states and self._conv_applyer is not None:
            try:
                self._conv_applyer(states)
                extra = f" + {len(states)} 个会话状态"
            except Exception:
                pass                                # 状态应用失败不影响消息恢复
        return True, f"已恢复 {added} 条消息{extra}（云端 {len(blob)} 字节密文）"

    def _on_cloud_data(self, h: dict, body: bytes) -> None:
        """CLOUD_DATA 回帧：blob 交给等待者（size=0 → 空 blob）。"""
        entry = self._cloud_wait.get("get")
        if entry is not None:
            entry["blob"] = bytes(body or b"")
            entry["ev"].set()

    def _on_cloud_done(self, h: dict) -> None:
        """上传回执：唤醒等待者。失败走 error 帧（code=cloud）→ _on_cloud_error。"""
        entry = self._cloud_wait.get("put")
        if entry is not None:
            entry["ev"].set()

    def _on_cloud_error(self, text: str) -> None:
        entry = self._cloud_wait.get("put")
        if entry is not None:
            entry["err"] = text
            entry["ev"].set()
        entry = self._cloud_wait.get("get")
        if entry is not None:
            entry["err"] = text
            entry["ev"].set()

    def latest_seq(self, channel: str = "public", to=None) -> int | None:
        """当前会话最新一条消息的 seq（已读回执取它当"读到哪条"）。"""
        msgs = self.history(channel, to)
        seqs = [m.get("seq") for m in msgs if m.get("seq") is not None]
        return max(seqs) if seqs else None

    def send_private(self, text: str, to_uid: int, sticker: str = "") -> bool:
        return self.send_chat(text, sticker=sticker, channel="private", to=to_uid)

    def send_group(self, text: str, gid: int, sticker: str = "") -> bool:
        return self.send_chat(text, sticker=sticker, channel="group", to=gid)

    def send_edit(self, seq: int, text: str, rich: list | None = None) -> bool:
        """C3 编辑：请求服务器改 seq 对应消息的文本（R59 带富文本段）。"""
        header = {"t": MsgType.MSG_EDIT.value, "seq": seq, "text": text}
        if rich is not None:
            header["rich"] = rich
        return self._send_frame(header)

    def send_del(self, seq: int, scope: str = "self") -> bool:
        """C3 撤回：请求服务器删除 seq 对应消息。

        scope=self 仅本人可删；scope=both 私聊双方可删（对端删除对方消息时用）。
        R53：管理员登录后服务器放行任意频道/任意人的消息。
        """
        return self._send_frame({"t": MsgType.MSG_DEL.value,
                                 "seq": seq, "scope": scope})

    # ---------- R53 服务器管理员（最高清理权限） ----------
    def send_admin_kick(self, uid: int) -> bool:
        """R53 管理员：踢指定用户下线（服务器校验权限，目标端收到 error/kicked）。"""
        return self._send_frame({"t": MsgType.ADMIN_KICK.value, "uid": int(uid)})

    def send_admin_clear_all(self) -> bool:
        """R53 管理员：清空全部聊天记录（服务器广播 cleared，全员清本地历史）。"""
        return self._send_frame({"t": MsgType.CLEAR_ALL.value})

    def send_admin_clear_uid(self, uid: int) -> bool:
        """R53 管理员：清空指定用户全部消息（跨全部频道，广播 cleared/uid）。"""
        return self._send_frame({"t": MsgType.CLEAR_UID.value, "uid": int(uid)})

    def send_admin_user_del(self, target) -> bool:
        """系统管理员：清除用户（删除账号）——target 可为 uid 或已知昵称。
        服务器逐项校验 is_admin；删除账号、清其消息、移出全部群、在线则下线。
        发送后立即从本地 known/roster 缓存剔除，让管理员面板不再显示该账号。"""
        if isinstance(target, int):
            uid = target
        elif isinstance(target, str) and target.strip().isdigit():
            uid = int(target)
        else:
            uid = None
            for coll in (self.known, self.roster):
                for u, info in (coll or {}).items():
                    if info.get("nick") == target:
                        uid = u
                        break
                if uid is not None:
                    break
        if uid is not None:
            for coll in (self.known, self.roster):
                if isinstance(coll, dict):
                    coll.pop(int(uid), None)
        return self._send_frame({"t": MsgType.ADMIN_USER_DEL.value, "uid": target})

    def send_admin_groups(self) -> bool:
        """系统管理员：拉取全量群目录+成员花名册（回帧事件 t=admin_groups_roster）。"""
        return self._send_frame({"t": MsgType.ADMIN_GROUPS.value})

    def send_admin_group_set(self, op: str, gid: int, uid: int | None = None) -> bool:
        """系统管理员：增删成员 / 解散群。
        op: add / remove / dissolve；add&remove 需传 uid，dissolve 传 gid 即可。"""
        header = {"t": MsgType.ADMIN_GROUP_SET.value, "op": op, "gid": int(gid)}
        if uid is not None:
            header["uid"] = int(uid)
        return self._send_frame(header)

    def send_admin_user_groups(self, target) -> bool:
        """系统管理员：查某人信息+所属全部群（target 可为 uid 或已知昵称）。
        回帧事件 t=admin_user_info。"""
        return self._send_frame({"t": MsgType.ADMIN_USER_GET.value, "uid": target})

    def send_invis_set(self, on: bool) -> bool:
        """隐身上线开关：开启后对自己"隐身"，不出现在他人可见名单里。
        服务器权威持久；回帧事件 t=invis_ack 含最新 {on}。"""
        return self._send_frame({"t": MsgType.INV_SET.value, "on": bool(on)})

    def send_admin_force_invis(self, target, on: bool) -> bool:
        """R56B：系统管理员强制某用户显身/隐身（服务器校验）。
        target 可为 uid 或已知昵称。"""
        return self._send_frame({"t": MsgType.ADMIN_INVIS_SET.value,
                                 "uid": target, "on": bool(on)})

    def sched_set(self, text: str, channel: str = "public", to=None,
                  fire_at: float = 0.0) -> bool:
        """R51：创建服务器权威定时消息（离线也会到点发出）。"""
        header = {"t": MsgType.SCHED_SET.value, "channel": channel,
                  "text": text, "fire_at": fire_at}
        if to is not None:
            header["to"] = to
        return self._send_frame(header)

    def sched_cancel(self, rid: str) -> bool:
        """R51：取消我的某条定时消息。"""
        return self._send_frame({"t": MsgType.SCHED_CANCEL.value, "rid": rid})

    def sched_list(self) -> bool:
        """R51：拉取我的待发定时消息（服务器回 SCHED_LIST 帧）。"""
        return self._send_frame({"t": MsgType.SCHED_LIST.value})

    def create_group(self, name: str, broadcast: bool = False,
                     public: bool = False, forum: bool = False) -> bool:
        """建群；broadcast=True 即 R26B 频道广播（仅创建者可发言）；
        forum=True 即 R72 论坛频道（按贴展示，主列表只显示帖子）；
        public=True 即 R54 公开群（所有人可见可直接加入，默认私有）。"""
        header = {"t": MsgType.GROUP_CREATE.value, "name": name}
        if broadcast:
            header["broadcast"] = True
        if forum:
            header["forum"] = True
        if public:
            header["public"] = True
        return self._send_frame(header)

    def join_group(self, gid: int) -> bool:
        self._joined_groups.add(gid)
        return self._send_frame({"t": MsgType.GROUP_JOIN.value, "gid": gid})

    def leave_group(self, gid: int) -> bool:
        self._joined_groups.discard(gid)
        return self._send_frame({"t": MsgType.GROUP_LEAVE.value, "gid": gid})

    def kick_member(self, gid: int, target: int) -> bool:
        """C8 踢人（群主/管理员）。"""
        return self._send_frame({"t": MsgType.GROUP_KICK.value,
                                 "gid": gid, "target": target})

    def mute_member(self, gid: int, target: int, duration: int) -> bool:
        """C8 禁言（duration<=0 解禁；省略用服务器默认时长）。"""
        return self._send_frame({"t": MsgType.GROUP_MUTE.value,
                                 "gid": gid, "target": target, "duration": duration})

    def set_admin(self, gid: int, target: int, enable: bool) -> bool:
        """C8 设/撤管理员（仅群主）。"""
        return self._send_frame({"t": MsgType.GROUP_SET_ADMIN.value,
                                 "gid": gid, "target": target, "enable": enable})

    def request_history(self, channel: str = "public", to=None) -> bool:
        header = {"t": MsgType.HISTORY.value, "channel": channel}
        if to is not None:
            header["to"] = to
        return self._send_frame(header)

    def request_stickers(self) -> bool:
        return self._send_frame({"t": MsgType.STICKER_LIST.value})

    def request_sticker_shop(self) -> bool:
        """R35 拉贴纸商店目录（服务器回 sticker_shop_list：packs+当前订阅）"""
        return self._send_frame({"t": MsgType.STICKER_SHOP.value})

    def send_sticker_sub(self, pack_id: str, on: bool) -> bool:
        """R35 订阅/退订表情包（回帧带全量订阅，客户端覆盖本地状态）"""
        return self._send_frame({"t": MsgType.STICKER_SUB.value,
                                 "pack_id": pack_id, "on": bool(on)})

    def subscribed_stickers(self) -> list:
        """R35 当前订阅包的全部表情条目（表情面板渲染用；无订阅回退默认包）"""
        subs = set(self.sticker_subs or ["basic"])
        out = []
        for p in self.sticker_shop or []:
            if p.get("pack_id") in subs:
                out.extend(p.get("items") or [])
        if not out:                      # 商店目录未拉取时回退服务器内置平铺
            out = self.stickers
        return out

    def ping(self) -> bool:
        return self._send_frame({"t": MsgType.PING.value})

    # ---------- 游戏 API ----------
    def game_list(self) -> bool:
        return self._send_frame({"t": MsgType.GAME_LIST.value})

    def game_create(self, game: str) -> bool:
        return self._send_frame({"t": MsgType.GAME_CREATE.value, "game": game})

    def game_join(self, room_id: str) -> bool:
        return self._game_reentry(MsgType.GAME_JOIN, room_id)

    def game_spectate(self, room_id: str) -> bool:
        return self._game_reentry(MsgType.GAME_SPECTATE, room_id)

    def _game_reentry(self, kind: MsgType, room_id: str) -> bool:
        rid = str(room_id)
        was_left = rid in self._game_left_rooms
        self._game_left_rooms.discard(rid)  # 接收线程可能在发送返回前处理新房间状态。
        sent = self._send_frame({"t": kind.value, "room_id": room_id})
        if not sent and was_left and (self.game_room or {}).get("room_id") != rid:
            self._game_left_rooms.add(rid)
        return sent

    def game_leave(self, room_id: str) -> bool:
        return self._send_frame({"t": MsgType.GAME_LEAVE.value, "room_id": room_id})

    def game_start(self, room_id: str) -> bool:
        return self._send_frame({"t": MsgType.GAME_START.value, "room_id": room_id})

    def game_action(self, room_id: str, action: dict) -> bool:
        return self._send_frame({"t": MsgType.GAME_ACTION.value,
                                 "room_id": room_id, "action": action})

    # R70H 摸鱼排行榜（opt-in：调用方负责先确认用户开关；服务器亦有开关兜底）
    def send_fish_score(self, game: str, score: int = 1) -> bool:
        """上报本会话摸鱼积分（服务器累加后广播该游戏排行榜）。"""
        rid = str(game or "").strip()
        if not rid:
            return False
        return self._send_frame({"t": MsgType.FISH_SCORE.value,
                                 "game": rid, "score": int(score)})

    def request_fish_board(self, game: str) -> bool:
        """拉取某游戏排行榜（回帧落到 self.fish_board[game]）。"""
        rid = str(game or "").strip()
        if not rid:
            return False
        return self._send_frame({"t": MsgType.FISH_BOARD.value, "game": rid})

    def history(self, channel: str = "public", to=None) -> list:
        """本地历史快照（GUI 渲染用）"""
        key = _channel_key(channel, self.uid or 0, to)
        return self._history.load(key)

    def history_tail(self, channel: str = "public", to=None, n: int = 100) -> list:
        """R39C 懒加载：会话最新一页（磁盘 JSONL 按行号索引读，升序去重）。"""
        return self._history.page_tail(_channel_key(channel, self.uid or 0, to), n)

    def history_page(self, channel: str = "public", to=None,
                     before_seq: int = 0, n: int = 100) -> list:
        """R39C 懒加载：seq<before_seq 的更旧一页（MsgList 滚到顶触发）。"""
        return self._history.page_before(_channel_key(channel, self.uid or 0, to),
                                         before_seq, n)

    def history_after(self, channel: str = "public", to=None,
                      after_seq: int = 0, n: int = 100) -> list:
        """R39C 懒加载：seq>after_seq 的更新一页（正向窗口备用）。"""
        return self._history.page_after(_channel_key(channel, self.uid or 0, to),
                                        after_seq, n)

    def drop_history(self, channel: str = "public", to=None) -> None:
        """删除某会话本地记录（右键菜单「删除会话记录」）"""
        self._history.drop(_channel_key(channel, self.uid or 0, to))

    # ---------- R50 屏蔽名单 ----------
    def set_block(self, target: int, on: bool) -> bool:
        """屏蔽/解除某用户（服务器权威持久化；结果经 block_list 帧反馈）。"""
        ok = self._send_frame({"t": MsgType.BLOCK_SET.value, "target": int(target),
                               "on": bool(on)})
        if ok:
            # 本地先行反映（服务器回帧也会再同步一次，幂等）
            if on:
                self.blocked.add(int(target))
            else:
                self.blocked.discard(int(target))
        return ok

    def request_blocks(self) -> None:
        """重连/换端后主动拉一次我的屏蔽名单（服务器回 block_list 帧）。"""
        self._send_frame({"t": MsgType.BLOCK_LIST.value})

    # ---------- 内部 ----------
    def _send_frame(self, header: dict, body: bytes = b"") -> bool:
        if getattr(self, "_manual_login_required", False):
            return False
        chan = self._chan
        if chan is None or not self._conn_alive.is_set():
            self._push({"t": "error", "code": "offline", "text": "未连接"})
            return False
        try:
            with self._send_lock:
                if getattr(self, "_manual_login_required", False):
                    return False
                chan.send_frame(header, body)
            return True
        except (OSError, ValueError) as exc:
            self._push({"t": "error", "code": "send", "text": f"发送失败: {exc}"})
            return False

    # 瞬时事件：可丢（重连/刷新即再生），用于事件队列满时的降级保护
    _TRANSIENT = frozenset({"pong", "state", "roster", "sticker_list",
                            "sticker_shop_list", "sticker_sub",
                            "sticker_pack_cover_data"})

    def _push(self, ev: dict) -> None:
        try:
            self.events.put_nowait(ev)
        except queue.Full:
            if ev.get("t") in self._TRANSIENT:
                return                    # 瞬时事件可丢，消息类绝不丢
            self.events.put(ev)           # 消息/关键事件：背压等待，绝不丢
        cb = self._on_event
        if cb is not None:
            try:
                cb(ev)
            except Exception:
                pass

    def _set_state(self, state: str) -> None:
        with self._lock:
            self.state = state
        self._push({"t": "state", "state": state})
