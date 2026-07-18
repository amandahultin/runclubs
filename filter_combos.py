"""Shared logic for computing indexable niva/typ/location filter-combination
pages on the city landing pages (stockholm.html, goteborg.html, ovriga-landet.html).

Used by generate_sitemap.py (to add these URLs to the sitemap) and by
generate_meta_sheet.py (to draft title/description text for the Google Sheet).

The third filter axis is "stadsdel" (city district) for Stockholm/Göteborg,
but "stad" (city/town) for Övriga landet, since that page spans multiple towns
rather than districts of one city.

Only combinations that actually match at least one club card are generated —
a filter combo with zero results would be a thin/empty page and must never be
indexed. "dag" (day of week) is deliberately excluded: low search intent, and
including it would multiply the URL count 3-4x for little SEO value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path

BASE_URL = "https://runclubs.se"

CITY_LABELS = {
    "stockholm": "Stockholm",
    "goteborg": "Göteborg",
    "ovriga-landet": "Övriga landet",
}

# The URL param / data-attribute name used for each city's third filter axis.
CITY_LOCATION_PARAM = {
    "stockholm": "stadsdel",
    "goteborg": "stadsdel",
    "ovriga-landet": "stad",
}

NIVA_LABELS = {
    "nybörjare": "Nybörjare",
    "mellannivå": "Mellannivå",
    "avancerad": "Avancerad",
}

TYP_LABELS = {
    "väg": "Väg",
    "trail": "Trail",
    "intervall": "Intervall",
    "långpass": "Långpass",
    "social": "Social",
    "girls-only": "Girls Only",
    "tempo": "Tempo",
    "frukost": "Frukost",
}

STADSDEL_LABELS = {
    "södermalm": "Södermalm",
    "östermalm": "Östermalm",
    "vasastan": "Vasastan",
    "city": "City",
    "söderort": "Söderort",
    "kungsholmen": "Kungsholmen",
    "linné-majorna": "Linné-Majorna",
    "johanneberg": "Johanneberg",
    "olskroken": "Olskroken",
}

STAD_LABELS = {
    "malmö": "Malmö",
    "varberg": "Varberg",
    "alingsås": "Alingsås",
    "eskilstuna": "Eskilstuna",
    "kalmar": "Kalmar",
    "lund": "Lund",
    "norrköping": "Norrköping",
    "uppsala": "Uppsala",
    "västerås": "Västerås",
}

# Label lookup for each city's third filter axis.
CITY_LOCATION_LABELS = {
    "stockholm": STADSDEL_LABELS,
    "goteborg": STADSDEL_LABELS,
    "ovriga-landet": STAD_LABELS,
}

CARD_TAG_RE = re.compile(r'<a href="[^"]*"\s+class="club-card"([^>]*)>')
ATTR_RE = re.compile(r'data-([\w-]+)="([^"]*)"')


@dataclass
class Combo:
    city: str
    niva: str | None
    typ: str | None
    location: str | None
    result_count: int
    title: str = field(init=False)
    description: str = field(init=False)
    url: str = field(init=False)

    def __post_init__(self) -> None:
        location_labels = CITY_LOCATION_LABELS[self.city]
        labels = [
            l for l in (
                NIVA_LABELS.get(self.niva) if self.niva else None,
                TYP_LABELS.get(self.typ) if self.typ else None,
                location_labels.get(self.location) if self.location else None,
            ) if l
        ]
        city_label = CITY_LABELS[self.city]
        suffix = f" – {' · '.join(labels)}" if labels else ""
        self.title = f"Löpargrupper i {city_label}{suffix} | Runclubs.se"
        facet = f" ({', '.join(labels)})" if labels else ""
        location_param = CITY_LOCATION_PARAM[self.city]
        filter_axes = f"nivå, typ och {location_param}"
        self.description = (
            f"Hitta löpargrupper i {city_label}{facet} — filtrera på {filter_axes} "
            f"och hitta din grupp. Gratis, ingen anmälan krävs. "
            f"Se tider och startplatser på Runclubs.se."
        )
        params = []
        if self.niva:
            params.append(f"niva={self.niva}")
        if self.typ:
            params.append(f"typ={self.typ}")
        if self.location:
            params.append(f"{location_param}={self.location}")
        qs = "&".join(params)
        self.url = f"{BASE_URL}/{self.city}" + (f"?{qs}" if qs else "")


def _parse_pill_options(html: str, filter_name: str) -> list[str]:
    pattern = re.compile(rf'data-filter="{filter_name}" data-value="([^"]+)"')
    seen: list[str] = []
    for val in pattern.findall(html):
        if val not in seen:
            seen.append(val)
    return seen


def _parse_cards(html: str) -> list[dict[str, set[str]]]:
    cards = []
    for tag_attrs in CARD_TAG_RE.findall(html):
        attrs = {name: set(value.split()) for name, value in ATTR_RE.findall(tag_attrs)}
        cards.append(attrs)
    return cards


def get_city_combos(city: str, html_path: Path) -> list[Combo]:
    """Return all non-empty niva/typ/location filter combinations for a city page."""
    html = html_path.read_text(encoding="utf-8")
    location_param = CITY_LOCATION_PARAM[city]
    pill_niva = _parse_pill_options(html, "niva")
    pill_typ = _parse_pill_options(html, "typ")
    pill_location = _parse_pill_options(html, location_param)
    cards = _parse_cards(html)

    combos: list[Combo] = []
    for niva, typ, location in product([None] + pill_niva, [None] + pill_typ, [None] + pill_location):
        if niva is None and typ is None and location is None:
            continue
        count = sum(
            1 for card in cards
            if (niva is None or niva in card.get("niva", set()))
            and (typ is None or typ in card.get("typ", set()))
            and (location is None or location in card.get(location_param, set()))
        )
        if count > 0:
            combos.append(Combo(city=city, niva=niva, typ=typ, location=location, result_count=count))
    return combos


def all_combos(root: Path) -> list[Combo]:
    result: list[Combo] = []
    for city in ("stockholm", "goteborg", "ovriga-landet"):
        html_path = root / f"{city}.html"
        if html_path.exists():
            result.extend(get_city_combos(city, html_path))
    return result


if __name__ == "__main__":
    root = Path(__file__).parent
    combos = all_combos(root)
    print(f"{len(combos)} filter-combo URLs")
    for c in combos[:5]:
        print(c.url, "|", c.title, "|", c.description)
