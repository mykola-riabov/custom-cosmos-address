#!/usr/bin/env python3
"""Test worker spawn as if launched via installed cosmos-vanity-gui."""
import multiprocessing as mp
import os
import queue
import sys
import time

mp.freeze_support()

# Match real GUI launch: __main__ is the console script.
SCRIPT = "/usr/lib/custom-cosmos-address/venv/bin/cosmos-vanity-gui"
with open(SCRIPT, encoding="utf-8") as f:
    code = compile(f.read(), SCRIPT, "exec")
globals_dict = {"__name__": "__main__", "__file__": SCRIPT}
exec(code, globals_dict)

from gui.worker import SearchConfig, start_search_process


def test(pool: bool) -> None:
    cfg = SearchConfig(
        prefix="osmo1a",
        batch=800,
        count=1,
        pool=pool,
        pool_workers=2,
        output=f"/tmp/entry-pool-{pool}.jsonl",
    )
    proc, q, stop = start_search_process(cfg)
    print(f"pool={pool} pid={proc.pid}", flush=True)
    proc.join(30)
    msgs = []
    while not q.empty():
        msgs.append(q.get_nowait())
    print(f"pool={pool} exit={proc.exitcode} types={[m.get('type') for m in msgs]}", flush=True)
    if any(m.get("type") == "error" for m in msgs):
        print("ERROR", [m for m in msgs if m.get("type") == "error"], flush=True)


if __name__ == "__main__":
    # Above exec starts GUI mainloop if we don't prevent it - so restructure
    pass
