import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Identity:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Identity, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('parent','student','admin')"),)
    firebase_uid: Mapped[str] = mapped_column(String(128), unique=True)
    email: Mapped[str | None] = mapped_column(
        String(320).with_variant(CITEXT(), "postgresql"), unique=True
    )
    display_name: Mapped[str | None] = mapped_column(String(150))
    role: Mapped[str] = mapped_column(String(30), default="parent", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ParentProfile(Identity, Timestamps, Base):
    __tablename__ = "parent_profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    phone: Mapped[str | None] = mapped_column(String(40))
    country_code: Mapped[str | None] = mapped_column(String(2))
    timezone: Mapped[str | None] = mapped_column(String(60))


class Student(Identity, Timestamps, Base):
    __tablename__ = "student_profiles"
    __table_args__ = (
        CheckConstraint("status IN ('active','inactive')"),
        CheckConstraint("age_band IN ('5-7','8-10','11-13','14-17','adult')"),
    )
    first_name: Mapped[str] = mapped_column(String(100))
    preferred_name: Mapped[str | None] = mapped_column(String(100))
    birth_year: Mapped[int | None] = mapped_column(Integer)
    age_band: Mapped[str] = mapped_column(String(30))
    avatar_key: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="active")


class ParentStudentLink(Identity, Base):
    __tablename__ = "parent_student_links"
    __table_args__ = (
        UniqueConstraint("parent_user_id", "student_id"),
        CheckConstraint("relationship IN ('parent','guardian')"),
    )
    parent_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), index=True
    )
    relationship: Mapped[str] = mapped_column(String(30), default="parent")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Course(Identity, Timestamps, Base):
    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint("status IN ('draft','review','published','archived')"),
        CheckConstraint("difficulty IN ('beginner','intermediate','advanced')"),
        Index("ix_courses_status_age", "status", "age_band"),
    )
    slug: Mapped[str] = mapped_column(String(160), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    short_description: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    age_band: Mapped[str] = mapped_column(String(30))
    difficulty: Mapped[str] = mapped_column(String(30), default="beginner")
    category: Mapped[str] = mapped_column(String(80), index=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str] = mapped_column(String(30), default="green")
    icon: Mapped[str] = mapped_column(String(30), default="BookOpen")
    status: Mapped[str] = mapped_column(String(30), default="draft")
    is_free: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Module(Identity, Timestamps, Base):
    __tablename__ = "course_modules"
    __table_args__ = (UniqueConstraint("course_id", "position"), CheckConstraint("position >= 0"))
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)


class Lesson(Identity, Timestamps, Base):
    __tablename__ = "lessons"
    __table_args__ = (
        UniqueConstraint("module_id", "position"),
        UniqueConstraint("module_id", "slug"),
        CheckConstraint("position >= 0"),
        CheckConstraint("estimated_minutes > 0"),
        CheckConstraint("status IN ('draft','review','published')"),
        CheckConstraint("lesson_type IN ('video','text','activity','project')"),
    )
    module_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_modules.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(160))
    lesson_type: Mapped[str] = mapped_column(String(30), default="activity")
    content: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=10)
    position: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="draft")


class Enrollment(Identity, Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", "course_id"),
        CheckConstraint("status IN ('active','completed','cancelled')"),
        Index("ix_enrollments_student_status", "student_id", "status"),
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"), index=True)
    enrolled_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), default="active")
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LessonProgress(Identity, Base):
    __tablename__ = "lesson_progress"
    __table_args__ = (
        UniqueConstraint("enrollment_id", "lesson_id"),
        CheckConstraint("progress_percent BETWEEN 0 AND 100"),
        CheckConstraint("status IN ('not_started','in_progress','completed')"),
    )
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("enrollments.id", ondelete="CASCADE"), index=True
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="not_started")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditLog(Identity, Base):
    __tablename__ = "audit_logs"
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
