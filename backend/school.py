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


MAX_ADMINS = 5  # one class teacher per class (hackathon: anyone can create one from any device)


def status() -> dict:
    d = _load()
    admins = d.get("admins", [])
    return {"setup": bool(admins), "school_name": d.get("school_name", ""), "admins": len(admins), "max_admins": MAX_ADMINS,
            "taken_classes": sorted({a["cls"] for a in admins}), "areas": AREAS, "categories": CATEGORIES}


def setup(school_name: str, username: str, name: str, cls: str, password: str) -> str:
    username, cls = username.strip().lower(), str(cls).strip()
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")
    if not username or not cls.isdigit() or not 1 <= int(cls) <= 10:
        raise ValueError("Choose a username and your class (1-10).")
    with _lock:
        d = _load()
        admins = d.setdefault("admins", [])
        if not d.get("school_name"):
            if not school_name.strip():
                raise ValueError("Enter the school's name.")
            d["school_name"] = school_name.strip()[:80]
        if len(admins) >= MAX_ADMINS:
            raise PermissionError(f"All {MAX_ADMINS} class-admin accounts are taken.")
        if any(a["username"] == username for a in admins):
            raise ValueError("That username is taken.")
        if any(a["cls"] == cls for a in admins):
            raise ValueError(f"Class {cls} already has an admin.")
        salt = secrets.token_hex(16)
        admin = {"id": secrets.token_hex(5), "username": username, "name": name.strip()[:60] or username, "cls": cls,
                 "pw_salt": salt, "pw_hash": _hash(password, salt)}
        admins.append(admin)
        d.setdefault("events", [])
        d.setdefault("reports", [])
        _save(d)
    return _token(admin["id"])


def login(username: str, password: str) -> str:
    a = next((x for x in _load().get("admins", []) if x["username"] == username.strip().lower()), None)
    if not a or not hmac.compare_digest(_hash(password, a["pw_salt"]), a["pw_hash"]):
        time.sleep(1)
        raise PermissionError("Wrong username or password.")
    return _token(a["id"])


def _token(admin_id: str) -> str:
    t = secrets.token_urlsafe(24)
    _tokens[t] = (admin_id, time.time() + TOKEN_TTL)
    return t


def require(token: str | None) -> dict:
    aid, exp = _tokens.get(token or "", (None, 0))
    a = next((x for x in _load().get("admins", []) if x["id"] == aid), None)
    if not a or exp < time.time():
        raise PermissionError("School admin login required.")
    return {k: a[k] for k in ("id", "username", "name", "cls")}


# ---------------- students ----------------
def _profile_of(uid: str | None) -> dict:
    f = (users.user_dir(uid) / "family.json") if uid else (DATA / "family.json")
    try:
        return json.loads(f.read_text(encoding="utf-8-sig")).get("profile") or {}
    except (OSError, ValueError):
        return {}


def students(cls: str | None = None) -> list[dict]:
    owner = _profile_of(None)
    out = [{"id": "owner", "name": owner.get("name") or "Main student (this laptop)", "cls": owner.get("cls")}]
    for u in users.all_users():
        p = _profile_of(u["id"])
        out.append({"id": u["id"], "name": p.get("name") or u["name"], "cls": p.get("cls"), "username": u["username"]})
    return [s for s in out if cls is None or str(s.get("cls")) == str(cls)]


# ---------------- events + reports ----------------
def add_event(ev: dict, admin: dict) -> dict:
    if str(ev.get("audience") or "all") not in ("all", admin["cls"]):
        raise ValueError(f"You can post for Class {admin['cls']} or the whole school.")
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
             "remind_days": max(0, min(int(ev.get("remind_days") or 2), 30)), "created": time.time(),
             "by": f"{admin['name']} · Class {admin['cls']}", "admin_id": admin["id"]}
        d.setdefault("events", []).append(e)
        _save(d)
        return e


def add_report(rep: dict, admin: dict) -> dict:
    sid = rep.get("student_id")
    st = next((s for s in students(admin["cls"]) if s["id"] == sid), None)
    if not st:
        raise ValueError(f"Choose a student from Class {admin['cls']}.")
    if rep.get("category") not in CATEGORIES:
        raise ValueError("Choose praise, concern or incident.")
    if not rep.get("note", "").strip():
        raise ValueError("Write what happened.")
    with _lock:
        d = _load()
        r = {"id": secrets.token_hex(6), "student_id": sid, "student_name": st["name"], "category": rep["category"],
             "area": rep.get("area") if rep.get("area") in AREAS else "Other", "note": rep["note"].strip()[:1500],
             "date": rep.get("date") or dt.date.today().isoformat(), "by": f"{admin['name']} · Class {admin['cls']}",
             "admin_id": admin["id"], "created": time.time()}
        d.setdefault("reports", []).append(r)
        _save(d)
        return r


def delete(kind: str, item_id: str, admin: dict):
    with _lock:
        d = _load()  # admins can only remove what they posted
        d[kind] = [x for x in d.get(kind, []) if not (x.get("id") == item_id and x.get("admin_id") == admin["id"])]
        _save(d)


def admin_overview(admin: dict) -> dict:
    d = _load()
    events = [e for e in d.get("events", []) if e.get("audience") in ("all", admin["cls"])]
    reports = [r for r in d.get("reports", []) if r.get("admin_id") == admin["id"]]
    return {**status(), "me": admin, "events": sorted(events, key=lambda e: e["date"]),
            "reports": sorted(reports, key=lambda r: r["created"], reverse=True)[:200], "students": students(admin["cls"])}


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
