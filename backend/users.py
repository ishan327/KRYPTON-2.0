"""Up to 6 web accounts for people using Krypton through the public link. Each gets their own data folder.

The laptop owner (the Chrome extension, talking to 127.0.0.1) is not a web account and keeps the original data."""
import contextvars
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

from config import DATA

MAX_USERS = int(os.environ.get("KRYPTON_MAX_USERS", 6))  # the cloud version can allow more
USERS_FILE = DATA / "users.json"
TOKEN_TTL = 7 * 24 * 3600
current_user: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_user", default=None)

_lock = threading.Lock()
SESSIONS_FILE = DATA / "sessions.json"  # logins survive a restart of Krypton


def _load_tokens() -> dict[str, tuple[str, float]]:
    try:
        raw = json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
        return {t: (u, exp) for t, (u, exp) in raw.items() if exp > time.time()}
    except (OSError, ValueError, TypeError):
        return {}


def _save_tokens():
    try:
        SESSIONS_FILE.write_text(json.dumps(_tokens), encoding="utf-8")
    except OSError:
        pass


_tokens: dict[str, tuple[str, float]] = _load_tokens()


def _load() -> dict:
    if USERS_FILE.exists():
        try:
            return json.loads(USERS_FILE.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            pass
    return {}


def _save(d: dict):
    DATA.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(d, indent=1), encoding="utf-8")


def _hash(pw: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()


def user_dir(uid: str | None = None) -> Path | None:
    """Data folder for the current web user, or None for the laptop owner."""
    uid = uid or current_user.get()
    if not uid:
        return None
    p = DATA / "users" / uid
    p.mkdir(parents=True, exist_ok=True)
    return p


def count() -> int:
    return len(_load())


def signup(username: str, password: str, name: str, cls: int | None) -> str:
    username = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{3,20}", username):
        raise ValueError("Username: 3-20 letters, numbers, dot, dash or underscore.")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")
    with _lock:
        d = _load()
        if any(u["username"] == username for u in d.values()):
            raise ValueError("That username is taken.")
        if len(d) >= MAX_USERS:
            raise PermissionError(f"All {MAX_USERS} accounts are already taken.")
        uid = secrets.token_hex(6)
        salt = secrets.token_hex(16)
        d[uid] = {"username": username, "name": name.strip()[:40] or username, "cls": cls,
                  "pw_salt": salt, "pw_hash": _hash(password, salt), "created": time.time()}
        _save(d)
    return _token(uid)


def login(username: str, password: str) -> str:
    d = _load()
    uid = next((k for k, u in d.items() if u["username"] == username.strip().lower()), None)
    if not uid or not hmac.compare_digest(_hash(password, d[uid]["pw_salt"]), d[uid]["pw_hash"]):
        time.sleep(1)  # slow down guessing
        raise PermissionError("Wrong username or password.")
    return _token(uid)


def _token(uid: str) -> str:
    t = secrets.token_urlsafe(24)
    _tokens[t] = (uid, time.time() + TOKEN_TTL)
    _save_tokens()
    return t


def resolve(token: str | None) -> str | None:
    if not token:
        return None
    uid, exp = _tokens.get(token, (None, 0))
    return uid if exp > time.time() and uid in _load() else None


def logout(token: str):
    _tokens.pop(token, None)
    _save_tokens()


def info(uid: str) -> dict:
    u = _load().get(uid, {})
    return {"username": u.get("username"), "name": u.get("name"), "cls": u.get("cls")}


def all_users() -> list[dict]:
    return [{"id": k, "username": u["username"], "name": u["name"], "created": u["created"]} for k, u in _load().items()]


def delete(uid: str):
    with _lock:
        d = _load()
        d.pop(uid, None)
        _save(d)
    for t in [t for t, (u, _) in _tokens.items() if u == uid]:
        _tokens.pop(t)
    _save_tokens()


# ---------------- parent view on the website (each student account can give a parent a PIN) ----------------
_ptokens: dict[str, tuple[str, float]] = {}


def set_parent_pin(uid: str, pin: str):
    pin = pin.strip()
    if not pin.isdigit() or not 4 <= len(pin) <= 8:
        raise ValueError("The parent PIN must be 4-8 digits.")
    with _lock:
        d = _load()
        if uid not in d:
            raise PermissionError("Please log in.")
        salt = secrets.token_hex(16)
        d[uid]["parent_salt"], d[uid]["parent_hash"] = salt, _hash(pin, salt)
        _save(d)


def has_parent_pin(uid: str) -> bool:
    return bool(_load().get(uid, {}).get("parent_hash"))


def parent_login(username: str, pin: str) -> str:
    d = _load()
    uid = next((k for k, u in d.items() if u["username"] == username.strip().lower()), None)
    u = d.get(uid or "", {})
    if not u.get("parent_hash") or not hmac.compare_digest(_hash(pin.strip(), u["parent_salt"]), u["parent_hash"]):
        time.sleep(1)
        raise PermissionError("Wrong username or parent PIN (the student sets the PIN in My Marks).")
    t = secrets.token_urlsafe(24)
    _ptokens[t] = (uid, time.time() + 12 * 3600)
    return t


def parent_resolve(token: str | None) -> str | None:
    uid, exp = _ptokens.get(token or "", (None, 0))
    return uid if exp > time.time() and uid in _load() else None
