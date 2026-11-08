#!/usr/bin/env python3
"""CLI for Cosmos SDK vanity address generation (CPU-only)."""

from __future__ import annotations

import argparse
import glob
import json
import multiprocessing as mp
import os
import signal
import sys
import time

try:
    import psutil
except ImportError as e:
    print(f"❌ Missing dependency: {e.name}")
    sys.exit(1)

import secp
from cosmos_address import (
    ALLOWED_STRENGTHS,
    VERSION,
    estimate_difficulty,
    hrp_from_prefix,
    make_matcher,
    validate_pattern,
)
from search_engine import Job, SearchEngine, default_workers, random_privkey

OUTPUT_MODE = 0o600


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="custom-cosmos is a CPU custom address generator for Cosmos-based chains.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--prefix", type=str, default="osmo1", help="Address must start with this string.")
    parser.add_argument("--suffix", type=str, default="", help="Address must end with this string.")
    parser.add_argument(
        "--batch",
        type=int,
        default=500,
        help="Keys each worker checks between progress reports and stop checks",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="addr_list.jsonl",
        help="Output base filename. Recommended: .jsonl (streaming).",
    )
    parser.add_argument(
        "--output-format",
        choices=["jsonl", "json"],
        default="jsonl",
        help="Write JSONL or finalize JSON arrays from JSONL at end.",
    )
    parser.add_argument(
        "--per-file",
        type=int,
        default=0,
        help="Rotate output after N FOUND results per file. 0 = single file.",
    )
    parser.add_argument("--count", type=int, default=1, help="Matches required before stopping")
    parser.add_argument(
        "--strength",
        type=int,
        default=256,
        choices=ALLOWED_STRENGTHS,
        help="Entropy bits (mnemonic: BIP39; fast: input expanded to 32-byte key)",
    )
    parser.add_argument(
        "--workers",
        "--pool-workers",
        dest="workers",
        type=int,
        default=default_workers(),
        help="Worker processes; each generates and checks keys on its own (default: CPU count)",
    )
    parser.add_argument("--pool", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--mnemonic", action="store_true", help="BIP39 + derivation path")
    parser.add_argument(
        "--index-search",
        action="store_true",
        help="With --mnemonic: one phrase per worker, scan the last path index (fast). "
        "The found path is saved with the result.",
    )
    parser.add_argument("--path", type=str, default="m/44'/118'/0'/0/0", help="Derivation path (--mnemonic)")
    parser.add_argument(
        "--no-private-key",
        action="store_true",
        help="Do not write private_key/mnemonic to output (address only)",
    )
    parser.add_argument(
        "--force-output",
        action="store_true",
        help="Append to existing output files without confirmation",
    )
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    return parser.parse_args()


def get_cpu_temp() -> str:
    try:
        temps = psutil.sensors_temperatures()
        for name in ("k10temp", "coretemp", "acpitz", "cpu_thermal"):
            entries = temps.get(name)
            if entries:
                return f"{entries[0].current:.1f}°C"
    except Exception:
        pass
    return "-"


def split_output_name(path: str) -> tuple[str, str]:
    root, ext = os.path.splitext(path)
    return root, ext or ".jsonl"


def secure_chmod(path: str) -> None:
    try:
        os.chmod(path, OUTPUT_MODE)
    except OSError:
        pass


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f} sec"
    if seconds < 3600:
        return f"{seconds / 60:.1f} min"
    if seconds < 86400:
        return f"{seconds / 3600:.1f} hr"
    return f"{seconds / 86400:.1f} days"


def warmup_speed(prefix: str, suffix: str, batch: int = 2_000) -> float:
    """Single-core address checks per second (random-key mode)."""
    matcher = make_matcher(prefix, suffix)
    keys = [random_privkey(256) for _ in range(batch)]
    t0 = time.perf_counter()
    for priv in keys:
        matcher(priv)
    elapsed = time.perf_counter() - t0
    return batch / elapsed if elapsed > 0 else 0.0


def search_mode(args: argparse.Namespace) -> str:
    if not args.mnemonic:
        return "key"
    return "index" if args.index_search else "mnemonic"


def warn_existing_outputs(out_root: str, force: bool) -> None:
    existing = [p for p in glob.glob(f"{out_root}*.jsonl") if os.path.getsize(p) > 0]
    if not existing or force:
        return
    print("⚠️  Output file(s) already exist and will be APPENDED to:")
    for p in existing[:5]:
        print(f"   - {p}")
    if len(existing) > 5:
        print(f"   ... and {len(existing) - 5} more")
    print("   Use --force-output to skip this warning, or choose a new --output path.")
    try:
        answer = input("Continue? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(1)
    if answer not in ("y", "yes"):
        print("Aborted.")
        sys.exit(0)


def jsonl_files_to_json_arrays(out_root: str) -> None:
    for jsonl_path in sorted(glob.glob(f"{out_root}*.jsonl")):
        array_path = os.path.splitext(jsonl_path)[0] + ".json"
        with open(jsonl_path, encoding="utf-8") as fin, open(array_path, "w", encoding="utf-8") as fout:
            fout.write("[\n")
            first = True
            for line in fin:
                line = line.strip()
                if not line:
                    continue
                if not first:
                    fout.write(",\n")
                fout.write(line)
                first = False
            fout.write("\n]\n")
        secure_chmod(array_path)


def build_record(found: dict, *, include_secrets: bool) -> dict:
    """Output record from an engine match; secrets dropped unless asked for. The path is not secret."""
    rec: dict = {"address": found["address"]}
    if include_secrets:
        rec["private_key"] = found["private_key"]
        if found.get("mnemonic"):
            rec["mnemonic"] = found["mnemonic"]
    if found.get("path"):
        rec["path"] = found["path"]
    return rec


def main() -> None:
    args = parse_args()

    if args.version:
        print(f"custom-cosmos (CPU-only) version {VERSION}")
        return

    if args.per_file < 0:
        print("❌ --per-file must be >= 0")
        sys.exit(1)
    if args.workers < 1 or args.batch < 1:
        print("❌ --workers and --batch must be >= 1")
        sys.exit(1)
    if args.index_search and not args.mnemonic:
        print("❌ --index-search needs --mnemonic")
        sys.exit(1)

    try:
        validate_pattern(args.prefix, args.suffix)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    hrp = hrp_from_prefix(args.prefix)
    diff = estimate_difficulty(args.prefix, args.suffix)
    out_root, _ = split_output_name(args.output)
    warn_existing_outputs(out_root, args.force_output)

    start = time.time()
    last_log = start
    found_count = 0
    include_secrets = not args.no_private_key

    current_part = 1

    def make_part_path(part_idx: int) -> str:
        if args.per_file > 0:
            return f"{out_root}_{part_idx:03d}.jsonl"
        return f"{out_root}.jsonl"

    current_path = make_part_path(current_part)
    os.makedirs(os.path.dirname(current_path) or ".", exist_ok=True)
    out_f = open(current_path, "a", encoding="utf-8")
    secure_chmod(current_path)
    written_in_part = 0

    def rotate_if_needed() -> None:
        nonlocal current_part, current_path, out_f, written_in_part
        if args.per_file <= 0 or written_in_part < args.per_file:
            return
        out_f.flush()
        out_f.close()
        current_part += 1
        current_path = make_part_path(current_part)
        out_f = open(current_path, "a", encoding="utf-8")
        secure_chmod(current_path)
        written_in_part = 0

    def write_jsonl(obj: dict) -> None:
        out_f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def handle_match(found: dict) -> bool:
        nonlocal found_count, written_in_part
        rec = build_record(found, include_secrets=include_secrets)
        write_jsonl(rec)
        found_count += 1
        written_in_part += 1
        rotate_if_needed()
        print(f"\n✅ Found! {found_count}/{args.count}")
        print(f"🔗 Address : {rec['address']}")
        if include_secrets:
            print(f"🔐 Private Key : {rec['private_key']}")
            if rec.get("mnemonic"):
                print(f"🧠 Mnemonic    : {rec['mnemonic']}")
        if rec.get("path"):
            print(f"📍 Path        : {rec['path']}")
        return found_count >= args.count

    engine: SearchEngine | None = None

    def on_interrupt(sig, frame) -> None:
        if mp.current_process().name != "MainProcess":
            return
        if engine is not None:
            engine.stop()
        attempts = engine.attempts if engine is not None else 0
        elapsed = time.time() - start
        print("\n🛑 Interrupted by user")
        print(f"🔁 Attempts : {attempts:,}")
        if elapsed > 0:
            print(f"⚡ Speed    : {attempts / elapsed:,.2f} addr/sec")
        print(f"⏱ Time     : {elapsed:.2f} sec\n")
        try:
            out_f.flush()
            out_f.close()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, on_interrupt)

    print("🚀 Start searching for a custom address")
    print(f"🔹 Prefix  : {args.prefix}")
    print(f"🔹 Suffix  : {args.suffix or '(none)'}")
    print(f"🔹 HRP     : {hrp}")
    print(
        f"🔐 Strength: {args.strength} bits "
        f"({'BIP39 entropy' if args.mnemonic else 'fast-mode input; privkey always 32 bytes'})"
    )
    print(f"📦 Report  : every {args.batch:,} keys per worker")
    print(f"🔁 Target  : {args.count} match(es)")
    mode = search_mode(args)
    print(
        "🧠 Mnemonic: "
        + {"key": "disabled", "mnemonic": "new phrase per attempt", "index": "one phrase per worker, index scan"}[mode]
    )
    if args.mnemonic:
        print(f"📍 Path    : {args.path}" + (" (last index scanned)" if mode == "index" else ""))
    print(f"🧵 Workers : {args.workers} process(es) · curve backend: {secp.BACKEND}")
    print(f"💾 Output  : {out_root}*.jsonl (format={args.output_format}, per_file={args.per_file})")
    if args.no_private_key:
        print("🔒 Secrets : not written to output (--no-private-key)")

    if diff.constrained_chars == 0:
        print("📊 Difficulty: trivial (no extra prefix/suffix constraints beyond HRP)")
    else:
        print(
            f"📊 Difficulty: ~{diff.expected_attempts:,.0f} attempts "
            f"({diff.constrained_chars} constrained char(s); "
            f"prefix+{diff.prefix_extra_chars}, suffix+{diff.suffix_chars})"
        )
        if diff.overlap_warning:
            print("   ⚠️  Prefix and suffix overlap — estimate may be optimistic.")

    print("⏳ Warmup benchmark...", flush=True)
    speed_est = warmup_speed(args.prefix, args.suffix)
    if speed_est > 0 and mode != "mnemonic":
        total = speed_est * args.workers
        line = f"⚡ Est. speed: ~{speed_est:,.0f} addr/sec per worker (up to ~{total:,.0f} total)"
        if diff.expected_attempts > 1:
            line += f" | ETA (mean): ~{format_duration(diff.expected_attempts / total)}"
        print(line)
    print()

    job = Job(
        matcher=make_matcher(args.prefix, args.suffix),
        mode=mode,
        strength=args.strength,
        path=args.path,
        report_every=args.batch,
    )
    try:
        engine = SearchEngine(job, args.workers).start()
        start = time.time()
        while found_count < args.count:
            try:
                found = engine.next_match(timeout=0.5)
            except RuntimeError as e:
                print(f"\n❌ Worker failed: {e}")
                sys.exit(1)
            if found and handle_match(found):
                break
            if not engine.alive():
                print("\n❌ All workers exited unexpectedly")
                sys.exit(1)
            now = time.time()
            if now - last_log >= 1:
                attempts = engine.attempts
                elapsed = now - start
                speed = attempts / elapsed if elapsed > 0 else 0.0
                print(
                    f"\r🔄 Checked: {attempts:,} | ⚡ {speed:,.2f} addr/sec | 🧊 CPU: {get_cpu_temp()}",
                    end="",
                    flush=True,
                )
                last_log = now
    finally:
        if engine is not None:
            engine.stop()
        try:
            out_f.flush()
            out_f.close()
        except Exception:
            pass

    if args.output_format == "json":
        jsonl_files_to_json_arrays(out_root)
        print(f"\n💾 Finalized JSON arrays: {out_root}*.json")

    print(f"\n💾 Done. Saved {found_count} result(s) to {out_root}*.jsonl")


if __name__ == "__main__":
    main()
