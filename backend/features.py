"""Krypton features. Each one tries the AI chain first and falls back to the offline engine."""
import random
import re
import time

import langs
import offline_engine as off
from config import settings
from library import library
from llm import EngineError, ai_json
from patterns import blueprint

SYSTEM = """You are Krypton, a brilliant and kind teacher for Indian school students (CBSE / NCERT, Classes 1-10).
Ground every fact in the NCERT textbook excerpts you are given (they are labelled [S1], [S2]…). If the excerpts
do not cover something, use standard NCERT-level knowledge and keep it accurate. Match vocabulary and depth to the
student's class. Write in the language you are told to use.
Reply with ONE valid JSON object only — no markdown, no text outside the JSON."""

DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def _lang(subject, query, chunks) -> str:
    chosen = langs.instruction(langs.current_lang.get())  # the student's picked answer language wins
    if chosen:
        return chosen
    text = " ".join(c["text"][:300] for c in chunks[:4])
    hindi = (subject or "").lower() in ("hindi", "sanskrit") or bool(DEVANAGARI.search(query or "")) \
        or (text and len(DEVANAGARI.findall(text)) > 0.3 * len(text))
    return ("LANGUAGE: Write everything in Hindi (Devanagari script)." if hindi
            else "LANGUAGE: Write everything in English.")


def _ctx_chars() -> int:
    return 9000 if settings.get("mode") == "groq" else 7000


def _run(feature: str, ai_prompt: str | None, offline_fn, max_tokens: int = 3000, validate=None, lang: str = "") -> dict:
    t0 = time.time()
    notes = []
    if ai_prompt is not None and settings.get("mode") != "offline":
        ai_prompt = f"{ai_prompt}\n\n{lang}" if lang else ai_prompt
        try:
            data, engine, model, notes = ai_json(SYSTEM, ai_prompt, max_tokens=max_tokens)
            if validate:
                data = validate(data)
            return {"data": data, "engine": engine, "model": model, "notes": notes, "ms": (time.time() - t0) * 1000}
        except EngineError as e:
            notes = [n for n in str(e).split("; ") if n and n != "offline mode"]
        except (ValueError, KeyError, TypeError, IndexError) as e:
            notes.append(f"AI answer was malformed ({type(e).__name__}); used offline engine")
    data = offline_fn()
    return {"data": data, "engine": "offline", "model": "Krypton offline engine", "notes": notes,
            "ms": (time.time() - t0) * 1000}


def _focus(cls, subject, chapters, query) -> list[str]:
    """A typed topic with no chapters picked -> the 1-3 chapters that best cover it."""
    if chapters or not (query or "").strip():
        return chapters
    hits = library.search(query, cls, subject, None, 12)
    return list(dict.fromkeys(f"{c['code']}:{c['ch']}" for _, c in hits))[:3] or chapters


def _who(cls) -> str:
    return f"a Class {cls} student" if cls else "a school student"


# ---------------- validators (make AI output safe for the UI) ----------------
def _fix_mcqs(qs: list) -> list:
    out = []
    for q in qs or []:
        opts = [str(o).strip() for o in (q.get("options") or [])][:4]
        try:
            ai = int(q.get("answer_index", -1))
        except (TypeError, ValueError):
            ai = -1
        if len(opts) != 4 or not 0 <= ai < 4 or not q.get("question"):
            continue
        correct = opts[ai]
        random.shuffle(opts)  # models love putting the answer at A
        out.append({"question": str(q["question"]), "options": opts, "answer_index": opts.index(correct),
                    "explanation": str(q.get("explanation", ""))})
    return out


def _v_quiz(d):
    d["questions"] = _fix_mcqs(d.get("questions"))
    if not d["questions"]:
        raise ValueError("no valid questions")
    return d


def _v_cards(d):
    d["cards"] = [{"front": str(c["front"]), "back": str(c["back"])} for c in d.get("cards", []) if c.get("front") and c.get("back")]
    if not d["cards"]:
        raise ValueError("no cards")
    return d


def _v_explain(d):
    d["lines"] = [{"text": str(l.get("text", "")), "explanation": str(l.get("explanation", ""))}
                  for l in d.get("lines", []) if l.get("text")]
    if not d["lines"]:
        raise ValueError("no lines")
    d.setdefault("key_terms", [])
    d.setdefault("summary", "")
    return d


# ---------------- features ----------------
def explain(cls, subject, chapters, query):
    chunks = library.gather(query, cls, subject, chapters, k=6)
    ctx, sources = library.to_context(chunks, _ctx_chars())
    prompt = f"""Student: {_who(cls)}{f' studying {subject}' if subject else ''}.
Question / topic: "{query or 'Explain this chapter'}"

NCERT excerpts:
{ctx}

Teach this topic LINE BY LINE, better than any textbook guide:
- Pick the 6-12 most important lines from the excerpts in teaching order (quote them closely) and for each give a
  simple, vivid explanation as a great teacher would in class — what it means, why it is true, and an everyday Indian
  example where it helps. Build from basics to the full idea.
- Then give a short summary, the key terms with simple meanings, one memorable example/analogy, and 3 quick
  check-your-understanding questions.

JSON shape:
{{"title": str, "lines": [{{"text": str, "explanation": str}}], "summary": str,
  "key_terms": [{{"term": str, "meaning": str}}], "example": str, "check_questions": [str]}}"""
    res = _run("explain", prompt, lambda: off.explain(query, chunks), 3500, _v_explain, _lang(subject, query, chunks))
    res["sources"] = sources
    return res


def flashcards(cls, subject, chapters, query, count):
    chunks = library.gather(query, cls, subject, chapters, k=10)
    ctx, sources = library.to_context(chunks, _ctx_chars())
    prompt = f"""Make exactly {count} revision flashcards for {_who(cls)} on "{query or 'these chapters'}".
Use only facts from these NCERT excerpts:
{ctx}

Front: a crisp question, term or fill-in-the-blank. Back: the answer in at most 40 words, in NCERT language.
Cover definitions, key facts, reasons, examples and formulas (if any). No duplicates.
JSON shape: {{"title": str, "cards": [{{"front": str, "back": str}}]}}"""
    res = _run("flashcards", prompt, lambda: off.flashcards(chunks, count), 3000, _v_cards, _lang(subject, query, chunks))
    res["sources"] = sources
    return res


def quiz(cls, subject, chapters, query, count, difficulty="mixed"):
    chunks = library.gather(query, cls, subject, chapters, k=10)
    ctx, sources = library.to_context(chunks, _ctx_chars())
    prompt = f"""Create exactly {count} CBSE-style multiple choice questions for {_who(cls)} on "{query or 'these chapters'}".
Difficulty: {difficulty}. Use these NCERT excerpts as the source:
{ctx}

Rules: 4 options each, exactly one correct, plausible distractors, mix of recall, understanding and application
(include 1-2 assertion-reason or case-style items for Class 9-10). "answer_index" is 0-3. Explanation: 1-2 lines
saying why the answer is right.
JSON shape: {{"title": str, "questions": [{{"question": str, "options": [str, str, str, str], "answer_index": int, "explanation": str}}]}}"""
    res = _run("quiz", prompt, lambda: off.quiz(chunks, count), 3500, _v_quiz, _lang(subject, query, chunks))
    res["sources"] = sources
    return res


def paper(cls, subject, chapters, query, paper_type):
    cls = cls or 10
    chapters = _focus(cls, subject, chapters, query)
    sel = library.selected_chapters(cls, subject, chapters)
    chunks = library.gather(query, cls, subject, chapters, k=14)
    ctx, sources = library.to_context(chunks, 8000 if settings.get("mode") == "groq" else 7000)
    bp = blueprint(cls, paper_type)
    spec = "\n".join(f"- Section {s} — {h}: {n} question(s) × {m} mark(s) [{k}]" for s, h, m, n, k in bp["sections"])
    exercises = "\n".join(f"- {q}" for ch in sel[:8] for q in ch["exercises"][:6])
    prompt = f"""Write a CBSE {'chapter test' if paper_type == 'chapter' else 'sample question paper'} for Class {cls} {subject or ''}.
Time: {bp['time']}. Maximum marks: {bp['max_marks']}. Follow this blueprint EXACTLY (same counts and marks):
{spec}
Question kinds: mcq = 4 options + answer; short = 2-mark direct question; medium = 3-mark; long = 5-mark (may include
"draw a diagram"); case = a 4-6 line passage from the textbook followed by subparts worth 1+1+2 marks.
Give 1-2 internal choices ("or") in long/medium sections, like real CBSE papers. Cover the chapters evenly.
Use real CBSE phrasing. Every question needs a short model answer / marking hint in "answer".

NCERT excerpts:
{ctx}

NCERT exercise questions you may adapt:
{exercises or '- (none)'}

JSON shape:
{{"title": str, "sections": [{{"name": "Section A", "title": str, "marks_each": int,
  "questions": [{{"q": str, "marks": int, "options": [str]?, "passage": str?, "subparts": [{{"q": str, "marks": int, "answer": str}}]?,
  "or": {{"q": str, "answer": str}}?, "answer": str}}]}}]}}"""

    def validate(d):
        ai_secs = [s for s in (d.get("sections") or []) if isinstance(s, dict)]
        if not any(s.get("questions") for s in ai_secs):
            raise ValueError("empty paper")
        backup = None
        secs = []
        # Force the exact CBSE blueprint: trim extras, top up gaps from the offline engine.
        for i, (sec, heading, marks, n, kind) in enumerate(bp["sections"]):
            src = next((s for s in ai_secs if str(s.get("name", "")).strip().upper().endswith(sec)), None)
            if src is None and i < len(ai_secs):
                src = ai_secs[i]
            qs = [q for q in (src or {}).get("questions", []) if isinstance(q, dict) and q.get("q")]
            if kind == "mcq":
                qs = [q for q in qs if len(q.get("options") or []) >= 2]
            qs = qs[:n]
            for q in qs:
                q["marks"] = marks
            if len(qs) < n:
                backup = backup or off.paper(cls, subject, sel, chunks, paper_type)
                qs += backup["sections"][i]["questions"][:n - len(qs)]
            secs.append({"name": f"Section {sec}", "title": heading, "marks_each": marks, "questions": qs})
        return {"title": d.get("title") or f"Sample Question Paper — {subject}", "class": cls, "subject": subject,
                "time": bp["time"], "max_marks": sum(q["marks"] for s in secs for q in s["questions"]),
                "instructions": bp["instructions"], "sections": secs}

    res = _run("paper", prompt, lambda: off.paper(cls, subject, sel, chunks, paper_type), 6500, validate,
               _lang(subject, query, chunks))
    res["sources"] = sources
    return res


def _v_mindmap(d):
    branches = []
    for b in d.get("branches", [])[:7]:
        kids = [{"label": _short(c.get("label") if isinstance(c, dict) else c, 34),
                 "note": str(c.get("note", "")) if isinstance(c, dict) else ""}
                for c in (b.get("children") or [])[:4] if c]
        if b.get("label"):
            branches.append({"label": _short(b["label"], 28), "children": kids})
    if len(branches) < 2:
        raise ValueError("too few branches")
    return {"title": str(d.get("title") or d.get("center") or "Mind map"), "center": _short(d.get("center") or d.get("title"), 30),
            "branches": branches}


def _short(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip().rstrip(".")
    return s if len(s) <= n else s[:n - 1].rsplit(" ", 1)[0] + "…"


def mindmap(cls, subject, chapters, query):
    chapters = _focus(cls, subject, chapters, query)
    chunks = library.gather(query, cls, subject, chapters, k=10)
    ctx, sources = library.to_context(chunks, _ctx_chars())
    prompt = f"""Make a revision MIND MAP for {_who(cls)} on "{query or 'these chapters'}" from these NCERT excerpts:
{ctx}

Centre = the topic (2-4 words). 4-6 main branches = the big ideas of the chapter in teaching order (1-3 words each).
Each branch has 2-4 children: short phrases (max 5 words) — key terms, facts, formulas, examples — and a "note":
one simple sentence explaining that child (shown when the student hovers it). Use NCERT wording.
JSON: {{"title": str, "center": str, "branches": [{{"label": str, "children": [{{"label": str, "note": str}}]}}]}}"""
    res = _run("mindmap", prompt, lambda: off.mindmap(query, chunks), 2500, _v_mindmap, _lang(subject, query, chunks))
    res["sources"] = sources
    return res


def guide(cls, subject, chapters, query, days):
    chapters = _focus(cls, subject, chapters, query)
    sel = library.selected_chapters(cls, subject, chapters)[:14]
    outline = "\n".join(f"- Ch {c['ch']} {c['title']} ({c['pages']} pages, {len(c['exercises'])} exercise Qs) [{c['book']}]"
                        for c in sel)
    chunks = library.gather(query, cls, subject, chapters, k=6)
    ctx, sources = library.to_context(chunks, 5000)
    prompt = f"""Make a practical study plan / guideline for {_who(cls)}{f' in {subject}' if subject else ''}.
Goal: {query or 'master these chapters and score full marks'}. Days available: {days}.
Chapters:
{outline or '- (whole subject)'}
Some textbook content:
{ctx}

Give a day-by-day plan (each day: focus + 3-5 concrete tasks with time in minutes), the key topics to master,
study tips specific to these chapters, common mistakes students make, and an exam strategy.
JSON shape: {{"title": str, "overview": str, "key_topics": [str], "days": [{{"day": int, "focus": str, "tasks": [str]}}],
  "tips": [str], "common_mistakes": [str], "exam_strategy": [str]}}"""

    def validate(d):
        if not d.get("days"):
            raise ValueError("no days")
        return d

    res = _run("guide", prompt, lambda: off.guide(sel, days, query), 3500, validate, _lang(subject, query, chunks))
    res["sources"] = sources
    return res
