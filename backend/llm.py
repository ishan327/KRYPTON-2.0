"""AI engines: Groq (cloud) and Ollama (local GPU). Callers fall back to the offline engine."""
import json
import re
import time

import requests

from config import settings

GROQ_URL = "https://api.groq.com/openai/v1"
GROQ_PREFERRED = ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b", "llama-3.3-70b-versatile",
                  "llama-3.1-8b-instant"]


class EngineError(Exception):
    pass


def parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


# ---------------- Groq ----------------
def _groq_pick_model(key: str) -> str | None:
    r = requests.get(f"{GROQ_URL}/models", headers={"Authorization": f"Bearer {key}"}, timeout=20)
    if not r.ok:
        return None
    ids = [m["id"] for m in r.json().get("data", []) if m.get("active", True)]
    for m in GROQ_PREFERRED:
        if m in ids:
            return m
    chat = [i for i in ids if not re.search(r"whisper|guard|tts|distil|prompt", i)]
    return chat[0] if chat else None


def groq_chat(system: str, user: str, json_mode: bool, max_tokens: int, temperature: float) -> tuple[str, str]:
    key = settings.get("groq_api_key")
    if not key:
        raise EngineError("No Groq API key set (add it in Krypton → Settings)")
    model = settings.get("groq_model")
    for attempt in range(3):
        body = {"model": model, "temperature": temperature, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            r = requests.post(f"{GROQ_URL}/chat/completions", json=body, timeout=120,
                              headers={"Authorization": f"Bearer {key}"})
        except requests.RequestException as e:
            raise EngineError(f"Groq unreachable ({type(e).__name__}) — are you online?")
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"], model
        err = r.text[:300]
        if r.status_code == 401:
            raise EngineError("Groq rejected the API key")
        if r.status_code == 429 and attempt < 2:
            wait = float(r.headers.get("retry-after", 3))
            if wait <= 15:
                time.sleep(wait)
                continue
            raise EngineError("Groq rate limit reached — try again in a minute")
        if r.status_code in (400, 404) and "model" in err.lower() and attempt == 0:
            new = _groq_pick_model(key)
            if new and new != model:
                model = new
                settings.update({"groq_model": new})
                continue
        if r.status_code == 400 and "json" in err.lower() and json_mode and attempt < 2:
            continue  # json_validate_failed: just retry
        raise EngineError(f"Groq error {r.status_code}: {err}")
    raise EngineError("Groq failed after retries")


# ---------------- Ollama ----------------
def ollama_status() -> dict:
    url, model = settings.get("ollama_url"), settings.get("ollama_model")
    try:
        r = requests.get(f"{url}/api/tags", timeout=3)
        names = [m["name"] for m in r.json().get("models", [])]
        has = any(n == model or n.split(":")[0] == model or n == f"{model}:latest" for n in names)
        return {"running": True, "models": names, "has_model": has, "model": model}
    except (requests.RequestException, ValueError):
        return {"running": False, "models": [], "has_model": False, "model": model}


def ollama_chat(system: str, user: str, json_mode: bool, max_tokens: int, temperature: float) -> tuple[str, str]:
    st = ollama_status()
    if not st["running"]:
        raise EngineError("Ollama isn't running")
    if not st["has_model"]:
        raise EngineError(f"Local model {st['model']} isn't downloaded yet")
    body = {"model": st["model"], "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": 12288},
            "keep_alive": "30m"}
    if json_mode:
        body["format"] = "json"
    try:
        r = requests.post(f"{settings.get('ollama_url')}/api/chat", json=body, timeout=600)
        r.raise_for_status()
    except requests.RequestException as e:
        raise EngineError(f"Local model failed: {e}")
    return r.json()["message"]["content"], st["model"]


ENGINES = {"groq": groq_chat, "local": ollama_chat}


# ---------------- speech to text (Groq Whisper) ----------------
def transcribe(audio: bytes, mime: str, language: str | None = None) -> str:
    key = settings.get("groq_api_key")
    if not key:
        raise EngineError("Voice input needs the Groq key (parent board)")
    ext = next((e for e in ("ogg", "mp4", "wav", "mpeg") if e in mime), "webm").replace("mpeg", "mp3")
    for model in ("whisper-large-v3-turbo", "whisper-large-v3"):
        try:
            r = requests.post(f"{GROQ_URL}/audio/transcriptions", headers={"Authorization": f"Bearer {key}"},
                              files={"file": (f"speech.{ext}", audio, mime or "audio/webm")},
                              data={"model": model, "temperature": "0",
                                    "prompt": "Student talking to a study assistant about NCERT, CBSE, homework, code.",
                                    **({"language": language} if language else {})},
                              timeout=60)
        except requests.RequestException as e:
            raise EngineError(f"Groq unreachable ({type(e).__name__})")
        if r.ok:
            return r.json().get("text", "").strip()
        if r.status_code not in (400, 404):
            break
    raise EngineError(f"Transcription failed ({r.status_code}): {r.text[:150]}")


# ---------------- tool calling (for the agent) ----------------
def _groq_tools(messages: list, tools: list) -> tuple[dict, str]:
    key = settings.get("groq_api_key")
    if not key:
        raise EngineError("No Groq API key set (parent board → Account)")
    model = settings.get("groq_model")
    body = {"model": model, "messages": messages, "tools": tools, "tool_choice": "auto",
            "temperature": 0.3, "max_tokens": 4000}
    for attempt in range(3):
        try:
            r = requests.post(f"{GROQ_URL}/chat/completions", json=body, timeout=120,
                              headers={"Authorization": f"Bearer {key}"})
        except requests.RequestException as e:
            raise EngineError(f"Groq unreachable ({type(e).__name__})")
        if r.ok:
            m = r.json()["choices"][0]["message"]
            calls = [{"id": c["id"], "name": c["function"]["name"],
                      "args": json.loads(c["function"].get("arguments") or "{}")} for c in m.get("tool_calls") or []]
            return {"content": m.get("content") or "", "tool_calls": calls}, model
        if r.status_code == 429 and attempt < 2:
            time.sleep(min(float(r.headers.get("retry-after", 3)), 10))
            continue
        if r.status_code == 400 and "tool" in r.text.lower() and attempt < 2:
            continue  # tool_use_failed: the model produced a bad call, ask again
        raise EngineError(f"Groq error {r.status_code}: {r.text[:200]}")
    raise EngineError("Groq failed after retries")


def _ollama_tools(messages: list, tools: list) -> tuple[dict, str]:
    st = ollama_status()
    if not st["has_model"]:
        raise EngineError("Local model not available")
    conv = []
    for m in messages:  # OpenAI-style history -> Ollama style
        m = dict(m)
        if m.get("tool_calls"):
            m["tool_calls"] = [{"function": {"name": c["function"]["name"],
                                             "arguments": json.loads(c["function"]["arguments"])}} for c in m["tool_calls"]]
        m.pop("tool_call_id", None)
        conv.append(m)
    try:
        r = requests.post(f"{settings.get('ollama_url')}/api/chat", timeout=600, json={
            "model": st["model"], "messages": conv, "tools": tools, "stream": False,
            "options": {"temperature": 0.3, "num_ctx": 12288}, "keep_alive": "30m"})
        r.raise_for_status()
    except requests.RequestException as e:
        raise EngineError(f"Local model failed: {e}")
    m = r.json()["message"]
    calls = [{"id": f"call_{i}", "name": c["function"]["name"], "args": c["function"].get("arguments") or {}}
             for i, c in enumerate(m.get("tool_calls") or [])]
    return {"content": m.get("content") or "", "tool_calls": calls}, st["model"]


def chat_tools(messages: list, tools: list) -> tuple[dict, str, str]:
    """One model turn with tools. Returns (message, engine, model); raises EngineError if no AI is available."""
    mode = settings.get("mode")
    chain = {"groq": [("groq", _groq_tools), ("local", _ollama_tools)], "local": [("local", _ollama_tools)]}.get(mode, [])
    notes = []
    for name, fn in chain:
        try:
            msg, model = fn(messages, tools)
            return msg, name, model
        except (EngineError, ValueError, KeyError) as e:
            notes.append(str(e))
    raise EngineError("; ".join(notes) or "offline mode")


def ai_json(system: str, user: str, max_tokens: int = 4000, temperature: float = 0.4,
            mode: str | None = None) -> tuple[dict, str, str, list[str]]:
    """Run the AI chain for the current mode. Returns (data, engine, model, notes).
    Raises EngineError (with notes) when no AI engine is available -> caller uses offline engine."""
    mode = mode or settings.get("mode")
    chain = {"groq": ["groq", "local"], "local": ["local"], "offline": []}.get(mode, [])
    notes = []
    for engine in chain:
        for attempt in range(2):
            try:
                text, model = ENGINES[engine](system, user, True, max_tokens, temperature)
                return parse_json(text), engine, model, notes
            except EngineError as e:
                notes.append(str(e))
                break
            except (ValueError, KeyError):
                if attempt == 1:
                    notes.append(f"{engine} returned unreadable JSON")
    raise EngineError("; ".join(notes) if notes else "offline mode")
