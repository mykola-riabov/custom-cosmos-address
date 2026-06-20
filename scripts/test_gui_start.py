#!/usr/bin/env python3
"""Headless-ish test: instantiate GUI and trigger START programmatically."""
import multiprocessing as mp
import os
import sys
import time

mp.freeze_support()

os.environ.setdefault("DISPLAY", ":0.0")

from PySide6.QtWidgets import QApplication

from gui.qt.main_window import MainWindow


def main() -> int:
    qt = QApplication(sys.argv)
    app = MainWindow()
    app._prefix.setText("osmo1a")
    app._batch.setValue(500)
    app._count.setValue(1)
    app._output.setText("/tmp/gui-autotest.jsonl")

    app._start()
    print("start invoked, proc=", app._proc, flush=True)

    deadline = time.time() + 30
    while time.time() < deadline:
        qt.processEvents()
        app._poll_queue()
        if app._proc and not app._proc.is_alive():
            app._poll_queue()
            break
        if app._progress_label.text() in ("Done", "Error", "Stopped", "Finished"):
            break
        time.sleep(0.05)

    print("--- LOG ---")
    print(app._log.toPlainText())
    print("progress:", app._progress_label.text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
