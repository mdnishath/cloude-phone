#!/usr/bin/env bash
# One-time setup that runs when the Codespace is created.
# Brings up the full P1a stack and prints test credentials.

set -euo pipefail

cd "$(dirname "$0")/.."

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo " Cloude Phone P1a — Codespace post-create setup"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# 1. Wait for Docker daemon to be ready (docker-in-docker takes ~30s)
echo "[1/8] Waiting for Docker daemon..."
for i in $(seq 1 60); do
  if docker info >/dev/null 2>&1; then
    echo "      Docker is up after ${i}s"
    break
  fi
  sleep 1
done
docker info >/dev/null 2>&1 || { echo "ERROR: Docker daemon never came up"; exit 1; }

# 2. Install Python deps for the host (just for invite/key generation)
echo "[2/8] Installing host Python deps..."
pip install --quiet pynacl 2>&1 | tail -3

# 3. Generate .env if missing
echo "[3/8] Generating .env..."
if [ ! -f .env ]; then
  cp .env.example .env
  python3 -c "import secrets;print('JWT_SECRET=' + secrets.token_urlsafe(64))" >> .env
  python3 -c "import secrets;print('STREAM_TOKEN_SECRET=' + secrets.token_urlsafe(64))" >> .env
  KEYS=$(python3 -c "
import nacl.public, base64
sk = nacl.public.PrivateKey.generate()
print(f'ENCRYPTION_PUBLIC_KEY={base64.b64encode(bytes(sk.public_key)).decode()}')
print(f'ENCRYPTION_PRIVATE_KEY={base64.b64encode(bytes(sk)).decode()}')
")
  # Replace placeholder keys in .env
  sed -i '/^ENCRYPTION_PUBLIC_KEY=/d;/^ENCRYPTION_PRIVATE_KEY=/d' .env
  echo "$KEYS" >> .env
  echo "      .env created with fresh secrets"
else
  echo "      .env already exists"
fi

# 4. Build + start stack
echo "[4/8] docker compose up -d --build (this takes 2-3 min on first run)..."
docker compose up -d --build

# 5. Wait for postgres + redis healthy
echo "[5/8] Waiting for postgres + redis healthchecks..."
for i in $(seq 1 60); do
  pg=$(docker inspect --format '{{.State.Health.Status}}' cloude-postgres 2>/dev/null || echo "starting")
  re=$(docker inspect --format '{{.State.Health.Status}}' cloude-redis 2>/dev/null || echo "starting")
  if [ "$pg" = "healthy" ] && [ "$re" = "healthy" ]; then
    echo "      postgres + redis healthy after ${i}s"
    break
  fi
  sleep 1
done

# 6. Run migrations
echo "[6/8] Running alembic migrations..."
docker compose exec -T api alembic upgrade head

# 7. Seed profiles
echo "[7/8] Seeding 6 device profiles..."
docker compose exec -T api python scripts/seed_profiles.py

# 8. Mint admin invite + redeem to create test user
echo "[8/8] Creating test admin user..."
INVITE_OUT=$(docker compose exec -T api python scripts/make_invite.py --role admin --ttl-hours 24)
INVITE_TOKEN=$(echo "$INVITE_OUT" | grep -E '^\s*token:' | awk '{print $2}')

# Wait for /healthz before redeeming
for i in $(seq 1 30); do
  if curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

EMAIL="admin@codespace.test"
PASSWORD="codespace-test-pw-$(date +%s)"
REDEEM=$(curl -fsS -X POST http://localhost:8000/api/v1/auth/redeem-invite \
  -H "content-type: application/json" \
  -d "{\"token\":\"$INVITE_TOKEN\",\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" 2>&1) || {
    echo "WARN: redeem failed — try running 'bash scripts/p1a/test-stack.sh' manually"
    REDEEM='{"access":"see-logs","refresh":"see-logs"}'
  }
ACCESS=$(echo "$REDEEM" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('access','see-logs'))" 2>/dev/null || echo "see-logs")

# Save credentials so postAttachCommand can show them
cat > /tmp/cloude-creds.txt <<EOF

═══════════════════════════════════════════════════════════════
  ✅ Cloude Phone P1a — STACK READY!
═══════════════════════════════════════════════════════════════

  📍 Open in browser:
     • Swagger UI:  https://\${CODESPACE_NAME}-8000.\${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}/api/docs
     • Health:      https://\${CODESPACE_NAME}-8000.\${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}/healthz

  🔑 Test user (already redeemed an admin invite):
     • Email:    $EMAIL
     • Password: $PASSWORD

  🎫 Bearer token (paste into Swagger "Authorize" or use with curl):
     $ACCESS

  🧪 Run full test sweep:
     bash scripts/p1a/test-stack.sh
     # but wait — stack already up, this will skip env setup

  📊 View logs:
     docker compose logs -f api worker

  🗑️  Cleanup:
     docker compose down -v

═══════════════════════════════════════════════════════════════
EOF

# Substitute environment variables in the URLs (CODESPACE_NAME etc.)
envsubst < /tmp/cloude-creds.txt > /tmp/cloude-creds-final.txt
mv /tmp/cloude-creds-final.txt /tmp/cloude-creds.txt

cat /tmp/cloude-creds.txt
