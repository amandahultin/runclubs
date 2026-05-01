"""cwv_optimise.py

Core Web Vitals pass — targets LCP < 1.2 s and TBT < 200 ms.

Changes applied to every HTML file that contains the GTM snippet:

1. GTM deferred  — inline snippet replaced with DOMContentLoaded +
   1 s setTimeout so gtm.js loads after LCP has painted.

Can also target specific files:
    python3 cwv_optimise.py file.html [file2.html ...]

Run on all files (no args):
    python3 cwv_optimise.py

Safe to re-run (idempotent).
"""

from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).parent

# ── Patterns to identify & skip already-patched files ────────────────────────

GTM_OLD = '<!-- Google Tag Manager -->\n<script>(function(w,d,s,l,i)'
GTM_NEW_MARKER = '<!-- Google Tag Manager (deferred) -->'

# ── Replacement strings ───────────────────────────────────────────────────────

GTM_OLD_BLOCK = (
    '<!-- Google Tag Manager -->\n'
    '<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({\'gtm.start\':\n'
    'new Date().getTime(),event:\'gtm.js\'});var f=d.getElementsByTagName(s)[0],\n'
    'j=d.createElement(s),dl=l!=\'dataLayer\'?\'&l=\'+l:\'\';j.async=true;j.src=\n'
    '\'https://www.googletagmanager.com/gtm.js?id=\'+i+dl;f.parentNode.insertBefore(j,f);\n'
    '})(window,document,\'script\',\'dataLayer\',\'GTM-TPSCMPZT\');</script>\n'
    '<!-- End Google Tag Manager -->'
)

GTM_NEW_BLOCK = (
    '<!-- Google Tag Manager (deferred) -->\n'
    '<script>\n'
    'window.dataLayer=window.dataLayer||[];\n'
    'window.dataLayer.push({\'gtm.start\':new Date().getTime(),event:\'gtm.js\'});\n'
    'document.addEventListener(\'DOMContentLoaded\',function(){\n'
    '  setTimeout(function(){\n'
    '    var s=document.createElement(\'script\');\n'
    '    s.async=true;\n'
    '    s.src=\'https://www.googletagmanager.com/gtm.js?id=GTM-TPSCMPZT\';\n'
    '    document.head.appendChild(s);\n'
    '  },1000);\n'
    '});\n'
    '</script>\n'
    '<!-- End Google Tag Manager -->'
)


# ── Per-file transform ────────────────────────────────────────────────────────

def transform(html: str) -> tuple[str, list[str]]:
    if GTM_OLD_BLOCK not in html:
        return html, []   # file doesn't have GTM at all — skip

    changes: list[str] = []
    already_deferred = GTM_NEW_MARKER in html

    # 1. Defer GTM
    if not already_deferred:
        html = html.replace(GTM_OLD_BLOCK, GTM_NEW_BLOCK, 1)
        changes.append("GTM deferred")

    return html, changes


# ── Main ──────────────────────────────────────────────────────────────────────

def main(targets: list[Path] | None = None) -> None:
    """Apply CWV transforms.

    targets: specific files to process. When None, processes all HTML
             files in the repo (excluding drafts/mockups).
             Can also be driven from the CLI: python3 cwv_optimise.py a.html b.html
    """
    print("\n── Core Web Vitals pass ────────────────────────────────────")

    if targets is not None:
        files = [p for p in targets if p.exists()]
    else:
        skip = {'mockup-botanik', 'mockup-korall', 'mockup-lila', 'mockup-solsken',
                'index-feminine', 'index-feminine-v2', 'placeholder-preview', 'klubb'}
        files = [
            p for p in sorted(ROOT.rglob("*.html"))
            if p.stem not in skip and 'node_modules' not in str(p)
        ]

    updated = skipped = 0
    for path in files:
        html = path.read_text(encoding="utf-8")
        new_html, changes = transform(html)
        if changes:
            path.write_text(new_html, encoding="utf-8")
            rel = path.relative_to(ROOT)
            print(f"  ✓ {rel}")
            for c in changes:
                print(f"      · {c}")
            updated += 1
        else:
            skipped += 1

    print(f"\nDone. {updated} files updated, {skipped} skipped.\n")


if __name__ == "__main__":
    import sys
    cli_targets = [Path(a) for a in sys.argv[1:]] if sys.argv[1:] else None
    main(cli_targets)
