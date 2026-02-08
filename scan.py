#!/usr/bin/env python3
from __future__ import annotations

import gc
import glob
import json
import os
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Iterable, List, Optional, Set, Tuple

import requests
from tqdm import tqdm

# =============================================================================
# Config
# =============================================================================
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
MAX_IN_FLIGHT = max(NUM_WORKERS, NUM_WORKERS * IN_FLIGHT_MULTIPLIER)

INPUT_GLOB = os.getenv("INPUT_GLOB", "*.jsonl")  # e.g. "osmo_*.jsonl" or "*.jsonl" or "*.json*"

os.makedirs(RESULT_DIR, exist_ok=True)

# =============================================================================
# Cache helpers
# =============================================================================
def load_cache(path: str) -> Dict[str, dict]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise RuntimeError(f"Cache file '{path}' must be a JSON object/dict at root.")
    return data

def save_cache_atomic(path: str, cache: Dict[str, dict]) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def cache_is_ok(cache: Dict[str, dict], addr: str) -> bool:
    rec = cache.get(addr)
    return bool(rec) and rec.get("status") == "ok"

def cache_put_ok(cache: Dict[str, dict], addr: str, amount: int) -> None:
    cache[addr] = {
        "checked_at": int(time.time()),
        "status": "ok",
        "denom": DENOM,
        "uosmo": amount,
    }

# =============================================================================
# HTTP helper
# =============================================================================
session = requests.Session()
session.headers.update({
    "User-Agent": "osmo-balance-check/1.0",
    "Accept": "application/json",
})

def get_json_with_retries(url: str) -> Tuple[Optional[dict], Optional[str]]:
    last_err = None
    for attempt in range(HTTP_RETRIES + 1):
        try:
            r = session.get(url, timeout=HTTP_TIMEOUT)

            if r.status_code == 429:
                wait = min(5.0, 0.5 * (attempt + 1) ** 2)
                time.sleep(wait)
                continue

            if r.status_code != 200:
                body = (r.text or "").strip()
                return None, f"HTTP {r.status_code}: {body[:200]}"

            return r.json(), None

        except requests.exceptions.RequestException as e:
            last_err = str(e)
            time.sleep(0.25 * (attempt + 1))

    return None, f"EXC: {last_err}"

# =============================================================================
# Worker
# =============================================================================
def worker_check(wallet: dict) -> Tuple[str, Optional[str], object, dict]:
    addr = wallet.get("address")
    if not addr:
        return ("BAD", None, "no address field", wallet)

    url = f"{LCD_ENDPOINT}/cosmos/bank/v1beta1/balances/{addr}"
    data, err = get_json_with_retries(url)
    if err:
        return ("ERR", addr, err, wallet)

    balances = data.get("balances", [])
    amount = 0
    for b in balances:
        if b.get("denom") == DENOM:
            try:
                amount = int(b.get("amount", "0"))
            except Exception:
                amount = 0
            break

    return ("OK", addr, amount, wallet)

# =============================================================================
# FOUND batching writer (JSONL append)
# =============================================================================
found_lock = threading.Lock()
found_buffer: List[dict] = []
found_jsonl_path: Optional[str] = None

def append_found_jsonl(batch: List[dict], path: str) -> None:
    if not batch:
        return
    with open(path, "a", encoding="utf-8") as f:
        for item in batch:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

def flush_found(force: bool = False) -> int:
    """
    Flush found_buffer to per-file JSONL. Returns flushed count.
    Uses global found_jsonl_path set per input file.
    """
    global found_jsonl_path
    if not found_jsonl_path:
        return 0

    with found_lock:
        if not force and len(found_buffer) < FOUND_FLUSH_EVERY:
            return 0
        batch = list(found_buffer)
        found_buffer.clear()

    append_found_jsonl(batch, found_jsonl_path)
    return len(batch)

def jsonl_to_array_streaming(jsonl_path: str, array_path: str) -> None:
    """
    Build JSON array file from JSONL without loading the whole file into RAM.
    """
    with open(array_path, "w", encoding="utf-8") as out:
        out.write("[\n")
        first = True
        if os.path.exists(jsonl_path):
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    if not first:
                        out.write(",\n")
                    out.write(line)
                    first = False
        out.write("\n]\n")

# =============================================================================
# Streaming wallet reader
# =============================================================================
def iter_wallets_streaming(path: str) -> Iterable[dict]:
    """
    Supports:
      - JSONL: one JSON object per line
      - JSON array: requires ijson (pip install ijson)
    """
    lower = path.lower()
    if lower.endswith(".jsonl"):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)
        return

    # For .json: detect first non-space char
    with open(path, "r", encoding="utf-8") as f:
        first = ""
        while True:
            ch = f.read(1)
            if not ch:
                break
            if not ch.isspace():
                first = ch
                break

    if first == "[":
        try:
            import ijson  # type: ignore
        except ImportError:
            raise RuntimeError(
                f"{path}: looks like a JSON array, but 'ijson' is not installed.\n"
                f"Install: pip install ijson\n"
                f"Or use JSONL input (.jsonl) from your generator."
            )
        with open(path, "r", encoding="utf-8") as f:
            for item in ijson.items(f, "item"):
                yield item
        return

    # Otherwise assume JSONL-like
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)

# =============================================================================
# Processing logic (clean scope)
# =============================================================================
def process_file(
    file_path: str,
    cache: Dict[str, dict],
    cache_lock: threading.Lock,
    ok_since_flush_ref: List[int],
) -> Tuple[int, int, int, int, List[str], str, str]:
    """
    Process one input file streaming, with bounded in-flight futures.

    ok_since_flush_ref: a 1-item list used as a mutable int holder so SIGINT can flush safely.
    Returns:
      skipped_this_file, ok_checked_this_file, errors_count_this_file, found_this_file, errors_list,
      found_jsonl_path, found_array_path
    """
    global found_jsonl_path

    base = os.path.splitext(os.path.basename(file_path))[0]
    found_jsonl_path = os.path.join(RESULT_DIR, f"found_from_{base}.jsonl")
    found_array_path = os.path.join(RESULT_DIR, f"found_from_{base}.json")

    skipped_this_file = 0
    ok_checked_this_file = 0
    found_this_file = 0
    errors: List[str] = []
    errors_count_this_file = 0

    pbar = tqdm(desc=f"Checking {os.path.basename(file_path)}", unit="addr")
    in_flight: Set = set()

    def handle_result(status: str, addr: Optional[str], payload: object, wallet: dict) -> None:
        nonlocal ok_checked_this_file, found_this_file, errors_count_this_file

        if status == "OK":
            amount = int(payload)  # type: ignore[arg-type]

            # Cache only successful checks
            with cache_lock:
                if addr and not cache_is_ok(cache, addr):
                    cache_put_ok(cache, addr, amount)
                    ok_checked_this_file += 1
                    ok_since_flush_ref[0] += 1

            # Found buffering (batched)
            if amount > 0:
                out = dict(wallet)
                out[DENOM] = amount
                with found_lock:
                    found_buffer.append(out)
                found_this_file += 1
                flush_found(force=False)

            # Cache flush by threshold
            with cache_lock:
                should_flush_cache = ok_since_flush_ref[0] >= CACHE_FLUSH_EVERY_OK
            if should_flush_cache:
                with cache_lock:
                    if ok_since_flush_ref[0] >= CACHE_FLUSH_EVERY_OK:
                        save_cache_atomic(CACHE_FILE, cache)
                        print(f"\n💾 Cache flushed (batched {CACHE_FLUSH_EVERY_OK} OK). cache_size={len(cache):,}")
                        ok_since_flush_ref[0] = 0

        elif status == "ERR":
            errors_count_this_file += 1
            errors.append(f"{addr} {payload}")
        else:
            errors.append(f"BAD_WALLET {payload}")

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        for wallet in iter_wallets_streaming(file_path):
            addr = wallet.get("address")
            if addr and cache_is_ok(cache, addr):
                skipped_this_file += 1
                pbar.update(1)
                continue

            fut = executor.submit(worker_check, wallet)
            in_flight.add(fut)

            if len(in_flight) >= MAX_IN_FLIGHT:
                done = next(as_completed(in_flight))
                in_flight.remove(done)
                status, a, payload, w = done.result()
                pbar.update(1)
                handle_result(status, a, payload, w)

        # Drain remaining futures
        for done in as_completed(in_flight):
            status, a, payload, w = done.result()
            pbar.update(1)
            handle_result(status, a, payload, w)

    pbar.close()

    # Tail flush after each input file
    flush_found(force=True)

    with cache_lock:
        if ok_since_flush_ref[0] > 0:
            save_cache_atomic(CACHE_FILE, cache)
            print(f"\n💾 Cache flushed (end-of-file tail). cache_size={len(cache):,}")
            ok_since_flush_ref[0] = 0

    # Errors file
    if errors:
        err_file = os.path.join(RESULT_DIR, f"errors_from_{base}.log")
        with open(err_file, "w", encoding="utf-8") as f:
            f.write("\n".join(errors) + "\n")
        print(f"⚠️ Errors saved to {err_file}")

    # Build JSON array (streaming)
    jsonl_to_array_streaming(found_jsonl_path, found_array_path)

    # Aggressive cleanup
    in_flight.clear()
    with found_lock:
        found_buffer.clear()
    gc.collect()

    return (
        skipped_this_file,
        ok_checked_this_file,
        errors_count_this_file,
        found_this_file,
        errors,
        found_jsonl_path,
        found_array_path,
    )

# =============================================================================
# SIGINT safe flush
# =============================================================================
cache_lock = threading.Lock()
cache = load_cache(CACHE_FILE)

if CREATE_EMPTY_CACHE_ON_START and not os.path.exists(CACHE_FILE):
    save_cache_atomic(CACHE_FILE, cache)

# use a 1-item list as "mutable integer" for safe sharing with signal handler
ok_since_flush_ref = [0]

def flush_all_and_exit(exit_code: int = 130):
    flushed_found = 0
    try:
        flushed_found = flush_found(force=True)
    except Exception:
        pass

    try:
        with cache_lock:
            if ok_since_flush_ref[0] > 0:
                save_cache_atomic(CACHE_FILE, cache)
                ok_since_flush_ref[0] = 0
                print(f"\n💾 Cache flushed (SIGINT tail). cache_size={len(cache):,}")
    except Exception:
        pass

    print(f"\n🛑 Interrupted. Flushed found_tail={flushed_found}")
    raise SystemExit(exit_code)

def _sigint_handler(sig, frame):
    flush_all_and_exit(130)

signal.signal(signal.SIGINT, _sigint_handler)

# =============================================================================
# Main
# =============================================================================
wallet_files = sorted([
    f for f in glob.glob(INPUT_GLOB)
    if not os.path.basename(f).startswith("found_")
    and not os.path.abspath(f).startswith(os.path.abspath(RESULT_DIR))
    and os.path.abspath(f) != os.path.abspath(CACHE_FILE)
])

if not wallet_files:
    print(f"No input files found by INPUT_GLOB='{INPUT_GLOB}'.")
    raise SystemExit(0)

total_skipped = 0
total_ok_checked = 0
total_errors = 0
total_found = 0

for file_path in wallet_files:
    print(f"\n📂 Processing file: {file_path}")

    (
        skipped_this_file,
        ok_checked_this_file,
        errors_this_file,
        found_this_file,
        _errors_list,
        out_jsonl,
        out_json,
    ) = process_file(file_path, cache, cache_lock, ok_since_flush_ref)

    total_skipped += skipped_this_file
    total_ok_checked += ok_checked_this_file
    total_errors += errors_this_file
    total_found += found_this_file

    print(f"⏭️ Pre-skip cached OK (this file): {skipped_this_file:,}")
    print(f"✅ Done file. Found in this file: {found_this_file} (written batched to {out_jsonl})")
    print(f"📄 Array file updated: {out_json}")

print("\n🎉 Done.")
print(f"🧾 Cache file: {CACHE_FILE} (only OK checks cached)")
print(f"📥 Input glob:                  {INPUT_GLOB}")
print(f"⏭️ Skipped (cached OK):         {total_skipped:,}")
print(f"🔎 Successfully checked (OK):   {total_ok_checked:,}")
print(f"✅ Found (uosmo>0):             {total_found:,}")
print(f"⚠️ Errors (not cached):         {total_errors:,}")
print(f"💾 Cache flush threshold (OK):  {CACHE_FLUSH_EVERY_OK:,}")
print(f"💾 Found flush threshold:       {FOUND_FLUSH_EVERY:,}")
print(f"🧵 Max in-flight futures:       {MAX_IN_FLIGHT:,}")

