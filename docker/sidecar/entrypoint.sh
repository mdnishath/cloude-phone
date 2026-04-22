#!/usr/bin/env bash
# Sidecar entrypoint.
#
# 1. Resolve PROXY_HOST -> PROXY_IP (iptables needs an IP)
# 2. Render redsocks.conf from template
# 3. Apply iptables rules: TCP -> redsocks :12345, DNS -> localhost, else DROP
# 4. Start dnscrypt-proxy in background (listens on 127.0.0.1:53)
# 5. Exec redsocks in foreground as PID 1
set -euo pipefail

: "${PROXY_HOST:?PROXY_HOST required}"
: "${PROXY_PORT:?PROXY_PORT required}"
: "${PROXY_TYPE:?PROXY_TYPE required (socks5|http-connect)}"
: "${PROXY_USER:=}"
: "${PROXY_PASS:=}"

echo "[sidecar] resolving proxy host to IP (iptables needs a literal IP)..."
PROXY_IP="$(getent hosts "$PROXY_HOST" | awk '{print $1}' | head -n1)"
if [[ -z "$PROXY_IP" ]]; then
  if [[ "$PROXY_HOST" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    PROXY_IP="$PROXY_HOST"
  else
    echo "ERROR: could not resolve PROXY_HOST=$PROXY_HOST"; exit 1
  fi
fi
echo "[sidecar] proxy resolved: $PROXY_HOST -> $PROXY_IP"

echo "[sidecar] rendering redsocks.conf from template..."
export PROXY_HOST PROXY_PORT PROXY_TYPE PROXY_USER PROXY_PASS
envsubst < /etc/redsocks/redsocks.conf.tpl > /etc/redsocks/redsocks.conf

echo "[sidecar] applying iptables rules..."

# Idempotent reset (in case container restarted without full wipe)
iptables -t nat -F
iptables -t nat -X REDSOCKS 2>/dev/null || true
iptables -F OUTPUT
iptables -P OUTPUT ACCEPT  # permissive while we build rules; tightened at end

# -- NAT table: REDSOCKS chain + hook from OUTPUT --
iptables -t nat -N REDSOCKS
iptables -t nat -A REDSOCKS -d 0.0.0.0/8      -j RETURN
iptables -t nat -A REDSOCKS -d 10.0.0.0/8     -j RETURN
iptables -t nat -A REDSOCKS -d 127.0.0.0/8    -j RETURN
iptables -t nat -A REDSOCKS -d 169.254.0.0/16 -j RETURN
iptables -t nat -A REDSOCKS -d 172.16.0.0/12  -j RETURN
iptables -t nat -A REDSOCKS -d 192.168.0.0/16 -j RETURN
# Don't redirect redsocks's own upstream connection to the proxy
iptables -t nat -A REDSOCKS -d "${PROXY_IP}" -p tcp --dport "${PROXY_PORT}" -j RETURN
iptables -t nat -A REDSOCKS -p tcp -j REDIRECT --to-ports 12345
iptables -t nat -A OUTPUT   -p tcp -j REDSOCKS

# -- Filter table: default DROP, selectively allow --
iptables -A OUTPUT -o lo -j ACCEPT                                # localhost
iptables -A OUTPUT -p tcp -j ACCEPT                               # (already REDIRECT'd above)
iptables -A OUTPUT -p udp --dport 53 -d 127.0.0.1 -j ACCEPT       # local dnscrypt
iptables -A OUTPUT -p icmp --icmp-type echo-request -d 127.0.0.1 -j ACCEPT
iptables -P OUTPUT DROP                                           # fail-closed default

# INPUT must stay open: Redroid publishes ADB :5555 through the sidecar's port map
iptables -P INPUT ACCEPT

echo "[sidecar] pointing resolver at local dnscrypt-proxy..."
echo "nameserver 127.0.0.1" > /etc/resolv.conf

echo "[sidecar] starting dnscrypt-proxy in background..."
mkdir -p /var/cache/dnscrypt-proxy /var/log/dnscrypt-proxy
dnscrypt-proxy -config /etc/dnscrypt-proxy/dnscrypt-proxy.toml &

# Give dnscrypt-proxy a moment to fetch the resolver list (first boot)
sleep 3

echo "[sidecar] exec redsocks (PID 1)..."
exec redsocks -c /etc/redsocks/redsocks.conf
