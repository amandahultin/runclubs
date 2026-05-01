"""inject_faq_html.py

Adds a visible FAQ accordion section to city pages and /om-oss.
Google requires FAQ content to be readable on the page — not just in JSON-LD.

Run from repo root:
    python3 inject_faq_html.py
"""

from pathlib import Path

ROOT = Path(__file__).parent

# ── FAQ content (must match inject_rich_schemas.py exactly) ──────────────────

FAQS: dict[str, list[tuple[str, str]]] = {
    "stockholm": [
        ("Vad kostar det att vara med i en run club i Stockholm?",
         "De flesta run clubs i Stockholm är helt gratis att delta i. Vissa clubs erbjuder betalda träningsprogram eller premium-pass, men grundkonceptet är öppet för alla."),
        ("Vilken nivå krävs för att vara med?",
         "De flesta löpargrupper i Stockholm välkomnar alla nivåer — från nybörjare till erfarna löpare. Många clubs har anpassade pass för olika tempo och distanser."),
        ("När och var samlas run clubs i Stockholm?",
         "Stockholms run clubs samlas på olika platser och tider beroende på club. Vanliga mötesplatser är Hagaparken, Djurgården, Östermalm och Södermalm. Kolla respektive clubs sida för aktuella tider."),
        ("Hur hittar jag rätt run club för mig i Stockholm?",
         "På Runclubs.se kan du filtrera Stockholms run clubs efter dag, nivå och stadsdel. Välj de kriterier som passar dig och hitta ditt crew direkt."),
        ("Kan jag ta med en vän som aldrig sprungit förut?",
         "Ja! De flesta run clubs välkomnar nybörjare och uppmuntrar till att ta med vänner. Social löpning är kärnan i run club-kulturen."),
    ],
    "goteborg": [
        ("Vad kostar det att vara med i en run club i Göteborg?",
         "De allra flesta run clubs i Göteborg är gratis att delta i. Du behöver bara dyka upp och vara redo att springa."),
        ("Vilken nivå krävs för att vara med i Göteborgs run clubs?",
         "Göteborgs run clubs är öppna för alla nivåer. Oavsett om du är nybörjare eller rutinerad löpare finns det en grupp som passar dig."),
        ("När samlas run clubs i Göteborg?",
         "Göteborg har run clubs som samlas på vardagar och helger. Kolla in varje clubs sida på Runclubs.se för aktuella tider och mötesplatser."),
        ("Hur hittar jag en löpargrupp i Göteborg?",
         "Runclubs.se listar alla kända run clubs i Göteborg med tider, startplatser och nivå. Bläddra bland clubs och hitta din matchning."),
        ("Finns det run clubs i Göteborg som fokuserar på tjejer?",
         "Ja, flera run clubs i Göteborg har pass riktade mot tjejer eller mixed grupper med inkluderande miljö. Se filtret på Göteborgs-sidan."),
    ],
    "malmo": [
        ("Vad kostar det att springa med en run club i Malmö?",
         "Malmös run clubs är gratis att delta i. Du anmäler dig enkelt via Strava eller Instagram och dyker upp på startplatsen."),
        ("Vilken nivå krävs för Malmös run clubs?",
         "Malmös run clubs tar emot alla — nybörjare som vill komma igång och erfarna löpare som vill ha sällskap."),
        ("Var samlas run clubs i Malmö?",
         "Malmös run clubs samlas på centrala platser som Stortorget och Pildammsparken. Se varje clubs sida för exakt startplats."),
        ("Hur ofta kör run clubs i Malmö sina pass?",
         "De flesta run clubs i Malmö kör återkommande veckopass. Frekvensen varierar — en till tre gånger i veckan är vanligt."),
    ],
    "om-oss": [
        ("Vad är Runclubs.se?",
         "Runclubs.se är Sveriges samlade guide till run clubs och löpargrupper. Vi listar clubs i Stockholm, Göteborg och Malmö med tider, startplatser och nivå så att du enkelt hittar rätt grupp."),
        ("Hur lägger jag till min run club på Runclubs.se?",
         "Maila oss på amanda@runclubs.se med information om din club — namn, startplats, tider och kontaktlänkar. Vi lägger upp er gratis."),
        ("Är det gratis att använda Runclubs.se?",
         "Ja, Runclubs.se är helt gratis för löpare att använda. Vi tar inte heller betalt av clubs för att listas."),
        ("Hur ofta uppdateras eventinformationen?",
         "Eventdata uppdateras automatiskt varje morgon från Strava och vårt eget kalkylblad. Du ser alltid de senaste passen."),
        ("Täcker ni fler städer än Stockholm, Göteborg och Malmö?",
         "I nuläget fokuserar vi på Sveriges tre största städer. Fler städer är på väg — hör av dig om du vill se din stad på sajten."),
    ],
}

# ── CSS (injected once per page, before </style> or before </head>) ───────────

FAQ_CSS = """
    /* ── FAQ ─────────────────────────────── */
    .faq-section { max-width: 780px; margin: 0 auto; padding: 4rem 2rem; }
    .faq-section .section-label { color: #D4715E; font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase; font-weight: 600; margin-bottom: 0.75rem; }
    .faq-section h2 { font-family: 'Archivo Black', sans-serif; font-size: clamp(22px, 3vw, 30px); color: #1C2A45; margin-bottom: 2rem; }
    .faq-item { border-bottom: 1px solid #F0E0DC; }
    .faq-item:first-of-type { border-top: 1px solid #F0E0DC; }
    .faq-question { width: 100%; background: none; border: none; text-align: left; padding: 1.25rem 0; display: flex; justify-content: space-between; align-items: center; gap: 1rem; cursor: pointer; font-family: 'DM Sans', sans-serif; font-size: 16px; font-weight: 600; color: #1C2A45; }
    .faq-question:hover { color: #D4715E; }
    .faq-icon { flex-shrink: 0; width: 20px; height: 20px; border-radius: 50%; border: 1.5px solid currentColor; display: flex; align-items: center; justify-content: center; transition: transform 0.25s; }
    .faq-icon::after { content: '+'; font-size: 14px; line-height: 1; }
    .faq-item.open .faq-icon { transform: rotate(45deg); }
    .faq-answer { max-height: 0; overflow: hidden; transition: max-height 0.3s ease; }
    .faq-answer p { padding: 0 0 1.25rem; font-size: 15px; line-height: 1.7; color: #555; }
"""

# ── HTML builder ──────────────────────────────────────────────────────────────

def build_faq_html(slug: str) -> str:
    items = []
    for i, (question, answer) in enumerate(FAQS[slug]):
        items.append(
            f'      <div class="faq-item">\n'
            f'        <button class="faq-question" aria-expanded="false" aria-controls="faq-answer-{slug}-{i}">\n'
            f'          {question}\n'
            f'          <span class="faq-icon" aria-hidden="true"></span>\n'
            f'        </button>\n'
            f'        <div class="faq-answer" id="faq-answer-{slug}-{i}" role="region">\n'
            f'          <p>{answer}</p>\n'
            f'        </div>\n'
            f'      </div>'
        )

    label = "Vanliga frågor"
    heading = "Frågor och svar"

    return (
        f'\n  <!-- FAQ -->\n'
        f'  <section class="faq-section fade-in" aria-labelledby="faq-heading-{slug}">\n'
        f'    <div class="section-label">{label}</div>\n'
        f'    <h2 id="faq-heading-{slug}">{heading}</h2>\n'
        + "\n".join(items) + "\n"
        f'  </section>\n'
    )

FAQ_JS = """
  <script>
    // FAQ accordion
    document.querySelectorAll('.faq-question').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var item   = btn.closest('.faq-item');
        var answer = item.querySelector('.faq-answer');
        var isOpen = item.classList.contains('open');
        // Close all
        document.querySelectorAll('.faq-item.open').forEach(function(el) {
          el.classList.remove('open');
          el.querySelector('.faq-answer').style.maxHeight = null;
          el.querySelector('.faq-question').setAttribute('aria-expanded', 'false');
        });
        // Open clicked (if it was closed)
        if (!isOpen) {
          item.classList.add('open');
          answer.style.maxHeight = answer.scrollHeight + 'px';
          btn.setAttribute('aria-expanded', 'true');
        }
      });
    });
  </script>"""

# ── Injection ─────────────────────────────────────────────────────────────────

def inject(slug: str) -> None:
    path = ROOT / f"{slug}.html"
    if not path.exists():
        print(f"  ⚠ {slug}.html not found")
        return

    html = path.read_text(encoding="utf-8")

    if 'class="faq-section' in html:
        print(f"  · FAQ section already present in {slug}.html")
        return

    # 1. Add CSS before closing </style> (first one)
    html = html.replace("  </style>", FAQ_CSS + "  </style>", 1)

    # 2. Add FAQ section before </main>
    faq_html = build_faq_html(slug)
    html = html.replace("  </main>", faq_html + "  </main>", 1)

    # 3. Add JS before </body> or last </script>
    if "</body>" in html:
        html = html.replace("</body>", FAQ_JS + "\n</body>", 1)
    else:
        # fallback: before last </html>
        html = html.replace("</html>", FAQ_JS + "\n</html>", 1)

    path.write_text(html, encoding="utf-8")
    print(f"  ✓ FAQ section added → {slug}.html ({len(FAQS[slug])} Q&As)")


def main() -> None:
    print("\n── Adding visible FAQ sections ─────────────────────────────")
    for slug in FAQS:
        inject(slug)
    print()


if __name__ == "__main__":
    main()
