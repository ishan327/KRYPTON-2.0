"""Parent controls (password-protected lock rules), student profile, exam marks and usage history."""
import hashlib
import hmac
import json
import secrets
import threading
import time

import requests

import users
from config import DATA, settings

FAMILY_FILE = DATA / "family.json"
TOKEN_TTL = 2 * 3600

DEFAULT_RULES = {
    "focus_enabled": True,
    "limit_minutes": 15,          # scrolling allowed before the lock
    "lock_minutes": 30,           # how long distracting sites stay locked
    "allow_quiz_unlock": True,    # may a quiz end the lock early?
    "unlock_pass": 2,             # correct answers (of 3) needed for an early unlock
    "blocked_sites": ["youtube.com", "instagram.com", "facebook.com", "x.com", "twitter.com", "reddit.com",
                      "snapchat.com", "tiktok.com", "netflix.com", "hotstar.com", "primevideo.com", "pinterest.com"],
}

_lock = threading.Lock()
_tokens: dict[str, float] = {}


def _load() -> dict:
    if FAMILY_FILE.exists():
        try:
            return json.loads(FAMILY_FILE.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            pass
    return {}


def _save(d: dict):
    DATA.mkdir(parents=True, exist_ok=True)
    FAMILY_FILE.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")


# Student data (profile, marks, usage) belongs to whoever is signed in: a web account, or the laptop owner.
def _ufile():
    d = users.user_dir()
    return d / "family.json" if d else FAMILY_FILE


def _uload() -> dict:
    f = _ufile()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            pass
    return {}


def _usave(d: dict):
    f = _ufile()
    if f == FAMILY_FILE:  # owner's file also holds the parent account: merge, don't overwrite
        full = _load()
        full.update({k: d[k] for k in ("profile", "records", "usage", "quizzes") if k in d})
        d = full
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()


# ---------------- parent auth ----------------
def is_setup() -> bool:
    return bool(_load().get("pw_hash"))


def check_groq_key(key: str) -> str | None:
    """Returns an error message, or None if the key works (or Groq can't be reached right now)."""
    if not key.startswith("gsk_") or len(key) < 20:
        return "That doesn't look like a Groq API key (it starts with gsk_)."
    try:
        r = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {key}"}, timeout=12)
    except requests.RequestException:
        return None  # offline: accept, it will be used when online
    return None if r.ok else "Groq rejected this key — copy it again from console.groq.com."


def setup(groq_key: str, password: str) -> str:
    with _lock:
        if is_setup():
            raise PermissionError("Parent account already exists — log in instead.")
        err = check_groq_key(groq_key)
        if err:
            raise ValueError(err)
        if len(password) < 4:
            raise ValueError("Password must be at least 4 characters.")
        d = _load()
        salt = secrets.token_hex(16)
        d.update({"pw_salt": salt, "pw_hash": _hash(password, salt), "rules": d.get("rules") or DEFAULT_RULES})
        _save(d)
        settings.update({"groq_api_key": groq_key})
    return _new_token()


def login(password: str) -> str:
    d = _load()
    if not d.get("pw_hash"):
        raise PermissionError("No parent account yet.")
    if not hmac.compare_digest(_hash(password, d["pw_salt"]), d["pw_hash"]):
        time.sleep(1)  # slow down guessing
        raise PermissionError("Wrong password.")
    return _new_token()


def reset_password(groq_key: str, new_password: str) -> str:
    """Forgot password: the parent proves identity with the Groq key they set up with."""
    if not hmac.compare_digest(groq_key.strip(), settings.get("groq_api_key") or ""):
        time.sleep(1)
        raise PermissionError("That Groq key doesn't match the one the parent set up.")
    return change_password(new_password)


def change_password(new_password: str) -> str:
    if len(new_password) < 4:
        raise ValueError("Password must be at least 4 characters.")
    with _lock:
        d = _load()
        salt = secrets.token_hex(16)
        d.update({"pw_salt": salt, "pw_hash": _hash(new_password, salt)})
        _save(d)
        _tokens.clear()
    return _new_token()


def _new_token() -> str:
    t = secrets.token_urlsafe(24)
    now = time.time()
    for k in [k for k, exp in _tokens.items() if exp < now]:
        _tokens.pop(k)
    _tokens[t] = now + TOKEN_TTL
    return t


def require(token: str | None):
    if not token or _tokens.get(token, 0) < time.time():
        raise PermissionError("Parent login required.")


# ---------------- rules ----------------
def rules() -> dict:
    return {**DEFAULT_RULES, **(_load().get("rules") or {})}


def set_rules(changes: dict) -> dict:
    with _lock:
        d = _load()
        r = {**DEFAULT_RULES, **(d.get("rules") or {})}
        for k, v in changes.items():
            if k in DEFAULT_RULES and v is not None:
                r[k] = v
        r["limit_minutes"] = max(1, min(int(r["limit_minutes"]), 600))
        r["lock_minutes"] = max(1, min(int(r["lock_minutes"]), 1440))
        r["unlock_pass"] = max(1, min(int(r["unlock_pass"]), 3))
        r["blocked_sites"] = sorted({s.strip().lower().removeprefix("https://").removeprefix("http://")
                                     .removeprefix("www.").split("/")[0] for s in r["blocked_sites"] if s.strip()})
        d["rules"] = r
        _save(d)
    settings.update({"unlock_pass": r["unlock_pass"]})
    return r


# ---------------- profile, marks, usage ----------------
def profile() -> dict:
    return _uload().get("profile") or {"name": "", "cls": 10, "school": "", "board": "CBSE", "goal": ""}


def set_profile(p: dict) -> dict:
    with _lock:
        d = _uload()
        d["profile"] = {**profile(), **{k: v for k, v in p.items() if v is not None}}
        _usave(d)
        return d["profile"]


def records() -> list[dict]:
    return _uload().get("records") or []


def add_record(rec: dict) -> dict:
    with _lock:
        d = _uload()
        rec = {**rec, "id": secrets.token_hex(6), "added": time.time()}
        d["records"] = (d.get("records") or []) + [rec]
        _usave(d)
        return rec


def delete_record(rid: str):
    with _lock:
        d = _uload()
        d["records"] = [r for r in d.get("records") or [] if r.get("id") != rid]
        _usave(d)


def save_usage(day: dict, quizzes: list | None):
    with _lock:
        d = _uload()
        usage = d.get("usage") or {}
        usage[day["date"]] = day
        d["usage"] = dict(sorted(usage.items())[-60:])
        if quizzes is not None:
            d["quizzes"] = quizzes[:50]
        _usave(d)


def overview() -> dict:
    d = _load()
    return {"rules": rules(), "profile": profile(), "records": records(),
            "usage": d.get("usage") or {}, "quizzes": d.get("quizzes") or []}


def student_summary() -> str:
    """Compact text for the AI agent."""
    p, recs, d = profile(), records(), _uload()
    lines = [f"Student: {p.get('name') or 'unknown'}, Class {p.get('cls')}, {p.get('school') or ''} goal: {p.get('goal') or '-'}"]
    for r in recs[-15:]:
        lines.append(f"- {r.get('exam')} {r.get('subject')}: {r.get('marks')}/{r.get('max_marks')} ({r.get('date', '')})")
    today = (d.get("usage") or {}).get(time.strftime("%Y-%m-%d"))
    if today:
        lines.append(f"Today: studied {today.get('study', 0) // 60} min, distracted {today.get('distracted', 0) // 60} min")
    for q in (d.get("quizzes") or [])[:5]:
        lines.append(f"Quiz: {q.get('title')} {q.get('score')}/{q.get('total')}")
    return "\n".join(lines)
