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
    echo -e "  ${C_DIM}────────────────────────────────────────────────────${C_RESET}"
}

print_banner() {
    clear 2>/dev/null || true
    echo ""
    echo -e "${C_CYAN}${C_BOLD}"
    cat <<'EOF'
  ██╗   ██╗██████╗ ██╗          █████╗ ████████╗████████╗ █████╗  ██████╗██╗  ██╗
  ██║   ██║██╔══██╗██║         ██╔══██╗╚══██╔══╝╚══██╔══╝██╔══██╗██╔════╝██║ ██╔╝
  ██║   ██║██████╔╝██║         ███████║   ██║      ██║   ███████║██║     █████╔╝ 
  ██║   ██║██╔══██╗██║         ██╔══██║   ██║      ██║   ██╔══██║██║     ██╔═██╗ 
  ╚██████╔╝██║  ██║███████╗    ██║  ██║   ██║      ██║   ██║  ██║╚██████╗██║  ██╗
   ╚═════╝ ╚═╝  ╚═╝╚══════╝    ╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝
EOF
    echo -e "${C_RESET}  ${C_BOLD}${C_MAGENTA}[ SETUP & DEPENDENCY INSTALLER ]${C_RESET}"
    echo -e "  ${C_DIM}Advanced Target Extermination Framework${C_RESET}"
    echo ""
}

print_banner

# ============================================================
# 1. SYSTEM DETECTION
# ============================================================
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

# Architecture info
ARCH=$(uname -m)
ok "Architecture: ${C_BOLD}$ARCH${C_RESET}"
ok "Kernel: $(uname -r)"

# ============================================================
# 2. INSTALL SYSTEM DEPENDENCIES
# ============================================================
section "INSTALLING SYSTEM DEPENDENCIES"

case "$PKG_MGR" in
    apt)
        info "Updating repositories..."
        $SUDO apt update -y >/dev/null 2>&1
        info "Installing python3, pip, venv, curl, wget, build tools, tmux..."
        $SUDO apt install -y \
            python3 python3-pip python3-venv \
            curl wget ca-certificates \
            build-essential libssl-dev libffi-dev \
            python3-dev pkg-config git \
            tmux screen >/dev/null 2>&1
        ;;
    yum)
        info "Installing python3, pip, curl, wget, build tools, tmux..."
        $SUDO yum install -y \
            python3 python3-pip \
            curl wget ca-certificates \
            gcc gcc-c++ openssl-devel libffi-devel \
            python3-devel git tmux screen >/dev/null 2>&1
        ;;
    dnf)
        info "Installing python3, pip, curl, wget, build tools, tmux..."
        $SUDO dnf install -y \
            python3 python3-pip \
            curl wget ca-certificates \
            gcc gcc-c++ openssl-devel libffi-devel \
            python3-devel git tmux screen >/dev/null 2>&1
        ;;
    pacman)
        info "Installing python, pip, curl, wget, build tools, tmux..."
        $SUDO pacman -Sy --noconfirm \
            python python-pip \
            curl wget ca-certificates \
            base-devel openssl libffi git \
            tmux screen >/dev/null 2>&1
        ;;
    apk)
        info "Installing python3, pip, curl, wget, build tools, tmux..."
        $SUDO apk add --no-cache \
            python3 py3-pip \
            curl wget ca-certificates \
            build-base openssl-dev libffi-dev \
            python3-dev git tmux screen >/dev/null 2>&1
        ;;
esac

ok "System dependencies installed"

# ============================================================
# 3. PYTHON VERSION CHECK
# ============================================================
section "PYTHON VERSION CHECK"

if ! command -v python3 &> /dev/null; then
    err "python3 not found after installation"
    exit 1
fi

PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
ok "Python version: ${C_BOLD}$PYVER${C_RESET}"

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
    err "Python 3.8+ is required. Current: $PYVER"
    exit 1
fi

ok "Version requirement satisfied"

info "Upgrading pip..."
python3 -m pip install --upgrade pip --quiet 2>/dev/null \
    || python3 -m pip install --upgrade pip --break-system-packages --quiet 2>/dev/null \
    || $SUDO python3 -m pip install --upgrade pip --break-system-packages --quiet 2>/dev/null \
    || warn "Could not upgrade pip — continuing anyway"

# ============================================================
# 4. INSTALL PYTHON PACKAGES
# ============================================================
section "INSTALLING PYTHON PACKAGES"

install_py_pkg() {
    local pkg="$1"
    local quiet="${2:-}"
    local flags=""
    [ -n "$quiet" ] && flags="--quiet"

    if python3 -m pip install "$pkg" --break-system-packages $flags 2>/dev/null; then return 0; fi
    if python3 -m pip install "$pkg" $flags 2>/dev/null; then return 0; fi
    if python3 -m pip install "$pkg" --user --break-system-packages $flags 2>/dev/null; then return 0; fi
    if python3 -m pip install "$pkg" --user $flags 2>/dev/null; then return 0; fi
    if $SUDO python3 -m pip install "$pkg" --break-system-packages $flags 2>/dev/null; then return 0; fi
    if $SUDO python3 -m pip install "$pkg" $flags 2>/dev/null; then return 0; fi
    return 1
}

PACKAGES=(
    "aiohttp"
    "aiohttp-socks"
    "brotli"
    "paramiko"
    "dnspython"
    "cryptography"
)

FAILED_PKGS=()
for pkg in "${PACKAGES[@]}"; do
    info "Installing ${C_BOLD}$pkg${C_RESET}..."
    if install_py_pkg "$pkg" "quiet"; then
        ok "$pkg installed"
    else
        err "Failed to install $pkg"
        FAILED_PKGS+=("$pkg")
    fi
done

if [ ${#FAILED_PKGS[@]} -ne 0 ]; then
    warn "Some packages failed to install: ${FAILED_PKGS[*]}"
    dim "Trying legacy method..."
    for pkg in "${FAILED_PKGS[@]}"; do
        $SUDO pip3 install "$pkg" --break-system-packages 2>/dev/null \
            || $SUDO pip3 install "$pkg" 2>/dev/null \
            || err "Still failed: $pkg"
    done
fi

# ============================================================
# 5. VERIFYING IMPORTS
# ============================================================
section "VERIFYING IMPORTS"

REQUIRED_MODS=("aiohttp" "aiohttp_socks" "brotli" "paramiko" "dns")
OPTIONAL_MODS=("cryptography" "ssl")

MISSING=()
for mod in "${REQUIRED_MODS[@]}"; do
    if python3 -c "import $mod" 2>/dev/null; then
        ok "$mod"
    else
        err "$mod ${C_RED}NOT available${C_RESET}"
        MISSING+=("$mod")
    fi
done

for mod in "${OPTIONAL_MODS[@]}"; do
    if python3 -c "import $mod" 2>/dev/null; then
        ok "$mod ${C_DIM}(optional)${C_RESET}"
    else
        warn "$mod ${C_DIM}(optional — not critical)${C_RESET}"
    fi
done

if [ ${#MISSING[@]} -ne 0 ]; then
    err "Missing required Python packages: ${MISSING[*]}"
    echo ""
    read -p "  Continue anyway? [y/N]: " cont
    if [[ ! "$cont" =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    ok "All Python packages verified"
fi

# ============================================================
# 6. RAISE FILE DESCRIPTOR LIMITS
# ============================================================
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

# ============================================================
# 7. TCP STACK TUNING
# ============================================================
section "TCP STACK TUNING"

if [ "$(id -u)" -eq 0 ]; then
    info "Tuning TCP stack for high-concurrency networking..."

    sysctl -w net.ipv4.tcp_fin_timeout=15 >/dev/null 2>&1 \
        && ok "tcp_fin_timeout = 15" || warn "tcp_fin_timeout failed"

    sysctl -w net.ipv4.tcp_tw_reuse=1 >/dev/null 2>&1 \
        && ok "tcp_tw_reuse = 1" || warn "tcp_tw_reuse failed"

    sysctl -w net.ipv4.ip_local_port_range="1024 65535" >/dev/null 2>&1 \
        && ok "ip_local_port_range widened" || warn "ip_local_port_range failed"

    sysctl -w net.ipv4.tcp_max_syn_backlog=65535 >/dev/null 2>&1 \
        && ok "tcp_max_syn_backlog raised" || warn "tcp_max_syn_backlog failed"

    sysctl -w net.core.somaxconn=65535 >/dev/null 2>&1 \
        && ok "somaxconn raised" || warn "somaxconn failed"

    sysctl -w fs.file-max=2097152 >/dev/null 2>&1 \
        && ok "fs.file-max raised" || warn "fs.file-max failed"
else
    warn "Skipping TCP stack tuning (requires root)"
fi

# ============================================================
# 8. ENVIRONMENT SETUP
# ============================================================
section "ENVIRONMENT SETUP"

if [ -z "$LANG" ] || [ -z "$LC_ALL" ]; then
    export LANG=C.UTF-8
    export LC_ALL=C.UTF-8
    ok "UTF-8 locale set for current session"
    if ! grep -q "LANG=C.UTF-8" ~/.bashrc 2>/dev/null; then
        echo 'export LANG=C.UTF-8' >> ~/.bashrc
        echo 'export LC_ALL=C.UTF-8' >> ~/.bashrc
        ok "UTF-8 locale saved to ~/.bashrc"
    fi
else
    ok "Locale already configured: $LANG"
fi

if ! grep -q "PYTHONDONTWRITEBYTECODE" ~/.bashrc 2>/dev/null; then
    echo 'export PYTHONDONTWRITEBYTECODE=1' >> ~/.bashrc
    ok "Python bytecode writing disabled"
fi

# ============================================================
# 9. DOWNLOAD MAIN SCRIPT
# ============================================================
section "DOWNLOADING MAIN SCRIPT"

RAW_PYTHON_URL="https://raw.githubusercontent.com/coderuseplayer-netizen/subscriptionlink-panel-DoS-ATTACK/main/main.py"
SCRIPT_DIR="$(pwd)"
SCRIPT_FILE="run.py"
FULL_SCRIPT_PATH="$SCRIPT_DIR/$SCRIPT_FILE"
BACKUP_FILE="run.py.bak"

if [ -f "$SCRIPT_FILE" ]; then
    info "Backing up existing $SCRIPT_FILE -> $BACKUP_FILE"
    cp "$SCRIPT_FILE" "$BACKUP_FILE"
    ok "Backup created"
fi

info "Downloading from repository..."
if curl -fsSL --connect-timeout 15 --retry 3 "$RAW_PYTHON_URL" -o "$SCRIPT_FILE"; then
    ok "Downloaded to ${C_BOLD}$SCRIPT_FILE${C_RESET}"
else
    err "Failed to download from $RAW_PYTHON_URL"
    if [ -f "$BACKUP_FILE" ]; then
        warn "Restoring from backup..."
        mv "$BACKUP_FILE" "$SCRIPT_FILE"
        ok "Using local $SCRIPT_FILE instead"
    else
        err "No backup available and download failed. Aborting."
        exit 1
    fi
fi

if ! head -1 "$SCRIPT_FILE" | grep -q "python"; then
    warn "Downloaded file doesn't look like a Python script"
    read -p "  Continue anyway? [y/N]: " cont
    if [[ ! "$cont" =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

chmod +x "$SCRIPT_FILE"
ok "Script marked as executable"

# ============================================================
# 10. INSTALL 'blackout' COMMAND (background session manager)
# ============================================================
section "INSTALLING 'blackout' COMMAND"

# Decide session name & directory
SESSION_NAME="blackout"
BLACKOUT_BIN="/usr/local/bin/blackout"

# Ensure we can write to /usr/local/bin
if [ ! -w /usr/local/bin ] && [ "$(id -u)" -ne 0 ]; then
    warn "Cannot write to /usr/local/bin without sudo — using ~/.local/bin"
    mkdir -p ~/.local/bin
    BLACKOUT_BIN="$HOME/.local/bin/blackout"
fi

# Write the blackout command wrapper
$SUDO tee "$BLACKOUT_BIN" > /dev/null <<EOF
#!/bin/bash
# ============================================================
# blackout — bring the attack script to the foreground
# ============================================================
SESSION_NAME="$SESSION_NAME"
SCRIPT_PATH="$FULL_SCRIPT_PATH"
SCRIPT_DIR="$SCRIPT_DIR"
TARGET_LIMIT=65535

C_RESET='\033[0m'
C_BOLD='\033[1m'
C_DIM='\033[2m'
C_RED='\033[91m'
C_GREEN='\033[92m'
C_YELLOW='\033[93m'
C_CYAN='\033[96m'
C_MAGENTA='\033[95m'

# Ensure tmux exists
if ! command -v tmux >/dev/null 2>&1; then
    echo -e "  \${C_RED}✗\${C_RESET} tmux not installed. Install it: apt install tmux"
    exit 1
fi

# Parse args
ACTION="attach"
case "\$1" in
    stop)
        ACTION="stop"
        ;;
    status)
        ACTION="status"
        ;;
    restart)
        ACTION="restart"
        ;;
    kill)
        ACTION="kill"
        ;;
    ""|attach)
        ACTION="attach"
        ;;
    *)
        echo "Usage: blackout [attach|stop|status|restart|kill]"
        exit 1
        ;;
esac

# ---- STOP ----
if [ "\$ACTION" = "stop" ]; then
    if tmux has-session -t "\$SESSION_NAME" 2>/dev/null; then
        # send SIGINT so python handles cleanup
        tmux send-keys -t "\$SESSION_NAME" C-c
        sleep 2
        tmux kill-session -t "\$SESSION_NAME" 2>/dev/null
        echo -e "  \${C_GREEN}✓\${C_RESET} Session '\$SESSION_NAME' stopped."
    else
        echo -e "  \${C_YELLOW}⚠\${C_RESET} No active session '\$SESSION_NAME'."
    fi
    exit 0
fi

# ---- KILL (force) ----
if [ "\$ACTION" = "kill" ]; then
    if tmux has-session -t "\$SESSION_NAME" 2>/dev/null; then
        tmux kill-session -t "\$SESSION_NAME" 2>/dev/null
        pkill -9 -f "\$SCRIPT_PATH" 2>/dev/null
        echo -e "  \${C_GREEN}✓\${C_RESET} Session force-killed."
    else
        echo -e "  \${C_YELLOW}⚠\${C_RESET} No active session."
    fi
    exit 0
fi

# ---- STATUS ----
if [ "\$ACTION" = "status" ]; then
    echo ""
    echo -e "  \${C_BOLD}\${C_MAGENTA}● BLACKOUT STATUS\${C_RESET}"
    echo -e "  \${C_DIM}────────────────────────────────────\${C_RESET}"
    if tmux has-session -t "\$SESSION_NAME" 2>/dev/null; then
        PID=\$(pgrep -f "\$SCRIPT_PATH" | head -1)
        echo -e "  \${C_GREEN}● ACTIVE\${C_RESET}    session: \$SESSION_NAME"
        echo -e "  \${C_DIM}├─\${C_RESET} Script    \$SCRIPT_PATH"
        echo -e "  \${C_DIM}└─\${C_RESET} PID       \${PID:-unknown}"
    else
        echo -e "  \${C_RED}● STOPPED\${C_RESET}   session: \$SESSION_NAME (not running)"
    fi
    echo ""
    exit 0
fi

# ---- RESTART ----
if [ "\$ACTION" = "restart" ]; then
    tmux kill-session -t "\$SESSION_NAME" 2>/dev/null
    pkill -9 -f "\$SCRIPT_PATH" 2>/dev/null
    sleep 1
    echo -e "  \${C_CYAN}➜\${C_RESET} Restarting..."
    ACTION="attach"
fi

# ---- ATTACH (start if needed) ----
if ! tmux has-session -t "\$SESSION_NAME" 2>/dev/null; then
    echo -e "  \${C_CYAN}➜\${C_RESET} No session found — starting new one..."
    cd "\$SCRIPT_DIR" || exit 1
    tmux new-session -d -s "\$SESSION_NAME" "ulimit -n \$TARGET_LIMIT; cd \$SCRIPT_DIR && python3 \$SCRIPT_PATH; exec bash"
    sleep 1
    echo -e "  \${C_GREEN}✓\${C_RESET} Session '\$SESSION_NAME' started in background."
    echo -e "  \${C_DIM}Tip: run 'blackout' again to attach.\${C_RESET}"
    echo ""
fi

# Attach to the session
exec tmux attach -t "\$SESSION_NAME"
EOF

$SUDO chmod +x "$BLACKOUT_BIN"

# Add ~/.local/bin to PATH if needed
if [[ "$BLACKOUT_BIN" == "$HOME/.local/bin/blackout" ]]; then
    if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
        export PATH="$HOME/.local/bin:$PATH"
        ok "Added ~/.local/bin to PATH"
    fi
fi

ok "Installed: ${C_BOLD}$BLACKOUT_BIN${C_RESET}"

# ============================================================
# 11. CREATE SHORTCUT ALIASES
# ============================================================
section "CREATING ALIASES"

BASHRC="$HOME/.bashrc"
touch "$BASHRC"

if ! grep -q "# --- blackout aliases ---" "$BASHRC" 2>/dev/null; then
    cat >> "$BASHRC" <<'ALIASEOF'

# --- blackout aliases ---
alias blackout='blackout attach'
alias blackout-stop='blackout stop'
alias blackout-status='blackout status'
alias blackout-restart='blackout restart'
alias blackout-kill='blackout kill'
ALIASEOF
    ok "Aliases added to ~/.bashrc"
else
    ok "Aliases already configured"
fi

# ============================================================
# 12. LAUNCH IN BACKGROUND
# ============================================================
section "LAUNCHING IN BACKGROUND"

# Start the session
cd "$SCRIPT_DIR" || exit 1
if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    tmux new-session -d -s "$SESSION_NAME" "ulimit -n $TARGET_LIMIT; cd $SCRIPT_DIR && python3 $FULL_SCRIPT_PATH; exec bash"
    sleep 1
    ok "Session '$SESSION_NAME' started in background"
    ok "Python script running inside tmux"
else
    warn "Session '$SESSION_NAME' already exists — skipping start"
fi

echo ""
echo -e "  ${C_BOLD}${C_GREEN}● SETUP COMPLETE${C_RESET}"
echo -e "  ${C_DIM}├─${C_RESET} Python         ${C_BOLD}$PYVER${C_RESET}"
echo -e "  ${C_DIM}├─${C_RESET} Socket limit   ${C_BOLD}$(ulimit -n)${C_RESET}"
echo -e "  ${C_DIM}├─${C_RESET} Locale         ${C_BOLD}${LANG:-unset}${C_RESET}"
echo -e "  ${C_DIM}├─${C_RESET} Script         ${C_BOLD}$FULL_SCRIPT_PATH${C_RESET}"
echo -e "  ${C_DIM}├─${C_RESET} Session        ${C_BOLD}$SESSION_NAME${C_RESET}"
echo -e "  ${C_DIM}└─${C_RESET} Status         ${C_GREEN}Running in background${C_RESET}"
echo ""
echo -e "  ${C_DIM}────────────────────────────────────────────────────${C_RESET}"
echo -e "  ${C_BOLD}● HOW TO USE${C_RESET}"
echo -e "  ${C_DIM}├─${C_RESET} ${C_CYAN}blackout${C_RESET}            → attach to session"
echo -e "  ${C_DIM}├─${C_RESET} ${C_CYAN}blackout stop${C_RESET}       → stop the attack"
echo -e "  ${C_DIM}├─${C_RESET} ${C_CYAN}blackout status${C_RESET}     → check status"
echo -e "  ${C_DIM}├─${C_RESET} ${C_CYAN}blackout restart${C_RESET}    → restart"
echo -e "  ${C_DIM}└─${C_RESET} ${C_CYAN}blackout kill${C_RESET}       → force kill"
echo ""
echo -e "  ${C_DIM}● SHORTCUTS${C_RESET}"
echo -e "  ${C_DIM}├─${C_RESET} ${C_CYAN}blackout-stop${C_RESET}"
echo -e "  ${C_DIM}├─${C_RESET} ${C_CYAN}blackout-status${C_RESET}"
echo -e "  ${C_DIM}└─${C_RESET} ${C_CYAN}blackout-restart${C_RESET}"
echo ""
echo -e "  ${C_DIM}────────────────────────────────────────────────────${C_RESET}"
echo -e "  ${C_YELLOW}⚠${C_RESET}  Detaching (Ctrl+B then D) keeps it running."
echo -e "  ${C_YELLOW}⚠${C_RESET}  Closing SSH does NOT kill the attack."
echo ""

# Reload bashrc in current shell (best-effort)
hash -r 2>/dev/null || true

echo -e "  ${C_CYAN}➜${C_RESET} To enter the attack console now, run:  ${C_BOLD}blackout${C_RESET}"
echo ""
