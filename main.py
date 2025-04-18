#!/usr/bin/python3
import argparse
import json
import os
import sys
import time
import signal
import numpy as np
import multiprocessing as mp

try:
    import pycuda.autoinit
    import pycuda.driver as cuda
    from pycuda.compiler import SourceModule
    import ecdsa
    import hashlib
    from bech32 import bech32_encode, convertbits
    import GPUtil
    import psutil
except ImportError as e:
    print(f"❌ Missing dependency: {e.name}")
    print("💡 Run this to install dependencies:\n   vanity-osmo-install-deps")
    sys.exit(1)

# === Embedded get_temps ===
def get_temps():
    cpu_temp = "-"
    gpu_temp = "-"
    try:
        temps = psutil.sensors_temperatures()
        for name in ["k10temp", "coretemp", "acpitz", "cpu_thermal"]:
            entries = temps.get(name)
            if entries:
                cpu_temp = f"{entries[0].current:.1f}°C"
                break
    except Exception:
        pass
    try:
        gpus = GPUtil.getGPUs()
        if gpus:
            gpu_temp = f"{gpus[0].temperature}°C"
    except Exception:
        pass
    return cpu_temp, gpu_temp

VERSION = "1.0.3"
ALLOWED_BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
ALLOWED_STRENGTHS = [128, 160, 192, 224, 256]

parser = argparse.ArgumentParser(description="GPU vanity address generator for Osmosis (Bech32 format osmo1...)")
parser.add_argument("--prefix", type=str, default="osmo1", help="Address must start with this string.")
parser.add_argument("--suffix", type=str, default="", help="Address must end with this string.")
parser.add_argument("--batch", type=int, default=100_00, help="Keys per GPU batch")
parser.add_argument("--output", type=str, default="osmo_gpu_found.json", help="Output JSON file")
parser.add_argument("--count", type=int, default=1, help="Number of matching addresses to find before stopping")
parser.add_argument("--strength", type=int, default=256, choices=ALLOWED_STRENGTHS,
                    help="Entropy strength in bits (choices: 128, 160, 192, 224, 256). Default: 256")
parser.add_argument("--version", action="store_true", help="Show version and exit")
parser.add_argument("--list-gpus", action="store_true", help="List available GPUs and exit")
parser.add_argument("--benchmark", action="store_true", help="Run in benchmark mode and exit")
parser.add_argument("--pool", action="store_true", help="Enable multiprocessing on CPU for address filtering")
parser.add_argument("--pool-workers", type=int, default=2, help="Number of CPU processes for filtering (default: 2)")
args = parser.parse_args()

if args.version:
    print(f"vanity-osmo version {VERSION}")
    sys.exit(0)

if args.list_gpus:
    print("🖥 Available GPUs:")
    for gpu in GPUtil.getGPUs():
        print(f" - ID {gpu.id}: {gpu.name}, {gpu.memoryTotal}MB VRAM")
    sys.exit(0)

def check_bech32(part: str):
    return [ch for ch in part if ch not in ALLOWED_BECH32]

prefix_body = args.prefix.replace("osmo1", "")
invalid_chars = set(check_bech32(prefix_body) + check_bech32(args.suffix))
if invalid_chars:
    print(f"❌ Invalid character(s) in --prefix/--suffix: {', '.join(invalid_chars)}")
    print(f"💡 Allowed Bech32 characters: {ALLOWED_BECH32}")
    sys.exit(1)

# === Benchmark mode
if args.benchmark:
    print("🧪 Benchmarking...")
    BATCH_SIZE = args.batch
    seed_offset = 0
    keys_gpu = cuda.mem_alloc(32 * BATCH_SIZE)
    hashes_gpu = cuda.mem_alloc(32 * BATCH_SIZE)
    threads = 256
    blocks = (BATCH_SIZE + threads - 1) // threads

    base_path = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base_path, "kernel_sha256.cu")) as f1, open(os.path.join(base_path, "kernel_ripemd160.cu")) as f2:
        kernel_code = f1.read() + "\n" + f2.read()

    mod = SourceModule(kernel_code, no_extern_c=True)
    generate_keys = mod.get_function("generate_keys")

    start = time.time()
    generate_keys(keys_gpu, hashes_gpu, np.int32(BATCH_SIZE), np.uint32(seed_offset),
                  block=(threads, 1, 1), grid=(blocks, 1))
    cuda.Context.synchronize()
    elapsed = time.time() - start
    print(f"✅ Benchmark done: {BATCH_SIZE / elapsed:,.2f} addr/sec in {elapsed:.2f} sec")
    sys.exit(0)

# === Config
PREFIX = args.prefix
SUFFIX = args.suffix
BATCH_SIZE = args.batch
OUTPUT_FILE = args.output
COUNT = args.count
STRENGTH = args.strength
USE_POOL = args.pool
POOL_WORKERS = args.pool_workers

base_path = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(base_path, "kernel_sha256.cu")) as f1, open(os.path.join(base_path, "kernel_ripemd160.cu")) as f2:
    kernel_code = f1.read() + "\n" + f2.read()

mod = SourceModule(kernel_code, no_extern_c=True)
generate_keys = mod.get_function("generate_keys")

print(f"🚀 Starting GPU vanity search")
print(f"🔹 Prefix : {PREFIX}")
print(f"🔹 Suffix : {SUFFIX or '(none)'}")
print(f"🔐 Strength: {STRENGTH} bits")
print(f"📦 Batch   : {BATCH_SIZE:,} keys")
print(f"🔁 Target  : {COUNT} match(es)")
if USE_POOL:
    print(f"🧵 Pool    : enabled with {POOL_WORKERS} process(es)\n")

attempts = 0
start = time.time()
last_log = start
seed_offset = 0
found = []

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

def check_key(priv_bytes: bytes):
    try:
        sk = ecdsa.SigningKey.from_string(priv_bytes, curve=ecdsa.SECP256k1)
        vk = sk.get_verifying_key()
        pubkey = b'\x02' + vk.to_string()[:32] if vk.to_string()[-1] % 2 == 0 else b'\x03' + vk.to_string()[:32]
        h1 = hashlib.sha256(pubkey).digest()
        h2 = hashlib.new("ripemd160", h1).digest()
        addr = bech32_encode("osmo", convertbits(h2, 8, 5))
        if addr.startswith(PREFIX) and addr.endswith(SUFFIX):
            return {
                "address": addr,
                "private_key": priv_bytes.hex()
            }
    except Exception:
        pass
    return None

while len(found) < COUNT:
    keys_gpu = cuda.mem_alloc(32 * BATCH_SIZE)
    hashes_gpu = cuda.mem_alloc(32 * BATCH_SIZE)
    host_keys = np.empty((BATCH_SIZE, 32), dtype=np.uint8)

    threads = 256
    blocks = (BATCH_SIZE + threads - 1) // threads
    generate_keys(keys_gpu, hashes_gpu, np.int32(BATCH_SIZE), np.uint32(seed_offset),
                  block=(threads, 1, 1), grid=(blocks, 1))
    cuda.Context.synchronize()
    seed_offset += BATCH_SIZE
    cuda.memcpy_dtoh(host_keys, keys_gpu)

    keys = [bytes(priv) for priv in host_keys]
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
        cpu_temp, gpu_temp = get_temps()
        print(f"\r🔄 Checked: {attempts:,} | ⚡ {speed:,.2f} addr/sec | 🧊 CPU: {cpu_temp} | 🔥 GPU: {gpu_temp}", end="", flush=True)
        last_log = now

with open(OUTPUT_FILE, "w") as f:
    json.dump(found, f, indent=2)
print(f"\n💾 Saved {len(found)} result(s) to {OUTPUT_FILE}")

