# -*- coding: utf-8 -*-
"""R31B2（相册分组）冒烟：
- 同人连续图片合并：成员行 _in_group=True / 高度 0，锚点画网格（估算=实测）
- 断组：跨 uid / 未读线；成员撤回 → 墓碑文本 + 相册重算
- 多选整组勾选 / 网格热区点击回调 / image_rows 覆盖成员
"""
import os
import tempfile
import time
import tkinter as tk

from widgets.msg_list import ALBUM_COLS, ALBUM_GAP, MsgList


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="r31e_")
    colors = ["#e74c3c", "#2ecc71", "#3498db", "#f39c12"]
    paths = []
    try:
        from PIL import Image
        for k, c in enumerate(colors):
            p = os.path.join(tmp, f"img{k}.png")
            Image.new("RGB", (300, 200), c).save(p)
            paths.append(p)
    except Exception as e:
        print(f"[FAIL] 无法生成测试图片: {e}")
        return 1

    root = tk.Tk()
    root.geometry("640x480")
    opened = []
    ml = MsgList(root, font=("Microsoft YaHei", 10), me_uid=1,
                 on_row_image=lambda i, p: opened.append((i, p)))
    ml.pack(fill="both", expand=True)

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
        t0 = time.time()
        for k in range(3):        # 同人连续 3 图 → 相册
            ml.append({"seq": 1 + k, "uid": 1, "nick": "我", "text": "",
                       "image_path": paths[k], "ts": t0 + 5 * k})
        ml.append({"seq": 4, "uid": 2, "nick": "他", "text": "文本",
                   "ts": t0 + 12})
        ml.append({"seq": 5, "uid": 2, "nick": "他", "text": "",
                   "image_path": paths[3], "ts": t0 + 400})
        pump(0.8)

        # 1. 分组判定与高度
        check("成员行入组", ml._in_group(1) and ml._in_group(2))
        check("跨 uid 文本不入组", not ml._in_group(3))
        check("超窗图片不入组", not ml._in_group(4) and ml._heights[4] > 0)
        check("成员行高度 0", ml._heights[1] == 0 and ml._heights[2] == 0,
              f"{ml._heights[1]},{ml._heights[2]}")
        grid3 = ml._album_grid_h(3)
        expect = ml._linespace + 3 * ml.PAD_TOP + grid3
        check("锚点高度=头部+网格", ml._heights[0] == expect,
              f"{ml._heights[0]} vs {expect}")
        check("成员归入 _album_rows", ml._album_rows(0) == [0, 1, 2],
              str(ml._album_rows(0)))
        check("image_rows 含成员",
              [i for i, _ in ml.image_rows()] == [0, 1, 2, 4],
              str([i for i, _ in ml.image_rows()]))
        h0 = ml._heights[0]
        pump(0.3)
        check("渲染后高度稳定", ml._heights[0] == h0)

        # 2. 未读线断组（成员行不能携带分隔条）
        ml.set_unread_seq(1)      # 行1(seq2) 起为未读
        check("未读线断组", not ml._in_group(1))
        ml.set_unread_seq(None)
        pump(0.2)
        check("撤线后恢复入组", ml._in_group(1) and ml._heights[1] == 0)

        # 3. 撤回中间成员图（seq2=行1）→ 墓碑 + 相册重算
        check("撤回成功", ml.mark_deleted(2))
        pump(0.5)
        check("墓碑文本", "撤回" in ml.body_text(1), ml.body_text(1))
        check("撤回行退出相册", ml._album_rows(0) == [0], str(ml._album_rows(0)))
        check("后图独立成行", not ml._in_group(2) and ml._heights[2] > 0)

        # 4. 多选整组勾选（当前相册只剩行0 单图）
        ml.enter_select_mode(0)
        pump(0.2)
        check("单图勾选", ml.selected_rows() == [0], str(ml.selected_rows()))
        ml.exit_select_mode()
        pump(0.2)

        # 5. 网格热区点击回调：重建 2 图相册，点第 2 格
        ml.clear()
        pump(0.2)
        t1 = time.time()
        ml.append({"seq": 11, "uid": 1, "nick": "我", "text": "",
                   "image_path": paths[0], "ts": t1})
        ml.append({"seq": 12, "uid": 1, "nick": "我", "text": "",
                   "image_path": paths[1], "ts": t1 + 4})
        pump(1.2)                 # 等缩略图解码
        ml.yview_moveto(0)
        ml._render()
        pump(0.3)
        check("2 图相册成立", ml._album_rows(len(ml._rows) - 2) == [0, 1],
              str(ml._album_rows(0)))
        cw, ch = ml._album_cell()
        tx = ml.PAD_X + ml.AVATAR + ml.GUTTER
        iy = (ml._cum[0] - ml.canvasy(0)) + ml.PAD_TOP + ml._linespace + ml.PAD_TOP
        cx = int(tx + (cw + ALBUM_GAP) + cw / 2)
        cy = int(iy + ch / 2)
        ml.event_generate("<Button-1>", x=cx, y=cy)
        pump(0.3)
        check("网格点击开大图", opened and opened[-1][0] == 1, str(opened))
    except Exception as e:
        import traceback
        traceback.print_exc()
        ok = False
        results.append(f"[FAIL] 异常: {type(e).__name__}: {e}")
    finally:
        root.destroy()

    print("\n".join(results))
    print("R31B2 冒烟:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
