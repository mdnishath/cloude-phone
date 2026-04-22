# P0 Foundation — Validated Redroid + Sidecar Pair — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a single, manually-operated pair of containers — one Redroid (Android 11) and one sidecar (redsocks + dnscrypt-proxy + iptables) — validated end-to-end: Android egress provably exits via the configured SOCKS5/HTTP proxy, zero traffic escapes when the sidecar is down, and a desktop scrcpy client can connect and display the home screen.

**Architecture:** The sidecar creates and owns a Linux network namespace. Redroid joins that same namespace via `docker run --network=container:<sidecar>`. Inside the namespace, iptables REDIRECT forces all TCP to `redsocks` on :12345, which forwards to the user-supplied proxy. DNS is served only by local `dnscrypt-proxy` (whose egress is also through redsocks). UDP to anything other than local DNS is DROP'd. If the sidecar dies, the kernel's `OUTPUT -P DROP` default means zero leak.

**Tech Stack:** Ubuntu 22.04 LTS VPS, Docker Engine 24+, Alpine 3.20 (sidecar base), `redsocks` 0.5, `dnscrypt-proxy` 2.x, `iptables` (legacy, not nftables), Redroid image `redroid/redroid:11.0.0_64only-latest`, bash 5, scrcpy 2.x (local desktop client).

---

## Prerequisites (before Task 0)

- **VPS:** Ubuntu 22.04 LTS, root SSH access, at least 4 vCPU / 8 GB RAM / 40 GB disk for this P0 single-pair test.
- **Proxy:** One working SOCKS5 or HTTP CONNECT proxy with known credentials. A free trial from any residential proxy vendor or a personal VPN's SOCKS port is fine. Note the `host`, `port`, `type`, `username`, `password` — you'll need them.
- **Local:** scrcpy 2.x installed (`brew install scrcpy` / `apt install scrcpy` / Windows build from GitHub releases).
- **Dev:** Git, your editor. Plan assumes dev happens on your Windows machine at `E:\cloude-phone` and you push to VPS via git (see Task 2 for sync approach).

---

## File Structure

```
E:\cloude-phone\
├── .gitignore
├── README.md
├── docker/
│   └── sidecar/
│       ├── Dockerfile
│       ├── entrypoint.sh
│       ├── redsocks.conf.tpl
│       └── dnscrypt-proxy.toml
└── scripts/
    └── p0/
        ├── check-vps.sh          # idempotent VPS readiness check
        ├── prepare-vps.sh        # one-time VPS setup (root)
        ├── build-sidecar.sh      # local+remote image build
        ├── spawn-sidecar.sh      # spawn ONE sidecar
        ├── spawn-redroid.sh      # spawn ONE redroid joined to a sidecar
        ├── spawn-pair.sh         # convenience: both in order
        ├── test-sidecar-healthy.sh
        ├── test-egress-via-proxy.sh
        ├── test-no-leak.sh
        └── cleanup.sh
```

One responsibility per file. Every script is idempotent (safe to re-run) and exits non-zero on failure.

---

## Task 0: Project scaffold + git init

**Files:**
- Create: `E:\cloude-phone\.gitignore`
- Create: `E:\cloude-phone\README.md`

- [ ] **Step 1:** Initialize git repo locally (Windows dev machine)

Run (in `E:\cloude-phone`):
```bash
git init
git branch -m main
```

Expected: `Initialized empty Git repository in E:/cloude-phone/.git/`

- [ ] **Step 2:** Write `.gitignore`

Create `E:\cloude-phone\.gitignore` with:
```
# Env / secrets
.env
.env.*
!.env.example

# OS
.DS_Store
Thumbs.db

# Editors
.vscode/
.idea/
*.swp

# Python
__pycache__/
*.pyc
.venv/
venv/

# Node
node_modules/
.next/
dist/
build/

# Logs / runtime
*.log
logs/

# Local test artifacts
scripts/p0/*.tmp
```

- [ ] **Step 3:** Write `README.md`

Create `E:\cloude-phone\README.md` with:
```markdown
# Cloud Android — QA Platform

Self-hosted cloud Android platform for app developers, QA engineers, and automation experts. Spawn Android device instances, interact via browser, test with per-instance proxy routing.

**Scope:** Device-diversity QA platform (Genymotion Cloud / BrowserStack style). Explicitly not a detection-evasion tool — see `docs/superpowers/specs/2026-04-20-cloud-android-platform-design.md` §16.

## Layout
- `docs/superpowers/specs/` — design documents
- `docs/superpowers/plans/` — implementation plans
- `docker/` — container image sources
- `scripts/` — operational scripts

## P0 Quick Start

On a fresh Ubuntu 22.04 VPS, clone this repo, then:

```bash
sudo bash scripts/p0/prepare-vps.sh
bash scripts/p0/build-sidecar.sh
bash scripts/p0/spawn-pair.sh \
  --proxy-host YOUR.PROXY.HOST \
  --proxy-port 1080 \
  --proxy-type socks5 \
  --proxy-user USER \
  --proxy-pass PASS
bash scripts/p0/test-egress-via-proxy.sh
bash scripts/p0/test-no-leak.sh
```

Then on your laptop:
```bash
adb connect <VPS_IP>:40000
scrcpy -s <VPS_IP>:40000
```
```

- [ ] **Step 4:** Commit

```bash
git add .gitignore README.md
git commit -m "chore: initial project scaffold"
```

Expected: commit succeeds, 2 files added.

---

## Task 1: VPS readiness check script (write the failing test first)

**Files:**
- Create: `scripts/p0/check-vps.sh`

- [ ] **Step 1:** Write the readiness check — this will FAIL on a fresh VPS

Create `scripts/p0/check-vps.sh`:
```bash
#!/usr/bin/env bash
# Idempotent VPS readiness check. Exits 0 if ready, 1 with reasons if not.
set -u

FAIL=0
ok()   { echo "  OK    $1"; }
fail() { echo "  FAIL  $1"; FAIL=1; }

echo "Checking VPS readiness for Redroid..."

if command -v docker >/dev/null 2>&1; then
  ok "docker installed ($(docker --version | head -c 40))"
else
  fail "docker not installed"
fi

if docker info >/dev/null 2>&1; then
  ok "docker daemon reachable"
else
  fail "docker daemon not running or user not in docker group"
fi

if lsmod 2>/dev/null | grep -qE '^binder_linux'; then
  ok "binder_linux module loaded"
elif grep -q binder /proc/kallsyms 2>/dev/null; then
  ok "binder built into kernel"
else
  fail "binder_linux not available"
fi

if [[ "$(cat /proc/sys/net/ipv4/ip_forward 2>/dev/null || echo 0)" == "1" ]]; then
  ok "net.ipv4.ip_forward = 1"
else
  fail "net.ipv4.ip_forward not enabled"
fi

if [[ $FAIL -eq 0 ]]; then
  echo "VPS READY"
  exit 0
else
  echo "VPS NOT READY — run: sudo bash scripts/p0/prepare-vps.sh"
  exit 1
fi
```

- [ ] **Step 2:** `chmod +x scripts/p0/check-vps.sh` and commit

```bash
chmod +x scripts/p0/check-vps.sh
git add scripts/p0/check-vps.sh
git commit -m "feat(p0): VPS readiness check"
```

- [ ] **Step 3:** Push repo to VPS

On local:
```bash
git remote add vps ssh://root@<VPS_IP>/root/cloude-phone.git   # or use GitHub
# create bare repo on VPS first:
ssh root@<VPS_IP> "git init --bare /root/cloude-phone.git && mkdir -p /root/cloude-phone"
git push vps main
ssh root@<VPS_IP> "cd /root/cloude-phone && git clone /root/cloude-phone.git ."
```

(GitHub private repo + `git pull` on VPS also works — use whatever sync method you prefer. From here on, "on VPS" = `cd /root/cloude-phone` on the VPS.)

- [ ] **Step 4:** Run the check on the (fresh) VPS and confirm it fails

On VPS:
```bash
bash scripts/p0/check-vps.sh
```

Expected on a fresh Ubuntu: FAIL lines for docker and/or binder_linux; final `VPS NOT READY`; exit code 1.

This failing output is the "red test" — Task 2 makes it green.

---

## Task 2: VPS preparation script (make the red test green)

**Files:**
- Create: `scripts/p0/prepare-vps.sh`

- [ ] **Step 1:** Write `prepare-vps.sh`

Create `scripts/p0/prepare-vps.sh`:
```bash
#!/usr/bin/env bash
# One-time VPS setup. Must be run as root. Idempotent.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: must be run as root (use sudo)"; exit 1
fi

echo "[1/4] Installing Docker Engine if missing..."
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
else
  echo "  docker already present"
fi

echo "[2/4] Loading binder_linux kernel module..."
if ! lsmod | grep -qE '^binder_linux'; then
  if modprobe binder_linux num_binders=8 2>/dev/null; then
    echo "  loaded binder_linux"
  elif grep -q binder /proc/kallsyms 2>/dev/null; then
    echo "  binder built into kernel; nothing to load"
  else
    echo "ERROR: binder_linux not available on this kernel ($(uname -r))."
    echo "Use Ubuntu 22.04 generic kernel or newer with binder support."
    exit 1
  fi
fi
modprobe ashmem_linux 2>/dev/null || true

echo "[3/4] Persisting module load across reboots..."
cat >/etc/modules-load.d/redroid.conf <<EOF
binder_linux
ashmem_linux
EOF
echo "options binder_linux num_binders=8" >/etc/modprobe.d/redroid.conf

echo "[4/4] Enabling IP forwarding..."
sysctl -w net.ipv4.ip_forward=1 >/dev/null
grep -qE '^\s*net\.ipv4\.ip_forward\s*=\s*1' /etc/sysctl.conf \
  || echo "net.ipv4.ip_forward=1" >>/etc/sysctl.conf

echo "VPS preparation complete."
```

- [ ] **Step 2:** `chmod +x`, commit, push to VPS

```bash
chmod +x scripts/p0/prepare-vps.sh
git add scripts/p0/prepare-vps.sh
git commit -m "feat(p0): VPS preparation script"
git push vps main
ssh root@<VPS_IP> "cd /root/cloude-phone && git pull"
```

- [ ] **Step 3:** Run it on VPS

On VPS (as root):
```bash
sudo bash scripts/p0/prepare-vps.sh
```

Expected: exits 0 with "VPS preparation complete." Docker install may take ~30 s on first run.

- [ ] **Step 4:** Re-run the readiness check — should now be GREEN

On VPS:
```bash
bash scripts/p0/check-vps.sh
```

Expected: all OK lines, `VPS READY`, exit 0.

If binder_linux load fails: the VPS kernel lacks binder. Either switch provider (Hetzner/DigitalOcean generic Ubuntu 22.04 work) or install `linux-image-generic-hwe-22.04` and reboot. This is a hard blocker for P0 — stop and resolve before continuing.

---

## Task 3: Sidecar — dnscrypt-proxy config (static file)

**Files:**
- Create: `docker/sidecar/dnscrypt-proxy.toml`

- [ ] **Step 1:** Write the dnscrypt-proxy config

Create `docker/sidecar/dnscrypt-proxy.toml`:
```toml
# Minimal dnscrypt-proxy config for sidecar.
# Listens on 127.0.0.1:53 inside the netns.
# Upstream DNS servers are DNSCrypt-capable public resolvers.
# Outbound DNS queries exit via the netns's TCP egress (which iptables
# REDIRECTs to redsocks → user proxy). Thus DNS cannot leak.

listen_addresses = ['127.0.0.1:53']

server_names = ['cloudflare', 'google']

require_dnssec = true
require_nolog = true
require_nofilter = false

# Use TCP so traffic is REDIRECTable by iptables (UDP would be DROP'd)
force_tcp = true

cache = true
cache_size = 4096
cache_min_ttl = 600
cache_max_ttl = 86400

[sources.public-resolvers]
urls = ['https://raw.githubusercontent.com/DNSCrypt/dnscrypt-resolvers/master/v3/public-resolvers.md']
cache_file = '/var/cache/dnscrypt-proxy/public-resolvers.md'
minisign_key = 'RWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3'
refresh_delay = 72
```

- [ ] **Step 2:** Commit

```bash
git add docker/sidecar/dnscrypt-proxy.toml
git commit -m "feat(sidecar): dnscrypt-proxy config (TCP-forced, no leak)"
```

---

## Task 4: Sidecar — redsocks config template

**Files:**
- Create: `docker/sidecar/redsocks.conf.tpl`

- [ ] **Step 1:** Write the redsocks template

Create `docker/sidecar/redsocks.conf.tpl`:
```
base {
  log_debug = off;
  log_info = on;
  log = "stderr";
  daemon = off;
  redirector = iptables;
}

redsocks {
  local_ip = 0.0.0.0;
  local_port = 12345;

  ip = ${PROXY_HOST};
  port = ${PROXY_PORT};

  // type: socks5 | http-connect
  type = ${PROXY_TYPE};

  login = "${PROXY_USER}";
  password = "${PROXY_PASS}";
}
```

Template uses shell-style `${VAR}` substitution — rendered at container start by `envsubst`.

- [ ] **Step 2:** Commit

```bash
git add docker/sidecar/redsocks.conf.tpl
git commit -m "feat(sidecar): redsocks config template"
```

---

## Task 5: Sidecar — entrypoint (iptables + redsocks)

**Files:**
- Create: `docker/sidecar/entrypoint.sh`

- [ ] **Step 1:** Write entrypoint

Create `docker/sidecar/entrypoint.sh`:
```bash
#!/usr/bin/env bash
# Sidecar entrypoint.
# 1. Render redsocks config from env
# 2. Apply iptables rules (TCP→redsocks, DNS→local, else DROP)
# 3. Start dnscrypt-proxy in background
# 4. Exec redsocks in foreground as PID 1
set -euo pipefail

: "${PROXY_HOST:?PROXY_HOST required}"
: "${PROXY_PORT:?PROXY_PORT required}"
: "${PROXY_TYPE:?PROXY_TYPE required (socks5|http-connect)}"
: "${PROXY_USER:=}"
: "${PROXY_PASS:=}"

echo "[sidecar] resolving proxy host to IP (needed for iptables)..."
# iptables needs an IP to build the RETURN rule; hostname lookup at rule-insert
# time is fragile and changes pin to one snapshot. We resolve once here.
PROXY_IP="$(getent hosts "$PROXY_HOST" | awk '{print $1}' | head -n1)"
if [[ -z "$PROXY_IP" ]]; then
  # Fallback: maybe PROXY_HOST is already a literal IP
  if [[ "$PROXY_HOST" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    PROXY_IP="$PROXY_HOST"
  else
    echo "ERROR: could not resolve PROXY_HOST=$PROXY_HOST"; exit 1
  fi
fi
echo "[sidecar] proxy resolved: $PROXY_HOST -> $PROXY_IP"

echo "[sidecar] rendering redsocks.conf..."
export PROXY_HOST PROXY_PORT PROXY_TYPE PROXY_USER PROXY_PASS
envsubst < /etc/redsocks/redsocks.conf.tpl > /etc/redsocks/redsocks.conf

echo "[sidecar] applying iptables rules..."
# Flush any prior state (idempotency if container restarted)
iptables -t nat -F
iptables -t nat -X REDSOCKS 2>/dev/null || true
iptables -F OUTPUT
iptables -P OUTPUT ACCEPT   # temporarily permissive while we build rules

# Chain for TCP redirect
iptables -t nat -N REDSOCKS
iptables -t nat -A REDSOCKS -d 0.0.0.0/8      -j RETURN
iptables -t nat -A REDSOCKS -d 10.0.0.0/8     -j RETURN
iptables -t nat -A REDSOCKS -d 127.0.0.0/8    -j RETURN
iptables -t nat -A REDSOCKS -d 169.254.0.0/16 -j RETURN
iptables -t nat -A REDSOCKS -d 172.16.0.0/12  -j RETURN
iptables -t nat -A REDSOCKS -d 192.168.0.0/16 -j RETURN
# Don't redirect redsocks's own outbound connection to the proxy
iptables -t nat -A REDSOCKS -d "${PROXY_IP}" -p tcp --dport "${PROXY_PORT}" -j RETURN
iptables -t nat -A REDSOCKS -p tcp -j REDIRECT --to-ports 12345
iptables -t nat -A OUTPUT   -p tcp -j REDSOCKS

# Filter OUTPUT: default DROP, selectively allow
iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -p tcp -j ACCEPT                    # goes through REDIRECT above
iptables -A OUTPUT -p udp --dport 53 -d 127.0.0.1 -j ACCEPT
iptables -A OUTPUT -p icmp --icmp-type echo-request -d 127.0.0.1 -j ACCEPT
iptables -P OUTPUT DROP

# Do NOT block inbound on the shared netns — Redroid needs ADB :5555 reachable
iptables -P INPUT ACCEPT

# Point system resolver at dnscrypt-proxy (will exist once it starts)
echo "nameserver 127.0.0.1" > /etc/resolv.conf

echo "[sidecar] starting dnscrypt-proxy..."
mkdir -p /var/cache/dnscrypt-proxy /var/log/dnscrypt-proxy
dnscrypt-proxy -config /etc/dnscrypt-proxy/dnscrypt-proxy.toml &

# Give dnscrypt-proxy time to fetch resolver list on first boot
sleep 3

echo "[sidecar] exec redsocks..."
exec redsocks -c /etc/redsocks/redsocks.conf
```

- [ ] **Step 2:** Commit

```bash
chmod +x docker/sidecar/entrypoint.sh
git add docker/sidecar/entrypoint.sh
git commit -m "feat(sidecar): entrypoint with iptables + redsocks + dnscrypt"
```

---

## Task 6: Sidecar — Dockerfile

**Files:**
- Create: `docker/sidecar/Dockerfile`

- [ ] **Step 1:** Write Dockerfile

Create `docker/sidecar/Dockerfile`:
```dockerfile
FROM alpine:3.20

RUN apk add --no-cache \
      redsocks \
      dnscrypt-proxy \
      iptables \
      ca-certificates \
      bash \
      curl \
      gettext \
      netcat-openbsd \
 && mkdir -p /etc/redsocks /var/cache/dnscrypt-proxy

COPY redsocks.conf.tpl /etc/redsocks/redsocks.conf.tpl
COPY dnscrypt-proxy.toml /etc/dnscrypt-proxy/dnscrypt-proxy.toml
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Sidecar needs to be able to set iptables + edit resolv.conf
# Run will add: --cap-add NET_ADMIN --cap-add NET_RAW

# Healthcheck: redsocks listening on 12345
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=3 \
  CMD nc -z 127.0.0.1 12345 || exit 1

ENTRYPOINT ["/entrypoint.sh"]
```

- [ ] **Step 2:** Commit

```bash
git add docker/sidecar/Dockerfile
git commit -m "feat(sidecar): Dockerfile (alpine + redsocks + dnscrypt)"
```

---

## Task 7: Build script + first build

**Files:**
- Create: `scripts/p0/build-sidecar.sh`

- [ ] **Step 1:** Write build script

Create `scripts/p0/build-sidecar.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

IMAGE="${SIDECAR_IMAGE:-cloude/sidecar:p0}"
CONTEXT="$(cd "$(dirname "$0")/../.." && pwd)/docker/sidecar"

echo "Building $IMAGE from $CONTEXT"
docker build -t "$IMAGE" "$CONTEXT"
echo "Built: $IMAGE"
docker images "$IMAGE"
```

- [ ] **Step 2:** Push to VPS and build there

```bash
chmod +x scripts/p0/build-sidecar.sh
git add scripts/p0/build-sidecar.sh
git commit -m "feat(p0): sidecar build script"
git push vps main
ssh root@<VPS_IP> "cd /root/cloude-phone && git pull && bash scripts/p0/build-sidecar.sh"
```

Expected final line: `cloude/sidecar   p0   <id>   <time>   ~70MB`.

---

## Task 8: Spawn-sidecar-only smoke test (sidecar healthcheck green)

**Files:**
- Create: `scripts/p0/spawn-sidecar.sh`
- Create: `scripts/p0/test-sidecar-healthy.sh`

- [ ] **Step 1:** Write spawn-sidecar script

Create `scripts/p0/spawn-sidecar.sh`:
```bash
#!/usr/bin/env bash
# Usage: spawn-sidecar.sh --name NAME --proxy-host H --proxy-port P
#                        --proxy-type socks5|http-connect
#                        [--proxy-user U --proxy-pass P]
#                        [--adb-port P (host-published ADB port)]
set -euo pipefail

NAME=""
PROXY_HOST=""
PROXY_PORT=""
PROXY_TYPE=""
PROXY_USER=""
PROXY_PASS=""
ADB_PORT="40000"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)        NAME="$2"; shift 2 ;;
    --proxy-host)  PROXY_HOST="$2"; shift 2 ;;
    --proxy-port)  PROXY_PORT="$2"; shift 2 ;;
    --proxy-type)  PROXY_TYPE="$2"; shift 2 ;;
    --proxy-user)  PROXY_USER="$2"; shift 2 ;;
    --proxy-pass)  PROXY_PASS="$2"; shift 2 ;;
    --adb-port)    ADB_PORT="$2"; shift 2 ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done

: "${NAME:?--name required}"
: "${PROXY_HOST:?--proxy-host required}"
: "${PROXY_PORT:?--proxy-port required}"
: "${PROXY_TYPE:?--proxy-type required}"

IMAGE="${SIDECAR_IMAGE:-cloude/sidecar:p0}"

# Remove any stale container with this name (idempotency)
docker rm -f "$NAME" 2>/dev/null || true

docker run -d \
  --name "$NAME" \
  --cap-add NET_ADMIN --cap-add NET_RAW \
  --sysctl net.ipv4.ip_forward=1 \
  -p "${ADB_PORT}:5555" \
  -e PROXY_HOST="$PROXY_HOST" \
  -e PROXY_PORT="$PROXY_PORT" \
  -e PROXY_TYPE="$PROXY_TYPE" \
  -e PROXY_USER="$PROXY_USER" \
  -e PROXY_PASS="$PROXY_PASS" \
  "$IMAGE"

echo "Sidecar started: $NAME (ADB will be exposed on host:$ADB_PORT once redroid joins)"
```

- [ ] **Step 2:** Write health test — this defines "sidecar works alone"

Create `scripts/p0/test-sidecar-healthy.sh`:
```bash
#!/usr/bin/env bash
# Asserts that a named sidecar reaches healthy state within 30s.
set -euo pipefail

NAME="${1:?usage: $0 <sidecar-container-name>}"

echo "Waiting for $NAME to become healthy..."
for i in $(seq 1 30); do
  status=$(docker inspect --format '{{.State.Health.Status}}' "$NAME" 2>/dev/null || echo "missing")
  if [[ "$status" == "healthy" ]]; then
    echo "OK: $NAME healthy in ${i}s"
    exit 0
  fi
  sleep 1
done

echo "FAIL: $NAME did not become healthy. Status: $status"
docker logs --tail=50 "$NAME"
exit 1
```

- [ ] **Step 3:** chmod, commit, push, run on VPS

```bash
chmod +x scripts/p0/spawn-sidecar.sh scripts/p0/test-sidecar-healthy.sh
git add scripts/p0/spawn-sidecar.sh scripts/p0/test-sidecar-healthy.sh
git commit -m "feat(p0): sidecar spawn + health test"
git push vps main
```

On VPS:
```bash
cd /root/cloude-phone && git pull
bash scripts/p0/spawn-sidecar.sh \
  --name p0-sidecar \
  --proxy-host YOUR.PROXY.HOST \
  --proxy-port 1080 \
  --proxy-type socks5 \
  --proxy-user YOURUSER --proxy-pass YOURPASS
bash scripts/p0/test-sidecar-healthy.sh p0-sidecar
```

Expected: `OK: p0-sidecar healthy in Ns` (N ≤ 15).

If unhealthy: `docker logs p0-sidecar` — likely redsocks failed to connect to proxy (bad creds / host) or dnscrypt-proxy couldn't fetch resolvers (first-boot DNS bootstrap).

---

## Task 9: Egress test using lightweight container (proves proxy works, Redroid not yet involved)

**Files:**
- Create: `scripts/p0/test-egress-via-proxy.sh`

- [ ] **Step 1:** Write the egress test

Create `scripts/p0/test-egress-via-proxy.sh`:
```bash
#!/usr/bin/env bash
# Spawns a throwaway alpine container into the sidecar's netns
# and compares its public IP vs the host's public IP.
# They MUST differ, AND the alpine container's IP MUST match the proxy exit IP.
set -euo pipefail

SIDECAR="${1:-p0-sidecar}"
EXPECTED_PROXY_EGRESS_IP="${2:-}"   # optional; if given, asserted exactly

echo "Host public IP:"
HOST_IP=$(curl -fsS --max-time 10 https://ifconfig.me || echo "HOST_IP_ERROR")
echo "  $HOST_IP"

echo "Container-via-sidecar public IP:"
# --dns 127.0.0.1: when joining sidecar's netns, Docker's default 127.0.0.11
# resolver is not reachable in that netns. The sidecar's dnscrypt-proxy is.
CONTAINER_IP=$(docker run --rm \
  --network="container:${SIDECAR}" \
  --dns 127.0.0.1 \
  alpine:3.20 \
  sh -c 'apk add --no-cache curl >/dev/null 2>&1 && curl -fsS --max-time 15 https://ifconfig.me')
echo "  $CONTAINER_IP"

if [[ "$HOST_IP" == "$CONTAINER_IP" ]]; then
  echo "FAIL: container IP matches host IP — traffic NOT going through proxy"
  exit 1
fi

if [[ -n "$EXPECTED_PROXY_EGRESS_IP" && "$CONTAINER_IP" != "$EXPECTED_PROXY_EGRESS_IP" ]]; then
  echo "FAIL: container IP ($CONTAINER_IP) != expected proxy IP ($EXPECTED_PROXY_EGRESS_IP)"
  exit 1
fi

echo "OK: egress correctly routed via proxy"
```

- [ ] **Step 2:** chmod, commit, push, run on VPS

```bash
chmod +x scripts/p0/test-egress-via-proxy.sh
git add scripts/p0/test-egress-via-proxy.sh
git commit -m "test(p0): egress-via-proxy validation"
git push vps main
```

On VPS:
```bash
cd /root/cloude-phone && git pull
bash scripts/p0/test-egress-via-proxy.sh p0-sidecar
```

Expected: `OK: egress correctly routed via proxy`. Container IP must differ from host IP.

If container IP == host IP: iptables rules didn't apply. Inspect: `docker exec p0-sidecar iptables -t nat -L -n -v`.

---

## Task 10: No-leak test (sidecar dies → zero egress)

**Files:**
- Create: `scripts/p0/test-no-leak.sh`

- [ ] **Step 1:** Write the leak test

Create `scripts/p0/test-no-leak.sh`:
```bash
#!/usr/bin/env bash
# Stops redsocks inside the sidecar, then verifies a joined container
# cannot reach the internet. Restores sidecar at end.
set -euo pipefail

SIDECAR="${1:-p0-sidecar}"

echo "Killing redsocks inside $SIDECAR (iptables+DROP policy should stop egress)..."
docker exec "$SIDECAR" sh -c 'pkill -STOP redsocks || true'

echo "Attempting egress from joined container (should TIMEOUT)..."
set +e
OUT=$(docker run --rm --network="container:${SIDECAR}" --dns 127.0.0.1 alpine:3.20 \
  sh -c 'apk add --no-cache curl >/dev/null 2>&1 && curl -fsS --max-time 8 https://ifconfig.me' 2>&1)
RC=$?
set -e

echo "Resuming redsocks..."
docker exec "$SIDECAR" sh -c 'pkill -CONT redsocks || true'

if [[ $RC -eq 0 ]]; then
  echo "FAIL: egress succeeded despite stopped redsocks — LEAK"
  echo "Output: $OUT"
  exit 1
fi

echo "OK: no leak detected (rc=$RC, expected curl failure)"
```

- [ ] **Step 2:** chmod, commit, push, run on VPS

```bash
chmod +x scripts/p0/test-no-leak.sh
git add scripts/p0/test-no-leak.sh
git commit -m "test(p0): fail-closed / no-leak validation"
git push vps main
```

On VPS:
```bash
cd /root/cloude-phone && git pull
bash scripts/p0/test-no-leak.sh p0-sidecar
```

Expected: `OK: no leak detected`.

If leak: the OUTPUT chain default policy isn't DROP, or RETURN targets above REDIRECT were too permissive. Re-inspect `iptables -L -n -v`.

---

## Task 11: Spawn Redroid joined to sidecar netns

**Files:**
- Create: `scripts/p0/spawn-redroid.sh`

- [ ] **Step 1:** Write spawn-redroid script

Create `scripts/p0/spawn-redroid.sh`:
```bash
#!/usr/bin/env bash
# Usage: spawn-redroid.sh --name NAME --sidecar SIDECAR_NAME
#                        [--width 1080 --height 2340 --dpi 420]
#                        [--ram-mb 4096 --cpus 4]
#                        [--model Pixel_5 --manufacturer Google]
set -euo pipefail

NAME=""
SIDECAR=""
WIDTH="1080"
HEIGHT="2340"
DPI="420"
RAM_MB="4096"
CPUS="4"
MODEL="Pixel_5"
MANUFACTURER="Google"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)          NAME="$2"; shift 2 ;;
    --sidecar)       SIDECAR="$2"; shift 2 ;;
    --width)         WIDTH="$2"; shift 2 ;;
    --height)        HEIGHT="$2"; shift 2 ;;
    --dpi)           DPI="$2"; shift 2 ;;
    --ram-mb)        RAM_MB="$2"; shift 2 ;;
    --cpus)          CPUS="$2"; shift 2 ;;
    --model)         MODEL="$2"; shift 2 ;;
    --manufacturer)  MANUFACTURER="$2"; shift 2 ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done

: "${NAME:?--name required}"
: "${SIDECAR:?--sidecar required}"

IMAGE="${REDROID_IMAGE:-redroid/redroid:11.0.0_64only-latest}"
VOLUME="${NAME}-data"

docker volume create "$VOLUME" >/dev/null

docker rm -f "$NAME" 2>/dev/null || true

docker run -d \
  --name "$NAME" \
  --network="container:${SIDECAR}" \
  --privileged \
  --memory="${RAM_MB}m" --cpus="$CPUS" \
  -v "${VOLUME}:/data" \
  "$IMAGE" \
  androidboot.redroid_width="$WIDTH" \
  androidboot.redroid_height="$HEIGHT" \
  androidboot.redroid_dpi="$DPI" \
  androidboot.redroid_gpu_mode=guest \
  ro.product.model="$MODEL" \
  ro.product.manufacturer="$MANUFACTURER" \
  net.dns1=127.0.0.1 \
  net.dns2=127.0.0.1

# net.dns1/2: point Android's system resolver at the sidecar's dnscrypt-proxy.
# Required because the sidecar's netns has no DHCP and Android's default 8.8.8.8
# DNS uses UDP, which our iptables policy drops (only localhost UDP:53 allowed).
echo "Redroid started: $NAME (joined netns of $SIDECAR, data volume $VOLUME)"
```

- [ ] **Step 2:** chmod, commit, push

```bash
chmod +x scripts/p0/spawn-redroid.sh
git add scripts/p0/spawn-redroid.sh
git commit -m "feat(p0): redroid spawn joined to sidecar netns"
git push vps main
```

---

## Task 12: Pair-spawn + end-to-end Android egress validation

**Files:**
- Create: `scripts/p0/spawn-pair.sh`

- [ ] **Step 1:** Write pair orchestration script

Create `scripts/p0/spawn-pair.sh`:
```bash
#!/usr/bin/env bash
# Spawns a sidecar + redroid pair with default P0 names.
# Waits for ADB boot-complete from inside Android.
set -euo pipefail

PROXY_HOST=""; PROXY_PORT=""; PROXY_TYPE=""
PROXY_USER=""; PROXY_PASS=""
ADB_PORT="40000"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --proxy-host) PROXY_HOST="$2"; shift 2 ;;
    --proxy-port) PROXY_PORT="$2"; shift 2 ;;
    --proxy-type) PROXY_TYPE="$2"; shift 2 ;;
    --proxy-user) PROXY_USER="$2"; shift 2 ;;
    --proxy-pass) PROXY_PASS="$2"; shift 2 ;;
    --adb-port)   ADB_PORT="$2"; shift 2 ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done

: "${PROXY_HOST:?--proxy-host required}"
: "${PROXY_PORT:?--proxy-port required}"
: "${PROXY_TYPE:?--proxy-type required}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[1/3] Spawning sidecar..."
bash "$SCRIPT_DIR/spawn-sidecar.sh" \
  --name p0-sidecar \
  --proxy-host "$PROXY_HOST" --proxy-port "$PROXY_PORT" --proxy-type "$PROXY_TYPE" \
  --proxy-user "$PROXY_USER" --proxy-pass "$PROXY_PASS" \
  --adb-port "$ADB_PORT"

bash "$SCRIPT_DIR/test-sidecar-healthy.sh" p0-sidecar

echo "[2/3] Spawning redroid..."
bash "$SCRIPT_DIR/spawn-redroid.sh" --name p0-redroid --sidecar p0-sidecar

echo "[3/3] Waiting for Android to boot (up to 120s)..."
for i in $(seq 1 60); do
  if docker exec p0-redroid sh -c 'getprop sys.boot_completed 2>/dev/null' | grep -q 1; then
    echo "OK: Android booted in $((i*2))s"
    echo "Run: adb connect <VPS_IP>:$ADB_PORT"
    exit 0
  fi
  sleep 2
done

echo "FAIL: Android did not reach boot_completed in 120s"
docker logs --tail=50 p0-redroid
exit 1
```

- [ ] **Step 2:** chmod, commit, push, run on VPS

```bash
chmod +x scripts/p0/spawn-pair.sh
git add scripts/p0/spawn-pair.sh
git commit -m "feat(p0): pair spawn script with boot wait"
git push vps main
```

On VPS — first destroy earlier containers:
```bash
cd /root/cloude-phone && git pull
docker rm -f p0-sidecar p0-redroid 2>/dev/null || true

bash scripts/p0/spawn-pair.sh \
  --proxy-host YOUR.PROXY.HOST --proxy-port 1080 --proxy-type socks5 \
  --proxy-user USER --proxy-pass PASS \
  --adb-port 40000
```

Expected: `OK: Android booted in Ns` (N typically 30-60).

- [ ] **Step 3:** Validate Android-internal egress uses proxy

On VPS:
```bash
# Install adb if missing on VPS
apt-get install -y android-tools-adb

adb connect 127.0.0.1:40000
sleep 2
adb devices   # should list 127.0.0.1:40000 as "device"

# Redroid has no curl/wget by default, but it has toybox nc.
# Use raw HTTP over nc — ifconfig.me's plain-text response ends with the IP.
# Also validate DNS works (i.e., net.dns1 routing works).
ANDROID_IP=$(adb -s 127.0.0.1:40000 shell \
  'printf "GET / HTTP/1.0\r\nHost: ifconfig.me\r\nUser-Agent: curl\r\n\r\n" \
   | toybox nc -w 10 ifconfig.me 80 | tail -1' | tr -d '\r\n')
HOST_IP=$(curl -s --max-time 10 https://ifconfig.me)

echo "Android sees: $ANDROID_IP"
echo "Host sees:    $HOST_IP"
if [[ -z "$ANDROID_IP" ]]; then
  echo "FAIL: Android got no response (DNS or egress broken)"; exit 1
fi
if [[ "$ANDROID_IP" == "$HOST_IP" ]]; then
  echo "FAIL: Android egress not proxied"; exit 1
fi
echo "OK: Android egress correctly proxied"
```

Expected: two different IPs; the Android one equals the proxy's exit IP.

If Android shows empty: DNS probably failing. Verify:
```bash
adb -s 127.0.0.1:40000 shell getprop net.dns1
# should print: 127.0.0.1
```
If it's different, the boot prop didn't stick — inspect Redroid's boot logs: `docker logs p0-redroid | grep -i dns`.

---

## Task 13: scrcpy desktop validation

**Files:** (no new files — manual validation step)

- [ ] **Step 1:** On your LOCAL laptop, connect ADB to the VPS

Local terminal:
```bash
adb connect <VPS_IP>:40000
adb devices
```

Expected: `<VPS_IP>:40000   device` (not `unauthorized` — Redroid accepts any ADB by default in P0).

- [ ] **Step 2:** Launch scrcpy

Local terminal:
```bash
scrcpy -s <VPS_IP>:40000 --max-size 1080 --max-fps 30
```

Expected: a window opens showing Android 11 home screen; you can click/scroll with mouse; keyboard works.

- [ ] **Step 3:** Record your P0 validation proof

Take a screenshot of:
1. scrcpy window showing Android home
2. Terminal with "Android sees: X" ≠ "Host sees: Y" output

Save under `docs/superpowers/plans/p0-validation/` (create dir). Commit:
```bash
mkdir -p docs/superpowers/plans/p0-validation
# drop screenshots in there
git add docs/superpowers/plans/p0-validation/
git commit -m "docs(p0): validation proof screenshots"
```

---

## Task 14: Cleanup script

**Files:**
- Create: `scripts/p0/cleanup.sh`

- [ ] **Step 1:** Write cleanup

Create `scripts/p0/cleanup.sh`:
```bash
#!/usr/bin/env bash
# Remove the P0 pair + its data volume. Idempotent.
set -euo pipefail

docker rm -f p0-redroid p0-sidecar 2>/dev/null || true
docker volume rm p0-redroid-data 2>/dev/null || true
echo "P0 pair removed."
```

- [ ] **Step 2:** chmod, commit, push

```bash
chmod +x scripts/p0/cleanup.sh
git add scripts/p0/cleanup.sh
git commit -m "feat(p0): cleanup script"
git push vps main
```

---

## Task 15: README update + P0 closeout

**Files:**
- Modify: `README.md`
- Create: `docs/superpowers/plans/p0-validation/RESULTS.md`

- [ ] **Step 1:** Write results file

Create `docs/superpowers/plans/p0-validation/RESULTS.md`:
```markdown
# P0 Validation Results

**Date:** <YYYY-MM-DD>
**VPS:** <provider, kernel version, e.g. DigitalOcean Ubuntu 22.04, kernel 5.15.0-xx>
**Proxy:** <type, provider name — not credentials>

## Success criteria (from design spec §17)

- [x] One Redroid + sidecar pair spawned via `spawn-pair.sh`
- [x] `adb shell curl ifconfig.me` returns configured proxy's public IP
- [x] Stopping redsocks results in zero egress from Redroid (test-no-leak.sh green)
- [x] Desktop scrcpy connects and displays home screen

## Recorded IPs
- Host public IP:   <xxx.xxx.xxx.xxx>
- Android-seen IP:  <yyy.yyy.yyy.yyy>  (matches proxy exit)

## Timings
- `prepare-vps.sh` runtime: <Xs>
- Sidecar healthy: <Xs> after spawn
- Android boot_completed: <Xs> after spawn

## Issues encountered
- <any; or "none">

## Ready for P1: YES / NO
```

- [ ] **Step 2:** Update README with validated commands

Replace the "P0 Quick Start" section in `README.md` with:
```markdown
## P0 Quick Start (validated <DATE>)

Fresh Ubuntu 22.04 VPS:

```bash
git clone <repo> /root/cloude-phone && cd /root/cloude-phone
sudo bash scripts/p0/prepare-vps.sh
bash scripts/p0/check-vps.sh         # VPS READY
bash scripts/p0/build-sidecar.sh

bash scripts/p0/spawn-pair.sh \
  --proxy-host YOUR.PROXY.HOST --proxy-port 1080 --proxy-type socks5 \
  --proxy-user USER --proxy-pass PASS \
  --adb-port 40000

bash scripts/p0/test-egress-via-proxy.sh p0-sidecar
bash scripts/p0/test-no-leak.sh p0-sidecar
```

Laptop:
```bash
adb connect <VPS_IP>:40000
scrcpy -s <VPS_IP>:40000 --max-size 1080
```

Cleanup: `bash scripts/p0/cleanup.sh`
```

- [ ] **Step 3:** Commit P0 closeout

```bash
git add README.md docs/superpowers/plans/p0-validation/RESULTS.md
git commit -m "docs(p0): validation results + updated README"
git push vps main
git tag p0-complete
git push vps p0-complete
```

---

## Completion Criteria

P0 is done when all of the following are green on the target VPS:

1. `bash scripts/p0/check-vps.sh` → `VPS READY`
2. `bash scripts/p0/test-sidecar-healthy.sh p0-sidecar` → `OK`
3. `bash scripts/p0/test-egress-via-proxy.sh p0-sidecar` → `OK: egress correctly routed via proxy`
4. `bash scripts/p0/test-no-leak.sh p0-sidecar` → `OK: no leak detected`
5. In-Android `curl ifconfig.me` (via ADB shell) returns the proxy exit IP, not the host IP
6. scrcpy desktop from a laptop displays Android 11 home screen
7. `docs/superpowers/plans/p0-validation/RESULTS.md` filled with actual timings and IPs
8. Git tag `p0-complete` pushed

## What's NOT in P0 (reminder)

- ❌ No API server, no dashboard, no auth, no Postgres, no Redis
- ❌ No browser-based streaming (desktop scrcpy only)
- ❌ No multi-device orchestration (exactly ONE pair at a time)
- ❌ No automated tests beyond the shell scripts above
- ❌ No Magisk, Shamiko, attestation-bypass (permanent non-goal per spec §16)

These are P1 work. A separate plan file (`2026-04-20-cloud-android-platform-p1.md`) will be written once P0 is validated complete — because P1 decisions depend on P0 learnings (actual boot timings, proxy behavior quirks, kernel compatibility on your chosen VPS).

---

*End of P0 plan.*
