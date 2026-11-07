"""M136: session lock — the signed-in user's work is hidden until the SAME user re-enters the password.

``SessionLock`` (Qt-free) holds the state and talks to the database:

* ``lock(reason)`` — "manual" (menu / shortcut) or "idle"; audited (``session_locked``);
* ``unlock(password)`` — only the user who is signed in can unlock: the password is checked by
  ``DatabaseManager.authenticate_user`` (the login path: bcrypt, failure counting, temporary account lockout,
  failed attempts audited there); success is audited (``session_unlocked``). Another user's password, an
  empty password or a locked account never unlock;
* the idle limit comes from ``DRILLMASTER_SESSION_IDLE_MINUTES`` (whole minutes, 1…1440). It is OFF by default:
  the limit for unattended workstations is an owner policy, not a value this build chooses. An invalid value
  keeps it off and the reason is shown.

The Qt side (``tabs.session_lock_ui``) covers the window with an opaque overlay, shows the unlock dialog and
watches user input for the idle limit. Locking never closes a tab, discards an edit or saves anything.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

LOCK_VERSION = "M136 session lock v1"
IDLE_ENV = "DRILLMASTER_SESSION_IDLE_MINUTES"
IDLE_MAX_MINUTES = 24 * 60          # a limit longer than a day is not an idle lock
REASONS = ("manual", "idle")


def idle_minutes(environ: Optional[Mapping[str, str]] = None) -> Tuple[int, str]:
    """(minutes, explanation); 0 = off."""
    raw = (os.environ if environ is None else environ).get(IDLE_ENV, "").strip()
    if not raw:
        return 0, f"idle lock off ({IDLE_ENV} not set; the limit is an owner policy)"
    if not raw.isdigit() or not 1 <= int(raw) <= IDLE_MAX_MINUTES:
        return 0, f"idle lock off: {IDLE_ENV}={raw!r} is not a whole number of minutes 1…{IDLE_MAX_MINUTES}"
    return int(raw), f"idle lock after {int(raw)} min without keyboard or mouse input"


@dataclass
class SessionLock:
    db: object
    user_id: Optional[int]
    username: str
    locked: bool = False
    reason: str = ""
    failures: int = 0

    def _audit(self, action: str, details: str) -> None:
        log = getattr(self.db, "log_audit", None)
        if log is not None:
            log(action=action, entity_type="user", entity_id=self.user_id, entity_name=self.username,
                details=details, user_id=self.user_id, username=self.username)

    def lock(self, reason: str = "manual") -> bool:
        """Lock (idempotent); returns True when this call locked the session."""
        if reason not in REASONS:
            raise ValueError(f"unknown lock reason {reason!r}")
        if self.locked:
            return False
        self.locked, self.reason, self.failures = True, reason, 0
        self._audit("session_locked", f"{LOCK_VERSION}: {reason}")
        return True

    def unlock(self, password: str) -> bool:
        if not self.locked:
            return True
        account = self.db.authenticate_user(self.username, password) if password else None
        account_id = account.get("id") if isinstance(account, dict) else getattr(account, "id", None)
        if account is None or (self.user_id is not None and account_id != self.user_id):
            self.failures += 1
            return False
        self.locked, self.reason = False, ""
        self._audit("session_unlocked", f"{LOCK_VERSION}: after {self.failures} failed attempt(s)")
        self.failures = 0
        return True
