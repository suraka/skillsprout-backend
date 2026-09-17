from functools import lru_cache

import firebase_admin
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, credentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.db import get_db
from app.models import ParentProfile, User

bearer = HTTPBearer(auto_error=False)


@lru_cache
def firebase_app():
    if not settings.firebase_project_id:
        raise HTTPException(503, "Parent sign-in has not been configured")
    try:
        return firebase_admin.get_app("skillsprout")
    except ValueError:
        credential = None
        if settings.firebase_private_key and settings.firebase_client_email:
            credential = credentials.Certificate(
                {
                    "type": "service_account",
                    "project_id": settings.firebase_project_id,
                    "private_key": settings.firebase_private_key.replace("\\n", "\n"),
                    "client_email": settings.firebase_client_email,
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            )
        return firebase_admin.initialize_app(
            credential, {"projectId": settings.firebase_project_id}, name="skillsprout"
        )


async def verified_identity(credential: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credential is None:
        raise HTTPException(401, "Sign in to continue", headers={"WWW-Authenticate": "Bearer"})
    app = firebase_app()
    try:
        return await run_in_threadpool(
            auth.verify_id_token, credential.credentials, app=app, check_revoked=True
        )
    except (auth.InvalidIdTokenError, auth.RevokedIdTokenError, auth.UserDisabledError, ValueError):
        raise HTTPException(
            401, "Invalid or expired sign-in", headers={"WWW-Authenticate": "Bearer"}
        ) from None
    except Exception:
        # Provider outages are not interpreted as a valid identity.
        raise HTTPException(503, "Sign-in service unavailable; try again later") from None


async def current_user(
    identity: dict = Depends(verified_identity),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    uid = identity.get("uid")
    if not uid or len(uid) > 128:
        raise HTTPException(401, "Invalid identity")
    user = await db.scalar(select(User).where(User.firebase_uid == uid))
    if user is None:
        # Never accept a role from the browser or auto-promote based on an email address.
        user = User(
            firebase_uid=uid,
            email=(identity.get("email") or "").lower() or None,
            display_name=(identity.get("name") or "Parent")[:150],
            role="parent",
        )
        db.add(user)
        await db.flush()
        db.add(ParentProfile(user_id=user.id))
        await db.flush()
    if not user.is_active:
        raise HTTPException(403, "This account is disabled")
    return user


async def parent_user(user: User = Depends(current_user)):
    if user.role not in ("parent", "admin"):
        raise HTTPException(403, "A parent or guardian account is required")
    return user


async def admin_user(user: User = Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return user
