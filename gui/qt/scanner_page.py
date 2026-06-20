"""Balance scanner page for the Qt GUI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui.qt.found_wallets_table import FoundWalletsPanel
from gui.qt.scan_runner import ScanThread
from gui.qt.theme import get_colors
from gui.qt.widgets import Card, form_row
from scanner import ScanConfig


class ScannerPage(QWidget):
    def __init__(self, *, theme_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme_name = theme_name
        self._scan_thread: ScanThread | None = None
        self._last_progress_log = 0
        self._build_ui()

    def set_theme_name(self, name: str) -> None:
        self._theme_name = name

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        grid = QGridLayout(body)
        grid.setContentsMargins(0, 0, 8, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        scroll.setWidget(body)
        outer.addWidget(scroll, stretch=1)

        prog = Card("Progress")
        self._progress_label = QLabel("Ready — select wallet file(s) and press Start scan")
        prog.body_layout.addWidget(self._progress_label)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setVisible(False)
        prog.body_layout.addWidget(self._progress_bar)
        grid.addWidget(prog, 0, 0, 1, 2)

        input_card = Card("Input")
        self._input_path = QLineEdit(str(Path.home() / "addr_list.jsonl"))
        browse_in = QPushButton("Browse")
        browse_in.clicked.connect(self._browse_input)
        in_row = QHBoxLayout()
        in_row.addWidget(self._input_path, stretch=1)
        in_row.addWidget(browse_in)
        in_wrap = QWidget()
        in_wrap.setLayout(in_row)
        input_card.body_layout.addLayout(form_row("Wallet file", in_wrap))
        hint = QLabel("JSONL or JSON array from the generator (or glob like *.jsonl)")
        hint.setObjectName("cardHint")
        input_card.body_layout.addWidget(hint)
        grid.addWidget(input_card, 1, 0)

        endpoint = Card("Endpoint")
        self._lcd = QLineEdit("https://lcd-osmosis.keplr.app")
        self._denom = QLineEdit("uosmo")
        self._workers = QSpinBox()
        self._workers.setRange(1, 64)
        self._workers.setValue(20)
        endpoint.body_layout.addLayout(form_row("LCD URL", self._lcd))
        endpoint.body_layout.addLayout(form_row("Denom", self._denom))
        endpoint.body_layout.addLayout(form_row("Workers", self._workers))
        grid.addWidget(endpoint, 1, 1)

        output = Card("Output")
        self._result_dir = QLineEdit("found_wallets")
        self._cache_file = QLineEdit("checked_cache.json")
        browse_res = QPushButton("Browse")
        browse_res.clicked.connect(self._browse_result_dir)
        res_row = QHBoxLayout()
        res_row.addWidget(self._result_dir, stretch=1)
        res_row.addWidget(browse_res)
        res_wrap = QWidget()
        res_wrap.setLayout(res_row)
        output.body_layout.addLayout(form_row("Results dir", res_wrap))
        output.body_layout.addLayout(form_row("Cache file", self._cache_file))
        grid.addWidget(output, 2, 0, 1, 2)

        found_card = Card("Found wallets")
        self._found_panel = FoundWalletsPanel()
        self._found_panel._open_dir_btn.clicked.connect(self._open_results_dir)
        found_card.body_layout.addWidget(self._found_panel)
        grid.addWidget(found_card, 3, 0, 1, 2)

        log_card = Card("Scan log")
        self._log = QTextEdit()
        self._log.setObjectName("logView")
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(140)
        log_card.body_layout.addWidget(self._log)
        grid.addWidget(log_card, 4, 0, 1, 2)
        grid.setRowStretch(3, 2)
        grid.setRowStretch(4, 1)

        actions = QHBoxLayout()
        self._start_btn = QPushButton("START SCAN")
        self._start_btn.setObjectName("accentBtn")
        self._start_btn.clicked.connect(self._start)
        self._stop_btn = QPushButton("STOP")
        self._stop_btn.setObjectName("dangerBtn")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop)
        self._use_generator_output = QPushButton("Use generator output")
        self._use_generator_output.setObjectName("ghostBtn")
        self._use_generator_output.clicked.connect(self._fill_from_generator)
        actions.addWidget(self._start_btn)
        actions.addWidget(self._stop_btn)
        actions.addWidget(self._use_generator_output)
        actions.addStretch()
        outer.addLayout(actions)

        self._append_log("Scan locally generated wallets only — checks balances via Cosmos LCD.")

    def set_generator_output_path(self, path: str) -> None:
        if path.strip():
            self._input_path.setText(path.strip())

    def _fill_from_generator(self) -> None:
        parent = self.window()
        if hasattr(parent, "get_generator_output_path"):
            path = parent.get_generator_output_path()  # type: ignore[attr-defined]
            if path:
                self._input_path.setText(path)
                self._append_log(f"Input set from generator: {path}")
                return
        self._append_log("Set output path on the Generator page first.")

    def _browse_input(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Wallet file",
            str(Path.home()),
            "Wallet files (*.jsonl *.json);;All files (*.*)",
        )
        if path:
            self._input_path.setText(path)

    def _browse_result_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Results directory", self._result_dir.text() or ".")
        if path:
            self._result_dir.setText(path)

    def _open_results_dir(self) -> None:
        self._found_panel.open_results_dir(self._result_dir.text().strip() or "found_wallets")

    def _append_log(self, line: str) -> None:
        self._log.append(line)

    def _set_running(self, running: bool) -> None:
        self._start_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)
        self._progress_bar.setVisible(running)

    def _config_from_ui(self) -> ScanConfig:
        raw = self._input_path.text().strip()
        if "*" in raw or "?" in raw:
            return ScanConfig(
                input_glob=raw,
                lcd_endpoint=self._lcd.text().strip(),
                denom=self._denom.text().strip(),
                num_workers=int(self._workers.value()),
                result_dir=self._result_dir.text().strip() or "found_wallets",
                cache_file=self._cache_file.text().strip() or "checked_cache.json",
            )
        return ScanConfig(
            input_files=[raw] if raw else [],
            input_glob=raw,
            lcd_endpoint=self._lcd.text().strip(),
            denom=self._denom.text().strip(),
            num_workers=int(self._workers.value()),
            result_dir=self._result_dir.text().strip() or "found_wallets",
            cache_file=self._cache_file.text().strip() or "checked_cache.json",
        )

    def _start(self) -> None:
        if self._scan_thread and self._scan_thread.isRunning():
            return
        try:
            config = self._config_from_ui()
            if not config.input_files and not config.input_glob:
                raise ValueError("Wallet file or glob is required.")
            if not config.lcd_endpoint:
                raise ValueError("LCD endpoint is required.")
            if not config.denom:
                raise ValueError("Denom is required.")
        except ValueError as e:
            QMessageBox.critical(self, "Invalid input", str(e))
            return

        self._append_log("——— Starting balance scan ———")
        self._found_panel.clear()
        self._last_progress_log = 0
        self._set_running(True)
        self._progress_label.setText("Connecting…")

        self._scan_thread = ScanThread(config, self)
        self._scan_thread.message.connect(self._handle_message)
        self._scan_thread.finished_scan.connect(self._on_thread_finished)
        self._scan_thread.start()

    def _stop(self) -> None:
        if self._scan_thread and self._scan_thread.isRunning():
            self._progress_label.setText("Stopping…")
            self._append_log("Stop requested…")
            self._scan_thread.stop()

    def _on_thread_finished(self) -> None:
        self._set_running(False)
        if self._progress_label.text() in ("Stopping…", "Connecting…"):
            self._progress_label.setText("Stopped")
        self._scan_thread = None

    def _handle_message(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "info":
            self._append_log(f"LCD: {msg.get('lcd')} | denom: {msg.get('denom')}")
            for f in msg.get("files", []):
                self._append_log(f"  • {f}")
        elif kind == "file_start":
            self._append_log(f"Scanning {msg.get('file')}…")
            self._progress_label.setText(f"Scanning {Path(msg.get('file', '')).name}…")
        elif kind == "progress":
            checked = msg.get("checked", 0)
            self._progress_label.setText(
                f"Checked: {checked:,}  ·  skipped {msg.get('skipped', 0):,}  ·  "
                f"found {msg.get('found', 0)}  ·  errors {msg.get('errors', 0)}"
            )
            if checked - self._last_progress_log >= 50_000:
                self._last_progress_log = checked
                self._append_log(
                    f"… checked {checked:,}, found {msg.get('found', 0)} so far"
                )
        elif kind == "found":
            address = msg.get("address", "")
            amount = int(msg.get("amount", 0))
            denom = msg.get("denom", "")
            if address:
                self._found_panel.add_found(address, amount, denom)
        elif kind == "cache_flush":
            self._append_log(f"Cache saved ({msg.get('cache_size', 0):,} addresses)")
        elif kind == "file_done":
            out_jsonl = msg.get("out_jsonl")
            if out_jsonl:
                loaded = self._found_panel.load_jsonl(out_jsonl, replace=True)
                if loaded:
                    self._append_log(f"Loaded {loaded:,} found wallet(s) from {out_jsonl}")
            self._append_log(
                f"File done: found {msg.get('found', 0)}, checked {msg.get('checked', 0):,}, "
                f"skipped {msg.get('skipped', 0):,}"
            )
        elif kind == "done":
            self._progress_label.setText("Done")
            n = self._found_panel.count
            self._append_log(
                f"Done. {n:,} wallet(s) with balance · "
                f"checked {msg.get('checked', 0):,} · skipped {msg.get('skipped', 0):,} · "
                f"errors {msg.get('errors', 0)}"
            )
            self._append_log(f"Results: {msg.get('result_dir')} | cache: {msg.get('cache_file')}")
        elif kind == "stopped":
            self._progress_label.setText("Stopped")
            self._append_log(
                f"Stopped. Found {msg.get('found', 0)}, checked {msg.get('checked', 0):,}"
            )
        elif kind == "error":
            self._progress_label.setText("Error")
            QMessageBox.critical(self, "Error", msg.get("message", "Unknown error"))
            self._append_log(f"ERROR: {msg.get('message')}")

    def is_running(self) -> bool:
        return self._scan_thread is not None and self._scan_thread.isRunning()

    def request_stop(self) -> None:
        if self.is_running():
            self._stop()
