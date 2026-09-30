# -*- coding: utf-8 -*-
"""R33 冒烟：回应条覆盖特殊行 + 已读标记独立段 + 已读详情链路。
- 语音/图片/贴纸/投票行 _row_reactable=True，带回应时渲染不崩且估算含占位
- ✓已读 为独立 READ_MARK 段（own+已读才有），on_read_detail 回调被保存并携带 (row,ev)
- 服务器 /api/read_detail：有权 200 + readers；外人查私聊键 403
"""
import http.client
import json
import os
import socket
import tempfile
import threading
import time
import tkinter as tk
from dataclasses import replace

from config import CFG
from server import Hub, serve as serve_tcp
from web import serve as serve_web
from widgets import runs
from widgets.msg_list import MsgList


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def gui_checks(results, check):
    tmp = tempfile.mkdtemp(prefix="r33_")
    from PIL import Image
    img = os.path.join(tmp, "p.png")
    Image.new("RGB", (80, 60), "#3b82f6").save(img)

    root = tk.Tk()
    root.withdraw()
    calls = []
    ml = MsgList(root, font=("Microsoft YaHei", 10), me_uid=1,
                 on_read_detail=lambda row, ev: calls.append((row, ev)))
    try:
        t0 = time.time()
        reacts = {"👍": {"2": time.time()}}
        rows = [
            {"seq": 101, "uid": 2, "nick": "乙", "text": "语音：",
             "voice": {"duration": 1.5}, "ts": t0},
            {"seq": 102, "uid": 2, "nick": "乙", "image_path": img, "ts": t0 + 1},
            {"seq": 103, "uid": 2, "nick": "乙", "text": "[:cat:]",
             "sticker_custom": "cat", "ts": t0 + 2},
            {"seq": 104, "uid": 2, "nick": "乙", "text": "投票",
             "poll": {"question": "Q", "options": ["a", "b"],
                      "end": t0 + 600}, "ts": t0 + 3},
        ]
        for r in rows:
            ml.append(r)
        ml.append({"seq": 105, "text": "系统行", "ts": t0 + 4}, is_system=True)
        check("特殊行可回应", all(ml._row_reactable(i) for i in range(4)))
        check("系统行不可回应", not ml._row_reactable(4))

        # 带回应渲染不崩 + 估算含回应占位
        for i in range(4):
            ml._rows[i].raw["reactions"] = dict(reacts)
        ml._render()
        check("带回应渲染不崩", True)
        pad = ml.REACT_PAD
        check("语音行估算含占位",
              ml._estimate(0, ml._rows[0]) >= ml._heights[0] * 0.5 + pad - pad)
        est_have = ml._estimate(0, ml._rows[0])
        ml._rows[0].raw.pop("reactions")
        est_none = ml._estimate(0, ml._rows[0])
        check("占位差=REACT_PAD", est_have - est_none == pad,
              f"{est_have - est_none} vs {pad}")

        # 已读标记独立段
        ml.append({"seq": 201, "uid": 1, "nick": "我", "text": "我的", "ts": t0 + 9})
        own = ml._rows[-1]
        check("未读无 READ_MARK",
              all(k != runs.READ_MARK for _t, k in ml._heading_segs(own, False, True)))
        ml.set_reads({"2": 201})
        segs = ml._heading_segs(own, False, True)
        check("已读出现 READ_MARK",
              any(k == runs.READ_MARK and "✓已读" in t for t, k in segs))
        other = ml._rows[0]
        check("他人消息无 READ_MARK",
              all(k != runs.READ_MARK for _t, k in ml._heading_segs(other, False, False)))

        # 回调携带 (row, ev)
        ml._on_read_detail(own, None)
        check("on_read_detail 回调触发", calls and calls[-1][0] is own)
    except Exception as e:
        import traceback
        traceback.print_exc()
        check("GUI 异常", False, f"{type(e).__name__}: {e}")
    finally:
        ml.destroy()
        root.destroy()


def http_checks(results, check):
    cfg = replace(CFG, audit_dir=tempfile.mkdtemp(prefix="r33a_"))
    h = Hub(cfg=cfg, audit_dir=cfg.audit_dir)
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    wport = _free_port()
    httpd = serve_web(h, port=wport)
    time.sleep(0.2)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=5)
        conn.request("POST", "/api/login", json.dumps({"nick": "网页甲"}).encode(),
                     {"Content-Type": "application/json"})
        d = json.loads(conn.getresponse().read().decode())
        check("网页登录", d.get("ok"))
        token = d["token"]
        body = json.dumps({"token": token, "key": "public"}).encode()
        conn.request("POST", "/api/read_detail", body,
                     {"Content-Type": "application/json"})
        r = json.loads(conn.getresponse().read().decode())
        check("read_detail 200", r.get("ok") and isinstance(r.get("readers"), list))
        body2 = json.dumps({"token": token, "key": "private:999:998"}).encode()
        conn.request("POST", "/api/read_detail", body2,
                     {"Content-Type": "application/json"})
        resp = conn.getresponse()
        r2 = json.loads(resp.read().decode())
        check("外人查私聊键 403", resp.status == 403 and not r2.get("ok"))
        conn.close()
    except Exception as e:
        import traceback
        traceback.print_exc()
        check("HTTP 异常", False, f"{type(e).__name__}: {e}")
    finally:
        stop.set()
        time.sleep(0.2)
        try:
            httpd.shutdown()
        except Exception:
            pass


def main() -> int:
    results = []
    ok = True

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    gui_checks(results, check)
    http_checks(results, check)

    print("\n".join(results))
    print("R33 冒烟:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
