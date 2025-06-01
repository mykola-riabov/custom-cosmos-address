# 🧪 custom-osmo-address (CPU-only)

**custom-osmo-address** is a fast custom address generator for the **Osmosis blockchain** (`osmo1...`) that runs **entirely on the CPU**, with optional multiprocessing for filtering.

---

## 🚀 Features

- ✅ Generate Osmosis addresses with custom prefix and/or suffix
- 🔐 Configurable entropy strength (128–256 bits)
- 🧵 Optional CPU multiprocessing for address filtering
- 🔥 Real-time speed and CPU temperature display
- 💾 Save results as JSON

---

## 🧰 Requirements

- Python 3.8+
- Install dependencies:

```bash
pip install -r requirements.txt
```

---

## 💻 Example Usage

```bash
python3 main.py --prefix osmo1aaa --batch 100000 --pool --pool-workers 4
```

---

## 🔧 Command-Line Arguments

| Option            | Description |
|-------------------|-------------|
| `--prefix`        | Address must start with this string |
| `--suffix`        | Address must end with this string |
| `--batch`         | Keys per CPU batch |
| `--count`         | Number of matching addresses to find |
| `--strength`      | Key entropy strength: 128–256 bits |
| `--output`        | Output file (default: `osmo_cpu_found.json`) |
| `--pool`          | Enable multiprocessing for filtering |
| `--pool-workers`  | Number of CPU processes (default: 2) |
| `--version`       | Print version and exit |

---

## 📈 Example Output

```
✅ Found!
🔗 Address     : osmo1aaa...
🔐 Private Key : abcd1234...
🔁 Attempts    : 1,000,000
⚡ Speed       : 12,345.67 addr/sec
🧊 CPU         : 54.2°C
💾 Saved 1 result(s) to osmo_cpu_found.json
```

---

## 📤 Uninstall

Simply delete the project files. No installation is required.
