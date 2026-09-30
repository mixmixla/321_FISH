# -*- coding: utf-8 -*-
"""moment_list.py —— 朋友圈时间轴控件（微信式互动 + 项目「暖粉手绘」皮肤）。

微信式卡片：
  · 顶部手绘暖粉渐变封面 + 发布区
  · 卡片：圆角方形头像 + 昵称/相对时间 + 正文
  · 图片九宫格（1 张大图 / 其余铺 3 列均匀网格，随内容列宽自适应）
  · 底部「点赞 + 评论」合并框，评论下置发表输入
微信式互动（纯 Tk 帧动画，无额外依赖）：
  · 新动态发布后平滑滚回顶部 + 卡片柔光高亮（降序观感、不突兀）
  · 点赞按钮「回弹」脉冲（❤ 放大再回落 + 珊瑚色切换）
  · 发表评论后输入框清空 + 评论框淡入高亮
图片懒加载：on_img 触服务器拉取，feed_img 回调回填并即时重排。
发/赞/评/删通过 host 透传到 client_core 再发服务器。
"""
import time
import tkinter as tk
from tkinter import filedialog

from PIL import Image as PILImage, ImageTk

AV_FILLS = ("#f5a06a", "#5aa9e6", "#3ba676", "#c77bec",
            "#ff8a5c", "#e8635a", "#9b6bd8", "#45c3a8")
# 手绘奶油底附近的软高亮（点缀用）
PAPER = "#fffdf7"
SOFT_LINE = "#efdcc4"


def _hx_mix(a, b, t):
    """按 t∈[0,1] 在 a/b 两个 #rrggbb 颜色间平滑插值。"""
    def ch(s):
        return (int(s[1:3], 16), int(s[3:5], 16), int(s[5:7], 16))
    x, y = ch(a), ch(b)
    m = tuple(round(x[i] + (y[i] - x[i]) * t) for i in range(3))
    return f"#{m[0]:02x}{m[1]:02x}{m[2]:02x}"


def _rel_time(ts):
    try:
        t = float(ts)
    except (TypeError, ValueError):
        return ""
    s = time.time() - t
    if s < 60:
        return "刚刚"
    if s < 3600:
        return f"{int(s//60)} 分钟前"
    if s < 86400:
        return f"{int(s//3600)} 小时前"
    if s < 86400 * 3:
        return f"{int(s//86400)} 天前"
    d = time.localtime(t)
    return f"{d.tm_mon} 月 {d.tm_mday} 日"


class MomentList(tk.Frame):
    def __init__(self, master, font, skin, *, uid, host,
                 max_img=400):
        super().__init__(master, bg=skin.get("panel_bg", PAPER))
        self._font = font
        self._skin = skin
        self._uid = uid
        self._host = host                       # client：提供 .core 及事件回填
        self._max_img = max_img
        self._posts = []                        # [{pid,...}] 恒按 pid 降序
        self._cards = {}                        # pid -> {frame, imgf, like_btn, ...}
        self._img_cache = {}                    # fn -> PIL.Image（显式持有防 GC）
        self._col_w = 360                       # 内容列宽（随画布宽动态校准）
        self._resize_job = None

        # ===== 皮肤 token（暖粉手绘：焦糖/珊瑚/奶油） =====
        self._bg = skin.get("panel_bg", PAPER)
        self._card = skin.get("list_bg", "#fff1e1")
        self._line = skin.get("glass_border", SOFT_LINE)
        self._sub = skin.get("sub", "#b08968")
        self._txt = skin.get("fg", "#5b4433")
        self._name = skin.get("fg", "#5b4433")
        self._accent = skin.get("accent", "#ff8a5c")
        self._input = skin.get("input_bg", "#fffdf6")

        # ===== 顶部封面：暖粉渐变 + 手绘标题（可换预设/上传图，右下昵称+签名） =====
        self._cover = tk.Canvas(self, bg=self._card, height=104,
                                highlightthickness=0)
        self._cover.pack(fill="x")
        self._cover.bind("<Configure>", self._draw_cover)
        self._cover_state = None             # {mode,preset,ext} 或 None=默认
        self._cover_img = None               # 封面图片原始字节
        self._cover_photo = None             # ImageTk.PhotoImage（显式持有防 GC）
        self._me_nick = ""
        self._sign = ""
        self._PRESETS = (("#ffd0b0", "#ffb98f"),   # 奶油珊瑚
                         ("#cdeedd", "#9fdcb8"),   # 薄荷
                         ("#d7e2ff", "#aec6ff"),   # 天空蓝
                         ("#ffd3de", "#ffadc4"),   # 樱粉
                         ("#e7dcff", "#cbb6ff"),   # 薰衣草
                         ("#ffe0a8", "#ffc47a"))   # 焦糖橙
        self._cov_btn = tk.Button(self._cover, text="🖼 换封面",
                                  font=(font[0], 9), relief="flat", bd=0,
                                  bg="#ffffff", fg=self._sub, cursor="hand2",
                                  activebackground=self._line,
                                  command=self._cover_menu)
        self._cov_item = None

        # ===== 发布区 =====
        wr = tk.Frame(self, bg=self._bg)
        wr.pack(fill="x", padx=10, pady=(0, 6))
        box = tk.Frame(wr, bg=self._card, highlightthickness=1,
                       highlightbackground=self._line)
        box.pack(fill="x", pady=(0, 2))
        self._text = tk.Text(box, height=2, font=font, relief="flat", bd=0,
                             bg=self._card, fg=self._txt,
                             insertbackground=self._txt, wrap="word")
        self._text.pack(fill="x", padx=8, pady=(8, 4))
        self._paths = []

        row = tk.Frame(box, bg=self._card)
        row.pack(fill="x", padx=8, pady=(0, 8))
        self._cam = tk.Button(row, text="＋", font=(font[0], 13), relief="flat",
                              bd=1, width=3, bg=self._input, fg=self._sub,
                              activebackground=self._line,
                              highlightthickness=1, highlightbackground=self._line,
                              command=self._pick_images)
        self._cam.pack(side="left")
        self._img_label = tk.Label(row, text="", font=font, bg=self._card,
                                   fg=self._sub)
        self._img_label.pack(side="left", padx=(8, 0))
        tk.Button(row, text="发布", font=(font[0], font[1], "bold"), relief="flat",
                  bd=0, bg=self._accent, fg="#ffffff",
                  activebackground=self._accent, cursor="hand2",
                  command=self._publish).pack(side="right")
        self._status = tk.Label(wr, text="", font=(font[0], 10), bg=self._bg,
                                fg=self._sub, anchor="w")
        self._status.pack(fill="x", padx=4)

        # ===== 时间轴 =====
        wrap = tk.Frame(self, bg=self._bg)
        wrap.pack(fill="both", expand=True)
        self._cv = tk.Canvas(wrap, bg=self._bg, highlightthickness=0)
        sb = tk.Scrollbar(wrap, orient="vertical", command=self._cv.yview)
        self._inner = tk.Frame(self._cv, bg=self._bg)
        self._inner_id = self._cv.create_window((0, 0), window=self._inner,
                                                anchor="nw")
        self._cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._cv.pack(side="left", fill="both", expand=True)
        self._inner.bind("<Configure>", self._on_inner_cfg)
        self._cv.bind("<Configure>", self._on_cv_cfg)
        self._cv.bind("<MouseWheel>", self._on_wheel)
        self._inner.bind("<MouseWheel>", self._on_wheel, add="+")
        self._empty = tk.Label(self._inner, text="还没有动态，来发第一条吧 📸",
                               font=font, bg=self._bg, fg=self._sub)
        self._empty.pack(pady=40)

        self._anim_jobs = {}                    # pid -> 动画 after id（防止叠加）
        self._rep_target = {}                   # pid -> (rep_uid, rep_nick) 楼中楼目标

    # ---------- 视图 ----------
    def _on_cv_cfg(self, e):
        # 内容列宽 = 画布宽扣掉滚动条与左右留白，钳到 [240, 380]
        self._col_w = int(max(240, min(380, e.width - 22)))
        self._cv.itemconfigure(self._inner_id, width=e.width)
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(60, self._relayout_all_img)
        self._draw_cover()

    def _on_inner_cfg(self, _e=None):
        self._cv.configure(scrollregion=self._cv.bbox("all"))

    def _on_wheel(self, e):
        try:
            self._cv.yview_scroll(int(-e.delta / 120), "units")
        except Exception:
            pass

    def _relayout_all_img(self):
        for pid in list(self._cards):
            self._layout_images(pid)

    # ---------- 封面 ----------
    def _make_cover_photo(self, data):
        """封面原图 → 等比放大裁剪铺满 w×104 的 PhotoImage。"""
        from io import BytesIO
        try:
            im = PILImage.open(BytesIO(data)).convert("RGB")
        except Exception:
            return None
        w = max(self._cover.winfo_width(), 200)
        h = max(self._cover.winfo_height(), 104)
        iw, ih = im.size
        scale = max(w / max(iw, 1), h / max(ih, 1))
        nw, nh = int(iw * scale + 0.5), int(ih * scale + 0.5)
        im = im.resize((nw, nh), PILImage.LANCZOS)
        x0 = (nw - w) // 2
        y0 = (nh - h) // 2
        im = im.crop((max(x0, 0), max(y0, 0), min(x0 + w, nw), min(y0 + h, nh)))
        return ImageTk.PhotoImage(im)

    def _draw_cover(self, _e=None):
        c = self._cover
        w = max(c.winfo_width(), 200)
        h = max(c.winfo_height(), 104)
        c.delete("all")
        use_img = self._cover_img is not None
        photo = self._make_cover_photo(self._cover_img) if use_img else None
        if photo is not None:
            self._cover_photo = photo
            c.create_image(0, 0, anchor="nw", image=photo)
        else:
            self._cover_photo = None
            if self._cover_state and self._cover_state.get("mode") == "preset":
                top, bot = self._PRESETS[
                    self._cover_state.get("preset", 0) % len(self._PRESETS)]
            else:
                top = _hx_mix(self._accent, "#ffffff", 0.72)
                mid = _hx_mix(self._accent, "#ffffff", 0.88)
                bot = self._bg
            n = 24
            for i in range(n):
                t = i / (n - 1)
                if self._cover_state and self._cover_state.get("mode") == "preset":
                    col = _hx_mix(top, bot, t)
                else:
                    band_top = _hx_mix(top, mid, min(t * 2, 1))
                    col = band_top if t * 2 < 1 else _hx_mix(mid, bot, t * 2 - 1)
                c.create_rectangle(0, i * (h / n), w, (i + 1) * (h / n),
                                   fill=col, outline="")
            if not (self._cover_state and self._cover_state.get("mode") == "preset"):
                # 默认：手绘云朵 + 标题
                c.create_oval(w - 70, 12, w - 22, 54,
                              fill=_hx_mix(top, "#ffffff", 0.4), outline="")
                c.create_oval(w - 96, 22, w - 40, 60,
                              fill=_hx_mix(top, "#ffffff", 0.25), outline="")
                _round_txt(c, 16, 18, "朋友圈", (self._font[0], 15, "bold"),
                           "#ffffff", 0)
                _round_txt(c, 16, 46, "摸鱼小屋 · Moments", (self._font[0], 9),
                           _hx_mix(self._accent, "#ffffff", 0.35), 0)
        # 右下：昵称 + 签名（点击编辑）
        cx = w - 14
        c.create_text(cx, h - 32, text=self._me_nick or "", anchor="se",
                      fill="#ffffff", font=(self._font[0], 13, "bold"))
        sig_txt = self._sign or "点击设置个性签名"
        c.create_text(cx, h - 9, text=sig_txt, anchor="se", tags=("sig",),
                      fill=_hx_mix("#ffffff", "#1f1f1f", 0.22),
                      font=(self._font[0], 9))
        c.tag_bind("sig", "<Button-1>", lambda e: self._edit_sign())
        # 换封面按钮（右上角）
        if self._cov_btn is not None:
            if self._cov_item is None:
                self._cov_item = c.create_window(w - 8, 8, anchor="ne",
                                                 window=self._cov_btn)
            else:
                c.coords(self._cov_item, w - 8, 8)

    def set_me(self, nick):
        """封面右下昵称（我的昵称）。"""
        self._me_nick = nick or ""
        self._draw_cover()

    def set_sign(self, sign):
        """封面右下签名展示。"""
        self._sign = sign or ""
        self._draw_cover()

    def apply_cover(self, cover, data=b""):
        """服务端封面回帧：cover=None=默认；img 模式带 data 图片字节。"""
        self._cover_state = cover
        self._cover_img = bytes(data or b"") or None
        self._draw_cover()

    def _cover_menu(self):
        m = tk.Menu(self, tearoff=0)
        m.add_command(label="📁 上传图片…", command=self._pick_cover_img)
        for i in range(len(self._PRESETS)):
            m.add_command(label=f"🎨 预设封面 {i + 1}",
                          command=lambda n=i: self._host.cover_set_preset(n))
        m.add_command(label="♻️ 恢复默认", command=lambda: self._host.cover_del())
        try:
            m.tk_popup(self._cover.winfo_rootx() + 8,
                       self._cover.winfo_rooty() + 40)
        finally:
            m.grab_release()

    def _pick_cover_img(self):
        path = filedialog.askopenfilename(
            parent=self, title="选择封面图片",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.gif *.bmp")])
        if path:
            self._host.cover_set_img(path)

    def _edit_sign(self):
        dlg = tk.Toplevel(self)
        dlg.title("个性签名")
        dlg.transient(self)
        dlg.configure(bg=self._bg)
        dlg.geometry("320x118+" + str(self.winfo_rootx() + 50) + "+"
                     + str(self.winfo_rooty() + 130))
        tk.Label(dlg, text="个性签名（60 字内，全员可见）", bg=self._bg,
                 fg=self._sub, font=(self._font[0], 10)).pack(
            fill="x", padx=12, pady=(12, 4), anchor="w")
        var = tk.StringVar(value=self._sign)
        en = tk.Entry(dlg, textvariable=var, font=self._font)
        en.pack(fill="x", padx=12)
        row = tk.Frame(dlg, bg=self._bg)
        row.pack(fill="x", padx=12, pady=(10, 12))
        tk.Button(row, text="保存", bg=self._accent, fg="#ffffff",
                  relief="flat", command=lambda: self._save_sign(dlg, var)
                  ).pack(side="right", padx=(8, 0))
        tk.Button(row, text="取消", bg=self._input, fg=self._sub,
                  relief="flat", command=dlg.destroy).pack(side="right")
        en.bind("<Return>", lambda e: self._save_sign(dlg, var))
        en.focus_set()

    def _save_sign(self, dlg, var):
        t = var.get().strip()[:60]
        self._host.set_sign(t)
        self.set_sign(t)
        dlg.destroy()

    # ---------- 数据：恒按 pid 降序 ----------
    def render_feed(self, posts):
        """替换全量时间轴（按 pid 倒序）。"""
        self._posts = sorted((list(posts) or []),
                             key=lambda p: p.get("pid", 0), reverse=True)
        for pid in list(self._cards):
            self._drop_card(pid)
        for p in self._posts:
            self._ensure_card(p)
        for p in self._posts:
            for fn in p.get("images") or []:
                self._request_img(p["pid"], fn)
        self._toggle_empty()
        self._cv.yview_moveto(0)

    def upsert(self, post, pid=None):
        """moment_new / moment_update：post=None 表示删除（pid 取广播顶层字段）。"""
        if post is None and pid is None:
            return
        if post is not None:
            pid = post.get("pid")
        if pid is None:
            return
        for i, p in enumerate(self._posts):
            if p.get("pid") == pid:
                self._posts.pop(i)
                if post is not None:
                    self._posts.insert(0, post)
                    self._posts.sort(key=lambda q: q.get("pid", 0),
                                     reverse=True)
                    self._drop_card(pid)
                    self._ensure_card(post)
                    for fn in post.get("images") or []:
                        self._request_img(pid, fn)
                    self._reorder()          # 回归 pid 降序的视觉顺序
                else:
                    self._drop_card(pid)
                self._toggle_empty()
                return
        # 全新动态 → 置顶 + 平滑滚回 + 柔光高亮
        self._posts.insert(0, post)
        self._posts.sort(key=lambda q: q.get("pid", 0), reverse=True)
        self._ensure_card(post, top=True, animate=True)
        for fn in post.get("images") or []:
            self._request_img(pid, fn)
        self._toggle_empty()
        self._scroll_to_top_smooth()
        self._highlight(pid)

    def _toggle_empty(self):
        if self._empty is None:
            return
        if self._posts:
            self._empty.pack_forget()
        else:
            self._empty.pack(pady=40)

    def _reorder(self):
        """按 self._posts（pid 降序）校正各卡片的垂直堆叠顺序。

        用 pack(front=True) 从最后一条往前依次置顶：每置顶一张，它压到最上，
        其余保持原相对顺序，最终第 0 条在最上、末条在最下，免销毁重建的闪烁。
        """
        for p in reversed(self._posts):
            c = self._cards.get(p.get("pid"))
            if c:
                try:
                    c["frame"].pack(front=True)
                except Exception:
                    pass
        self._cv.after_idle(self._on_inner_cfg)

    def _drop_card(self, pid):
        c = self._cards.pop(pid, None)
        if c:
            job = self._anim_jobs.pop(pid, None)
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
            try:
                c["frame"].destroy()
            except Exception:
                pass
        if pid in self._img_cache:                    # 顺带释放该动态私有图
            pass

    # ---------- 微信式动画 ----------
    def _scroll_to_top_smooth(self):
        """把画布平滑滚回顶部（微信发新动态后的回落观感）。"""
        cur = self._cv.yview()[0]

        def step(fr):
            if fr > 1:
                return
            self._cv.yview_moveto(cur + (0 - cur) * (1 - (1 - fr) ** 3))
            self.after(16, step, fr + 0.12)
        step(0.0)

    def _highlight(self, pid):
        """新卡片柔光高亮：描边珊瑚 → 逐帧淡回奶油。"""
        c = self._cards.get(pid)
        if not c:
            return
        frame = c["frame"]
        frame.configure(highlightthickness=2,
                        highlightbackground=self._accent)

        def fade(i):
            c2 = self._cards.get(pid)
            if not c2:
                return
            f = c2["frame"]
            t = i / 12.0
            f.configure(highlightbackground=_hx_mix(self._accent, self._line, t))
            if i < 12:
                self._anim_jobs[pid] = self.after(20, fade, i + 1)
            else:
                f.configure(highlightthickness=1, highlightbackground=self._line)
        self._anim_jobs[pid] = self.after(20, fade, 0)

    # ---------- 卡片 ----------
    def _avatar_color(self, uid):
        try:
            return AV_FILLS[uid % len(AV_FILLS)]
        except (TypeError, ValueError):
            return AV_FILLS[0]

    def _initials(self, nick):
        n = (nick or "").strip() or "?"
        return n[0].upper()

    def _ensure_card(self, post, top=False, animate=False):
        pid = post["pid"]
        if pid in self._cards:
            return
        card = tk.Frame(self._inner, bg=self._card)
        if animate:
            card.configure(highlightthickness=2,
                           highlightbackground=self._accent)
        card.pack(fill="x", padx=10, pady=5)
        if top:
            card.pack(front=True, padx=10, pady=5)

        # ---- 头部：圆角方形头像 + 昵称 + 相对时间 ----
        head = tk.Frame(card, bg=self._card)
        head.pack(fill="x", padx=10, pady=(10, 2))
        av = tk.Canvas(head, width=40, height=40, bg=self._card,
                       highlightthickness=0)
        av.pack(side="left")
        _round_sq(av, self._avatar_color(post.get("uid")))
        av.create_text(20, 20, text=self._initials(post.get("nick")),
                       fill="#ffffff", font=(self._font[0], 15, "bold"))
        inf = tk.Frame(head, bg=self._card)
        inf.pack(side="left", padx=(8, 0))
        tk.Label(inf, text=post.get("nick") or "",
                 font=(self._font[0], self._font[1], "bold"),
                 bg=self._card, fg=self._name).pack(anchor="w")
        tk.Label(inf, text=_rel_time(post.get("ts")),
                 font=(self._font[0], 10), bg=self._card,
                 fg=self._sub).pack(anchor="w")
        own = (post.get("uid") == self._uid)
        if own:
            tk.Button(head, text="🗑", font=self._font, relief="flat", bd=0,
                      bg=self._card, fg=self._sub, activebackground=self._card,
                      command=lambda p=pid: self._host.del_moment(p)).pack(
                side="right")

        # ---- 正文 ----
        if post.get("text"):
            tk.Label(card, text=post["text"], font=self._font, justify="left",
                     wraplength=self._col_w - 20, anchor="w", bg=self._card,
                     fg=self._txt).pack(fill="x", padx=10, pady=(4, 2))

        # ---- 图片九宫格 ----
        imgf = tk.Frame(card, bg=self._card)
        imgf.pack(fill="x", padx=10, pady=(2, 4))

        # ---- 点赞 + 评论 合并框 ----
        act = tk.Frame(card, bg=self._card)
        act.pack(fill="x", padx=10, pady=(2, 2))
        liked = self._uid in (post.get("likes") or [])
        like_btn = tk.Button(act, text=f"♥ 赞 {len(post.get('likes') or [])}",
                             font=self._font, relief="flat", bd=0, bg=self._card,
                             fg=(self._accent if liked else self._name),
                             activebackground=self._card, cursor="hand2",
                             command=lambda p=pid, on=(not liked):
                                 self._toggle_like_anim(p, on))
        like_btn.pack(side="left")
        comments = post.get("comments") or []
        cbtn = tk.Button(act, text=f"💬 评论 {len(comments)}", font=self._font,
                         relief="flat", bd=0, bg=self._card, fg=self._name,
                         activebackground=self._card, cursor="hand2",
                         command=lambda p=pid: self._focus_comment(p))
        cbtn.pack(side="left", padx=12)

        # ---- 评论输入行 ----
        add = tk.Frame(card, bg=self._card)
        add.pack(fill="x", padx=10, pady=(0, 8))
        rep_lbl = tk.Label(add, text="", font=(self._font[0], 10),
                           bg=self._input, fg=self._accent, cursor="hand2")
        centry = tk.Entry(add, font=self._font, relief="flat",
                          bg=self._input, fg=self._txt,
                          insertbackground=self._txt)
        centry.pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=4)
        centry.bind("<Return>",
                    lambda e, p=pid, en=centry: self._comment(p, en))
        tk.Button(add, text="发表", font=self._font, relief="flat", bd=0,
                  bg=self._accent, fg="#ffffff", activebackground=self._accent,
                  cursor="hand2",
                  command=lambda p=pid, en=centry: self._comment(p, en)).pack(
            side="right")

        self._cards[pid] = {"frame": card, "imgf": imgf, "like_btn": like_btn,
                            "centry": centry, "rep_lbl": rep_lbl,
                            "soc_fr": None, "soc_anim": None, "rep_clear": None}
        self._render_comments(pid, comments)

        self._cv.after_idle(lambda: self._layout_images(pid))

    # ---------- 点赞回弹动画 ----------
    def _toggle_like_anim(self, pid, on):
        """心跳回弹：❤ 放大 → 回落，同时切换珊瑚色。"""
        liked = self._uid in self._current_likes(pid)
        target_on = not liked
        # 先发真实事件
        self._host.toggle_like(pid, target_on)
        btn = self._cards.get(pid, {}).get("like_btn")
        if not btn:
            return

        def pulse(i):
            b = self._cards.get(pid, {}).get("like_btn")
            if not b:
                return
            grow = max(0, 1 - abs(3 - i) / 3)       # 3 帧时峰值
            sym = "❤" if grow > 0.35 else "♥"
            size = self._font[1] + (2 if grow > 0.5 else 0)
            f = (self._font[0], size, "bold") if grow > 0.3 else self._font
            b.config(text=f"{sym} 赞 {len(self._current_likes(pid))}", font=f,
                     fg=self._accent if target_on else self._name)
            if i < 6:
                self._anim_jobs[pid] = self.after(45, pulse, i + 1)
            else:
                b.config(font=self._font)
        pulse(0)

    def _current_likes(self, pid):
        p = next((x for x in self._posts if x.get("pid") == pid), None)
        return p.get("likes") or [] if p else []

    # ---------- 评论 ----------
    def _render_comments(self, pid, comments):
        c = self._cards.get(pid)
        if not c:
            return
        card = c["frame"]
        soc = c.get("soc_fr")
        if soc:
            try:
                soc.destroy()
            except Exception:
                pass
            c["soc_fr"] = None
        if c.get("soc_anim"):
            try:
                self.after_cancel(c["soc_anim"])
            except Exception:
                pass
            c["soc_anim"] = None
        if not comments:
            return
        soc = tk.Frame(card, bg=self._input, highlightthickness=1,
                       highlightbackground=self._line)
        soc.pack(fill="x", padx=10, pady=(2, 2))
        self._build_rows(soc, pid, comments)
        c["soc_fr"] = soc
        # 评论框淡入：暖橙半透明 → 秒级回落回奶油
        def fade(i):
            c2 = self._cards.get(pid)
            if not c2:
                return
            sf = c2.get("soc_fr")
            if not sf:
                return
            t = i / 10.0
            sf.configure(highlightbackground=_hx_mix(self._accent, self._line, t),
                         bg=_hx_mix(self._accent, self._input, 0.35 * (1 - t)))
            if i < 10:
                c2["soc_anim"] = self.after(18, fade, i + 1)
            else:
                sf.configure(highlightbackground=self._line, bg=self._input)
        c["soc_anim"] = self.after(18, fade, 0)

    def _build_rows(self, parent, pid, comments):
        """把评论铺成「昵称：内容 ⤷回复」行；楼中楼显示『作者 回复 @被回者』并缩进。"""
        for cmt in comments:
            ismine = (cmt.get("uid") == self._uid)
            has_rep = cmt.get("rep")
            row = tk.Frame(parent, bg=self._input)
            row.pack(fill="x", padx=4, pady=1)
            if has_rep:                     # 楼中楼缩进
                tk.Frame(row, width=16, bg=self._input).pack(side="left")
            nmcol = self._accent if ismine else self._name
            tkwraph = self._col_w - 96
            tk.Label(row, text=f"{cmt.get('nick','')}",
                     font=self._font, bg=self._input, fg=nmcol).pack(side="left")
            if has_rep:
                tk.Label(row, text=" 回复 ", bg=self._input, fg=self._sub,
                         font=self._font).pack(side="left")
                tk.Label(row, text=f"@{has_rep.get('nick','')}", bg=self._input,
                         fg=self._accent, font=self._font).pack(side="left")
            tk.Label(row, text=f"：{cmt.get('text','')}", bg=self._input,
                     fg=self._txt, font=self._font, justify="left",
                     wraplength=tkwraph).pack(side="left")
            tk.Button(row, text="回复", font=(self._font[0], 9), relief="flat",
                      bd=0, bg=self._input, fg=self._sub,
                      activebackground=self._line, cursor="hand2",
                      command=lambda p=pid, c=cmt: self._set_rep(p, c)).pack(
                side="right")

    def _focus_comment(self, pid):
        en = self._cards.get(pid, {}).get("centry")
        if en:
            en.focus_set()

    def _layout_images(self, pid):
        """按当前内容列宽稳定铺九宫格：1 张走大图，>=2 铺 3 列均匀方形。"""
        p = next((x for x in self._posts if x.get("pid") == pid), None)
        c = self._cards.get(pid)
        if not p or not c:
            return
        imgs = [fn for fn in (p.get("images") or []) if fn in self._img_cache]
        imgf = c["imgf"]
        for w in imgf.winfo_children():
            w.destroy()
        if not imgs:
            return
        avail = max(self._col_w - 20, 240)
        n = len(imgs)
        if n == 1:
            _place_img(self, imgf, imgs[0], max_w=avail, max_h=260,
                       square=False, anchor="nw")
        else:
            cols = 3 if n >= 3 else n
            gap = 5
            cell = (avail - (cols - 1) * gap) // cols
            for idx, fn in enumerate(imgs):
                r, cidx = divmod(idx, cols)
                holder = tk.Frame(imgf, bg=self._card)
                holder.grid(row=r, column=cidx, padx=(gap // 2), pady=(gap // 2))
                _place_img(self, holder, fn, max_w=cell, max_h=cell,
                           square=True, anchor="w")
            imgf.grid_columnconfigure(list(range(cols)), weight=0)

    # ---------- 发布/赞/评/删 ----------
    def _pick_images(self):
        paths = filedialog.askopenfilenames(
            title="选择图片（最多9张）",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.gif *.webp *.bmp")])
        paths = list(paths)[:9]
        self._paths = paths
        self._img_label.config(text=f"已选 {len(paths)} 张" if paths else "")

    def _publish(self):
        text = self._text.get("1.0", "end").strip()
        if not text and not self._paths:
            return
        self._status.config(text="发布中…", fg=self._sub)
        self._host.publish_moment(text, list(self._paths))
        self._text.delete("1.0", "end")
        self._paths = []
        self._img_label.config(text="")
        self._cam.focus_set()

    def _comment(self, pid, entry):
        text = entry.get().strip()
        if text:
            ru, rn = self._rep_target.get(pid) or (None, "")
            self._host.comment_moment(pid, text, ru, rn)
            entry.delete(0, "end")
            self._clear_rep(pid)

    def _set_rep(self, pid, cmt):
        """把评论输入切换为「回复 @某人」，占位显示在输入框左侧。"""
        self._rep_target[pid] = (cmt.get("uid"), cmt.get("nick") or "")
        c = self._cards.get(pid)
        if not c:
            return
        lbl = c.get("rep_lbl")
        lbl.config(text=f"回复 @{cmt.get('nick','')}  ✕", fg=self._accent)
        lbl.pack(side="left", padx=(0, 4), before=c.get("centry"))
        lbl.bind("<Button-1>", lambda _e, p=pid: self._clear_rep(p))
        if c.get("centry"):
            c["centry"].focus_set()

    def _clear_rep(self, pid):
        self._rep_target.pop(pid, None)
        c = self._cards.get(pid)
        if c and c.get("rep_lbl"):
            c["rep_lbl"].pack_forget()

    # ---------- 图片懒加载 ----------
    def _request_img(self, pid, fn):
        if fn in self._img_cache:
            self._layout_images(pid)
            return
        self._host.fetch_img(fn)

    def feed_img(self, fn, ext, blob):
        """moment_data 回填：解码缩略，缓存 PIL，再按格子重排。"""
        if not blob:
            return
        try:
            im = PILImage.open(__import__("io").BytesIO(blob))
            im.thumbnail((self._max_img, self._max_img))
        except Exception:
            return
        self._img_cache[fn] = im             # 显式持有 PIL，防止 GC 丢图
        pid_txt = fn.split("_", 1)[0]
        try:
            pid = int(pid_txt)
        except (TypeError, ValueError):
            pid = None
        if pid is not None:
            self._layout_images(pid)


def _thumb_fit(im, max_w, max_h, square=False):
    """等比缩放（square 时先中心裁方再填满 max_w×max_h，保证格子均匀）。"""
    w, h = im.size
    if square:
        s = min(w, h)
        im = im.crop(((w - s) // 2, (h - s) // 2,
                      (w - s) // 2 + s, (h - s) // 2 + s))
        w = h = s
        im = im.resize((max_w, max_h), PILImage.LANCZOS)
        return im, max_w, max_h
    scale = min(max_w / w, max_h / h, 1.0)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    if scale < 1.0:
        im = im.resize((nw, nh), PILImage.LANCZOS)
    return im, nw, nh


def _place_img(widget, parent, fn, max_w, max_h, square=False, anchor="nw"):
    """把缓存 PIL 按格子裁切缩放后铺进 parent。"""
    src = widget._img_cache.get(fn)
    if src is None:
        return False
    im, nw, nh = _thumb_fit(src, max_w, max_h, square=square)
    photo = ImageTk.PhotoImage(im)
    lbl = tk.Label(parent, image=photo, bg=parent["bg"])
    lbl.image = photo        # 引用持有，防 GC
    lbl.pack(anchor=anchor)
    return True


def _round_sq(cv, color, r=10):
    """手绘圆角方形头像。"""
    w = cv.winfo_reqwidth() or 40
    h = cv.winfo_reqheight() or 40
    w, h = 40, 40
    cv.create_arc(r, r, 2 * r, 2 * r, start=90, extent=90, fill=color, outline="")
    cv.create_arc(w - 2 * r, r, w, 2 * r, start=0, extent=90, fill=color,
                  outline="")
    cv.create_arc(r, h - 2 * r, 2 * r, h, start=180, extent=90, fill=color,
                  outline="")
    cv.create_arc(w - 2 * r, h - 2 * r, w, h - r, start=270, extent=90,
                  fill=color, outline="")
    cv.create_rectangle(r, 2, w - r, h - 2, fill=color, outline="")
    cv.create_rectangle(2, r, w - 2, h - r, fill=color, outline="")


def _round_txt(cv, x, y, text, font, color, anchor=0):
    cv.create_text(x, y, text=text, font=font, fill=color, anchor="nw")