"""Read the official NCERT textbook catalogue and download the books (classes 1-10)."""
import json
import re
import shutil
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from rich.progress import (BarColumn, DownloadColumn, Progress, SpinnerColumn,
                           TextColumn, TimeRemainingColumn, TransferSpeedColumn)

from config import BOOKS_DIR, CATALOG_FILE, DATA
from ui import console

CATALOG_URL = "https://ncert.nic.in/textbook.php"
PDF_BASE = "https://ncert.nic.in/textbook/pdf/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KryptonStudyBuddy/1.0"}

# Language-of-instruction subjects are always kept, even when their code says "Hindi medium".
LANGUAGE_SUBJECTS = {"hindi", "sanskrit"}
SKIP_SUBJECTS = {"urdu"}


def fetch_catalog() -> list[dict]:
    for attempt in range(5):
        try:
            html = requests.get(CATALOG_URL, headers=HEADERS, timeout=90).text
            break
        except requests.RequestException:
            if attempt == 4:
                raise
            time.sleep(3 + attempt * 3)
    js = html[html.find("function change1"):]
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    js = "\n".join(l for l in js.splitlines() if not l.strip().startswith("//"))
    cond = re.compile(r'tclass\.value\s*==\s*(\d+)\)\s*&&\s*\(document\.test\.tsubject\.options\[sind\]\.text\s*==\s*"([^"]+)"\)')
    matches = list(cond.finditer(js))
    books, seen = [], set()
    for i, m in enumerate(matches):
        cls, subject = int(m.group(1)), m.group(2).strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(js)
        block = js[m.end():end]
        nxt = block.find("function ")
        if nxt != -1:
            block = block[:nxt]
        titles = dict(re.findall(r'tbook\.options\[(\d+)\]\.text\s*=\s*["\']([^"\']*)["\']', block))
        for idx, code, lo, hi in re.findall(
                r'tbook\.options\[(\d+)\]\.value\s*=\s*["\']textbook\.php\?([a-z]+\d)=(\d+)-(\d+)["\']', block):
            if not 1 <= cls <= 10 or code in seen:
                continue
            seen.add(code)
            books.append({"code": code, "cls": cls, "subject": subject,
                          "title": titles.get(idx, code).strip(), "chapters": int(hi)})
    return books


def wanted(book: dict, hindi_medium: bool) -> bool:
    code, subj = book["code"], book["subject"].lower()
    if subj in SKIP_SUBJECTS or not re.fullmatch(r"[a-j][eh][a-z]{2}\d", code):
        return False  # regional-language editions use longer codes
    if code[1] == "h" and not hindi_medium and subj not in LANGUAGE_SUBJECTS:
        return False
    return True


def _get(url: str, dest, progress=None, task=None) -> bool:
    for attempt in range(3):
        try:
            with requests.get(url, headers=HEADERS, stream=True, timeout=(20, 60)) as r:
                if r.status_code == 404:
                    return False
                r.raise_for_status()
                total = int(r.headers.get("Content-Length", 0))
                if progress and task is not None and total:
                    progress.update(task, total=total, completed=0)
                tmp = dest.with_suffix(dest.suffix + ".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        f.write(chunk)
                        if progress and task is not None:
                            progress.advance(task, len(chunk))
                tmp.replace(dest)
                return True
        except requests.RequestException:
            time.sleep(2 + attempt * 3)
    return False


def download_book(book: dict, progress, task) -> str:
    code = book["code"]
    progress.update(task, visible=True)
    out = BOOKS_DIR / code
    missing = [ch for ch in range(1, book["chapters"] + 1) if not (out / f"{code}{ch:02d}.pdf").exists()]
    if not missing:
        progress.update(task, total=1, completed=1)
        return "cached"
    out.mkdir(parents=True, exist_ok=True)
    zpath = BOOKS_DIR / f"{code}.zip"
    if len(missing) == book["chapters"] and _get(f"{PDF_BASE}{code}dd.zip", zpath, progress, task):
        try:
            with zipfile.ZipFile(zpath) as z:
                for name in z.namelist():
                    if name.lower().endswith(".pdf"):
                        with z.open(name) as src, open(out / name.split("/")[-1].lower(), "wb") as dst:
                            shutil.copyfileobj(src, dst)
            zpath.unlink(missing_ok=True)
            return "zip"
        except zipfile.BadZipFile:
            zpath.unlink(missing_ok=True)
    # Fallback / top-up: chapter-by-chapter PDFs
    got = 0
    for ch in range(1, book["chapters"] + 1):
        dest = out / f"{code}{ch:02d}.pdf"
        if dest.exists() or _get(f"{PDF_BASE}{code}{ch:02d}.pdf", dest):
            got += 1
    progress.update(task, total=1, completed=1)
    return f"{got} chapters" if got else "failed"


def run(hindi_medium: bool = False, workers: int = 2) -> list[dict]:
    DATA.mkdir(parents=True, exist_ok=True)
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    if CATALOG_FILE.exists() and time.time() - CATALOG_FILE.stat().st_mtime < 7 * 86400 and not hindi_medium:
        all_books = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    else:
        with console.status("[bold #5cff6a]Reading the NCERT catalogue…"):
            all_books = fetch_catalog()
    books = [b for b in all_books if wanted(b, hindi_medium)]
    core = ("science", "math", "social", "english", "hindi", "world around", "environmental")
    books.sort(key=lambda b: (-b["cls"], next((i for i, c in enumerate(core) if c in b["subject"].lower()), 9)))
    CATALOG_FILE.write_text(json.dumps(books, indent=1, ensure_ascii=False), encoding="utf-8")
    console.print(f"  [#5cff6a]✔[/] Found [bold]{len(books)}[/] textbooks for classes 1–10 "
                  f"[#9fb3a8](of {len(all_books)} listed)[/]")

    columns = [SpinnerColumn(style="#5cff6a"), TextColumn("[bold]{task.description:<38}"),
               BarColumn(complete_style="#5cff6a", finished_style="#2ff58a"),
               DownloadColumn(), TransferSpeedColumn(), TimeRemainingColumn()]
    results = {}
    with Progress(*columns, console=console, transient=False) as progress:
        overall = progress.add_task("[#5cff6a]ALL BOOKS", total=len(books))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {}
            for b in books:
                label = f"Class {b['cls']} · {b['title'][:26]}"
                task = progress.add_task(label, total=None, visible=False)
                futs[pool.submit(download_book, b, progress, task)] = (b, task)
            for fut in as_completed(futs):
                b, task = futs[fut]
                try:
                    results[b["code"]] = fut.result()
                except Exception as e:  # keep going on one bad book
                    results[b["code"]] = f"failed: {e}"
                progress.update(task, visible=False)
                progress.advance(overall)
    failed = [c for c, r in results.items() if str(r).startswith("failed")]
    if failed:
        console.print(f"  [#ffaf5f]⚠ Could not download: {', '.join(failed)}[/]")
    return books


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--hindi-medium", action="store_true", help="also download Hindi-medium editions")
    p.add_argument("--workers", type=int, default=2)  # NCERT throttles parallel connections
    a = p.parse_args()
    run(a.hindi_medium, a.workers)
