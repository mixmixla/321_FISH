# -*- coding: utf-8 -*-
"""R34 群内话题 Threads 冒烟：
- MsgList 徽标：set_thread_count → 估算增高 / 归零摘除 / 点击回调携带 row
- ThreadWindow：load_msgs 按 root 过滤去重升序 / append_msg 实时去重 /
  双击引用快照 + 发送自动清引用（send 回调收到 thread_root 由 ChatWindow 侧负责）
"""
import time
import tkinter as tk

from widgets.msg_list import MsgList
from widgets.thread_window import ThreadWindow


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    ok = True
    results = []

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    def pump(secs):
        t = time.time() + secs
        while time.time() < t:
            root.update()
            time.sleep(0.02)

    try:
        # 1. 徽标点击链路
        opened = []
        ml = MsgList(root, font=("Microsoft YaHei", 10), me_uid=1,
                     on_open_thread=lambda row: opened.append(row))
        ml.configure(width=420, height=360)
        ml.pack()
        t0 = time.time()
        ml.append({"seq": 10, "uid": 2, "nick": "乙", "channel": "public",
                   "ts": t0, "text": "这是根消息"})
        ml.append({"seq": 11, "uid": 2, "nick": "乙", "channel": "public",
                   "ts": t0 + 1, "text": "普通消息"})
        pump(0.3)
        est0 = ml._estimate(0, ml._rows[0])
        ml.set_thread_count(10, 2)
        pump(0.2)
        check("徽标计数生效", ml._rows[0].raw.get("thread_count") == 2)
        check("徽标增高占位",
              ml._estimate(0, ml._rows[0]) == est0 + ml._thread_badge_h(ml._rows[0]))
        ml._render()
        ml._on_open_thread(ml._rows[0])
        check("点击回调携带根 row", opened and opened[-1].raw.get("seq") == 10)
        ml.set_thread_count(10, 0)
        check("归零摘除", "thread_count" not in ml._rows[0].raw)
        ml.destroy()

        # 2. ThreadWindow 行为
        sent = []
        tw = ThreadWindow(
            root, root_msg={"seq": 10, "uid": 2, "nick": "乙", "text": "这是根消息"},
            key="public", me_uid=1,
            make_msglist=lambda p: MsgList(p, font=("Microsoft YaHei", 10),
                                           me_uid=1,
                                           on_row_double=lambda idx: tw and
                                           tw.set_reply(idx)),
            send=lambda text, reply=None: sent.append((text, reply)))
        tw.load_msgs([
            {"seq": 10, "uid": 2, "nick": "乙", "text": "这是根消息"},
            {"seq": 12, "uid": 3, "nick": "丙", "text": "回B", "thread_root": 10},
            {"seq": 11, "uid": 1, "nick": "我", "text": "回A", "thread_root": 10},
            {"seq": 13, "uid": 2, "nick": "乙", "text": "别人的话题", "thread_root": 99},
        ])
        pump(0.3)
        body = tw.msg_list.body_text(0) if tw.msg_list.count else ""
        check("窗口仅装本话题回复", tw.msg_list.count == 2,
              f"count={tw.msg_list.count}")
        check("回复按 seq 升序", body.startswith("回A"), body[:12])
        # 实时追加 + 去重
        tw.append_msg({"seq": 14, "uid": 3, "nick": "丙", "text": "回C",
                       "thread_root": 10})
        tw.append_msg({"seq": 14, "uid": 3, "nick": "丙", "text": "回C重复",
                       "thread_root": 10})
        pump(0.2)
        check("append 去重", tw.msg_list.count == 3)
        # 引用 + 发送
        tw.set_reply(1)                        # 双击第 1 条（排序后=回B, seq12）
        tw.entry.insert(0, "窗口内回复")
        tw._do_send()
        pump(0.2)
        check("发送带引用", sent and sent[0][0] == "窗口内回复" and
              sent[0][1] and sent[0][1].get("seq") == 12 and
              sent[0][1].get("text") == "回B", str(sent))
        check("发送后清引用", tw._reply is None)
        tw.destroy()
        pump(0.2)
    except Exception as e:
        import traceback
        traceback.print_exc()
        check("GUI 异常", False, f"{type(e).__name__}: {e}")
    finally:
        root.destroy()

    print("\n".join(results))
    print("R34 冒烟:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
