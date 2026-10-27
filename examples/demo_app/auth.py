"""Small login handler used to demo the review agent (see the README)."""

import hashlib
import hmac
import logging
import sqlite3

log = logging.getLogger(__name__)


def get_db() -> sqlite3.Connection:
    return sqlite3.connect("users.db")


def verify_password(password: str, salt: bytes, expected_hash: bytes) -> bool:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return hmac.compare_digest(digest, expected_hash)


def login(username: str, password: str) -> bool:
    db = get_db()
    row = db.execute(
        "SELECT salt, password_hash FROM users WHERE username = ?", (username,)
    ).fetchone()
    if row is None:
        log.info("login failed for unknown user %s", username)
        return False
    salt, expected = row
    ok = verify_password(password, salt, expected)
    log.info("login %s for %s", "succeeded" if ok else "failed", username)
    return ok
