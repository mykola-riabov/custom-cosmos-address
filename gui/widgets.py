"""Reusable tkinter widgets."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ScrollableFrame(ttk.Frame):
    """Vertically scrollable container; place child widgets on `.inner`."""

    def __init__(self, parent: tk.Misc, *, bg: str = "#1e1e2e", **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self._bg = bg
        self._canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, bg=bg)
        self._scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._canvas.yview)
        # tk.Frame (not ttk): ttk children inside Canvas on Linux ignore theme updates.
        self.inner = tk.Frame(self._canvas, bg=bg, bd=0, highlightthickness=0)

        self._window_id = self._canvas.create_window((0, 0), window=self.inner, anchor=tk.NW)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._bind_mousewheel(self._canvas)
        self._bind_mousewheel(self.inner)

    def _on_inner_configure(self, _event: tk.Event | None = None) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self._canvas.itemconfigure(self._window_id, width=event.width)

    def _bind_mousewheel(self, widget: tk.Misc) -> None:
        def on_enter(_e: tk.Event) -> None:
            widget.bind_all("<MouseWheel>", self._on_mousewheel)
            widget.bind_all("<Button-4>", self._on_mousewheel_linux)
            widget.bind_all("<Button-5>", self._on_mousewheel_linux)

        def on_leave(_e: tk.Event) -> None:
            widget.unbind_all("<MouseWheel>")
            widget.unbind_all("<Button-4>")
            widget.unbind_all("<Button-5>")

        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    def _on_mousewheel(self, event: tk.Event) -> None:
        if event.delta:
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_mousewheel_linux(self, event: tk.Event) -> None:
        if event.num == 4:
            self._canvas.yview_scroll(-3, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(3, "units")

    def set_colors(self, bg: str) -> None:
        self._bg = bg
        self._canvas.configure(bg=bg)
        self.inner.configure(bg=bg)

    def scroll_to_top(self) -> None:
        self._canvas.yview_moveto(0)
