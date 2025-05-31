#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
import signal
import numpy as np
import multiprocessing as mp

try:
    import ecdsa
    import hashlib
    from bech32 import bech32_encode, convertbits
    import GPUtil
    import psutil
except ImportError as e:
    print(f"❌ Missing dependency: {e.name}")
    sys.exit(1)

VERSION = "1.0.4-cpu"
ALLOWED_BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
ALLOWED_STRENGTHS = [128, 160, 192, 224, 256]

# === Argument parser ===
parser = argparse.ArgumentParser(description="CPU vanity address generator for Osmosis (Bech32 format osmo1...)")
parser.add_argument("--prefix", type=str, default="osmo1", help="Address must start with this string.")
parser.add_argument("--suffix", type=str, default="", help="Address must end with this string.")
parser.add_argument("--batch", type=int, default=100_00, help="Keys per batch")
parser.add_argument("--output", type=str, default="osmo_cpu_found.json", help="Output JSON file")
parser.add_argument("--count", type=int, default=1, help="Number of matching addresses to find before stopping")
parser.add_argument("--strength", type=int, default=256, choices=ALLOWED_STRENGTHS, help="Entropy strength in bits")
parser.add_argument("--pool", action="store_true", help="Enable multiprocessing for filtering")
parser.add_argument("--pool-workers", type=int, default=2, help="Number of processes for filtering")
parser.add_argument("--version", action="store_true", help="Show version and exit")
args = parser.parse_args()

if args.version:
    print(f"vanity-osmo (CPU-only) version {VERSION}")
    sys.exit(0)

# === Bech32 validation ===
def check_bech32(part: str):
    return [ch for ch in part if ch not in ALLOWED_BECH32]

prefix_body = args.prefix.replace("osmo1", "")
invalid_chars = set(check_bech32(prefix_body) + check_bech32(args.suffix))
if invalid_chars:
    print(f"❌ Invalid character(s) in --prefix/--suffix: {', '.join(invalid_chars)}")
    print(f"💡 Allowed Bech32 characters: {ALLOWED_BECH32}")
    sys.exit(1)

# === Key generator ===
def generate_keys_cpu(batch_size: int, strength_bits: int):
    return [os.urandom(strength_bits // 8) for _ in range(batch_size)]

# === Temperature display ===
def get_temps():
    cpu_temp = "-"
    try:
        temps = psutil.sensors_temperatures()
        for name in ["k10temp", "coretemp", "acpitz", "cpu_thermal"]:
            entries = temps.get(name)
            if entries:
                cpu_temp = f"{entries[0].current:.1f}°C"
                break
    except Exception:
        pass
    return cpu_temp

# === Key filtering ===
def check_key(priv_bytes: bytes):
    try:
        sk = ecdsa.SigningKey.from_string(priv_bytes, curve=ecdsa.SECP256k1)
        vk = sk.get_verifying_key()
        pubkey = b'\x02' + vk.to_string()[:32] if vk.to_string()[-1] % 2 == 0 else b'\x03' + vk.to_string()[:32]
        h1 = hashlib.sha256(pubkey).digest()
        h2 = hashlib.new("ripemd160", h1).digest()
        addr = bech32_encode("osmo", convertbits(h2, 8, 5))
        if addr.startswith(args.prefix) and addr.endswith(args.suffix):
            return {
                "address": addr,
                "private_key": priv_bytes.hex()
            }
    except Exception:
        pass
    return None

# === Interrupt handler ===
def handle_interrupt(sig, frame):
    if mp.current_process().name != "MainProcess":
        return
    elapsed = time.time() - start
    print(f"\n🛑 Interrupted by user")
    print(f"🔁 Attempts : {attempts:,}")
    print(f"⚡ Speed    : {attempts / elapsed:,.2f} addr/sec")
    print(f"⏱ Time     : {elapsed:.2f} sec\n")
    sys.exit(0)

signal.signal(signal.SIGINT, handle_interrupt)

# === Config ===
PREFIX = args.prefix
SUFFIX = args.suffix
BATCH_SIZE = args.batch
COUNT = args.count
OUTPUT_FILE = args.output
STRENGTH = args.strength
USE_POOL = args.pool
POOL_WORKERS = args.pool_workers

print(f"🚀 Starting CPU vanity search")
print(f"🔹 Prefix  : {PREFIX}")
print(f"🔹 Suffix  : {SUFFIX or '(none)'}")
print(f"🔐 Strength: {STRENGTH} bits")
print(f"📦 Batch   : {BATCH_SIZE:,} keys")
print(f"🔁 Target  : {COUNT} match(es)")
if USE_POOL:
    print(f"🧵 Pool    : enabled with {POOL_WORKERS} process(es)\n")

# === Main loop ===
attempts = 0
start = time.time()
last_log = start
found = []

while len(found) < COUNT:
    keys = generate_keys_cpu(BATCH_SIZE, STRENGTH)
    attempts += len(keys)

    if USE_POOL:
        with mp.Pool(processes=POOL_WORKERS) as pool:
            for result in pool.imap_unordered(check_key, keys):
                if result:
                    found.append(result)
                    print(f"\n✅ Found!")
                    print(f"🔗 Address     : {result['address']}")
                    print(f"🔐 Private Key : {result['private_key']}")
                    if len(found) >= COUNT:
                        break
    else:
        for priv in keys:
            result = check_key(priv)
            if result:
                found.append(result)
                print(f"\n✅ Found!")
                print(f"🔗 Address     : {result['address']}")
                print(f"🔐 Private Key : {result['private_key']}")
                if len(found) >= COUNT:
                    break

    now = time.time()
    if now - last_log >= 1:
        speed = attempts / (now - start)
        cpu_temp = get_temps()
        print(f"\r🔄 Checked: {attempts:,} | ⚡ {speed:,.2f} addr/sec | 🧊 CPU: {cpu_temp}", end="", flush=True)
        last_log = now

with open(OUTPUT_FILE, "w") as f:
    json.dump(found, f, indent=2)
print(f"\n💾 Saved {len(found)} result(s) to {OUTPUT_FILE}")

