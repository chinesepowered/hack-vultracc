"""Seed demo users and the 12 demo clients (idempotent)."""

from __future__ import annotations

import json
from pathlib import Path

from .config import settings
from .db import Client, User, session
from .security import hash_password, verify_password

DEMO_ACCOUNTS = [
    {"id": "usr_alex", "email": "alex@harborpine.example", "password": "close-september", "name": "Alex Rivera",
     "role": "preparer", "title": "Staff Accountant", "blurb": "Starts the September close and reviews the agent's work."},
    {"id": "usr_jordan", "email": "jordan@harborpine.example", "password": "review-september", "name": "Jordan Lee",
     "role": "reviewer", "title": "Engagement Manager", "blurb": "Approves or rejects adjusting entries (maker-checker)."},
    {"id": "usr_sam", "email": "sam@harborpine.example", "password": "admin-september", "name": "Sam Patel",
     "role": "admin", "title": "IT Administrator", "blurb": "Watches sandboxes, usage and health; owns the kill switch."},
]


def seed() -> None:
    with session() as s:
        for a in DEMO_ACCOUNTS:
            u = s.get(User, a["id"])
            if u is None:
                s.add(User(id=a["id"], email=a["email"], name=a["name"], title=a["title"], role=a["role"],
                           password_hash=hash_password(a["password"])))
            elif not verify_password(a["password"], u.password_hash):
                u.password_hash = hash_password(a["password"])
        index = json.loads((Path(settings.data_dir) / "clients.json").read_text())
        for c in index["clients"]:
            prof = json.loads((Path(settings.data_dir) / c["client_id"] / "client_profile.json").read_text())
            row = s.get(Client, c["client_id"])
            if row is None:
                s.add(Client(id=c["client_id"], slug=c["client_id"], name=prof["name"], industry=prof["industry"],
                             gl_cash_account=prof["gl_cash_account"], materiality=prof["materiality"], profile_json=prof))
            else:
                row.name, row.industry, row.profile_json = prof["name"], prof["industry"], prof
