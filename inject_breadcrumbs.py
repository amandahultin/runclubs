"""inject_breadcrumbs.py
Injects BreadcrumbList JSON-LD into every non-home HTML page.

Run from the repo root:
    python inject_breadcrumbs.py
"""

from __future__ import annotations
import json
import re
import sys
from pathlib import Path

BASE_URL = "https://runclubs.se"

# ── Static page map ──────────────────────────────────────────────────────────
# slug (without .html) → list of (name, url) crumbs AFTER "Hem"
STATIC_PAGES: dict[str, list[tuple[str, str]]] = {
    # City pages
    "stockholm":               [("Stockholm", f"{BASE_URL}/stockholm")],
    "goteborg":                [("Göteborg",  f"{BASE_URL}/goteborg")],
    "ovriga-landet":           [("Övriga landet", f"{BASE_URL}/ovriga-landet")],
    # City event pages
    "stockholm-running-events": [("Stockholm", f"{BASE_URL}/stockholm"),
                                 ("Events",    f"{BASE_URL}/stockholm-running-events")],
    "goteborg-running-events":  [("Göteborg",  f"{BASE_URL}/goteborg"),
                                 ("Events",    f"{BASE_URL}/goteborg-running-events")],
    "ovriga-landet-running-events": [("Events",       f"{BASE_URL}/events"),
                                     ("Övriga landet", f"{BASE_URL}/ovriga-landet-running-events")],
    # Global event / race pages
    "events":               [("Events",       f"{BASE_URL}/events")],
    "loppkalender":             [("Loppkalender", f"{BASE_URL}/loppkalender")],
    # News hub
    "nyheter":                  [("Nyheter", f"{BASE_URL}/nyheter")],
    # Articles
    "tjejer-tar-over-lopsparen":      [("Nyheter", f"{BASE_URL}/nyheter"),
                                       ("Tjejer tar över löpspåren — och gör det tillsammans",
                                        f"{BASE_URL}/tjejer-tar-over-lopsparen")],
    "stockholm-marathon-2026-slutsalt": [("Nyheter", f"{BASE_URL}/nyheter"),
                                         ("Stockholm Marathon 2026 slutsålt — på rekordtid",
                                          f"{BASE_URL}/stockholm-marathon-2026-slutsalt")],
    "lopning-for-tjejer":             [("Nyheter", f"{BASE_URL}/nyheter"),
                                       ("Löpning för tjejer",
                                        f"{BASE_URL}/lopning-for-tjejer")],
    # Info pages
    "om-oss":    [("Om oss",    f"{BASE_URL}/om-oss")],
    "kontakt":   [("Kontakt",   f"{BASE_URL}/kontakt")],
    "samarbeta": [("Samarbeta", f"{BASE_URL}/samarbeta")],
}

CITY_URL = {
    "Stockholm": f"{BASE_URL}/stockholm",
    "Göteborg":  f"{BASE_URL}/goteborg",
    "Malmö":     f"{BASE_URL}/ovriga-landet",
}

# Pages to skip entirely
SKIP = {
    "index", "klubb", "saucony-run-club",
    "mockup-botanik", "mockup-korall", "mockup-lila", "mockup-solsken",
    "index-feminine", "index-feminine-v2", "placeholder-preview",
}


def extract_h1(html: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
    if not m:
        return ""
    return re.sub(r"<[^>]+>", " ", m.group(1)).replace("\n", " ").strip()


def extract_address_locality(html: str) -> str | None:
    m = re.search(r'"addressLocality"\s*:\s*"([^"]+)"', html)
    return m.group(1) if m else None


def build_breadcrumb_json(crumbs: list[tuple[str, str]]) -> str:
    # crumbs = [(name, url), ...] — Hem is prepended automatically
    full = [("Hem", f"{BASE_URL}/")] + crumbs
    items = [
        {
            "@type": "ListItem",
            "position": i + 1,
            "name": name,
            "item": url,
        }
        for i, (name, url) in enumerate(full)
    ]
    schema = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": items,
    }
    return json.dumps(schema, ensure_ascii=False, indent=2)


def inject(html: str, json_ld: str) -> str:
    """Insert <script type="application/ld+json"> just before </head>."""
    tag = f'  <script type="application/ld+json">\n{json_ld}\n  </script>\n'
    return html.replace("</head>", tag + "</head>", 1)


def already_has_breadcrumb(html: str) -> bool:
    return "BreadcrumbList" in html


def process_file(path: Path) -> str:
    slug = path.stem
    html = path.read_text(encoding="utf-8")

    if already_has_breadcrumb(html):
        return "skip (already has BreadcrumbList)"

    # Static mapping takes priority
    if slug in STATIC_PAGES:
        crumbs = STATIC_PAGES[slug]
    else:
        # Treat as a club page — detect city from addressLocality
        city = extract_address_locality(html)
        if not city or city not in CITY_URL:
            return f"skip (no city detected — addressLocality={city!r})"
        club_name = extract_h1(html).replace("<br>", " ").replace("\n", " ").strip()
        if not club_name:
            return "skip (no h1 found)"
        slug_url = f"{BASE_URL}/{slug}"
        crumbs = [
            (city,      CITY_URL[city]),
            (club_name, slug_url),
        ]

    json_ld = build_breadcrumb_json(crumbs)
    path.write_text(inject(html, json_ld), encoding="utf-8")
    return "ok — " + " › ".join(n for n, _ in [("Hem", "")] + crumbs)


def main() -> None:
    root = Path(__file__).parent
    results: list[tuple[str, str]] = []

    for path in sorted(root.glob("*.html")):
        if path.stem in SKIP:
            continue
        status = process_file(path)
        results.append((path.name, status))

    ok = [(f, s) for f, s in results if s.startswith("ok")]
    skipped = [(f, s) for f, s in results if not s.startswith("ok")]

    print(f"\n✓ Injected breadcrumbs into {len(ok)} files:")
    for f, s in ok:
        print(f"  {f}: {s}")
    if skipped:
        print(f"\n⚠ Skipped {len(skipped)} files:")
        for f, s in skipped:
            print(f"  {f}: {s}")


if __name__ == "__main__":
    main()
