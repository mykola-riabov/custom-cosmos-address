#!/usr/bin/env python3
"""
Scan generated wallet files for on-chain balances via a Cosmos LCD endpoint.

Intended for checking addresses you generated locally (see main.py).
Do not use this tool to probe third-party or unknown wallets.
"""

from __future__ import annotations

import os
import signal
import sys

from tqdm import tqdm

from scanner import ScanConfig, load_cache, process_file, resolve_input_files, run_scan, save_cache_atomic

# Re-export env-based defaults for CLI compatibility
LCD_ENDPOINT = os.getenv("LCD_ENDPOINT", "https://lcd-osmosis.keplr.app").rstrip("/")
DENOM = os.getenv("DENOM", "uosmo")
NUM_WORKERS = int(os.getenv("NUM_WORKERS", "20"))
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "10"))
HTTP_RETRIES = int(os.getenv("HTTP_RETRIES", "2"))
RESULT_DIR = os.getenv("RESULT_DIR", "found_wallets")
CACHE_FILE = os.getenv("CACHE_FILE", "checked_cache.json")
CACHE_FLUSH_EVERY_OK = int(os.getenv("CACHE_FLUSH_EVERY_OK", "10000"))
FOUND_FLUSH_EVERY = int(os.getenv("FOUND_FLUSH_EVERY", "1"))
CREATE_EMPTY_CACHE_ON_START = os.getenv("CREATE_EMPTY_CACHE_ON_START", "false").lower() in ("1", "true", "yes")
IN_FLIGHT_MULTIPLIER = int(os.getenv("IN_FLIGHT_MULTIPLIER", "20"))
INPUT_GLOB = os.getenv("INPUT_GLOB", "*.jsonl")

os.makedirs(RESULT_DIR, exist_ok=True)


def _default_config() -> ScanConfig:
    return ScanConfig(
        input_glob=INPUT_GLOB,
        lcd_endpoint=LCD_ENDPOINT,
        denom=DENOM,
        num_workers=NUM_WORKERS,
        http_timeout=HTTP_TIMEOUT,
        http_retries=HTTP_RETRIES,
        result_dir=RESULT_DIR,
        cache_file=CACHE_FILE,
        cache_flush_every_ok=CACHE_FLUSH_EVERY_OK,
        found_flush_every=FOUND_FLUSH_EVERY,
        in_flight_multiplier=IN_FLIGHT_MULTIPLIER,
        create_empty_cache_on_start=CREATE_EMPTY_CACHE_ON_START,
    )


def main() -> None:
    import threading

    config = _default_config()
    cache_lock = threading.Lock()
    cache = load_cache(config.cache_file)

    if config.create_empty_cache_on_start and not os.path.exists(config.cache_file):
        save_cache_atomic(config.cache_file, cache)

    ok_since_flush_ref = [0]
    stop_event = threading.Event()

    def flush_all_and_exit(exit_code: int = 130) -> None:
        try:
            with cache_lock:
                if ok_since_flush_ref[0] > 0:
                    save_cache_atomic(config.cache_file, cache)
                    ok_since_flush_ref[0] = 0
                    print(f"\n💾 Cache flushed (SIGINT tail). cache_size={len(cache):,}")
        except Exception:
            pass
        print("\n🛑 Interrupted.")
        raise SystemExit(exit_code)

    signal.signal(signal.SIGINT, lambda s, f: flush_all_and_exit(130))

    wallet_files = resolve_input_files(config)
    if not wallet_files:
        print(f"No input files found by INPUT_GLOB='{config.input_glob}'.")
        return

    total_skipped = 0
    total_ok_checked = 0
    total_errors = 0
    total_found = 0

    for file_path in wallet_files:
        print(f"\n📂 Processing file: {file_path}")

        # tqdm wrapper via on_message for CLI progress line
        pbar = tqdm(desc=f"Checking {os.path.basename(file_path)}", unit="addr")

        def on_message(msg: dict) -> None:
            if msg.get("type") == "progress":
                pbar.update(500)

        (
            skipped_this_file,
            ok_checked_this_file,
            errors_this_file,
            found_this_file,
            _errors_list,
            out_jsonl,
            out_json,
        ) = process_file(
            file_path,
            config,
            cache,
            cache_lock,
            ok_since_flush_ref,
            stop_event=stop_event,
            on_message=on_message,
        )
        pbar.close()

        total_skipped += skipped_this_file
        total_ok_checked += ok_checked_this_file
        total_errors += errors_this_file
        total_found += found_this_file

        print(f"⏭️ Pre-skip cached OK (this file): {skipped_this_file:,}")
        print(f"✅ Done file. Found in this file: {found_this_file} (written to {out_jsonl})")
        print(f"📄 Array file updated: {out_json}")

    print("\n🎉 Done.")
    print(f"🧾 Cache file: {config.cache_file} (only OK checks cached)")
    print(f"📥 Input glob:                  {config.input_glob}")
    print(f"⏭️ Skipped (cached OK):         {total_skipped:,}")
    print(f"🔎 Successfully checked (OK):   {total_ok_checked:,}")
    print(f"✅ Found ({config.denom}>0):           {total_found:,}")
    print(f"⚠️ Errors (not cached):         {total_errors:,}")


if __name__ == "__main__":
    main()
