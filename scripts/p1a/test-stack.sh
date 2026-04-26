#!/usr/bin/env bash
# Full P1a stack E2E test.
# Brings up docker compose, runs migrations, seeds profiles, mints invite,
# redeems it, logs in, hits /me, lists profiles, creates a device, polls
# until worker stub flips it to running, and finally fetches adb-info +
# stream-token.
#
# Usage:
#   bash scripts/p1a/test-stack.sh
#
# Prereqs:
#   - Docker Desktop running.
#   - .env populated (this script will auto-populate if missing).
#
# Exit codes:
#   0 — green
#   1 — generic failure
#   2 — Docker not available

set -euo pipefail

cd "$(dirname "$0")/../.."

# Python binary — Ubuntu often has python3 only, no `python` alias
PY=$(command -v python3 || command -v python)
if [ -z "$PY" ]; then
  echo "ERROR: Python 3 not found on PATH. Install: sudo apt install python3"
  exit 1
fi

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

step() { echo -e "\n${YELLOW}▶${NC} $1"; }
ok()   { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }

# --- 0. Prereq check ----------------------------------------------------
step "Docker check"
if ! command -v docker >/dev/null; then
  echo -e "${RED}Docker not found.${NC} Install Docker Desktop first."
  exit 2
fi
if ! docker info >/dev/null 2>&1; then
  echo -e "${RED}Docker daemon not running.${NC} Start Docker Desktop."
  exit 2
fi
ok "Docker is up"

# --- 1. Generate .env if missing ---------------------------------------
step ".env setup"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "" >> .env
  echo "# auto-generated $(date)" >> .env
  $PY -c "import secrets;print('JWT_SECRET=' + secrets.token_urlsafe(64))" >> .env
  $PY -c "import secrets;print('STREAM_TOKEN_SECRET=' + secrets.token_urlsafe(64))" >> .env
  ok "Created .env from template"
else
  ok ".env already exists, leaving it alone"
fi

# Generate libsodium keypair via Docker if not yet present in .env
if grep -q '^ENCRYPTION_PUBLIC_KEY=replace_me' .env 2>/dev/null \
   || grep -q '^ENCRYPTION_PUBLIC_KEY=AAAA' .env 2>/dev/null \
   || ! grep -qE '^ENCRYPTION_PUBLIC_KEY=[A-Za-z0-9+/=]{40,}' .env 2>/dev/null; then
  step "Generate libsodium keypair (one-off Docker run with pynacl)"
  KEYS=$(docker run --rm python:3.11-slim sh -c \
    'pip install -q pynacl >/dev/null 2>&1 && python -c "
import nacl.public, base64
sk = nacl.public.PrivateKey.generate()
print(\"ENCRYPTION_PUBLIC_KEY=\" + base64.b64encode(bytes(sk.public_key)).decode())
print(\"ENCRYPTION_PRIVATE_KEY=\" + base64.b64encode(bytes(sk)).decode())
"')
  # Strip old placeholders, append fresh
  sed -i.bak '/^ENCRYPTION_PUBLIC_KEY=/d;/^ENCRYPTION_PRIVATE_KEY=/d' .env
  echo "$KEYS" >> .env
  rm -f .env.bak
  ok "libsodium keypair written to .env"
fi

# --- 2. Bring stack up --------------------------------------------------
step "docker compose up -d --build (this may take 2-3 min on first run)"
docker compose up -d --build
ok "Stack started"

step "Wait for postgres + redis healthy"
for i in $(seq 1 30); do
  pg=$(docker inspect --format '{{.State.Health.Status}}' cloude-postgres 2>/dev/null || echo "starting")
  re=$(docker inspect --format '{{.State.Health.Status}}' cloude-redis 2>/dev/null || echo "starting")
  if [ "$pg" = "healthy" ] && [ "$re" = "healthy" ]; then
    ok "postgres + redis healthy ($i s)"
    break
  fi
  sleep 1
done
[ "$pg" = "healthy" ] || fail "postgres not healthy after 30s"
[ "$re" = "healthy" ] || fail "redis not healthy after 30s"

# --- 3. Apply migrations ------------------------------------------------
step "alembic upgrade head"
docker compose exec -T api alembic upgrade head
ok "Migrations applied"

# --- 4. Seed device profiles --------------------------------------------
step "Seed 6 public device profiles"
docker compose exec -T api python scripts/seed_profiles.py
ok "Profiles seeded"

# --- 5. Mint an admin invite --------------------------------------------
step "Mint admin invite (1h TTL)"
INVITE_OUT=$(docker compose exec -T api python scripts/make_invite.py --role admin --ttl-hours 1)
INVITE_TOKEN=$(echo "$INVITE_OUT" | grep -E '^\s*token:' | awk '{print $2}')
[ -n "$INVITE_TOKEN" ] || fail "Could not parse invite token from script output"
ok "Invite minted (token first 8 chars: ${INVITE_TOKEN:0:8}...)"

# --- 6. Wait for API healthz -------------------------------------------
step "Wait for /healthz"
for i in $(seq 1 30); do
  if curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then
    ok "/healthz responding ($i s)"
    break
  fi
  sleep 1
done

# --- 7. Redeem invite ---------------------------------------------------
step "Redeem invite"
EMAIL="admin-test-$(date +%s)@example.com"
PASSWORD="test-password-$(date +%s)"
REDEEM=$(curl -fsS -X POST http://localhost:8000/api/v1/auth/redeem-invite \
  -H "content-type: application/json" \
  -d "{\"token\":\"$INVITE_TOKEN\",\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
ACCESS=$(echo "$REDEEM" | $PY -c "import json,sys;print(json.load(sys.stdin)['access'])")
REFRESH=$(echo "$REDEEM" | $PY -c "import json,sys;print(json.load(sys.stdin)['refresh'])")
[ -n "$ACCESS" ] || fail "No access token returned"
ok "Redeemed → access token ${ACCESS:0:20}..."

# --- 8. Hit /me ---------------------------------------------------------
step "GET /api/v1/me"
ME=$(curl -fsS http://localhost:8000/api/v1/me -H "authorization: Bearer $ACCESS")
echo "$ME" | $PY -m json.tool
echo "$ME" | grep -q "\"email\": \"$EMAIL\"" || fail "/me did not return our email"
echo "$ME" | grep -q '"role": "admin"' || fail "/me did not return role=admin"
ok "/me works"

# --- 9. List profiles ---------------------------------------------------
step "GET /api/v1/device-profiles"
PROFILES=$(curl -fsS http://localhost:8000/api/v1/device-profiles -H "authorization: Bearer $ACCESS")
PROFILE_COUNT=$(echo "$PROFILES" | $PY -c "import json,sys;print(len(json.load(sys.stdin)))")
[ "$PROFILE_COUNT" -ge 6 ] || fail "Expected ≥ 6 profiles, got $PROFILE_COUNT"
PROFILE_ID=$(echo "$PROFILES" | $PY -c "import json,sys;print(json.load(sys.stdin)[0]['id'])")
ok "Listed $PROFILE_COUNT profiles, will use $PROFILE_ID"

# --- 10. Create device --------------------------------------------------
step "POST /api/v1/devices"
DEVICE=$(curl -fsS -X POST http://localhost:8000/api/v1/devices \
  -H "authorization: Bearer $ACCESS" \
  -H "content-type: application/json" \
  -d "{\"name\":\"smoke-test\",\"profile_id\":\"$PROFILE_ID\"}")
DEVICE_ID=$(echo "$DEVICE" | $PY -c "import json,sys;print(json.load(sys.stdin)['id'])")
DEVICE_STATE=$(echo "$DEVICE" | $PY -c "import json,sys;print(json.load(sys.stdin)['state'])")
[ "$DEVICE_STATE" = "creating" ] || fail "Expected state=creating, got $DEVICE_STATE"
ok "Device $DEVICE_ID created in state=creating"

# --- 11. Poll until running ---------------------------------------------
step "Poll device until state=running (worker stub takes ~2s)"
for i in $(seq 1 15); do
  STATE=$(curl -fsS http://localhost:8000/api/v1/devices/$DEVICE_ID \
    -H "authorization: Bearer $ACCESS" | $PY -c "import json,sys;print(json.load(sys.stdin)['state'])")
  if [ "$STATE" = "running" ]; then
    ok "Device flipped to running ($i s)"
    break
  fi
  sleep 1
done
[ "$STATE" = "running" ] || fail "Device still in state=$STATE after 15s. Check 'docker compose logs worker'"

# --- 12. Get adb-info ---------------------------------------------------
step "GET /api/v1/devices/$DEVICE_ID/adb-info"
ADB=$(curl -fsS http://localhost:8000/api/v1/devices/$DEVICE_ID/adb-info \
  -H "authorization: Bearer $ACCESS")
echo "$ADB" | $PY -m json.tool
echo "$ADB" | grep -q '"host": "localhost"' || fail "adb-info host wrong"
ok "adb-info returned"

# --- 13. Get stream-token -----------------------------------------------
step "GET /api/v1/devices/$DEVICE_ID/stream-token"
TOK=$(curl -fsS http://localhost:8000/api/v1/devices/$DEVICE_ID/stream-token \
  -H "authorization: Bearer $ACCESS")
echo "$TOK" | $PY -m json.tool
SEGMENTS=$(echo "$TOK" | $PY -c "import json,sys;print(json.load(sys.stdin)['token'].count(':'))")
[ "$SEGMENTS" -eq 2 ] || fail "Stream token should have 2 colons, got $SEGMENTS"
ok "stream-token has 3 segments (HMAC format correct)"

# --- 14. Refresh token rotation -----------------------------------------
step "POST /api/v1/auth/refresh"
REFRESHED=$(curl -fsS -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "content-type: application/json" \
  -d "{\"refresh\":\"$REFRESH\"}")
NEW_ACCESS=$(echo "$REFRESHED" | $PY -c "import json,sys;print(json.load(sys.stdin)['access'])")
[ -n "$NEW_ACCESS" ] || fail "Refresh did not return new access token"
ok "Refresh rotation works"

step "Verify refresh single-use (second use must fail with 401)"
REUSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "content-type: application/json" \
  -d "{\"refresh\":\"$REFRESH\"}")
[ "$REUSE" = "401" ] || fail "Second refresh use should be 401, got $REUSE"
ok "Refresh denylist works (second use → 401)"

# --- 15. Final summary --------------------------------------------------
echo ""
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ALL CHECKS GREEN — P1a stack works end-to-end ${NC}"
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo ""
echo "  • API:        http://localhost:8000"
echo "  • Docs:       http://localhost:8000/api/docs"
echo "  • Postgres:   localhost:5432 (cloude / changeme_local_dev / cloude)"
echo "  • Redis:      localhost:6379"
echo ""
echo "  Login creds:"
echo "    email:    $EMAIL"
echo "    password: $PASSWORD"
echo ""
echo "  Cleanup: docker compose down -v"
