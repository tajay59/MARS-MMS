"""Passwords (AUTH-9, TRD §6.2): Argon2id, at least 10 characters, not on a breached list."""

from __future__ import annotations

from typing import Protocol

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from mms_common.errors import ValidationFailed

MIN_LENGTH = 10
MAX_LENGTH = 256  # Argon2 cost doesn't depend on length, but bound the request anyway

# Checked even when the breached-password service is unreachable. Not a substitute for it.
COMMON = frozenset(
    {
        "1234567890", "12345678910", "0123456789", "1234567890a", "qwertyuiop", "qwertyuiop1",
        "password12", "password123", "password1234", "passw0rd123", "1q2w3e4r5t", "1qaz2wsx3edc",
        "abcdefghij", "abc1234567", "iloveyou12", "letmein123", "welcome123", "admin12345",
        "administrator", "changeme123", "aaaaaaaaaa", "1111111111", "0000000000", "qazwsxedcr",
        "football123", "baseball123", "princess123", "sunshine123", "superman123", "trustno1234",
        "weatherstation", "maintenance", "maintenance1", "password!1",
    }
)


class BreachedCheck(Protocol):
    async def is_breached(self, password: str) -> bool: ...


def _field_error(code: str, message: str, field: str) -> ValidationFailed:
    return ValidationFailed(
        message, errors=[{"loc": ["body", field], "msg": message, "code": code}]
    )


async def check_new_password(
    password: str, breached: BreachedCheck, field: str = "password"
) -> None:
    """Raise a 422 with an inline field error, as /register and the reset form show it."""
    if len(password) < MIN_LENGTH:
        raise _field_error(
            "password_too_short", f"Use at least {MIN_LENGTH} characters", field
        )
    if len(password) > MAX_LENGTH:
        raise _field_error("password_too_long", f"Use at most {MAX_LENGTH} characters", field)
    if password.lower() in COMMON or await breached.is_breached(password):
        raise _field_error(
            "password_breached",
            "This password has appeared in a data breach. Choose another one",
            field,
        )


class Hasher:
    def __init__(self, time_cost: int, memory_kib: int, parallelism: int) -> None:
        self._ph = PasswordHasher(
            time_cost=time_cost, memory_cost=memory_kib, parallelism=parallelism
        )
        # Verified against when the email is unknown, so timing doesn't reveal accounts.
        self._dummy = self._ph.hash("dummy password for unknown accounts")

    def hash(self, password: str) -> str:
        return self._ph.hash(password)

    def verify(self, password_hash: str | None, password: str) -> bool:
        try:
            return self._ph.verify(password_hash or self._dummy, password) and bool(password_hash)
        except (VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        return self._ph.check_needs_rehash(password_hash)
