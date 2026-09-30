# -*- coding: utf-8 -*-
"""Excel 主界面冒烟；隔离偏好和历史，不连接服务器。"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from client import ChatWindow
from client_core import ClientCore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="moyu-excel-") as folder:
        folder = Path(folder)
        pref_path = folder / "prefs.json"
        pref_path.write_text(json.dumps({"skin": "excel", "frameless": True,
                                        "skin_follow_system": False, "dnd": True}),
                             encoding="utf-8")
        core = ClientCore(nick="开发预览", history_dir=str(folder / "history"))
        core.uid = 1
        core.roster = {1: {"uid": 1, "nick": "开发预览", "type": "tcp"},
                       2: {"uid": 2, "nick": "项目协作", "type": "tcp"},
                       3: {"uid": 3, "nick": "产品讨论", "type": "web"}}
        app = ChatWindow(core, prefs_path=str(pref_path))
        app.msg_list.set_me_uid(core.uid)
        errors = []
        app.root.report_callback_exception = lambda *details: errors.append(details)
        app.root.geometry("1060x740+80+80")
        app.root.deiconify()
        def pump(seconds=0.2):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                app.root.update()
                time.sleep(0.02)
        try:
            app._refresh_roster()
            for index, (uid, nick, text) in enumerate([
                (2, "项目协作", "Excel 工作簿皮肤已就绪。"),
                (1, "开发预览", "顶部功能区可以搜索消息、发送附件和打开设置。"),
                (2, "项目协作", "会话、消息和工作表标签仍是实际聊天功能。"),
                (1, "开发预览", "切换其他皮肤时，聊天记录和输入内容都会保留。"),
            ]):
                app._append_msg({"t": "chat", "channel": "public", "uid": uid,
                                 "nick": nick, "text": text, "seq": index + 1,
                                 "ts": time.time() + index})
            pump()
            count = len(app.msg_list._rows)
            assert app._excel_chrome.winfo_ismapped()
            assert app._excel_chrome.sheet_row.winfo_ismapped()
            assert not app._body_frame.winfo_ismapped()
            assert app._excel_chrome.sheet_area.winfo_ismapped()
            for skin in ("office", "dark", "excel"):
                app._on_skin_change(skin)
                pump()
                assert bool(app._excel_chrome.winfo_ismapped()) == (skin == "excel")
                assert bool(app._excel_chrome.sheet_row.winfo_ismapped()) == (skin == "excel")
                assert len(app.msg_list._rows) == count
            assert json.loads(pref_path.read_text(encoding="utf-8"))["skin"] == "excel"
            chrome = app._excel_chrome
            sheet = chrome.work_sheet
            for row, values in enumerate([
                ["序号", "项目", "说明", "状态"],
                ["1", "需求整理", "本周工作", "已完成"],
                ["2", "界面调整", "工作表", "进行中"],
                ["3", "测试验证", "输入格子", "待复核"],
            ]):
                for col, value in enumerate(values):
                    sheet.set_cell(row, col, value)
            sheet.select_cell(4, 2)
            sheet.edit_selected(initial="中文格子")
            pump()
            sheet.editor.event_generate("<Return>")
            pump()
            assert sheet.get_cell(4, 2) == "中文格子"
            assert sheet.selected_cell == (5, 2)
            sheet.select_cell(5, 2)
            chrome.formula_var.set("公式栏输入")
            chrome.apply_formula()
            pump()
            assert sheet.get_cell(5, 2) == "公式栏输入"
            assert chrome.name_var.get() == "C6"
            sent = []
            original_send = core.send_chat
            core.send_chat = lambda text, **fields: sent.append((text, fields)) or True
            app.entry.insert("1.0", "原聊天草稿")
            try:
                sheet.edit_selected(initial="从单元格发送")
                pump()
                sheet.editor.event_generate("<Control-Return>")
                pump()
                assert sent and sent[-1][0] == "从单元格发送"
                assert app._entry_text() == "原聊天草稿"
                assert sheet.get_cell(5, 2) == "从单元格发送"
            finally:
                core.send_chat = original_send
            chrome.show_sheet("messages")
            pump()
            assert chrome.message_sheet.winfo_ismapped()
            assert chrome.message_sheet.get_cell(0, 2)
            assert not chrome.message_sheet.set_cell(0, 2, "禁止修改历史")
            chrome.show_sheet("workbook")
            pump()
            chrome.show_native()
            pump()
            assert app._body_frame.winfo_ismapped()
            chrome.show_sheet("workbook")
            pump()
            assert not app._body_frame.winfo_ismapped()
            app._on_settings()
            pump()
            assert app._settings_win.winfo_ismapped()
            app._close_settings()
            pump()
            sheet.select_cell(6, 2)
            sheet.edit_selected(initial="这个格子可以直接打字")
            pump()
            sheet.editor.event_generate("<KeyRelease>")
            pump()
            if args.screenshot:
                from PIL import ImageGrab
                args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                hwnd = ctypes.windll.user32.GetAncestor(app.root.winfo_id(), 2)
                pump(0.5)
                ImageGrab.grab(window=hwnd).save(args.screenshot)
            app.root.geometry("680x480")
            pump()
            assert chrome.active_sheet.grid_canvas.winfo_height() > 80
            assert app._excel_chrome.sheet_row.winfo_ismapped()
            assert not errors, errors
            print("Excel worksheet smoke passed: cells, Chinese input, formula bar, Ctrl+Enter, sheets, drafts, skins, 680x480")
            if args.preview:
                app.root.mainloop()
        finally:
            if not app._closed:
                app.quit_app()
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
