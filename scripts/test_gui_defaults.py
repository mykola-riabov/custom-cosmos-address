#!/usr/bin/env python3
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
    print(
        "defaults:",
        app._prefix.text(),
        app._batch.value(),
        app._output.text(),
        flush=True,
    )
    app._start()

    deadline = time.time() + 60
    while time.time() < deadline:
        qt.processEvents()
        app._poll_queue()
        if app._progress_label.text() in ("Done", "Error", "Stopped", "Finished"):
            break
        if app._proc and not app._proc.is_alive():
            app._poll_queue()
            break
        time.sleep(0.05)

    print("--- LOG ---")
    print(app._log.toPlainText())
    print("progress:", app._progress_label.text())
    print("proc alive:", app._proc.is_alive() if app._proc else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
