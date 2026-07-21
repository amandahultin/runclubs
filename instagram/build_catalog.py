"""Pre-render the Jinja component/template sources into static HTML for Claude Design.

Claude Design's preview pane loads these files directly in a browser — it has
no Jinja engine, so the {% %} / {{ }} source files in components/ and
templates/ won't render there as-is. This script renders each @dsCard-marked
file with sample data (the same demo data each file already uses for its own
standalone preview) into plain, self-contained HTML under instagram/catalog/,
which is what actually gets pushed to the design-sync project.

instagram/components/*.html and instagram/templates/*.html remain the single
source of truth for production rendering (generate_instagram_event_images.py
reads them directly, unrendered-to-static, at request time with real event
data) — this script only produces a browsable snapshot for the catalog.

Usage:
    python instagram/build_catalog.py
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

INSTAGRAM_DIR = Path(__file__).resolve().parent
CATALOG_DIR = INSTAGRAM_DIR / "catalog"

# Demo context for the two files that need real event data to render at all
# (the components embed their own sample calls; only the composing
# templates need a context passed in from outside).
_EVENT_DEMO = dict(
    city="Stockholm", day=25, day_name="LÖRDAG", month="JUL",
    club="Vitamin Well", title="Run Well in Stockholm — Social & Speedy",
    location="Sturegatan 11, Stockholm, Sverige", title_size=82,
)
_REEL_DEMO = dict(
    title="Veckan på runclubs.se",
    events=[
        {"day": "MÅN", "date": "27", "club": "Vitamin Well", "city": "Stockholm",
         "title": "Run Well i Stockholm", "loc": "Sturegatan 11"},
        {"day": "ONS", "date": "29", "club": "Core Run Club", "city": "Göteborg",
         "title": "Tempopass", "loc": "Heden"},
    ],
)

CONTEXTS = {
    "templates/event-post.html": _EVENT_DEMO,
    "templates/event-story.html": _EVENT_DEMO,
    "templates/reel-frame.html": _REEL_DEMO,
}



# instagram/ predates this catalog and holds a lot of unrelated legacy assets
# (old campaign images, markdown notes) alongside components/ and templates/ —
# scope the scan explicitly rather than walking the whole directory tree.
CARD_FILES = [
    "components/tokens.html",
    "components/logo.html",
    "components/city-pill.html",
    "components/date-block.html",
    "components/location-line.html",
    "templates/event-post.html",
    "templates/event-story.html",
    "templates/reel-frame.html",
]


def build() -> list[Path]:
    env = Environment(loader=FileSystemLoader(str(INSTAGRAM_DIR)), autoescape=select_autoescape(["html"]))
    written: list[Path] = []

    for rel_path in CARD_FILES:
        full_source = (INSTAGRAM_DIR / rel_path).read_text(encoding="utf-8")
        if "@dsCard" not in full_source.splitlines()[0]:
            raise ValueError(f"{rel_path} is missing its @dsCard first-line marker")

        html = env.get_template(rel_path).render(**CONTEXTS.get(rel_path, {}))
        out_path = CATALOG_DIR / rel_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        written.append(out_path)
        print(f"Built {rel_path} -> {out_path.relative_to(INSTAGRAM_DIR.parent)}")

    return written


if __name__ == "__main__":
    build()
