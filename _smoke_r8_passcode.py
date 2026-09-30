# -*- coding: utf-8 -*-
"""R8 冒烟：PasscodeBox 交互（空/错/对码 → 红字 / on_ok / 关闭）。"""
import tkinter as tk
from widgets.passcode import PasscodeBox


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    results = []
    ok = True

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    correct = "0000"
    ok_flag = {"hit": 0}
    box = PasscodeBox(root, title="解锁", verifier=lambda c: c == correct,
                      on_ok=lambda: ok_flag.__setitem__("hit", 1))

    def pump():
        root.update()

    # 1) 空码 → 红字提示，不触发 on_ok，窗口仍在
    box.entry.insert(0, "   ")
    box._submit()
    pump()
    check("empty shows error", "请输入解锁码" in box.err["text"], box.err["text"])
    check("empty keeps window", box.winfo_exists())

    # 2) 错码 → 红字+select_all，窗口仍在
    box.entry.delete(0, "end")
    box.entry.insert(0, "9999")
    box._submit()
    pump()
    check("wrong shows error", "错误" in box.err["text"], box.err["text"])
    check("wrong keeps window", box.winfo_exists())
    check("wrong no ok", ok_flag["hit"] == 0)

    # 3) 对码 → on_ok 命中 + 窗口关闭
    box.entry.delete(0, "end")
    box.entry.insert(0, correct)
    box._submit()
    pump()
    check("correct triggers ok", ok_flag["hit"] == 1)
    check("correct closes window", not box.winfo_exists())

    root.destroy()
    print("\n".join(results))
    print("GUI PASSCODE SMOKE OK" if ok else "GUI PASSCODE SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())