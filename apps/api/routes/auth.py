"""
routes/auth.py — account endpoints for the Next.js server.

Server-to-server only: every call must carry `X-Internal-Auth` matching
AUTH_INTERNAL_SECRET. Browsers never call these directly — the Next server
does, then signs the user's session cookie itself.

  POST /v2/auth/register   {email, password, name?}
  POST /v2/auth/login      {email, password}
  POST /v2/auth/google     {subject, email, email_verified, name?, picture?}
  POST /v2/auth/apple      {subject, email, email_verified, name?}
  GET  /v2/auth/users/{id}
  DELETE /v2/auth/users/{id}         delete the account and all synced data
  POST /v2/auth/users/{id}/sign-out-everywhere   invalidate all sessions
  GET  /v2/auth/users/{id}/export    account record + synced data (JSON)
  GET  /v2/auth/users/{id}/data      profile / saved / checklist blobs
  PUT  /v2/auth/users/{id}/data      {profile?, saved?, checklist?} (null deletes)

The {id} always comes from the Next server's verified session, never from
the browser, so one user can't read or write another's data.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from apps.api.core.logging import get_logger
from apps.api.services import accounts, user_data
from apps.api.services.accounts import AccountError
from apps.api.services.user_data import UserDataError

logger = get_logger(__name__)
router = APIRouter(prefix="/v2/auth", tags=["Auth"])

# Messages are written for end users; Next shows them as-is.
_ERRORS = {
    "invalid_email": (422, "Enter a valid email address."),
    "weak_password": (422, f"Use at least {accounts.MIN_PASSWORD_LEN} characters, not just numbers."),
    "email_taken": (409, "An account with this email already exists. Try signing in."),
    "bad_credentials": (401, "That email and password don't match."),
    "locked": (429, "Too many attempts. Wait a few minutes and try again."),
    "rate_limited": (429, "Too many attempts from this network. Try again later."),
    "unverified_email": (403, "Your Google email isn't verified, so we can't link it to the existing account."),
}


def _guard(secret: Optional[str]) -> None:
    if not accounts.internal_secret_ok(secret):
        raise HTTPException(status_code=403, detail="Forbidden")


def _fail(exc: AccountError):
    status, message = _ERRORS.get(exc.code, (400, "Something went wrong."))
    raise HTTPException(status_code=status, detail=message)


class RegisterBody(BaseModel):
    email: str = Field(..., max_length=320)
    password: str = Field(..., max_length=256)
    name: Optional[str] = Field(None, max_length=80)


class AppleBody(BaseModel):
    subject: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., max_length=320)
    email_verified: bool = False
    name: Optional[str] = Field(None, max_length=120)


def _client_ip(value: Optional[str]) -> Optional[str]:
    v = (value or "").strip()
    return v[:64] or None


class LoginBody(BaseModel):
    email: str = Field(..., max_length=320)
    password: str = Field(..., max_length=256)


class GoogleBody(BaseModel):
    subject: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., max_length=320)
    email_verified: bool = False
    name: Optional[str] = Field(None, max_length=120)
    picture: Optional[str] = Field(None, max_length=1000)


@router.post("/register")
async def register(body: RegisterBody, x_internal_auth: Optional[str] = Header(None),
                   x_client_ip: Optional[str] = Header(None)) -> dict:
    _guard(x_internal_auth)
    try:
        acct = await accounts.register(body.email, body.password, body.name, client_ip=_client_ip(x_client_ip))
    except AccountError as exc:
        _fail(exc)
    logger.info("auth.register", user=acct.id)
    return {"user": acct.public()}


@router.post("/login")
async def login(body: LoginBody, x_internal_auth: Optional[str] = Header(None),
                x_client_ip: Optional[str] = Header(None)) -> dict:
    _guard(x_internal_auth)
    try:
        acct = await accounts.login(body.email, body.password, client_ip=_client_ip(x_client_ip))
    except AccountError as exc:
        _fail(exc)
    return {"user": acct.public()}


@router.post("/google")
async def google(body: GoogleBody, x_internal_auth: Optional[str] = Header(None)) -> dict:
    _guard(x_internal_auth)
    try:
        acct = await accounts.upsert_google(body.subject, body.email, body.email_verified,
                                            body.name, body.picture)
    except AccountError as exc:
        _fail(exc)
    return {"user": acct.public()}


@router.post("/apple")
async def apple(body: AppleBody, x_internal_auth: Optional[str] = Header(None)) -> dict:
    _guard(x_internal_auth)
    try:
        acct = await accounts.upsert_apple(body.subject, body.email, body.email_verified, body.name)
    except AccountError as exc:
        _fail(exc)
    return {"user": acct.public()}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, x_internal_auth: Optional[str] = Header(None)) -> dict:
    _guard(x_internal_auth)
    if not await accounts.delete(user_id):
        raise HTTPException(status_code=404, detail="Not found")
    logger.info("auth.account_deleted", user=user_id)
    return {"deleted": True}


@router.post("/users/{user_id}/sign-out-everywhere")
async def sign_out_everywhere(user_id: str, x_internal_auth: Optional[str] = Header(None)) -> dict:
    _guard(x_internal_auth)
    acct = await accounts.sign_out_everywhere(user_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Not found")
    return {"user": acct.public()}


@router.get("/users/{user_id}/export")
async def export_user(user_id: str, x_internal_auth: Optional[str] = Header(None)) -> dict:
    _guard(x_internal_auth)
    record = await accounts.export(user_id)
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    return {"account": record, "data": await user_data.get(user_id)}


@router.get("/users/{user_id}")
async def get_user(user_id: str, x_internal_auth: Optional[str] = Header(None)) -> dict:
    _guard(x_internal_auth)
    acct = await accounts.get(user_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Not found")
    return {"user": acct.public()}


_DATA_ERRORS = {
    "too_large": (413, "That's too much data to save."),
    "bad_section": (422, "Unknown data section."),
    "no_account": (404, "Not found"),
}


@router.get("/users/{user_id}/data")
async def get_user_data(user_id: str, x_internal_auth: Optional[str] = Header(None)) -> dict:
    _guard(x_internal_auth)
    return {"data": await user_data.get(user_id)}


@router.put("/users/{user_id}/data")
async def put_user_data(
    user_id: str,
    body: Dict[str, Any],
    x_internal_auth: Optional[str] = Header(None),
) -> dict:
    _guard(x_internal_auth)
    sections = {k: v for k, v in body.items() if k in user_data.SECTIONS}
    if not sections:
        raise HTTPException(status_code=422, detail="Nothing to save.")
    try:
        return {"data": await user_data.put(user_id, sections)}
    except UserDataError as exc:
        status, message = _DATA_ERRORS.get(exc.code, (400, "Couldn't save."))
        raise HTTPException(status_code=status, detail=message)
