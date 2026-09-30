# -*- coding: utf-8 -*-
"""服务器审计日志：JSONL 按天轮转，只记元数据（不存聊天内容），保留最近 N 天。

留底复盘：谁 / 何时 / 从哪 / 做了什么 —— 登录、下线、发消息（不含正文）、
建群/进群/退群、踢人、网页端进出。聊天正文只存在于客户端本地历史与服务器
内存环形缓冲（到期淘汰），落盘审计不写内容，隐私与"留底"两头兼顾。
"""
import glob
import json
import os
import threading
import time


class AuditLog:
    """线程安全追加式审计日志（audit-YYYYMMDD.jsonl，按天轮转）"""

    def __init__(self, base_dir: str = "audit", keep_days: int = 7) -> None:
        self._dir = os.path.abspath(base_dir)
        self._keep_days = max(1, int(keep_days))
        self._lock = threading.Lock()
        os.makedirs(self._dir, exist_ok=True)
        self._day = None
        self._fh = None
        self._rotate()

    # ---- 内部 ----
    def _path(self, day: str) -> str:
        return os.path.join(self._dir, f"audit-{day}.jsonl")

    def _rotate(self) -> None:
        day = time.strftime("%Y%m%d")
        if self._day == day:
            return
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
        self._day = day
        self._fh = open(self._path(day), "a", encoding="utf-8")
        self._purge_old()

    def _purge_old(self) -> None:
        cutoff = time.time() - self._keep_days * 86400
        for p in glob.glob(os.path.join(self._dir, "audit-*.jsonl")):
            try:
                if os.path.getmtime(p) < cutoff:
                    os.remove(p)
            except OSError:
                pass

    # ---- 对外 ----
    def log(self, **fields) -> None:
        """记一条审计事件；None 字段自动丢弃"""
        fields = {k: v for k, v in fields.items() if v is not None}
        fields.setdefault("ts", round(time.time(), 3))
        fields.setdefault("time", time.strftime("%Y-%m-%d %H:%M:%S"))
        line = json.dumps(fields, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self._rotate()
            self._fh.write(line + "\n")
            self._fh.flush()

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.close()
                except OSError:
                    pass
                self._fh = None

    def recent(self, limit: int = 50, type_prefix: str = "") -> list:
        """返回今日审计最近 limit 条（旧→新）。type_prefix 非空则只保留该前缀的事件。"""
        try:
            with self._lock:
                p = self._path(time.strftime("%Y%m%d"))
                if not os.path.exists(p):
                    return []
                with open(p, "r", encoding="utf-8") as f:
                    lines = f.readlines()
        except OSError:
            return []
        out = []
        for ln in lines:
            try:
                e = json.loads(ln)
            except (ValueError):
                continue
            if type_prefix and not str(e.get("type", "")).startswith(type_prefix):
                continue
            out.append(e)
        return out[-limit:]
