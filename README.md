# Anonymous VPN Installer (WireGuard)

Two scripts that set up a self-hosted WireGuard VPN for anonymous internet browsing.

| Script | Purpose |
|---|---|
| `vpn_server_setup.sh` | Run on your VPS/server to create the VPN endpoint |
| `vpn_client_install.sh` | Run on any client machine to connect through that server |

---

## Quick Start

### Step 1 — Set up the VPN server (on your VPS)

```bash
chmod +x vpn_server_setup.sh
sudo ./vpn_server_setup.sh
```

Then add a client profile:

```bash
sudo ./vpn_server_setup.sh add-client mylaptop
```

This prints a client `.conf` file path and an optional QR code for mobile.

---

### Step 2 — Install & connect on the client machine

**Option A — Import the `.conf` file the server generated:**

```bash
chmod +x vpn_client_install.sh

# Copy the conf from your server first:
scp root@<SERVER_IP>:/etc/wireguard/clients/mylaptop.conf .

sudo ./vpn_client_install.sh import mylaptop.conf
```

**Option B — Interactive setup (enter keys manually):**

```bash
sudo ./vpn_client_install.sh install
```

---

## Client Commands

```bash
sudo ./vpn_client_install.sh connect          # Connect VPN
sudo ./vpn_client_install.sh disconnect       # Disconnect
sudo ./vpn_client_install.sh status           # Show status & current IP
sudo ./vpn_client_install.sh check-leak       # DNS/IP leak check
sudo ./vpn_client_install.sh enable-autostart # Auto-connect on boot
sudo ./vpn_client_install.sh generate-keys    # Generate a new key pair
```

## Server Commands

```bash
sudo ./vpn_server_setup.sh                    # Initial server install
sudo ./vpn_server_setup.sh add-client <name>  # Add a new client
sudo ./vpn_server_setup.sh list-clients       # List clients
sudo ./vpn_server_setup.sh status             # Show WireGuard status
```

---

## iPhone / iOS Setup

WireGuard has an official free iOS app. No jailbreak required.

### Step 1 — Add a client profile on your server

```bash
sudo ./vpn_server_setup.sh add-client myiphone
```

### Step 2 — Transfer the config to your iPhone

**Option A — QR Code (easiest, no cable needed)**

```bash
sudo ./vpn_server_setup.sh qr myiphone
```

On your iPhone:
1. Open the **App Store** → search **WireGuard** → install it (it's free, by WireGuard Development Team)
2. Tap **+** → **Create from QR Code**
3. Point the camera at the QR code on your screen
4. Name the tunnel and tap **Allow** when asked for VPN permissions

**Option B — File transfer via Mac + AirDrop**

```bash
# On your Mac, copy the conf file from the server:
scp root@<SERVER_IP>:/etc/wireguard/clients/myiphone.conf ~/Desktop/myiphone.conf
```

Then AirDrop `myiphone.conf` to your iPhone → open it → WireGuard imports it automatically.

**Option C — Show all options**

```bash
sudo ./vpn_server_setup.sh ios myiphone
```

### Step 3 — Connect on iPhone

In the WireGuard app, tap the toggle next to your tunnel. A VPN icon appears in the status bar when connected.

> The `.conf` file format is identical for Linux, macOS, Windows, Android, and iOS — the same profile works everywhere.

---

## How It Works

```
Your machine ──[WireGuard encrypted tunnel]──► VPS server ──► Internet
              Your ISP sees only encrypted      Traffic exits from
              traffic to one IP.                the server's IP.
```

- All traffic (`0.0.0.0/0`) is routed through the tunnel
- DNS is resolved through the tunnel (Cloudflare 1.1.1.1 by default)
- A preshared key adds an extra layer of post-quantum resistance
- `PersistentKeepalive` keeps the tunnel alive through NAT

---

## Requirements

| Component | Requirement |
|---|---|
| **Server** | Linux VPS with a public IP, root access, UDP port 51820 open |
| **Client** | Linux (Ubuntu/Debian/Fedora/Arch/openSUSE), root access |
| **Protocol** | WireGuard (installed automatically) |

---

## Supported Operating Systems

- Ubuntu / Debian
- Fedora / CentOS / RHEL / Rocky / AlmaLinux
- Arch / Manjaro
- openSUSE / SLES

---

## Security Notes

- Server private key is stored at `/etc/wireguard/server_private.key` (mode 600)
- Client configs are stored at `/etc/wireguard/clients/` (mode 600)
- A unique preshared key is generated per client for extra security
- No logs are written by default; WireGuard is a silent protocol
