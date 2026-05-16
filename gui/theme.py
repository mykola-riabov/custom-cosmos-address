"""Theme palettes and ttk styling for the GUI."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TypedDict


class ThemeColors(TypedDict):
    bg: str
    surface: str
    surface2: str
    fg: str
    fg_dim: str
    accent: str
    accent_hover: str
    success: str
    danger: str
    warning: str
    border: str
    input_bg: str
    log_bg: str
    log_fg: str
    accent_btn_fg: str


THEMES: dict[str, ThemeColors] = {
    "Mocha (dark)": {
        "bg": "#1e1e2e",
        "surface": "#313244",
        "surface2": "#45475a",
        "fg": "#cdd6f4",
        "fg_dim": "#a6adc8",
        "accent": "#89b4fa",
        "accent_hover": "#74c7ec",
        "success": "#a6e3a1",
        "danger": "#f38ba8",
        "warning": "#fab387",
        "border": "#585b70",
        "input_bg": "#313244",
        "log_bg": "#181825",
        "log_fg": "#cdd6f4",
        "accent_btn_fg": "#1e1e2e",
    },
    "Latte (light)": {
        "bg": "#eff1f5",
        "surface": "#e6e9ef",
        "surface2": "#dce0e8",
        "fg": "#4c4f69",
        "fg_dim": "#6c6f85",
        "accent": "#1e66f5",
        "accent_hover": "#3584e4",
        "success": "#40a02b",
        "danger": "#d20f39",
        "warning": "#fe640b",
        "border": "#bcc0cc",
        "input_bg": "#ffffff",
        "log_bg": "#ffffff",
        "log_fg": "#4c4f69",
        "accent_btn_fg": "#ffffff",
    },
    "Nord (dark)": {
        "bg": "#2e3440",
        "surface": "#3b4252",
        "surface2": "#434c5e",
        "fg": "#eceff4",
        "fg_dim": "#d8dee9",
        "accent": "#88c0d0",
        "accent_hover": "#8fbcbb",
        "success": "#a3be8c",
        "danger": "#bf616a",
        "warning": "#ebcb8b",
        "border": "#4c566a",
        "input_bg": "#3b4252",
        "log_bg": "#242933",
        "log_fg": "#eceff4",
        "accent_btn_fg": "#2e3440",
    },
    "Dracula (dark)": {
        "bg": "#282a36",
        "surface": "#383a59",
        "surface2": "#44475a",
        "fg": "#f8f8f2",
        "fg_dim": "#bd93f9",
        "accent": "#bd93f9",
        "accent_hover": "#ff79c6",
        "success": "#50fa7b",
        "danger": "#ff5555",
        "warning": "#ffb86c",
        "border": "#6272a4",
        "input_bg": "#383a59",
        "log_bg": "#1e1f29",
        "log_fg": "#f8f8f2",
        "accent_btn_fg": "#282a36",
    },
    "Forest (dark)": {
        "bg": "#1b2421",
        "surface": "#243029",
        "surface2": "#2f3d36",
        "fg": "#e0ece4",
        "fg_dim": "#9bb0a0",
        "accent": "#7fd99a",
        "accent_hover": "#9ae6b0",
        "success": "#7fd99a",
        "danger": "#f07178",
        "warning": "#e6c77a",
        "border": "#3d5248",
        "input_bg": "#243029",
        "log_bg": "#141a18",
        "log_fg": "#e0ece4",
        "accent_btn_fg": "#1b2421",
    },
    "Solarized (dark)": {
        "bg": "#002b36",
        "surface": "#073642",
        "surface2": "#0a4452",
        "fg": "#fdf6e3",
        "fg_dim": "#93a1a1",
        "accent": "#2aa198",
        "accent_hover": "#268bd2",
        "success": "#859900",
        "danger": "#dc322f",
        "warning": "#cb4b16",
        "border": "#586e75",
        "input_bg": "#073642",
        "log_bg": "#001e26",
        "log_fg": "#eee8d5",
        "accent_btn_fg": "#002b36",
    },
}

DEFAULT_THEME = "Mocha (dark)"


def theme_names() -> list[str]:
    return list(THEMES.keys())


def apply_theme(root: tk.Tk, name: str) -> ThemeColors:
    if name not in THEMES:
        name = DEFAULT_THEME
    c = THEMES[name]
    root.configure(bg=c["bg"])

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(
        ".",
        background=c["bg"],
        foreground=c["fg"],
        fieldbackground=c["input_bg"],
        bordercolor=c["border"],
        troughcolor=c["surface2"],
    )
    style.configure("TFrame", background=c["bg"])
    style.configure("Card.TFrame", background=c["surface"])
    style.configure("TLabelframe", background=c["bg"], foreground=c["fg"])
    style.configure("TLabelframe.Label", background=c["bg"], foreground=c["accent"])
    style.configure("TLabel", background=c["bg"], foreground=c["fg"])
    style.configure("Dim.TLabel", background=c["bg"], foreground=c["fg_dim"])
    style.configure("Warn.TLabel", background=c["bg"], foreground=c["warning"])
    style.configure(
        "TEntry",
        fieldbackground=c["input_bg"],
        foreground=c["fg"],
        insertcolor=c["fg"],
    )
    style.configure(
        "TSpinbox",
        fieldbackground=c["input_bg"],
        foreground=c["fg"],
        arrowcolor=c["fg"],
    )
    style.configure(
        "TCombobox",
        fieldbackground=c["input_bg"],
        foreground=c["fg"],
        arrowcolor=c["fg"],
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", c["input_bg"])],
        foreground=[("readonly", c["fg"])],
    )
    style.configure("TCheckbutton", background=c["bg"], foreground=c["fg"])
    style.map("TCheckbutton", background=[("active", c["bg"])])
    style.configure(
        "TButton",
        background=c["surface2"],
        foreground=c["fg"],
        padding=(12, 8),
        borderwidth=0,
    )
    style.map(
        "TButton",
        background=[("active", c["surface"]), ("disabled", c["surface"])],
        foreground=[("disabled", c["fg_dim"])],
    )
    style.configure(
        "Accent.TButton",
        background=c["accent"],
        foreground=c["accent_btn_fg"],
        font=("", 11, "bold"),
        padding=(24, 12),
    )
    style.map(
        "Accent.TButton",
        background=[("active", c["accent_hover"]), ("disabled", c["surface2"])],
        foreground=[("disabled", c["fg_dim"])],
    )
    style.configure(
        "Danger.TButton",
        background=c["surface2"],
        foreground=c["danger"],
        padding=(16, 10),
    )
    style.map("Danger.TButton", background=[("active", c["surface"])])
    style.configure(
        "Horizontal.TProgressbar",
        background=c["accent"],
        troughcolor=c["surface2"],
        borderwidth=0,
        thickness=8,
    )
    style.configure("Vertical.TScrollbar", background=c["surface2"], troughcolor=c["bg"])

    return c
