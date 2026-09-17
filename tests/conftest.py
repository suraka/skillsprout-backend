import os

import pytest_asyncio
from fastapi import HTTPException, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import Base, User
from app.security import verified_identity


@pytest_asyncio.fixture
async def client():
    url = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite://")
    engine = create_async_engine(
        url, **({"poolclass": StaticPool} if url.startswith("sqlite") else {})
    )
    if url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def enable_fk(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        if url.startswith("postgresql"):
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS citext"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as db:
        db.add_all(
            [
                User(firebase_uid="admin", email="admin@example.test", role="admin"),
                User(
                    firebase_uid="disabled",
                    email="disabled@example.test",
                    role="parent",
                    is_active=False,
                ),
            ]
        )

    async def database():
        async with sessions() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    async def identity(request: Request):
        uid = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if uid not in ("parent-a", "parent-b", "admin", "disabled"):
            raise HTTPException(401, "Invalid test token")
        return {"uid": uid, "email": f"{uid}@example.test", "name": uid}

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[verified_identity] = identity
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()
