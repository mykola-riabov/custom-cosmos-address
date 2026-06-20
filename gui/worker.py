"""Background search process for the GUI (keeps Qt main thread responsive)."""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

# Project root on sys.path when launched as `python -m gui`
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from cosmos_address import (  # noqa: E402
    ALLOWED_STRENGTHS,
    check_key_indexed,
    estimate_difficulty,
    generate_keys_batch,
    hrp_from_prefix,
    try_match_privkey,
    validate_pattern,
)

OUTPUT_MODE = 0o600
_PROGRESS_EVERY = 2_000


def _worker_mp_context() -> mp.context.BaseContext:
    """Prefer forkserver on Linux for reliable GUI + multiprocessing."""
    if sys.platform == "linux":
        for method in ("forkserver", "spawn"):
            try:
                return mp.get_context(method)
            except ValueError:
                continue
    return mp.get_context("spawn")


def _pool_mp_context() -> mp.context.BaseContext:
    """Worker subprocess has no Qt; fork is safe and faster on Linux."""
    if sys.platform == "linux":
        try:
            return mp.get_context("fork")
        except ValueError:
            pass
    return mp.get_context("spawn")


@dataclass
class SearchConfig:
    prefix: str = "osmo1"
    suffix: str = ""
    batch: int = 10_000
    count: int = 1
    strength: int = 256
    mnemonic: bool = False
    path: str = "m/44'/118'/0'/0/0"
    output: str = "addr_list.jsonl"
    no_private_key: bool = False
    pool: bool = False
    pool_workers: int = 2


def _secure_chmod(path: str) -> None:
    try:
        os.chmod(path, OUTPUT_MODE)
    except OSError:
        pass


def _build_record(
    addr: str,
    priv: bytes,
    mnemonic: str | None,
    *,
    include_secrets: bool,
) -> dict[str, Any]:
    rec: dict[str, Any] = {"address": addr}
    if include_secrets:
        rec["private_key"] = priv.hex()
        if mnemonic:
            rec["mnemonic"] = mnemonic
    return rec


def run_search(config: SearchConfig, msg_queue: mp.Queue, stop_event: mp.Event) -> None:
    """Run vanity search; push dict messages to msg_queue."""
    try:
        validate_pattern(config.prefix, config.suffix)
    except ValueError as e:
        msg_queue.put({"type": "error", "message": str(e)})
        return

    if config.strength not in ALLOWED_STRENGTHS:
        msg_queue.put({"type": "error", "message": f"Invalid strength: {config.strength}"})
        return

    hrp = hrp_from_prefix(config.prefix)
    diff = estimate_difficulty(config.prefix, config.suffix)
    msg_queue.put(
        {
            "type": "info",
            "hrp": hrp,
            "difficulty": asdict(diff),
        }
    )

    out_path = config.output
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    include_secrets = not config.no_private_key
    pool_args = (config.prefix, config.suffix, hrp)

    attempts = 0
    found_count = 0
    start = time.time()
    last_progress_at = 0

    def emit_progress(*, force: bool = False, attempt_count: int | None = None) -> None:
        nonlocal last_progress_at
        current = attempt_count if attempt_count is not None else attempts
        if not force and current - last_progress_at < _PROGRESS_EVERY:
            return
        last_progress_at = current
        elapsed = time.time() - start
        speed = current / elapsed if elapsed > 0 else 0.0
        msg_queue.put(
            {
                "type": "progress",
                "attempts": current,
                "speed": speed,
                "found": found_count,
                "target": config.count,
            }
        )

    def process_batch(keys: list[bytes], mnemonics: list[str] | None, pool: mp.Pool | None) -> bool:
        """Process one batch. Returns True if search should stop."""
        nonlocal found_count, attempts

        if pool is not None:
            work = [(i, k, *pool_args) for i, k in enumerate(keys)]
            checked_in_batch = 0
            for idx, addr in pool.imap_unordered(check_key_indexed, work, chunksize=256):
                if stop_event.is_set():
                    return True
                checked_in_batch += 1
                if checked_in_batch % _PROGRESS_EVERY == 0:
                    emit_progress(force=True, attempt_count=attempts + checked_in_batch)
                if not addr:
                    continue
                rec = _build_record(
                    addr,
                    keys[idx],
                    mnemonics[idx] if mnemonics else None,
                    include_secrets=include_secrets,
                )
                out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out_f.flush()
                found_count += 1
                msg_queue.put({"type": "found", "record": rec, "found": found_count})
                if found_count >= config.count:
                    return True
            return stop_event.is_set()

        for idx, priv in enumerate(keys):
            if stop_event.is_set():
                return True
            addr = try_match_privkey(priv, *pool_args)
            if idx and idx % _PROGRESS_EVERY == 0:
                emit_progress(force=True, attempt_count=attempts + idx + 1)
            if not addr:
                continue
            rec = _build_record(
                addr,
                priv,
                mnemonics[idx] if mnemonics else None,
                include_secrets=include_secrets,
            )
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_f.flush()
            found_count += 1
            msg_queue.put({"type": "found", "record": rec, "found": found_count})
            if found_count >= config.count:
                return True
        return stop_event.is_set()

    try:
        with open(out_path, "a", encoding="utf-8") as out_f:
            _secure_chmod(out_path)

            pool_ctx = (
                _pool_mp_context().Pool(processes=config.pool_workers) if config.pool else None
            )
            try:
                while found_count < config.count and not stop_event.is_set():
                    keys, mnemonics = generate_keys_batch(
                        config.batch,
                        config.strength,
                        mnemonic=config.mnemonic,
                        derivation_path=config.path,
                    )
                    attempts += len(keys)

                    if process_batch(keys, mnemonics, pool_ctx):
                        break

                    emit_progress(force=True)
            finally:
                if pool_ctx is not None:
                    pool_ctx.close()
                    pool_ctx.join()

        if stop_event.is_set():
            msg_queue.put({"type": "stopped", "attempts": attempts, "found": found_count})
        else:
            msg_queue.put(
                {
                    "type": "done",
                    "attempts": attempts,
                    "found": found_count,
                    "output": out_path,
                }
            )
    except Exception as e:
        msg_queue.put({"type": "error", "message": str(e)})


def start_search_process(
    config: SearchConfig,
) -> tuple[mp.Process, mp.Queue, mp.Event]:
    ctx = _worker_mp_context()
    msg_queue: mp.Queue = ctx.Queue()
    stop_event = ctx.Event()
    # Non-daemon: pool mode spawns child workers inside run_search.
    proc = ctx.Process(
        target=run_search,
        args=(config, msg_queue, stop_event),
        daemon=False,
    )
    proc.start()
    return proc, msg_queue, stop_event
