import json
import uuid

from sqlalchemy import JSON, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from profiles.models import (
    ExperienceProject,
    ProfileAchievement,
    ProfileCertification,
    ProfileEducation,
    ProfileExperience,
    ProfileLanguage,
    ProfileProject,
    ProfileSkill,
    UserProfile,
)
from profiles.schemas import ProfileResponse, ProfileWriteRequest


class ProfileNotFoundError(Exception):
    pass


# Single-round-trip replacement for the 7-selectinload read _get_owned does — see
# docs/BUILD_PLAN.md's N+1 backlog note. Each child collection is built inline via a correlated
# json_agg subquery (experiences nests a further one for experience_projects) instead of one
# sequential round trip per relationship. First raw-SQL query in this codebase — no existing
# precedent to follow, so this stays deliberately self-contained in one function.
_PROFILE_RESPONSE_SQL = text(
    """
    SELECT
        up.id, up.user_id, up.target_job_title, up.is_default, up.professional_summary,
        up.personal_info, up.created_at, up.updated_at,
        (SELECT COALESCE(json_agg(row_to_json(t) ORDER BY t.display_order), '[]'::json)
         FROM (SELECT id, category, skill_name, display_order
               FROM profile_skills WHERE profile_id = up.id) t
        ) AS skills,
        (SELECT COALESCE(json_agg(row_to_json(t) ORDER BY t.display_order), '[]'::json)
         FROM (
            SELECT pe.id, pe.job_title, pe.company_name, pe.employment_type, pe.location,
                   pe.start_date, pe.end_date, pe.currently_working_here, pe.responsibilities,
                   pe.display_order,
                   (SELECT COALESCE(json_agg(row_to_json(pt) ORDER BY pt.display_order), '[]'::json)
                    FROM (SELECT id, project_name, details, display_order
                          FROM experience_projects WHERE experience_id = pe.id) pt
                   ) AS projects
            FROM profile_experiences pe WHERE pe.profile_id = up.id
         ) t
        ) AS experiences,
        (SELECT COALESCE(json_agg(row_to_json(t) ORDER BY t.display_order), '[]'::json)
         FROM (SELECT id, project_name, details, demo_url, github_url, display_order
               FROM profile_projects WHERE profile_id = up.id) t
        ) AS projects,
        (SELECT COALESCE(json_agg(row_to_json(t) ORDER BY t.display_order), '[]'::json)
         FROM (SELECT id, degree, field_of_study, minor, institution_name, university_board,
                      location, start_date, end_date, graduation_year, gpa, honors, display_order
               FROM profile_education WHERE profile_id = up.id) t
        ) AS education,
        (SELECT COALESCE(json_agg(row_to_json(t) ORDER BY t.display_order), '[]'::json)
         FROM (SELECT id, certification_name, issuing_organization, issue_date, expiry_date,
                      credential_id, credential_url, display_order
               FROM profile_certifications WHERE profile_id = up.id) t
        ) AS certifications,
        (SELECT COALESCE(json_agg(row_to_json(t) ORDER BY t.display_order), '[]'::json)
         FROM (SELECT id, achievement_title, organization, date_achieved, description, display_order
               FROM profile_achievements WHERE profile_id = up.id) t
        ) AS achievements,
        (SELECT COALESCE(json_agg(row_to_json(t) ORDER BY t.display_order), '[]'::json)
         FROM (SELECT id, language, proficiency, display_order
               FROM profile_languages WHERE profile_id = up.id) t
        ) AS languages
    FROM user_profiles up
    WHERE up.id = :profile_id AND up.user_id = :user_id
    """
).columns(
    personal_info=JSON,
    skills=JSON,
    experiences=JSON,
    projects=JSON,
    education=JSON,
    certifications=JSON,
    achievements=JSON,
    languages=JSON,
)

_JSON_FIELDS = (
    "personal_info",
    "skills",
    "experiences",
    "projects",
    "education",
    "certifications",
    "achievements",
    "languages",
)


def _maybe_json_loads(value):
    # Defensive: whether the asyncpg driver or SQLAlchemy's JSON type-hint already deserialized
    # this column or not, handle both — there's no existing raw-SQL precedent in this codebase to
    # confirm which one happens in practice, so don't assume either way.
    return json.loads(value) if isinstance(value, str) else value


async def _fetch_profile_response(
    db: AsyncSession, user_id: uuid.UUID, profile_id: uuid.UUID
) -> ProfileResponse | None:
    result = await db.execute(_PROFILE_RESPONSE_SQL, {"profile_id": profile_id, "user_id": user_id})
    row = result.mappings().first()
    if row is None:
        return None
    data = dict(row)
    for field in _JSON_FIELDS:
        data[field] = _maybe_json_loads(data[field])
    return ProfileResponse.model_validate(data)


def _load_options():
    return (
        selectinload(UserProfile.skills),
        selectinload(UserProfile.experiences).selectinload(ProfileExperience.projects),
        selectinload(UserProfile.projects),
        selectinload(UserProfile.education),
        selectinload(UserProfile.certifications),
        selectinload(UserProfile.achievements),
        selectinload(UserProfile.languages),
    )


async def _get_owned(db: AsyncSession, user_id: uuid.UUID, profile_id: uuid.UUID) -> UserProfile:
    profile = await db.scalar(
        select(UserProfile)
        .where(UserProfile.id == profile_id, UserProfile.user_id == user_id)
        .options(*_load_options())
    )
    if profile is None:
        raise ProfileNotFoundError(str(profile_id))
    return profile


async def _demote_other_defaults(db: AsyncSession, user_id: uuid.UUID, keep_profile_id: uuid.UUID | None) -> None:
    stmt = update(UserProfile).where(UserProfile.user_id == user_id, UserProfile.is_default.is_(True))
    if keep_profile_id is not None:
        stmt = stmt.where(UserProfile.id != keep_profile_id)
    await db.execute(stmt.values(is_default=False))


def _apply_children(profile: UserProfile, payload: ProfileWriteRequest) -> None:
    """Wholesale-replace every nested collection. Relationships are configured with
    cascade="all, delete-orphan", so reassigning the list deletes the old rows and inserts new ones
    inside the same transaction — this is a full-replace aggregate update, not per-item patching."""
    profile.skills = [
        ProfileSkill(category=s.category, skill_name=s.skill_name, display_order=s.display_order)
        for s in payload.skills
    ]
    profile.experiences = [
        ProfileExperience(
            job_title=e.job_title,
            company_name=e.company_name,
            employment_type=e.employment_type,
            location=e.location,
            start_date=e.start_date,
            end_date=e.end_date,
            currently_working_here=e.currently_working_here,
            responsibilities=e.responsibilities,
            display_order=e.display_order,
            # ExperienceProject rows are keyed by experience_id, not profile_id — see
            # docs/PROGRESS.md Phase 2 log for why this deviates from the PRD's literal (loose)
            # prose about sub-tables all referencing profile_id.
            projects=[
                ExperienceProject(project_name=p.project_name, details=p.details, display_order=p.display_order)
                for p in e.projects
            ],
        )
        for e in payload.experiences
    ]
    profile.projects = [
        ProfileProject(
            project_name=p.project_name,
            details=p.details,
            demo_url=p.demo_url,
            github_url=p.github_url,
            display_order=p.display_order,
        )
        for p in payload.projects
    ]
    profile.education = [
        ProfileEducation(
            degree=e.degree,
            field_of_study=e.field_of_study,
            minor=e.minor,
            institution_name=e.institution_name,
            university_board=e.university_board,
            location=e.location,
            start_date=e.start_date,
            end_date=e.end_date,
            graduation_year=e.graduation_year,
            gpa=e.gpa,
            honors=e.honors,
            display_order=e.display_order,
        )
        for e in payload.education
    ]
    profile.certifications = [
        ProfileCertification(
            certification_name=c.certification_name,
            issuing_organization=c.issuing_organization,
            issue_date=c.issue_date,
            expiry_date=c.expiry_date,
            credential_id=c.credential_id,
            credential_url=c.credential_url,
            display_order=c.display_order,
        )
        for c in payload.certifications
    ]
    profile.achievements = [
        ProfileAchievement(
            achievement_title=a.achievement_title,
            organization=a.organization,
            date_achieved=a.date_achieved,
            description=a.description,
            display_order=a.display_order,
        )
        for a in payload.achievements
    ]
    profile.languages = [
        ProfileLanguage(language=lang.language, proficiency=lang.proficiency, display_order=lang.display_order)
        for lang in payload.languages
    ]


async def create_profile(db: AsyncSession, user_id: uuid.UUID, payload: ProfileWriteRequest) -> ProfileResponse:
    existing_count = await db.scalar(
        select(UserProfile.id).where(UserProfile.user_id == user_id).limit(1)
    )
    # A user's very first profile is always their default — there should never be a moment where
    # a user has profiles but none of them is the default.
    make_default = payload.is_default or existing_count is None

    if make_default:
        await _demote_other_defaults(db, user_id, keep_profile_id=None)

    profile = UserProfile(
        user_id=user_id,
        target_job_title=payload.target_job_title,
        is_default=make_default,
        professional_summary=payload.professional_summary,
        personal_info=payload.personal_info.model_dump(mode="json"),
    )
    _apply_children(profile, payload)

    db.add(profile)
    await db.commit()
    response = await _fetch_profile_response(db, user_id, profile.id)
    assert response is not None  # just created in this same transaction
    return response


async def list_profiles(db: AsyncSession, user_id: uuid.UUID) -> list[UserProfile]:
    # Deliberately no selectinload options here: this backs GET /profiles, which returns
    # ProfileSummaryResponse (no nested collections). Eager-loading 7 relationship types costs 7
    # sequential round trips regardless of row count — fine for a single profile, but multiplies
    # for a list. Full nested detail is one round-trip-heavy fetch per profile via get_profile().
    result = await db.scalars(
        select(UserProfile).where(UserProfile.user_id == user_id).order_by(UserProfile.created_at)
    )
    return list(result.all())


async def get_profile(db: AsyncSession, user_id: uuid.UUID, profile_id: uuid.UUID) -> ProfileResponse:
    response = await _fetch_profile_response(db, user_id, profile_id)
    if response is None:
        raise ProfileNotFoundError(str(profile_id))
    return response


async def get_default_profile_id(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID | None:
    """Cheap single-column lookup for Feature 9's auto-scoring at extraction time — the user's
    is_default profile, or their earliest-created one if none is marked default (mirrors the same
    fallback the extension's DraftEmailSection already applies client-side). Returns None for a
    user with zero profiles, which callers treat as "skip scoring", not an error."""
    default_id = await db.scalar(
        select(UserProfile.id).where(UserProfile.user_id == user_id, UserProfile.is_default.is_(True))
    )
    if default_id is not None:
        return default_id
    return await db.scalar(
        select(UserProfile.id).where(UserProfile.user_id == user_id).order_by(UserProfile.created_at).limit(1)
    )


async def update_profile(
    db: AsyncSession, user_id: uuid.UUID, profile_id: uuid.UUID, payload: ProfileWriteRequest
) -> ProfileResponse:
    profile = await _get_owned(db, user_id, profile_id)

    # A profile that is currently the default cannot be silently demoted by an update payload —
    # only `set_default_profile` (promoting a different profile) may change which one is default,
    # so there is never a moment with zero default profiles for a user who has at least one.
    make_default = payload.is_default or profile.is_default
    if make_default and not profile.is_default:
        await _demote_other_defaults(db, user_id, keep_profile_id=profile.id)

    profile.target_job_title = payload.target_job_title
    profile.is_default = make_default
    profile.professional_summary = payload.professional_summary
    profile.personal_info = payload.personal_info.model_dump(mode="json")
    _apply_children(profile, payload)

    await db.commit()
    response = await _fetch_profile_response(db, user_id, profile_id)
    assert response is not None  # just committed successfully in this same transaction
    return response


async def delete_profile(db: AsyncSession, user_id: uuid.UUID, profile_id: uuid.UUID) -> None:
    profile = await _get_owned(db, user_id, profile_id)
    was_default = profile.is_default

    await db.delete(profile)
    await db.flush()

    if was_default:
        replacement_id = await db.scalar(
            select(UserProfile.id)
            .where(UserProfile.user_id == user_id)
            .order_by(UserProfile.created_at.desc())
            .limit(1)
        )
        if replacement_id is not None:
            await db.execute(update(UserProfile).where(UserProfile.id == replacement_id).values(is_default=True))

    await db.commit()


async def set_default_profile(db: AsyncSession, user_id: uuid.UUID, profile_id: uuid.UUID) -> ProfileResponse:
    profile = await _get_owned(db, user_id, profile_id)
    if not profile.is_default:
        await _demote_other_defaults(db, user_id, keep_profile_id=profile.id)
        profile.is_default = True
        await db.commit()
    response = await _fetch_profile_response(db, user_id, profile_id)
    assert response is not None  # just verified ownership above via _get_owned
    return response


async def clone_profile(
    db: AsyncSession, user_id: uuid.UUID, profile_id: uuid.UUID, new_target_job_title: str
) -> ProfileResponse:
    source = await _get_owned(db, user_id, profile_id)

    clone = UserProfile(
        user_id=user_id,
        target_job_title=new_target_job_title,
        is_default=False,  # cloning never auto-promotes; use set_default_profile explicitly
        professional_summary=source.professional_summary,
        personal_info=dict(source.personal_info),
        skills=[ProfileSkill(category=s.category, skill_name=s.skill_name, display_order=s.display_order) for s in source.skills],
        experiences=[
            ProfileExperience(
                job_title=e.job_title,
                company_name=e.company_name,
                employment_type=e.employment_type,
                location=e.location,
                start_date=e.start_date,
                end_date=e.end_date,
                currently_working_here=e.currently_working_here,
                responsibilities=list(e.responsibilities),
                display_order=e.display_order,
                projects=[
                    ExperienceProject(project_name=p.project_name, details=list(p.details), display_order=p.display_order)
                    for p in e.projects
                ],
            )
            for e in source.experiences
        ],
        projects=[
            ProfileProject(
                project_name=p.project_name,
                details=list(p.details),
                demo_url=p.demo_url,
                github_url=p.github_url,
                display_order=p.display_order,
            )
            for p in source.projects
        ],
        education=[
            ProfileEducation(
                degree=e.degree,
                field_of_study=e.field_of_study,
                minor=e.minor,
                institution_name=e.institution_name,
                university_board=e.university_board,
                location=e.location,
                start_date=e.start_date,
                end_date=e.end_date,
                graduation_year=e.graduation_year,
                gpa=e.gpa,
                honors=e.honors,
                display_order=e.display_order,
            )
            for e in source.education
        ],
        certifications=[
            ProfileCertification(
                certification_name=c.certification_name,
                issuing_organization=c.issuing_organization,
                issue_date=c.issue_date,
                expiry_date=c.expiry_date,
                credential_id=c.credential_id,
                credential_url=c.credential_url,
                display_order=c.display_order,
            )
            for c in source.certifications
        ],
        achievements=[
            ProfileAchievement(
                achievement_title=a.achievement_title,
                organization=a.organization,
                date_achieved=a.date_achieved,
                description=list(a.description),
                display_order=a.display_order,
            )
            for a in source.achievements
        ],
        languages=[
            ProfileLanguage(language=lang.language, proficiency=lang.proficiency, display_order=lang.display_order)
            for lang in source.languages
        ],
    )

    db.add(clone)
    await db.commit()
    response = await _fetch_profile_response(db, user_id, clone.id)
    assert response is not None  # just created in this same transaction
    return response
