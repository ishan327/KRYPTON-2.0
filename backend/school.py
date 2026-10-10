"""School administration: a staff login that posts events (with reminders) and behaviour reports to parents."""
import datetime as dt
import hashlib
import hmac
import json
import secrets
import threading
import time

import users
from config import DATA

SCHOOL_FILE = DATA / "school.json"
TOKEN_TTL = 12 * 3600
CATEGORIES = {"praise": "🌟 Praise", "concern": "⚠️ Concern", "incident": "🚩 Incident"}
AREAS = ["Homework", "Punctuality", "Attendance", "Conduct", "Participation", "Uniform", "Teamwork", "Academics", "Other"]

_lock = threading.Lock()
_tokens: dict[str, float] = {}


def _load() -> dict:
    if SCHOOL_FILE.exists():
        try:
            return json.loads(SCHOOL_FILE.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            pass
    return {}


def _save(d: dict):
    DATA.mkdir(parents=True, exist_ok=True)
    SCHOOL_FILE.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")


def _hash(pw: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()


def status() -> dict:
    a = _load().get("admin") or {}
    return {"setup": bool(a.get("pw_hash")), "school_name": a.get("school_name", ""), "areas": AREAS, "categories": CATEGORIES}


def setup(school_name: str, admin_name: str, password: str) -> str:
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")
    if not school_name.strip():
        raise ValueError("Enter the school's name.")
    with _lock:
        d = _load()
        if (d.get("admin") or {}).get("pw_hash"):
            raise PermissionError("The school admin account already exists — log in instead.")
        salt = secrets.token_hex(16)
        d["admin"] = {"school_name": school_name.strip()[:80], "name": admin_name.strip()[:60] or "School admin",
                      "pw_salt": salt, "pw_hash": _hash(password, salt)}
        d.setdefault("events", [])
        d.setdefault("reports", [])
        _save(d)
    return _token()


def login(password: str) -> str:
    a = _load().get("admin") or {}
    if not a.get("pw_hash"):
        raise PermissionError("No school admin account yet.")
    if not hmac.compare_digest(_hash(password, a["pw_salt"]), a["pw_hash"]):
        time.sleep(1)
        raise PermissionError("Wrong password.")
    return _token()


def _token() -> str:
    t = secrets.token_urlsafe(24)
    _tokens[t] = time.time() + TOKEN_TTL
    return t


def require(token: str | None):
    if not token or _tokens.get(token, 0) < time.time():
        raise PermissionError("School admin login required.")


# ---------------- students ----------------
def _profile_of(uid: str | None) -> dict:
    f = (users.user_dir(uid) / "family.json") if uid else (DATA / "family.json")
    try:
        return json.loads(f.read_text(encoding="utf-8-sig")).get("profile") or {}
    except (OSError, ValueError):
        return {}


def students() -> list[dict]:
    owner = _profile_of(None)
    out = [{"id": "owner", "name": owner.get("name") or "Main student (this laptop)", "cls": owner.get("cls")}]
    for u in users.all_users():
        p = _profile_of(u["id"])
        out.append({"id": u["id"], "name": p.get("name") or u["name"], "cls": p.get("cls"), "username": u["username"]})
    return out


# ---------------- events + reports ----------------
def add_event(ev: dict) -> dict:
    try:
        dt.date.fromisoformat(ev.get("date", ""))
    except ValueError:
        raise ValueError("Pick a date for the event.")
    if not ev.get("title", "").strip():
        raise ValueError("Give the event a title.")
    with _lock:
        d = _load()
        e = {"id": secrets.token_hex(6), "title": ev["title"].strip()[:120], "date": ev["date"], "time": ev.get("time", "")[:10],
             "description": ev.get("description", "").strip()[:1000], "audience": str(ev.get("audience") or "all"),
             "remind_days": max(0, min(int(ev.get("remind_days") or 2), 30)), "created": time.time()}
        d.setdefault("events", []).append(e)
        _save(d)
        return e


def add_report(rep: dict) -> dict:
    sid = rep.get("student_id")
    st = next((s for s in students() if s["id"] == sid), None)
    if not st:
        raise ValueError("Choose a student.")
    if rep.get("category") not in CATEGORIES:
        raise ValueError("Choose praise, concern or incident.")
    if not rep.get("note", "").strip():
        raise ValueError("Write what happened.")
    with _lock:
        d = _load()
        r = {"id": secrets.token_hex(6), "student_id": sid, "student_name": st["name"], "category": rep["category"],
             "area": rep.get("area") if rep.get("area") in AREAS else "Other", "note": rep["note"].strip()[:1500],
             "date": rep.get("date") or dt.date.today().isoformat(), "by": (d.get("admin") or {}).get("name", "School"),
             "created": time.time()}
        d.setdefault("reports", []).append(r)
        _save(d)
        return r


def delete(kind: str, item_id: str):
    with _lock:
        d = _load()
        d[kind] = [x for x in d.get(kind, []) if x.get("id") != item_id]
        _save(d)


def admin_overview() -> dict:
    d = _load()
    return {**status(), "events": sorted(d.get("events", []), key=lambda e: e["date"]),
            "reports": sorted(d.get("reports", []), key=lambda r: r["created"], reverse=True)[:200], "students": students()}


def feed(uid: str | None) -> dict:
    """What a student (and their parents) see: upcoming events for their class + behaviour reports about them."""
    d = _load()
    today = dt.date.today()
    cls = _profile_of(uid).get("cls")
    events = []
    for e in d.get("events", []):
        day = dt.date.fromisoformat(e["date"])
        if day < today or (e["audience"] != "all" and str(cls) != e["audience"]):
            continue
        left = (day - today).days
        events.append({**e, "days_left": left, "remind": left <= e.get("remind_days", 2)})
    events.sort(key=lambda e: e["date"])
    sid = uid or "owner"
    reports = sorted([r for r in d.get("reports", []) if r["student_id"] == sid], key=lambda r: r["created"], reverse=True)
    return {"school_name": status()["school_name"], "events": events, "reports": reports[:50], "categories": CATEGORIES}
