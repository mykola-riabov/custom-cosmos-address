# 🧪 vanity-osmo

**vanity-osmo** is a blazing-fast vanity address generator for the **Osmosis blockchain** (`osmo1...`).  
It uses **GPU acceleration via CUDA** and optionally **parallel CPU filtering**.

---

## 🚀 Features

- ✅ Generate Osmosis addresses with custom prefix and/or suffix  
- ⚡ GPU-accelerated with PyCUDA  
- 🧵 Optional CPU multiprocessing for filtering (via `--pool`)  
- 🔐 Control key entropy strength (128–256 bits)  
- 🔥 Real-time speed and temperature display (CPU/GPU)  
- 🧠 Optional mnemonic support (can be disabled)

---

## 🧰 Requirements

- Python 3.8+
- CUDA-compatible GPU (NVIDIA)
- PyCUDA (`pip install pycuda`)
- Other dependencies listed in `requirements.txt`

Install all requirements:

```bash
pip install -r requirements.txt
```

---

## 💻 Usage

```bash
vanity-osmo --prefix osmo1aaa --batch 200000
```

### Arguments

| Option             | Description |
|--------------------|-------------|
| `--prefix`         | Address must start with this string |
| `--suffix`         | Address must end with this string |
| `--batch`          | Keys per GPU batch |
| `--count`          | Stop after finding N matches (default: 1) |
| `--output`         | Save result JSON file (default: `osmo_gpu_found.json`) |
| `--strength`       | Key entropy strength: 128, 160, 192, 224, 256 (default: 256) |
| `--pool`           | Enable multiprocessing (CPU) for address filtering |
| `--pool-workers`   | Number of CPU processes if `--pool` is enabled (default: 2) |
| `--list-gpus`      | Show available GPUs |
| `--benchmark`      | Measure GPU key generation speed |
| `--version`        | Print version and exit |

---

## 🧪 Example Output

```
✅ Found!
🔗 Address     : osmo1aaa8xyh...
🔐 Private Key : 0c32bc12...
🔁 Attempts    : 45,172
⚡ Speed       : 3,000.21 addr/sec
⏱ Time        : 15.06 sec
💾 Saved 1 result(s) to osmo_gpu_found.json
```

---

## 📦 Build `.deb` installer (optional)

You can package this project as a Debian `.deb` file for easy distribution.

### 1. Prepare structure

```bash
mkdir -p vanity-osmo_1.0.3/DEBIAN
mkdir -p vanity-osmo_1.0.3/usr/bin
mkdir -p vanity-osmo_1.0.3/opt/vanity-osmo
```

### 2. Copy project files

```bash
cp main.py kernel_*.cu requirements.txt vanity-osmo_1.0.3/opt/vanity-osmo/
```

### 3. Add executable wrapper

```bash
cat <<EOF > vanity-osmo_1.0.3/usr/bin/vanity-osmo
#!/bin/bash
python3 /opt/vanity-osmo/main.py "\$@"
EOF

chmod +x vanity-osmo_1.0.3/usr/bin/vanity-osmo
```

### 4. Create control file

```bash
cat <<EOF > vanity-osmo_1.0.3/DEBIAN/control
Package: vanity-osmo
Version: 1.0.3
Section: utils
Priority: optional
Architecture: all
Maintainer: Your Name <you@example.com>
Description: GPU vanity address generator for Osmosis
EOF
```

### 5. Add post-install script (optional)

```bash
cat <<EOF > vanity-osmo_1.0.3/DEBIAN/postinst
#!/bin/bash
pip3 install -r /opt/vanity-osmo/requirements.txt
exit 0
EOF

chmod +x vanity-osmo_1.0.3/DEBIAN/postinst
```

### 6. Build the `.deb`

```bash
dpkg-deb --build vanity-osmo_1.0.3
```

---

## 📥 Install & Use

```bash
sudo dpkg -i vanity-osmo_1.0.3.deb
vanity-osmo --prefix osmo1abc --pool --pool-workers 4
```

---

## 📤 Uninstall

```bash
sudo dpkg -r vanity-osmo
```
