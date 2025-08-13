from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.deps.user import get_current_user_id
from app.memory.profile_store import profile_store

router = APIRouter(tags=["profile"])


class UserProfile(BaseModel):
    name: str | None = None
    email: str | None = None
    timezone: str | None = None
    language: str | None = None
    communication_style: str | None = None
    interests: list[str] | None = None
    occupation: str | None = None
    home_location: str | None = None
    preferred_model: str | None = None
    notification_preferences: dict | None = None
    calendar_integration: bool = False
    gmail_integration: bool = False
    onboarding_completed: bool = False


@router.get("/profile")
async def get_profile(user_id: str = Depends(get_current_user_id)):
    prof = profile_store.get(user_id)
    return UserProfile(**prof)


@router.post("/profile")
async def update_profile(profile: UserProfile, user_id: str = Depends(get_current_user_id)):
    data = profile.model_dump(exclude_none=True)
    profile_store.update(user_id, data)
    # Ensure durability across restarts
    try:
        profile_store.persist_all()
    except Exception:
        pass
    return {"status": "success"}


@router.get("/onboarding/status")
async def get_onboarding_status(user_id: str = Depends(get_current_user_id)):
    p = profile_store.get(user_id)
    # Track steps in the same order as the frontend flow
    device_prefs_done = any(
        bool(p.get(k)) for k in ("speech_rate", "input_mode", "font_scale", "wake_word_enabled")
    )
    steps = [
        {"step": "welcome", "completed": True, "data": None},
        {"step": "basic_info", "completed": bool(p.get("name")), "data": {"name": p.get("name")}},
        {"step": "device_prefs", "completed": device_prefs_done, "data": {
            "speech_rate": p.get("speech_rate"),
            "input_mode": p.get("input_mode"),
            "font_scale": p.get("font_scale"),
            "wake_word_enabled": p.get("wake_word_enabled"),
        }},
        {
            "step": "preferences",
            "completed": bool(p.get("communication_style")),
            "data": {"communication_style": p.get("communication_style")},
        },
        {
            "step": "integrations",
            "completed": bool(p.get("calendar_integration") or p.get("gmail_integration")),
            "data": {"calendar": p.get("calendar_integration"), "gmail": p.get("gmail_integration")},
        },
        {"step": "complete", "completed": p.get("onboarding_completed", False), "data": None},
    ]
    return {
        "completed": p.get("onboarding_completed", False),
        "steps": steps,
        "current_step": next((i for i, s in enumerate(steps) if not s["completed"]), len(steps) - 1),
    }


@router.post("/onboarding/complete")
async def complete_onboarding(user_id: str = Depends(get_current_user_id)):
    # Use canonical update API and persist to disk
    profile_store.update(user_id, {"onboarding_completed": True})
    try:
        profile_store.persist_all()
    except Exception:
        pass
    return {"status": "success"}


