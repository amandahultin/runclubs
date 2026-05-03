"""Split events.html into city-specific event pages.

Reads the pre-generated events.html, extracts the embedded events JSON,
filters by city, and renders each city page using the existing city generators'
render_html functions.  No Google Sheets API calls are made.

Usage:
    python split_city_events.py          # reads events.html in cwd
    python split_city_events.py path/to/events.html
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent


def extract_events(source: Path) -> list[dict]:
    text = source.read_text(encoding="utf-8")
    m = re.search(r"const events = (\[[\s\S]*?\]);", text)
    if not m:
        raise ValueError(f"Could not find 'const events = [...]' in {source}")
    return json.loads(m.group(1))


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "events.html"
    if not source.exists():
        print(f"ERROR: {source} not found — run generate_running_events.py first")
        return 1

    all_events = extract_events(source)
    generated_at = datetime.now(timezone.utc).strftime("%-d %B %Y")

    from generate_stockholm_events import render_html as render_stockholm
    from generate_goteborg_events import render_html as render_goteborg
    from generate_malmo_events import render_html as render_malmo

    cities = [
        ("Stockholm", ROOT / "stockholm-running-events.html", render_stockholm),
        ("Göteborg",  ROOT / "goteborg-running-events.html",  render_goteborg),
        ("Malmö",     ROOT / "malmo-running-events.html",     render_malmo),
    ]

    for city_name, out_path, render_fn in cities:
        city_events = [e for e in all_events if e.get("city") == city_name]
        city_events.sort(key=lambda x: (x.get("date") or "9999", x.get("club") or ""))
        html = render_fn(city_events, generated_at)
        out_path.write_text(html, encoding="utf-8")
        print(f"  ✓ {out_path.name} ({len(city_events)} events)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
