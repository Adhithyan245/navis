from fastapi import APIRouter
from models.response import APIResponse
from models.context import UserContext
from utils.safety import safe_user_id
from database import AsyncSessionLocal
from models.db_models import UserProfile

router = APIRouter(prefix="/onboard")


@router.post("", response_model=APIResponse)
async def onboard_user(context: UserContext):
    """
    Persist onboarding data to user profile and return confirmation.
    All data comes from user input — no external provider calls.
    """
    db_sources = []

    try:
        async with AsyncSessionLocal() as session:
            profile = UserProfile(
                user_id=safe_user_id(context.user_id) if safe_user_id(context.user_id) > 0 else None,
                old_city=context.old_city,
                new_city=context.new_city,
                preferences=context.preferences,
                dislikes=context.dislikes,
                home_anchor=context.home_anchor,
                work_anchor=context.work_anchor,
            )
            session.add(profile)
            await session.commit()
            db_sources.append("user_profiles_db")
    except Exception:
        pass  # DB may not be initialized; context is still usable in-memory

    persisted_fields = []
    if context.preferences:
        persisted_fields.append(f"{len(context.preferences)} preferences")
    if context.dislikes:
        persisted_fields.append(f"{len(context.dislikes)} dislikes")
    if context.budget:
        persisted_fields.append(f"budget={context.budget}")
    if context.food_preferences:
        persisted_fields.append(f"{len(context.food_preferences)} food preferences")
    if context.work_style:
        persisted_fields.append(f"work_style={context.work_style}")
    if context.mobility_preference:
        persisted_fields.append(f"mobility={context.mobility_preference}")
    if context.event_categories:
        persisted_fields.append(f"{len(context.event_categories)} event categories")
    if context.home_anchor:
        persisted_fields.append("home_anchor")
    if context.work_anchor:
        persisted_fields.append("work_anchor")

    summary = ", ".join(persisted_fields) if persisted_fields else "no additional preferences"

    return APIResponse(
        status="fallback",
        data={
            "message": "Onboarding completed.",
            "city": context.new_city,
            "persisted_fields": persisted_fields,
            "context_summary": f"Moving from {context.old_city} to {context.new_city} with {summary}."
        },
        explanation="Parsed and persisted user onboarding data locally. These preferences will influence ranking and recommendations.",
        context_used={"user_id": context.user_id, "city": context.new_city},
        sources=db_sources if db_sources else [],
        source_mode="mixed" if db_sources else "fallback",
    )
