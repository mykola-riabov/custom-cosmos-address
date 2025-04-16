#!/usr/bin python3
import argparse
import json
import os
import sys
import time
import signal
import numpy as np

# === Check dependencies ===
try:
    import pycuda.autoinit
    import pycuda.driver as cuda
    from pycuda.compiler import SourceModule
    from mnemonic import Mnemonic
    from bip_utils import Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes
    import ecdsa
    import hashlib
    from bech32 import bech32_encode, convertbits
    from temps import get_temps
except ImportError as e:
    print(f"❌ Missing dependency: {e.name}")
    print("💡 Run this to install dependencies:")
    print("   vanity-osmo-install-deps")
    sys.exit(1)

VERSION = "1.0.0"

# === Argument parsing ===
parser = argparse.ArgumentParser()
parser.add_argument("--prefix", type=str, default="osmo1", help="Prefix to match")
parser.add_argument("--suffix", type=str, default="", help="Suffix to match")
parser.add_argument("--batch", type=int, default=100_000, help="Keys per GPU batch")
parser.add_argument("--output", type=str, default="osmo_gpu_found.json", help="Output JSON file")
parser.add_argument("--version", action="store_true", help="Show version and exit")
args = parser.parse_args()

if args.version:
    print(f"vanity-osmo version {VERSION}")
    sys.exit(0)

PREFIX = args.prefix
SUFFIX = args.suffix
BATCH_SIZE = args.batch
OUTPUT_FILE = args.output

# === Load CUDA kernels ===
base_path = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(base_path, "kernel_sha256.cu")) as f1, \
     open(os.path.join(base_path, "kernel_ripemd160.cu")) as f2:
    kernel_code = f1.read() + "\n" + f2.read()

mod = SourceModule(kernel_code, no_extern_c=True)
generate_keys = mod.get_function("generate_keys")

# === Setup
print(f"🚀 Starting GPU vanity search")
print(f"🔹 Prefix : {PREFIX}")
print(f"🔹 Suffix : {SUFFIX or '(none)'}")
print(f"📦 Batch size: {BATCH_SIZE:,}\n")

mnemo = Mnemonic("english")
attempts = 0
start = time.time()
last_log = start
seed_offset = 0
found = False

# === Graceful shutdown handler
def handle_interrupt(signal_received, frame):
    elapsed = time.time() - start
    print(f"\n🛑 Interrupted by user")
    print(f"🔁 Attempts    : {attempts:,}")
    print(f"⚡ Speed       : {attempts / elapsed:,.2f} addr/sec")
    print(f"⏱ Time        : {elapsed:.2f} sec\n")
    sys.exit(0)

signal.signal(signal.SIGINT, handle_interrupt)

# === Main loop
while True:
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

    for priv in host_keys:
        try:
            sk = ecdsa.SigningKey.from_string(priv.tobytes(), curve=ecdsa.SECP256k1)
            vk = sk.get_verifying_key()
            pubkey = b'\x02' + vk.to_string()[:32] if vk.to_string()[-1] % 2 == 0 else b'\x03' + vk.to_string()[:32]
            h1 = hashlib.sha256(pubkey).digest()
            h2 = hashlib.new("ripemd160", h1).digest()
            addr = bech32_encode("osmo", convertbits(h2, 8, 5))

            attempts += 1
            if addr.startswith(PREFIX) and addr.endswith(SUFFIX):
                mnemonic = mnemo.to_mnemonic(priv)
                elapsed = time.time() - start
                print(f"\n\n✅ Found!")
                print(f"🔗 Address     : {addr}")
                print(f"🔐 Private Key : {priv.tobytes().hex()}")
                print(f"🧠 Mnemonic    : {mnemonic}")
                print(f"🔁 Attempts    : {attempts:,}")
                print(f"⚡ Speed       : {attempts / elapsed:,.2f} addr/sec")
                print(f"⏱ Time        : {elapsed:.2f} sec")

                with open(OUTPUT_FILE, "w") as f:
                    json.dump({
                        "address": addr,
                        "private_key": priv.tobytes().hex(),
                        "mnemonic": mnemonic
                    }, f, indent=2)
                    print(f"💾 Saved to {OUTPUT_FILE}")
                found = True
                break
        except Exception:
            continue

    if found:
        break

    now = time.time()
    if now - last_log >= 1:
        speed = attempts / (now - start)
        cpu_temp, gpu_temp = get_temps()
        print(f"\r🔄 Checked: {attempts:,} | ⚡ {speed:,.2f} addr/sec | 🧊 CPU: {cpu_temp} | 🔥 GPU: {gpu_temp}", end="", flush=True)
        last_log = now

