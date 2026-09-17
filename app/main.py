import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError

from app.config import settings
from app.db import engine
from app.routes import router


@asynccontextmanager
async def lifespan(app):
    yield
    await engine.dispose()


app = FastAPI(title="SkillSprout API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.frontend_url.split(",")],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(IntegrityError)
async def duplicate_or_invalid(request, exc):
    return JSONResponse(
        status_code=409,
        content={"detail": "This record already exists or conflicts with existing data"},
    )


@app.exception_handler(OperationalError)
async def database_unavailable(request, exc):
    logging.getLogger("skillsprout").error(
        "Database unavailable; request=%s", request.state.request_id
    )
    return JSONResponse(
        status_code=503, content={"detail": "Learning service unavailable; try again later"}
    )


app.include_router(router)
