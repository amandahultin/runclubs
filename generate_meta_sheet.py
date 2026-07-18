"""Build a CSV inventory of every URL in sitemap.xml with its meta title and
meta description, for manual editing in a spreadsheet.

- Static pages (index, city pages, club pages, articles, ...): title/description
  are scraped from the live HTML, marked "Befintlig" (existing).
- Filter-combo pages (?niva=...&typ=...&stadsdel=...): title/description are the
  auto-generated drafts injected by the city pages' JS, marked "Ny (förslag)"
  (new / draft) since they've never been manually reviewed.

Run directly:  python3 generate_meta_sheet.py
Writes meta-sheet.csv in the project root.
"""

from __future__ import annotations

import csv
import html as html_lib
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from filter_combos import all_combos
from generate_sitemap import BASE_URL

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL)
DESC_RE = re.compile(r'<meta\s+name="description"\s+content="([^"]*)"', re.DOTALL)
REFRESH_RE = re.compile(r'<meta\s+http-equiv="refresh"\s+content="[^"]*url=([^"]+)"', re.IGNORECASE)


def local_path_for_url(url: str, root: Path) -> Path:
    """Map a canonical runclubs.se URL to its local HTML file on disk."""
    path = url.removeprefix(BASE_URL)
    if path in ("", "/"):
        return root / "index.html"
    path = path.lstrip("/")
    if path.endswith("/"):
        return root / path / "index.html"
    return root / f"{path}.html"


def scrape_meta(url: str, root: Path, hops: int = 0) -> tuple[str, str]:
    """Scrape <title>/description, following meta-refresh redirect stubs
    (many club/article slugs are just a stub at the root that instant-redirects
    into a /city/slug/ or /nyheter/slug/ folder — the stub's own <title> is
    always the placeholder "Flyttad sida", not real content)."""
    path = local_path_for_url(url, root)
    if not path.exists():
        return "", ""
    html = path.read_text(encoding="utf-8")
    refresh_m = REFRESH_RE.search(html) if hops < 5 else None
    if refresh_m:
        target = refresh_m.group(1)
        target_url = target if target.startswith("http") else BASE_URL + target
        return scrape_meta(target_url, root, hops + 1)
    title_m = TITLE_RE.search(html)
    desc_m = DESC_RE.search(html)
    title = html_lib.unescape(title_m.group(1).strip()) if title_m else ""
    desc = html_lib.unescape(desc_m.group(1).strip()) if desc_m else ""
    return title, desc


def page_type(url: str, has_query: bool) -> str:
    path = url.removeprefix(BASE_URL)
    if has_query:
        return "Filtersida"
    if path in ("", "/"):
        return "Startsida"
    if path in ("/stockholm", "/goteborg", "/ovriga-landet"):
        return "Stadssida"
    if re.match(r"^/(stockholm|goteborg|ovriga-landet)/", path):
        return "Klubbsida"
    return "Övrig sida"


def build_rows(root: Path) -> list[dict[str, str]]:
    tree = ET.parse(root / "sitemap.xml")
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [el.text for el in tree.findall(".//sm:url/sm:loc", ns)]

    combo_by_url = {c.url: c for c in all_combos(root)}

    rows = []
    for url in urls:
        has_query = "?" in url
        if has_query:
            combo = combo_by_url.get(url)
            if combo is None:
                continue
            title, desc, status = combo.title, combo.description, "Ny (förslag)"
        else:
            title, desc = scrape_meta(url, root)
            status = "Befintlig" if title else "Okänd källfil"

        rows.append({
            "URL": url,
            "Sidtyp": page_type(url, has_query),
            "Status": status,
            "Meta titel": title,
            "Titel (tecken)": str(len(title)),
            "Meta description": desc,
            "Description (tecken)": str(len(desc)),
        })
    return rows


if __name__ == "__main__":
    root = Path(__file__).parent
    rows = build_rows(root)
    out = root / "meta-sheet.csv"
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "URL", "Sidtyp", "Status", "Meta titel", "Titel (tecken)",
            "Meta description", "Description (tecken)",
        ])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {out} ({len(rows)} rows)")
