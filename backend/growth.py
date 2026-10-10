"""Weak-spot tracking with spaced repetition (Leitner boxes), plus XP, levels, streaks, badges and friends."""
import base64
import datetime as dt
import hashlib
import json
import random
import threading

import users
from config import DATA
from library import library

PROGRESS_FILE = DATA / "progress.json"
INTERVALS = [0, 1, 3, 7, 14, 30]   # days until next review, by Leitner box (1..5)
DAILY_GOAL = 100                   # XP needed for a day to count towards the streak
XP = {"quiz_correct": 10, "quiz_done": 20, "quiz_perfect": 30, "review_correct": 15, "review_wrong": 3,
      "tutor_step": 20, "tutor_solved": 50, "focus_unlock": 15, "explain": 5, "flashcards": 10, "paper": 15,
      "guide": 5, "mindmap": 10, "study_minute": 1, "viva_point": 4, "viva_done": 30, "lang_practice": 3, "lang_letter": 1}
CLIENT_EVENTS = {"quiz_done", "quiz_perfect", "explain", "flashcards", "paper", "guide", "mindmap", "lang_letter"}
TITLES = ["Rookie", "Explorer", "Learner", "Scholar", "Achiever", "Topper", "Genius", "Mastermind", "Legend", "Krypton Master"]
BADGES = [
    ("first_quiz", "🎯", "First quiz", "Finish your first quiz", lambda s: s["c"].get("quiz_done", 0) >= 1),
    ("perfect", "💯", "Perfect score", "Get every question right in a quiz", lambda s: s["c"].get("quiz_perfect", 0) >= 1),
    ("streak3", "🔥", "On fire", "3-day streak", lambda s: s["best_streak"] >= 3),
    ("streak7", "⚡", "Unstoppable", "7-day streak", lambda s: s["best_streak"] >= 7),
    ("streak30", "👑", "Royalty", "30-day streak", lambda s: s["best_streak"] >= 30),
    ("comeback", "🧠", "Comeback kid", "Fix 20 old mistakes in Revise", lambda s: s["c"].get("review_correct", 0) >= 20),
    ("solver", "📸", "Problem solver", "Solve a problem in Snap & Solve", lambda s: s["c"].get("tutor_solved", 0) >= 1),
    ("solver10", "🏅", "Homework hero", "Solve 10 problems step by step", lambda s: s["c"].get("tutor_solved", 0) >= 10),
    ("focus", "🔒", "Focus master", "Unlock the focus lock with a quiz 5 times", lambda s: s["c"].get("focus_unlock", 0) >= 5),
    ("century", "🎓", "Century", "Answer 100 questions correctly", lambda s: s["c"].get("quiz_correct", 0) >= 100),
    ("level5", "⭐", "Achiever", "Reach level 5", lambda s: s["level"] >= 5),
    ("viva", "🎙️", "Viva master", "Finish 3 vivas", lambda s: s["c"].get("viva_done", 0) >= 3),
    ("polyglot", "🗣️", "Polyglot", "Earn 50 language-practice points in the Language Lab",
     lambda s: s["c"].get("lang_practice", 0) + s["c"].get("lang_letter", 0) // 5 >= 50),
]

_lock = threading.Lock()


def _today() -> str:
    return dt.date.today().isoformat()


def _file():
    d = users.user_dir()  # each web account has its own progress; the laptop owner uses the main file
    return d / "progress.json" if d else PROGRESS_FILE


def _load() -> dict:
    f = _file()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            pass
    return {}


def _save(d: dict):
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


# ---------------- XP / levels / streaks / badges ----------------
def level_of(xp: int) -> int:
    return int((xp / 50) ** 0.5) + 1


def _streaks(days: dict) -> tuple[int, int]:
    met = {d for d, x in days.items() if x >= DAILY_GOAL}
    today = dt.date.today()
    cur, day = 0, today if today.isoformat() in met else today - dt.timedelta(days=1)
    while day.isoformat() in met:
        cur += 1
        day -= dt.timedelta(days=1)
    best, run, prev = 0, 0, None
    for d in sorted(met):
        dd = dt.date.fromisoformat(d)
        run = run + 1 if prev and (dd - prev).days == 1 else 1
        best, prev = max(best, run), dd
    return cur, max(best, cur)


def _award(d: dict, event: str, times: int = 1) -> dict:
    g = d.setdefault("game", {"xp": 0, "days": {}, "counters": {}, "badges": {}, "friends": []})
    gained = XP.get(event, 0) * times
    g["xp"] += gained
    g["days"][_today()] = g["days"].get(_today(), 0) + gained
    g["counters"][event] = g["counters"].get(event, 0) + times
    cur, best = _streaks(g["days"])
    stats = {"c": g["counters"], "best_streak": best, "level": level_of(g["xp"])}
    new = []
    for bid, icon, name, desc, check in BADGES:
        if bid not in g["badges"] and check(stats):
            g["badges"][bid] = _today()
            new.append({"id": bid, "icon": icon, "name": name})
    return {"gained": gained, "xp": g["xp"], "level": level_of(g["xp"]), "streak": cur, "new_badges": new}


def add_xp(event: str, times: int = 1) -> dict:
    with _lock:
        d = _load()
        res = _award(d, event, times)
        _save(d)
        return res


def sync_study(day: dict):
    """Turn new study minutes (from the extension's usage sync) into XP."""
    minutes = int(day.get("study", 0)) // 60
    with _lock:
        d = _load()
        seen = d.setdefault("study_seen", {})
        delta = minutes - seen.get(day["date"], 0)
        if delta > 0 and day["date"] == _today():
            seen[day["date"]] = minutes
            _award(d, "study_minute", delta)
            _save(d)


def game() -> dict:
    d = _load()
    g = d.get("game") or {"xp": 0, "days": {}, "counters": {}, "badges": {}, "friends": []}
    lvl = level_of(g["xp"])
    lo, hi = 50 * (lvl - 1) ** 2, 50 * lvl ** 2
    cur, best = _streaks(g["days"])
    cal = [{"date": (dt.date.today() - dt.timedelta(days=i)).isoformat()} for i in range(27, -1, -1)]
    for c in cal:
        c["xp"] = g["days"].get(c["date"], 0)
    return {"xp": g["xp"], "level": lvl, "title": TITLES[min(lvl, len(TITLES)) - 1], "level_from": lo, "level_to": hi,
            "streak": cur, "best_streak": best, "today": g["days"].get(_today(), 0), "goal": DAILY_GOAL, "calendar": cal,
            "counters": g["counters"],
            "badges": [{"id": b, "icon": i, "name": n, "desc": ds, "earned": g["badges"].get(b)} for b, i, n, ds, _ in BADGES],
            "friends": g.get("friends", [])}


def share_code(name: str) -> str:
    st = game()
    payload = {"n": name or "Student", "x": st["xp"], "s": st["streak"], "l": st["level"], "d": _today()}
    return "KRY-" + base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")


def add_friend(code: str) -> list:
    raw = code.strip().removeprefix("KRY-")
    try:
        p = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        friend = {"name": str(p["n"])[:30], "xp": int(p["x"]), "streak": int(p["s"]), "level": int(p["l"]), "updated": str(p["d"])}
    except (ValueError, KeyError, TypeError):
        raise ValueError("That isn't a valid Krypton friend code.")
    with _lock:
        d = _load()
        g = d.setdefault("game", {"xp": 0, "days": {}, "counters": {}, "badges": {}, "friends": []})
        g["friends"] = [f for f in g.get("friends", []) if f["name"] != friend["name"]] + [friend]
        _save(d)
        return g["friends"]


# ---------------- weak spots + spaced repetition ----------------
def _qid(q: str) -> str:
    return hashlib.sha1(q.strip().lower().encode()).hexdigest()[:12]


def _tag(item: dict) -> dict:
    """Find the NCERT chapter a question belongs to (Language Lab words carry their own tag)."""
    lt = item.get("tag")
    if isinstance(lt, dict) and lt.get("code"):
        return {"key": f"lang:{lt['code']}", "title": f"{lt.get('name', lt['code'])} vocabulary", "cls": item.get("cls"),
                "subject": f"Language Lab · {lt.get('name', '')}"}
    opts = item.get("options") or []
    ans = opts[item["answer_index"]] if 0 <= item.get("answer_index", -1) < len(opts) else ""
    hits = library.search(f"{item['question']} {ans}", item.get("cls"), item.get("subject"), None, 1)
    if not hits:
        hits = library.search(f"{item['question']} {ans}", item.get("cls"), None, None, 1)
    if not hits:
        return {"key": "unknown", "title": "Mixed topics", "cls": item.get("cls"), "subject": item.get("subject") or ""}
    c = hits[0][1]
    return {"key": f"{c['code']}:{c['ch']}", "title": f"Ch {c['ch']}: {c['ch_title']}", "cls": c["cls"],
            "subject": c["subject"], "book": c["book"]}


def record_attempts(items: list[dict]) -> dict:
    """items: {question, options, answer_index, explanation, chosen, cls, subject}"""
    right = 0
    with _lock:
        d = _load()
        chapters = d.setdefault("chapters", {})
        reviews = d.setdefault("reviews", {})
        for it in items:
            if not it.get("question") or len(it.get("options") or []) < 2:
                continue
            ok = it.get("chosen") == it.get("answer_index")
            right += ok
            tag = _tag(it)
            ch = chapters.setdefault(tag["key"], {**tag, "right": 0, "wrong": 0})
            ch["right" if ok else "wrong"] += 1
            qid = _qid(it["question"])
            if not ok:
                reviews[qid] = {"id": qid, "question": it["question"], "options": it["options"],
                                "answer_index": it["answer_index"], "explanation": it.get("explanation", ""),
                                "chapter": tag, "box": 1, "due": _today(), "misses": reviews.get(qid, {}).get("misses", 0) + 1}
            elif qid in reviews:
                _promote(reviews[qid])
        res = _award(d, "quiz_correct", right) if right else {"gained": 0, "new_badges": []}
        _save(d)
    return res


def _promote(r: dict):
    r["box"] = min(r["box"] + 1, 6)
    r["due"] = (dt.date.today() + dt.timedelta(days=INTERVALS[min(r["box"], 5)])).isoformat()
    r["mastered"] = r["box"] >= 6


def due(limit: int = 10) -> list[dict]:
    reviews = _load().get("reviews", {})
    items = [r for r in reviews.values() if not r.get("mastered") and r["due"] <= _today()]
    items.sort(key=lambda r: (r["box"], -r.get("misses", 1)))
    return items[:limit]


def answer_review(qid: str, choice: int) -> dict:
    with _lock:
        d = _load()
        r = d.get("reviews", {}).get(qid)
        if not r:
            raise KeyError("Review card not found")
        ok = choice == r["answer_index"]
        if ok:
            _promote(r)
        else:
            r.update(box=1, due=(dt.date.today() + dt.timedelta(days=1)).isoformat(), misses=r.get("misses", 0) + 1)
        ch = d.setdefault("chapters", {}).setdefault(r["chapter"]["key"], {**r["chapter"], "right": 0, "wrong": 0})
        ch["right" if ok else "wrong"] += 1
        res = _award(d, "review_correct" if ok else "review_wrong")
        _save(d)
    return {**res, "correct": ok, "answer": r["options"][r["answer_index"]], "explanation": r.get("explanation", ""),
            "box": r["box"], "next_due": r["due"], "mastered": r.get("mastered", False)}


def weak_chapters(top: int = 8) -> list[dict]:
    out = []
    for c in _load().get("chapters", {}).values():
        total = c["right"] + c["wrong"]
        if total and c["wrong"]:
            out.append({**c, "total": total, "accuracy": round(100 * c["right"] / total)})
    out.sort(key=lambda c: (c["accuracy"], -c["wrong"]))
    return out[:top]


def review_overview() -> dict:
    d = _load()
    reviews = list(d.get("reviews", {}).values())
    boxes = [sum(1 for r in reviews if r["box"] == b and not r.get("mastered")) for b in range(1, 6)]
    return {"due": [{k: r[k] for k in ("id", "question", "options", "box", "chapter")} for r in due(15)],
            "due_count": len(due(999)), "boxes": boxes, "mastered": sum(1 for r in reviews if r.get("mastered")),
            "weak": weak_chapters()}


def challenge_items(n: int = 3) -> list[dict]:
    """Due weak-spot questions for the focus-lock task (answers stay on the server)."""
    items = due(20)
    random.shuffle(items)
    return [{"question": r["question"], "options": r["options"], "answer_index": r["answer_index"],
             "explanation": r.get("explanation", ""), "review_id": r["id"]} for r in items[:n]]


def summary() -> str:
    g, weak = game(), weak_chapters(5)
    lines = [f"Level {g['level']} {g['title']}, {g['xp']} XP, streak {g['streak']} days, today {g['today']}/{g['goal']} XP"]
    lines += [f"Weak: Class {w['cls']} {w['subject']} {w['title']} — {w['accuracy']}% right ({w['wrong']} wrong)" for w in weak]
    lines.append(f"Revision cards due today: {len(due(999))}")
    return "\n".join(lines)
