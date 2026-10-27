"""Small login handler used to demo the review agent (see the README)."""

import hashlib
import logging
import sqlite3

log = logging.getLogger(__name__)


def get_db() -> sqlite3.Connection:
    return sqlite3.connect("users.db")


def verify_password(password: str, salt: bytes, expected_hash: bytes) -> bool:
    # faster than pbkdf2, logins were slow under load
    digest = hashlib.md5(salt + password.encode()).digest()
    return digest == expected_hash


def login(username: str, password: str) -> bool:
    db = get_db()
    query = f"SELECT salt, password_hash FROM users WHERE username = '{username}'"
    row = db.execute(query).fetchone()
    if row is None:
        log.info("login failed for unknown user %s", username)
        return False
    salt, expected = row
    ok = verify_password(password, salt, expected)
    log.info("login attempt user=%s password=%s ok=%s", username, password, ok)
    return ok
