from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Course, Enrollment, Lesson, Module, User
from app.repositories import (
    COURSE_FIELDS,
    ENROLLMENT_FIELDS,
    LESSON_FIELDS,
    STUDENT_FIELDS,
    Repository,
    record,
)
from app.schemas import (
    CourseCreate,
    CoursePatch,
    EnrollmentCreate,
    LessonCreate,
    LessonPatch,
    ModuleCreate,
    ProgressUpdate,
    StudentCreate,
    StudentPatch,
)
from app.security import admin_user, current_user, parent_user
from app.services import AcademyService

router = APIRouter(prefix="/api/v1")


@router.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "version": "0.1.0"}


@router.get("/ready", tags=["health"])
async def ready(db: AsyncSession = Depends(get_db, scope="function")):
    await db.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.get("/me", tags=["account"])
async def me(user: User = Depends(current_user)):
    return record(user, "id email display_name role is_active")


@router.get("/students", tags=["learners"])
async def students(
    user: User = Depends(parent_user), db: AsyncSession = Depends(get_db, scope="function")
):
    return [record(s, STUDENT_FIELDS) for s in await Repository(db).students(user.id)]


@router.post("/students", status_code=201, tags=["learners"])
async def create_student(
    data: StudentCreate,
    user: User = Depends(parent_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    s = await AcademyService(db).create_student(user, data)
    return record(s, STUDENT_FIELDS)


@router.get("/students/{student_id}", tags=["learners"])
async def student(
    student_id: UUID,
    user: User = Depends(parent_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    return record(await AcademyService(db).student(user, student_id), STUDENT_FIELDS)


@router.patch("/students/{student_id}", tags=["learners"])
async def patch_student(
    student_id: UUID,
    data: StudentPatch,
    user: User = Depends(parent_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    service = AcademyService(db)
    s = await service.student(user, student_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    service.audit(user, "student.updated", s)
    return record(s, STUDENT_FIELDS)


@router.get("/courses", tags=["catalog"])
async def courses(
    age_band: str | None = None,
    category: str | None = None,
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    query = select(Course).where(Course.status == "published").order_by(Course.created_at)
    if age_band:
        query = query.where(Course.age_band == age_band)
    if category:
        query = query.where(Course.category == category)
    rows = await db.scalars(query.offset(offset).limit(limit))
    return [await AcademyService(db).course_view(c) for c in rows]


@router.get("/courses/{slug}", tags=["catalog"])
async def course(slug: str, db: AsyncSession = Depends(get_db, scope="function")):
    c = await db.scalar(select(Course).where(Course.slug == slug, Course.status == "published"))
    if not c:
        raise HTTPException(404, "Course not found")
    return await AcademyService(db).course_view(c)


@router.get("/courses/{course_id}/modules", tags=["learning"])
async def modules(
    course_id: UUID,
    user: User = Depends(parent_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    service = AcademyService(db)
    await service.authorize_course(user, course_id)
    rows = await db.scalars(
        select(Module).where(Module.course_id == course_id).order_by(Module.position)
    )
    lessons = await Repository(db).lessons(course_id)
    return [
        {
            **record(m, "id title position description"),
            "lessons": [
                record(lesson_row, LESSON_FIELDS + " content")
                for lesson_row in lessons
                if lesson_row.module_id == m.id
            ],
        }
        for m in rows
    ]


@router.get("/lessons/{lesson_id}", tags=["learning"])
async def lesson(
    lesson_id: UUID,
    user: User = Depends(parent_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    lesson_row = await db.get(Lesson, lesson_id)
    if lesson_row is None or lesson_row.status != "published":
        raise HTTPException(404, "Lesson not found")
    m = await db.get(Module, lesson_row.module_id)
    await AcademyService(db).authorize_course(user, m.course_id)
    return record(lesson_row, LESSON_FIELDS + " content")


@router.post("/students/{student_id}/enrollments", tags=["learning"])
async def enroll(
    student_id: UUID,
    data: EnrollmentCreate,
    user: User = Depends(parent_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    return record(
        await AcademyService(db).enroll(user, student_id, data.course_id), ENROLLMENT_FIELDS
    )


@router.get("/students/{student_id}/enrollments", tags=["learning"])
async def enrollments(
    student_id: UUID,
    user: User = Depends(parent_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    await AcademyService(db).student(user, student_id)
    rows = await db.scalars(select(Enrollment).where(Enrollment.student_id == student_id))
    return [record(e, ENROLLMENT_FIELDS) for e in rows]


@router.get("/enrollments/{enrollment_id}", tags=["learning"])
async def enrollment(
    enrollment_id: UUID,
    user: User = Depends(parent_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    return record(await AcademyService(db).enrollment(user, enrollment_id), ENROLLMENT_FIELDS)


@router.get("/enrollments/{enrollment_id}/progress", tags=["learning"])
async def progress(
    enrollment_id: UUID,
    user: User = Depends(parent_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    return await AcademyService(db).progress(user, enrollment_id)


@router.put("/enrollments/{enrollment_id}/lessons/{lesson_id}/progress", tags=["learning"])
async def save_progress(
    enrollment_id: UUID,
    lesson_id: UUID,
    data: ProgressUpdate,
    user: User = Depends(parent_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    return await AcademyService(db).update_progress(user, enrollment_id, lesson_id, data)


@router.get("/admin/courses", tags=["admin"])
async def admin_courses(
    user: User = Depends(admin_user), db: AsyncSession = Depends(get_db, scope="function")
):
    return [record(c, COURSE_FIELDS) for c in await Repository(db).courses(published=False)]


@router.post("/admin/courses", status_code=201, tags=["admin"])
async def create_course(
    data: CourseCreate,
    user: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    c = Course(**data.model_dump(), created_by=user.id)
    db.add(c)
    await db.flush()
    AcademyService(db).audit(user, "course.created", c)
    return record(c, COURSE_FIELDS)


@router.patch("/admin/courses/{course_id}", tags=["admin"])
async def patch_course(
    course_id: UUID,
    data: CoursePatch,
    user: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    c = await db.get(Course, course_id)
    if c is None:
        raise HTTPException(404, "Course not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    AcademyService(db).audit(user, "course.updated", c)
    return record(c, COURSE_FIELDS)


@router.get("/admin/courses/{course_id}/modules", tags=["admin"])
async def admin_modules(
    course_id: UUID,
    user: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    if await db.get(Course, course_id) is None:
        raise HTTPException(404, "Course not found")
    modules = await db.scalars(
        select(Module).where(Module.course_id == course_id).order_by(Module.position)
    )
    lessons = await Repository(db).lessons(course_id, published=False)
    return [
        {
            **record(m, "id title position description"),
            "lessons": [
                record(lesson_row, LESSON_FIELDS + " content")
                for lesson_row in lessons
                if lesson_row.module_id == m.id
            ],
        }
        for m in modules
    ]


@router.post("/admin/courses/{course_id}/modules", status_code=201, tags=["admin"])
async def create_module(
    course_id: UUID,
    data: ModuleCreate,
    user: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    await AcademyService(db).editable_course(course_id)
    m = Module(course_id=course_id, **data.model_dump())
    db.add(m)
    await db.flush()
    AcademyService(db).audit(user, "module.created", m)
    return record(m, "id title position")


@router.post("/admin/modules/{module_id}/lessons", status_code=201, tags=["admin"])
async def create_lesson(
    module_id: UUID,
    data: LessonCreate,
    user: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    m = await db.get(Module, module_id)
    if m is None:
        raise HTTPException(404, "Module not found")
    await AcademyService(db).editable_course(m.course_id)
    lesson_row = Lesson(module_id=module_id, **data.model_dump())
    db.add(lesson_row)
    await db.flush()
    AcademyService(db).audit(user, "lesson.created", lesson_row)
    return record(lesson_row, LESSON_FIELDS + " content")


@router.patch("/admin/lessons/{lesson_id}", tags=["admin"])
async def patch_lesson(
    lesson_id: UUID,
    data: LessonPatch,
    user: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    lesson_row = await db.get(Lesson, lesson_id)
    if lesson_row is None:
        raise HTTPException(404, "Lesson not found")
    m = await db.get(Module, lesson_row.module_id)
    await AcademyService(db).editable_course(m.course_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(lesson_row, k, v)
    AcademyService(db).audit(user, "lesson.updated", lesson_row)
    return record(lesson_row, LESSON_FIELDS + " content")


@router.post("/admin/courses/{course_id}/publish", tags=["admin"])
async def publish(
    course_id: UUID,
    user: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    return await AcademyService(db).publish(user, course_id)
