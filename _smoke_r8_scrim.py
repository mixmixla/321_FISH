# -*- coding: utf-8 -*-
"""R8 冒烟：Scrim 半透明遮罩淡入到 target、淡出后销毁。"""
import time
import tkinter as tk
from widgets.scrim import Scrim
from theme import BASE


def main() -> int:
    root = tk.Tk()
    root.geometry("400x300+50+50")
    root.update_idletasks()
    results = []
    ok = True

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    s = Scrim(root)
    s.show()
    done = {"fade": 0.0}
    deadline = time.time() + 2
    while time.time() < deadline:
        root.update()
        time.sleep(0.02)
        if s.winfo_exists():
            a = s.alpha_value() or 0
            done["fade"] = max(done["fade"], a)
        else:
            break
    target = BASE["scrim_alpha"]
    check("scrim fades to target", abs(done["fade"] - target) < 0.13,
          f"peak={done['fade']:.2f} target={target}")
    check("scrim exists after show", s.winfo_exists())

    # 淡出后销毁
    s.hide(cb=lambda: done.__setitem__("hidden", True))
    deadline = time.time() + 2
    gone = False
    while time.time() < deadline:
        root.update()
        time.sleep(0.02)
        if not s.winfo_exists():
            gone = True
            break
    check("scrim destroyed after hide", gone)
    check("scrim hide callback fired", done.get("hidden", False))

    root.destroy()
    print("\n".join(results))
    print("GUI SCRIM SMOKE OK" if ok else "GUI SCRIM SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())