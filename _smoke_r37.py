# -*- coding: utf-8 -*-
"""R37 加密云历史冒烟（真服务器 + 真客户端核心）：
- 甲聊天 → 加密上传 → 服务器 .bin/audit 均无明文
- 同昵称重登（同 uid，新历史目录=模拟换设备）→ 口令解密恢复 → 内容一致
- 再恢复不重复（去重）；错口令拒解；从未上传者提示云端无备份
"""
import os
import socket
import tempfile
import threading
import time
from dataclasses import replace

from client_core import ClientCore
from config import CFG
from server import Hub, serve as serve_tcp


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="r37_")
    ok = True
    results = []

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    stop = threading.Event()
    try:
        cfg = replace(CFG, audit_dir=os.path.join(tmp, "audit"),
                      web_files_dir=os.path.join(tmp, "web"))
        hub = Hub(cfg=cfg, audit_dir=os.path.join(tmp, "audit"))
        port = _free_port()
        threading.Thread(target=serve_tcp, args=(hub, port, stop, False),
                         daemon=True).start()
        time.sleep(0.2)

        a = _spawn(port, "甲", tmp, "")
        a._store_chat({"t": "chat", "channel": "public", "uid": a.uid,
                       "nick": "甲", "text": "冒烟云备份#1", "seq": 1, "ts": 1.0})
        ok1, msg1 = a.cloud_upload("冒烟口令")
        check("加密上传", ok1, msg1)

        bin_path = os.path.join(tmp, "web", "cloud", f"{a.uid}.bin")
        raw = open(bin_path, "rb").read() if os.path.isfile(bin_path) else b""
        check("云端 .bin 无明文", "冒烟云备份#1".encode() not in raw)
        audit_raw = "".join(
            open(os.path.join(tmp, "audit", fn), "r", encoding="utf-8",
                 errors="ignore").read()
            for fn in (os.listdir(os.path.join(tmp, "audit"))
                       if os.path.isdir(os.path.join(tmp, "audit")) else []))
        check("audit 无明文", "冒烟云备份#1" not in audit_raw)

        a.stop()
        time.sleep(0.3)
        b = _spawn(port, "甲", tmp, "_newdev")        # 换设备：同 uid 新历史
        check("同昵称复用 uid", b.uid == a.uid)
        ok2, msg2 = b.cloud_restore("冒烟口令")
        check("口令解密恢复", ok2, msg2)
        pub = b._history.load_disk("public")
        check("恢复内容一致",
              any(m.get("text") == "冒烟云备份#1" for m in pub))
        ok3, _ = b.cloud_restore("冒烟口令")
        check("重复恢复去重", ok3 and "0 条" in _)

        bad_ok, bad_msg = b.cloud_restore("错误口令")
        check("错口令拒解", not bad_ok and "解密失败" in bad_msg, bad_msg)
        c = _spawn(port, "乙", tmp, "")
        check("无备份提示", "没有" in _noop_restore(c))

        a.stop(); b.stop(); c.stop()
    except Exception as e:
        import traceback
        traceback.print_exc()
        check("异常", False, f"{type(e).__name__}: {e}")
    finally:
        stop.set()
        time.sleep(0.2)

    print("\n".join(results))
    print("R37 冒烟:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


def _noop_restore(core):
    _ok, msg = core.cloud_restore("任意口令")
    return msg


def _spawn(port, nick, tmp, sub):
    events = []
    core = ClientCore(host="127.0.0.1", port=port, nick=nick,
                      history_dir=os.path.join(tmp, f"h_{nick}{sub}"),
                      on_event=events.append)
    core.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        if any(e.get("t") == "welcome" for e in events):
            break
        time.sleep(0.02)
    return core


if __name__ == "__main__":
    raise SystemExit(main())
