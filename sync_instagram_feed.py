"""Fetch the latest Instagram posts for the connected Business account via
Meta's Instagram Graph API, save them as square thumbnails, and write
posts.json describing them — all into instagram/feed/. The ig-feed-card on
the homepage fetches posts.json client-side to render a live feed. Run by
.github/workflows/instagram-feed-sync.yml on a schedule.

Requires env vars IG_ACCESS_TOKEN (long-lived token) and IG_USER_ID
(Instagram Business Account ID) for the @runclubs.se account.

Thumbnails are re-hosted locally (not linked straight to Instagram's CDN)
because Instagram's media URLs are signed and expire after a few days.
"""
import io
import json
import os

import requests
from PIL import Image

TOKEN = os.environ["IG_ACCESS_TOKEN"]
USER_ID = os.environ["IG_USER_ID"]
OUT_DIR = os.path.join(os.path.dirname(__file__), "instagram", "feed")
GRAPH_VERSION = "v21.0"
POST_COUNT = 6


def main():
    resp = requests.get(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{USER_ID}/media",
        params={
            "fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp",
            "access_token": TOKEN,
            "limit": 12,
        },
        timeout=30,
    )
    resp.raise_for_status()
    items = [
        item for item in resp.json().get("data", [])
        if item.get("media_type") != "VIDEO" or item.get("thumbnail_url")
    ]
    # Don't rely on the API returning newest-first — sort explicitly so
    # slot 1 (top-left in the grid) is always the most recent post.
    items.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    items = items[:POST_COUNT]

    if not items:
        print("No media returned, leaving existing feed untouched.")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    posts = []
    for i, item in enumerate(items, start=1):
        url = item.get("thumbnail_url") or item.get("media_url")
        if not url:
            continue
        img_resp = requests.get(url, timeout=30)
        img_resp.raise_for_status()
        im = Image.open(io.BytesIO(img_resp.content)).convert("RGB")

        w, h = im.size
        side = min(w, h)
        left, top = (w - side) // 2, (h - side) // 2
        im = im.crop((left, top, left + side, top + side))
        im.thumbnail((640, 640), Image.LANCZOS)
        im.save(os.path.join(OUT_DIR, f"{i}.jpg"), quality=82, optimize=True)
        print(f"Saved {i}.jpg from {item.get('permalink')}")

        posts.append({
            "id": item.get("id"),
            "caption": item.get("caption", ""),
            "mediaType": item.get("media_type"),
            "imageUrl": f"instagram/feed/{i}.jpg",
            "permalink": item.get("permalink"),
            "timestamp": item.get("timestamp"),
        })

    with open(os.path.join(OUT_DIR, "posts.json"), "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    print(f"Wrote posts.json with {len(posts)} posts.")


if __name__ == "__main__":
    main()
