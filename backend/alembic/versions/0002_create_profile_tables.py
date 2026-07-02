"""create profile tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def _uuid_pk():
    return sa.Column(
        "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )


def _display_order():
    return sa.Column("display_order", sa.Integer(), nullable=False, server_default="0")


def _text_array():
    return sa.ARRAY(sa.Text())


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_job_title", sa.String(length=255), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("professional_summary", sa.Text(), nullable=True),
        sa.Column("personal_info", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_profiles_user_id", "user_profiles", ["user_id"])
    op.create_index(
        "ix_user_profiles_one_default_per_user",
        "user_profiles",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
    )

    op.create_table(
        "profile_skills",
        _uuid_pk(),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("skill_name", sa.String(length=100), nullable=False),
        _display_order(),
    )
    op.create_index("ix_profile_skills_profile_id", "profile_skills", ["profile_id"])

    op.create_table(
        "profile_experiences",
        _uuid_pk(),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_title", sa.String(length=255), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("employment_type", sa.String(length=100), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("currently_working_here", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("responsibilities", _text_array(), nullable=False, server_default=sa.text("'{}'")),
        _display_order(),
    )
    op.create_index("ix_profile_experiences_profile_id", "profile_experiences", ["profile_id"])

    op.create_table(
        "experience_projects",
        _uuid_pk(),
        sa.Column(
            "experience_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profile_experiences.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("project_name", sa.String(length=255), nullable=False),
        sa.Column("details", _text_array(), nullable=False, server_default=sa.text("'{}'")),
        _display_order(),
    )
    op.create_index("ix_experience_projects_experience_id", "experience_projects", ["experience_id"])

    op.create_table(
        "profile_projects",
        _uuid_pk(),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_name", sa.String(length=255), nullable=False),
        sa.Column("details", _text_array(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("demo_url", sa.String(length=1024), nullable=True),
        sa.Column("github_url", sa.String(length=1024), nullable=True),
        _display_order(),
    )
    op.create_index("ix_profile_projects_profile_id", "profile_projects", ["profile_id"])

    op.create_table(
        "profile_education",
        _uuid_pk(),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("degree", sa.String(length=255), nullable=False),
        sa.Column("field_of_study", sa.String(length=255), nullable=True),
        sa.Column("minor", sa.String(length=255), nullable=True),
        sa.Column("institution_name", sa.String(length=255), nullable=False),
        sa.Column("university_board", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("graduation_year", sa.Integer(), nullable=True),
        sa.Column("gpa", sa.String(length=50), nullable=True),
        sa.Column("honors", sa.String(length=255), nullable=True),
        _display_order(),
    )
    op.create_index("ix_profile_education_profile_id", "profile_education", ["profile_id"])

    op.create_table(
        "profile_certifications",
        _uuid_pk(),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("certification_name", sa.String(length=255), nullable=False),
        sa.Column("issuing_organization", sa.String(length=255), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("credential_id", sa.String(length=255), nullable=True),
        sa.Column("credential_url", sa.String(length=1024), nullable=True),
        _display_order(),
    )
    op.create_index("ix_profile_certifications_profile_id", "profile_certifications", ["profile_id"])

    op.create_table(
        "profile_achievements",
        _uuid_pk(),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("achievement_title", sa.String(length=255), nullable=False),
        sa.Column("organization", sa.String(length=255), nullable=True),
        sa.Column("date_achieved", sa.Date(), nullable=True),
        sa.Column("description", _text_array(), nullable=False, server_default=sa.text("'{}'")),
        _display_order(),
    )
    op.create_index("ix_profile_achievements_profile_id", "profile_achievements", ["profile_id"])

    op.create_table(
        "profile_languages",
        _uuid_pk(),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(length=100), nullable=False),
        sa.Column("proficiency", sa.String(length=32), nullable=False),
        _display_order(),
    )
    op.create_index("ix_profile_languages_profile_id", "profile_languages", ["profile_id"])


def downgrade() -> None:
    op.drop_table("profile_languages")
    op.drop_table("profile_achievements")
    op.drop_table("profile_certifications")
    op.drop_table("profile_education")
    op.drop_table("profile_projects")
    op.drop_table("experience_projects")
    op.drop_table("profile_experiences")
    op.drop_table("profile_skills")
    op.drop_index("ix_user_profiles_one_default_per_user", table_name="user_profiles")
    op.drop_index("ix_user_profiles_user_id", table_name="user_profiles")
    op.drop_table("user_profiles")
