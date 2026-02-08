#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
import signal
import multiprocessing as mp

try:
    import ecdsa
    import hashlib
    from bech32 import bech32_encode, convertbits
    from mnemonic import Mnemonic
    from bip32 import BIP32
    import psutil
except ImportError as e:
    print(f"❌ Missing dependency: {e.name}")
    sys.exit(1)

VERSION = "1.0.7-cpu"
HARDENED_OFFSET = 0x80000000
ALLOWED_BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
ALLOWED_STRENGTHS = [128, 160, 192, 224, 256]

# =============================================================================
# Args
# =============================================================================
parser = argparse.ArgumentParser(
    description="custom-cosmos is a CPU custom address generator for Cosmos-based chains.",
    formatter_class=argparse.RawTextHelpFormatter
)

parser.add_argument("--prefix", type=str, default="osmo1", help="Address must start with this string. Default: osmo1")
parser.add_argument("--suffix", type=str, default="", help="Address must end with this string.")
parser.add_argument("--batch", type=int, default=10_000, help="Keys per CPU batch")

parser.add_argument("--output", type=str, default="addr_list.jsonl",
                    help="Output base filename. Recommended: .jsonl (streaming).")
parser.add_argument("--output-format", choices=["jsonl", "json"], default="jsonl",
                    help="Write JSONL (streaming) or finalize JSON arrays from JSONL at end. Default: jsonl")
parser.add_argument("--per-file", type=int, default=0,
                    help="Rotate output after N FOUND results per file. 0 = single file.")

parser.add_argument("--count", type=int, default=1, help="Number of matching addresses to find before stopping")
parser.add_argument("--strength", type=int, default=256, choices=ALLOWED_STRENGTHS, help="Entropy strength in bits")
parser.add_argument("--pool", action="store_true", help="Enable multiprocessing for filtering")
parser.add_argument("--pool-workers", type=int, default=2, help="Number of CPU processes for filtering")
parser.add_argument("--mnemonic", action="store_true", help="Generate from BIP39 mnemonic instead of random key")
parser.add_argument("--path", type=str, default="m/44'/118'/0'/0/0", help="Derivation path for --mnemonic")
parser.add_argument("--version", action="store_true", help="Print version and exit")
args = parser.parse_args()

if args.version:
    print(f"custom-cosmos (CPU-only) version {VERSION}")
    sys.exit(0)

if args.per_file < 0:
    print("❌ --per-file must be >= 0")
    sys.exit(1)

# =============================================================================
# Bech32 validation
# =============================================================================
def check_bech32(part: str):
    return [ch for ch in part if ch not in ALLOWED_BECH32]

prefix_body = args.prefix.split("1", 1)[-1]
invalid_chars = set(check_bech32(prefix_body) + check_bech32(args.suffix))
if invalid_chars:
    print(f"❌ Invalid character(s) in --prefix/--suffix: {', '.join(invalid_chars)}")
    print(f"💡 Allowed Bech32 characters: {ALLOWED_BECH32}")
    sys.exit(1)

# =============================================================================
# Mnemonic derivation
# =============================================================================
def mnemonic_to_privkey(strength_bits: int, derivation_path: str):
    mnemo = Mnemonic("english")
    entropy_bytes = os.urandom(strength_bits // 8)
    words = mnemo.to_mnemonic(entropy_bytes)
    seed = mnemo.to_seed(words)

    bip32 = BIP32.from_seed(seed)
    path = derivation_path.lstrip("m/").split("/")
    path = [int(p.replace("'", "")) + HARDENED_OFFSET if "'" in p else int(p) for p in path]

    privkey = bip32.get_privkey_from_path(path)  # 32 bytes
    return privkey, words

# =============================================================================
# Random privkey generator (FIX)
# - strength controls input entropy, but output private key MUST be 32 bytes.
# - ensure 1 <= priv_int < curve_order
# =============================================================================
_CURVE_ORDER = ecdsa.SECP256k1.order

def random_privkey_from_entropy(strength_bits: int) -> bytes:
    """
    Produce a valid 32-byte secp256k1 private key from strength_bits of entropy.
    For strength_bits < 256 we expand entropy deterministically using SHA256.
    """
    if strength_bits not in ALLOWED_STRENGTHS:
        raise ValueError("Invalid strength_bits")

    nbytes = strength_bits // 8

    while True:
        raw = os.urandom(nbytes)

        # Expand to 32 bytes if needed
        if len(raw) != 32:
            raw = hashlib.sha256(raw).digest()  # 32 bytes

        priv_int = int.from_bytes(raw, "big")
        if 1 <= priv_int < _CURVE_ORDER:
            return raw

def generate_keys_cpu(batch_size: int, strength_bits: int):
    if args.mnemonic:
        keys = []
        mnemonics = []
        for _ in range(batch_size):
            privkey, words = mnemonic_to_privkey(strength_bits, args.path)
            keys.append(privkey)
            mnemonics.append(words)
        return keys, mnemonics
    else:
        # IMPORTANT: always 32-byte privkeys (secp256k1 requirement)
        return [random_privkey_from_entropy(strength_bits) for _ in range(batch_size)], None

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

# =============================================================================
# Address check
# =============================================================================
def _addr_from_priv(priv_bytes: bytes) -> str | None:
    try:
        # priv_bytes must be 32 bytes here
        sk = ecdsa.SigningKey.from_string(priv_bytes, curve=ecdsa.SECP256k1)
        vk = sk.get_verifying_key()
        pub_raw = vk.to_string()
        pubkey = (b"\x02" + pub_raw[:32]) if (pub_raw[-1] % 2 == 0) else (b"\x03" + pub_raw[:32])
        h1 = hashlib.sha256(pubkey).digest()
        h2 = hashlib.new("ripemd160", h1).digest()
        hrp = args.prefix.split("1")[0]
        addr = bech32_encode(hrp, convertbits(h2, 8, 5))
        if addr.startswith(args.prefix) and addr.endswith(args.suffix):
            return addr
    except Exception:
        pass
    return None

def check_key_indexed(item: tuple[int, bytes]) -> tuple[int, str | None]:
    idx, priv_bytes = item
    return (idx, _addr_from_priv(priv_bytes))

# =============================================================================
# Streaming output with rotation (NO RAM growth)
# =============================================================================
def _split_name(path: str):
    root, ext = os.path.splitext(path)
    return root, ext or ".jsonl"

out_root, _ = _split_name(args.output)

def make_part_path(part_idx: int) -> str:
    if args.per_file > 0:
        return f"{out_root}_{part_idx:03d}.jsonl"
    return f"{out_root}.jsonl"

current_part = 1
current_path = make_part_path(current_part)
os.makedirs(os.path.dirname(current_path) or ".", exist_ok=True)

out_f = open(current_path, "a", encoding="utf-8")
written_in_part = 0
written_total = 0

def rotate_if_needed():
    global current_part, current_path, out_f, written_in_part
    if args.per_file <= 0:
        return
    if written_in_part < args.per_file:
        return
    out_f.flush()
    out_f.close()
    current_part += 1
    current_path = make_part_path(current_part)
    out_f = open(current_path, "a", encoding="utf-8")
    written_in_part = 0

def write_jsonl(obj: dict):
    out_f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def jsonl_files_to_json_arrays():
    import glob as _glob
    pattern = f"{out_root}*.jsonl"
    for jsonl_path in sorted(_glob.glob(pattern)):
        array_path = os.path.splitext(jsonl_path)[0] + ".json"
        with open(jsonl_path, "r", encoding="utf-8") as fin, open(array_path, "w", encoding="utf-8") as fout:
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

# =============================================================================
# Interrupt handler
# =============================================================================
attempts = 0
start = time.time()
last_log = start

def handle_interrupt(sig, frame):
    if mp.current_process().name != "MainProcess":
        return
    elapsed = time.time() - start
    print(f"\n🛑 Interrupted by user")
    print(f"🔁 Attempts : {attempts:,}")
    print(f"⚡ Speed    : {attempts / elapsed:,.2f} addr/sec")
    print(f"⏱ Time     : {elapsed:.2f} sec\n")
    try:
        out_f.flush()
        out_f.close()
    except Exception:
        pass
    sys.exit(0)

signal.signal(signal.SIGINT, handle_interrupt)

# =============================================================================
# Info
# =============================================================================
print(f"🚀 Start searching for a custom address")
print(f"🔹 Prefix  : {args.prefix}")
print(f"🔹 Suffix  : {args.suffix or '(none)'}")
print(f"🔐 Strength: {args.strength} bits ({'BIP39 entropy' if args.mnemonic else 'entropy input; privkey=32 bytes'})")
print(f"📦 Batch   : {args.batch:,} keys")
print(f"🔁 Target  : {args.count} match(es)")
print(f"🧠 Mnemonic: {'enabled' if args.mnemonic else 'disabled'}")
if args.mnemonic:
    print(f"📍 Path    : {args.path}")
if args.pool:
    print(f"🧵 Pool    : enabled with {args.pool_workers} process(es)")
print(f"💾 Output  : {out_root}*.jsonl (format={args.output_format}, per_file={args.per_file})")
print("")

# =============================================================================
# Main loop
# =============================================================================
found_count = 0

try:
    while found_count < args.count:
        keys, mnemonics = generate_keys_cpu(args.batch, args.strength)
        attempts += len(keys)

        if args.pool:
            with mp.Pool(processes=args.pool_workers) as pool:
                for idx, addr in pool.imap_unordered(check_key_indexed, enumerate(keys), chunksize=256):
                    if not addr:
                        continue

                    priv = keys[idx]
                    rec = {"address": addr, "private_key": priv.hex()}
                    if args.mnemonic and mnemonics is not None:
                        rec["mnemonic"] = mnemonics[idx]

                    write_jsonl(rec)
                    found_count += 1
                    written_total += 1
                    written_in_part += 1
                    rotate_if_needed()

                    print(f"\n✅ Found! {found_count}/{args.count}")
                    print(f"🔗 Address     : {rec['address']}")
                    print(f"🔐 Private Key : {rec['private_key']}")
                    if args.mnemonic:
                        print(f"🧠 Mnemonic    : {rec['mnemonic']}")
                    if found_count >= args.count:
                        break
        else:
            for idx, priv in enumerate(keys):
                addr = _addr_from_priv(priv)
                if not addr:
                    continue

                rec = {"address": addr, "private_key": priv.hex()}
                if args.mnemonic and mnemonics is not None:
                    rec["mnemonic"] = mnemonics[idx]

                write_jsonl(rec)
                found_count += 1
                written_total += 1
                written_in_part += 1
                rotate_if_needed()

                print(f"\n✅ Found! {found_count}/{args.count}")
                print(f"🔗 Address     : {rec['address']}")
                print(f"🔐 Private Key : {rec['private_key']}")
                if args.mnemonic:
                    print(f"🧠 Mnemonic    : {rec['mnemonic']}")
                if found_count >= args.count:
                    break

        now = time.time()
        if now - last_log >= 1:
            speed = attempts / (now - start)
            cpu_temp = get_temps()
            print(f"\r🔄 Checked: {attempts:,} | ⚡ {speed:,.2f} addr/sec | 🧊 CPU: {cpu_temp}", end="", flush=True)
            last_log = now

finally:
    try:
        out_f.flush()
        out_f.close()
    except Exception:
        pass

if args.output_format == "json":
    jsonl_files_to_json_arrays()
    print(f"\n💾 Finalized JSON arrays: {out_root}*.json")

print(f"\n💾 Done. Saved {found_count} result(s) to {out_root}*.jsonl")

