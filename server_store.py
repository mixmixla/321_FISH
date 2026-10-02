# -*- coding: utf-8 -*-
"""服务器全状态持久化（R16）：单一 JSON 快照文件，进程重启后恢复消息/会话状态。

采用「全量快照 + 原子替换」，不做增量日志：
- 消息在 edit/del/reaction 是原地改，全量序列化 _channels 天然捕获这些改动；
- 单文件原子替换（.tmp + os.replace）保证崩溃时要么旧完整快照要么新完整快照，
  绝无半写；
- 只维护最新一份快照（权威态，非审计留底），不做按天轮转。

与 audit.py 的关系：audit 只记元数据/留底、可删；本模块存聊天正文与全部会话
状态、只留最新。二者职责不同，分开落盘。
"""
import json
import os
import threading


class ServerStore:
    """线程安全的全量快照持久化。纯 IO，不含计时/节流（节流交给 Hub）。"""

    def __init__(self, path: str) -> None:
        self._path = os.path.abspath(path)
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self._path), exist_ok=True)

    def load(self) -> dict:
        """读 state.json；缺失/JSON 损坏/残留 .tmp → 返回 {}，绝不抛异常。"""
        with self._lock:
            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                return data if isinstance(data, dict) else {}
            except (OSError, ValueError, TypeError):
                return {}

    def save(self, state: dict) -> bool:
        """原子写快照并报告真实结果。

        ``True`` 只表示 JSON 编码、flush、fsync 和 replace 全部完成；任一
        阶段失败都返回 ``False``，保留旧的 state.json。调用方据此推进
        fingerprint/确认状态，不能把临时文件存在误当成持久成功。
        """
        tmp = self._path + ".tmp"
        with self._lock:
            try:
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(state, fh, ensure_ascii=False, separators=(",", ":"))
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, self._path)
                return True
            except Exception:
                # encode/open/write/flush/fsync/replace 任一阶段失败时，旧
                # 快照仍是唯一可确认内容；临时文件仅作失败清理对象。
                try:
                    os.remove(tmp)           # replace 失败则清残留，保留旧快照
                except OSError:
                    pass
                return False
