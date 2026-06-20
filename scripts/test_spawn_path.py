#!/usr/bin/env python3
import multiprocessing as mp
import os
import sys
import time

mp.freeze_support()
os.environ.setdefault("DISPLAY", ":0.0")

_orig_start = mp.context.SpawnProcess.start


def _logged_start(self):
    print(
        "SpawnProcess starting, parent __main__ file:",
        getattr(sys.modules.get("__main__"), "__file__", None),
        flush=True,
    )
    return _orig_start(self)


mp.context.SpawnProcess.start = _logged_start

from PySide6.QtWidgets import QApplication

from gui.qt.main_window import MainWindow

qt = QApplication(sys.argv)
app = MainWindow()
app._prefix.setText("osmo1a")
app._batch.setValue(500)
app._output.setText("/tmp/spawn-path-test.jsonl")
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

print("progress:", app._progress_label.text(), flush=True)
print("proc exit:", app._proc.exitcode if app._proc else None, flush=True)
print(app._log.toPlainText())
