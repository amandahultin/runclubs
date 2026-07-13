"""update_generator_templates.py

Updates the embedded HTML templates inside the 5 generator scripts so
their output matches the current site standards:

  - GTM: deferred (DOMContentLoaded + 1 s setTimeout)

Run once from repo root:
    python3 update_generator_templates.py

The generators now permanently produce correct HTML — the cwv_optimise.py
post-processing step in each workflow is a belt-and-braces safety net.
"""

from pathlib import Path

ROOT = Path(__file__).parent

TARGETS = [
    "generate_running_events.py",
    "generate_stockholm_events.py",
    "generate_goteborg_events.py",
    "generate_ovriga_landet_events.py",
    "generate_kommande_lopp.py",
]

# ── Replacement pairs (old, new) ──────────────────────────────────────────────
# Strings are exactly as they appear in the Python source files.
# CSS curly braces are doubled ({{ }}) because the templates use f-strings.

SWAPS = [

    # 1. GTM: blocking inline snippet → deferred
    (
        "<!-- Google Tag Manager -->\n"
        "<script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':\n"
        "new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],\n"
        "j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=\n"
        "'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);\n"
        "}})(window,document,'script','dataLayer','GTM-TPSCMPZT');</script>\n"
        "<!-- End Google Tag Manager -->",

        "<!-- Google Tag Manager (deferred) -->\n"
        "<script>\n"
        "window.dataLayer=window.dataLayer||[];\n"
        "window.dataLayer.push({{'gtm.start':new Date().getTime(),event:'gtm.js'}});\n"
        "document.addEventListener('DOMContentLoaded',function(){{\n"
        "  setTimeout(function(){{\n"
        "    var s=document.createElement('script');\n"
        "    s.async=true;\n"
        "    s.src='https://www.googletagmanager.com/gtm.js?id=GTM-TPSCMPZT';\n"
        "    document.head.appendChild(s);\n"
        "  }},1000);\n"
        "}});\n"
        "</script>\n"
        "<!-- End Google Tag Manager -->"
    ),

]


def patch(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    orig = text
    applied: list[str] = []

    for old, new in SWAPS:
        if old in text:
            text = text.replace(old, new)
            applied.append(old[:60].replace("\n", "↵").strip() + "…")

    if text != orig:
        path.write_text(text, encoding="utf-8")
    return applied


def main() -> None:
    print("\n── Updating generator templates ────────────────────────────")
    for name in TARGETS:
        path = ROOT / name
        if not path.exists():
            print(f"  · {name}  (not found — skipped)")
            continue
        changes = patch(path)
        if changes:
            print(f"  ✓ {name}  ({len(changes)} changes)")
            for c in changes:
                print(f"      · {c}")
        else:
            print(f"  · {name}  (already up to date)")
    print()


if __name__ == "__main__":
    main()
