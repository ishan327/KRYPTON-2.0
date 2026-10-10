"""Krypton backend — run this, then use the Chrome extension."""
import secrets
import subprocess
import sys
import threading
import time

from pathlib import Path

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import agent
import family
import features
import llm
import growth
import langlab
import langs
import mindmap_svg
import pdfgen
import tts
import school
import tutor
import users
import viva
from config import HOST, MODES, PORT, VERSION, settings
from library import library
from llm import ollama_status
from ui import banner, console, log_event, status_panel, step

app = FastAPI(title="Krypton", version=VERSION)
app.add_middleware(CORSMiddleware, allow_origin_regex=r"chrome-extension://.*|http://localhost:8766", allow_methods=["*"], allow_headers=["*"])

# Things only the laptop owner (the Chrome extension on 127.0.0.1) may use — never web accounts.
OWNER_ONLY = ("/api/settings", "/api/parent", "/api/focus", "/api/reload", "/api/usage", "/api/rules", "/api/public-url")


@app.middleware("http")
async def accounts(request: Request, call_next):
    path = request.url.path
    host = request.headers.get("host", "").split(":")[0]
    remote = "cf-connecting-ip" in request.headers or "cf-ray" in request.headers or host not in ("127.0.0.1", "localhost")
    uid = users.resolve(request.headers.get("x-user-token"))
    if path.startswith("/api") and not path.startswith("/api/auth"):
        if remote and not uid:
            return JSONResponse({"detail": "Please log in."}, status_code=401)
        if uid and path.startswith(OWNER_ONLY) and not (request.method == "GET" and path == "/api/settings"):
            return JSONResponse({"detail": "Only the laptop owner can do that."}, status_code=403)
    token = users.current_user.set(uid)
    lang_token = langs.current_lang.set(request.headers.get("x-lang", "") if request.headers.get("x-lang", "") in langs.LANGUAGES else "")
    try:
        return await call_next(request)
    finally:
        users.current_user.reset(token)
        langs.current_lang.reset(lang_token)


class StudyReq(BaseModel):
    cls: int | None = None
    subject: str | None = None
    chapters: list[str] = []
    query: str = ""
    count: int = 10
    difficulty: str = "mixed"
    paper_type: str = "full"
    days: int = 7


class SettingsReq(BaseModel):
    mode: str | None = None
    groq_api_key: str | None = None
    groq_model: str | None = None
    ollama_model: str | None = None
    agent_workspace: str | None = None


class SetupReq(BaseModel):
    groq_api_key: str
    password: str


class PasswordReq(BaseModel):
    password: str


class ResetReq(BaseModel):
    groq_api_key: str
    new_password: str


class RulesReq(BaseModel):
    focus_enabled: bool | None = None
    limit_minutes: int | None = None
    lock_minutes: int | None = None
    allow_quiz_unlock: bool | None = None
    unlock_pass: int | None = None
    blocked_sites: list[str] | None = None


class RecordReq(BaseModel):
    exam: str
    subject: str
    marks: float
    max_marks: float
    date: str = ""
    note: str = ""


class ProfileReq(BaseModel):
    name: str | None = None
    cls: int | None = None
    school: str | None = None
    board: str | None = None
    goal: str | None = None


class UsageReq(BaseModel):
    day: dict
    quizzes: list | None = None


class AgentReq(BaseModel):
    messages: list[dict]


class VerifyReq(BaseModel):
    challenge_id: str
    answers: list[int]


class EventReq(BaseModel):
    type: str
    host: str = ""
    minutes: float = 0


def _where(r: StudyReq) -> str:
    parts = [f"Class {r.cls}" if r.cls else "", r.subject or "", f"“{r.query[:40]}”" if r.query else "",
             f"{len(r.chapters)} ch" if r.chapters else ""]
    return " · ".join(p for p in parts if p)


def _logged(feature: str, r: StudyReq, res: dict, extra: str = "") -> dict:
    log_event(feature, res["engine"], f"{_where(r)} {extra}".strip(), res["ms"],
              note=" | ".join(res.get("notes") or []))
    return res


@app.get("/api/status")
def status():
    return {"ok": True, "version": VERSION, "settings": settings.public(), "library": library.stats(),
            "ollama": ollama_status()}


@app.post("/api/reload")
def reload_library():
    library.load()
    st = library.stats()
    log_event("settings", None, f"library reloaded → {st['books']} books · {st['chunks']:,} passages")
    return st


@app.get("/api/catalog")
def catalog():
    return library.catalog()


@app.get("/api/settings")
def get_settings():
    return settings.public()


@app.post("/api/settings")
def post_settings(r: SettingsReq):
    changes = {k: v for k, v in r.model_dump().items() if v is not None}
    if "mode" in changes and changes["mode"] not in MODES:
        raise HTTPException(400, "unknown mode")
    if "groq_api_key" in changes:
        if family.is_setup():
            raise HTTPException(403, "The Groq key is managed in the Parent board.")
        changes["groq_api_key"] = changes["groq_api_key"].strip()
    if "agent_workspace" in changes:
        p = Path(changes["agent_workspace"]).expanduser()
        if not p.is_absolute():
            raise HTTPException(400, "Use a full folder path, e.g. C:\\Users\\you\\Documents\\code")
        p.mkdir(parents=True, exist_ok=True)
    settings.update(changes)
    shown = {k: ("•••" if k == "groq_api_key" else v) for k, v in changes.items()}
    log_event("settings", changes.get("mode"), ", ".join(f"{k}={v}" for k, v in shown.items()))
    return settings.public()


@app.post("/api/explain")
def explain(r: StudyReq):
    res = features.explain(r.cls, r.subject, r.chapters, r.query)
    return _logged("explain", r, res, f"→ {len(res['data'].get('lines', []))} lines")


@app.post("/api/flashcards")
def flashcards(r: StudyReq):
    res = features.flashcards(r.cls, r.subject, r.chapters, r.query, max(3, min(r.count, 40)))
    return _logged("flashcards", r, res, f"→ {len(res['data'].get('cards', []))} cards")


@app.post("/api/quiz")
def quiz(r: StudyReq):
    res = features.quiz(r.cls, r.subject, r.chapters, r.query, max(3, min(r.count, 30)), r.difficulty)
    return _logged("quiz", r, res, f"→ {len(res['data'].get('questions', []))} questions")


@app.post("/api/paper")
def paper(r: StudyReq):
    res = features.paper(r.cls, r.subject, r.chapters, r.query, r.paper_type)
    return _logged("paper", r, res, f"→ {res['data'].get('max_marks')} marks")


@app.post("/api/mindmap")
def mindmap(r: StudyReq):
    res = features.mindmap(r.cls, r.subject, r.chapters, r.query)
    res["svg"] = mindmap_svg.render(res["data"])
    return _logged("mindmap", r, res, f"→ {len(res['data'].get('branches', []))} branches")


@app.post("/api/guide")
def guide(r: StudyReq):
    res = features.guide(r.cls, r.subject, r.chapters, r.query, max(1, min(r.days, 30)))
    return _logged("guide", r, res, f"→ {len(res['data'].get('days', []))} days")


# ---------------- focus guard ----------------
CHALLENGES: dict[str, dict] = {}
_ch_lock = threading.Lock()


@app.post("/api/focus/challenge")
def challenge(r: StudyReq):
    qs = growth.challenge_items(3)  # weak spots first: scrolling time becomes revision time
    res = {"engine": "offline", "ms": 0}
    if len(qs) < 3:
        res = features.quiz(r.cls, r.subject, r.chapters, r.query, 3, "easy")
        qs += res["data"]["questions"][:3 - len(qs)]
    if len(qs) < 3:  # tiny chapter: widen to whole subject
        res = features.quiz(r.cls, r.subject, [], "", 3, "easy")
        qs += res["data"]["questions"][:3 - len(qs)]
    cid = secrets.token_urlsafe(12)
    with _ch_lock:
        now = time.time()
        for k in [k for k, v in CHALLENGES.items() if now - v["t"] > 1800]:
            CHALLENGES.pop(k)
        CHALLENGES[cid] = {"t": now, "questions": qs}
    weak = sum(1 for q in qs if q.get("review_id"))
    log_event("challenge", res["engine"], f"{_where(r)} → 3 unlock questions ({weak} from weak spots)", res["ms"])
    return {"challenge_id": cid, "engine": res["engine"], "pass_mark": settings.get("unlock_pass"),
            "questions": [{"question": q["question"], "options": q["options"]} for q in qs]}


@app.post("/api/focus/verify")
def verify(r: VerifyReq):
    with _ch_lock:
        ch = CHALLENGES.pop(r.challenge_id, None)
    if not ch:
        raise HTTPException(404, "Challenge expired — get a new one")
    qs = ch["questions"]
    correct = [i < len(r.answers) and r.answers[i] == q["answer_index"] for i, q in enumerate(qs)]
    score = sum(correct)
    need = min(int(family.rules()["unlock_pass"]), len(qs))
    passed = score >= need and family.rules()["allow_quiz_unlock"]
    for q, ok, a in zip(qs, correct, r.answers):
        if q.get("review_id"):
            try:
                growth.answer_review(q["review_id"], a if ok else -1)
            except KeyError:
                pass
    growth.record_attempts([{**q, "chosen": a} for q, a in zip(qs, r.answers) if not q.get("review_id")])
    if passed:
        growth.add_xp("focus_unlock")
    log_event("verify", None, f"{score}/{len(qs)} correct → {'UNLOCKED' if passed else 'still locked'}")
    return {"passed": passed, "score": score, "total": len(qs), "need": need, "correct": correct,
            "review": [{"question": q["question"], "answer": q["options"][q["answer_index"]],
                        "explanation": q.get("explanation", "")} for q in qs]}


@app.post("/api/focus/event")
def focus_event(r: EventReq):
    if r.type == "lock":
        log_event("lock", None, f"{r.host} blocked after {r.minutes:.0f} min of scrolling")
    elif r.type == "unlock":
        log_event("unlock", None, f"task complete — scrolling allowed again")
    return {"ok": True}


# ---------------- parent board ----------------
def _guard(fn, *a):
    try:
        return fn(*a)
    except PermissionError as e:
        raise HTTPException(401, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/parent/status")
def parent_status():
    return {"setup": family.is_setup()}


@app.post("/api/parent/setup")
def parent_setup(r: SetupReq):
    token = _guard(family.setup, r.groq_api_key.strip(), r.password)
    log_event("settings", None, "👪 parent account created — Groq key verified")
    return {"token": token}


@app.post("/api/parent/login")
def parent_login(r: PasswordReq):
    token = _guard(family.login, r.password)
    log_event("settings", None, "👪 parent logged in")
    return {"token": token}


@app.post("/api/parent/reset")
def parent_reset(r: ResetReq):
    token = _guard(family.reset_password, r.groq_api_key, r.new_password)
    log_event("settings", None, "👪 parent password reset with Groq key")
    return {"token": token}


@app.post("/api/parent/password")
def parent_password(r: PasswordReq, x_parent_token: str | None = Header(None)):
    _guard(family.require, x_parent_token)
    return {"token": _guard(family.change_password, r.password)}


@app.post("/api/parent/groq-key")
def parent_groq_key(r: PasswordReq, x_parent_token: str | None = Header(None)):
    _guard(family.require, x_parent_token)
    err = family.check_groq_key(r.password.strip())
    if err:
        raise HTTPException(400, err)
    settings.update({"groq_api_key": r.password.strip()})
    log_event("settings", None, "👪 Groq key updated by parent")
    return settings.public()


@app.get("/api/parent/overview")
def parent_overview(x_parent_token: str | None = Header(None)):
    _guard(family.require, x_parent_token)
    return {**family.overview(), "settings": settings.public()}


@app.get("/api/rules")
def get_rules():
    return {**family.rules(), "parent_setup": family.is_setup()}


@app.post("/api/parent/rules")
def post_rules(r: RulesReq, x_parent_token: str | None = Header(None)):
    _guard(family.require, x_parent_token)
    rules = family.set_rules({k: v for k, v in r.model_dump().items() if v is not None})
    log_event("settings", None, f"👪 rules: {rules['limit_minutes']} min scroll → {rules['lock_minutes']} min lock, "
                                f"quiz unlock {'on' if rules['allow_quiz_unlock'] else 'off'}")
    return rules


# ---------------- student profile, marks, usage ----------------
@app.get("/api/profile")
def get_profile():
    return {"profile": family.profile(), "records": family.records()}


@app.post("/api/profile")
def post_profile(r: ProfileReq):
    return family.set_profile(r.model_dump())


@app.post("/api/records")
def post_record(r: RecordReq):
    if r.max_marks <= 0 or r.marks < 0 or r.marks > r.max_marks:
        raise HTTPException(400, "Marks must be between 0 and the maximum.")
    rec = family.add_record(r.model_dump())
    log_event("settings", None, f"📊 marks saved: {r.exam} {r.subject} {r.marks:g}/{r.max_marks:g}")
    return rec


@app.delete("/api/records/{rid}")
def delete_record(rid: str):
    family.delete_record(rid)
    return {"ok": True}


@app.post("/api/usage")
def post_usage(r: UsageReq):
    if "date" in r.day:
        family.save_usage(r.day, r.quizzes)
        growth.sync_study(r.day)
    return {"ok": True}


# ---------------- weak spots, revision, XP ----------------
class AttemptsReq(BaseModel):
    items: list[dict]


class ReviewAnswerReq(BaseModel):
    id: str
    choice: int


class XpReq(BaseModel):
    event: str


class CodeReq(BaseModel):
    code: str


@app.post("/api/attempts")
def attempts(r: AttemptsReq):
    res = growth.record_attempts(r.items[:50])
    wrong = sum(1 for i in r.items if i.get("chosen") != i.get("answer_index"))
    if wrong:
        log_event("quiz", None, f"🎯 {wrong} mistake(s) saved to Revise")
    return res


@app.get("/api/review")
def review():
    return growth.review_overview()


@app.post("/api/review/answer")
def review_answer(r: ReviewAnswerReq):
    try:
        res = growth.answer_review(r.id, r.choice)
    except KeyError as e:
        raise HTTPException(404, str(e))
    log_event("verify", None, f"🎯 revision card {'✔ promoted to box ' + str(res['box']) if res['correct'] else '✘ back to box 1'}")
    return res


@app.post("/api/xp")
def xp(r: XpReq):
    if r.event not in growth.CLIENT_EVENTS:
        raise HTTPException(400, "unknown event")
    return growth.add_xp(r.event)


@app.get("/api/game")
def game():
    return {**growth.game(), "my_code": growth.share_code(family.profile().get("name", ""))}


@app.post("/api/game/friend")
def add_friend(r: CodeReq):
    try:
        return growth.add_friend(r.code)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------- viva (oral exam) ----------------
class VivaStartReq(StudyReq):
    pass


class VivaAnswerReq(BaseModel):
    session_id: str
    answer: str = ""


@app.post("/api/viva/start")
def viva_start(r: VivaStartReq):
    t0 = time.time()
    res = _tutor(viva.start, r.cls, r.subject, r.chapters, r.query, r.count)
    log_event("challenge", res["engine"], f"🎙️ viva started: {res['topic']} · {res['total']} questions", (time.time() - t0) * 1000)
    return res


@app.post("/api/viva/answer")
def viva_answer(r: VivaAnswerReq):
    res = _tutor(viva.answer, r.session_id, r.answer)
    if res.get("follow_up"):
        log_event("verify", None, f"🎙️ viva Q{res['n']}: {res['score']}/5 → follow-up question")
    else:
        log_event("verify", None, f"🎙️ viva Q{res['n']}: {res['final_score']}/5"
                  + (f" — finished {res['report']['score']}/{res['report']['out_of']}" if res.get("report") else ""))
    return res


# ---------------- snap & solve tutor ----------------
class ReadReq(BaseModel):
    image: str
    kind: str = "question"


class TutorStartReq(BaseModel):
    question: str
    cls: int | None = None
    subject: str | None = None


class TutorCheckReq(BaseModel):
    session_id: str
    work: str = ""


def _tutor(fn, *a):
    try:
        return fn(*a)
    except KeyError as e:
        raise HTTPException(404, str(e).strip("'\""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except llm.EngineError as e:
        raise HTTPException(503, "This needs AI — switch to Groq or Local mode. " + str(e))


@app.post("/api/tutor/read")
def tutor_read(r: ReadReq):
    t0 = time.time()
    text = _tutor(tutor.read_image, r.image, r.kind)
    log_event("explain", "groq", f"📸 read {'question' if r.kind == 'question' else 'working'}: “{text[:50]}”", (time.time() - t0) * 1000)
    return {"text": text}


@app.post("/api/tutor/start")
def tutor_start(r: TutorStartReq):
    t0 = time.time()
    res = _tutor(tutor.start, r.question, r.cls, r.subject)
    log_event("explain", res["engine"], f"📸 tutor planned {res['total']} steps: “{r.question[:45]}”", (time.time() - t0) * 1000)
    return res


@app.post("/api/tutor/check")
def tutor_check(r: TutorCheckReq):
    res = _tutor(tutor.check, r.session_id, r.work)
    log_event("verify", None, "📸 step ✔" + (" — SOLVED 🎉" if res.get("solved") else "") if res["correct"] else "📸 step ✘ — coaching")
    return res


@app.post("/api/tutor/hint")
def tutor_hint(r: TutorCheckReq):
    return _tutor(tutor.hint, r.session_id)


# ---------------- language lab ----------------
class LangReq(BaseModel):
    lang: str
    topic: str = ""
    level: str = "beginner"
    count: int = 8
    english: str = ""
    answer: str = ""
    target: str = ""
    heard: str = ""
    scenario: str = ""
    messages: list[dict] = []


@app.get("/api/lang/list")
def lang_list():
    return {"languages": langs.all_languages()}


@app.get("/api/lang/alphabet/{code}")
def lang_alphabet(code: str):
    try:
        return langs.alphabet(code)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/lang/words")
def lang_words(r: LangReq):
    t0 = time.time()
    res = _tutor(langlab.words, r.lang, r.topic, r.level, r.count)
    log_event("flashcards", res["engine"], f"🗣️ {res['language']['name']} words · {r.topic or 'everyday'} → {len(res['words'])}", (time.time() - t0) * 1000)
    return res


@app.post("/api/lang/sentence")
def lang_sentence(r: LangReq):
    return _tutor(langlab.sentence, r.lang, r.level)


@app.post("/api/lang/check")
def lang_check(r: LangReq):
    res = _tutor(langlab.check_translation, r.lang, r.english, r.answer)
    log_event("verify", res["engine"], f"🗣️ {langs.info(r.lang)['name']} translation {res['score']}/5")
    return res


@app.post("/api/lang/speak")
def lang_speak(r: LangReq):
    res = _tutor(langlab.speak_check, r.lang, r.target, r.heard)
    log_event("verify", None, f"🗣️ {res['language']} speaking {res['match']}% match")
    return res


@app.post("/api/lang/chat")
def lang_chat(r: LangReq):
    t0 = time.time()
    res = _tutor(langlab.chat, r.lang, r.scenario, r.messages)
    log_event("explain", res["engine"], f"🗣️ {langs.info(r.lang)['name']} role-play: {r.scenario[:30] or 'new friend'}", (time.time() - t0) * 1000)
    return res


# ---------------- voice ----------------
@app.post("/api/transcribe")
async def transcribe(request: Request):
    audio = await request.body()
    if not 1000 < len(audio) < 20_000_000:
        raise HTTPException(400, "No audio recorded — hold the mic a bit longer.")
    t0 = time.time()
    try:
        info = langs.info(request.query_params.get("lang", ""))
        text = llm.transcribe(audio, request.headers.get("content-type", "audio/webm"), info["whisper"] if info else None)
    except llm.EngineError as e:
        raise HTTPException(503, str(e))
    log_event("explain", "groq", f"🎤 heard “{text[:60]}”", (time.time() - t0) * 1000)
    return {"text": text}


class SpeakReq(BaseModel):
    text: str


@app.post("/api/tts")
def text_to_speech(r: SpeakReq):
    if not r.text.strip() or not tts.can_speak(r.text):
        raise HTTPException(415, "Use the browser voice for this text")
    try:
        return Response(tts.synth(r.text), media_type="audio/wav")
    except (RuntimeError, OSError, subprocess.SubprocessError) as e:
        raise HTTPException(503, str(e))


class PdfReq(BaseModel):
    kind: str          # explain | flashcards
    data: dict
    meta: str = ""
    sources: list = []


@app.post("/api/pdf")
def make_pdf(r: PdfReq):
    if r.kind not in ("explain", "flashcards", "mindmap"):
        raise HTTPException(400, "unknown kind")
    t0 = time.time()
    try:
        pdf = pdfgen.render(r.kind, r.data, r.meta, r.sources)
    except (RuntimeError, OSError, subprocess.SubprocessError) as e:
        raise HTTPException(503, str(e))
    log_event("paper", None, f"📄 PDF {r.kind}: “{str(r.data.get('title', ''))[:40]}” ({len(pdf) // 1024} KB)", (time.time() - t0) * 1000)
    return Response(pdf, media_type="application/pdf")


# ---------------- agent ----------------
@app.post("/api/agent")
def agent_chat(r: AgentReq):
    res = agent.chat(r.messages)
    tools = ", ".join(s["tool"] for s in res["steps"]) or "chat"
    last = r.messages[-1]["content"][:50] if r.messages else ""
    log_event("explain", res["engine"], f"🤖 agent “{last}” → {tools}", res["ms"], note=" | ".join(res["notes"]))
    return res


# ---------------- web accounts (public link) ----------------
class SignupReq(BaseModel):
    username: str
    password: str
    name: str = ""
    cls: int | None = None


class LoginReq(BaseModel):
    username: str
    password: str


@app.get("/api/auth/slots")
def auth_slots():
    return {"used": users.count(), "max": users.MAX_USERS}


@app.post("/api/auth/signup")
def auth_signup(r: SignupReq):
    token = _guard(users.signup, r.username, r.password, r.name, r.cls)
    uid = users.resolve(token)
    ctx = users.current_user.set(uid)
    try:
        family.set_profile({"name": r.name.strip() or r.username, "cls": r.cls})
    finally:
        users.current_user.reset(ctx)
    log_event("settings", None, f"👤 new account @{r.username.strip().lower()} ({users.count()}/{users.MAX_USERS})")
    return {"token": token, "user": users.info(uid)}


@app.post("/api/auth/login")
def auth_login(r: LoginReq):
    token = _guard(users.login, r.username, r.password)
    log_event("settings", None, f"👤 @{r.username.strip().lower()} logged in")
    return {"token": token, "user": users.info(users.resolve(token))}


@app.get("/api/auth/me")
def auth_me(x_user_token: str | None = Header(None)):
    uid = users.resolve(x_user_token)
    if not uid:
        raise HTTPException(401, "Please log in.")
    return users.info(uid)


@app.post("/api/auth/logout")
def auth_logout(x_user_token: str | None = Header(None)):
    if x_user_token:
        users.logout(x_user_token)
    return {"ok": True}


@app.get("/api/public-url")
def public_url():
    return {"url": PUBLIC_URL["url"], "accounts": users.count(), "max": users.MAX_USERS}


@app.get("/api/parent/users")
def parent_users(x_parent_token: str | None = Header(None)):
    _guard(family.require, x_parent_token)
    return {"users": users.all_users(), "max": users.MAX_USERS, "public_url": PUBLIC_URL["url"]}


@app.delete("/api/parent/users/{uid}")
def parent_delete_user(uid: str, x_parent_token: str | None = Header(None)):
    _guard(family.require, x_parent_token)
    users.delete(uid)
    log_event("settings", None, "👤 web account removed by parent")
    return {"ok": True}


# ---------------- school administration ----------------
# Staff use their own admin password (X-School-Token); students/parents read their feed under /api.
class SchoolSetupReq(BaseModel):
    school_name: str = ""
    username: str
    name: str = ""
    cls: str
    password: str


class SchoolLoginReq(BaseModel):
    username: str
    password: str


class SchoolEventReq(BaseModel):
    title: str
    date: str
    time: str = ""
    description: str = ""
    audience: str = "all"
    remind_days: int = 2


class SchoolReportReq(BaseModel):
    student_id: str
    category: str
    area: str = "Other"
    note: str
    date: str = ""


def _staff(token) -> dict:
    return _guard(school.require, token)


@app.get("/school-api/status")
def school_status():
    return school.status()


@app.post("/school-api/setup")
def school_setup(r: SchoolSetupReq):
    # Hackathon mode: the school admin can be created from any device (first one wins; later it's login only)
    token = _guard(school.setup, r.school_name, r.username, r.name, r.cls, r.password)
    log_event("settings", None, f"🏫 class admin @{r.username} created for Class {r.cls}")
    return {"token": token}


@app.post("/school-api/login")
def school_login(r: SchoolLoginReq):
    return {"token": _guard(school.login, r.username, r.password)}


@app.get("/school-api/overview")
def school_overview(x_school_token: str | None = Header(None)):
    return school.admin_overview(_staff(x_school_token))


@app.post("/school-api/events")
def school_event(r: SchoolEventReq, x_school_token: str | None = Header(None)):
    e = _guard(school.add_event, r.model_dump(), _staff(x_school_token))
    log_event("settings", None, f"🏫 event posted: {e['title']} on {e['date']}")
    return e


@app.post("/school-api/reports")
def school_report(r: SchoolReportReq, x_school_token: str | None = Header(None)):
    rep = _guard(school.add_report, r.model_dump(), _staff(x_school_token))
    log_event("settings", None, f"🏫 behaviour report ({rep['category']}) for {rep['student_name']}")
    return rep


@app.delete("/school-api/{kind}/{item_id}")
def school_delete(kind: str, item_id: str, x_school_token: str | None = Header(None)):
    admin = _staff(x_school_token)
    if kind not in ("events", "reports"):
        raise HTTPException(400, "unknown item")
    school.delete(kind, item_id, admin)
    return {"ok": True}


@app.get("/api/school/feed")
def school_feed():
    return school.feed(users.current_user.get())


@app.get("/school")
def web_school():
    page = (EXT_DIR / "school.html").read_text(encoding="utf-8").replace("<head>", '<head>\n  <base href="/ext/">', 1)
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


# ---------------- web version of the app ----------------
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
EXT_DIR = Path(__file__).resolve().parent.parent / "extension"


@app.get("/", response_class=HTMLResponse)
def web_app():
    page = (EXT_DIR / "app.html").read_text(encoding="utf-8")
    page = page.replace("<head>", '<head>\n  <base href="/ext/">', 1)
    page = page.replace('<script src="shared.js"></script>', '<script src="/web/web.js"></script>\n<script src="shared.js"></script>', 1)
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


@app.get("/login")
def web_login():
    return HTMLResponse((WEB_DIR / "login.html").read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")
app.mount("/ext", StaticFiles(directory=EXT_DIR), name="ext")

# ---------------- public link (Cloudflare quick tunnel) ----------------
PUBLIC_URL = {"url": None}


def cloudflared_path() -> str | None:
    import shutil
    found = shutil.which("cloudflared")
    for p in (found, r"C:\Program Files (x86)\cloudflared\cloudflared.exe", r"C:\Program Files\cloudflared\cloudflared.exe",
              str(Path.home() / r"AppData\Local\Microsoft\WinGet\Links\cloudflared.exe")):
        if p and Path(p).exists():
            return p
    return None


def start_tunnel():
    import atexit
    import re as _re
    from rich.panel import Panel

    exe = cloudflared_path()
    if not exe:
        step("Public link", False, "cloudflared not installed — run: winget install Cloudflare.cloudflared")
        return
    proc = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://{HOST}:{PORT}"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    atexit.register(proc.terminate)

    def watch():
        for line in proc.stdout:
            m = _re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if m and not PUBLIC_URL["url"]:
                PUBLIC_URL["url"] = m.group(0)
                (Path(__file__).resolve().parent.parent / "data" / "public_url.txt").write_text(m.group(0), encoding="utf-8")
                console.print()
                console.print(Panel(f"[bold #5cff6a]{m.group(0)}[/]\n\n[#cfe9da]Share this link with up to {users.MAX_USERS} people. "
                                    f"Each signs up with their own account.\nIt works while this window stays open.[/]",
                                    title="[bold]🌍 PUBLIC LINK[/]", border_style="#5cff6a", padding=(1, 3)))
        console.print("  [#ff5f5f]✘ Public link closed.[/]")

    threading.Thread(target=watch, daemon=True).start()


# ---------------- boot ----------------
def gpu_name() -> str:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        return out.splitlines()[0] if out else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def boot():
    banner()
    st = library.stats()
    step("NCERT library", bool(st["chunks"]),
         f"{st['books']} books · {st['chapters']} chapters · {st['chunks']:,} passages · classes "
         f"{min(st['classes'])}–{max(st['classes'])}" if st["chunks"] else "not indexed — run setup_krypton.py")
    key = settings.get("groq_api_key")
    step("Groq cloud AI", True if key else None,
         f"key {settings.public()['groq_key_hint']} · {settings.get('groq_model')}" if key else "no key yet — parent adds it in the Parent board")
    r = family.rules()
    step("Parent controls", family.is_setup() or None,
         f"{r['limit_minutes']} min scrolling → {r['lock_minutes']} min lock · quiz unlock {'on' if r['allow_quiz_unlock'] else 'off'}"
         + ("" if family.is_setup() else " · parent account not created yet"))
    ol = ollama_status()
    gpu = gpu_name()
    step("Local GPU AI", ol["has_model"] or (None if ol["running"] else False),
         (f"{ol['model']} ready" if ol["has_model"] else f"Ollama running, {ol['model']} not pulled" if ol["running"]
          else "Ollama not running") + (f" · {gpu}" if gpu else ""))
    step("Offline engine", True, "always available — no AI needed")
    mode = settings.get("mode")
    status_panel([("Mode", {"groq": "⚡ Groq cloud", "local": "🖥  Local GPU", "offline": "📘 Offline"}[mode]),
                  ("Fallback", "Groq → Local GPU → Offline" if mode == "groq" else "Local GPU → Offline" if mode == "local" else "—"),
                  ("Features", "Explain · Flashcards · Quiz · CBSE Paper · Study Guide · My Marks"),
                  ("Superpowers", "🤖 AI Agent · 🔒 Focus Lock · 👪 Parent board"),
                  ("Agent folder", str(agent.workspace())),
                  ("Extension", "chrome://extensions → Load unpacked → krypton/extension")],
                 f"http://{HOST}:{PORT}")


def books_newer_than_index() -> bool:
    from config import BOOKS_DIR, INDEX_DIR
    idx = INDEX_DIR / "library.pkl"
    if not BOOKS_DIR.exists():
        return False
    if not idx.exists():
        return True
    newest = max((p.stat().st_mtime for p in BOOKS_DIR.rglob("*.pdf")), default=0)
    return newest > idx.stat().st_mtime


if __name__ == "__main__":
    if books_newer_than_index():
        import ingest
        console.print("  [#ffd75f]New NCERT books found — updating the index…[/]")
        ingest.run()
        library.load()
    boot()
    if "--public" in sys.argv:
        step("Public link", None, f"starting Cloudflare tunnel · {users.count()}/{users.MAX_USERS} web accounts used")
        start_tunnel()
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
