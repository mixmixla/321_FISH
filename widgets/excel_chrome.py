# -*- coding: utf-8 -*-
"""Excel 工作簿外观：可编辑工作表、公式栏及独立的会话记录表页。"""
from __future__ import annotations
import re
import tkinter as tk
from tkinter import ttk, simpledialog
import time
from typing import Callable

from widgets.excel_sheet import ExcelSheet


class ExcelChrome(tk.Frame):
    _TABS = ("文件", "开始", "插入", "页面布局", "公式", "数据", "审阅", "视图")

    def __init__(self, master, app, font=None, *, visible=False):
        self.app = app
        self._font = font or ("Microsoft YaHei", 9)
        self._anchor = None
        self._visible = False
        self._native = False
        self._poll_id = None
        self._save_id = None
        self._signature = None
        self._context = "公共频道"
        self._formula_target = None
        self._formula_loading = False
        self._buttons = []
        self._tab = "workbook"
        self._conversation_choices = {}
        super().__init__(master, bg="#f3f3f3", bd=0)
        self._build()
        self.set_theme(getattr(app, "_skin", {}) or {})
        self.set_visible(visible)
        self._poll_id = self.after(350, self._poll)

    def _button(self, parent, text, command, **kw):
        button = tk.Button(parent, text=text, command=command, font=self._font,
                           bd=0, relief="flat", bg="#fafafa", fg="#333333",
                           activebackground="#dcefe3", padx=6, pady=2, **kw)
        self._buttons.append((button, "fg"))
        return button

    def _build(self):
        self.header = tk.Frame(self, height=30, bg="#217346")
        self.header.pack_propagate(False)
        tk.Label(self.header, text="▦  工作簿1 · 内部办公助手", bg="#217346",
                 fg="white", font=(self._font[0], 10)).pack(side="left", padx=10)
        self._button(self.header, "设置", lambda: self._invoke("_on_settings")).pack(side="right")
        self.tab_row = tk.Frame(self, bg="#217346", height=27)
        self.tab_row.pack(fill="x")
        self.tab_row.pack_propagate(False)
        self._tab_labels = []
        for text in self._TABS:
            button = tk.Button(self.tab_row, text=text, bd=0, relief="flat",
                               bg="#217346", fg="white", activebackground="#ffffff",
                               activeforeground="#217346", font=self._font, padx=11,
                               command=lambda t=text: self._ribbon_tab(t))
            button.pack(side="left", fill="y")
            self._tab_labels.append(button)
        self._tab_labels[1].configure(bg="#f5f5f5", fg="#217346")
        self.ribbon = tk.Frame(self, bg="#f5f5f5", height=86)
        self.ribbon.pack(fill="x")
        self.ribbon.pack_propagate(False)
        def group(title):
            frame = tk.Frame(self.ribbon, bg="#f5f5f5", padx=7)
            frame.pack(side="left", fill="y", pady=3)
            body = tk.Frame(frame, bg="#f5f5f5")
            body.pack(fill="both", expand=True)
            tk.Label(frame, text=title, bg="#f5f5f5", fg="#777777",
                     font=(self._font[0], 8)).pack(fill="x", side="bottom")
            tk.Frame(self.ribbon, bg="#d9d9d9", width=1).pack(side="left", fill="y", pady=7)
            return body
        clip = group("剪贴板")
        self._button(clip, "▣\n粘贴", lambda: self._sheet_action("paste_selection"),
                     width=5, height=2).pack(side="left", fill="y")
        actions = tk.Frame(clip, bg="#f5f5f5")
        actions.pack(side="left")
        self._button(actions, "✂ 剪切", lambda: self._sheet_action("cut_selection")).pack(anchor="w")
        self._button(actions, "▢ 复制", lambda: self._sheet_action("copy_selection")).pack(anchor="w")
        display = group("字体 / 显示")
        self.font_var = tk.StringVar(value="Calibri")
        self.size_var = tk.StringVar(value="11")
        fonts = ttk.Combobox(display, textvariable=self.font_var, width=15,
                             values=("Calibri", "Arial", "Microsoft YaHei", "宋体", "Consolas"),
                             state="readonly")
        fonts.pack(side="left", padx=2, anchor="n", pady=7)
        sizes = ttk.Combobox(display, textvariable=self.size_var, width=3,
                             values=("9", "10", "11", "12", "14", "16", "18"), state="readonly")
        sizes.pack(side="left", padx=2, anchor="n", pady=7)
        fonts.bind("<<ComboboxSelected>>", lambda _e: self._change_font())
        sizes.bind("<<ComboboxSelected>>", lambda _e: self._change_font())
        edit = group("单元格")
        self._button(edit, "编辑  F2", lambda: self._sheet_action("edit_selected")).pack(anchor="w")
        self._button(edit, "清除  Delete", lambda: self._sheet_action("clear_selection")).pack(anchor="w")
        send = group("协作")
        self.send_button = self._button(send, "发送单元格\nCtrl+Enter", self.send_selected,
                                        width=12, height=2)
        self.send_button.pack(side="left")
        self._button(send, "附件", lambda: self._invoke("_on_send_file")).pack(anchor="w")
        self._button(send, "游戏", lambda: self._invoke("open_game")).pack(anchor="w")
        view = group("视图")
        self._button(view, "原聊天界面", self.show_native).pack(anchor="w")
        self._button(view, "设置", lambda: self._invoke("_on_settings")).pack(anchor="w")
        self.formula_row = tk.Frame(self, bg="#f3f3f3", height=29, padx=4, pady=3)
        self.formula_row.pack(fill="x")
        self.formula_row.pack_propagate(False)
        self.name_var = tk.StringVar(value="A1")
        self.name_box = tk.Entry(self.formula_row, textvariable=self.name_var, width=9,
                                 relief="solid", bd=1, font=self._font)
        self.name_box.pack(side="left", fill="y")
        self.name_box.bind("<Return>", self._jump_address)
        self._button(self.formula_row, "×", self.cancel_formula).pack(side="left", padx=(8, 0))
        self._button(self.formula_row, "✓", self.apply_formula).pack(side="left")
        tk.Label(self.formula_row, text="ƒx", bg="#f3f3f3", fg="#555555",
                 font=("Calibri", 12, "italic"), width=3).pack(side="left")
        self.formula_var = tk.StringVar()
        self.formula_entry = tk.Entry(self.formula_row, textvariable=self.formula_var,
                                      relief="solid", bd=1, font=("Calibri", 11))
        self.formula_entry.pack(side="left", fill="both", expand=True)
        self.formula_entry.bind("<FocusIn>", self._formula_focus)
        self.formula_entry.bind("<Return>", self.apply_formula)
        self.formula_entry.bind("<Escape>", self.cancel_formula)
        self.formula_entry.bind("<FocusOut>", self._formula_blur)
        self.formula_entry.bind("<Control-Return>", self._formula_send)
        self.sheet_area = tk.Frame(self.master, bg="white")
        self.work_sheet = ExcelSheet(self.sheet_area, font=("Calibri", 11),
                                    on_selection=self._on_selection,
                                    on_commit=self._on_commit,
                                    on_send=self._send_value, on_edit=self._on_edit)
        self.message_sheet = ExcelSheet(self.sheet_area, font=("Calibri", 11),
                                       on_selection=self._on_selection)
        prefs = getattr(self.app, "_prefs", None)
        if prefs is not None:
            self.work_sheet.import_cells(prefs.get("excel_cells", {}))
        self.work_sheet.pack(fill="both", expand=True)
        self.sheet_row = tk.Frame(self.master, bg="#f3f3f3", height=28)
        self.sheet_row.pack_propagate(False)
        tk.Label(self.sheet_row, text="◁  ▷", bg="#f3f3f3", fg="#777777",
                 font=self._font, width=6).pack(side="left")
        self._sheet_tabs = {}
        for key, label in (("workbook", "工作表1"), ("messages", "会话记录")):
            button = self._button(self.sheet_row, label, lambda k=key: self.show_sheet(k))
            button.pack(side="left", fill="y")
            self._sheet_tabs[key] = button
        tk.Label(self.sheet_row, text="  当前会话：", bg="#f3f3f3", fg="#555555",
                 font=self._font).pack(side="left", padx=(12, 0))
        self.conversation_var = tk.StringVar(value="公共频道")
        self.conversation_box = ttk.Combobox(self.sheet_row, textvariable=self.conversation_var,
                                             state="readonly", width=22)
        self.conversation_box.pack(side="left", pady=2)
        self.conversation_box.bind("<<ComboboxSelected>>", self._pick_conversation)
        self.status_var = tk.StringVar(value="就绪 · Enter 保存格子，Ctrl+Enter 发送")
        tk.Label(self.sheet_row, textvariable=self.status_var, bg="#f3f3f3", fg="#444444",
                 font=(self._font[0], 8), anchor="e").pack(side="right", fill="x", expand=True, padx=8)
        self._style_sheet_tabs()

    @property
    def active_sheet(self):
        return self.message_sheet if self._tab == "messages" else self.work_sheet

    def _invoke(self, method):
        callback = getattr(self.app, method, None)
        if callable(callback):
            return callback()

    def _sheet_action(self, method):
        if self._tab == "messages" and method != "copy_selection":
            self.status_var.set("会话记录只读，请切换工作表1填写")
            return None
        return getattr(self.active_sheet, method)()

    def _ribbon_tab(self, text):
        for tab in self._tab_labels:
            active = tab.cget("text") == text
            tab.configure(bg="#f5f5f5" if active else "#217346",
                          fg="#217346" if active else "white")
        if text == "公式":
            self.formula_entry.focus_set()
        elif text in ("数据", "审阅"):
            self.show_sheet("messages")
        elif text == "视图":
            self.show_sheet("workbook")
        elif text == "文件":
            self._invoke("_on_settings")
        elif text == "插入":
            self.active_sheet.edit_selected()

    def _on_selection(self, address, value):
        if self._formula_target:
            sheet, (row, col) = self._formula_target
            previous = self.formula_var.get()
            self._formula_target = None
            if sheet.set_cell(row, col, previous) and sheet is self.work_sheet:
                self._on_commit(row, col, previous)
            if sheet is self.active_sheet:
                value = sheet.get_selected_value()
        self._formula_loading = True
        self.name_var.set(address)
        self.formula_var.set(str(value or ""))
        self._formula_target = None
        self._formula_loading = False
        sheet = getattr(self, "message_sheet" if self._tab == "messages" else "work_sheet", None)
        readonly = sheet is not None and sheet._is_message_readonly(*sheet.selected_cell)
        self.formula_entry.configure(state="readonly" if readonly else "normal")

    def _on_edit(self, value):
        if not self._formula_loading:
            self.formula_var.set(value)

    def _on_commit(self, row, col, value):
        if self._save_id is not None:
            self.after_cancel(self._save_id)
        self._save_id = self.after(180, self._save_workbook)
        self.status_var.set("本地工作表已编辑 · Ctrl+Enter 发送当前格")

    def _save_workbook(self):
        self._save_id = None
        prefs = getattr(self.app, "_prefs", None)
        if prefs is not None:
            prefs.set("excel_cells", self.work_sheet.export_cells())
        self.status_var.set("已保存本地工作表 · Ctrl+Enter 发送当前格")

    def _formula_focus(self, _event=None):
        self._formula_target = (self.active_sheet, self.active_sheet.selected_cell)

    def _formula_blur(self, _event=None):
        if self._formula_target:
            sheet, (row, col) = self._formula_target
            value = self.formula_var.get()
            self._formula_target = None
            if sheet.set_cell(row, col, value) and sheet is self.work_sheet:
                self._on_commit(row, col, value)

    def apply_formula(self, _event=None):
        sheet = self.active_sheet
        value = self.formula_var.get()
        if self._formula_target:
            target, (row, col) = self._formula_target
            self._formula_target = None
            if target.set_cell(row, col, value) and target is self.work_sheet:
                self._on_commit(row, col, value)
        else:
            if sheet.set_selected_value(value) and sheet is self.work_sheet:
                self._on_commit(*sheet.selected_cell, value)
        sheet.grid_canvas.focus_set()
        return "break"

    def cancel_formula(self, _event=None):
        self._formula_target = None
        self.active_sheet.cancel_edit()
        self.formula_var.set(self.active_sheet.get_selected_value())
        self.active_sheet.grid_canvas.focus_set()
        return "break"

    def _formula_send(self, _event=None):
        self.apply_formula()
        self.send_selected()
        return "break"

    def _jump_address(self, _event=None):
        match = re.fullmatch(r"([A-Za-z]+)([1-9][0-9]*)", self.name_var.get().strip())
        if match:
            col = 0
            for char in match[1].upper():
                col = col * 26 + ord(char) - 64
            try:
                self.active_sheet.select_cell(int(match[2]) - 1, col - 1)
                self.active_sheet.grid_canvas.focus_set()
            except (IndexError, ValueError):
                self.status_var.set("单元格地址超出工作表范围")
        else:
            self.status_var.set("请输入单元格地址，例如 C5")
        return "break"

    def _change_font(self):
        for sheet in (self.work_sheet, self.message_sheet):
            sheet.set_font((self.font_var.get(), int(self.size_var.get())))

    def _send_value(self, value):
        callback = getattr(self.app, "_send_excel_text", None)
        if callback:
            ok = callback(str(value))
            self.status_var.set("已提交发送 · 内容保留在单元格" if ok else "发送未成功，请检查会话或连接")
            return ok
        return False

    def send_selected(self):
        if self._tab != "workbook":
            self.status_var.set("请从工作表1发送单元格内容")
            return False
        self.active_sheet.commit_edit()
        return self._send_value(self.active_sheet.get_selected_value())

    def _style_sheet_tabs(self):
        for key, button in self._sheet_tabs.items():
            active = key == self._tab and not self._native
            button.configure(bg="white" if active else "#f3f3f3",
                             fg="#217346" if active else "#444444",
                             font=(self._font[0], 9, "bold" if active else "normal"))

    def show_sheet(self, key="workbook"):
        self.active_sheet.commit_edit()
        self._tab = key
        self._native = False
        self.work_sheet.pack_forget()
        self.message_sheet.pack_forget()
        self.active_sheet.pack(fill="both", expand=True)
        self._style_sheet_tabs()
        sync = getattr(self.app, "_sync_excel_layout", None)
        if sync:
            sync()
        self.refresh_messages()
        self.active_sheet.select_cell(*self.active_sheet.selected_cell)
        self.active_sheet.grid_canvas.focus_set()

    def show_native(self):
        self.active_sheet.commit_edit()
        self._native = True
        self._style_sheet_tabs()
        sync = getattr(self.app, "_sync_excel_layout", None)
        if sync:
            sync()

    def find_cell(self):
        query = simpledialog.askstring("查找", "查找单元格内容：", parent=self.app.root)
        if query:
            sheet = self.active_sheet
            for row in range(sheet.row_count):
                for col in range(sheet.column_count):
                    if query.casefold() in sheet.get_cell(row, col).casefold():
                        sheet.select_cell(row, col)
                        sheet.grid_canvas.focus_set()
                        self.status_var.set(f"找到：{sheet.selected_address()}")
                        return "break"
            self.status_var.set("没有找到匹配的单元格")
        return "break"

    def refresh_messages(self):
        messages = getattr(self.app, "msg_list", None)
        if messages is None:
            return
        rows = []
        for index, row in enumerate(messages._rows):
            record = dict(row.raw)
            record["time"] = time.strftime("%H:%M:%S", time.localtime(float(record.get("ts") or 0)))
            record["sender"] = record.get("nick") or "系统"
            record["content"] = "（消息已撤回）" if record.get("deleted") else messages.body_text(index)
            record["status"] = "发送失败" if record.get("failed") else "发送中" if record.get("pending") else "已编辑" if record.get("edited") else "已接收"
            rows.append(record)
        signature = tuple((r.get("seq"), r.get("text"), r.get("deleted"),
                           r.get("pending"), r.get("failed"), r.get("sticker")) for r in rows)
        if signature != self._signature:
            self._signature = signature
            self.message_sheet.set_messages(rows)

    def refresh_conversations(self):
        core = getattr(self.app, "core", None)
        choices = {"公共频道": ("public", None)}
        if core is not None:
            for uid, user in getattr(core, "roster", {}).items():
                if uid != getattr(core, "uid", None):
                    choices[f"{user.get('nick', uid)} ({uid})"] = ("private", uid)
            for gid, group in getattr(core, "groups", {}).items():
                choices[f"群：{group.get('name', gid)} ({gid})"] = ("group", gid)
        view = getattr(self.app, "view", ("public", None))
        current = next((name for name, target in choices.items() if target == view), self._context)
        choices.setdefault(current, view)
        self._conversation_choices = choices
        self.conversation_box.configure(values=list(choices))
        self.conversation_var.set(current)
        self.send_button.configure(state="disabled" if self._tab != "workbook" or getattr(self.app, "_ro_mode", False) else "normal")

    def _pick_conversation(self, _event=None):
        target = self._conversation_choices.get(self.conversation_var.get())
        if target is not None:
            self.app._switch_view(*target)
            self.refresh_messages()

    def _poll(self):
        if self._visible:
            self.refresh_messages()
            self.refresh_conversations()
        self._poll_id = self.after(350, self._poll)

    def set_context(self, text):
        self._context = str(text or "公共频道")
        self.refresh_conversations()

    def set_anchor(self, widget):
        self._anchor = widget

    def set_visible(self, visible):
        self._visible = bool(visible)
        if visible:
            kw = {"fill": "x"}
            if self._anchor is not None:
                kw["before"] = self._anchor
            self.pack(**kw)
            kw = {"side": "bottom", "fill": "x"}
            if self._anchor is not None:
                kw["before"] = self._anchor
            self.sheet_row.pack(**kw)
            # 已有自绘标题栏时仅保留一个绿色标题，避免双层标题条。
            if getattr(self.app, "title_bar", None) is None:
                self.header.pack(fill="x", before=self.tab_row)
            else:
                self.header.pack_forget()
        else:
            self.work_sheet.commit_edit()
            if self._save_id is not None:
                self.after_cancel(self._save_id)
                self._save_workbook()
            self.pack_forget()
            self.sheet_area.pack_forget()
            self.sheet_row.pack_forget()

    def set_theme(self, skin):
        accent = skin.get("accent", "#217346")
        if hasattr(self, "work_sheet"):
            for sheet in (self.work_sheet, self.message_sheet):
                sheet.set_theme({"accent": accent, "bg": "#ffffff", "grid": "#d4d4d4",
                                 "header_bg": "#f3f3f3", "fg": "#222222"})

    def destroy(self):
        self._formula_blur()
        self.work_sheet.commit_edit()
        if self._save_id is not None:
            self.after_cancel(self._save_id)
            self._save_workbook()
        if self._poll_id is not None:
            self.after_cancel(self._poll_id)
        for widget in (self.sheet_area, self.sheet_row):
            if widget.winfo_exists():
                widget.destroy()
        super().destroy()
