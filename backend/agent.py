"""Krypton Agent: a study assistant that can open tabs, work on code files and use the NCERT library."""
import json
import re
import time
from pathlib import Path

import family
import growth
import langs
import users
from config import ROOT, settings
from library import library
from llm import EngineError, chat_tools

MAX_STEPS = 8
FILE_LIMIT = 60_000

SYSTEM = """You are Krypton Agent, a friendly, sharp AI assistant for an Indian school student (CBSE/NCERT, Classes 1-10).
You can act, not just talk. Use tools whenever they help:
- open_tab / web_search: open websites or searches in the browser (never open distracting sites during study time).
- search_ncert: look up the student's NCERT textbooks; base study answers on what you find and cite the chapter.
- open_krypton: open Krypton's study tools (explain, flashcards, quiz, paper, guide) on a topic.
- list_files / read_file / write_file / edit_file: work on code and notes inside the student's workspace folder.
  Read a file before editing it. Keep edits minimal and explain what you changed.
- get_student_info: the student's profile, exam marks, quiz scores and today's study time — use it to give
  personal advice (weak subjects, what to revise next).
Be concise and encouraging. Use simple language matching the student's class. After using tools, tell the student
what you did. Today is {today}. Workspace folder: {workspace}"""

TOOLS = [
    {"name": "open_tab", "description": "Open a website in a new browser tab.",
     "parameters": {"url": {"type": "string", "description": "Full URL, e.g. https://www.wikipedia.org"}}, "required": ["url"]},
    {"name": "web_search", "description": "Open a Google search for a query in a new tab.",
     "parameters": {"query": {"type": "string"}}, "required": ["query"]},
    {"name": "search_ncert", "description": "Search the NCERT textbooks (Classes 1-10). Returns the best matching passages.",
     "parameters": {"query": {"type": "string"}, "cls": {"type": "integer", "description": "Class 1-10 (optional)"},
                    "subject": {"type": "string", "description": "e.g. Science, Mathematics (optional)"}},
     "required": ["query"]},
    {"name": "open_krypton", "description": "Open a Krypton study tool on a topic for the student.",
     "parameters": {"tool": {"type": "string", "enum": ["explain", "flashcards", "quiz", "paper", "guide"]},
                    "topic": {"type": "string"}}, "required": ["tool", "topic"]},
    {"name": "list_files", "description": "List files in a folder of the workspace ('.' = workspace root).",
     "parameters": {"path": {"type": "string"}}, "required": ["path"]},
    {"name": "read_file", "description": "Read a text/code file from the workspace.",
     "parameters": {"path": {"type": "string"}}, "required": ["path"]},
    {"name": "write_file", "description": "Create or overwrite a text/code file in the workspace.",
     "parameters": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
    {"name": "edit_file", "description": "Replace an exact piece of text in a workspace file.",
     "parameters": {"path": {"type": "string"}, "find": {"type": "string", "description": "Exact existing text"},
                    "replace": {"type": "string"}}, "required": ["path", "find", "replace"]},
    {"name": "get_student_info", "description": "Get the student's profile, exam marks, quiz scores and study time.",
     "parameters": {}, "required": []},
]
SCHEMAS = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                              "parameters": {"type": "object", "properties": t["parameters"],
                                                             "required": t["required"]}}} for t in TOOLS]
CLIENT_TOOLS = {"open_tab", "web_search", "open_krypton"}


def workspace() -> Path:
    ud = users.user_dir()  # web accounts get their own private folder
    p = (ud / "workspace" if ud else Path(settings.get("agent_workspace") or ROOT / "workspace")).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe(rel: str) -> Path:
    base = workspace()
    p = (base / (rel or ".")).resolve()
    if p != base and base not in p.parents:
        raise PermissionError("That path is outside the workspace folder.")
    return p


def run_tool(name: str, args: dict, actions: list) -> str:
    try:
        if name == "open_tab":
            url = str(args.get("url", "")).strip()
            if not re.match(r"^https?://", url):
                url = "https://" + url
            actions.append({"type": "open_tab", "url": url})
            return f"Opened {url}"
        if name == "web_search":
            actions.append({"type": "web_search", "query": str(args.get("query", ""))})
            return "Search opened"
        if name == "open_krypton":
            actions.append({"type": "open_krypton", "tool": args.get("tool", "explain"), "topic": args.get("topic", "")})
            return f"Opened Krypton {args.get('tool')} for '{args.get('topic')}'"
        if name == "search_ncert":
            cls = args.get("cls")
            hits = library.search(str(args.get("query", "")), int(cls) if str(cls or "").isdigit() else None,
                                  args.get("subject") or None, None, 4)
            if not hits:
                return "No matching NCERT passages."
            return "\n\n".join(f"[Class {c['cls']} {c['subject']} — {c['book']} Ch {c['ch']} '{c['ch_title']}' p.{c['page']}]\n"
                               f"{c['text'][:900]}" for _, c in hits)
        if name == "list_files":
            p = _safe(args.get("path", "."))
            items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))[:200]
            return "\n".join(f"{'📁' if i.is_dir() else '📄'} {i.relative_to(workspace())}" for i in items) or "(empty folder)"
        if name == "read_file":
            text = _safe(args["path"]).read_text(encoding="utf-8", errors="replace")
            return text[:FILE_LIMIT] + ("\n…(truncated)" if len(text) > FILE_LIMIT else "")
        if name == "write_file":
            p = _safe(args["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(str(args.get("content", "")), encoding="utf-8")
            actions.append({"type": "file", "op": "wrote", "path": str(p.relative_to(workspace()))})
            return f"Wrote {p.name} ({len(str(args.get('content', '')))} chars)"
        if name == "edit_file":
            p = _safe(args["path"])
            text = p.read_text(encoding="utf-8")
            find = str(args.get("find", ""))
            if not find or text.count(find) == 0:
                return "Edit failed: the 'find' text was not found exactly. Read the file and try again."
            p.write_text(text.replace(find, str(args.get("replace", "")), 1), encoding="utf-8")
            actions.append({"type": "file", "op": "edited", "path": str(p.relative_to(workspace()))})
            return f"Edited {p.name}"
        if name == "get_student_info":
            return family.student_summary() + "\n" + growth.summary()
        return f"Unknown tool {name}"
    except (OSError, KeyError, ValueError, PermissionError) as e:
        return f"Tool error: {e}"


def chat(history: list[dict]) -> dict:
    t0 = time.time()
    actions, steps = [], []
    sys_prompt = SYSTEM.format(today=time.strftime("%d %B %Y"), workspace=workspace())
    lang_line = langs.instruction(langs.current_lang.get())
    if lang_line:
        sys_prompt += "\n" + lang_line.replace("LANGUAGE: Write everything", "Reply")
    msgs = [{"role": "system", "content": sys_prompt}]
    msgs += [{"role": m["role"], "content": str(m["content"])} for m in history[-16:] if m.get("role") in ("user", "assistant")]
    engine = model = None
    try:
        for _ in range(MAX_STEPS):
            msg, engine, model = chat_tools(msgs, SCHEMAS)
            if not msg["tool_calls"]:
                return _done(msg["content"], engine, model, actions, steps, t0)
            msgs.append({"role": "assistant", "content": msg["content"], "tool_calls": [
                {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["args"])}}
                for c in msg["tool_calls"]]})
            for c in msg["tool_calls"]:
                result = run_tool(c["name"], c["args"], actions)
                steps.append({"tool": c["name"], "args": {k: (str(v)[:80]) for k, v in c["args"].items()},
                              "result": result[:160]})
                msgs.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"], "content": result})
        return _done("I did several steps — tell me if you want me to continue.", engine, model, actions, steps, t0)
    except EngineError as e:
        return offline(history[-1]["content"] if history else "", str(e), t0)


def _done(text, engine, model, actions, steps, t0):
    return {"reply": text, "engine": engine, "model": model, "actions": actions, "steps": steps,
            "ms": (time.time() - t0) * 1000, "notes": []}


def offline(text: str, why: str, t0: float) -> dict:
    """No AI available: understand simple commands."""
    actions, steps = [], []
    t = text.strip()
    low = t.lower()
    m = re.match(r"^(open|go to|visit)\s+(.+)$", low)
    if m:
        site = m.group(2).strip()
        url = site if "." in site else f"{site}.com"
        reply = run_tool("open_tab", {"url": url}, actions)
    elif re.match(r"^(search|google|look up)\s+", low):
        q = re.sub(r"^(search|google|look up)\s+(for\s+)?", "", t, flags=re.I)
        reply = run_tool("web_search", {"query": q}, actions)
    elif re.match(r"^(explain|quiz|flashcards?|paper|guide)\b", low):
        tool = re.match(r"^(\w+)", low).group(1).rstrip("s") if not low.startswith("flash") else "flashcards"
        tool = {"flashcard": "flashcards"}.get(tool, tool)
        topic = re.sub(r"^\w+\s*(me\s+)?(on|about)?\s*", "", t, flags=re.I)
        reply = run_tool("open_krypton", {"tool": tool, "topic": topic}, actions)
    elif low.startswith(("list files", "ls")):
        reply = run_tool("list_files", {"path": "."}, actions)
    elif low.startswith("read "):
        reply = run_tool("read_file", {"path": t[5:].strip()}, actions)
    elif low.startswith(("my marks", "marks", "progress")):
        reply = run_tool("get_student_info", {}, actions)
    else:
        found = run_tool("search_ncert", {"query": t}, actions)
        reply = ("Here's what your NCERT books say:\n\n" + found[:1200]) if not found.startswith("No ") else \
            "I'm in offline mode, so I understand simple commands: open <site>, search <words>, explain/quiz/flashcards <topic>, list files, read <file>, my marks."
    steps.append({"tool": "offline", "args": {}, "result": "command mode"})
    return {"reply": reply, "engine": "offline", "model": "Krypton command mode", "actions": actions, "steps": steps,
            "ms": (time.time() - t0) * 1000, "notes": [n for n in why.split("; ") if n and n != "offline mode"]}
