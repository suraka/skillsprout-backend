from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.config import settings
from app.models import (
    AuditLog,
    Course,
    Enrollment,
    LessonProgress,
    Module,
    ParentStudentLink,
    Student,
    User,
)
from app.repositories import COURSE_FIELDS, LESSON_FIELDS, PROGRESS_FIELDS, Repository, record


def now():
    return datetime.now(timezone.utc)


class AcademyService:
    def __init__(self, db):
        self.db = db
        self.repo = Repository(db)

    def audit(self, user, action, entity):
        self.db.add(
            AuditLog(
                actor_user_id=user.id,
                action=action,
                entity_type=entity.__tablename__,
                entity_id=entity.id,
            )
        )

    async def student(self, user, student_id):
        student = await self.repo.linked_student(user.id, student_id)
        if student is None:
            raise HTTPException(404, "Learner not found")
        return student

    async def create_student(self, user, data):
        # Serialize profile creation for the same parent so the limit is race-safe.
        await self.db.scalar(select(User).where(User.id == user.id).with_for_update())
        if len(await self.repo.students(user.id)) >= settings.max_students_per_parent:
            raise HTTPException(409, "Your account has reached its learner limit")
        student = Student(**data.model_dump())
        self.db.add(student)
        await self.db.flush()
        self.db.add(ParentStudentLink(parent_user_id=user.id, student_id=student.id))
        self.audit(user, "student.created", student)
        return student

    async def course_view(self, course):
        result = record(course, COURSE_FIELDS)
        result["lessons"] = [
            record(lesson_row, LESSON_FIELDS) for lesson_row in await self.repo.lessons(course.id)
        ]
        return result

    async def enroll(self, user, student_id, course_id):
        student = await self.student(user, student_id)
        await self.db.scalar(select(Student).where(Student.id == student_id).with_for_update())
        if student.status != "active":
            raise HTTPException(409, "This learner is inactive")
        course = await self.db.get(Course, course_id)
        if course is None or course.status != "published":
            raise HTTPException(404, "Course not found")
        if not course.is_free:
            raise HTTPException(409, "Paid enrollment is not available in this release")
        existing = await self.db.scalar(
            select(Enrollment).where(
                Enrollment.student_id == student_id, Enrollment.course_id == course_id
            )
        )
        if existing:
            if existing.status == "cancelled":
                raise HTTPException(409, "This enrollment has been cancelled")
            return existing
        e = Enrollment(student_id=student_id, course_id=course_id, enrolled_by=user.id)
        self.db.add(e)
        await self.db.flush()
        self.audit(user, "enrollment.created", e)
        return e

    async def enrollment(self, user, enrollment_id, lock=False):
        enrollment = await self.repo.enrollment_for_parent(user.id, enrollment_id, lock)
        if enrollment is None:
            raise HTTPException(404, "Enrollment not found")
        return enrollment

    async def authorize_course(self, user, course_id):
        course = await self.db.get(Course, course_id)
        if course is None or course.status != "published":
            raise HTTPException(404, "Course not found")
        query = (
            select(Enrollment)
            .join(ParentStudentLink, ParentStudentLink.student_id == Enrollment.student_id)
            .join(Student, Student.id == Enrollment.student_id)
            .where(
                ParentStudentLink.parent_user_id == user.id,
                Enrollment.course_id == course_id,
                Enrollment.status.in_(["active", "completed"]),
                Student.status == "active",
            )
        )
        if not await self.db.scalar(query):
            raise HTTPException(403, "Enroll a linked learner to open these lessons")
        return course

    async def progress(self, user, enrollment_id):
        e = await self.enrollment(user, enrollment_id)
        lessons = await self.repo.lessons(e.course_id)
        rows = list(
            await self.db.scalars(
                select(LessonProgress).where(LessonProgress.enrollment_id == e.id)
            )
        )
        by_id = {p.lesson_id: p for p in rows}
        views = [
            record(by_id[lesson_row.id], PROGRESS_FIELDS)
            if lesson_row.id in by_id
            else {"lesson_id": lesson_row.id, "status": "not_started", "progress_percent": 0}
            for lesson_row in lessons
        ]
        percent = round(sum(v["progress_percent"] for v in views) / len(views)) if views else 0
        return {"enrollment_id": e.id, "progress_percent": percent, "lessons": views}

    async def update_progress(self, user, enrollment_id, lesson_id, data):
        e = await self.enrollment(user, enrollment_id, lock=True)
        student = await self.student(user, e.student_id)
        if e.status == "cancelled" or student.status != "active":
            raise HTTPException(409, "This enrollment is not active")
        await self.authorize_course(user, e.course_id)
        lessons = await self.repo.lessons(e.course_id)
        if lesson_id not in {lesson_row.id for lesson_row in lessons}:
            raise HTTPException(404, "Lesson not found in this enrollment")
        p = await self.db.scalar(
            select(LessonProgress).where(
                LessonProgress.enrollment_id == e.id, LessonProgress.lesson_id == lesson_id
            )
        )
        if p is None:
            p = LessonProgress(enrollment_id=e.id, lesson_id=lesson_id)
            self.db.add(p)
        elif p.status == "completed" and data.status != "completed":
            raise HTTPException(409, "Completed lessons cannot be reset through progress updates")
        p.status = data.status
        p.progress_percent = data.progress_percent
        p.last_seen_at = now()
        if data.status != "not_started" and p.started_at is None:
            p.started_at = now()
        if data.status == "completed" and p.completed_at is None:
            p.completed_at = now()
        await self.db.flush()
        progress = await self.progress(user, e.id)
        if lessons and all(
            lesson_row["status"] == "completed" for lesson_row in progress["lessons"]
        ):
            e.status = "completed"
            e.completed_at = e.completed_at or now()
        return record(p, PROGRESS_FIELDS)

    async def editable_course(self, course_id):
        course = await self.db.get(Course, course_id)
        if course is None:
            raise HTTPException(404, "Course not found")
        if course.status == "published":
            raise HTTPException(409, "Move the course to draft before editing its lessons")
        return course

    async def publish(self, user, course_id):
        course = await self.db.get(Course, course_id)
        if course is None:
            raise HTTPException(404, "Course not found")
        modules = list(await self.db.scalars(select(Module).where(Module.course_id == course_id)))
        lessons = await self.repo.lessons(course_id, published=False)
        if (
            not modules
            or not lessons
            or any(not any(lesson_row.module_id == m.id for lesson_row in lessons) for m in modules)
        ):
            raise HTTPException(409, "Add at least one lesson to every module before publishing")
        from app.schemas import Content

        for lesson in lessons:
            Content.model_validate(lesson.content)
            lesson.status = "published"
        course.status = "published"
        course.published_at = now()
        self.audit(user, "course.published", course)
        await self.db.flush()
        return await self.course_view(course)
