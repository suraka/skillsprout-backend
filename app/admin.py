"""Run from a trusted operator shell: python -m app.admin FIREBASE_UID."""

import asyncio
import sys

from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import User


async def promote(uid):
    async with SessionLocal.begin() as db:
        user = await db.scalar(select(User).where(User.firebase_uid == uid))
        if not user or not user.is_active:
            raise SystemExit("An active account must sign in to the API before promotion.")
        user.role = "admin"
        print("Administrator role assigned to the existing account.")
    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.admin FIREBASE_UID")
    asyncio.run(promote(sys.argv[1]))
