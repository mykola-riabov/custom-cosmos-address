# 🧪 vanity-osmo

**vanity-osmo** is a blazing-fast vanity address generator for the **Osmosis blockchain** (`osmo1...`).  
It uses **GPU acceleration via CUDA** and supports matching prefixes and suffixes.

---

## 🚀 Features

- ✅ Generate Osmosis addresses with custom prefix and/or suffix  
- ⚡ GPU-accelerated using PyCUDA + SHA256 + RIPEMD160  
- 🔥 Real-time speed and temperature display (CPU/GPU)  
- 📦 Installable via `.deb` package  
- 🧠 Output includes mnemonic, private key, and address  
- 🛑 Graceful exit with `Ctrl+C`  

---

## 🧰 Requirements

- Python 3.8+
- CUDA-compatible GPU (NVIDIA)
- PyCUDA (`pip install pycuda`)
- Other Python dependencies (see `requirements.txt`)

Install all requirements:

```bash
pip install -r requirements.txt
```

---

## 💻 Usage

Once installed:

```bash
vanity-osmo --prefix osmo1aaa --batch 200000
```

### Arguments

| Option       | Description                          |
|--------------|--------------------------------------|
| `--prefix`   | Address must start with this string  |
| `--suffix`   | Address must end with this string    |
| `--batch`    | Number of keys to generate per GPU batch |
| `--output`   | Where to save result JSON (default: `osmo_gpu_found.json`) |

---

## 🧪 Example Output

```
✅ Found!
🔗 Address     : osmo1aaa4v3smu4n9...
🔐 Private Key : abc123...
🧠 Mnemonic    : pause honey canoe ...
🔁 Attempts    : 28,376
⚡ Speed       : 3,112.43 addr/sec
⏱ Time        : 9.11 sec
💾 Saved to osmo_gpu_found.json
```

---

## 📦 Build `.deb` installer (for Debian/Ubuntu)

### 1. Create directory structure

```bash
mkdir -p vanity-osmo_1.0.0/DEBIAN
mkdir -p vanity-osmo_1.0.0/usr/bin
mkdir -p vanity-osmo_1.0.0/opt/vanity-osmo
```

### 2. Copy files into package

```bash
cp main.py kernel_*.cu temps.py requirements.txt vanity-osmo_1.0.0/opt/vanity-osmo/
```

### 3. Create executable launcher

```bash
cat <<EOF > vanity-osmo_1.0.0/usr/bin/vanity-osmo
#!/bin/bash
python3 /opt/vanity-osmo/main.py "\$@"
EOF

chmod +x vanity-osmo_1.0.0/usr/bin/vanity-osmo
```

### 4. Create control file

```bash
cat <<EOF > vanity-osmo_1.0.0/DEBIAN/control
Package: vanity-osmo
Version: 1.0.0
Section: utils
Priority: optional
Architecture: all
Maintainer: Your Name <you@example.com>
Description: GPU vanity address generator for Osmosis
EOF
```

### 5. (Optional) Post-install to auto-install Python deps

```bash
cat <<EOF > vanity-osmo_1.0.0/DEBIAN/postinst
#!/bin/bash
pip3 install -r /opt/vanity-osmo/requirements.txt
exit 0
EOF

chmod +x vanity-osmo_1.0.0/DEBIAN/postinst
```

### 6. Build the .deb package

```bash
dpkg-deb --build vanity-osmo_1.0.0
```

This creates: `vanity-osmo_1.0.0.deb`

---

## 📥 Install

```bash
sudo dpkg -i vanity-osmo_1.0.0.deb
```

After that, use:

```bash
vanity-osmo --prefix osmo1cool --batch 100000
```

---

## 📤 Uninstall

```bash
sudo dpkg -r vanity-osmo
```
