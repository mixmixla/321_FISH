# -*- coding: utf-8 -*-
"""boss.py —— 多套伪装工作窗（快速隐藏的"正经"替身）。

摸鱼应急场景：热键（或按钮）触发后，把聊天主窗/游戏窗/迷你条全部藏起来，
弹出这个仿办公窗口挡视线。R69A 起支持多套皮肤，一键轮换（右键菜单或 F2）：

    excel    仿 Excel：Ribbon 标签条 + 公式栏 + 数据表 + 状态栏
    vscode   仿 VS Code：活动栏 + 文件树侧栏 + 代码编辑区 + 集成终端
    terminal 仿 PowerShell：深色控制台 + 滚动日志 + 提示符
    ppt      仿 PowerPoint：幻灯片缩略图 + 大画布 + 备注栏
    mail     仿 Outlook：文件夹树 + 邮件列表 + 阅读窗格

每 BOSS_ALIVE_INTERVAL 秒"活"更新一次（改单元格/加日志/切幻灯片/标未读），
像真的在干活。全部控件只在主线程创建/更新（Toplevel 挂聊天主窗的 root）。
"""
import random
import tkinter as tk
from tkinter import ttk

from config import (BOSS_ALIVE_INTERVAL, BOSS_SKIN_LABELS, BOSS_SKIN_TITLES,
                    BOSS_SKINS, FONT_FAMILY)

_NAMES = ["张伟", "王芳", "李娜", "刘洋", "陈静", "杨帆", "赵磊", "黄敏",
          "周涛", "吴霞", "徐明", "孙丽", "马强", "朱婷", "胡军", "郭雪"]
_DEPTS = ["销售部", "市场部", "研发部", "人事部", "财务部", "运营部"]
_ITEMS = ["办公用品", "差旅报销", "设备采购", "培训费", "招待费",
          "快递费", "印刷费", "软件订阅", "会议餐费", "通讯费"]
_COLUMNS = [f"c{i}" for i in range(8)]
_HEADS = ["姓名", "部门", "日期", "事项", "金额", "账期", "进度", "备注"]

_MONO = ("Consolas", 9)


def _rand_row() -> list:
    return [
        random.choice(_NAMES),
        random.choice(_DEPTS),
        f"{random.randint(1, 28)}日",
        random.choice(_ITEMS),
        f"{random.randint(20, 9000)}",
        f"2026-{random.randint(1, 9):02d}月",
        random.choice(["10%", "35%", "60%", "85%", "100%", "待审批"]),
        random.choice(["", "加急", "已备注", "预算内", "需复核"]),
    ]


# ---------- 各皮肤静态素材 ----------
_VSC_FILES = ["src", "  main.py", "  config.py", "  utils.py",
              "tests", "  test_main.py", "README.md", "requirements.txt"]
_VSC_CODE = [
    ("kw", "import"), ("pl", " asyncio"), ("", ""),
    ("kw", "from"), ("pl", " config "), ("kw", "import"), ("pl", " CFG"), ("", ""),
    ("", ""), ("kw", "async def"), ("fn", " handle_message"), ("pl", "(sess, msg):"),
    ("", ""), ("cm", "    # 分发到对应频道处理器"),
    ("pl", "    ch = msg.get("), ("st", "\"channel\""), ("pl", ")"),
    ("kw", "    if"), ("pl", " ch == "), ("st", "\"group\""), ("pl", ":"),
    ("fn", "        await"), ("pl", " dispatch_group(sess, msg)"),
    ("kw", "    else"), ("pl", ":"),
    ("fn", "        await"), ("pl", " dispatch_private(sess, msg)"),
]
_PPT_SLIDES = ["封面", "行业背景", "竞品分析", "核心数据", "增长策略",
               "执行计划", "风险与应对", "总结"]
_MAIL_SENDER = ["行政部", "HR 王芳", "IT 支持", "财务部", "项目组", "客户成功"]
_MAIL_SUBJ = ["【通知】本周例会安排", "月度报销单据提交提醒", "服务器维护窗口",
              "Q3 OKR 对齐会议纪要", "客户反馈汇总", "新版工具链升级说明"]


class BossWindow:
    """多皮肤假工作窗；默认隐藏，show() 时置顶 1.5s 拉注意力。"""

    def __init__(self, root: tk.Tk, skin: str = "excel", on_cycle=None) -> None:
        self.win = tk.Toplevel(root)
        self.win.geometry("960x600")
        self._alive = True
        self._skin = skin if skin in BOSS_SKINS else BOSS_SKINS[0]
        self._on_cycle = on_cycle          # 轮换回调（client 持久化所选皮肤）
        self._tick_fn = None
        self._body = None
        self._build()
        self.win.protocol("WM_DELETE_WINDOW", self.hide)   # 关窗=藏，不真退
        self.hide()

    # ---------- 皮肤 ----------
    @property
    def skin(self) -> str:
        return self._skin

    def set_skin(self, skin: str) -> None:
        """切换皮肤：重建内容区（显隐状态不变）。"""
        if skin not in BOSS_SKINS:
            return
        self._skin = skin
        self._build()
        if self.visible():
            self.show()

    def cycle(self) -> str:
        """轮换到下一套皮肤并返回其键（右键菜单 / F2 触发）。"""
        i = BOSS_SKINS.index(self._skin)
        self.set_skin(BOSS_SKINS[(i + 1) % len(BOSS_SKINS)])
        if self._on_cycle is not None:
            try:
                self._on_cycle(self._skin)
            except Exception:
                pass
        return self._skin

    def _skin_menu(self, event=None) -> None:
        """右键菜单：一键选皮肤 / 轮换下一套。"""
        m = tk.Menu(self.win, tearoff=0)
        m.add_command(label="🔄 轮换下一套（F2）", command=self.cycle)
        m.add_separator()
        for sk in BOSS_SKINS:
            mark = "✓ " if sk == self._skin else "   "
            m.add_command(label=mark + BOSS_SKIN_LABELS.get(sk, sk),
                          command=lambda s=sk: self.set_skin(s))
        try:
            m.tk_popup(event.x_root if event else self.win.winfo_rootx() + 40,
                       event.y_root if event else self.win.winfo_rooty() + 40)
        finally:
            m.grab_release()

    # ---------- 构建 ----------
    def _build(self) -> None:
        win = self.win
        win.title(random.choice(BOSS_SKIN_TITLES.get(self._skin, ["工作窗"])))
        for ch in win.winfo_children():
            ch.destroy()
        self._body = tk.Frame(win)
        self._body.pack(fill="both", expand=True)
        builder = getattr(self, f"_build_{self._skin}", self._build_excel)
        self._tick_fn = builder(self._body)
        self.win.bind("<F2>", lambda e: self.cycle())
        self.win.bind("<Button-3>", self._skin_menu)
        self.win.after(int(BOSS_ALIVE_INTERVAL * 1000), self._tick)

    def _tick(self) -> None:
        if not self._alive:
            return
        try:
            if self._tick_fn is not None:
                self._tick_fn()
        except Exception:
            pass
        self.win.after(int(BOSS_ALIVE_INTERVAL * 1000), self._tick)

    # ---------- 皮肤①：Excel ----------
    def _build_excel(self, body: tk.Frame):
        f = (FONT_FAMILY, 9)
        ribbon = tk.Frame(body, bg="#f3f3f3")
        ribbon.pack(fill="x")
        for tab in ("开始", "插入", "页面布局", "公式", "数据", "审阅",
                    "视图", "开发工具"):
            tk.Label(ribbon, text=tab, bg="#f3f3f3", fg="#444", font=f,
                     padx=10, pady=4).pack(side="left")
        bar = tk.Frame(body)
        bar.pack(fill="x", pady=2)
        tk.Label(bar, text="fx", bg="#e8e8e8", fg="#888", font=f,
                 width=3).pack(side="left")
        formula = tk.Label(bar, text="=SUM(A2:A10)", anchor="w", fg="#333",
                           font=f, relief="sunken", padx=4)
        formula.pack(side="left", fill="x", expand=True)
        tree = ttk.Treeview(body, columns=_COLUMNS, show="headings")
        for i, h in enumerate(_HEADS):
            tree.heading(f"c{i}", text=h)
            tree.column(f"c{i}", width=110, anchor="center")
        for _ in range(24):
            tree.insert("", "end", values=_rand_row())
        tree.pack(fill="both", expand=True)
        st = tk.Frame(body, bg="#f3f3f3")
        st.pack(fill="x")
        st_label = tk.Label(st, text="就绪  第 1 页/共 1 页",
                            bg="#f3f3f3", fg="#777", font=(FONT_FAMILY, 8))
        st_label.pack(side="left", padx=8, pady=2)

        def tick() -> None:
            kids = tree.get_children()
            if kids:
                kid = random.choice(kids)
                col = random.choice(_COLUMNS[:-1])
                tree.set(kid, col, random.choice(_rand_row()))
            formula.config(text=random.choice([
                "=SUM(A2:A10)", "=IF(E2>5000,\"达标\",\"待跟进\")",
                "=VLOOKUP(B2,明细表!A:D,3,0)", "=ROUND(E2*0.15,2)"]))
            cell = f"{random.choice('ABCDEF')}{random.randint(2, 25)}"
            st_label.config(text=f"就绪  单元格 {cell}  已保存")

        return tick

    # ---------- 皮肤②：VS Code ----------
    def _build_vscode(self, body: tk.Frame):
        wrap = tk.Frame(body)
        wrap.pack(fill="both", expand=True)
        # 活动栏
        act = tk.Frame(wrap, bg="#333333", width=44)
        act.pack(side="left", fill="y")
        act.pack_propagate(False)
        for ico in ("📄", "🔍", "🌿", "🐞", "🧩"):
            tk.Label(act, text=ico, bg="#333333", fg="#cccccc",
                     font=(FONT_FAMILY, 13), pady=6).pack()
        # 侧栏文件树
        side = tk.Frame(wrap, bg="#252526", width=200)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="资源管理器", bg="#252526", fg="#bbbbbb",
                 font=(FONT_FAMILY, 8), anchor="w", padx=8, pady=4).pack(fill="x")
        file_lbls = {}
        for name in _VSC_FILES:
            is_dir = not name.startswith("  ")
            lb = tk.Label(side, text=("📁 " if is_dir else "📄 ") + name.strip(),
                          bg="#252526", fg="#cfcfcf", anchor="w", padx=10,
                          font=(FONT_FAMILY, 8))
            lb.pack(fill="x")
            file_lbls[name] = lb
        # 编辑区
        edit = tk.Frame(wrap, bg="#1e1e1e")
        edit.pack(side="left", fill="both", expand=True)
        tabbar = tk.Frame(edit, bg="#2d2d2d")
        tabbar.pack(fill="x")
        self._vsc_tab = tk.Label(tabbar, text=" app.py ✕", bg="#1e1e1e",
                                 fg="#e0e0e0", font=(FONT_FAMILY, 8), padx=8, pady=3)
        self._vsc_tab.pack(side="left")
        code = tk.Text(edit, bg="#1e1e1e", fg="#d4d4d4", font=_MONO,
                       relief="flat", padx=8, pady=4, wrap="none")
        code.pack(fill="both", expand=True)
        code.tag_config("kw", foreground="#569cd6")
        code.tag_config("fn", foreground="#dcdcaa")
        code.tag_config("st", foreground="#ce9178")
        code.tag_config("cm", foreground="#6a9955")
        code.tag_config("pl", foreground="#d4d4d4")
        code.insert("end", "   1\n")
        for tag, txt in _VSC_CODE:
            code.insert("end", txt, tag)
        code.insert("end", "\n")
        code.config(state="disabled")
        # 集成终端
        term = tk.Frame(edit, bg="#181818", height=120)
        term.pack(fill="x")
        term.pack_propagate(False)
        self._vsc_term = tk.Label(term, text="$ python -m pytest -q", bg="#181818",
                                  fg="#cccccc", font=_MONO, anchor="w", padx=8, pady=4)
        self._vsc_term.pack(fill="x")
        # 状态栏
        st = tk.Frame(body, bg="#007acc")
        st.pack(fill="x")
        self._vsc_st = tk.Label(st, text="✓ Python 3.14.5   UTF-8   LF",
                                bg="#007acc", fg="#ffffff",
                                font=(FONT_FAMILY, 8), anchor="w", padx=8, pady=2)
        self._vsc_st.pack(side="left")
        tk.Label(st, text="Ln 12, Col 24", bg="#007acc", fg="#ffffff",
                 font=(FONT_FAMILY, 8), padx=8).pack(side="right")

        def tick() -> None:
            name = random.choice(_VSC_FILES)
            lb = file_lbls.get(name)
            if lb is not None:
                base = ("📁 " if not name.startswith("  ") else "📄 ") + name.strip()
                lb.config(text=base + "  ●")
            self._vsc_term.config(text=random.choice([
                "$ python -m pytest -q",
                "collected 1012 items",
                "collected 1012 items / 0 failed",
                "$ git status", "On branch main, nothing to commit",
                "$ python build.py", "building client.exe ..."]))
            self._vsc_st.config(
                text=f"✓ Python 3.14.5   第 {random.randint(1, 40)} 行，共 128 行")

        return tick

    # ---------- 皮肤③：PowerShell ----------
    def _build_terminal(self, body: tk.Frame):
        wrap = tk.Frame(body, bg="#0c0c0c")
        wrap.pack(fill="both", expand=True)
        tk.Label(wrap, text="Windows PowerShell", bg="#0c0c0c", fg="#cccccc",
                 font=(FONT_FAMILY, 9), anchor="w", padx=6, pady=2).pack(fill="x")
        log = tk.Text(wrap, bg="#0c0c0c", fg="#cccccc", font=_MONO,
                      relief="flat", padx=6, pady=4)
        log.pack(fill="both", expand=True)
        log.tag_config("ps", foreground="#f9f1a5")
        log.tag_config("err", foreground="#ff6b6b")
        log.tag_config("ok", foreground="#8be9a1")
        log.insert("end", "Windows PowerShell\n", ("ps",))
        log.insert("end", "版权所有 (C) Microsoft Corporation。保留所有权利。\n\n"
                          "尝试新的跨平台 PowerShell https://aka.ms/pscore6\n\n")
        log.insert("end", "PS C:\\Users\\admin\\projects\\app> ", ("ps",))
        log.insert("end", "git pull\n")
        log.insert("end", "Already up to date.\n\n")
        log.insert("end", "PS C:\\Users\\admin\\projects\\app> ", ("ps",))
        log.config(state="disabled")
        cnt = {"n": 0}

        def tick() -> None:
            cnt["n"] += 1
            log.config(state="normal")
            if cnt["n"] % 3 == 0:
                log.insert("end", f"PS C:\\Users\\admin\\projects\\app> python main.py --check\n")
                log.insert("end", "[ok] config loaded, 0 warnings\n", ("ok",))
            elif cnt["n"] % 3 == 1:
                log.insert("end", "$ ls src\\\n"
                                  "    Directory: C:\\Users\\admin\\projects\\app\\src\n\n"
                                  "Mode   LastWriteTime     Length Name\n"
                                  "----   -------------     ------ ----\n"
                                  "-a---  2026/9/26 10:12       8421 main.py\n"
                                  "-a---  2026/9/26 10:09       3310 config.py\n")
            else:
                log.insert("end", "[warn] unused import: os\n", ("err",))
            log.see("end")
            log.config(state="disabled")

        return tick

    # ---------- 皮肤④：PowerPoint ----------
    def _build_ppt(self, body: tk.Frame):
        wrap = tk.Frame(body, bg="#f0f0f0")
        wrap.pack(fill="both", expand=True)
        # 左侧缩略图
        left = tk.Frame(wrap, bg="#e6e6e6", width=160)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self._ppt_thumb_boxes = []
        for i, s in enumerate(_PPT_SLIDES):
            box = tk.Frame(left, bg="#ffffff", bd=1, relief="solid")
            box.pack(fill="x", padx=6, pady=3)
            tk.Label(box, text=f"{i + 1}", bg="#ffffff", fg="#888",
                     font=(FONT_FAMILY, 7)).pack(side="left", padx=3)
            tk.Label(box, text=s, bg="#ffffff", fg="#333", anchor="w",
                     font=(FONT_FAMILY, 8)).pack(side="left", fill="x")
            self._ppt_thumb_boxes.append(box)
        self._ppt_idx = 0
        self._ppt_thumb_boxes[0].config(bg="#cde3ff")
        # 主画布
        main = tk.Frame(wrap, bg="#f0f0f0")
        main.pack(side="left", fill="both", expand=True)
        self._ppt_slide = tk.Frame(main, bg="#ffffff", bd=1, relief="solid")
        self._ppt_slide.pack(fill="both", expand=True, padx=14, pady=14)
        self._ppt_title = tk.Label(self._ppt_slide, text=_PPT_SLIDES[0],
                                   bg="#ffffff", fg="#1f3d6e",
                                   font=(FONT_FAMILY, 20, "bold"))
        self._ppt_title.pack(anchor="w", padx=24, pady=(24, 8))
        self._ppt_bullets = tk.Label(self._ppt_slide, text="", bg="#ffffff",
                                     fg="#444", justify="left",
                                     font=(FONT_FAMILY, 11))
        self._ppt_bullets.pack(anchor="w", padx=28, pady=6)
        # 备注栏
        notes = tk.Frame(wrap, bg="#fafafa", width=190)
        notes.pack(side="right", fill="y")
        notes.pack_propagate(False)
        tk.Label(notes, text="备注", bg="#fafafa", fg="#666",
                 font=(FONT_FAMILY, 8), anchor="w", padx=8, pady=4).pack(fill="x")
        self._ppt_notes = tk.Label(notes, text="", bg="#fafafa", fg="#555",
                                   wraplength=170, justify="left", anchor="nw",
                                   font=(FONT_FAMILY, 8))
        self._ppt_notes.pack(fill="both", expand=True, padx=8)
        self._ppt_set(0)

        def tick() -> None:
            nxt = (self._ppt_idx + 1) % len(_PPT_SLIDES)
            self._ppt_set(nxt)

        return tick

    def _ppt_set(self, idx: int) -> None:
        self._ppt_idx = idx
        for i, box in enumerate(self._ppt_thumb_boxes):
            box.config(bg="#cde3ff" if i == idx else "#ffffff")
        title = _PPT_SLIDES[idx]
        self._ppt_title.config(text=title)
        bullets = "\n".join(
            f"• {random.choice(_ITEMS)}相关要点 {random.randint(1, 9)}"
            for _ in range(4))
        self._ppt_bullets.config(text=bullets)
        self._ppt_notes.config(text=random.choice([
            "讲稿：先讲结论，再补数据支撑。",
            "口径与财务对齐，避免口径不一致。",
            "此处停一下，等领导提问再展开。",
            "时间控制在 2 分钟内，不拖堂。"]))

    # ---------- 皮肤⑤：Outlook ----------
    def _build_mail(self, body: tk.Frame):
        wrap = tk.Frame(body)
        wrap.pack(fill="both", expand=True)
        folders = tk.Frame(wrap, bg="#f3f3f3", width=150)
        folders.pack(side="left", fill="y")
        folders.pack_propagate(False)
        for name in ("收件箱 (12)", "草稿", "已发送", "已删除", "存档", "垃圾邮件"):
            tk.Label(folders, text=name, bg="#f3f3f3", fg="#333", anchor="w",
                     padx=10, pady=4, font=(FONT_FAMILY, 8)).pack(fill="x")
        mid = tk.Frame(wrap, width=340)
        mid.pack(side="left", fill="y")
        mid.pack_propagate(False)
        tree = ttk.Treeview(mid, columns=("s", "t"), show="headings")
        tree.heading("s", text="发件人")
        tree.heading("t", text="主题")
        tree.column("s", width=90, anchor="w")
        tree.column("t", width=240, anchor="w")
        rows = []
        for _ in range(14):
            rows.append((random.choice(_MAIL_SENDER), random.choice(_MAIL_SUBJ)))
        for r in rows:
            tree.insert("", "end", values=r)
        tree.pack(fill="both", expand=True)
        right = tk.Frame(wrap, bg="#ffffff")
        right.pack(side="left", fill="both", expand=True)
        self._mail_hdr = tk.Label(right, text="请选择一封邮件",
                                  bg="#ffffff", fg="#1f3d6e", anchor="w",
                                  font=(FONT_FAMILY, 12, "bold"))
        self._mail_hdr.pack(fill="x", padx=14, pady=(14, 2))
        self._mail_meta = tk.Label(right, text="", bg="#ffffff", fg="#888",
                                   anchor="w", font=(FONT_FAMILY, 8))
        self._mail_meta.pack(fill="x", padx=14)
        self._mail_body = tk.Label(
            right, text="", bg="#ffffff", fg="#333", justify="left", anchor="nw",
            wraplength=380, font=(FONT_FAMILY, 9))
        self._mail_body.pack(fill="both", expand=True, padx=14, pady=10)
        self._mail_pick(rows[0])

        def tick() -> None:
            self._mail_pick(random.choice(rows))

        return tick

    def _mail_pick(self, row) -> None:
        sender, subj = row
        self._mail_hdr.config(text=subj)
        self._mail_meta.config(text=f"发件人：{sender}    收件人：我    "
                                    f"2026/9/26 {random.randint(9, 18)}:"
                                    f"{random.randint(10, 59)}")
        self._mail_body.config(text=(
            "您好：\n\n"
            f"    关于「{subj}」，请查收附件并按要求回复。\n"
            "    如对内容有疑问，请于本周五前反馈，谢谢。\n\n"
            f"                                        —— {sender}"))

    # ---------- 显隐 ----------
    def show(self) -> None:
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        self.win.attributes("-topmost", True)
        # 1.5s 后取消置顶，避免长期抢占前台惹注意
        self.win.after(1500, lambda: self.win.attributes("-topmost", False))

    def hide(self) -> None:
        self.win.withdraw()

    def visible(self) -> bool:
        try:
            return self.win.state() == "normal"
        except Exception:
            return False

    def close(self) -> None:
        self._alive = False
        try:
            self.win.destroy()
        except Exception:
            pass
