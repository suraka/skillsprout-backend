"""Add immutable course review records and completion provenance."""

import sqlalchemy as sa

from alembic import op

revision = "20260924_pubrev"
down_revision = "675e3ce72cc5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "lesson_progress",
        sa.Column(
            "completion_source",
            sa.String(length=40),
            nullable=False,
            server_default="legacy_self_reported",
        ),
    )
    op.create_table(
        "course_reviews",
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("content_digest", sa.String(length=64), nullable=False),
        sa.Column("review_gate", sa.String(length=30), nullable=False),
        sa.Column("reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("review_gate IN ('curriculum','safety','assets')"),
        sa.CheckConstraint("decision IN ('approved','rejected')"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "content_digest", "review_gate", "reviewer_user_id"),
    )
    op.create_index("ix_course_reviews_course_id", "course_reviews", ["course_id"], unique=False)
    op.create_index(
        "ix_course_reviews_reviewer_user_id",
        "course_reviews",
        ["reviewer_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_course_reviews_course_digest",
        "course_reviews",
        ["course_id", "content_digest"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_course_reviews_course_digest", table_name="course_reviews")
    op.drop_index("ix_course_reviews_reviewer_user_id", table_name="course_reviews")
    op.drop_index("ix_course_reviews_course_id", table_name="course_reviews")
    op.drop_table("course_reviews")
    op.drop_column("lesson_progress", "completion_source")
