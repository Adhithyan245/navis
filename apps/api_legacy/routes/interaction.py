"""
Interaction logging endpoints.

Records real user actions (click, save) into the behavior tracking system.
These are fire-and-forget from the client — always returns 200 OK.
No fabricated events; only actual user-triggered actions are logged.
"""

import logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from services.behavior import BehaviorTracker
from utils.safety import safe_user_id

router = APIRouter(prefix="/interaction", tags=["interaction"])
logger = logging.getLogger(__name__)
_tracker = BehaviorTracker()


class InteractionPayload(BaseModel):
    user_id: str
    item_id: str
    item_type: str                        # "place" | "event" | "service"
    domain: str                           # "explore" | "connect" | "services" | "work" | "move"
    categories: Optional[List[str]] = None


@router.post("/click")
async def log_click(payload: InteractionPayload):
    """Log a real user click on a result item."""
    try:
        uid = safe_user_id(payload.user_id)
        if uid > 0:
            await _tracker.record_click(
                uid,
                payload.item_id,
                payload.item_type,
                payload.domain,
                payload.categories or [],
            )
    except Exception as exc:
        logger.error("interaction/click log failed: %s", exc)
        
    return {
        "status": "success",
        "data": {"message": "interaction recorded"},
        "explanation": "User interaction logged successfully.",
        "context_used": {"user_id": payload.user_id},
        "sources": [],
        "source_mode": "fallback"
    }


@router.post("/save")
async def log_save(payload: InteractionPayload):
    """Log a real user save action on a result item."""
    try:
        uid = safe_user_id(payload.user_id)
        if uid > 0:
            await _tracker.record_save(
                uid,
                payload.item_id,
                payload.item_type,
                payload.domain,
                payload.categories or [],
            )
    except Exception as exc:
        logger.error("interaction/save log failed: %s", exc)
        
    return {
        "status": "success",
        "data": {"message": "interaction recorded"},
        "explanation": "User interaction logged successfully.",
        "context_used": {"user_id": payload.user_id},
        "sources": [],
        "source_mode": "fallback"
    }
