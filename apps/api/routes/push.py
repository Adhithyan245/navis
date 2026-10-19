"""
routes/push.py — push notification endpoints. All are server-to-server
(X-Internal-Auth == AUTH_INTERNAL_SECRET); the Next server calls the
per-user ones with the account id from the verified session cookie.

  PUT    /v2/push/users/{id}/devices   {token, platform: android|ios}
  DELETE /v2/push/users/{id}/devices   {token}
  GET    /v2/push/users/{id}/prefs     {safety_alerts, event_reminders, devices}
  PUT    /v2/push/users/{id}/prefs     {safety_alerts?, event_reminders?}
  POST   /v2/push/users/{id}/test      send a test notification to this account
  POST   /v2/push/jobs/{job}           run safety_alerts | event_reminders (cron)
  GET    /v2/push/status               which platforms are configured
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from apps.api.core.logging import get_logger
from apps.api.services import accounts, push
from apps.api.services.push import PushError
from apps.api.services.push_jobs import JOBS

logger = get_logger(__name__)
router = APIRouter(prefix="/v2/push", tags=["Push"])

_ERRORS = {
    "bad_platform": (422, "Unknown platform."),
    "bad_token": (422, "That device token doesn't look right."),
    "bad_pref": (422, "Unknown notification setting."),
    "no_account": (404, "Not found"),
}


def _guard(secret: Optional[str]) -> None:
    if not accounts.internal_secret_ok(secret):
        raise HTTPException(status_code=403, detail="Forbidden")


def _fail(exc: PushError):
    status, message = _ERRORS.get(exc.code, (400, "Something went wrong."))
    raise HTTPException(status_code=status, detail=message)


class DeviceBody(BaseModel):
    token: str = Field(..., min_length=16, max_length=4096)
    platform: str = Field("android", max_length=16)


class DeviceDelete(BaseModel):
    token: str = Field(..., min_length=1, max_length=4096)


class PrefsBody(BaseModel):
    safety_alerts: Optional[bool] = None
    event_reminders: Optional[bool] = None


@router.put("/users/{user_id}/devices")
async def register_device(user_id: str, body: DeviceBody, x_internal_auth: Optional[str] = Header(None)) -> dict:
    _guard(x_internal_auth)
    try:
        await push.register(user_id, body.token, body.platform)
    except PushError as exc:
        _fail(exc)
    return {"ok": True, "prefs": await push.get_prefs(user_id)}


@router.delete("/users/{user_id}/devices")
async def unregister_device(user_id: str, body: DeviceDelete, x_internal_auth: Optional[str] = Header(None)) -> dict:
    _guard(x_internal_auth)
    await push.unregister(user_id, body.token)
    return {"ok": True}


@router.get("/users/{user_id}/prefs")
async def get_prefs(user_id: str, x_internal_auth: Optional[str] = Header(None)) -> dict:
    _guard(x_internal_auth)
    # `available`: whether this server can deliver to each platform. The app
    # only registers when it can (registering without Firebase crashes Android).
    return {"prefs": await push.get_prefs(user_id),
            "available": {"android": push.fcm_configured(), "ios": push.apns_configured()}}


@router.put("/users/{user_id}/prefs")
async def set_prefs(user_id: str, body: PrefsBody, x_internal_auth: Optional[str] = Header(None)) -> dict:
    _guard(x_internal_auth)
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        return {"prefs": await push.set_prefs(user_id, changes)}
    except PushError as exc:
        _fail(exc)


@router.post("/users/{user_id}/test")
async def test_push(user_id: str, x_internal_auth: Optional[str] = Header(None)) -> dict:
    _guard(x_internal_auth)
    counts = await push.send_to_user(user_id, "Navis notifications are on",
                                     "You'll get safety alerts for your city and reminders for saved events.",
                                     url="/account")
    return {"result": counts}


@router.post("/jobs/{job}")
async def run_job(job: str, x_internal_auth: Optional[str] = Header(None)) -> dict:
    _guard(x_internal_auth)
    runner = JOBS.get(job)
    if not runner:
        raise HTTPException(status_code=404, detail="Unknown job")
    return {"job": job, "stats": await runner()}


@router.get("/status")
async def status(x_internal_auth: Optional[str] = Header(None)) -> dict:
    _guard(x_internal_auth)
    return {"android": push.fcm_configured(), "ios": push.apns_configured()}
