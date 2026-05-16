#!/usr/bin/env python3
"""Tkinter GUI for Cosmos vanity address generation."""

from __future__ import annotations

import multiprocessing as mp
import queue
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from cosmos_address import ALLOWED_STRENGTHS, VERSION, estimate_difficulty, validate_pattern
from gui.theme import DEFAULT_THEME, apply_theme, refresh_embedded_ttk, theme_names
from gui.widgets import ScrollableFrame
from gui.worker import SearchConfig, start_search_process


class VanityGuiApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Custom Cosmos Address — v{VERSION}")
        self.minsize(640, 480)
        self.geometry("900x700")

        self._theme_var = tk.StringVar(value=DEFAULT_THEME)
        self._colors = apply_theme(self, self._theme_var.get())

        self._proc: mp.Process | None = None
        self._msg_queue: mp.Queue | None = None
        self._stop_event: mp.Event | None = None
        self._poll_after_id: str | None = None

        self._build_menu()
        self._build_ui()
        self._apply_theme(self._theme_var.get())
        self._update_difficulty_hint()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)

        theme_menu = tk.Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label="Theme", menu=theme_menu)

        for name in theme_names():
            theme_menu.add_radiobutton(
                label=name,
                variable=self._theme_var,
                value=name,
                command=self._on_theme_changed,
            )

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(
            label="About",
            command=lambda: messagebox.showinfo(
                "About",
                f"Custom Cosmos Address v{VERSION}\n\n"
                "Vanity address generator for Cosmos SDK chains.\n"
                "Use View → Theme to change appearance.",
            ),
        )

    def _on_theme_changed(self) -> None:
        self._apply_theme(self._theme_var.get())

    def _apply_theme(self, name: str) -> None:
        self._colors = apply_theme(self, name)
        c = self._colors
        self._scroll_frame.set_colors(c["bg"])
        refresh_embedded_ttk(self._scroll_frame.inner)
        self._style_menus(c)
        self.log.configure(
            bg=c["log_bg"],
            fg=c["log_fg"],
            insertbackground=c["fg"],
            selectbackground=c["accent"],
            selectforeground=c["accent_btn_fg"],
        )
        self.update_idletasks()

    def _style_menus(self, c: dict) -> None:
        """Best-effort menu colors (tk.Menu is separate from ttk themes)."""
        try:
            menu_cfg = {
                "bg": c["surface"],
                "fg": c["fg"],
                "activebackground": c["accent"],
                "activeforeground": c["accent_btn_fg"],
                "relief": tk.FLAT,
                "bd": 0,
            }

            def walk(menu: tk.Menu) -> None:
                menu.configure(**menu_cfg)
                end = menu.index(tk.END)
                if end is None:
                    return
                for i in range(end + 1):
                    try:
                        if menu.type(i) == "cascade":
                            walk(menu.nametowidget(menu.entrycget(i, "menu")))
                    except tk.TclError:
                        pass

            walk(self.nametowidget(self["menu"]))
        except (tk.TclError, KeyError):
            pass

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}
        outer = ttk.Frame(self, padding=8)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)
        outer.rowconfigure(1, weight=2)

        # --- Bottom: fixed action bar ---
        action_wrap = ttk.Frame(outer)
        action_wrap.grid(row=2, column=0, sticky=tk.EW, pady=(8, 0))
        ttk.Separator(action_wrap, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 8))

        btn_row = ttk.Frame(action_wrap)
        btn_row.pack(fill=tk.X)

        self.start_btn = ttk.Button(
            btn_row, text="▶  START", style="Accent.TButton", command=self._start
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_btn = ttk.Button(
            btn_row, text="■  STOP", style="Danger.TButton", command=self._stop, state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT)

        ttk.Label(
            btn_row,
            text="⚠ Output may contain private keys",
            style="Warn.TLabel",
        ).pack(side=tk.RIGHT)

        # --- Middle: log ---
        log_frame = ttk.LabelFrame(outer, text="Log & results", padding=8)
        log_frame.grid(row=1, column=0, sticky=tk.NSEW, pady=(8, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        c = self._colors
        self.log = scrolledtext.ScrolledText(
            log_frame,
            height=8,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg=c["log_bg"],
            fg=c["log_fg"],
            insertbackground=c["fg"],
            selectbackground=c["accent"],
            selectforeground=c["accent_btn_fg"],
            relief=tk.FLAT,
            padx=8,
            pady=8,
            font=("Consolas", 10),
        )
        self.log.grid(row=0, column=0, sticky=tk.NSEW)

        # --- Top: scrollable settings + progress ---
        self._scroll_frame = ScrollableFrame(outer, bg=c["bg"])
        self._scroll_frame.grid(row=0, column=0, sticky=tk.NSEW)
        content = self._scroll_frame.inner

        settings = ttk.LabelFrame(content, text="Search settings", padding=10)
        settings.pack(fill=tk.X, padx=4, pady=(0, 8))

        self.prefix_var = tk.StringVar(value="osmo1")
        self.suffix_var = tk.StringVar(value="")
        self.batch_var = tk.IntVar(value=10_000)
        self.count_var = tk.IntVar(value=1)
        self.strength_var = tk.StringVar(value="256")
        self.path_var = tk.StringVar(value="m/44'/118'/0'/0/0")
        self.output_var = tk.StringVar(value=str(_ROOT / "addr_list.jsonl"))
        self.workers_var = tk.IntVar(value=2)

        row = 0
        ttk.Label(settings, text="Prefix").grid(row=row, column=0, sticky=tk.W, **pad)
        ttk.Entry(settings, textvariable=self.prefix_var).grid(
            row=row, column=1, columnspan=3, sticky=tk.EW, **pad
        )
        row += 1
        ttk.Label(settings, text="Suffix").grid(row=row, column=0, sticky=tk.W, **pad)
        ttk.Entry(settings, textvariable=self.suffix_var).grid(
            row=row, column=1, columnspan=3, sticky=tk.EW, **pad
        )
        row += 1

        ttk.Label(settings, text="Batch size").grid(row=row, column=0, sticky=tk.W, **pad)
        ttk.Spinbox(
            settings, from_=100, to=1_000_000, increment=1000, textvariable=self.batch_var, width=12
        ).grid(row=row, column=1, sticky=tk.W, **pad)
        ttk.Label(settings, text="Target count").grid(row=row, column=2, sticky=tk.W, **pad)
        ttk.Spinbox(settings, from_=1, to=10_000, textvariable=self.count_var, width=8).grid(
            row=row, column=3, sticky=tk.W, **pad
        )
        row += 1

        ttk.Label(settings, text="Strength (bits)").grid(row=row, column=0, sticky=tk.W, **pad)
        ttk.Combobox(
            settings,
            textvariable=self.strength_var,
            values=[str(s) for s in ALLOWED_STRENGTHS],
            width=10,
            state="readonly",
        ).grid(row=row, column=1, sticky=tk.W, **pad)

        self.mnemonic_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings, text="BIP39 mnemonic mode", variable=self.mnemonic_var).grid(
            row=row, column=2, columnspan=2, sticky=tk.W, **pad
        )
        row += 1

        ttk.Label(settings, text="Derivation path").grid(row=row, column=0, sticky=tk.W, **pad)
        ttk.Entry(settings, textvariable=self.path_var).grid(
            row=row, column=1, columnspan=3, sticky=tk.EW, **pad
        )
        row += 1

        ttk.Label(settings, text="Output file").grid(row=row, column=0, sticky=tk.W, **pad)
        ttk.Entry(settings, textvariable=self.output_var).grid(
            row=row, column=1, columnspan=2, sticky=tk.EW, **pad
        )
        ttk.Button(settings, text="Browse…", command=self._browse_output).grid(row=row, column=3, **pad)
        row += 1

        opts = ttk.Frame(settings)
        opts.grid(row=row, column=0, columnspan=4, sticky=tk.W, **pad)
        self.no_secrets_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Address only (no keys in file)", variable=self.no_secrets_var).pack(
            anchor=tk.W, pady=2
        )
        pool_row = ttk.Frame(opts)
        pool_row.pack(anchor=tk.W, pady=2)
        self.pool_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(pool_row, text="Multiprocessing", variable=self.pool_var).pack(side=tk.LEFT)
        ttk.Label(pool_row, text="Workers").pack(side=tk.LEFT, padx=(12, 4))
        ttk.Spinbox(pool_row, from_=1, to=64, textvariable=self.workers_var, width=5).pack(side=tk.LEFT)

        for col in (1, 2, 3):
            settings.columnconfigure(col, weight=1)

        self.difficulty_label = ttk.Label(content, text="", style="Dim.TLabel")
        self.difficulty_label.pack(fill=tk.X, padx=8, pady=(0, 4))
        self.prefix_var.trace_add("write", lambda *_: self._update_difficulty_hint())
        self.suffix_var.trace_add("write", lambda *_: self._update_difficulty_hint())

        prog = ttk.LabelFrame(content, text="Progress", padding=10)
        prog.pack(fill=tk.X, padx=4, pady=(0, 8))
        self.progress_var = tk.StringVar(value="Idle — configure settings and press START")
        ttk.Label(prog, textvariable=self.progress_var, font=("", 11, "bold")).pack(anchor=tk.W)
        self.progress_bar = ttk.Progressbar(prog, mode="indeterminate")
        self.progress_bar.pack(fill=tk.X, pady=(8, 0))

        hint = ttk.Label(
            content,
            text="Tip: scroll this panel with mouse wheel if settings do not fit on screen.",
            style="Dim.TLabel",
        )
        hint.pack(fill=tk.X, padx=8, pady=(0, 4))

        self._append_log("Ready. View → Theme to change colors. Press ▶ START at the bottom.")

    def _browse_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Output JSONL",
            defaultextension=".jsonl",
            filetypes=[("JSON Lines", "*.jsonl"), ("All files", "*.*")],
            initialfile="addr_list.jsonl",
        )
        if path:
            self.output_var.set(path)

    def _update_difficulty_hint(self) -> None:
        try:
            validate_pattern(self.prefix_var.get().strip(), self.suffix_var.get().strip())
            d = estimate_difficulty(self.prefix_var.get().strip(), self.suffix_var.get().strip())
            if d.constrained_chars == 0:
                text = "Difficulty: trivial (HRP only)"
            else:
                text = f"Difficulty: ~{d.expected_attempts:,.0f} attempts ({d.constrained_chars} constrained char(s))"
            self.difficulty_label.configure(text=text, style="Dim.TLabel")
        except ValueError as e:
            self.difficulty_label.configure(text=str(e), style="Warn.TLabel")

    def _append_log(self, line: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, line + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _set_running(self, running: bool) -> None:
        self.start_btn.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_btn.configure(state=tk.NORMAL if running else tk.DISABLED)
        if running:
            self.progress_bar.start(12)
        else:
            self.progress_bar.stop()

    def _config_from_ui(self) -> SearchConfig:
        return SearchConfig(
            prefix=self.prefix_var.get().strip(),
            suffix=self.suffix_var.get().strip(),
            batch=int(self.batch_var.get()),
            count=int(self.count_var.get()),
            strength=int(self.strength_var.get()),
            mnemonic=self.mnemonic_var.get(),
            path=self.path_var.get().strip(),
            output=self.output_var.get().strip(),
            no_private_key=self.no_secrets_var.get(),
            pool=self.pool_var.get(),
            pool_workers=int(self.workers_var.get()),
        )

    def _start(self) -> None:
        if self._proc and self._proc.is_alive():
            return
        try:
            config = self._config_from_ui()
            validate_pattern(config.prefix, config.suffix)
        except ValueError as e:
            messagebox.showerror("Invalid input", str(e))
            return

        self._append_log("——— Starting search ———")
        self._set_running(True)
        self.progress_var.set("Running…")

        self._proc, self._msg_queue, self._stop_event = start_search_process(config)
        self._poll_queue()

    def _cleanup_process(self, *, terminate: bool = False) -> None:
        if self._stop_event:
            self._stop_event.set()
        if not self._proc:
            return
        if self._proc.is_alive():
            self._proc.join(timeout=4 if not terminate else 0)
        if terminate and self._proc.is_alive():
            self._proc.terminate()
            self._proc.join(timeout=2)
        self._proc = None
        self._msg_queue = None
        self._stop_event = None

    def _stop(self) -> None:
        self.progress_var.set("Stopping…")
        self._append_log("Stop requested…")
        self._cleanup_process(terminate=True)
        self._set_running(False)
        if self.progress_var.get() == "Stopping…":
            self.progress_var.set("Stopped")

    def _poll_queue(self) -> None:
        if not self._msg_queue:
            return
        try:
            while True:
                msg = self._msg_queue.get_nowait()
                self._handle_message(msg)
        except queue.Empty:
            pass

        if self._proc and not self._proc.is_alive():
            self._cleanup_process()
            self._set_running(False)
            if self.progress_var.get() not in ("Done", "Stopped", "Error"):
                self.progress_var.set("Finished")
            return

        self._poll_after_id = self.after(150, self._poll_queue)

    def _handle_message(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "info":
            d = msg.get("difficulty", {})
            self._append_log(f"HRP: {msg.get('hrp')} | constrained chars: {d.get('constrained_chars', 0)}")
        elif kind == "progress":
            self.progress_var.set(
                f"Checked: {msg['attempts']:,} | {msg['speed']:,.0f} addr/s | "
                f"found {msg['found']}/{msg['target']}"
            )
        elif kind == "found":
            rec = msg["record"]
            self._append_log(f"✅ Found ({msg['found']}): {rec['address']}")
            if "private_key" in rec:
                self._append_log(f"   private_key: {rec['private_key']}")
            if "mnemonic" in rec:
                self._append_log(f"   mnemonic: {rec['mnemonic']}")
        elif kind == "done":
            self.progress_var.set("Done")
            self._set_running(False)
            self._append_log(
                f"Done. Found {msg['found']} / attempts {msg['attempts']:,}. Saved to {msg['output']}"
            )
        elif kind == "stopped":
            self.progress_var.set("Stopped")
            self._set_running(False)
            self._append_log(f"Stopped. Found {msg['found']}, attempts {msg['attempts']:,}")
        elif kind == "error":
            self.progress_var.set("Error")
            self._set_running(False)
            messagebox.showerror("Error", msg.get("message", "Unknown error"))
            self._append_log(f"ERROR: {msg.get('message')}")

    def _on_close(self) -> None:
        if self._proc and self._proc.is_alive():
            if not messagebox.askyesno("Quit", "Search is running. Stop and quit?"):
                return
            self._cleanup_process(terminate=True)
        if self._poll_after_id:
            self.after_cancel(self._poll_after_id)
        self.destroy()


def main() -> None:
    mp.freeze_support()
    app = VanityGuiApp()
    app.mainloop()


if __name__ == "__main__":
    main()
