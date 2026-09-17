from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, Enrollment, Lesson, Module, ParentStudentLink, Student


class Repository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def students(self, parent_id):
        result = await self.db.scalars(
            select(Student)
            .join(ParentStudentLink)
            .where(ParentStudentLink.parent_user_id == parent_id)
            .order_by(Student.created_at)
        )
        return list(result)

    async def linked_student(self, parent_id, student_id):
        return await self.db.scalar(
            select(Student)
            .join(ParentStudentLink)
            .where(ParentStudentLink.parent_user_id == parent_id, Student.id == student_id)
        )

    async def lessons(self, course_id, published=True):
        query = select(Lesson).join(Module).where(Module.course_id == course_id)
        if published:
            query = query.where(Lesson.status == "published")
        return list(await self.db.scalars(query.order_by(Module.position, Lesson.position)))

    async def courses(self, published=True):
        query = select(Course).order_by(Course.created_at)
        if published:
            query = query.where(Course.status == "published")
        return list(await self.db.scalars(query))

    async def enrollment_for_parent(self, parent_id, enrollment_id, lock=False):
        query = (
            select(Enrollment)
            .join(ParentStudentLink, ParentStudentLink.student_id == Enrollment.student_id)
            .where(Enrollment.id == enrollment_id, ParentStudentLink.parent_user_id == parent_id)
        )
        if lock:
            query = query.with_for_update(of=Enrollment)
        return await self.db.scalar(query)


def record(obj, fields):
    return {field: getattr(obj, field) for field in fields.split()}


STUDENT_FIELDS = "id first_name preferred_name age_band avatar_key status"
COURSE_FIELDS = "id slug title short_description description age_band difficulty category color icon status is_free published_at"
LESSON_FIELDS = "id module_id title slug lesson_type estimated_minutes position status"
ENROLLMENT_FIELDS = "id student_id course_id status enrolled_at completed_at"
PROGRESS_FIELDS = "lesson_id status progress_percent started_at completed_at last_seen_at"
