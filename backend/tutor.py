"""Snap & Solve: read a homework photo, then coach the student one step at a time — never revealing answers.

The full step plan (with each step's expected result) stays on the server. The student only ever sees the
goal of the current step and hints; a step unlocks only after the student's own work is judged correct."""
import re
import secrets
import threading
import time

import requests

import growth
import langs
from config import settings
from llm import GROQ_URL, EngineError, ai_json

VISION_MODEL = "qwen/qwen3.8-27b"
SESSIONS: dict[str, dict] = {}
_lock = threading.Lock()

TUTOR_SYSTEM = """You are Krypton Tutor, a patient Indian school teacher (CBSE/NCERT). You NEVER give the student the
answer or the result of any step. You guide them to do the work themselves. Reply with ONE JSON object only."""


def read_image(data_url: str, kind: str = "question") -> str:
    key = settings.get("groq_api_key")
    if not key:
        raise EngineError("Reading photos needs the Groq key (parent board).")
    if not data_url.startswith("data:image/") or len(data_url) > 8_000_000:
        raise ValueError("Please use a JPG/PNG photo under 6 MB.")
    ask = ("Transcribe the homework question in this image exactly, including all numbers, units and symbols. "
           "Describe any diagram briefly in [brackets]. Output only the question text, nothing else."
           if kind == "question" else
           "Transcribe the student's handwritten working in this image exactly as written, line by line. "
           "Output only the transcription.")
    try:
        r = requests.post(f"{GROQ_URL}/chat/completions", headers={"Authorization": f"Bearer {key}"}, timeout=90, json={
            "model": VISION_MODEL, "max_tokens": 1500, "temperature": 0,
            "messages": [{"role": "user", "content": [{"type": "text", "text": ask},
                                                      {"type": "image_url", "image_url": {"url": data_url}}]}]})
    except requests.RequestException as e:
        raise EngineError(f"Groq unreachable ({type(e).__name__})")
    if not r.ok:
        raise EngineError(f"Couldn't read the photo ({r.status_code}): {r.text[:150]}")
    text = r.json()["choices"][0]["message"]["content"] or ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def _clean(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _leaks(text: str, secret: str) -> bool:
    """True if the coach's text gives away the expected result."""
    norm = lambda s: re.sub(r"[^a-z0-9.=/\-+]", "", s.lower())
    s = norm(secret)
    return len(s) >= 2 and s in norm(text)


def start(question: str, cls, subject) -> dict:
    question = _clean(question)
    if len(question) < 5:
        raise ValueError("Type or photograph the question first.")
    prompt = f"""A Class {cls or '?'} student{f' ({subject})' if subject else ''} needs help with this question:
\"\"\"{question}\"\"\"

Plan how YOU would guide them to solve it themselves, in 2-6 small steps (simple questions: 2-3 steps).
For every step give:
- "goal": what the student must do in this step, phrased as an instruction — must NOT contain the result
- "hint1": a gentle nudge (no result)
- "hint2": a stronger hint, e.g. the formula/idea to use (still no result)
- "expected": the correct result of this step (kept secret from the student; used only to check their work)
Also give "topic" (the NCERT concept involved) and "final_answer" (secret).
JSON: {{"topic": str, "steps": [{{"goal": str, "hint1": str, "hint2": str, "expected": str}}], "final_answer": str}}
{langs.instruction(langs.current_lang.get()) or ''}"""
    data, engine, model, _ = ai_json(TUTOR_SYSTEM, prompt, max_tokens=2500, temperature=0.2)
    steps = [s for s in data.get("steps", []) if isinstance(s, dict) and s.get("goal") and s.get("expected")][:6]
    if not steps:
        raise ValueError("Couldn't plan this one — try typing the question more clearly.")
    for s in steps:  # never let a goal or hint carry its own answer
        for k in ("goal", "hint1", "hint2"):
            if _leaks(s.get(k, ""), s["expected"]):
                s[k] = "Think about what this step asks for and try it in your notebook."
    sid = secrets.token_urlsafe(10)
    with _lock:
        now = time.time()
        for k in [k for k, v in SESSIONS.items() if now - v["t"] > 6 * 3600]:
            SESSIONS.pop(k)
        SESSIONS[sid] = {"t": now, "question": question, "topic": data.get("topic", ""), "steps": steps,
                         "final": str(data.get("final_answer", "")), "idx": 0, "tries": 0, "hints": 0,
                         "cls": cls, "subject": subject, "done": []}
    return {"session_id": sid, "question": question, "topic": data.get("topic", ""), "total": len(steps),
            "step": _public_step(SESSIONS[sid]), "engine": engine, "model": model}


def _public_step(s: dict) -> dict:
    st = s["steps"][s["idx"]]
    return {"n": s["idx"] + 1, "goal": st["goal"]}


def hint(sid: str) -> dict:
    s = _get(sid)
    st = s["steps"][s["idx"]]
    s["hints"] += 1
    h = st.get("hint1") if s["hints"] == 1 else st.get("hint2") or st.get("hint1")
    return {"hint": h, "level": min(s["hints"], 2)}


def check(sid: str, work: str) -> dict:
    s = _get(sid)
    work = _clean(work)
    if len(work) < 1:
        raise ValueError("Write what you did for this step first.")
    st = s["steps"][s["idx"]]
    prompt = f"""Question: \"\"\"{s['question']}\"\"\"
Current step goal: {st['goal']}
Correct result of this step (SECRET — never reveal it): {st['expected']}
Steps the student already completed: {' | '.join(s['done']) or 'none'}
Student's work for this step: \"\"\"{work}\"\"\"

Is the student's work for THIS step correct? Accept equivalent forms (e.g. 3x = 15 vs x = 5 only if the step goal is
satisfied; 0.5 vs 1/2; units in words). If it's partly right, it is not correct yet.
"feedback": 1-2 encouraging sentences. If wrong, point to WHERE the mistake is (e.g. "check the sign when you move 7")
without giving the correct result. If right, praise briefly.
JSON: {{"correct": bool, "feedback": str}}
{langs.instruction(langs.current_lang.get()) or ''}"""
    data, _, _, _ = ai_json(TUTOR_SYSTEM, prompt, max_tokens=600, temperature=0)
    ok = bool(data.get("correct"))
    fb = _clean(data.get("feedback")) or ("Nice work!" if ok else "Not quite — have another look.")
    if not ok and _leaks(fb, st["expected"]):
        fb = "Not quite yet — re-check your working for this step carefully."
    res = {"correct": ok, "feedback": fb}
    if ok:
        s["done"].append(work)
        s["idx"] += 1
        s["tries"] = s["hints"] = 0
        xp = growth.add_xp("tutor_step")
        if s["idx"] >= len(s["steps"]):
            xp = growth.add_xp("tutor_solved")
            res.update(solved=True, topic=s["topic"], steps_done=s["done"])
        else:
            res["step"] = _public_step(s)
        res["xp"] = xp
    else:
        s["tries"] += 1
        if s["tries"] >= 2 and s["hints"] < 2:  # struggling: offer the next hint automatically
            res["hint"] = hint(sid)["hint"]
    return res


def _get(sid: str) -> dict:
    s = SESSIONS.get(sid)
    if not s:
        raise KeyError("This session expired — start the question again.")
    if s["idx"] >= len(s["steps"]):
        raise ValueError("This problem is already solved! 🎉")
    return s
