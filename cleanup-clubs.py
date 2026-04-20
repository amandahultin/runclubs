#!/usr/bin/env python3
"""
cleanup-clubs.py

Tar bort klubbar från runclubs.se. Körning:

    python3 cleanup-clubs.py --dry-run   # Visa vad som skulle ändras, utan att ändra något
    python3 cleanup-clubs.py             # Gör ändringarna (säkerhetskopior skapas automatiskt)

Säkerhetskopior sparas i ./backup-cleanup-YYYYMMDD-HHMMSS/ bredvid projektet.

Du kan också använda git för att ångra: `git diff` visar ändringar, `git checkout <fil>` rullar tillbaka.
"""

import os, re, sys, shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ── KONFIG ─────────────────────────────────────────────────────────────────────

# Klubbar att ta bort, per stadsida. Värdet är exakt strängen i <div class="card-name">.
CITY_CARDS_TO_REMOVE = {
    'stockholm.html': [
        'Stockholm Frontrunners',
        'Hagaparken Parkrun',
        'Adidas Runners Stockholm',
        'Founders Running Club',
    ],
    'goteborg.html': [
        'Solvikingarna',
        'Språng Trail Club',
        'Majornas IK',
        'Runacademy Skatås',
        'Skatås Parkrun',
    ],
    'malmo.html': [
        'Sweden Runners Malmö',
        'MAI Runners',
        'Malmö Ribersborg Parkrun',
        'Runacademy City',
        'Runacademy Bulltofta',
    ],
}

# HTML-filer som ska raderas (klubbar med egna sidor)
FILES_TO_DELETE = [
    'stockholm-frontrunners.html',
    'solvikingarna.html',
    'sprang-trail-club.html',
    'sweden-runners-malmo.html',
    'mai-runners.html',
    'malmo-ribersborg-parkrun.html',
]

# URL-slugs att ta bort ur sitemap.xml
SITEMAP_SLUGS_TO_REMOVE = [
    'stockholm-frontrunners',
    'solvikingarna',
    'sprang-trail-club',
    'sweden-runners-malmo',
    'mai-runners',
    'malmo-ribersborg-parkrun',
]

# Filer där totalsiffran "32" (klubbar) behöver minskas
COUNT_FILES = [
    ('om-oss.html', r'>(\d+) run clubs<', '{n} run clubs'),
    ('samarbeta.html', r'>(\d+)</span>\s*<span[^>]*>\s*Listade klubbar',
     None),  # Hanteras separat nedan
]

# Antal klubbar som tas bort totalt
REMOVED_COUNT = sum(len(v) for v in CITY_CARDS_TO_REMOVE.values())
assert REMOVED_COUNT == 14, f"Väntade 14 klubbar, hittade {REMOVED_COUNT}"

# ── HJÄLPFUNKTIONER ────────────────────────────────────────────────────────────

def backup_file(path, backup_dir):
    rel = path.relative_to(ROOT)
    dest = backup_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)

def remove_card_block(html, club_name):
    """
    Plockar bort en hel <a class="club-card">-block som innehåller
    <div class="card-name">CLUB_NAME</div>.

    Använder BeautifulSoup för att hitta EXAKT rätt kort — regex är
    opålitligt eftersom icke-girig matchning fortfarande startar från
    första <a class="club-card"> i dokumentet.

    Returnerar (new_html, removed_count).
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    removed = 0
    for card in soup.find_all('a', class_='club-card'):
        name_div = card.find('div', class_='card-name')
        if name_div and name_div.get_text(strip=True) == club_name:
            # Ta bort ev. vitsrad/newline innan kortet för att undvika dubbla tomrader
            prev = card.previous_sibling
            if prev and isinstance(prev, str) and prev.strip() == '':
                prev.extract()
            card.decompose()
            removed += 1
    if removed:
        return str(soup), removed
    return html, 0

def count_actual_cards():
    """Räkna faktiska klubbkort i städsidor efter städning."""
    from bs4 import BeautifulSoup
    total = 0
    for fname in ('stockholm.html', 'goteborg.html', 'malmo.html'):
        p = ROOT / fname
        if not p.exists(): continue
        soup = BeautifulSoup(p.read_text(encoding='utf-8'), 'html.parser')
        total += len(soup.find_all('a', class_='club-card'))
    return total

def update_count_in_file(path, actual_count):
    """
    Sätter siffror i om-oss.html och samarbeta.html till faktiskt antal klubbar.
    Returnerar (ny_text, ändringar).
    """
    text = path.read_text(encoding='utf-8')
    changes = []

    # Mönster 1: "32 run clubs" (om-oss) — byt till actual_count
    def repl1(m):
        old = int(m.group(1))
        changes.append(f'{old} run clubs → {actual_count} run clubs')
        return m.group(0).replace(str(old), str(actual_count), 1)
    text2 = re.sub(r'(\d+)\s+run\s+clubs', repl1, text, count=1, flags=re.IGNORECASE)

    # Mönster 2: <div class="stats-number">32</div> ... Listade klubbar (samarbeta)
    def repl2(m):
        old = int(m.group(2))
        changes.append(f'{old} (Listade klubbar) → {actual_count}')
        return m.group(1) + str(actual_count) + m.group(3)
    text3 = re.sub(
        r'(<div class="stats-number">)(\d+)(</div>\s*<div class="stats-label">\s*Listade klubbar)',
        repl2, text2, count=1
    )

    return text3, changes

def remove_sitemap_entries(text, slugs):
    """Ta bort <url>…</url>-block vars <loc> innehåller någon av våra slugs."""
    new_text = text
    total_removed = 0
    for slug in slugs:
        pattern = re.compile(
            r'\s*<url>\s*<loc>https://runclubs\.se/' + re.escape(slug) + r'</loc>.*?</url>',
            re.DOTALL
        )
        new_text, n = pattern.subn('', new_text)
        total_removed += n
    return new_text, total_removed

# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    dry_run = '--dry-run' in sys.argv

    print(f'{"[DRY RUN] " if dry_run else ""}Städning av klubbar — runclubs.se')
    print(f'Projekt: {ROOT}\n')

    # Säkerhetskopior (endast om vi faktiskt skriver)
    backup_dir = None
    if not dry_run:
        ts = datetime.now().strftime('%Y%m%d-%H%M%S')
        backup_dir = ROOT / f'backup-cleanup-{ts}'
        backup_dir.mkdir(exist_ok=True)
        print(f'Backup-mapp: {backup_dir.name}\n')

    total_cards_removed = 0
    total_files_deleted = 0
    total_sitemap_removed = 0

    # 1. Ta bort kort från städsidor
    print('── 1. Städar kort från städsidor ──')
    for city_file, clubs in CITY_CARDS_TO_REMOVE.items():
        path = ROOT / city_file
        if not path.exists():
            print(f'  ⚠ {city_file} saknas, hoppar över')
            continue
        html = path.read_text(encoding='utf-8')
        orig = html
        removed_here = []
        missing_here = []
        for club in clubs:
            html, n = remove_card_block(html, club)
            if n:
                removed_here.append(f'{club} ({n}×)')
            else:
                missing_here.append(club)
        if removed_here:
            print(f'  {city_file}:')
            for line in removed_here:
                print(f'    ✓ {line}')
        if missing_here:
            for line in missing_here:
                print(f'    ✗ MATCHADE INTE: {line}')
        if not dry_run and html != orig:
            backup_file(path, backup_dir)
            path.write_text(html, encoding='utf-8')
        total_cards_removed += len(removed_here)

    # 2. Radera egna klubbsidor
    print('\n── 2. Raderar egna klubbsidor ──')
    for fname in FILES_TO_DELETE:
        path = ROOT / fname
        if path.exists():
            print(f'  ✓ {fname}')
            if not dry_run:
                backup_file(path, backup_dir)
                path.unlink()
            total_files_deleted += 1
        else:
            print(f'  ⚠ {fname} finns inte, hoppar över')

    # 3. Uppdatera sitemap.xml
    print('\n── 3. Städar sitemap.xml ──')
    sitemap = ROOT / 'sitemap.xml'
    if sitemap.exists():
        text = sitemap.read_text(encoding='utf-8')
        new_text, n = remove_sitemap_entries(text, SITEMAP_SLUGS_TO_REMOVE)
        print(f'  ✓ Tog bort {n} URL:er')
        total_sitemap_removed = n
        if not dry_run and n > 0:
            backup_file(sitemap, backup_dir)
            sitemap.write_text(new_text, encoding='utf-8')

    # 4. Uppdatera räknare — baserat på FAKTISKT antal kort
    print('\n── 4. Uppdaterar klubbräknare ──')
    actual = count_actual_cards()
    print(f'  Faktiskt antal kort efter städning: {actual}')
    for fname in ('om-oss.html', 'samarbeta.html'):
        path = ROOT / fname
        if not path.exists():
            continue
        new_text, changes = update_count_in_file(path, actual)
        if changes:
            for c in changes:
                print(f'  {fname}: {c}')
            if not dry_run:
                backup_file(path, backup_dir)
                path.write_text(new_text, encoding='utf-8')
        else:
            print(f'  {fname}: ingen räknare hittad (kolla manuellt)')

    # Summering
    print(f'\n── Summering ──')
    print(f'  Kort borttagna:   {total_cards_removed}')
    print(f'  Filer raderade:   {total_files_deleted}')
    print(f'  Sitemap-poster:   {total_sitemap_removed}')
    if dry_run:
        print('\n  Detta var en DRY RUN — inga filer ändrades.')
        print('  Kör utan --dry-run för att göra ändringarna på riktigt.')
    else:
        print(f'\n  Säkerhetskopior sparade i: {backup_dir.name}/')
        print('  För att rulla tillbaka: kopiera tillbaka från backup-mappen eller använd git.')

if __name__ == '__main__':
    main()
