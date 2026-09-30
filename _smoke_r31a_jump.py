# -*- coding: utf-8 -*-
"""R31A（jump-to-bottom 浮动按钮 + 未读计数）冒烟：
- 默认按钮隐藏
- 滚离底部 → 按钮出现
- 离底期间收到新消息 → 按钮「⬇ N」计数
- 点按钮 → 回到底部、按钮收起、计数清零
- 未读分隔线优先计数
"""
import time
import tkinter as tk

from widgets.msg_list import MsgList

PAL = {"bg": "#ffffff", "self": "#2ea6ff"}


def main() -> int:
    root = tk.Tk()
    root.geometry("420x600")
    ml = MsgList(root, ("Microsoft YaHei UI", 10), colors=PAL, me_uid=1)
    ml.pack(fill="both", expand=True)

    ok = True
    results = []

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    def pump(secs: float):
        t = time.time() + secs
        while time.time() < t:
            root.update()
            time.sleep(0.02)

    try:
        pump(0.3)
        # 1. 默认隐藏
        check("初始按钮隐藏", not ml._jump_btn.winfo_manager())

        # 2. 装载 60 条消息（钉底）
        msgs = [{"seq": i, "from": i % 2 + 1, "text": f"消息 {i} 测试滚动",
                 "ts": 1700000000 + i} for i in range(1, 61)]
        ml.load(msgs, me_uid=1)
        pump(0.5)
        check("装载后钉底隐藏", not ml._jump_btn.winfo_manager())
        check("装载后到底", ml.yview()[1] >= 0.999)

        # 3. 滚离底部 → 按钮出现（无计数）
        ml.yview_moveto(0.5)
        ml._set_stick_from_view()
        ml._render()
        pump(0.3)
        check("滚离底部按钮出现", ml._jump_btn.winfo_manager() == "place")
        check("无未读时无计数", str(ml._jump_btn.cget("text")) == "⬇",
              ml._jump_btn.cget("text"))

        # 4. 离底期间新消息 → 计数
        for i in range(61, 65):
            ml.append({"seq": i, "from": 2, "text": f"新消息 {i}",
                       "ts": 1700000000 + i})
        ml._update_jump_btn()
        pump(0.4)
        check("离底新消息计数", str(ml._jump_btn.cget("text")) == "⬇ 4",
              ml._jump_btn.cget("text"))
        check("仍在底部之上", ml.yview()[1] < 0.999)

        # 5. 未读分隔线优先计数
        ml.set_unread_seq(60)
        ml._update_jump_btn()
        pump(0.2)
        check("未读分隔线计数优先", str(ml._jump_btn.cget("text")) == "⬇ 4",
              ml._jump_btn.cget("text"))

        # 6. 点击按钮 → 回到底部、收起、清零、撤未读线
        ml._jump_bottom()
        pump(0.4)
        check("点击后按钮收起", not ml._jump_btn.winfo_manager())
        check("点击后回到钉底", ml._at_bottom and ml.yview()[1] >= 0.999,
              f"at_bottom={ml._at_bottom} yview={ml.yview()}")
        check("离底计数清零", ml._jump_new == 0)
        check("点击后撤未读线", ml._unread_seq is None)

        # 7. 主题切换按钮颜色跟随
        ml.set_colors({"self": "#ff5500"})
        check("按钮颜色跟随主题", ml._jump_btn.cget("bg") == "#ff5500",
              ml._jump_btn.cget("bg"))
    except Exception as e:
        ok = False
        results.append(f"[FAIL] 异常: {type(e).__name__}: {e}")
    finally:
        root.destroy()

    print("\n".join(results))
    print("R31A 冒烟:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
