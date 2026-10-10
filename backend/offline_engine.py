"""No-AI engine: builds explanations, flashcards, quizzes, papers and guides straight from NCERT text."""
import random
import re
from collections import Counter

from library import library
from patterns import blueprint
from textutil import STOPWORDS, WORD_RE, sentences

DEFN = re.compile(
    r"\b(is|are|was|were)\s+(called|known as|defined as|termed|referred to as)\b|\brefers?\s+to\b|\bmeans?\b|"
    r"\b(is|are)\s+(the|a|an)\s+\w+\s+(of|which|that|in)\b|कहते हैं|कहलाते|कहलाता|को\s+\S+\s+कहते", re.I)
EXAMPLE = re.compile(r"\bfor example\b|\be\.g\.|\bsuch as\b|\bfor instance\b|उदाहरण", re.I)
CAUSE = re.compile(r"\bbecause\b|\btherefore\b|\bhence\b|\bdue to\b|\bas a result\b|\bso that\b|क्योंकि|इसलिए", re.I)
FORMULA = re.compile(r"[=×÷+]|\d+\s*(cm|m|kg|g|km|s|°C|%|N|J|W|V|Ω)\b")
QUESTION_START_SHORT = re.compile(r"^(what is|what are|define|name|give|which|who|when|list|state|write the)", re.I)
QUESTION_LONG = re.compile(r"in detail|describe|explain with|differentiate|distinguish|discuss|diagram|compare|elaborate", re.I)


def _good_sentences(chunks: list[dict]) -> list[tuple[str, dict]]:
    out, seen = [], set()
    for c in chunks:
        for s in sentences(c["text"]):
            key = re.sub(r"\W+", "", s.lower())[:80]
            if key in seen:
                continue
            seen.add(key)
            if 40 <= len(s) <= 260 and not s.endswith("?") and not re.match(r"^(fig|figure|activity|table)\b", s, re.I) \
                    and not re.search(r"\b(teacher|learners|the children|students should)\b", s, re.I):
                out.append((s, c))
    return out


def key_terms(chunks: list[dict], n: int = 40) -> list[str]:
    idf = library.index["idf"]
    counts: Counter = Counter()
    surface: dict[str, Counter] = {}
    for c in chunks:
        for w in WORD_RE.findall(c["text"]):
            lw = w.lower()
            if len(lw) < 4 or lw in STOPWORDS or lw.isdigit():
                continue
            counts[lw] += 1
            surface.setdefault(lw, Counter())[w] += 1
    scored = sorted(counts, key=lambda t: counts[t] * idf.get(t, 1.0) ** 1.5, reverse=True)
    return [surface[t].most_common(1)[0][0] for t in scored[:n]]


def _cloze_items(chunks: list[dict], terms: list[str], limit: int, rng: random.Random) -> list[dict]:
    term_rank = {t.lower(): i for i, t in enumerate(terms)}
    items = []
    for s, c in _good_sentences(chunks):
        best = None
        for w in WORD_RE.findall(s):
            r = term_rank.get(w.lower())
            if r is not None and (best is None or r < best[0]):
                best = (r, w)
        if not best:
            continue
        word = best[1]
        blanked = re.sub(rf"\b{re.escape(word)}\b", "_____", s, count=1)
        if blanked == s:
            continue
        score = (3 if DEFN.search(s) else 0) + (1 if len(s) < 180 else 0) - best[0] / 20
        items.append({"sentence": s, "blank": blanked, "answer": word, "chunk": c, "score": score})
    items.sort(key=lambda x: x["score"], reverse=True)
    seen, out = set(), []
    for it in items:
        if it["answer"].lower() in seen:
            continue
        seen.add(it["answer"].lower())
        out.append(it)
        if len(out) >= limit:
            break
    rng.shuffle(out)
    return out


def _distractors(answer: str, pool: list[str], sentence: str, rng: random.Random) -> list[str]:
    cands = [t for t in pool if t.lower() != answer.lower() and t.lower() not in sentence.lower()
             and answer.lower() not in t.lower() and t.lower() not in answer.lower()]
    cands.sort(key=lambda t: abs(len(t) - len(answer)))
    picks = rng.sample(cands[:8], min(3, len(cands[:8])))
    fillers = ["None of these", "All of these", "Cannot be determined"]
    while len(picks) < 3:
        picks.append(fillers[len(picks)])
    return [p if not answer[:1].isupper() else p[:1].upper() + p[1:] for p in picks]


def _src(c: dict) -> str:
    return f"NCERT Class {c['cls']} {c['book']}, Ch {c['ch']} ({c['ch_title']}), p. {c['page']}"


def make_mcqs(chunks: list[dict], count: int, seed=None) -> list[dict]:
    rng = random.Random(seed)
    terms = key_terms(chunks, 60)
    qs = []
    for it in _cloze_items(chunks, terms, count, rng):
        opts = _distractors(it["answer"], terms, it["sentence"], rng) + [it["answer"]]
        rng.shuffle(opts)
        qs.append({"question": f"Fill in the blank: {it['blank']}", "options": opts,
                   "answer_index": opts.index(it["answer"]),
                   "explanation": f"“{it['sentence']}” — {_src(it['chunk'])}"})
    return qs


# ---------------- features ----------------
def explain(query: str, chunks: list[dict]) -> dict:
    top = chunks[:3]
    terms = key_terms(chunks, 15)
    tset = {t.lower() for t in terms}
    lines = []
    for s, c in _good_sentences(top)[:12]:
        found = [w for w in dict.fromkeys(WORD_RE.findall(s)) if w.lower() in tset][:3]
        if DEFN.search(s):
            note = f"Definition — this line tells you what {found[0] if found else 'the term'} means. Learn it word for word for 1–2 mark questions."
        elif EXAMPLE.search(s):
            note = "Example — connects the idea to something real. Use an example like this in 3-mark answers."
        elif CAUSE.search(s):
            note = "Cause and effect — notice the reason being given. 'Why' questions in exams come from lines like this."
        elif FORMULA.search(s):
            note = "Numbers/formula — note the quantities and units carefully."
        else:
            note = "Key point" + (f" — focus on: {', '.join(found)}." if found else ".")
        lines.append({"text": s, "explanation": note})
    key = []
    for t in terms[:8]:
        d = next((s for s, _ in _good_sentences(chunks) if re.search(rf"\b{re.escape(t)}\b", s) and DEFN.search(s)), None)
        if d:
            key.append({"term": t, "meaning": d})
    title = query.strip().capitalize() if query.strip() else (top[0]["ch_title"] if top else "Topic")
    summary = " ".join(s for s, _ in _good_sentences(top[:1])[:2])
    return {"title": title, "lines": lines, "summary": summary, "key_terms": key[:6],
            "example": "", "check_questions": [q["question"] for q in make_mcqs(top, 2)]}


TERM_AFTER = re.compile(r"\b(?:is|are)\s+(?:called|known as|termed|referred to as)\s+(?:the\s+|a\s+|an\s+)?"
                        r"([A-Za-z][\w\s'-]{2,40}?)(?=\s+(?:of|in|for|and|which|that)\b|[.,;:(]|$)", re.I)
TERM_BEFORE = re.compile(r"^(?:The\s+|A\s+|An\s+)?([A-Za-z][\w\s'-]{2,40}?)\s+(?:is|are)\s+(?:defined as|the\s+\w+\s+of|"
                         r"a\s+\w+\s+(?:of|which|that)|an?\s+\w+\s+\w+\s+(?:of|which|that))\b|"
                         r"^(?:The\s+)?([A-Za-z][\w\s'-]{2,40}?)\s+(?:refers? to|means?)\b", re.I)


def defined_term(sentence: str) -> str | None:
    m = TERM_AFTER.search(sentence)
    if m:
        return m.group(1).strip()
    m = TERM_BEFORE.search(sentence)
    if m:
        t = (m.group(1) or m.group(2) or "").strip()
        if t and t.split()[0].lower() not in ("this", "these", "it", "they", "that", "there", "such", "we", "he", "she"):
            return t
    return None


def flashcards(chunks: list[dict], count: int) -> dict:
    rng = random.Random()
    terms = key_terms(chunks, 60)
    cards = []
    for s, c in _good_sentences(chunks):
        t = defined_term(s) if DEFN.search(s) else None
        if t and len(t.split()) <= 5 and all(t.lower() != x["term"].lower() for x in cards):
            cards.append({"term": t, "front": f"Define: {t}", "back": s, "source": _src(c)})
        if len(cards) >= count:
            break
    for it in _cloze_items(chunks, terms, count * 2, rng):
        if len(cards) >= count:
            break
        if any(it["answer"].lower() == x["term"].lower() for x in cards):
            continue
        cards.append({"term": it["answer"], "front": it["blank"], "back": it["answer"] + " — " + it["sentence"],
                      "source": _src(it["chunk"])})
    return {"title": chunks[0]["ch_title"] if chunks else "Flashcards",
            "cards": [{"front": c["front"], "back": c["back"]} for c in cards[:count]]}


def quiz(chunks: list[dict], count: int) -> dict:
    return {"title": chunks[0]["ch_title"] if chunks else "Quiz", "questions": make_mcqs(chunks, count)}


def _classify(q: str) -> str:
    if QUESTION_LONG.search(q) or len(q) > 150:
        return "long"
    if QUESTION_START_SHORT.match(q) and len(q) < 110:
        return "short"
    return "medium"


def paper(cls: int, subject: str, chapters: list[dict], chunks: list[dict], paper_type: str) -> dict:
    bp = blueprint(cls, paper_type)
    rng = random.Random()
    pools = {"short": [], "medium": [], "long": []}
    for ch in chapters:
        for q in ch["exercises"]:
            pools[_classify(q)].append((q, ch))
    for p in pools.values():
        rng.shuffle(p)
    pool = [library.chunks[i] for ch in chapters for i in library.by_chapter[(ch["code"], ch["ch"])]]
    rng.shuffle(pool)
    defined = list(dict.fromkeys(t for s, _ in _good_sentences(chunks + pool[:150]) if DEFN.search(s)
                                 for t in [defined_term(s)] if t and 1 <= len(t.split()) <= 4))
    terms = defined + [t for t in key_terms(chunks, 50) if len(t) >= 6]
    templates = {
        "short": ["Define the term '{t}'.", "What do you understand by '{t}'?", "Write two points about '{t}'."],
        "medium": ["Explain '{t}' with a suitable example.", "Write a short note on '{t}'.", "Why is '{t}' important? Give reasons."],
        "long": ["Describe '{t}' in detail with examples.", "Explain '{t}' in detail. Draw a diagram if necessary."],
    }
    sections, answers, used_terms = [], [], set()
    # Topic chunks first, then the rest of the selected chapters, so Section A always has enough MCQs.
    mcq_bank = make_mcqs(chunks, 40)
    need = sum(n for _, _, _, n, k in bp["sections"] if k == "mcq")
    if len(mcq_bank) < need and pool:
        seen = {m["question"] for m in mcq_bank}
        mcq_bank = [m for m in make_mcqs(pool[:250], need * 2) if m["question"] not in seen] + mcq_bank
    for sec, heading, marks, n, kind in bp["sections"]:
        qs = []
        for _ in range(n):
            if kind == "mcq":
                if not mcq_bank:
                    break
                m = mcq_bank.pop()
                qs.append({"q": m["question"], "options": m["options"], "marks": marks,
                           "answer": m["options"][m["answer_index"]]})
            elif kind == "case":
                c = rng.choice([c for c in chunks if 350 < len(c["text"]) < 1200] or chunks)
                subs = make_mcqs([c], 2)
                parts = [{"q": s["question"] + "  (" + " / ".join(s["options"]) + ")", "marks": 1,
                          "answer": s["options"][s["answer_index"]]} for s in subs]
                t = next((x for x in key_terms([c], 5)), "the main idea")
                parts.append({"q": f"Based on the passage, explain the significance of '{t}'.", "marks": marks - len(parts),
                              "answer": f"See passage — {_src(c)}"})
                qs.append({"q": "Read the passage and answer the questions that follow.",
                           "passage": re.sub(r"\s+", " ", c["text"])[:900], "marks": marks, "subparts": parts,
                           "answer": _src(c)})
            else:
                if pools[kind]:
                    q, ch = pools[kind].pop()
                    qs.append({"q": q, "marks": marks,
                               "answer": f"NCERT exercise — Class {ch['cls']} {ch['book']}, Ch {ch['ch']} ({ch['title']})"})
                else:
                    t = next((x for x in terms if x.lower() not in used_terms), None)
                    if not t:
                        break
                    used_terms.add(t.lower())
                    d = next((s for s, _ in _good_sentences(chunks) if re.search(rf"\b{re.escape(t)}\b", s)), "")
                    qs.append({"q": rng.choice(templates[kind]).format(t=t), "marks": marks,
                               "answer": d or "Refer to the textbook chapter."})
        sections.append({"name": f"Section {sec}", "title": heading, "marks_each": marks, "questions": qs})
    subj_label = subject or (chapters[0]["subject"] if chapters else "")
    return {"title": f"{'Chapter Test' if paper_type == 'chapter' else 'Sample Question Paper'} — {subj_label}",
            "class": cls, "subject": subj_label, "time": bp["time"],
            "max_marks": sum(q["marks"] for s in sections for q in s["questions"]),
            "instructions": bp["instructions"], "sections": sections}


def mindmap(query: str, chunks: list[dict]) -> dict:
    """No-AI mind map: defined terms become branches, their defining sentences become the children."""
    sents = _good_sentences(chunks)
    branches, used = [], set()
    for s, c in sents:
        t = defined_term(s) if DEFN.search(s) else None
        if not t or t.lower() in used or len(t.split()) > 4:
            continue
        used.add(t.lower())
        related = [x for x, _ in sents if x != s and re.search(rf"\b{re.escape(t.split()[-1])}\b", x, re.I)][:2]
        kids = [{"label": _phrase(x), "note": x} for x in [s] + related]
        branches.append({"label": _nice(t), "children": kids})
        if len(branches) >= 6:
            break
    for t in key_terms(chunks, 20):  # top up with frequent key terms
        if len(branches) >= 5:
            break
        if t.lower() in used:
            continue
        used.add(t.lower())
        hits = [x for x, _ in sents if re.search(rf"\b{re.escape(t)}\b", x, re.I)][:3]
        if len(hits) >= 2:
            branches.append({"label": _nice(t), "children": [{"label": _phrase(x), "note": x} for x in hits]})
    branches = [b for b in branches if len(b["children"]) >= 2] or branches
    center = query.strip().title() if query.strip() else (chunks[0]["ch_title"] if chunks else "Topic")
    return {"title": center, "center": center[:30], "branches": branches}


def _nice(term: str) -> str:
    return term[:1].upper() + term[1:].lower() if term.isupper() or term.islower() else term


def _phrase(sentence: str, words: int = 5) -> str:
    w = [x for x in re.findall(r"[\wऀ-ॿ'-]+", sentence) if x.lower() not in STOPWORDS]
    return " ".join(w[:words]) or sentence[:30]


def guide(chapters: list[dict], days: int, goal: str) -> dict:
    chapters = chapters[:14]
    days = max(1, min(days, 30))
    plan = [{"day": d + 1, "focus": "", "tasks": []} for d in range(days)]
    study_days = max(1, days - 1) if days > 2 else days
    for i, ch in enumerate(chapters):
        d = plan[i % study_days]
        terms = key_terms([library.chunks[j] for j in library.by_chapter[(ch["code"], ch["ch"])]], 6)
        d["focus"] = (d["focus"] + " + " if d["focus"] else "") + f"Ch {ch['ch']}: {ch['title']}"
        d["tasks"] += [f"Read Ch {ch['ch']} '{ch['title']}' ({ch['pages']} pages) — underline definitions",
                       f"Make Krypton flashcards on: {', '.join(terms[:5])}" if terms else "Make flashcards of key terms",
                       f"Solve the NCERT exercise ({len(ch['exercises'])} questions)" if ch["exercises"] else "Write 5 questions of your own and answer them",
                       "Take a 10-question Krypton quiz; re-read anything you got wrong"]
    if days > 2:
        plan[-1]["focus"] = "Revision + full practice paper"
        plan[-1]["tasks"] = ["Revise all flashcards (shuffle mode)", "Attempt a Krypton question paper in exam time",
                             "Check answers with the answer key and note weak topics"]
    plan = [p for p in plan if p["tasks"]]
    return {"title": f"Study plan — {goal}" if goal else "Your study plan",
            "overview": f"{len(chapters)} chapter(s) over {days} day(s). Each day: read → flashcards → exercise → quiz.",
            "key_topics": [f"Ch {c['ch']}: {c['title']}" for c in chapters],
            "days": plan,
            "tips": ["Study in 25-minute focus blocks with 5-minute breaks (Krypton blocks scrolling for you).",
                     "Learn NCERT definitions exactly — 1 and 2 mark answers come straight from the textbook.",
                     "For 3 and 5 mark answers write in points, underline keywords and add a diagram/example.",
                     "Solve every in-text and end-of-chapter question — CBSE papers are built from them.",
                     "Revise flashcards the next day and again after 3 days (spaced repetition)."],
            "exam_strategy": ["Read the whole paper in the first 10 minutes.",
                              "Attempt the sections you are most confident in first.",
                              "Keep 15 minutes at the end to revise answers."]}
