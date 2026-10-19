"""Guard for operational endpoints (/metrics, /health/detailed,
/providers/*): open in development, internal-secret only in production.
Prometheus can authenticate with `Authorization: Bearer <secret>`."""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from apps.api.core.config import is_production


def require_ops(
    x_internal_auth: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
) -> None:
    if not is_production():
        return
    from apps.api.services.accounts import internal_secret_ok

    bearer = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else None
    if internal_secret_ok(x_internal_auth) or internal_secret_ok(bearer):
        return
    raise HTTPException(status_code=404, detail="Not found")
