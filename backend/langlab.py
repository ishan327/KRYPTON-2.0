"""Language Lab: practise any of India's 22 scheduled languages — vocabulary, translation, speaking, conversation."""
import difflib
import re
import unicodedata

import growth
import langs
from llm import ai_json

TEACHER = """You are Krypton, a warm, patient language teacher for Indian school students. You teach India's scheduled
languages with correct native script, simple transliteration (Latin letters a student can read aloud) and plain
English meanings. Be accurate; if a word is uncertain in this language, choose a common, safe one.
Reply with ONE JSON object only."""


def _lang(code: str) -> dict:
    l = langs.info(code)
    if not l or code == "en":
        raise ValueError("Pick one of the Indian languages first.")
    return l


def words(code: str, topic: str, level: str, count: int) -> dict:
    l = _lang(code)
    count = max(4, min(int(count or 8), 15))
    data, engine, model, _ = ai_json(TEACHER, f"""Teach {count} useful {l['name']} ({l['native']}, {l['script']} script) words
for a {level or 'beginner'} school student on the topic "{topic or 'everyday life'}".
For each: the word in {l['script']} script, transliteration, English meaning, a short example sentence in {l['name']}
(native script), its transliteration and English meaning.
JSON: {{"words": [{{"word": str, "translit": str, "meaning": str, "example": str, "example_translit": str, "example_meaning": str}}]}}""",
                                        max_tokens=2500, temperature=0.4)
    ws = [w for w in data.get("words", []) if isinstance(w, dict) and w.get("word") and w.get("meaning")][:count]
    if len(ws) < 3:
        raise ValueError("Couldn't make a word list — try another topic.")
    return {"language": l, "words": ws, "engine": engine, "model": model}


def sentence(code: str, level: str) -> dict:
    l = _lang(code)
    data, engine, _, _ = ai_json(TEACHER, f"""Give ONE short English sentence (5-10 words) for a {level or 'beginner'} student
to translate into {l['name']}. Everyday school-life topics. JSON: {{"english": str}}""", max_tokens=200, temperature=0.9)
    return {"english": str(data.get("english", "")).strip(), "engine": engine}


def check_translation(code: str, english: str, answer: str) -> dict:
    l = _lang(code)
    if not answer.strip():
        raise ValueError("Type your translation first.")
    data, engine, _, _ = ai_json(TEACHER, f"""A student translated this English sentence into {l['name']} ({l['script']} script).
English: "{english}"
Student's {l['name']}: "{answer}"
Mark it out of 5 (meaning first, then grammar and spelling; transliterated Latin-letter answers are OK but note the script).
Give the best correct translation in native script with transliteration, and explain the mistakes simply in English.
JSON: {{"score": int, "correct": str, "correct_translit": str, "feedback": str}}""", max_tokens=700, temperature=0)
    score = max(0, min(5, int(data.get("score", 0) or 0)))
    xp = growth.add_xp("lang_practice", score) if score else {"gained": 0, "new_badges": []}
    return {"score": score, "correct": data.get("correct", ""), "correct_translit": data.get("correct_translit", ""),
            "feedback": data.get("feedback", ""), "xp": xp, "engine": engine}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s.lower())
    return re.sub(r"[\s\W_]+", "", s, flags=re.UNICODE)


def speak_check(code: str, target: str, heard: str) -> dict:
    """Compare what the student said (transcribed) with the target phrase."""
    l = _lang(code)
    ratio = difflib.SequenceMatcher(None, _norm(target), _norm(heard)).ratio()
    pct = round(ratio * 100)
    verdict = "Excellent — very clear!" if pct >= 85 else "Good — almost there." if pct >= 60 else "Keep practising — listen and try again."
    xp = growth.add_xp("lang_practice", 3 if pct >= 85 else 2 if pct >= 60 else 0) if pct >= 60 else {"gained": 0, "new_badges": []}
    return {"match": pct, "verdict": verdict, "heard": heard, "target": target, "language": l["name"], "xp": xp}


def chat(code: str, scenario: str, history: list[dict]) -> dict:
    l = _lang(code)
    convo = "\n".join(f"{'Student' if m.get('role') == 'user' else 'You'}: {m.get('content', '')}" for m in history[-12:])
    data, engine, model, _ = ai_json(TEACHER, f"""Role-play in {l['name']} ({l['script']} script) with a student who is learning it.
Scenario: {scenario or 'chatting with a new friend at school'}. You play the other person.
Keep replies short (1-2 simple sentences) and natural. If the student's last message has a mistake, gently correct it.
Conversation so far:
{convo or '(start the conversation yourself with a greeting suited to the scenario)'}

JSON: {{"reply": str (native script), "translit": str, "meaning": str (English), "correction": str (empty if the
student's last message was fine; else the corrected sentence + a one-line English explanation)}}""",
                                        max_tokens=600, temperature=0.6)
    if any(m.get("role") == "user" for m in history[-1:]):
        growth.add_xp("lang_practice", 1)
    return {"reply": data.get("reply", ""), "translit": data.get("translit", ""), "meaning": data.get("meaning", ""),
            "correction": data.get("correction", ""), "tts": l["tts"], "engine": engine, "model": model}
