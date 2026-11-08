# custom-cosmos-address (CPU-only)

`custom-cosmos-address` is a **CPU-based utility** for generating Cosmos SDK–compatible Bech32 addresses with a desired **prefix** and/or **suffix** (vanity addresses). It supports fast random-key generation as well as deterministic HD wallets via **BIP39 mnemonics** and derivation paths.

> ⚠️ **SECURITY WARNING**
> This tool **writes private keys** (and optionally **mnemonics**) to output files. These files are extremely sensitive.
> **Never commit them to Git, never upload them to cloud storage, and never share them publicly.**

---

## Features

- Generate Cosmos addresses (`osmo1…`, `cosmos1…`, `inj1…`, etc.)
- Vanity matching by:
  - `--prefix` (address must start with a given string)
  - `--suffix` (address must end with a given string)
- Three generation modes:
  - **Fast mode**: random private keys (maximum speed)
  - **Mnemonic mode**: a new BIP39 phrase per attempt (slow: PBKDF2 with 2048 rounds per phrase)
  - **Index search** (`--mnemonic --index-search`): one BIP39 phrase per worker, then the last
    path index 0, 1, 2… — as fast as fast mode and still recoverable from the phrase; the found
    path (for example `m/44'/118'/0'/0/1749`) is saved with the result
- Parallel workers: each worker process generates, derives and checks keys on its own; only
  matches cross processes, so speed grows with the number of workers (default: CPU count)
- Elliptic-curve math through the system **libsecp256k1** (the library Bitcoin Core uses) when it
  is installed, pure-Python `ecdsa` otherwise
- Streaming output (low memory usage)
- Output formats:
  - **JSONL** (default, recommended)
  - **JSON array** (optional)
- Output file rotation by number of found results
- Difficulty estimate and warmup benchmark at startup
- `--no-private-key` for address-only output
- Secure output files (`chmod 600`) and append warnings
- Shared `cosmos_address` module + unit tests

---

## Requirements

- Python **3.10+** recommended
- Dependencies listed in `requirements.txt` (`pycryptodome` provides RIPEMD160 on OpenSSL 3 systems)
- Recommended: `sudo apt install libsecp256k1-6` (or the `libsecp256k1-*` runtime of your release).
  Without it the program works through pure-Python `ecdsa`, about ten times slower per core.
  `SECP256K1_LIBRARY=/path/libsecp256k1.so` picks a library, `SECP256K1_DISABLE=1` forces the fallback.

Measured on a 16-thread desktop CPU (prefix search, 2026-11-08):

| Mode | 1.3.5 (1 process) | 1.4.0, 1 worker | 1.4.0, 16 workers |
|------|------------------:|----------------:|------------------:|
| Fast (random key) | 2,600/s | 25,700/s | 213,000/s |
| Index search | — | 22,900/s | 198,000/s |
| Mnemonic (new phrase each time) | 630/s | 1,200/s | 9,000/s |

In 1.3.5 the Workers value was used only with the Multiprocessing box, and even then only the
address check ran in the pool while one process generated every key: random-key mode reached about
20,000/s on 16 workers, and in mnemonic mode the workers waited for the single generator.

Install dependencies:

```bash
pip install -r requirements.txt
# optional: tests
pip install -r requirements-dev.txt
pytest
```

---

## Quick Start

### 1. Fast vanity address search (random private keys)

```bash
python3 main.py --prefix osmo1abc --suffix xyz --batch 100000 --count 1
```

### 2. Choose the number of workers

```bash
python3 main.py --prefix osmo1abc --workers 8
```

### 3. Mnemonic (HD wallet) mode

```bash
python3 main.py --prefix cosmos1gpt --mnemonic --strength 256 --count 1
```

Fast and recoverable — one phrase per worker, the address index is searched:

```bash
python3 main.py --prefix cosmos1gpt --mnemonic --index-search --count 1
```

Write down the phrase **and** the saved `path`. In Keplr: import the phrase, open
*Advanced* → HD path and set the address index (the last number of the path).

### 4. Custom derivation path (mnemonic mode only)

```bash
python3 main.py --prefix inj1zzz --mnemonic --path "m/44'/118'/0'/0/0"
```

### 5. Desktop GUI

```bash
python3 -m gui
# or after pip install -e .:
cosmos-vanity-gui
```

The GUI uses the same `cosmos_address` engine as the CLI (PySide6 / Qt 6).

**Workspace folder** — choose once in the sidebar (**WORKSPACE → Choose…**). Everything stays under one directory (saved between sessions):

```
~/custom-cosmos-address/     ← default
├── generated/               ← generator output (*.jsonl)
│   └── addr_list.jsonl
├── found_wallets/           ← scanner: wallets with balance
└── checked_cache.json       ← scanner resume cache
```

Generator and scanner paths stay in sync — no separate file pickers.

Use the **Theme** selector in the sidebar to switch palettes (21 built-in themes).

### 6. Install from `.deb` (Debian / Ubuntu / Kali)

Build the package (requires `python3-venv`, `fakeroot`, and `dpkg-deb`):

```bash
sudo apt install python3-venv fakeroot
./scripts/build-deb.sh
```

Install the generated package:

```bash
sudo apt install ./dist/custom-cosmos-address_*.deb
```

This installs:

| Command | Purpose |
|---------|---------|
| `cosmos-vanity-gui` | Desktop GUI (also in application menu) |
| `cosmos-vanity` | CLI generator |
| `cosmos-scan` | Balance scanner |

Runtime dependencies: `python3 (>= 3.10)` and `libxcb-cursor0`. Python libraries are bundled inside the package.

Launch the GUI from the terminal or find **Custom Cosmos Address** in your desktop application menu.

Uninstall:

```bash
sudo apt remove custom-cosmos-address
```

---

## Command-Line Arguments (`main.py`)

| Argument | Description | Default |
|--------|-------------|---------|
| `--prefix` | Required address prefix | `osmo1` |
| `--suffix` | Required address suffix | empty |
| `--batch` | Keys each worker checks between progress reports and stop checks | `500` |
| `--count` | Stop after N matches | `1` |
| `--strength` | Entropy bits (128–256); fast mode expands to 32-byte key | `256` |
| `--mnemonic` | Enable BIP39 mnemonic mode | off |
| `--path` | Derivation path (mnemonic mode) | `m/44'/118'/0'/0/0` |
| `--index-search` | With `--mnemonic`: scan the last path index of one phrase per worker | off |
| `--workers` | Worker processes (`--pool-workers` still accepted; `--pool` is ignored) | CPU count |
| `--no-private-key` | Write address only (no secrets in output) | off |
| `--force-output` | Append without confirmation if output exists | off |
| `--output` | Base output filename | `addr_list.jsonl` |
| `--output-format` | `jsonl` or `json` | `jsonl` |
| `--per-file` | Rotate file after N results (0 = single file) | `0` |
| `--version` | Print version and exit | — |

---

## Output Format

### JSONL (default)

Each line is a standalone JSON object:

```json
{"address":"osmo1…","private_key":"<hex>","mnemonic":"<optional>","path":"<mnemonic modes>"}
```

Advantages:
- Stream-safe
- Low memory usage
- Ideal for large searches

### JSON array (`--output-format json`)

A single JSON array containing all results (built from streamed data).

---

## BIP39 Entropy Reference (Mnemonic Mode)

| Entropy | Words |
|--------|-------|
| 128-bit | 12 |
| 160-bit | 15 |
| 192-bit | 18 |
| 224-bit | 21 |
| 256-bit | 24 |

---

## Osmosis Balance Scanner (`scan.py`)

`scan.py` scans generated addresses for balances using a Cosmos LCD endpoint (e.g. Osmosis).

### Run

```bash
python3 scan.py
```

### Environment Variables

| Variable | Description | Default |
|--------|-------------|---------|
| `LCD_ENDPOINT` | LCD API endpoint | `https://lcd-osmosis.keplr.app` |
| `DENOM` | Token denom | `uosmo` |
| `INPUT_GLOB` | Input wallet files | `*.jsonl` |
| `NUM_WORKERS` | Parallel HTTP workers | `20` |
| `HTTP_TIMEOUT` | Request timeout (sec) | `10` |
| `HTTP_RETRIES` | Retry count | `2` |
| `RESULT_DIR` | Output directory | `found_wallets` |
| `CACHE_FILE` | Checked-address cache | `checked_cache.json` |

Example:

```bash
export INPUT_GLOB="addr_list*.jsonl"
export NUM_WORKERS=50
python3 scan.py
```

### Scanner Output

- `found_wallets/found_from_<file>.jsonl` — addresses with balance > 0
- `found_wallets/found_from_<file>.json` — JSON array version
- `found_wallets/errors_from_<file>.log` — request errors
- `checked_cache.json` — cache of successfully checked addresses

---

## Git Safety

The repository `.gitignore` already excludes wallet output files. **Never commit** `*.jsonl`, `found_wallets/`, or `checked_cache.json`.

---

## Legal & Ethical Notice

This software is intended for **educational, research, and personal wallet management purposes only** (e.g. vanity address generation for your own keys, auditing your own datasets, recovery testing).

You are solely responsible for complying with applicable laws and regulations in your jurisdiction.

---

