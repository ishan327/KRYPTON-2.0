"""One-time setup: icons → download NCERT books → build the search index."""
import argparse

import download_ncert
import ingest
import make_icons
from ui import banner, console

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--skip-download", action="store_true")
    p.add_argument("--hindi-medium", action="store_true")
    a = p.parse_args()
    banner("first-time setup")
    make_icons.run()
    console.print("  [#5cff6a]✔[/] Extension icons drawn")
    if not a.skip_download:
        download_ncert.run(a.hindi_medium)
    ingest.run()
    console.print("\n  [bold #5cff6a]Setup complete.[/] Run [bold]start_krypton.bat[/] to launch.\n")
