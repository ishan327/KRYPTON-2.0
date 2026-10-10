"""Turn downloaded NCERT PDFs into searchable chunks, chapter metadata and a BM25 index."""
import json
import math
import pickle
import re
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed

from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

from config import BOOKS_DIR, CATALOG_FILE, INDEX_DIR
from textutil import clean_page, tokenize
from ui import console

CHUNK_CHARS = 1100
EXERCISE_HEAD = re.compile(
    r"^\s*(exercises?|questions|let us reflect|think and answer|let us discuss|check your progress|"
    r"what you have learnt|let us do|reflect|let'?s practise|abhyas|अभ्यास|प्रश्न-अभ्यास|प्रश्न अभ्यास)\s*:?\s*$", re.I)
NUMBERED = re.compile(r"^\s*(?:Q\.?\s*)?(\d{1,2})[.)]\s+(.{8,})$")


def chapter_title(first_page_text: str, fallback: str) -> str:
    for line in first_page_text.splitlines()[:25]:
        s = line.strip()
        if len(s) < 4 or len(s) > 70 or not re.search(r"[A-Za-zऀ-ॿ]{3}", s):
            continue
        if re.fullmatch(r"(chapter|unit|lesson|अध्याय|पाठ)\s*[\dIVX]*", s, re.I):
            continue
        if re.search(r"reprint|ncert|rationalised|\.indd", s, re.I):
            continue
        return s.title() if s.isupper() else s
    return fallback


SKIP_TITLE = re.compile(r"^(chapter|unit|lesson|अध्याय|पाठ|इकाई)\s*[\dIVX]*[:.]?$|reprint|rationalised|ncert|\.indd", re.I)


def big_font_title(doc, book_title: str) -> str | None:
    """Chapter titles are set in the largest font on the opening page."""
    for pno in range(min(2, len(doc))):
        lines = []
        for block in doc[pno].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = "".join(s["text"] for s in line["spans"]).strip()
                size = max((s["size"] for s in line["spans"]), default=0)
                if len(text) >= 3 and re.search(r"[A-Za-zऀ-ॿ]{3}", text) and not SKIP_TITLE.search(text) \
                        and text.lower() != book_title.lower():
                    lines.append((size, line["bbox"][1], text))
        if not lines:
            continue
        top = max(s for s, _, _ in lines)
        if top < 13:
            continue
        picked = [t for s, _, t in sorted((l for l in lines if l[0] >= top * 0.92), key=lambda l: l[1])][:2]
        title = re.sub(r"\s+", " ", " ".join(picked)).strip(" :-–")
        title = re.sub(r"^(let us (read|sing|speak|listen|write|do)|मिलकर पढ़िए|सुनें कहानी|पढ़ें)\s+(?=\S)", "", title, flags=re.I)
        if len(title) > 50 and re.search(r"[.।]", title[:50]):
            title = re.split(r"(?<=[.।])\s", title)[0]
        if 3 <= len(title) <= 90:
            return title.title() if title.isupper() else title
    return None


HEADS = {"exercises", "exercise", "questions", "letusreflect", "thinkandanswer", "letusdiscuss", "checkyourprogress",
         "reflect", "letspractise", "letuspractise", "अभ्यास", "प्रश्नअभ्यास", "प्रश्नाभ्यास"}
BARE_NUMBER = re.compile(r"^\s*(?:Q\.?\s*)?(\d{1,2})[.)]\s*$")


QUESTION_LIKE = re.compile(r"\?\s*$|^(why|what|how|when|where|which|who|explain|describe|define|name|draw|find|state|give|"
                           r"list|write|show|calculate|prove|compare|distinguish|differentiate|discuss|identify|"
                           r"classify|suggest|solve|mention|क्या|क्यों|कैसे|लिखिए|बताइए|समझाइए)\b", re.I)


def extract_exercises(lines: list[str]) -> list[str]:
    found = _numbered_items(lines, needs_heading=True)
    if len(found) < 3:  # heading is an image in many books: keep numbered items that read like questions
        found = [q for q in _numbered_items(lines, needs_heading=False) if QUESTION_LIKE.search(q)]
    return found


def _numbered_items(lines: list[str], needs_heading: bool) -> list[str]:
    out, active, current = [], not needs_heading, None
    for line in lines:
        norm = re.sub(r"[^a-zऀ-ॿ]", "", line.lower())
        if norm in HEADS or EXERCISE_HEAD.match(line):
            active = True
            continue
        if not active:
            continue
        m = NUMBERED.match(line)
        if m or BARE_NUMBER.match(line):
            if current:
                out.append(current)
            current = m.group(2).strip() if m else ""
        elif current is not None and len(current) < 400 and not line.isupper():
            current = (current + " " + line.strip()).strip()
    if current:
        out.append(current)
    cleaned = []
    junk = re.compile(r"\s(Activity \d|We (will|shall|have|are)\b|In this (chapter|section)|Fig\.|\b(\d+\.\d+\s+){2}|n [A-Z])")
    for q in out:
        q = re.sub(r"\s+", " ", q).strip()
        m = junk.search(q)
        if m:
            q = q[:m.start()].strip()
        if "?" in q and not re.search(r"\(i+\)", q[q.rfind("?"):]):
            q = q[:q.rfind("?") + 1]
        if 12 <= len(q) <= 450 and q not in cleaned:
            cleaned.append(q)
    return cleaned[:60]


def process_book(book: dict) -> tuple[list[dict], list[dict]]:
    import pymupdf as fitz  # imported in the worker process

    code = book["code"]
    folder = BOOKS_DIR / code
    chunks, chapters = [], []
    pdfs = sorted(folder.glob("*.pdf"))
    for pdf in pdfs:
        m = re.fullmatch(re.escape(code) + r"(\d{2})", pdf.stem.lower())
        if not m:
            continue  # prelims, answers, appendices
        ch = int(m.group(1))
        try:
            doc = fitz.open(pdf)
        except Exception:
            continue
        header = re.compile(rf"^\s*(\d+\s*)?{re.escape(book['title'].split('(')[0].strip())}(\s*\d+)?\s*$", re.I)
        pages = [clean_page("\n".join(l for l in p.get_text("text").splitlines() if not header.match(l))) for p in doc]
        try:
            title = big_font_title(doc, book["title"])
        except Exception:
            title = None
        doc.close()
        if not any(pages):
            continue
        title = title or chapter_title(pages[0], f"Chapter {ch}")
        all_lines = [l for p in pages for l in p.splitlines()]
        chapters.append({"code": code, "cls": book["cls"], "subject": book["subject"], "book": book["title"],
                         "ch": ch, "title": title, "pages": len(pages),
                         "exercises": extract_exercises(all_lines)})
        for pno, text in enumerate(pages, start=1):
            paras = [p.strip() for p in re.split(r"\n(?=[A-Zऀ-ॿ•\d])", text) if p.strip()]
            buf = ""
            for para in paras:
                if len(buf) + len(para) > CHUNK_CHARS and len(buf) > 200:
                    chunks.append(_chunk(book, ch, title, pno, buf))
                    buf = ""
                buf = f"{buf}\n{para}" if buf else para
            if len(buf) > 60:
                chunks.append(_chunk(book, ch, title, pno, buf))
    return chunks, chapters


def _chunk(book, ch, title, page, text):
    return {"code": book["code"], "cls": book["cls"], "subject": book["subject"], "book": book["title"],
            "ch": ch, "ch_title": title, "page": page, "text": re.sub(r"[ \t]+", " ", text).strip()}


def build_index(chunks: list[dict]) -> dict:
    postings = defaultdict(list)
    lengths = []
    for i, c in enumerate(chunks):
        toks = tokenize(c["text"] + " " + c["ch_title"])
        lengths.append(len(toks))
        for term, tf in Counter(toks).items():
            postings[term].append((i, tf))
    n = len(chunks)
    idf = {t: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in postings.items()}
    return {"postings": dict(postings), "lengths": lengths, "avgdl": sum(lengths) / max(n, 1), "idf": idf}


def run(workers: int = 6):
    books = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    books = [b for b in books if (BOOKS_DIR / b["code"]).exists()]
    all_chunks, all_chapters = [], []
    cols = [SpinnerColumn(style="#5cff6a"), TextColumn("[bold]{task.description}"),
            BarColumn(complete_style="#5cff6a"), MofNCompleteColumn()]
    with Progress(*cols, console=console) as progress:
        task = progress.add_task("Reading textbooks", total=len(books))
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(process_book, b): b for b in books}
            for fut in as_completed(futs):
                b = futs[fut]
                try:
                    chunks, chapters = fut.result()
                    all_chunks += chunks
                    all_chapters += chapters
                except Exception as e:
                    console.print(f"  [#ffaf5f]⚠ {b['code']} skipped: {e}[/]")
                progress.update(task, advance=1, description=f"Reading Class {b['cls']} {b['title'][:30]}")
    all_chunks.sort(key=lambda c: (c["cls"], c["code"], c["ch"], c["page"]))
    all_chapters.sort(key=lambda c: (c["cls"], c["subject"], c["code"], c["ch"]))
    with console.status("[bold #5cff6a]Building the search index…"):
        index = build_index(all_chunks)
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        with open(INDEX_DIR / "library.pkl", "wb") as f:
            pickle.dump({"chunks": all_chunks, "chapters": all_chapters, "index": index}, f,
                        protocol=pickle.HIGHEST_PROTOCOL)
    n_ex = sum(len(c["exercises"]) for c in all_chapters)
    console.print(f"  [#5cff6a]✔[/] Indexed [bold]{len(all_chunks):,}[/] passages from [bold]{len(all_chapters)}[/] "
                  f"chapters · [bold]{n_ex:,}[/] exercise questions found")


if __name__ == "__main__":
    run()
