"""Viva mode: an oral exam. Krypton asks questions aloud, grades spoken/typed answers against NCERT,
asks one follow-up when an answer is half right, and gives a report at the end.
Model answers stay on the server until the viva is finished."""
import re
import secrets
import threading
import time

import growth
from features import _focus, _lang, _who
from library import library
from llm import ai_json

SESSIONS: dict[str, dict] = {}
_lock = threading.Lock()

EXAMINER = """You are Krypton, a strict but fair CBSE viva examiner for Indian school students. You ask clear oral
questions from the NCERT textbook and mark answers fairly: reward correct ideas in the student's own words, ignore
grammar and filler words (spoken answers are transcribed). Reply with ONE JSON object only."""


def start(cls, subject, chapters, query, count: int) -> dict:
    count = max(3, min(int(count or 5), 10))
    chapters = _focus(cls, subject, chapters, query)
    chunks = library.gather(query, cls, subject, chapters, k=10)
    ctx, sources = library.to_context(chunks, 7000)
    if not ctx:
        raise ValueError("Pick a class and subject (or chapter) first.")
    lang = _lang(subject, query, chunks)
    data, engine, model, _ = ai_json(EXAMINER, f"""Prepare a {count}-question viva for {_who(cls)}{f' in {subject}' if subject else ''}
on "{query or 'these chapters'}", using ONLY these NCERT excerpts:
{ctx}

Questions go from easy to harder: definitions → explain why/how → apply to an example. Each must be answerable aloud
in 1-3 sentences. For each give the model answer and the 2-4 key points an examiner listens for.
JSON: {{"topic": str, "questions": [{{"q": str, "ideal": str, "points": [str]}}]}}
{lang}""", max_tokens=3000, temperature=0.4)
    qs = [q for q in data.get("questions", []) if isinstance(q, dict) and q.get("q") and q.get("ideal")][:count]
    if len(qs) < 2:
        raise ValueError("Couldn't prepare questions for this topic — try another chapter.")
    sid = secrets.token_urlsafe(10)
    with _lock:
        now = time.time()
        for k in [k for k, v in SESSIONS.items() if now - v["t"] > 4 * 3600]:
            SESSIONS.pop(k)
        SESSIONS[sid] = {"t": now, "cls": cls, "subject": subject, "topic": data.get("topic") or query, "lang": lang,
                         "ctx": ctx, "qs": qs, "i": 0, "followup": None, "results": [], "sources": sources}
    return {"session_id": sid, "topic": SESSIONS[sid]["topic"], "total": len(qs), "n": 1, "question": qs[0]["q"],
            "engine": engine, "model": model, "sources": sources}


def answer(sid: str, text: str) -> dict:
    s = SESSIONS.get(sid)
    if not s:
        raise KeyError("This viva expired — start a new one.")
    if s["i"] >= len(s["qs"]):
        raise ValueError("This viva is already finished.")
    q = s["qs"][s["i"]]
    text = re.sub(r"\s+", " ", text or "").strip()
    follow = s["followup"]
    asked = follow or q["q"]
    if not text:  # skipped / no answer
        grade = {"score": 0, "feedback": "No answer given — that's okay, let's keep going.", "missed": q.get("points", [])}
    else:
        grade, _, _, _ = ai_json(EXAMINER, f"""Viva question: {asked}
{f'(This was a follow-up to: {q["q"]})' if follow else ''}
Model answer (examiner only): {q['ideal']}
Key points: {'; '.join(q.get('points', []))}
Student's spoken answer (transcribed): \"\"\"{text}\"\"\"

Mark it out of 5 (5 = all key points, clearly; 3 = main idea but incomplete; 1 = barely related; 0 = wrong/blank).
"feedback": 1-2 sentences spoken to the student — say what was good and what was missing. Do NOT read out the full
model answer. "missed": the key points they left out (short phrases).
{'"follow_up": ONE short follow-up question that nudges them toward what they missed, ONLY if the score is 1-3; else ""' if not follow else ''}
JSON: {{"score": int, "feedback": str, "missed": [str]{', "follow_up": str' if not follow else ''}}}
{s['lang']}""", max_tokens=700, temperature=0)
    score = max(0, min(5, int(grade.get("score", 0) or 0)))
    res = {"score": score, "feedback": str(grade.get("feedback", "")), "missed": [str(m) for m in grade.get("missed", [])][:4]}
    fu = str(grade.get("follow_up") or "").strip()
    if not follow and 1 <= score <= 3 and fu:
        s["followup"] = fu
        s["first_score"] = score
        s["first_answer"] = text
        return {**res, "follow_up": fu, "n": s["i"] + 1, "total": len(s["qs"])}
    # after a follow-up, keep the better of the two attempts, capped at 4 (a hint was given)
    final = min(4, max(s.get("first_score", 0), score)) if follow else score
    s["results"].append({"q": q["q"], "answer": s.get("first_answer", text) if follow else text, "score": final,
                         "feedback": res["feedback"], "missed": res["missed"], "ideal": q["ideal"]})
    s["followup"] = None
    s.pop("first_score", None)
    s.pop("first_answer", None)
    s["i"] += 1
    xp = growth.add_xp("viva_point", final) if final else {"gained": 0, "new_badges": []}
    out = {**res, "final_score": final, "xp": xp, "n": s["i"], "total": len(s["qs"])}
    if s["i"] < len(s["qs"]):
        out["next_question"] = s["qs"][s["i"]]["q"]
    else:
        out["report"] = _report(s)
    return out


def _report(s: dict) -> dict:
    total = sum(r["score"] for r in s["results"])
    out_of = 5 * len(s["results"])
    pct = round(100 * total / out_of) if out_of else 0
    xp = growth.add_xp("viva_done")
    return {"topic": s["topic"], "score": total, "out_of": out_of, "percent": pct, "results": s["results"],
            "verdict": "Outstanding — viva ready!" if pct >= 85 else "Good — polish the missed points." if pct >= 60
            else "Keep practising — revise this chapter and try again.", "xp": xp, "sources": s["sources"]}
