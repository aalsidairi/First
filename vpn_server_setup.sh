#!/usr/bin/env bash
# WireGuard VPN Server Setup Script
# Run this on your VPS/server to set up the VPN endpoint

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()    { echo -e "${GREEN}[+]${NC} $*"; }
warn()   { echo -e "${YELLOW}[!]${NC} $*"; }
error()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }
info()   { echo -e "${BLUE}[i]${NC} $*"; }

WG_INTERFACE="wg0"
WG_PORT=51820
SERVER_SUBNET="10.8.0.1/24"
DNS_SERVERS="1.1.1.1,1.0.0.1"
CONFIG_DIR="/etc/wireguard"
CLIENT_DIR="$CONFIG_DIR/clients"

require_root() {
    [[ $EUID -eq 0 ]] || error "This script must be run as root (sudo $0)"
}

detect_os() {
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        OS_ID="$ID"
        OS_VERSION_ID="${VERSION_ID:-}"
    else
        error "Cannot detect OS. /etc/os-release not found."
    fi
}

detect_public_ip() {
    PUBLIC_IP=$(curl -s --max-time 10 https://api.ipify.org 2>/dev/null \
        || curl -s --max-time 10 https://icanhazip.com 2>/dev/null \
        || echo "")
    if [[ -z "$PUBLIC_IP" ]]; then
        warn "Could not auto-detect public IP."
        read -rp "Enter your server's public IP address: " PUBLIC_IP
    fi
    log "Server public IP: $PUBLIC_IP"
}

detect_interface() {
    NET_IFACE=$(ip -4 route show default 2>/dev/null | awk '/^default/ {print $5; exit}')
    [[ -n "$NET_IFACE" ]] || error "Could not detect default network interface."
    log "Default network interface: $NET_IFACE"
}

install_wireguard() {
    log "Installing WireGuard..."
    case "$OS_ID" in
        ubuntu|debian)
            apt-get update -qq
            apt-get install -y wireguard wireguard-tools iptables curl
            ;;
        centos|rhel|fedora|rocky|almalinux)
            if [[ "$OS_ID" == "fedora" ]]; then
                dnf install -y wireguard-tools iptables curl
            else
                dnf install -y epel-release 2>/dev/null || yum install -y epel-release 2>/dev/null || true
                dnf install -y wireguard-tools iptables curl 2>/dev/null \
                    || yum install -y wireguard-tools iptables curl
            fi
            ;;
        arch|manjaro)
            pacman -Sy --noconfirm wireguard-tools iptables curl
            ;;
        *)
            error "Unsupported OS: $OS_ID. Install WireGuard manually."
            ;;
    esac
    log "WireGuard installed."
}

generate_server_keys() {
    log "Generating server keys..."
    mkdir -p "$CONFIG_DIR"
    chmod 700 "$CONFIG_DIR"

    if [[ -f "$CONFIG_DIR/server_private.key" ]]; then
        warn "Server keys already exist. Skipping key generation."
    else
        wg genkey | tee "$CONFIG_DIR/server_private.key" \
            | wg pubkey > "$CONFIG_DIR/server_public.key"
        chmod 600 "$CONFIG_DIR/server_private.key"
    fi

    SERVER_PRIVATE_KEY=$(cat "$CONFIG_DIR/server_private.key")
    SERVER_PUBLIC_KEY=$(cat "$CONFIG_DIR/server_public.key")
    log "Server public key: $SERVER_PUBLIC_KEY"
}

enable_ip_forwarding() {
    log "Enabling IP forwarding..."
    if ! grep -q "^net.ipv4.ip_forward=1" /etc/sysctl.conf 2>/dev/null; then
        echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
    fi
    if ! grep -q "^net.ipv6.conf.all.forwarding=1" /etc/sysctl.conf 2>/dev/null; then
        echo "net.ipv6.conf.all.forwarding=1" >> /etc/sysctl.conf
    fi
    sysctl -p -q
}

write_server_config() {
    log "Writing server configuration..."
    cat > "$CONFIG_DIR/$WG_INTERFACE.conf" <<EOF
[Interface]
Address = $SERVER_SUBNET
ListenPort = $WG_PORT
PrivateKey = $SERVER_PRIVATE_KEY
PostUp   = iptables -A FORWARD -i %i -j ACCEPT; iptables -A FORWARD -o %i -j ACCEPT; iptables -t nat -A POSTROUTING -o $NET_IFACE -j MASQUERADE
PostDown = iptables -D FORWARD -i %i -j ACCEPT; iptables -D FORWARD -o %i -j ACCEPT; iptables -t nat -D POSTROUTING -o $NET_IFACE -j MASQUERADE

# --- Clients will be appended below ---
EOF
    chmod 600 "$CONFIG_DIR/$WG_INTERFACE.conf"
}

start_wireguard() {
    log "Starting WireGuard service..."
    systemctl enable --now "wg-quick@$WG_INTERFACE"
    systemctl is-active --quiet "wg-quick@$WG_INTERFACE" \
        && log "WireGuard is running." \
        || error "WireGuard failed to start. Check: journalctl -xeu wg-quick@$WG_INTERFACE"
}

open_firewall_port() {
    if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
        ufw allow "$WG_PORT/udp" &>/dev/null
        log "ufw: opened UDP port $WG_PORT"
    elif command -v firewall-cmd &>/dev/null; then
        firewall-cmd --permanent --add-port="$WG_PORT/udp" &>/dev/null
        firewall-cmd --reload &>/dev/null
        log "firewalld: opened UDP port $WG_PORT"
    else
        warn "No recognized firewall found. Manually open UDP port $WG_PORT."
    fi
}

add_client() {
    local CLIENT_NAME="${1:-client1}"
    local CLIENT_IP
    local LAST_IP

    mkdir -p "$CLIENT_DIR"

    # Pick next available IP in 10.8.0.x
    LAST_IP=$(grep -oP '10\.8\.0\.\K\d+' "$CONFIG_DIR/$WG_INTERFACE.conf" 2>/dev/null | sort -n | tail -1 || echo 1)
    CLIENT_IP="10.8.0.$((LAST_IP + 1))/32"

    log "Adding client '$CLIENT_NAME' with IP $CLIENT_IP ..."

    # Generate client keys
    CLIENT_PRIVATE_KEY=$(wg genkey)
    CLIENT_PUBLIC_KEY=$(echo "$CLIENT_PRIVATE_KEY" | wg pubkey)
    CLIENT_PRESHARED_KEY=$(wg genpsk)

    # Append peer to server config
    cat >> "$CONFIG_DIR/$WG_INTERFACE.conf" <<EOF

[Peer]
# $CLIENT_NAME
PublicKey = $CLIENT_PUBLIC_KEY
PresharedKey = $CLIENT_PRESHARED_KEY
AllowedIPs = $CLIENT_IP
EOF

    # Write client config file
    cat > "$CLIENT_DIR/$CLIENT_NAME.conf" <<EOF
[Interface]
PrivateKey = $CLIENT_PRIVATE_KEY
Address = $CLIENT_IP
DNS = $DNS_SERVERS

[Peer]
PublicKey = $SERVER_PUBLIC_KEY
PresharedKey = $CLIENT_PRESHARED_KEY
Endpoint = $PUBLIC_IP:$WG_PORT
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
EOF
    chmod 600 "$CLIENT_DIR/$CLIENT_NAME.conf"

    # Hot-reload WireGuard (no disconnect for existing peers)
    wg syncconf "$WG_INTERFACE" <(wg-quick strip "$WG_INTERFACE") 2>/dev/null || true

    log "Client config saved: $CLIENT_DIR/$CLIENT_NAME.conf"

    if command -v qrencode &>/dev/null; then
        echo ""
        info "Scan this QR code with your WireGuard mobile app:"
        qrencode -t ansiutf8 < "$CLIENT_DIR/$CLIENT_NAME.conf"
    else
        info "Install 'qrencode' to display a mobile QR code."
    fi

    echo ""
    info "Copy the client config to the client machine:"
    echo "  scp root@$PUBLIC_IP:$CLIENT_DIR/$CLIENT_NAME.conf /etc/wireguard/$CLIENT_NAME.conf"
}

print_usage() {
    echo ""
    echo "Usage:"
    echo "  sudo $0                        # Install & configure VPN server"
    echo "  sudo $0 add-client <name>      # Add a new VPN client"
    echo "  sudo $0 list-clients           # List all clients"
    echo "  sudo $0 status                 # Show WireGuard status"
    echo ""
}

list_clients() {
    if [[ -d "$CLIENT_DIR" ]]; then
        echo "Clients:"
        ls "$CLIENT_DIR"/*.conf 2>/dev/null | xargs -I{} basename {} .conf || echo "  (none)"
    else
        echo "No clients directory found."
    fi
}

main() {
    case "${1:-install}" in
        install)
            require_root
            detect_os
            detect_public_ip
            detect_interface
            install_wireguard
            generate_server_keys
            enable_ip_forwarding
            write_server_config
            open_firewall_port
            start_wireguard
            echo ""
            log "Server setup complete!"
            info "Public key: $SERVER_PUBLIC_KEY"
            info "Listening on: $PUBLIC_IP:$WG_PORT/udp"
            echo ""
            info "Add your first client with:"
            echo "  sudo $0 add-client myclient"
            ;;
        add-client)
            require_root
            [[ -n "${2:-}" ]] || { warn "Provide a client name."; print_usage; exit 1; }
            SERVER_PUBLIC_KEY=$(cat "$CONFIG_DIR/server_public.key")
            PUBLIC_IP=$(curl -s --max-time 10 https://api.ipify.org 2>/dev/null || cat /tmp/vpn_server_ip 2>/dev/null || error "Cannot detect server IP")
            add_client "$2"
            ;;
        list-clients)
            require_root
            list_clients
            ;;
        status)
            require_root
            wg show "$WG_INTERFACE" 2>/dev/null || error "WireGuard interface $WG_INTERFACE not found"
            ;;
        *)
            print_usage
            ;;
    esac
}

main "$@"
