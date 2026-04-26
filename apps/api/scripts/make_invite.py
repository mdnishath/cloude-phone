"""Mint an invite. Prints the raw token (store nowhere — give it to the user once).

Usage examples:
  python scripts/make_invite.py --role admin --ttl-hours 48
  python scripts/make_invite.py --email new@user.com --role user
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from cloude_api.core.auth import generate_invite_token, hash_invite_token
from cloude_api.db import async_session_factory
from cloude_api.enums import UserRole
from cloude_api.models.invite import Invite


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Mint a single-use invite token.")
    p.add_argument("--email", default=None, help="Optional pre-bind to this email.")
    p.add_argument("--role", choices=[r.value for r in UserRole], default=UserRole.user.value)
    p.add_argument("--ttl-hours", type=int, default=72)
    return p.parse_args()


async def main() -> None:
    args = _parse()
    raw = generate_invite_token()
    invite = Invite(
        id=uuid.uuid4(),
        token_hash=hash_invite_token(raw),
        email=args.email,
        role=UserRole(args.role),
        expires_at=datetime.now(tz=UTC) + timedelta(hours=args.ttl_hours),
    )
    async with async_session_factory() as db:
        db.add(invite)
        await db.commit()
    print("Invite minted.")
    print(f"  id:         {invite.id}")
    print(f"  email:      {args.email or '(any)'}")
    print(f"  role:       {args.role}")
    print(f"  expires_at: {invite.expires_at.isoformat()}")
    print("")
    print(f"  token:  {raw}")
    print("")
    print("Give the user this curl to redeem:")
    print("  curl -X POST http://localhost:8000/api/v1/auth/redeem-invite \\")
    print('    -H "content-type: application/json" \\')
    body = f'{{"token":"{raw}","email":"USER@EXAMPLE.COM","password":"choose-strong-pw"}}'
    print(f"    -d '{body}'")


if __name__ == "__main__":
    asyncio.run(main())
