from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

AgeBand = Literal["5-7", "8-10", "11-13", "14-17", "adult"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StudentCreate(Input):
    first_name: str = Field(min_length=1, max_length=100)
    age_band: AgeBand
    preferred_name: str | None = Field(None, max_length=100)
    avatar_key: str | None = Field(None, max_length=100)


class StudentPatch(Input):
    first_name: str | None = Field(None, min_length=1, max_length=100)
    age_band: AgeBand | None = None
    preferred_name: str | None = Field(None, max_length=100)
    status: Literal["active", "inactive"] | None = None

    @model_validator(mode="after")
    def nonnull_fields(self):
        for field in ("first_name", "age_band", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class CourseCreate(Input):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=160)
    title: str = Field(min_length=1, max_length=200)
    short_description: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=10000)
    age_band: AgeBand
    difficulty: Literal["beginner", "intermediate", "advanced"] = "beginner"
    category: str = Field(min_length=1, max_length=80)
    is_free: bool = True
    color: Literal["green", "purple", "orange", "pink", "blue", "yellow"] = "green"
    icon: Literal["BookOpen", "Bot", "Code2", "Palette", "ShieldCheck", "Sparkles"] = "BookOpen"


class CoursePatch(Input):
    title: str | None = Field(None, min_length=1, max_length=200)
    short_description: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = Field(None, max_length=10000)
    status: Literal["draft", "review", "archived"] | None = None
    is_free: bool | None = None

    @model_validator(mode="after")
    def no_explicit_null(self):
        if any(getattr(self, f) is None for f in self.model_fields_set):
            raise ValueError("Updated fields cannot be null")
        return self


class ModuleCreate(Input):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    position: int = Field(ge=0)


class Block(Input):
    type: Literal["heading", "paragraph", "activity"]
    text: str = Field(min_length=1, max_length=10000)


class Content(Input):
    blocks: list[Block] = Field(min_length=1, max_length=50)


class LessonCreate(Input):
    title: str = Field(min_length=1, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=160)
    lesson_type: Literal["text", "activity", "project"] = "activity"
    content: Content
    estimated_minutes: int = Field(default=10, ge=1, le=240)
    position: int = Field(ge=0)
    status: Literal["draft", "review", "published"] = "draft"


class LessonPatch(Input):
    title: str | None = Field(None, min_length=1, max_length=200)
    content: Content | None = None
    status: Literal["draft", "review", "published"] | None = None
    estimated_minutes: int | None = Field(None, ge=1, le=240)

    @model_validator(mode="after")
    def no_null(self):
        if any(getattr(self, f) is None for f in self.model_fields_set):
            raise ValueError("Updated fields cannot be null")
        return self


class EnrollmentCreate(Input):
    course_id: UUID


class ProgressUpdate(Input):
    status: Literal["not_started", "in_progress", "completed"]
    progress_percent: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def consistent_status(self):
        if self.status == "completed" and self.progress_percent != 100:
            raise ValueError("Completed lessons must have 100 percent progress")
        if self.status == "not_started" and self.progress_percent != 0:
            raise ValueError("Not-started lessons must have zero percent progress")
        if self.status == "in_progress" and not 1 <= self.progress_percent <= 99:
            raise ValueError("In-progress lessons require 1–99 percent")
        return self
