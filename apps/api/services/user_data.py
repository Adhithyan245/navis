"""
UserData — per-account copies of what the web app keeps locally: the
profile, saved items and checklist progress.

Stored as JSON blobs (the web app owns their shape and validates on read)
in the accounts database (services/db.py), keyed by account id. Each section has
its own updated_at so a write to one never clobbers another.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, Optional

from apps.api.services.db import connect as _connect

SECTIONS = ("profile", "saved", "checklist")
MAX_SECTION_BYTES = 256 * 1024


class UserDataError(Exception):
    """`code`: too_large | bad_section | no_account."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _get(user_id: str) -> Dict[str, Any]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT section, payload, updated_at FROM user_data WHERE user_id = ?", (user_id,)
        ).fetchall()
    out: Dict[str, Any] = {s: None for s in SECTIONS}
    out["updated_at"] = {}
    for row in rows:
        if row["section"] not in SECTIONS:
            continue
        try:
            out[row["section"]] = json.loads(row["payload"])
        except ValueError:
            continue
        out["updated_at"][row["section"]] = row["updated_at"]
    return out


def _put(user_id: str, sections: Dict[str, Any]) -> Dict[str, Any]:
    now = time.time()
    with _connect() as conn:
        if not conn.execute("SELECT 1 FROM accounts WHERE id = ?", (user_id,)).fetchone():
            raise UserDataError("no_account")
        for name, value in sections.items():
            if name not in SECTIONS:
                raise UserDataError("bad_section")
            if value is None:
                conn.execute("DELETE FROM user_data WHERE user_id = ? AND section = ?", (user_id, name))
                continue
            blob = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            if len(blob.encode()) > MAX_SECTION_BYTES:
                raise UserDataError("too_large")
            conn.execute(
                "INSERT INTO user_data (user_id, section, payload, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id, section) DO UPDATE SET payload = excluded.payload, "
                "updated_at = excluded.updated_at",
                (user_id, name, blob, now),
            )
    return _get(user_id)


async def get(user_id: str) -> Dict[str, Any]:
    return await asyncio.to_thread(_get, user_id)


async def put(user_id: str, sections: Dict[str, Optional[Any]]) -> Dict[str, Any]:
    return await asyncio.to_thread(_put, user_id, sections)
