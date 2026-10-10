"""Beautiful PDFs for Explain lessons and Flashcards, rendered by headless Chrome/Edge (handles Hindi perfectly)."""
import html
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

BROWSERS = [
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
    Path("/usr/bin/chromium"), Path("/usr/bin/chromium-browser"),   # cloud (Linux)
]

e = lambda s: html.escape(str(s or ""))

CSS = """
@page { size: A4; margin: 16mm 14mm 18mm; }
* { box-sizing: border-box; }
body { font-family: "Segoe UI", "Nirmala UI", Arial, sans-serif; color: #10231a; font-size: 11.5pt; line-height: 1.55; margin: 0; }
.head { display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 3px solid #1fbf6a; padding-bottom: 8px; margin-bottom: 14px; }
.brand { font-weight: 800; letter-spacing: .3em; color: #13a35a; font-size: 10pt; }
.gem { display: inline-block; width: 12px; height: 12px; background: linear-gradient(135deg,#b6ff3b,#18c9c2); transform: rotate(45deg); margin-right: 8px; border-radius: 2px; }
h1 { font-size: 22pt; margin: 4px 0 2px; color: #0b1a12; }
.meta { color: #5b7266; font-size: 10pt; }
.line { display: flex; gap: 12px; padding: 10px 12px; margin: 8px 0; border: 1px solid #d8eee1; border-radius: 10px; break-inside: avoid; background: #fbfffc; }
.n { flex: none; width: 26px; height: 26px; border-radius: 7px; background: #e3f9ea; color: #0f8a4a; font-weight: 800; display: flex; align-items: center; justify-content: center; }
.q { font-weight: 600; margin-bottom: 3px; }
.q:before { content: "“"; } .q:after { content: "”"; }
.ex { color: #2c4a3a; }
.box { margin: 14px 0; padding: 12px 14px; border-radius: 10px; background: linear-gradient(135deg,#f1ffe6,#e6fbf8); border: 1px solid #c9ecd6; break-inside: avoid; }
h2 { font-size: 13pt; margin: 18px 0 8px; color: #0f8a4a; }
.terms { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.term { border: 1px solid #d8eee1; border-radius: 8px; padding: 8px 10px; break-inside: avoid; }
.term b { color: #0f8a4a; }
.src { font-size: 9pt; color: #6b8277; }
.foot { margin-top: 18px; font-size: 8.5pt; color: #8aa093; text-align: center; }
/* flashcards: fold along the dashed line */
.cards { display: grid; grid-template-columns: 1fr; gap: 0; }
.card { display: grid; grid-template-columns: 1fr 1fr; border: 1.5px dashed #9ccfb2; border-radius: 0; margin: -0.75px 0; min-height: 38mm; break-inside: avoid; }
.side { padding: 10px 14px; display: flex; flex-direction: column; justify-content: center; }
.front { border-right: 1.5px dashed #9ccfb2; font-weight: 600; font-size: 12pt; }
.back { background: #f6fff9; color: #23443a; }
.tag { font-size: 8pt; letter-spacing: .15em; color: #13a35a; font-weight: 800; margin-bottom: 4px; }
.tip { font-size: 9.5pt; color: #5b7266; margin-bottom: 10px; }
"""


def _page(title: str, meta: str, body: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<div class="head"><div><div class="brand"><span class="gem"></span>KRYPTON</div><h1>{e(title)}</h1>
<div class="meta">{e(meta)}</div></div><div class="meta">{time.strftime('%d %b %Y')}</div></div>
{body}<div class="foot">Made with Krypton · NCERT study buddy · based on NCERT textbooks</div></body></html>"""


def _sources(sources: list) -> str:
    if not sources:
        return ""
    items = "".join(f"<li>{e(s.get('label'))} — page {e(s.get('page'))}</li>" for s in sources)
    return f'<h2>NCERT sources</h2><ul class="src">{items}</ul>'


def explain_html(d: dict, meta: str, sources: list) -> str:
    lines = "".join(f'<div class="line"><div class="n">{i}</div><div><div class="q">{e(l.get("text"))}</div>'
                    f'<div class="ex">{e(l.get("explanation"))}</div></div></div>'
                    for i, l in enumerate(d.get("lines", []), 1))
    body = f"<h2>Line by line</h2>{lines}"
    if d.get("summary"):
        body += f'<div class="box"><b>In short:</b> {e(d["summary"])}</div>'
    if d.get("example"):
        body += f'<div class="box"><b>Remember it like this:</b> {e(d["example"])}</div>'
    if d.get("key_terms"):
        body += '<h2>Key terms</h2><div class="terms">' + "".join(
            f'<div class="term"><b>{e(t.get("term"))}</b><br>{e(t.get("meaning"))}</div>' for t in d["key_terms"]) + "</div>"
    if d.get("check_questions"):
        body += "<h2>Check yourself</h2><ol>" + "".join(f"<li>{e(q)}</li>" for q in d["check_questions"]) + "</ol>"
    return _page(d.get("title") or "Lesson", meta, body + _sources(sources))


def flashcards_html(d: dict, meta: str, sources: list) -> str:
    cards = "".join(f'<div class="card"><div class="side front"><div class="tag">CARD {i}</div>{e(c.get("front"))}</div>'
                    f'<div class="side back"><div class="tag">ANSWER</div>{e(c.get("back"))}</div></div>'
                    for i, c in enumerate(d.get("cards", []), 1))
    body = (f'<div class="tip">✂ Cut along the dashed outline, then fold each card down the middle — question on the front, '
            f'answer on the back. {len(d.get("cards", []))} cards.</div><div class="cards">{cards}</div>')
    return _page(d.get("title") or "Flashcards", meta, body + _sources(sources))


def mindmap_html(d: dict, meta: str, sources: list) -> str:
    import mindmap_svg  # the map is redrawn here from the data, never taken from the browser
    svg = mindmap_svg.render({"center": d.get("center"), "title": d.get("title"), "branches": d.get("branches", [])}, light=True)
    svg = svg.replace('width="100%"', 'width="100%" height="128mm"', 1)  # one landscape page
    extra = f'<div style="break-before:page">{_sources(sources)}</div>' if sources else ""
    page = _page(d.get("title") or "Mind map", meta, f'<div style="margin-top:4mm">{svg}</div>{extra}')
    return page.replace("size: A4;", "size: A4 landscape;")


def render(kind: str, data: dict, meta: str, sources: list) -> bytes:
    page = {"explain": explain_html, "flashcards": flashcards_html, "mindmap": mindmap_html}[kind](data, meta, sources)
    browser = next((b for b in BROWSERS if b.exists()), None)
    if not browser:
        raise RuntimeError("Chrome or Edge is needed to make PDFs.")
    tmp = Path(tempfile.mkdtemp(prefix="krypton_pdf_"))
    try:
        src, out = tmp / "page.html", tmp / "out.pdf"
        src.write_text(page, encoding="utf-8")
        linux = [] if os.name == "nt" else ["--no-sandbox", "--disable-dev-shm-usage"]
        subprocess.run([str(browser), "--headless=new", "--disable-gpu", "--no-first-run", "--no-pdf-header-footer", *linux,
                        f"--user-data-dir={tmp / 'profile'}", f"--print-to-pdf={out}", src.as_uri()],
                       capture_output=True, timeout=90)
        if not out.exists():
            raise RuntimeError("The browser couldn't create the PDF.")
        return out.read_bytes()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
