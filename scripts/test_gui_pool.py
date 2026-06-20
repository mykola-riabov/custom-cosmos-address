#!/usr/bin/env python3
import multiprocessing as mp
import os
import sys
import time

mp.freeze_support()
os.environ.setdefault("DISPLAY", ":0.0")

from PySide6.QtWidgets import QApplication

from gui.qt.main_window import MainWindow


def main() -> None:
    qt = QApplication(sys.argv)
    app = MainWindow()
    app._prefix.setText("osmo1a")
    app._batch.setValue(800)
    app._pool.setChecked(True)
    app._workers.setValue(2)
    app._output.setText("/tmp/gui-pool-fixed.jsonl")
    app._start()

    deadline = time.time() + 60
    while time.time() < deadline:
        qt.processEvents()
        app._poll_queue()
        if app._progress_label.text() in ("Done", "Error", "Stopped", "Finished"):
            break
        time.sleep(0.05)

    print("progress:", app._progress_label.text())
    print(app._log.toPlainText())


if __name__ == "__main__":
    main()
