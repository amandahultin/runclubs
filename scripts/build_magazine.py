#!/usr/bin/env python3
"""Build the Min löpning diary (URL /magazine) from markdown posts.

Every post is one file in magazine/posts/<slug>.md (front matter + text).
From those, plus the hand-written articles listed in magazine/posts-legacy.json,
this script builds:

  - magazine/<slug>/index.html   one page per post (canonical, for SEO)
  - magazine.html                the feed between <!-- FEED:START/END --> and the
                                 newest post between <!-- FEATURED:START/END -->
  - magazine/tagg/<tag>/         one page per tag
  - magazine/arkiv/              all posts grouped by month
  - <slug>.html + _redirects     root stub, so generate_sitemap.py picks it up
  - news-sitemap.xml             an entry per post

Usage:  python3 scripts/build_magazine.py

Post format (front matter keys, one per line, `key: value`):
  title, h1 (optional, e.g. with &shy;), date (YYYY-MM-DD), time (HH:MM, only
  orders posts from the same day), tags (comma separated,
  first is the main one), kicker, description, excerpt, subtitle, crumb,
  image + image_alt (hero), card_image + card_image_alt (feed card + og:image),
  feed (full | excerpt), outro, draft (true to skip),
  ig_permalink, ig_published, ig_reach, ig_views, ig_saved, ig_shares, ig_updated

Body shortcodes (besides **bold**, *italic*, [link](url), ## headings, - lists):
  :: 📍 Östermalm | ☕ Kaffe               info strip
  > 🏃 **Rundan dit:** text              tip strip (first token is the emoji)
  ![alt](bild.jpg "Bildtext. Foto: X")   figure, webp used if bild.webp exists
  {{instagram https://www.instagram.com/reel/...}}   official embed + fallback link
  Lines starting with < are passed through as raw HTML.
"""
import html
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "magazine" / "posts"
LEGACY = ROOT / "magazine" / "posts-legacy.json"
TEMPLATE = ROOT / "templates" / "magazine_post.html"
FEED_START, FEED_END = "<!-- FEED:START -->", "<!-- FEED:END -->"
FEATURED_START, FEATURED_END = "<!-- FEATURED:START -->", "<!-- FEATURED:END -->"
SITE = "https://runclubs.se"

SECTION = "Min löpning"  # sektionens namn i rubriker och brödsmulor
TAGS = {
    "crew": "Find Your Crew", "nextup": "Next Up", "news": "Running News",
    "mystory": "My Story", "community": "Community", "portrait": "Club Portrait",
}
MONTHS = ["januari", "februari", "mars", "april", "maj", "juni", "juli",
          "augusti", "september", "oktober", "november", "december"]

esc = lambda s: html.escape(str(s), quote=True)


def month_label(iso):
    d = date.fromisoformat(iso)
    return f"{MONTHS[d.month - 1].capitalize()} {d.year}"


def day_label(iso):
    d = date.fromisoformat(iso)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


# ── Markdown ────────────────────────────────────────────────────────────────

def inline(s):
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", s)


def split_emoji(s):
    head, _, rest = s.partition(" ")
    if head and not any(ch.isalnum() for ch in head):
        return head, rest
    return None, s


def image_size(rel):
    try:
        from PIL import Image
        with Image.open(ROOT / rel.lstrip("/")) as im:
            return im.size
    except Exception:
        return None


def hero_css(src):
    """background-image declarations for the hero: webp first when it exists."""
    src = "/" + src.lstrip("/")
    css = f"background-image: url('{src}');"
    webp = re.sub(r"\.(jpe?g|png)$", ".webp", src)
    if webp != src and (ROOT / webp.lstrip("/")).exists():
        css += f"\n      background-image: image-set(url('{webp}') type('image/webp'), url('{src}') type('image/jpeg'));"
    return css


def picture(src, alt, extra=""):
    src = "/" + src.lstrip("/")
    webp = re.sub(r"\.(jpe?g|png)$", ".webp", src)
    size = image_size(src)
    dims = f' width="{size[0]}" height="{size[1]}"' if size else ""
    img = f'<img src="{src}" alt="{esc(alt)}" loading="lazy"{dims}{extra}>'
    if webp != src and (ROOT / webp.lstrip("/")).exists():
        return f'<picture><source srcset="{webp}" type="image/webp">{img}</picture>'
    return img


def instagram_embed(url):
    return (f'    <div class="ig-embed">\n'
            f'      <blockquote class="instagram-media" data-instgrm-permalink="{esc(url)}" data-instgrm-version="14"></blockquote>\n'
            f'      <a class="ig-embed-link" href="{esc(url)}" target="_blank" rel="noopener">Se reelen på Instagram →</a>\n'
            f'    </div>')


def markdown(text):
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        b = block.strip()
        lines = b.splitlines()
        if b.startswith("<"):
            out.append(block.rstrip())
        elif b.startswith("## ") or b.startswith("### "):
            level = 2 if b.startswith("## ") else 3
            emoji, rest = split_emoji(b[level + 1:].strip())
            span = f'<span class="emoji" aria-hidden="true">{emoji}</span>' if emoji else ""
            out.append(f"    <h{level}>{span}{inline(rest)}</h{level}>")
        elif b.startswith(":: "):
            items = []
            for part in b[3:].split("|"):
                emoji, rest = split_emoji(part.strip())
                items.append(f'      <div class="info-strip-item"><span class="info-strip-emoji" aria-hidden="true">{emoji or "•"}</span>'
                             f'<div class="info-strip-value">{inline(rest)}</div></div>')
            out.append('    <div class="info-strip">\n' + "\n".join(items) + "\n    </div>")
        elif b.startswith("> "):
            emoji, rest = split_emoji(" ".join(l[2:] if l.startswith("> ") else l for l in lines))
            out.append(f'    <div class="fits-strip">\n      <span class="fits-strip-emoji" aria-hidden="true">{emoji or "💡"}</span>\n'
                       f"      <div>{inline(rest)}</div>\n    </div>")
        elif m := re.fullmatch(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)', b):
            cap = f"\n      <figcaption>{inline(m.group(3))}</figcaption>" if m.group(3) else ""
            out.append(f"    <figure>\n      {picture(m.group(2), m.group(1))}{cap}\n    </figure>")
        elif m := re.fullmatch(r"\{\{instagram\s+(\S+)\}\}", b):
            out.append(instagram_embed(m.group(1)))
        elif all(l.startswith("- ") for l in lines):
            out.append("    <ul>\n" + "\n".join(f"      <li>{inline(l[2:])}</li>" for l in lines) + "\n    </ul>")
        else:
            out.append(f"    <p>{inline(' '.join(l.strip() for l in lines))}</p>")
    return "\n\n".join(out)


# ── Data ────────────────────────────────────────────────────────────────────

def read_post(path):
    raw = path.read_text()
    m = re.match(r"---\n(.*?)\n---\n(.*)", raw, re.S)
    if not m:
        raise SystemExit(f"{path.name}: front matter saknas")
    meta = {}
    for line in m.group(1).splitlines():
        if line.strip() and not line.startswith("#"):
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    for k in ("ig_reach", "ig_views", "ig_saved", "ig_shares"):
        meta[k] = int(meta[k].replace(" ", "")) if meta.get(k) else None
    meta["slug"] = path.stem
    meta["tags"] = [t.strip() for t in meta.get("tags", "mystory").split(",") if t.strip()]
    meta["url"] = f"/magazine/{path.stem}/"
    meta["body"] = m.group(2)
    meta["kind"] = "post"
    return meta


def load_entries():
    posts = [read_post(p) for p in sorted(POSTS.glob("*.md"))]
    posts = [p for p in posts if p.get("draft") != "true"]
    legacy = json.loads(LEGACY.read_text())
    for e in legacy:
        e["kind"] = "legacy"
        e["tags"] = [e["cat"]]
    entries = posts + [e for e in legacy if e["url"] not in {p["url"] for p in posts}]
    return sorted(entries, key=lambda e: (e["date"], e.get("time", "")), reverse=True)


def tag_label(e):
    if e["kind"] == "legacy":
        return e["tag"]
    label = TAGS.get(e["tags"][0], e["tags"][0])
    return f"{label} · {e['kicker']}" if e.get("kicker") else label


def card_img(e):
    """(src, alt, object-position) for the feed card / lists."""
    if e["kind"] == "legacy":
        return e["image"], e["alt"], e["pos"]
    return (f"/{e.get('card_image') or e['image']}.jpg",
            e.get("card_image_alt") or e.get("image_alt", ""), "center 50%")


# ── Building blocks ─────────────────────────────────────────────────────────

def ig_box(e):
    stats = [(l, e.get(k)) for l, k in (("Räckvidd", "ig_reach"), ("Visningar", "ig_views"),
                                         ("Sparningar", "ig_saved"), ("Delningar", "ig_shares"))]
    stats = [(l, v) for l, v in stats if isinstance(v, int)]
    if not stats:
        return ""
    spans = ([f"<span>Publicerat {day_label(e['ig_published'])}</span>"] if e.get("ig_published") else [])
    spans += [f"<span>{l} {v:,}</span>".replace(",", " ") for l, v in stats]
    foot = []
    if e.get("ig_permalink"):
        foot.append(f'<a href="{esc(e["ig_permalink"])}" target="_blank" rel="noopener">Se inlägget på Instagram →</a>')
    if e.get("ig_updated"):
        foot.append(f"Siffror uppdaterade {day_label(e['ig_updated'])}.")
    foot_html = f'\n      <div class="ig-diary-foot">{" ".join(foot)}</div>' if foot else ""
    return (f'    <aside class="ig-diary">\n      <div class="ig-diary-label">Från Instagram</div>\n'
            f'      <div class="ig-diary-stats">{"".join(spans)}</div>{foot_html}\n    </aside>')


def list_item(e):
    return (f'        <li style="border-bottom:1px solid #F0E0DC;">\n'
            f'          <a href="{e["url"]}" style="display:flex; justify-content:space-between; align-items:center; gap:1rem; padding:0.85rem 0; text-decoration:none; color:#1C2A45; font-size:14px; font-weight:500;">\n'
            f'            <span>{e["title"]}</span>\n'
            f'            <span style="color:#aaa; font-size:12px; white-space:nowrap; margin-left:1rem;">{month_label(e["date"])}</span>\n'
            f'          </a>\n        </li>')


def jsonld(items):
    return "\n".join(f'  <script type="application/ld+json">\n{json.dumps(i, ensure_ascii=False, indent=2)}\n  </script>' for i in items)


def breadcrumb(name, url):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Hem", "item": f"{SITE}/"},
        {"@type": "ListItem", "position": 2, "name": SECTION, "item": f"{SITE}/magazine"},
        {"@type": "ListItem", "position": 3, "name": name, "item": url}]}


def header(crumb, tag, h1, subtitle, meta):
    meta_html = "".join(f"\n        <span>{m}</span>" for m in meta)
    sub = f'\n      <p class="hero-subtitle">{subtitle}</p>' if subtitle else ""
    return f'''<header class="hero">
    <div class="hero-bg"></div>
    <div class="hero-content">
      <div class="breadcrumb"><a href="/">Start</a> / <a href="/magazine">{SECTION}</a> / {crumb}</div>
      <div class="hero-tag">{tag}</div>
      <h1>{h1}</h1>{sub}
      <div class="hero-meta">{meta_html}
      </div>
    </div>
  </header>'''


def page(**v):
    h = TEMPLATE.read_text()
    v.setdefault("EXTRA_BODY", "")
    v.setdefault("POST_NAV", "")
    v.setdefault("SECTION_LC", SECTION)
    for k, val in v.items():
        h = h.replace("{{" + k + "}}", val)
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", h)
    if leftover:
        raise SystemExit(f"oersatta platshållare: {leftover}")
    return h


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text() != text:
        path.write_text(text)
        print("  wrote", path.relative_to(ROOT))


# ── Pages ───────────────────────────────────────────────────────────────────

def post_page(e, entries):
    i = entries.index(e)
    url = SITE + e["url"]
    og = f"{SITE}/{e.get('card_image') or e['image']}.jpg"
    body = markdown(e["body"])
    box = ig_box(e)
    nav = []
    if i + 1 < len(entries):
        o = entries[i + 1]
        nav.append(f'    <a href="{o["url"]}" class="post-nav-prev">\n      <span class="post-nav-label">← Föregående inlägg</span>\n      <span class="post-nav-title">{o["title"]}</span>\n    </a>')
    if i > 0:
        n = entries[i - 1]
        nav.append(f'    <a href="{n["url"]}" class="post-nav-next">\n      <span class="post-nav-label">Nästa inlägg →</span>\n      <span class="post-nav-title">{n["title"]}</span>\n    </a>')
    article = {"@context": "https://schema.org", "@type": "Article", "headline": e["title"],
               "description": e["description"], "image": og,
               "author": {"@type": "Person", "name": "Amanda Hultin", "url": "https://amandahultin.se"},
               "publisher": {"@type": "Organization", "name": "Swedish Run Clubs", "url": SITE,
                             "logo": {"@type": "ImageObject", "url": f"{SITE}/favicon.svg"}},
               "datePublished": e["date"], "dateModified": e.get("updated", e["date"]),
               "mainEntityOfPage": {"@type": "WebPage", "@id": url}, "inLanguage": "sv"}
    seo_title = e.get("seo_title") or f"{e['title']} | Runclubs.se"
    return page(
        URL=url, SEO_TITLE=esc(seo_title), TITLE=esc(e["title"]), DESCRIPTION=esc(e["description"]),
        OG_TYPE="article", OG_IMAGE=og,
        ARTICLE_META=(f'<meta property="article:published_time" content="{e["date"]}">\n'
                      f'  <meta property="article:modified_time" content="{e.get("updated", e["date"])}">\n'
                      f'  <meta property="article:author" content="Amanda Hultin">'),
        HERO_CSS=hero_css(f"{e['image']}.jpg"), HERO_POS=e.get("image_pos", "center 50%"),
        JSONLD=jsonld([breadcrumb(e["title"], url), article]),
        HEADER=header(e.get("crumb", e["title"]), tag_label(e), e.get("h1", e["title"]),
                      e.get("subtitle", ""), [month_label(e["date"]), "Av Amanda Hultin"]),
        BODY=body + ("\n\n" + box if box else ""),
        OUTRO=e.get("outro", ""),
        POST_NAV='<nav class="post-nav">\n' + "\n".join(nav) + "\n  </nav>" if nav else "",
        MORE="\n".join(list_item(x) for x in [x for x in entries if x is not e][:12]),
        EXTRA_BODY='  <script async src="https://www.instagram.com/embed.js"></script>' if "instagram-media" in body else "",
    )


def list_page(url, title, description, crumb, tag, subtitle, hero_entry, body, entries):
    src, _, pos = card_img(hero_entry)
    if hero_entry["kind"] == "post":  # the post's own hero has no text-covered face
        src, pos = f"/{hero_entry['image']}.jpg", hero_entry.get("image_pos", "center 50%")
    return page(
        URL=url, SEO_TITLE=esc(f"{title} | Runclubs.se"), TITLE=esc(title), DESCRIPTION=esc(description),
        OG_TYPE="website", OG_IMAGE=f"{SITE}{src}", ARTICLE_META="",
        HERO_CSS=hero_css(src), HERO_POS=pos,
        JSONLD=jsonld([breadcrumb(crumb, url),
                       {"@context": "https://schema.org", "@type": "CollectionPage", "name": title, "url": url, "inLanguage": "sv"}]),
        HEADER=header(crumb, tag, title, subtitle, [f"{len(entries)} inlägg"]),
        BODY=body, OUTRO="", MORE="\n".join(list_item(x) for x in entries[:12]),
    )


def entry_list(entries):
    return ('    <ul style="list-style:none; padding:0; margin:0 0 1.5rem;">\n'
            + "\n".join(list_item(e) for e in entries) + "\n    </ul>")


def tag_pages(entries):
    for tag, label in TAGS.items():
        tagged = [e for e in entries if tag in e["tags"]]
        if not tagged:
            continue
        url = f"{SITE}/magazine/tagg/{tag}/"
        write(ROOT / "magazine" / "tagg" / tag / "index.html", list_page(
            url, f"{label} – alla inlägg", f"Alla inlägg taggade {label} på runclubs.se.", label, "Tagg",
            f"Alla inlägg taggade {label}.", tagged[0], entry_list(tagged), entries))


def archive_page(entries):
    body, current = [], None
    for e in entries:
        m = month_label(e["date"])
        if m != current:
            if current:
                body.append("    </ul>")
            body.append(f'    <h2>{m}</h2>\n    <ul style="list-style:none; padding:0; margin:0 0 1.5rem;">')
            current = m
        body.append(list_item(e))
    body.append("    </ul>")
    write(ROOT / "magazine" / "arkiv" / "index.html", list_page(
        f"{SITE}/magazine/arkiv/", f"Arkiv – {SECTION}", "Alla inlägg på runclubs.se, månad för månad.",
        "Arkiv", "Arkiv", "Alla inlägg, månad för månad.", entries[0], "\n".join(body), entries))


def featured(e):
    src, alt, pos = card_img(e)
    style = f' style="object-position: {pos};"'
    img = (f'<img src="{src}" alt="{esc(alt)}" loading="lazy" width="{e["w"]}" height="{e["h"]}"{style}>'
           if e["kind"] == "legacy" else picture(src, alt, style))
    excerpt = e["excerpt"] if e["kind"] == "legacy" else e.get("excerpt", e["description"])
    return f'''        <div class="featured-card fade-in">
          <div class="featured-image">
            {img}
          </div>
          <div class="featured-body">
            <span class="article-tag tag-{e["tags"][0]}">{tag_label(e)}</span>
            <h2><a href="{e["url"]}">{e["title"]}</a></h2>
            <div class="featured-meta">{month_label(e["date"])} · Av Amanda Hultin</div>
            <p class="featured-excerpt">{excerpt}</p>
            <a href="{e["url"]}" class="read-more">Läs hela inlägget <span>→</span></a>
          </div>
        </div>'''


def feed_item(e, first=False):
    cats = " ".join(e["tags"])
    feat = " data-featured" if first else ""  # hidden under "Alla", shown in the featured box
    src, alt, pos = card_img(e)
    if e["kind"] == "legacy":
        return f'''          <a href="{e["url"]}" class="article-card fade-in" data-cats="{cats}"{feat}>
            <div class="article-card-image">
              <img src="{src}" alt="{esc(alt)}" loading="lazy" width="{e["w"]}" height="{e["h"]}" style="object-position: {pos};">
            </div>
            <div class="article-card-body">
              <span class="article-tag tag-{e["cat"]}">{e["tag"]}</span>
              <h3>{e["title"]}</h3>
              <p>{e["excerpt"]}</p>
              <div class="article-card-footer">
                <span class="article-card-date">{month_label(e["date"])}</span>
                <span class="article-card-arrow">Läs mer <span>→</span></span>
              </div>
            </div>
          </a>'''
    if e.get("feed") == "full":
        content = f'<div class="diary-body">\n{markdown(e["body"])}\n            </div>'
    else:
        style = f' style="object-position: {pos};"'
        content = (f'<a href="{e["url"]}" class="diary-image">{picture(src, alt, style)}</a>\n'
                   f'            <p class="diary-excerpt">{e.get("excerpt", e["description"])}</p>\n'
                   f'            <a href="{e["url"]}" class="diary-more">Läs hela inlägget <span>→</span></a>')
    box = ig_box(e)
    return f'''          <article class="diary-post fade-in" data-cats="{cats}"{feat} id="{e["slug"]}">
            <div class="diary-meta"><span class="article-tag tag-{e["tags"][0]}">{tag_label(e)}</span><time datetime="{e["date"]}">{day_label(e["date"])}</time></div>
            <h2 class="diary-title"><a href="{e["url"]}">{e["title"]}</a></h2>
            {content}{chr(10) + box if box else ""}
          </article>'''


def feed(entries):
    path = ROOT / "magazine.html"
    h = path.read_text()
    if FEED_START not in h:
        raise SystemExit("magazine.html saknar FEED-markörerna")
    links = " · ".join(f'<a href="/magazine/tagg/{t}/">{l}</a>' for t, l in TAGS.items()
                       if any(t in e["tags"] for e in entries))
    inner = ("\n\n".join(feed_item(e, i == 0) for i, e in enumerate(entries))
             + f'\n\n          <p class="feed-links"><a href="/magazine/arkiv/">Arkiv</a> · Taggar: {links}</p>')
    h = re.sub(re.escape(FEED_START) + ".*?" + re.escape(FEED_END),
               lambda m: f"{FEED_START}\n{inner}\n          {FEED_END}", h, count=1, flags=re.S)
    h = re.sub(re.escape(FEATURED_START) + ".*?" + re.escape(FEATURED_END),
               lambda m: f"{FEATURED_START}\n{featured(entries[0])}\n        {FEATURED_END}", h, count=1, flags=re.S)
    write(path, h)


def stubs_and_sitemaps(posts):
    redirects = ROOT / "_redirects"
    r = redirects.read_text()
    news = ROOT / "news-sitemap.xml"
    n = news.read_text()
    for e in posts:
        s = e["slug"]
        stub = ROOT / f"{s}.html"
        if stub.exists() and f"url=/magazine/{s}/" not in stub.read_text():
            raise SystemExit(f"{s}.html finns redan och är en annan sida, byt slug på inlägget")
        write(stub, f'''<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="0;url=/magazine/{s}/">
<link rel="canonical" href="{SITE}/magazine/{s}/">
<title>Flyttad sida</title>
</head>
<body>
<script>window.location.replace("/magazine/{s}/");</script>
<p>Den här sidan har flyttat. <a href="/magazine/{s}/">Klicka här</a> om du inte skickas vidare automatiskt.</p>
</body>
</html>
''')
        if f"/{s} " not in r:
            r = r.rstrip("\n") + f"\n/{s} /magazine/{s}/ 301\n"
        if f"/magazine/{s}/</loc>" not in n:
            entry = f'''
  <url>
    <loc>{SITE}/magazine/{s}/</loc>
    <news:news>
      <news:publication>
        <news:name>Runclubs.se</news:name>
        <news:language>sv</news:language>
      </news:publication>
      <news:publication_date>{e["date"]}</news:publication_date>
      <news:title>{esc(e["title"])}</news:title>
    </news:news>
  </url>
'''
            n = n.replace('sitemap-news/0.9">\n', 'sitemap-news/0.9">\n' + entry, 1)
    write(redirects, r)
    write(news, n)


def main():
    entries = load_entries()
    posts = [e for e in entries if e["kind"] == "post"]
    print(f"{len(posts)} inlägg + {len(entries) - len(posts)} äldre artiklar")
    for e in posts:
        write(ROOT / "magazine" / e["slug"] / "index.html", post_page(e, entries))
    feed(entries)
    tag_pages(entries)
    archive_page(entries)
    stubs_and_sitemaps(posts)


if __name__ == "__main__":
    main()
