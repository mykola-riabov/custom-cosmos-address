#!/usr/bin/python3
import json
import requests
import time
import glob
import os
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor, as_completed

# Config
LCD_ENDPOINT = "https://lcd.osmosis.zone"
NUM_PROCESSES = 20
RESULT_DIR = "found_wallets"

# Create output folder
os.makedirs(RESULT_DIR, exist_ok=True)

# Find all .json files in current directory (excluding already processed)
wallet_files = sorted([f for f in glob.glob("*.json") if not f.startswith("found_") and not f.startswith(RESULT_DIR)])

# Function to check one wallet
def check_wallet(wallet):
    address = wallet["address"]
    try:
        url = f"{LCD_ENDPOINT}/cosmos/bank/v1beta1/balances/{address}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        balances = response.json().get("balances", [])
        for b in balances:
            if b["denom"] == "uosmo":
                amount = int(b["amount"])
                if amount > 0:
                    wallet["uosmo"] = amount
                    return wallet
                break
    except Exception:
        return None
    return None

# Process each file one by one
for file in wallet_files:
    print(f"📂 Processing file: {file}")

    with open(file, "r") as f:
        wallets = json.load(f)

    found = []
    with ProcessPoolExecutor(max_workers=NUM_PROCESSES) as executor:
        futures = [executor.submit(check_wallet, w) for w in wallets]

        for f in tqdm(as_completed(futures), total=len(wallets), desc=f"Checking {file}"):
            result = f.result()
            if result:
                found.append(result)

    # Save results for this file
    out_file = os.path.join(RESULT_DIR, f"found_from_{file}")
    with open(out_file, "w") as f:
        json.dump(found, f, indent=2)

    print(f"✅ {len(found)} wallets with uosmo > 0 saved to {out_file}\n")

print("🎉 All files processed.")


