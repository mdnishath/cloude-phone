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

# Sidecar needs to write iptables + resolv.conf.
# Run with: --cap-add NET_ADMIN --cap-add NET_RAW

# Healthcheck: redsocks listening on 12345 means config parsed + upstream connect likely OK.
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=3 \
  CMD nc -z 127.0.0.1 12345 || exit 1

ENTRYPOINT ["/entrypoint.sh"]
