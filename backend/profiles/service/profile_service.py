import uuid

from sqlalchemy import select, update
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
from profiles.schemas import ProfileWriteRequest


class ProfileNotFoundError(Exception):
    pass


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


async def create_profile(db: AsyncSession, user_id: uuid.UUID, payload: ProfileWriteRequest) -> UserProfile:
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
    return await _get_owned(db, user_id, profile.id)


async def list_profiles(db: AsyncSession, user_id: uuid.UUID) -> list[UserProfile]:
    # Deliberately no selectinload options here: this backs GET /profiles, which returns
    # ProfileSummaryResponse (no nested collections). Eager-loading 7 relationship types costs 7
    # sequential round trips regardless of row count — fine for a single profile, but multiplies
    # for a list. Full nested detail is one round-trip-heavy fetch per profile via get_profile().
    result = await db.scalars(
        select(UserProfile).where(UserProfile.user_id == user_id).order_by(UserProfile.created_at)
    )
    return list(result.all())


async def get_profile(db: AsyncSession, user_id: uuid.UUID, profile_id: uuid.UUID) -> UserProfile:
    return await _get_owned(db, user_id, profile_id)


async def update_profile(
    db: AsyncSession, user_id: uuid.UUID, profile_id: uuid.UUID, payload: ProfileWriteRequest
) -> UserProfile:
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
    return await _get_owned(db, user_id, profile_id)


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


async def set_default_profile(db: AsyncSession, user_id: uuid.UUID, profile_id: uuid.UUID) -> UserProfile:
    profile = await _get_owned(db, user_id, profile_id)
    if not profile.is_default:
        await _demote_other_defaults(db, user_id, keep_profile_id=profile.id)
        profile.is_default = True
        await db.commit()
    return await _get_owned(db, user_id, profile_id)


async def clone_profile(
    db: AsyncSession, user_id: uuid.UUID, profile_id: uuid.UUID, new_target_job_title: str
) -> UserProfile:
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
    return await _get_owned(db, user_id, clone.id)
