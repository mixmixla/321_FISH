# -*- coding: utf-8 -*-
"""R9 全局消息搜索冒烟：Ctrl+Shift+F 打开结果窗、输词后台扫磁盘全量命中、
点结果切会话并高亮定位；既有 Ctrl+F 会话内搜索不受影响。"""
import os
import tempfile
import time

from config import CFG
from client_core import ClientCore, LocalHistory
from client import ChatWindow


def main() -> int:
    import os as _os
    import tempfile as _tf
    tmp = _tf.mkdtemp(prefix="r9gs_")
    hist_dir = _os.path.join(tmp, "history")
    lh = LocalHistory(hist_dir, max_in_mem=CFG.chat_history_max)
    lh.add("public", {"seq": 1, "text": "冒烟关键词甲 例会", "uid": 1, "ts": 1})
    lh.add("private:1:9", {"seq": 1, "text": "帮我看下冒烟关键词乙布局", "nick": "乙方", "uid": 9, "ts": 2})
    lh.add("group:7", {"seq": 1, "text": "冒烟关键词丙 记得归档", "nick": "丙", "uid": 8, "ts": 3})
    lh._flush()                       # 强制落盘，保证磁盘扫描可见

    core = ClientCore(host="127.0.0.1", port=1, nick="冒烟")
    core.uid = 1
    core.roster = {9: {"uid": 9, "nick": "乙方"}}
    core.groups = {7: {"gid": 7, "name": "部门群"}}
    core._history = lh

    prefs_path = _os.path.join(tmp, "prefs.json")
    app = ChatWindow(core, prefs_path=prefs_path)

    ok = True
    results = []

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    def pump(secs: float):
        t = time.time() + secs
        while time.time() < t:
            app.root.update()
            time.sleep(0.02)

    try:
        # 快捷键已注册，handler 指向 _focus_global_search
        bound_f = [h for p, h in app._bound if p == "<Control-Shift-f>"]
        check("ctrl_shift_f registered",
              any(h == app._focus_global_search for h in bound_f),
              str(bound_f[:1]))

        # 打开结果窗
        app._focus_global_search()
        pump(0.4)
        box = app._global_search_box
        check("box opened", box is not None and box.winfo_exists())
        check("box has entry+listbox",
              hasattr(box, "entry") and hasattr(box, "listbox"))

        # 输词触发后台扫描 → 命中公共/私聊/群 三会话
        box.entry.insert(0, "冒烟关键词")
        box._start_scan()               # 直接触发（绕过防抖）
        pump(0.8)
        n = box.listbox.size()
        items = [box.listbox.get(i) for i in range(n)]
        check("3 sessions hit", n == 3, ",".join(items))
        name_set = {it.split("(")[0].strip() for it in items}
        check("names resolved", {"公共频道", "乙方", "部门群"} <= name_set,
              str(name_set))
        check("count shows", "3 个会话" in box.count_lb.cget("text"),
              box.count_lb.cget("text"))

        # 选「公共频道」→ on_pick → 切会话并高亮
        for i in range(n):
            if "公共频道" in box.listbox.get(i):
                box.listbox.selection_clear(0, "end")
                box.listbox.selection_set(i)
                box._pick_sel()
                break
        pump(0.4)
        check("switched to public", app.view == ("public", None), str(app.view))
        check("jump highlighted hit", app.msg_list.search_count() >= 1,
              f"hits={app.msg_list.search_count()}")

        # 既有 Ctrl+F 会话内搜索仍可用（不回归）
        app.chat_search_entry.insert(0, "甲")
        app._do_chat_search()
        pump(0.3)
        check("in-session ctrl_f intact", app.msg_list.search_count() >= 1,
              f"hits={app.msg_list.search_count()}")
        app._close_chat_search()
    finally:
        try:
            box.destroy()
        except Exception:
            pass
        app.quit_app()
        try:
            lh.close()
        except Exception:
            pass

    print("\n".join(results))
    print("GUI GLOBAL SEARCH SMOKE OK" if ok else "GUI GLOBAL SEARCH SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())