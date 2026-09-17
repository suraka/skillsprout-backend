"""Idempotently load the starter catalog. Never creates a usable admin login."""

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import Course, Lesson, Module, User
from app.services import now


async def seed():
    async with SessionLocal.begin() as db:
        system = await db.scalar(select(User).where(User.firebase_uid == "system-catalog-seed"))
        if system is None:
            system = User(
                firebase_uid="system-catalog-seed",
                display_name="SkillSprout Catalog",
                role="admin",
                is_active=False,
            )
            db.add(system)
            await db.flush()
        for item in json.loads(
            (Path(__file__).resolve().parent.parent / "data/courses.json").read_text()
        ):
            if await db.scalar(select(Course).where(Course.slug == item["slug"])):
                continue
            data = {
                k: item[k]
                for k in (
                    "slug",
                    "title",
                    "category",
                    "age_band",
                    "short_description",
                    "description",
                    "difficulty",
                    "is_free",
                    "color",
                    "icon",
                )
            }
            c = Course(**data, status="published", created_by=system.id, published_at=now())
            db.add(c)
            await db.flush()
            m = Module(course_id=c.id, title="Your first adventure", position=0)
            db.add(m)
            await db.flush()
            for i, lesson_row in enumerate(item["lessons"]):
                db.add(
                    Lesson(
                        module_id=m.id,
                        slug=f"lesson-{i + 1}",
                        title=lesson_row["title"],
                        lesson_type=lesson_row["lesson_type"],
                        content=lesson_row["content"],
                        estimated_minutes=lesson_row["estimated_minutes"],
                        position=i,
                        status="published",
                    )
                )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
