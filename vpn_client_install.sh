#!/usr/bin/env bash
# WireGuard VPN Client Installer
# Connects your machine anonymously through a WireGuard VPN server

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()   { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; exit 1; }
info()  { echo -e "${BLUE}[i]${NC} $*"; }

WG_INTERFACE="${WG_INTERFACE:-wg0}"
CONFIG_DIR="/etc/wireguard"

require_root() {
    [[ $EUID -eq 0 ]] || error "Run as root: sudo $0 $*"
}

detect_os() {
    [[ -f /etc/os-release ]] || error "/etc/os-release not found."
    source /etc/os-release
    OS_ID="$ID"
}

install_wireguard() {
    if command -v wg &>/dev/null; then
        log "WireGuard already installed."
        return
    fi
    log "Installing WireGuard..."
    case "$OS_ID" in
        ubuntu|debian)
            apt-get update -qq
            apt-get install -y wireguard wireguard-tools resolvconf curl
            ;;
        centos|rhel|rocky|almalinux)
            dnf install -y epel-release 2>/dev/null || yum install -y epel-release 2>/dev/null || true
            dnf install -y wireguard-tools 2>/dev/null || yum install -y wireguard-tools
            ;;
        fedora)
            dnf install -y wireguard-tools
            ;;
        arch|manjaro)
            pacman -Sy --noconfirm wireguard-tools
            ;;
        opensuse*|sles)
            zypper install -y wireguard-tools
            ;;
        *)
            error "Unsupported OS: $OS_ID. Please install WireGuard manually."
            ;;
    esac
    log "WireGuard installed."
}

prompt_config() {
    echo ""
    echo "═══════════════════════════════════════════════"
    echo "   WireGuard VPN Client Configuration"
    echo "═══════════════════════════════════════════════"
    echo ""

    read -rp "Client private key  : " CLIENT_PRIVATE_KEY
    read -rp "Server public key   : " SERVER_PUBLIC_KEY
    read -rp "Preshared key (leave blank to skip): " CLIENT_PRESHARED_KEY
    read -rp "Client VPN IP (e.g. 10.8.0.2/32)  : " CLIENT_ADDRESS
    read -rp "Server endpoint (IP:PORT)           : " SERVER_ENDPOINT
    read -rp "DNS servers [1.1.1.1,1.0.0.1]      : " DNS_INPUT
    DNS="${DNS_INPUT:-1.1.1.1,1.0.0.1}"
}

import_config() {
    local CONFIG_FILE="$1"
    [[ -f "$CONFIG_FILE" ]] || error "Config file not found: $CONFIG_FILE"

    DEST="$CONFIG_DIR/$WG_INTERFACE.conf"
    mkdir -p "$CONFIG_DIR"
    cp "$CONFIG_FILE" "$DEST"
    chmod 600 "$DEST"
    log "Config imported to $DEST"
}

write_config() {
    mkdir -p "$CONFIG_DIR"
    DEST="$CONFIG_DIR/$WG_INTERFACE.conf"

    PEER_EXTRA=""
    if [[ -n "${CLIENT_PRESHARED_KEY:-}" ]]; then
        PEER_EXTRA="PresharedKey = $CLIENT_PRESHARED_KEY"$'\n'
    fi

    cat > "$DEST" <<EOF
[Interface]
PrivateKey = $CLIENT_PRIVATE_KEY
Address = $CLIENT_ADDRESS
DNS = $DNS

[Peer]
PublicKey = $SERVER_PUBLIC_KEY
${PEER_EXTRA}Endpoint = $SERVER_ENDPOINT
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
EOF
    chmod 600 "$DEST"
    log "Configuration written to $DEST"
}

connect() {
    log "Connecting to VPN..."
    wg-quick up "$WG_INTERFACE" 2>/dev/null || {
        warn "Interface may already be up. Bringing it down first..."
        wg-quick down "$WG_INTERFACE" 2>/dev/null || true
        wg-quick up "$WG_INTERFACE"
    }
    log "VPN connected on interface $WG_INTERFACE"
}

disconnect() {
    log "Disconnecting VPN..."
    wg-quick down "$WG_INTERFACE" 2>/dev/null && log "Disconnected." || warn "Interface was not up."
}

status() {
    if wg show "$WG_INTERFACE" &>/dev/null; then
        log "VPN is CONNECTED"
        wg show "$WG_INTERFACE"
        echo ""
        info "Current public IP:"
        curl -s --max-time 10 https://api.ipify.org && echo ""
    else
        warn "VPN is NOT connected."
        info "Your real public IP:"
        curl -s --max-time 10 https://api.ipify.org && echo ""
    fi
}

enable_autostart() {
    systemctl enable "wg-quick@$WG_INTERFACE"
    log "VPN will auto-start on boot."
}

disable_autostart() {
    systemctl disable "wg-quick@$WG_INTERFACE" 2>/dev/null || true
    log "VPN auto-start disabled."
}

generate_keys() {
    echo ""
    log "Generating a new WireGuard key pair..."
    PRIV=$(wg genkey)
    PUB=$(echo "$PRIV" | wg pubkey)
    PSK=$(wg genpsk)
    echo ""
    echo "  Private key (keep secret): $PRIV"
    echo "  Public key  (share with server): $PUB"
    echo "  Preshared key (optional, share with server): $PSK"
    echo ""
}

check_leak() {
    echo ""
    log "Running basic anonymity check..."
    echo ""

    info "Current public IP (via VPN tunnel):"
    CURRENT_IP=$(curl -s --max-time 10 https://api.ipify.org 2>/dev/null || echo "Failed to fetch")
    echo "  $CURRENT_IP"

    info "DNS leak test (should show VPN DNS, not your ISP's):"
    dig +short TXT whoami.ds.akahelp.net 2>/dev/null | head -3 || \
        nslookup -type=TXT whoami.ds.akahelp.net 2>/dev/null | grep '"' || \
        echo "  (install 'dig' or 'nslookup' for full test)"

    echo ""
    info "For a full DNS/WebRTC leak test visit: https://dnsleaktest.com"
}

print_usage() {
    echo ""
    echo "WireGuard VPN Client Installer"
    echo ""
    echo "Usage:"
    echo "  sudo $0 install                        # Interactive install & connect"
    echo "  sudo $0 import <file.conf>             # Import existing .conf & connect"
    echo "  sudo $0 connect                        # Connect (config must exist)"
    echo "  sudo $0 disconnect                     # Disconnect VPN"
    echo "  sudo $0 status                         # Show status & current IP"
    echo "  sudo $0 enable-autostart               # Auto-connect on boot"
    echo "  sudo $0 disable-autostart              # Disable auto-connect"
    echo "  sudo $0 check-leak                     # Basic anonymity/DNS leak check"
    echo "       $0 generate-keys                  # Generate a new key pair (no root)"
    echo ""
}

main() {
    case "${1:-}" in
        install)
            require_root
            detect_os
            install_wireguard
            prompt_config
            write_config
            connect
            info "Run 'sudo $0 status' to verify your anonymized IP."
            info "Run 'sudo $0 check-leak' to check for DNS leaks."
            ;;
        import)
            require_root
            [[ -n "${2:-}" ]] || { warn "Provide a config file path."; print_usage; exit 1; }
            detect_os
            install_wireguard
            import_config "$2"
            connect
            info "Run 'sudo $0 status' to verify your anonymized IP."
            ;;
        connect)
            require_root
            [[ -f "$CONFIG_DIR/$WG_INTERFACE.conf" ]] || error "No config at $CONFIG_DIR/$WG_INTERFACE.conf. Run install or import first."
            connect
            ;;
        disconnect)
            require_root
            disconnect
            ;;
        status)
            require_root
            status
            ;;
        enable-autostart)
            require_root
            enable_autostart
            ;;
        disable-autostart)
            require_root
            disable_autostart
            ;;
        check-leak)
            require_root
            check_leak
            ;;
        generate-keys)
            command -v wg &>/dev/null || error "WireGuard not installed. Run: sudo $0 install"
            generate_keys
            ;;
        *)
            print_usage
            exit 1
            ;;
    esac
}

main "$@"
