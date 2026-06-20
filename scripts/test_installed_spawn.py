#!/usr/bin/env python3
"""Reproduce GUI worker spawn using installed entry script as __main__."""
import multiprocessing as mp
import queue
import sys
import time

mp.freeze_support()

# Force __main__ to be the installed console script (like spawn does).
import runpy

SCRIPT = "/usr/lib/custom-cosmos-address/venv/bin/cosmos-vanity-gui"
runpy.run_path(SCRIPT, run_name="__mp_main__")

from gui.worker import SearchConfig, start_search_process

if __name__ == "__main__":
    cfg = SearchConfig(
        prefix="osmo1a",
        batch=500,
        count=1,
        output="/tmp/test-gui-spawn-installed.jsonl",
    )
    proc, q, stop = start_search_process(cfg)
    print("started pid", proc.pid, "alive", proc.is_alive(), flush=True)
    for _ in range(50):
        try:
            while True:
                msg = q.get_nowait()
                print("MSG", msg.get("type"), msg, flush=True)
        except queue.Empty:
            pass
        if not proc.is_alive():
            print("child exit", proc.exitcode, flush=True)
            break
        time.sleep(0.2)
    else:
        print("timeout still alive", proc.is_alive(), flush=True)
        stop.set()
        proc.join(2)
        print("after stop exit", proc.exitcode, flush=True)
