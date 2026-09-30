"""Excel 工作簿集成与旧聊天渲染回归。"""
import tkinter as tk
from types import SimpleNamespace
import pytest
from theme import get_skin, msg_colors
from widgets.excel_chrome import ExcelChrome
from widgets.msg_list import MsgList


@pytest.fixture(scope="module")
def root():
    try:
        window = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"无可用 Tk 显示环境: {error}")
    window.withdraw()
    window.geometry("1000x650")
    yield window
    window.destroy()


@pytest.fixture(autouse=True)
def clear_widgets(root):
    yield
    for widget in list(root.winfo_children()):
        if widget.winfo_exists():
            widget.destroy()


class MemoryPrefs:
    def __init__(self):
        self.values = {}
    def get(self, key, default=None):
        return self.values.get(key, default)
    def set(self, key, value):
        self.values[key] = value


def test_workbook_formula_send_and_sheet_switch(root):
    sent = []
    prefs = MemoryPrefs()
    app = SimpleNamespace(root=root, _skin=get_skin("excel"), _prefs=prefs,
                          view=("public", None), _ro_mode=False,
                          core=SimpleNamespace(uid=1, roster={}, groups={}),
                          _send_excel_text=lambda value: sent.append(value) or True,
                          _sync_excel_layout=lambda: None)
    anchor = tk.Frame(root)
    anchor.pack()
    chrome = ExcelChrome(root, app)
    chrome.set_anchor(anchor)
    chrome.set_visible(True)
    chrome.sheet_area.pack(fill="both", expand=True)
    root.deiconify()
    root.update()
    chrome.work_sheet.select_cell(2, 2)
    chrome.formula_var.set("中文单元格")
    chrome.apply_formula()
    assert chrome.work_sheet.get_cell(2, 2) == "中文单元格"
    assert sent == []                       # 填表不会自动发送
    chrome.send_selected()
    assert sent == ["中文单元格"]
    assert chrome.work_sheet.get_cell(2, 2) == "中文单元格"
    chrome._save_workbook()
    assert prefs.values["excel_cells"]["C3"] == "中文单元格"
    chrome.show_sheet("messages")
    assert chrome.send_selected() is False
    assert sent == ["中文单元格"]
    chrome.show_sheet("workbook")
    assert chrome.work_sheet.get_cell(2, 2) == "中文单元格"
    assert chrome.sheet_row.pack_info()["side"] == "bottom"
    chrome.set_visible(False)
    assert chrome.winfo_manager() == ""
    assert chrome.sheet_row.winfo_manager() == ""
    assert chrome.sheet_area.winfo_manager() == ""
    chrome.work_sheet.select_cell(4, 4)
    chrome.work_sheet.edit_selected(initial="关闭前的输入")
    chrome.destroy()
    assert prefs.values["excel_cells"]["E5"] == "关闭前的输入"


def test_workbook_grid_is_bounded_and_preserves_message_rows(root):
    messages = MsgList(root, ("Segoe UI", 10), colors=msg_colors(get_skin("excel")))
    messages.pack(fill="both", expand=True)
    root.deiconify()
    root.update()
    messages.set_grid("#c5d2c8")
    for index in range(100):
        messages.append({"uid": 1, "nick": "test", "seq": index + 1,
                         "channel": "public", "text": f"第 {index + 1} 条", "ts": 1.0})
    root.update()
    rows = list(messages._rows)
    for fraction in (0.0, 0.5, 1.0, 0.0):
        messages.yview_moveto(fraction)
        messages._render()
        assert 0 < len(messages.find_withtag("excel_grid")) < 100
    messages.set_grid(None)
    assert not messages.find_withtag("excel_grid")
    assert messages._rows == rows
