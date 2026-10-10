"""The good-looking terminal: banner, boot checks and live request log."""
import sys
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import users

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (ValueError, OSError):
        pass

console = Console(highlight=False)

LOGO = r"""
 ██╗  ██╗██████╗ ██╗   ██╗██████╗ ████████╗ ██████╗ ███╗   ██╗
 ██║ ██╔╝██╔══██╗╚██╗ ██╔╝██╔══██╗╚══██╔══╝██╔═══██╗████╗  ██║
 █████╔╝ ██████╔╝ ╚████╔╝ ██████╔╝   ██║   ██║   ██║██╔██╗ ██║
 ██╔═██╗ ██╔══██╗  ╚██╔╝  ██╔═══╝    ██║   ██║   ██║██║╚██╗██║
 ██║  ██╗██║  ██║   ██║   ██║        ██║   ╚██████╔╝██║ ╚████║
 ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝        ╚═╝    ╚═════╝ ╚═╝  ╚═══╝"""

GRADIENT = ["#b6ff3b", "#8dff4f", "#5cff6a", "#2ff58a", "#1fe0a8", "#18c9c2"]

ENGINE_STYLE = {
    "groq": ("⚡ GROQ", "bold black on #f55036"),
    "local": ("🖥  LOCAL", "bold black on #5cff6a"),
    "offline": ("📘 OFFLINE", "bold black on #8ab4ff"),
}

FEATURE_ICON = {
    "explain": "🧠", "flashcards": "🃏", "quiz": "❓", "paper": "📝",
    "guide": "🧭", "mindmap": "🗺 ", "challenge": "🔐", "verify": "✅", "lock": "🔒",
    "unlock": "🔓", "settings": "⚙️ ",
}


def banner(subtitle: str = "NCERT study buddy · Classes 1–10 · focus guard"):
    console.print()
    for line, color in zip(LOGO.strip("\n").splitlines(), GRADIENT):
        console.print(Text(line, style=f"bold {color}"))
    console.print(Text(f"   ◆ {subtitle}", style="italic #9fb3a8"))
    console.print()


def step(label: str, ok: bool | None, detail: str = ""):
    with console.status(f"[#9fb3a8]checking {label.lower()}…", spinner="dots", spinner_style="#5cff6a"):
        time.sleep(0.35)
    mark = {True: "[bold #5cff6a]✔[/]", False: "[bold #ff5f5f]✘[/]", None: "[bold #ffd75f]●[/]"}[ok]
    console.print(f"  {mark} [bold]{label:<18}[/] [#9fb3a8]{detail}[/]")


def status_panel(rows: list[tuple[str, str]], url: str):
    t = Table.grid(padding=(0, 2))
    t.add_column(style="#7fd9a8", justify="right")
    t.add_column(style="bold white")
    for k, v in rows:
        t.add_row(k, v)
    console.print()
    console.print(Panel(t, title="[bold #5cff6a]KRYPTON ONLINE[/]", subtitle=f"[#9fb3a8]{url}[/]",
                        border_style="#2ff58a", padding=(1, 3)))
    console.print("  [#9fb3a8]Live activity ↓   (Ctrl+C to stop)[/]\n")


def log_event(feature: str, engine: str | None, detail: str, ms: float | None = None, note: str = ""):
    ts = time.strftime("%H:%M:%S")
    icon = FEATURE_ICON.get(feature, "•")
    line = Text()
    line.append(f"  {ts} ", style="#5f6f66")
    uid = users.current_user.get()
    if uid:  # web account doing this
        line.append(f"@{users.info(uid).get('username')} ", style="bold #18c9c2")
    line.append(f"{icon} {feature.upper():<10} ", style="bold #e8fff1")
    if engine:
        label, style = ENGINE_STYLE.get(engine, (engine.upper(), "bold"))
        line.append(f" {label} ", style=style)
        line.append(" ")
    line.append(detail, style="#cfe9da")
    if ms is not None:
        line.append(f"  {ms/1000:.1f}s", style="bold #ffd75f")
    console.print(line)
    if note:
        console.print(f"             [#ffaf5f]↳ {note}[/]")
