"""Draw a radial mind map as SVG (used on screen and in the PDF). All text is escaped here."""
import html
import math

PALETTE = ["#5cff6a", "#18c9c2", "#ffd75f", "#ff8f6b", "#b98cff", "#6bb8ff", "#ff6bb5"]
W, H = 1400, 900
CX, CY = W / 2, H / 2


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines[:3]


def _size(text, size, wrap):
    lines = _wrap(text, wrap) or [""]
    return max(len(l) for l in lines) * size * 0.58 + size * 1.6, len(lines) * size * 1.25 + size * 0.9


def _hits(box, placed, pad=8):
    x, y, w, h = box
    return any(abs(x - px) < (w + pw) / 2 + pad and abs(y - py) < (h + ph) / 2 + pad for px, py, pw, ph in placed)


def _node(x, y, text, color, size, wrap, fill, weight=600, note="", text_color="#e8fff1"):
    lines = _wrap(text, wrap) or [""]
    lh = size * 1.25
    w, h = _size(text, size, wrap)
    tspans = "".join(f'<tspan x="{x:.0f}" dy="{lh if i else -(len(lines) - 1) * lh / 2 + size * 0.35:.1f}">{html.escape(l)}</tspan>'
                     for i, l in enumerate(lines))
    tip = f"<title>{html.escape(note)}</title>" if note else ""
    return (f'<g class="mm-node">{tip}<rect x="{x - w / 2:.0f}" y="{y - h / 2:.0f}" width="{w:.0f}" height="{h:.0f}" rx="{h / 2 if len(lines) == 1 else 14:.0f}" '
            f'fill="{fill}" stroke="{color}" stroke-width="2"/>'
            f'<text x="{x:.0f}" y="{y:.0f}" text-anchor="middle" font-size="{size}" font-weight="{weight}" fill="{text_color}">{tspans}</text></g>')


def render(data: dict, light: bool = False) -> str:
    bg = "#ffffff" if light else "transparent"
    card = "#f4fff6" if light else "#0f1f17"
    ink = "#0b1a12" if light else "#e8fff1"
    branches = data.get("branches", [])
    n = max(len(branches), 1)
    links, nodes = [], []
    cw, ch = _size(data.get("center") or data.get("title", ""), 26, 14)
    placed = [(CX, CY, cw, ch)]  # boxes already on the canvas, so children can step out of each other's way
    hubs = []
    for i, b in enumerate(branches):
        ang = -math.pi / 2 + i * 2 * math.pi / n
        bx, by = CX + 290 * math.cos(ang), CY + 215 * math.sin(ang)
        hubs.append((ang, bx, by))
        placed.append((bx, by, *_size(b.get("label", ""), 19, 16)))
    for i, b in enumerate(branches):
        color = PALETTE[i % len(PALETTE)]
        ang, bx, by = hubs[i]
        links.append(f'<path d="M{CX:.0f},{CY:.0f} Q{(CX + bx) / 2:.0f},{(CY + by) / 2 + 30 * math.cos(ang):.0f} {bx:.0f},{by:.0f}" '
                     f'stroke="{color}" stroke-width="5" fill="none" stroke-linecap="round" opacity=".85"/>')
        kids = b.get("children", [])
        m = len(kids)
        spread = min(math.radians(64), 2 * math.pi / n * 0.85)
        for j, c in enumerate(kids):
            a = ang + (j - (m - 1) / 2) * (spread / max(m - 1, 1)) if m > 1 else ang
            kw, kh = _size(c.get("label", ""), 15, 20)
            for step in range(12):  # walk outward until the box is clear of every other box
                r = 1 + step * 0.06
                kx, ky = CX + 520 * r * math.cos(a), CY + 350 * r * math.sin(a)
                if not _hits((kx, ky, kw, kh), placed):
                    break
            kx, ky = min(max(kx, kw / 2 + 6), W - kw / 2 - 6), min(max(ky, kh / 2 + 6), H - kh / 2 - 6)
            placed.append((kx, ky, kw, kh))
            links.append(f'<path d="M{bx:.0f},{by:.0f} Q{(bx + kx) / 2:.0f},{(by + ky) / 2:.0f} {kx:.0f},{ky:.0f}" '
                         f'stroke="{color}" stroke-width="2.2" fill="none" opacity=".6"/>')
            nodes.append(_node(kx, ky, c.get("label", ""), color, 15, 20, card, 500, c.get("note", ""), ink))
        nodes.append(_node(bx, by, b.get("label", ""), color, 19, 16, card, 700, "", ink))
    center = _node(CX, CY, data.get("center") or data.get("title", ""), "#5cff6a", 26, 14,
                   "url(#mmg)", 800, "", "#04170b")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" style="background:{bg}" '
            f'font-family="Segoe UI, Nirmala UI, Arial, sans-serif"><defs><linearGradient id="mmg" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="#b6ff3b"/><stop offset=".55" stop-color="#2ff58a"/><stop offset="1" stop-color="#18c9c2"/>'
            f'</linearGradient></defs>{"".join(links)}{"".join(nodes)}{center}</svg>')
