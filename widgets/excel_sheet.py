# -*- coding: utf-8 -*-
"""A small, editable Excel-like worksheet widget.

The widget deliberately implements a worksheet *surface*, rather than an
Excel formula engine.  Values are kept in a sparse dictionary and only the
cells in the visible canvas viewport are drawn.  There is one real
``tk.Entry`` while editing, so normal keyboard input (including a Chinese IME)
continues to work as it does in a regular Tk entry.

Rows and columns in the public API are zero based.  The address shown to the
user is the familiar one-based Excel address (``A1``, ``B3`` and so on).
Message rows supplied through :meth:`set_messages` are read-only in columns
A through D.  Local values in all other cells, including columns E onward on a
message row, remain independent of the message view.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Mapping
import re
import tkinter as tk
from typing import Any, Callable, Iterable


Callback = Callable[..., object] | None


class ExcelSheet(tk.Frame):
    """A sparse, keyboard-editable worksheet implemented with Tkinter.

    ``on_selection(address, value)`` is called whenever the active selection
    changes.  ``on_commit(row, col, value)`` is called for a user edit or a
    pasted value.  ``on_send(value)`` is called only by Ctrl+Enter; ordinary
    Enter commits and moves down without sending anything.

    The widget does not create an Entry per cell.  A single Entry is embedded
    over the selected cell while editing, which keeps a 1000x26 worksheet
    responsive and leaves the native Entry responsible for IME composition.
    """

    DEFAULT_ROWS = 1000
    DEFAULT_COLS = 26
    HEADER_HEIGHT = 25
    ROW_HEADER_WIDTH = 48
    ROW_HEIGHT = 23

    _ADDRESS_RE = re.compile(r"^([A-Za-z]+)([1-9][0-9]*)$")

    def __init__(
        self,
        master: tk.Misc,
        *,
        rows: int = DEFAULT_ROWS,
        cols: int = DEFAULT_COLS,
        font: object | None = None,
        column_width: int = 85,
        column_widths: Iterable[int] | None = None,
        on_selection: Callback = None,
        on_commit: Callback = None,
        on_send: Callback = None,
        on_edit: Callback = None,
        **kwargs: Any,
    ) -> None:
        self.row_count = max(1, int(rows))
        self.column_count = max(1, int(cols))
        self.on_selection = on_selection
        self.on_commit = on_commit
        self.on_send = on_send
        # Optional live formula-bar hook.  It is intentionally separate from
        # on_commit: typing should update a host preview without saving or
        # sending anything until the user chooses an explicit action.
        self.on_edit = on_edit
        self._font = self._normalise_font(font)

        # Local drafts are sparse.  Message data lives in a separate map so a
        # refreshed message list cannot destroy the user's workbook values.
        self._cells: dict[tuple[int, int], str] = {}
        self._message_rows: dict[int, tuple[str, str, str, str]] = {}
        self._message_records: list[dict[str, Any]] = []

        self.selected_row = 0
        self.selected_col = 0
        self._anchor = (0, 0)
        self._dragging = False
        self._editor: tk.Entry | None = None
        self._editor_var: tk.StringVar | None = None
        self._editor_trace: str | None = None
        self._editor_item: int | None = None
        self._editing_cell: tuple[int, int] | None = None
        self._last_drawn: tuple[int, int, int, int] = (0, 0, 0, 0)

        self._column_widths = self._make_column_widths(
            self.column_count, column_width=column_width, custom=column_widths
        )
        self._x_starts = [0]
        for width in self._column_widths:
            self._x_starts.append(self._x_starts[-1] + width)

        self._colors = {
            "frame": "#f3f3f3",
            "canvas": "#ffffff",
            "alt_row": "#fbfbfb",
            "header": "#f2f2f2",
            "header_active": "#e2f0d9",
            "readonly": "#f5f5f5",
            "line": "#d7d7d7",
            "line_dark": "#bcbcbc",
            "text": "#222222",
            "muted": "#666666",
            "selection": "#217346",
            "selection_fill": "#eaf4e3",
            "handle": "#217346",
            "editor_bg": "#fffef5",
        }

        super().__init__(master, bd=0, highlightthickness=0, bg=self._colors["frame"], **kwargs)
        self._build_widgets()
        self._bind_events()
        self._redraw()

    # ------------------------------------------------------------------
    # Construction and drawing
    # ------------------------------------------------------------------
    @staticmethod
    def _make_column_widths(
        count: int,
        *,
        column_width: int = 85,
        custom: Iterable[int] | None = None,
    ) -> list[int]:
        fallback = max(24, int(column_width))
        supplied = [max(24, int(width)) for width in custom] if custom is not None else []
        return [supplied[index] if index < len(supplied) else fallback for index in range(count)]

    @staticmethod
    def _normalise_font(font: object | None) -> tuple[object, ...]:
        """Keep a compact Tk font tuple for Canvas text and the Entry."""
        if isinstance(font, (tuple, list)) and len(font) >= 2:
            return tuple(font)
        if font:
            return (str(font), 9)
        return ("TkDefaultFont", 9)

    def _font_with(self, *, delta: int = 0, weight: str | None = None) -> tuple[object, ...]:
        family = self._font[0]
        try:
            size = int(self._font[1]) + delta
        except (IndexError, TypeError, ValueError):
            size = 9 + delta
        if weight:
            return (family, max(1, size), weight)
        return (family, max(1, size))

    def _build_widgets(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        self.corner = tk.Canvas(
            self,
            width=self.ROW_HEADER_WIDTH,
            height=self.HEADER_HEIGHT,
            bd=0,
            highlightthickness=0,
            bg=self._colors["header"],
        )
        self.corner.grid(row=0, column=0, sticky="nsew")

        self.column_header = tk.Canvas(
            self,
            height=self.HEADER_HEIGHT,
            bd=0,
            highlightthickness=0,
            bg=self._colors["header"],
            xscrollincrement=1,
        )
        self.column_header.grid(row=0, column=1, sticky="ew")

        self.row_header = tk.Canvas(
            self,
            width=self.ROW_HEADER_WIDTH,
            bd=0,
            highlightthickness=0,
            bg=self._colors["header"],
            yscrollincrement=1,
        )
        self.row_header.grid(row=1, column=0, sticky="ns")

        self.grid_canvas = tk.Canvas(
            self,
            bd=0,
            highlightthickness=0,
            takefocus=True,
            bg=self._colors["canvas"],
            xscrollcommand=self._xscroll_changed,
            yscrollcommand=self._yscroll_changed,
            xscrollincrement=1,
            yscrollincrement=1,
        )
        self.grid_canvas.grid(row=1, column=1, sticky="nsew")

        self.vscroll = tk.Scrollbar(self, orient="vertical", command=self._yview)
        self.vscroll.grid(row=1, column=2, sticky="ns")
        self.hscroll = tk.Scrollbar(self, orient="horizontal", command=self._xview)
        self.hscroll.grid(row=2, column=1, sticky="ew")

        total_width = self._x_starts[-1]
        total_height = self.row_count * self.ROW_HEIGHT
        self.grid_canvas.configure(scrollregion=(0, 0, total_width, total_height))
        self.column_header.configure(scrollregion=(0, 0, total_width, self.HEADER_HEIGHT))
        self.row_header.configure(scrollregion=(0, 0, self.ROW_HEADER_WIDTH, total_height))

    def _bind_events(self) -> None:
        canvas = self.grid_canvas
        canvas.bind("<Configure>", lambda _event: self._redraw(), add="+")
        canvas.bind("<Button-1>", self._on_button_press, add="+")
        canvas.bind("<B1-Motion>", self._on_button_motion, add="+")
        canvas.bind("<ButtonRelease-1>", self._on_button_release, add="+")
        canvas.bind("<Double-Button-1>", self._on_double_click, add="+")
        canvas.bind("<KeyPress>", self._on_key_press, add="+")
        canvas.bind("<Control-c>", self._on_copy, add="+")
        canvas.bind("<Control-C>", self._on_copy, add="+")
        canvas.bind("<Control-v>", self._on_paste, add="+")
        canvas.bind("<Control-V>", self._on_paste, add="+")
        canvas.bind("<Control-Return>", self._on_send_key, add="+")
        canvas.bind("<Control-KP_Enter>", self._on_send_key, add="+")
        canvas.bind("<MouseWheel>", self._on_mousewheel, add="+")
        canvas.bind("<Shift-MouseWheel>", self._on_mousewheel, add="+")
        canvas.bind("<Button-4>", self._on_mousewheel, add="+")
        canvas.bind("<Button-5>", self._on_mousewheel, add="+")

        # Scrolling over the headers should feel like scrolling over the sheet.
        for header in (self.column_header, self.row_header):
            header.bind("<MouseWheel>", self._on_mousewheel, add="+")
            header.bind("<Shift-MouseWheel>", self._on_mousewheel, add="+")
            header.bind("<Button-4>", self._on_mousewheel, add="+")
            header.bind("<Button-5>", self._on_mousewheel, add="+")

        self._draw_corner()

    def _draw_corner(self) -> None:
        self.corner.delete("all")
        self.corner.create_rectangle(
            0,
            0,
            self.ROW_HEADER_WIDTH,
            self.HEADER_HEIGHT,
            fill=self._colors["header"],
            outline=self._colors["line"],
        )
        self.corner.create_text(
            self.ROW_HEADER_WIDTH // 2,
            self.HEADER_HEIGHT // 2,
            text="▦",
            fill=self._colors["muted"],
            font=self._font_with(delta=1, weight="bold"),
        )

    @staticmethod
    def _column_label(col: int) -> str:
        result = ""
        number = int(col) + 1
        while number:
            number, remainder = divmod(number - 1, 26)
            result = chr(65 + remainder) + result
        return result

    def _visible_columns(self) -> tuple[int, int]:
        x0 = max(0.0, float(self.grid_canvas.canvasx(0)))
        x1 = max(x0 + 1, x0 + float(self.grid_canvas.winfo_width()))
        first = max(0, min(self.column_count - 1, bisect_right(self._x_starts, x0) - 1))
        last = max(first, min(self.column_count - 1, bisect_left(self._x_starts, x1)))
        return first, last

    def _visible_rows(self) -> tuple[int, int]:
        y0 = max(0.0, float(self.grid_canvas.canvasy(0)))
        y1 = max(y0 + 1, y0 + float(self.grid_canvas.winfo_height()))
        first = max(0, min(self.row_count - 1, int(y0 // self.ROW_HEIGHT)))
        last = max(first, min(self.row_count - 1, int((y1 - 1) // self.ROW_HEIGHT)))
        return first, last

    def _redraw(self) -> None:
        if not self.winfo_exists():
            return
        try:
            first_col, last_col = self._visible_columns()
            first_row, last_row = self._visible_rows()
        except tk.TclError:
            return
        self._last_drawn = (first_row, last_row, first_col, last_col)
        self.grid_canvas.delete("grid")
        self.grid_canvas.delete("selection")

        for row in range(first_row, last_row + 1):
            y1 = row * self.ROW_HEIGHT
            y2 = y1 + self.ROW_HEIGHT
            for col in range(first_col, last_col + 1):
                x1 = self._x_starts[col]
                x2 = self._x_starts[col + 1]
                value, readonly = self._cell_display(row, col)
                fill = self._colors["readonly"] if readonly else (
                    self._colors["alt_row"] if row % 2 else self._colors["canvas"]
                )
                self.grid_canvas.create_rectangle(
                    x1,
                    y1,
                    x2,
                    y2,
                    fill=fill,
                    outline=self._colors["line"],
                    tags=("grid",),
                )
                if value != "":
                    self.grid_canvas.create_text(
                        x1 + 5,
                        y1 + self.ROW_HEIGHT // 2,
                        text=self._display_text(value, x2 - x1 - 9),
                        anchor="w",
                        fill=self._colors["muted"] if readonly else self._colors["text"],
                        font=self._font,
                        tags=("grid",),
                    )

        self._draw_selection()
        self._draw_headers()
        self._position_editor()

    @staticmethod
    def _display_text(value: str, width: int) -> str:
        # Canvas text has no native ellipsis option.  Keep long messages from
        # painting over neighbouring cells while leaving normal Unicode intact.
        text = str(value).replace("\r", " ").replace("\n", " ↵ ")
        if len(text) <= 180:
            return text
        return text[:177] + "..."

    def _draw_headers(self) -> None:
        self.column_header.delete("all")
        self.row_header.delete("all")
        try:
            first_col, last_col = self._visible_columns()
            first_row, last_row = self._visible_rows()
        except tk.TclError:
            return

        selected_r0, selected_r1, selected_c0, selected_c1 = self._selection_bounds()
        for col in range(first_col, last_col + 1):
            x1 = self._x_starts[col]
            x2 = self._x_starts[col + 1]
            active = selected_c0 <= col <= selected_c1
            self.column_header.create_rectangle(
                x1,
                0,
                x2,
                self.HEADER_HEIGHT,
                fill=self._colors["header_active"] if active else self._colors["header"],
                outline=self._colors["line"],
            )
            self.column_header.create_text(
                (x1 + x2) / 2,
                self.HEADER_HEIGHT / 2,
                text=self._column_label(col),
                fill=self._colors["selection"] if active else self._colors["muted"],
                font=self._font_with(weight="bold" if active else None),
            )

        for row in range(first_row, last_row + 1):
            y1 = row * self.ROW_HEIGHT
            y2 = y1 + self.ROW_HEIGHT
            active = selected_r0 <= row <= selected_r1
            self.row_header.create_rectangle(
                0,
                y1,
                self.ROW_HEADER_WIDTH,
                y2,
                fill=self._colors["header_active"] if active else self._colors["header"],
                outline=self._colors["line"],
            )
            self.row_header.create_text(
                self.ROW_HEADER_WIDTH - 6,
                (y1 + y2) / 2,
                text=str(row + 1),
                anchor="e",
                fill=self._colors["selection"] if active else self._colors["muted"],
                font=self._font_with(weight="bold" if active else None),
            )

    def _draw_selection(self) -> None:
        r0, r1, c0, c1 = self._selection_bounds()
        x1 = self._x_starts[c0]
        x2 = self._x_starts[c1 + 1]
        y1 = r0 * self.ROW_HEIGHT
        y2 = (r1 + 1) * self.ROW_HEIGHT
        self.grid_canvas.create_rectangle(
            x1 + 1,
            y1 + 1,
            x2 - 1,
            y2 - 1,
            outline=self._colors["selection"],
            width=2,
            tags=("selection",),
        )
        # Excel's little fill handle is deliberately small but visible at the
        # lower right of the selected range.
        handle = 5
        self.grid_canvas.create_rectangle(
            x2 - handle,
            y2 - handle,
            x2,
            y2,
            fill=self._colors["handle"],
            outline=self._colors["handle"],
            tags=("selection",),
        )

    # ------------------------------------------------------------------
    # Cell and message data
    # ------------------------------------------------------------------
    def _validate_cell(self, row: int, col: int) -> tuple[int, int]:
        try:
            row = int(row)
            col = int(col)
        except (TypeError, ValueError) as exc:
            raise ValueError("row and col must be integers") from exc
        if not 0 <= row < self.row_count or not 0 <= col < self.column_count:
            raise IndexError(f"cell ({row}, {col}) is outside the worksheet")
        return row, col

    def _is_message_readonly(self, row: int, col: int) -> bool:
        return row in self._message_rows and col < 4

    def _cell_display(self, row: int, col: int) -> tuple[str, bool]:
        message = self._message_rows.get(row)
        if message is not None and col < 4:
            return message[col], True
        return self._cells.get((row, col), ""), False

    def get_cell(self, row: int, col: int) -> str:
        """Return the displayed value at zero-based ``row``, ``col``."""
        row, col = self._validate_cell(row, col)
        return self._cell_display(row, col)[0]

    def set_cell(self, row: int, col: int, value: object) -> bool:
        """Set a local value and redraw it.

        Returns ``False`` for read-only message columns.  Programmatic writes
        do not call ``on_commit``; use a real edit or paste when the host wants
        the commit callback.
        """
        row, col = self._validate_cell(row, col)
        if self._is_message_readonly(row, col):
            return False
        self._store_local(row, col, value)
        self._redraw()
        return True

    def _store_local(self, row: int, col: int, value: object) -> None:
        text = "" if value is None else str(value)
        if text == "":
            self._cells.pop((row, col), None)
        else:
            self._cells[(row, col)] = text

    def get_selected_value(self) -> str:
        return self.get_cell(self.selected_row, self.selected_col)

    def set_selected_value(self, value: object) -> bool:
        if self._is_message_readonly(self.selected_row, self.selected_col):
            return False
        if self._editor is not None:
            self._editor.delete(0, tk.END)
            self._editor.insert(0, "" if value is None else str(value))
            return True
        return self.set_cell(self.selected_row, self.selected_col, value)

    def select_cell(self, row: int, col: int, *, extend: bool = False) -> str:
        """Select a zero-based cell and return its one-based Excel address."""
        row, col = self._validate_cell(row, col)
        if self._editor is not None:
            self.commit_edit()
        self._set_selection(row, col, extend=extend)
        return self.selected_address

    def _set_selection(self, row: int, col: int, *, extend: bool = False) -> None:
        if not extend:
            self._anchor = (row, col)
        self.selected_row, self.selected_col = row, col
        self._notify_selection()
        self._ensure_visible(row, col)
        self._redraw()

    @property
    def selected_address(self) -> str:
        return self._address(self.selected_row, self.selected_col)

    @classmethod
    def _address(cls, row: int, col: int) -> str:
        return f"{cls._column_label(col)}{int(row) + 1}"

    def _notify_selection(self) -> None:
        if callable(self.on_selection):
            self.on_selection(self.selected_address, self.get_selected_value())

    def _selection_bounds(self) -> tuple[int, int, int, int]:
        ar, ac = self._anchor
        return (
            min(ar, self.selected_row),
            max(ar, self.selected_row),
            min(ac, self.selected_col),
            max(ac, self.selected_col),
        )

    def _ensure_visible(self, row: int, col: int) -> None:
        try:
            view_w = max(1, self.grid_canvas.winfo_width())
            view_h = max(1, self.grid_canvas.winfo_height())
            x1, x2 = self._x_starts[col], self._x_starts[col + 1]
            y1, y2 = row * self.ROW_HEIGHT, (row + 1) * self.ROW_HEIGHT
            left, right = self.grid_canvas.canvasx(0), self.grid_canvas.canvasx(view_w)
            top, bottom = self.grid_canvas.canvasy(0), self.grid_canvas.canvasy(view_h)
            if x1 < left:
                self.grid_canvas.xview_moveto(x1 / max(1, self._x_starts[-1]))
            elif x2 > right:
                self.grid_canvas.xview_moveto(
                    max(0.0, (x2 - view_w) / max(1, self._x_starts[-1] - view_w))
                )
            if y1 < top:
                self.grid_canvas.yview_moveto(y1 / max(1, self.row_count * self.ROW_HEIGHT))
            elif y2 > bottom:
                self.grid_canvas.yview_moveto(
                    max(0.0, (y2 - view_h) / max(1, self.row_count * self.ROW_HEIGHT - view_h))
                )
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Messages and snapshots
    # ------------------------------------------------------------------
    @staticmethod
    def _message_field(record: Mapping[str, Any], *names: str) -> str:
        for name in names:
            if name in record and record[name] is not None:
                return str(record[name])
        return ""

    def set_messages(self, messages: Iterable[Mapping[str, Any]]) -> None:
        """Show messages as read-only A:D rows while keeping local drafts."""
        self._message_records = [dict(item) for item in messages if isinstance(item, Mapping)]
        self._message_rows = {}
        for row, record in enumerate(self._message_records):
            self._message_rows[row] = (
                self._message_field(record, "time", "timestamp", "created_at", "createdAt", "date", "ts"),
                self._message_field(record, "sender", "from", "user", "username", "name", "nick", "author"),
                self._message_field(record, "content", "text", "message", "body"),
                self._message_field(record, "status", "state", "read_state", "read"),
            )
        if self._editor is not None and self._is_message_readonly(*self._editing_cell):
            self.cancel_edit()
        self._redraw()

    def export_cells(self) -> dict[str, str]:
        """Return local draft cells as an address keyed snapshot."""
        return {self._address(row, col): value for (row, col), value in self._cells.items()}

    def import_cells(self, snapshot: Mapping[object, object], *, clear: bool = False) -> None:
        """Restore a snapshot made by :meth:`export_cells`."""
        if clear:
            self._cells.clear()
        for key, value in snapshot.items():
            row_col = self._parse_address(key)
            if row_col is None:
                continue
            row, col = row_col
            if not self._is_message_readonly(row, col):
                self._store_local(row, col, value)
        self._redraw()

    def _parse_address(self, address: object) -> tuple[int, int] | None:
        if isinstance(address, (tuple, list)) and len(address) == 2:
            try:
                return self._validate_cell(int(address[0]), int(address[1]))
            except (TypeError, ValueError, IndexError):
                return None
        match = self._ADDRESS_RE.match(str(address).strip())
        if match is None:
            return None
        letters, row_text = match.groups()
        col = 0
        for letter in letters.upper():
            col = col * 26 + ord(letter) - 64
        try:
            return self._validate_cell(int(row_text) - 1, col - 1)
        except (TypeError, ValueError, IndexError):
            return None

    # ------------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------------
    def edit_selected(self, initial: str | None = None) -> bool:
        """Open the native Entry editor over the selected cell."""
        if self._editor is not None:
            self._editor.focus_set()
            return True
        row, col = self.selected_row, self.selected_col
        if self._is_message_readonly(row, col):
            try:
                self.bell()
            except tk.TclError:
                pass
            return False

        value = self.get_cell(row, col) if initial is None else str(initial)
        self._editing_cell = (row, col)
        self._editor = tk.Entry(
            self.grid_canvas,
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightcolor=self._colors["selection"],
            bg=self._colors["editor_bg"],
            fg=self._colors["text"],
            insertbackground=self._colors["text"],
            font=self._font,
        )
        # A StringVar trace observes regular key input, paste, and IME commits
        # equally. It keeps the optional formula-bar hook live for every edit
        # route, including native input methods.
        self._editor_var = tk.StringVar(self, value=value)
        self._editor_trace = self._editor_var.trace_add("write", self._on_editor_var_write)
        self._editor.configure(textvariable=self._editor_var)
        self._editor_item = self.grid_canvas.create_window(
            self._x_starts[col] + 1,
            row * self.ROW_HEIGHT + 1,
            anchor="nw",
            width=max(2, self._column_widths[col] - 2),
            height=max(2, self.ROW_HEIGHT - 2),
            window=self._editor,
            tags=("editor",),
        )
        self._editor.bind("<Return>", self._on_entry_return, add="+")
        self._editor.bind("<KP_Enter>", self._on_entry_return, add="+")
        self._editor.bind("<Tab>", self._on_entry_tab, add="+")
        self._editor.bind("<Escape>", self._on_entry_escape, add="+")
        self._editor.bind("<Control-Return>", self._on_entry_send, add="+")
        self._editor.bind("<Control-KP_Enter>", self._on_entry_send, add="+")
        self._editor.bind("<Control-KeyPress-Return>", self._on_entry_send, add="+")
        self._editor.bind("<Control-KeyPress-KP_Enter>", self._on_entry_send, add="+")
        # Some Tk builds expose Tab/Return as a class binding before the
        # shorthand sequence above.  The generic key handler makes those
        # commands deterministic while leaving ordinary text input untouched.
        self._editor.bind("<KeyPress>", self._on_entry_key_press, add="+")
        self._editor.bind("<KeyRelease>", self._on_entry_key_release, add="+")
        self._editor.focus_set()
        if initial is None:
            self._editor.select_range(0, tk.END)
        self.grid_canvas.tag_raise("editor")
        return True

    def _position_editor(self) -> None:
        if self._editor_item is None or self._editing_cell is None:
            return
        row, col = self._editing_cell
        try:
            self.grid_canvas.coords(self._editor_item, self._x_starts[col] + 1, row * self.ROW_HEIGHT + 1)
            self.grid_canvas.itemconfigure(
                self._editor_item,
                width=max(2, self._column_widths[col] - 2),
                height=max(2, self.ROW_HEIGHT - 2),
            )
            self.grid_canvas.tag_raise("editor")
        except tk.TclError:
            pass

    def commit_edit(self, move: str | None = None) -> bool:
        """Commit the active Entry and optionally move ``down`` or ``right``."""
        if self._editor is None or self._editing_cell is None:
            return False
        row, col = self._editing_cell
        value = self._editor.get()
        self._close_editor()
        self._store_local(row, col, value)
        if callable(self.on_commit):
            self.on_commit(row, col, value)
        if move == "down":
            self._move_selection(1, 0)
        elif move == "right":
            self._move_selection(0, 1)
        else:
            self._redraw()
            self.grid_canvas.focus_set()
        return True

    def cancel_edit(self) -> bool:
        if self._editor is None:
            return False
        self._close_editor()
        self._redraw()
        self.grid_canvas.focus_set()
        return True

    def _close_editor(self) -> None:
        editor = self._editor
        editor_var = self._editor_var
        editor_trace = self._editor_trace
        item = self._editor_item
        self._editor = None
        self._editor_var = None
        self._editor_trace = None
        self._editor_item = None
        self._editing_cell = None
        if editor_var is not None and editor_trace:
            try:
                editor_var.trace_remove("write", editor_trace)
            except tk.TclError:
                pass
        if item is not None:
            try:
                self.grid_canvas.delete(item)
            except tk.TclError:
                pass
        if editor is not None:
            try:
                editor.destroy()
            except tk.TclError:
                pass

    def _move_selection(self, row_delta: int, col_delta: int) -> None:
        row = max(0, min(self.row_count - 1, self.selected_row + row_delta))
        col = max(0, min(self.column_count - 1, self.selected_col + col_delta))
        self._set_selection(row, col)
        self.grid_canvas.focus_set()

    # ------------------------------------------------------------------
    # Keyboard, mouse, clipboard, and scrolling
    # ------------------------------------------------------------------
    def _on_entry_return(self, _event: tk.Event) -> str:
        self.commit_edit(move="down")
        return "break"

    def _on_entry_tab(self, _event: tk.Event) -> str:
        self.commit_edit(move="right")
        return "break"

    def _on_entry_escape(self, _event: tk.Event) -> str:
        self.cancel_edit()
        return "break"

    def _on_entry_key_press(self, event: tk.Event) -> str | None:
        key = str(getattr(event, "keysym", ""))
        state = int(getattr(event, "state", 0) or 0)
        if key in {"Return", "KP_Enter"}:
            if state & 0x4:
                return self._on_entry_send(event)
            return self._on_entry_return(event)
        if key == "Tab":
            return self._on_entry_tab(event)
        if key == "Escape":
            return self._on_entry_escape(event)
        return None

    def _on_entry_send(self, _event: tk.Event) -> str:
        if self._editor is None:
            return "break"
        value = self._editor.get()
        self.commit_edit()
        if callable(self.on_send):
            self.on_send(value)
        return "break"

    def _on_entry_key_release(self, _event: tk.Event) -> None:
        if self._editor is not None and callable(self.on_edit):
            self.on_edit(self._editor.get())

    def _on_editor_var_write(self, *_args: object) -> None:
        if self._editor is not None and callable(self.on_edit):
            self.on_edit(self._editor.get())

    def _on_send_key(self, _event: tk.Event) -> str:
        if self._editor is not None:
            return self._on_entry_send(_event)
        if callable(self.on_send):
            self.on_send(self.get_selected_value())
        return "break"

    def _on_key_press(self, event: tk.Event) -> str | None:
        if self._editor is not None:
            return None
        key = str(getattr(event, "keysym", ""))
        if key in {"Left", "KP_Left"}:
            self._move_selection(0, -1)
            return "break"
        if key in {"Right", "KP_Right"}:
            self._move_selection(0, 1)
            return "break"
        if key in {"Up", "KP_Up"}:
            self._move_selection(-1, 0)
            return "break"
        if key in {"Down", "KP_Down"}:
            self._move_selection(1, 0)
            return "break"
        if key in {"F2"}:
            self.edit_selected()
            return "break"
        if key in {"Return", "KP_Enter"}:
            self._move_selection(1, 0)
            return "break"
        if key == "Tab":
            self._move_selection(0, 1)
            return "break"
        char = str(getattr(event, "char", "") or "")
        state = int(getattr(event, "state", 0) or 0)
        # 0x4 is Control and 0x20000 is Alt on the Windows Tk builds used by
        # the app.  Printable Unicode is passed straight into a real Entry.
        if char and char.isprintable() and not (state & 0x4) and not (state & 0x20000):
            self.edit_selected(initial=char)
            return "break"
        return None

    def _cell_at(self, x: float, y: float) -> tuple[int, int]:
        x = max(0.0, float(x))
        y = max(0.0, float(y))
        col = max(0, min(self.column_count - 1, bisect_right(self._x_starts, x) - 1))
        row = max(0, min(self.row_count - 1, int(y // self.ROW_HEIGHT)))
        return row, col

    def _on_button_press(self, event: tk.Event) -> str:
        if self._editor is not None:
            self.commit_edit()
        row, col = self._cell_at(self.grid_canvas.canvasx(event.x), self.grid_canvas.canvasy(event.y))
        extend = bool(int(getattr(event, "state", 0) or 0) & 0x0001)
        if not extend:
            self._anchor = (row, col)
        self._dragging = True
        self._set_selection(row, col, extend=extend)
        self.grid_canvas.focus_set()
        return "break"

    def _on_button_motion(self, event: tk.Event) -> str:
        if not self._dragging:
            return "break"
        row, col = self._cell_at(self.grid_canvas.canvasx(event.x), self.grid_canvas.canvasy(event.y))
        self._set_selection(row, col, extend=True)
        return "break"

    def _on_button_release(self, _event: tk.Event) -> str:
        self._dragging = False
        return "break"

    def _on_double_click(self, event: tk.Event) -> str:
        row, col = self._cell_at(self.grid_canvas.canvasx(event.x), self.grid_canvas.canvasy(event.y))
        self._anchor = (row, col)
        self._set_selection(row, col)
        self.edit_selected()
        return "break"

    def _selection_text(self) -> str:
        r0, r1, c0, c1 = self._selection_bounds()
        return "\n".join(
            "\t".join(self.get_cell(row, col) for col in range(c0, c1 + 1))
            for row in range(r0, r1 + 1)
        )

    def copy_selection(self) -> str:
        """Copy the selected range to the system clipboard and return TSV."""
        text = self._selection_text()
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except tk.TclError:
            pass
        return text

    def _on_copy(self, _event: tk.Event) -> str:
        self.copy_selection()
        return "break"

    def paste_text(self, text: str) -> tuple[int, int]:
        """Paste TSV text at the active cell and return its dimensions."""
        if self._editor is not None:
            return (0, 0)
        raw = str(text).replace("\r\n", "\n").replace("\r", "\n")
        rows = raw.split("\n")
        if rows and rows[-1] == "":
            rows.pop()
        if not rows:
            return (0, 0)
        matrix = [row.split("\t") for row in rows]
        start_row, start_col = self.selected_row, self.selected_col
        last_row, last_col = start_row, start_col
        for row_offset, values in enumerate(matrix):
            row = start_row + row_offset
            if row >= self.row_count:
                break
            for col_offset, value in enumerate(values):
                col = start_col + col_offset
                if col >= self.column_count:
                    break
                if self._is_message_readonly(row, col):
                    continue
                self._store_local(row, col, value)
                if callable(self.on_commit):
                    self.on_commit(row, col, value)
                last_row, last_col = row, col
        self._anchor = (start_row, start_col)
        self.selected_row, self.selected_col = last_row, last_col
        self._notify_selection()
        self._ensure_visible(last_row, last_col)
        self._redraw()
        return (len(matrix), max((len(values) for values in matrix), default=0))

    def _on_paste(self, _event: tk.Event) -> str:
        try:
            text = self.clipboard_get()
        except tk.TclError:
            text = ""
        if text:
            self.paste_text(text)
        return "break"

    def paste_selection(self) -> tuple[int, int]:
        """Paste the system clipboard TSV at the active cell."""
        try:
            text = self.clipboard_get()
        except tk.TclError:
            return (0, 0)
        return self.paste_text(text) if text else (0, 0)

    def clear_selection(self) -> int:
        """Clear editable cells in the current range and return its count."""
        if self._editor is not None:
            self.commit_edit()
        r0, r1, c0, c1 = self._selection_bounds()
        changed = 0
        for row in range(r0, r1 + 1):
            for col in range(c0, c1 + 1):
                if self._is_message_readonly(row, col):
                    continue
                if (row, col) in self._cells:
                    self._cells.pop((row, col), None)
                    changed += 1
                    if callable(self.on_commit):
                        self.on_commit(row, col, "")
        self._redraw()
        return changed

    def cut_selection(self) -> str:
        """Copy the current range, then clear its editable local cells."""
        r0, _r1, c0, _c1 = self._selection_bounds()
        text = self.copy_selection()
        self.clear_selection()
        # Keep the active paste anchor at the upper-left of the cut range,
        # matching the normal spreadsheet cut/paste workflow.
        self._set_selection(r0, c0)
        return text

    def _on_mousewheel(self, event: tk.Event) -> str:
        num = getattr(event, "num", None)
        delta = int(getattr(event, "delta", 0) or 0)
        if num == 4:
            units = -3
        elif num == 5:
            units = 3
        else:
            units = -int(delta / 120) if delta else 0
            if units == 0 and delta:
                units = -1 if delta > 0 else 1
        state = int(getattr(event, "state", 0) or 0)
        if state & 0x0001:  # Shift+wheel = horizontal scroll, as in Excel.
            self.grid_canvas.xview_scroll(units, "units")
        else:
            self.grid_canvas.yview_scroll(units, "units")
        return "break"

    @property
    def selected_cell(self) -> tuple[int, int]:
        """Current zero-based ``(row, col)`` tuple for host integrations."""
        return self.selected_row, self.selected_col

    @property
    def selection(self) -> tuple[int, int]:
        """Alias for :attr:`selected_cell` used by the Excel chrome."""
        return self.selected_cell

    @property
    def editor(self) -> tk.Entry | None:
        """The active native Entry, or ``None`` when the sheet is not editing."""
        return self._editor

    def _xview(self, *args: Any) -> None:
        self.grid_canvas.xview(*args)

    def _yview(self, *args: Any) -> None:
        self.grid_canvas.yview(*args)

    def _xscroll_changed(self, *args: str) -> None:
        self.hscroll.set(*args)
        try:
            self.column_header.xview_moveto(float(args[0]))
        except (IndexError, TypeError, ValueError, tk.TclError):
            pass
        self._redraw()

    def _yscroll_changed(self, *args: str) -> None:
        self.vscroll.set(*args)
        try:
            self.row_header.yview_moveto(float(args[0]))
        except (IndexError, TypeError, ValueError, tk.TclError):
            pass
        self._redraw()

    # ------------------------------------------------------------------
    # Theme integration
    # ------------------------------------------------------------------
    def set_font(self, font: object) -> None:
        """Change the display font for the worksheet and active Entry."""
        self._font = self._normalise_font(font)
        self.ROW_HEIGHT = max(23, int(self._font[1] * 1.8))
        total_height = self.row_count * self.ROW_HEIGHT
        self.grid_canvas.configure(scrollregion=(0, 0, self._x_starts[-1], total_height))
        self.row_header.configure(scrollregion=(0, 0, self.ROW_HEADER_WIDTH, total_height))
        if self._editor is not None:
            self._editor.configure(font=self._font)
            self._position_editor()
        self._ensure_visible(*self.selected_cell)
        self._redraw()

    def set_theme(self, skin: Mapping[str, Any] | None = None) -> None:
        """Apply optional skin tokens while retaining worksheet data."""
        skin = skin or {}
        mapping = {
            # The short palette names are used by ExcelChrome.  The longer
            # skin-token names keep this widget compatible with theme.py.
            "frame": skin.get("bg") or skin.get("window_bg"),
            "canvas": skin.get("bg") or skin.get("panel_bg"),
            "alt_row": skin.get("input_bg") or skin.get("bg"),
            "header": skin.get("header_bg") or skin.get("list_bg"),
            "line": skin.get("grid") or skin.get("glass_border"),
            "selection": skin.get("accent"),
            "text": skin.get("fg") or skin.get("text"),
        }
        for key, value in mapping.items():
            if value:
                self._colors[key] = str(value)
        self.configure(bg=self._colors["frame"])
        self.grid_canvas.configure(bg=self._colors["canvas"])
        self.column_header.configure(bg=self._colors["header"])
        self.row_header.configure(bg=self._colors["header"])
        self.corner.configure(bg=self._colors["header"])
        self._draw_corner()
        self._redraw()


# Friendly aliases for integration code that uses a more descriptive name.
EditableWorksheet = ExcelSheet
ExcelWorksheet = ExcelSheet

__all__ = ["ExcelSheet", "EditableWorksheet", "ExcelWorksheet"]
