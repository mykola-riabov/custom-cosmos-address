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
- Two generation modes:
  - **Fast mode**: random private keys (maximum speed)
  - **Mnemonic mode**: BIP39 + derivation path (deterministic, recoverable)
- Multiprocessing support for address filtering
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

### 2. Fast mode with multiprocessing

```bash
python3 main.py --prefix osmo1abc --batch 200000 --pool --pool-workers 4
```

### 3. Mnemonic (HD wallet) mode

```bash
python3 main.py --prefix cosmos1gpt --mnemonic --strength 256 --count 1
```

### 4. Custom derivation path (mnemonic mode only)

```bash
python3 main.py --prefix inj1zzz --mnemonic --path "m/44'/118'/0'/0/0"
```

---

## Command-Line Arguments (`main.py`)

| Argument | Description | Default |
|--------|-------------|---------|
| `--prefix` | Required address prefix | `osmo1` |
| `--suffix` | Required address suffix | empty |
| `--batch` | Keys generated per iteration | `10000` |
| `--count` | Stop after N matches | `1` |
| `--strength` | Entropy bits (128–256); fast mode expands to 32-byte key | `256` |
| `--mnemonic` | Enable BIP39 mnemonic mode | off |
| `--path` | Derivation path (mnemonic mode) | `m/44'/118'/0'/0/0` |
| `--pool` | Enable multiprocessing | off |
| `--pool-workers` | Worker process count | `2` |
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
{"address":"osmo1…","private_key":"<hex>","mnemonic":"<optional>"}
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

