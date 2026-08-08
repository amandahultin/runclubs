"""Render Instagram-ready PNGs from standalone HTML design files.

Unlike generate_instagram_event_images.py (which fills Jinja templates with
event data), this script takes already-finished HTML files — e.g. exported
from a Claude Design project into posts/<week>/ — and screenshots each one
as-is. Each file must declare its own render size via data-width/data-height
on the <html> tag (same convention as instagram/templates/*.html):

    <html data-width="1080" data-height="1350">

Usage:
    python generate_design_post_images.py posts/vecka33
    python generate_design_post_images.py posts/vecka33 --out-dir instagram/generated

Dependencies: playwright (chromium).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_DIMS_RE = re.compile(r'data-width="(\d+)"\s+data-height="(\d+)"')


async def render_file(html_path: Path, out_dir: Path, browser) -> Path:
    html = html_path.read_text(encoding="utf-8")
    match = _DIMS_RE.search(html)
    if not match:
        raise ValueError(
            f"{html_path}: missing data-width/data-height on the <html> tag"
        )
    width, height = int(match.group(1)), int(match.group(2))

    png_path = out_dir / f"{html_path.stem}.png"
    ctx = await browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
    page = await ctx.new_page()
    await page.goto(f"file://{html_path.resolve()}")
    await page.evaluate("document.fonts.ready")
    await page.wait_for_timeout(400)
    await page.screenshot(path=str(png_path), clip={"x": 0, "y": 0, "width": width, "height": height})
    await ctx.close()
    return png_path


async def render_all(html_paths: list[Path], out_dir: Path) -> list[Path]:
    from playwright.async_api import async_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            for html_path in html_paths:
                png_path = await render_file(html_path, out_dir, browser)
                log.info("Rendered %s -> %s", html_path.name, png_path.name)
                paths.append(png_path)
        finally:
            await browser.close()

    return paths


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_dir", help="Folder of .html design files, e.g. posts/vecka33")
    ap.add_argument("--out-dir", default=None, help="Where to write PNGs (defaults to input_dir)")
    args = ap.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        sys.exit(f"No such directory: {input_dir}")

    html_paths = sorted(input_dir.glob("*.html"))
    if not html_paths:
        log.info("No .html files found in %s — nothing to render", input_dir)
        return

    out_dir = Path(args.out_dir) if args.out_dir else input_dir
    asyncio.run(render_all(html_paths, out_dir))


if __name__ == "__main__":
    main()
