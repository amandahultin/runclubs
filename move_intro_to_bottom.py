"""move_intro_to_bottom.py

Moves the "Om klubben" article (intro copy) from inside the .club-content
grid to just before <footer> on every migrated club page.

Layout change:
  BEFORE: [article | sidebar]  (two-column grid)
  AFTER:  [sidebar strip]  →  map  →  related  →  CTA  →  newsletter
          [Om klubben article]
          <footer>

CSS changes:
  - .club-content: drop grid, keep max-width container
  - .club-sidebar: horizontal flex strip (3 sections side by side)
  - .sidebar-section: flex: 1 so sections distribute evenly
  - .club-about: becomes standalone bottom section with border-top
  - Mobile: sidebar stacks, club-about full width

Safe to re-run (idempotent — skips pages already transformed).
"""

from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).parent

CLUB_PAGES = (
    list(ROOT.glob("stockholm/*/index.html")) +
    list(ROOT.glob("goteborg/*/index.html")) +
    list(ROOT.glob("malmo/*/index.html"))
)

# ── CSS replacements ──────────────────────────────────────────────────────────

CSS_SWAPS = [
    # 1. .club-content: drop the grid, keep max-width container
    (
        "      display: grid; grid-template-columns: 1fr 320px; gap: 0;\n"
        "      min-height: 400px; max-width: 1200px; margin: 0 auto;",

        "      max-width: 1200px; margin: 0 auto;"
    ),

    # 2. .club-about: drop border-right, add border-top + auto centering
    (
        "      padding: 3rem 2.5rem;\n"
        "      border-right: 1px solid #F0E0DC;",

        "      max-width: 1200px; margin: 0 auto;\n"
        "      padding: 3rem 2.5rem;\n"
        "      border-top: 1px solid #F0E0DC;"
    ),

    # 3. /* Left column - about */ comment
    (
        "    /* Left column - about */",
        "    /* Om klubben (moved to bottom) */"
    ),

    # 4. /* Right column - sidebar */ → strip comment + make flex
    (
        "    /* Right column - sidebar */\n"
        "    .club-sidebar {\n"
        "      padding: 3rem 2rem;\n"
        "      background: #FDFAF9;\n"
        "    }",

        "    /* Quick facts strip */\n"
        "    .club-sidebar {\n"
        "      padding: 2.5rem 2.5rem;\n"
        "      background: #FDFAF9;\n"
        "      display: flex; gap: 3rem; flex-wrap: wrap;\n"
        "      border-bottom: 1px solid #F0E0DC;\n"
        "    }"
    ),

    # 5. .sidebar-section: flex children
    (
        "    .sidebar-section { margin-bottom: 2.5rem; }\n"
        "    .sidebar-section:last-child { margin-bottom: 0; }",

        "    .sidebar-section { flex: 1; min-width: 200px; }"
    ),

    # 6. Mobile: club-content grid reset (no longer a grid)
    (
        "      .club-content { grid-template-columns: 1fr; }",
        "      .club-sidebar { flex-direction: column; gap: 1.5rem; padding: 2rem 1.25rem; }"
    ),

    # 7. Mobile: club-about border cleanup
    (
        "      .club-about { padding: 2rem 1.25rem; border-right: none; border-bottom: 1px solid #F0E0DC; }",
        "      .club-about { padding: 2rem 1.25rem; }"
    ),
]

# ── Article extraction regex ──────────────────────────────────────────────────

# Matches the entire <article class="club-about ...">...</article> block
ARTICLE_RE = re.compile(
    r'\n?[ \t]*<article class="club-about[^"]*">(.*?)</article>[ \t]*\n?',
    re.DOTALL,
)

ALREADY_DONE_RE = re.compile(
    r'<article class="club-about',
)


# ── Per-file transform ────────────────────────────────────────────────────────

def transform(html: str) -> tuple[str, list[str]]:
    """Return (new_html, list_of_changes_applied). Empty list = already done."""
    changes: list[str] = []

    # Idempotency: check whether the article is STILL inside .club-content
    # (i.e. before the sidebar). If it's already been moved, skip.
    article_match = ARTICLE_RE.search(html)
    if not article_match:
        return html, []  # no article to move (Malmö stubs)

    # Check position: article must come before </div> that closes .club-content
    # i.e. before <aside class="club-sidebar
    article_pos = article_match.start()
    sidebar_pos = html.find('<aside class="club-sidebar')
    if sidebar_pos == -1 or article_pos > sidebar_pos:
        return html, []  # already moved

    # ── 1. Remove article from its current position ──────────────────────────
    article_html = article_match.group(0)
    html = html[:article_match.start()] + "\n" + html[article_match.end():]
    changes.append("extracted article from .club-content")

    # ── 2. Apply CSS swaps ───────────────────────────────────────────────────
    for old, new in CSS_SWAPS:
        if old in html:
            html = html.replace(old, new, 1)
            changes.append(f"css: {old[:40].strip()!r}…")

    # ── 3. Re-insert article before <footer> ────────────────────────────────
    # Normalise the article snippet: strip leading/trailing whitespace, add
    # a wrapper with section-level padding for the bottom-of-page position.
    inner = article_match.group(1)  # content between <article>…</article>
    bottom_article = (
        '\n\n  <article class="club-about fade-in">'
        + inner
        + '</article>\n\n'
    )

    footer_pos = html.find('\n  <footer')
    if footer_pos == -1:
        footer_pos = html.find('<footer')
    if footer_pos != -1:
        html = html[:footer_pos] + bottom_article + html[footer_pos:]
        changes.append("inserted article before <footer>")
    else:
        # Fallback: append before </main>
        html = html.replace('  </main>', bottom_article + '  </main>', 1)
        changes.append("inserted article before </main> (no <footer> found)")

    return html, changes


def main() -> None:
    print("\n── Moving intro copy to bottom of club pages ───────────────")
    updated = skipped = 0

    for path in sorted(CLUB_PAGES):
        rel = path.relative_to(ROOT)
        html = path.read_text(encoding="utf-8")
        new_html, changes = transform(html)

        if changes:
            path.write_text(new_html, encoding="utf-8")
            print(f"  ✓ {rel}  ({len(changes)} changes)")
            updated += 1
        else:
            print(f"  · {rel}  (skipped)")
            skipped += 1

    print(f"\nDone. {updated} updated, {skipped} skipped.\n")


if __name__ == "__main__":
    main()
