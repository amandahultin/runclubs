"""inject_tracker.py

Adds <script src="/tracker.js" defer></script> before </body> in every
public HTML page. Idempotent — running it twice makes no change the second time.

Excludes:
  - .claude/ worktrees and any backup directories
  - mockup-*, index-feminine*, placeholder*, veckans-running-events-* files
  - stockholm-marathon-2026-slutsalt.html (standalone promo page, no tracker needed)

Run:
    python3 inject_tracker.py
"""

from __future__ import annotations
from pathlib import Path
import re

ROOT = Path(__file__).parent

SCRIPT_TAG = '<script src="/tracker.js" defer></script>'

EXCLUDE_NAMES = {
    "stockholm-marathon-2026-slutsalt.html",
}
EXCLUDE_PREFIXES = ("mockup-", "index-feminine", "placeholder", "veckans-running-events-")
EXCLUDE_PATHS = (".claude", "backup")


def is_excluded(path: Path) -> bool:
    parts = path.parts
    if any(part.startswith(".claude") or "backup" in part for part in parts):
        return True
    name = path.name
    if name in EXCLUDE_NAMES:
        return True
    if any(name.startswith(p) for p in EXCLUDE_PREFIXES):
        return True
    return False


def patch(html: str) -> tuple[str, str]:
    """Return (new_html, status) where status is 'added', 'already', or 'no-body'."""
    if SCRIPT_TAG in html:
        return html, "already"
    new_html = html.replace("</body>", f"  {SCRIPT_TAG}\n</body>", 1)
    if new_html == html:
        return html, "no-body"
    return new_html, "added"


def main() -> None:
    print("\n── inject_tracker.py ──────────────────────────────────────")

    pages = [
        p for p in ROOT.rglob("*.html")
        if not is_excluded(p)
    ]
    pages.sort()

    added = skipped = already = 0

    for path in pages:
        html = path.read_text(encoding="utf-8")
        new_html, status = patch(html)
        if status == "added":
            path.write_text(new_html, encoding="utf-8")
            print(f"  ✓ {path.relative_to(ROOT)}")
            added += 1
        elif status == "already":
            already += 1
        else:
            print(f"  ! {path.relative_to(ROOT)}  (no </body> found — skipped)")
            skipped += 1

    print(f"\nDone. {added} updated, {already} already had tracker, {skipped} skipped.\n")


if __name__ == "__main__":
    main()
