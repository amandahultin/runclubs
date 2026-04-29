const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageNumber, Header, Footer, PageBreak, ExternalHyperlink
} = require('./node_modules/docx');

const SITE_DIR = '/sessions/nice-bold-heisenberg/mnt/loparklubbar';
const config = JSON.parse(fs.readFileSync(path.join(SITE_DIR, 'seo-config.json'), 'utf8'));

// ─── HELPERS ────────────────────────────────────────────────────────────────

function replaceTag(html, tagPattern, newTag) {
  const replaced = html.replace(tagPattern, newTag);
  return replaced;
}

function updateMeta(html, name, newContent) {
  // Handle name="..." and property="..." variants
  const namePattern = new RegExp(
    `<meta\\s+(name|property)=["']${name}["'][^>]*content=["'][^"']*["'][^>]*>|` +
    `<meta\\s+content=["'][^"']*["'][^>]*(name|property)=["']${name}["'][^>]*>`,
    'gi'
  );
  const escaped = newContent.replace(/&/g, '&amp;').replace(/"/g, '&quot;');

  if (name.startsWith('og:') || name.startsWith('twitter:')) {
    const prop = name.startsWith('og:') ? 'property' : 'name';
    const newTag = `<meta ${prop}="${name}" content="${escaped}">`;
    if (namePattern.test(html)) {
      return html.replace(namePattern, newTag);
    } else {
      // Insert before </head>
      return html.replace('</head>', `  ${newTag}\n</head>`);
    }
  } else {
    const newTag = `<meta name="${name}" content="${escaped}">`;
    if (namePattern.test(html)) {
      return html.replace(namePattern, newTag);
    } else {
      return html.replace('</head>', `  ${newTag}\n</head>`);
    }
  }
}

function updateTitle(html, newTitle) {
  const escaped = newTitle.replace(/&/g, '&amp;');
  return html.replace(/<title>[^<]*<\/title>/i, `<title>${escaped}</title>`);
}

function addDataNoSnippetToFooter(html) {
  // Add data-nosnippet to the footer-brand div to prevent Google from
  // using footer text as snippet (fixes the "Städer" concat bug)
  return html.replace(
    '<div class="footer-brand">',
    '<div class="footer-brand" data-nosnippet>'
  );
}

// ─── APPLY SEO CONFIG TO ALL HTML FILES ─────────────────────────────────────

const results = [];

for (const [filename, seo] of Object.entries(config.pages)) {
  const filePath = path.join(SITE_DIR, filename);
  if (!fs.existsSync(filePath)) {
    console.log(`SKIP (not found): ${filename}`);
    continue;
  }

  let html = fs.readFileSync(filePath, 'utf8');

  // Capture current values for the report
  const oldTitle = (html.match(/<title>([^<]*)<\/title>/i) || [])[1] || '';
  const oldDesc = (html.match(/name=["']description["'][^>]*content=["']([^"']*)["']/i) ||
                   html.match(/content=["']([^"']*)["'][^>]*name=["']description["']/i) || [])[1] || '';

  // Apply updates
  html = updateTitle(html, seo.title);
  html = updateMeta(html, 'description', seo.description);
  html = updateMeta(html, 'og:title', seo.og_title);
  html = updateMeta(html, 'og:description', seo.og_description);
  html = updateMeta(html, 'twitter:title', seo.twitter_title);
  html = updateMeta(html, 'twitter:description', seo.twitter_description);

  // Fix Städer bug on index.html
  if (filename === 'index.html') {
    html = addDataNoSnippetToFooter(html);
  }

  fs.writeFileSync(filePath, html, 'utf8');

  results.push({
    file: filename,
    oldTitle: oldTitle.trim(),
    newTitle: seo.title,
    oldDesc: oldDesc.trim(),
    newDesc: seo.description,
    titleLenOld: oldTitle.trim().length,
    titleLenNew: seo.title.length,
    descLenOld: oldDesc.trim().length,
    descLenNew: seo.description.length,
  });

  console.log(`✓ ${filename}`);
}

console.log(`\nUpdated ${results.length} files.\n`);

// ─── GENERATE WORD DOCUMENT ─────────────────────────────────────────────────

const BLUE_DARK = "1B4F72";
const RED = "C0392B";
const ORANGE = "E67E22";
const GREEN = "27AE60";
const GREY = "F2F3F4";
const RED_BG = "FADBD8";
const GREEN_BG = "D5F5E3";
const YELLOW_BG = "FEF9E7";
const ORANGE_BG = "FDEBD0";
const border = { style: BorderStyle.SINGLE, size: 1, color: "DDDDDD" };
const borders = { top: border, bottom: border, left: border, right: border };

function cell(text, width, opts = {}) {
  const { bg = "FFFFFF", bold = false, color = "1A1A1A", size = 18 } = opts;
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: bg, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({
      children: [new TextRun({ text: String(text), font: "Arial", size, bold, color })]
    })]
  });
}

function hdr(text, width) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: BLUE_DARK, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({
      children: [new TextRun({ text, font: "Arial", size: 18, bold: true, color: "FFFFFF" })]
    })]
  });
}

function p(text, opts = {}) {
  return new Paragraph({
    spacing: { before: 80, after: 80 },
    children: [new TextRun({ text, font: "Arial", size: 22, color: "1A1A1A", ...opts })]
  });
}

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 160 },
    children: [new TextRun({ text, font: "Arial", size: 32, bold: true, color: BLUE_DARK })]
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 120 },
    children: [new TextRun({ text, font: "Arial", size: 26, bold: true, color: "1A1A1A" })]
  });
}

function sp() { return new Paragraph({ children: [new TextRun("")] }); }

function lenBadge(len, type) {
  // type: 'title' = 50-60 ideal, 'desc' = 145-160 ideal
  if (type === 'title') {
    if (len === 0) return `${len} ⚠️ saknas`;
    if (len > 60) return `${len} ⚠️ för lång`;
    if (len < 30) return `${len} ⚠️ för kort`;
    return `${len} ✓`;
  } else {
    if (len === 0) return `${len} ❌ saknas`;
    if (len > 160) return `${len} ⚠️ för lång`;
    if (len < 100) return `${len} ⚠️ för kort`;
    return `${len} ✓`;
  }
}

function rowBg(len, type) {
  if (type === 'title') {
    if (len === 0 || len > 60) return ORANGE_BG;
    return "FFFFFF";
  } else {
    if (len === 0) return RED_BG;
    if (len > 160 || len < 100) return ORANGE_BG;
    return "FFFFFF";
  }
}

// Split results into main pages and club pages
const mainPages = results.filter(r =>
  ['index.html','stockholm.html','goteborg.html','malmo.html',
   'running-events.html','stockholm-running-events.html',
   'goteborg-running-events.html','malmo-running-events.html',
   'loppkalender.html','om-oss.html','samarbeta.html',
   'kontakt.html','nyheter.html','lopning-for-tjejer.html',
   'tjejer-tar-over-lopsparen.html','stockholm-marathon-2026-slutsalt.html'
  ].includes(r.file)
);
const clubPages = results.filter(r => !mainPages.includes(r));

function buildTable(rows) {
  const W = [2000, 900, 3200, 900, 3200]; // widths sum = ~10200 but we use 9360
  const WW = [1800, 850, 3050, 850, 3050]; // sum = 9600 ≈ content width
  return new Table({
    width: { size: 9600, type: WidthType.DXA },
    columnWidths: WW,
    rows: [
      new TableRow({ tableHeader: true, children: [
        hdr("Sida", WW[0]),
        hdr("Nuv. titel (tecken)", WW[1]),
        hdr("Föreslagen titel", WW[2]),
        hdr("Nuv. desc (tecken)", WW[3]),
        hdr("Föreslagen description", WW[4]),
      ]}),
      ...rows.map(r => new TableRow({ children: [
        cell(r.file.replace('.html',''), WW[0], { bold: true, size: 16 }),
        new TableCell({
          borders,
          width: { size: WW[1], type: WidthType.DXA },
          shading: { fill: rowBg(r.titleLenOld,'title'), type: ShadingType.CLEAR },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [
            new Paragraph({ children: [new TextRun({ text: r.oldTitle, font: "Arial", size: 16, color: "555555" })] }),
            new Paragraph({ children: [new TextRun({ text: lenBadge(r.titleLenOld,'title'), font: "Arial", size: 16, bold: true, color: r.titleLenOld > 60 || r.titleLenOld === 0 ? ORANGE : GREEN })] }),
          ]
        }),
        new TableCell({
          borders,
          width: { size: WW[2], type: WidthType.DXA },
          shading: { fill: GREEN_BG, type: ShadingType.CLEAR },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [
            new Paragraph({ children: [new TextRun({ text: r.newTitle, font: "Arial", size: 16, bold: true, color: "1A1A1A" })] }),
            new Paragraph({ children: [new TextRun({ text: lenBadge(r.titleLenNew,'title'), font: "Arial", size: 16, color: GREEN })] }),
          ]
        }),
        new TableCell({
          borders,
          width: { size: WW[3], type: WidthType.DXA },
          shading: { fill: rowBg(r.descLenOld,'desc'), type: ShadingType.CLEAR },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [
            new Paragraph({ children: [new TextRun({ text: r.oldDesc || '(saknas)', font: "Arial", size: 16, color: r.oldDesc ? "555555" : RED })] }),
            new Paragraph({ children: [new TextRun({ text: lenBadge(r.descLenOld,'desc'), font: "Arial", size: 16, bold: true, color: r.descLenOld === 0 ? RED : r.descLenOld > 160 || r.descLenOld < 100 ? ORANGE : GREEN })] }),
          ]
        }),
        new TableCell({
          borders,
          width: { size: WW[4], type: WidthType.DXA },
          shading: { fill: GREEN_BG, type: ShadingType.CLEAR },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [
            new Paragraph({ children: [new TextRun({ text: r.newDesc, font: "Arial", size: 16, bold: true, color: "1A1A1A" })] }),
            new Paragraph({ children: [new TextRun({ text: lenBadge(r.descLenNew,'desc'), font: "Arial", size: 16, color: GREEN })] }),
          ]
        }),
      ]}))
    ]
  });
}

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial" }, paragraph: { spacing: { before: 360, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial" }, paragraph: { spacing: { before: 280, after: 120 }, outlineLevel: 1 } },
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 16838, height: 11906 }, // A4 liggande
        margin: { top: 1000, right: 1000, bottom: 1000, left: 1000 },
        orientation: "landscape"
      }
    },
    headers: {
      default: new Header({ children: [new Paragraph({
        border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: BLUE_DARK, space: 1 } },
        children: [
          new TextRun({ text: "SEO meta descriptions — runclubs.se", font: "Arial", size: 18, color: "666666" }),
          new TextRun({ text: "\t29 april 2026  •  Nuläge vs förslag", font: "Arial", size: 18, color: "999999" }),
        ],
        tabStops: [{ type: "right", position: 12000 }]
      })] })
    },
    footers: {
      default: new Footer({ children: [new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [
          new TextRun({ text: "Sida ", font: "Arial", size: 16, color: "999999" }),
          new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 16, color: "999999" }),
          new TextRun({ text: " av ", font: "Arial", size: 16, color: "999999" }),
          new TextRun({ children: [PageNumber.TOTAL_PAGES], font: "Arial", size: 16, color: "999999" }),
        ]
      })] })
    },
    children: [
      // Title
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 200, after: 80 },
        children: [new TextRun({ text: "SEO meta descriptions — runclubs.se", font: "Arial", size: 48, bold: true, color: BLUE_DARK })]
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 0, after: 40 },
        children: [new TextRun({ text: "Nuläge vs förslag enligt Googles SEO-guide", font: "Arial", size: 24, color: "666666" })]
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 0, after: 200 },
        children: [new TextRun({ text: "29 april 2026  •  Samtliga ändringar är redan applicerade på sajten", font: "Arial", size: 20, color: "999999" })]
      }),

      // Google guidelines box
      new Table({
        width: { size: 9600, type: WidthType.DXA },
        columnWidths: [4800, 4800],
        rows: [
          new TableRow({ children: [
            new TableCell({
              borders,
              width: { size: 4800, type: WidthType.DXA },
              shading: { fill: "EAF2FF", type: ShadingType.CLEAR },
              margins: { top: 160, bottom: 160, left: 200, right: 200 },
              children: [
                new Paragraph({ children: [new TextRun({ text: "Googles guide — titlar", font: "Arial", size: 20, bold: true, color: BLUE_DARK })] }),
                sp(),
                new Paragraph({ children: [new TextRun({ text: "• 50–60 tecken (Google trunkerar längre)", font: "Arial", size: 18, color: "1A1A1A" })] }),
                new Paragraph({ children: [new TextRun({ text: "• Primärt sökord tidigt, helst i första halvan", font: "Arial", size: 18, color: "1A1A1A" })] }),
                new Paragraph({ children: [new TextRun({ text: "• Unikt per sida — aldrig identiska titlar", font: "Arial", size: 18, color: "1A1A1A" })] }),
                new Paragraph({ children: [new TextRun({ text: "• Varumärket (Runclubs.se) sist, separerat med |", font: "Arial", size: 18, color: "1A1A1A" })] }),
                new Paragraph({ children: [new TextRun({ text: "• Undvik generiska ord som 'hem', 'sida', 'välkommen'", font: "Arial", size: 18, color: "1A1A1A" })] }),
              ]
            }),
            new TableCell({
              borders,
              width: { size: 4800, type: WidthType.DXA },
              shading: { fill: "EAF2FF", type: ShadingType.CLEAR },
              margins: { top: 160, bottom: 160, left: 200, right: 200 },
              children: [
                new Paragraph({ children: [new TextRun({ text: "Googles guide — meta descriptions", font: "Arial", size: 20, bold: true, color: BLUE_DARK })] }),
                sp(),
                new Paragraph({ children: [new TextRun({ text: "• 145–160 tecken (Google trunkerar längre)", font: "Arial", size: 18, color: "1A1A1A" })] }),
                new Paragraph({ children: [new TextRun({ text: "• Primärt sökord i första 80 tecknen", font: "Arial", size: 18, color: "1A1A1A" })] }),
                new Paragraph({ children: [new TextRun({ text: "• Tydlig CTA — 'Hitta', 'Dyk in', 'Hoppa på', 'Anmäl dig'", font: "Arial", size: 18, color: "1A1A1A" })] }),
                new Paragraph({ children: [new TextRun({ text: "• Unik per sida — Google ignorerar duplicerade", font: "Arial", size: 18, color: "1A1A1A" })] }),
                new Paragraph({ children: [new TextRun({ text: "• Google kan byta ut om sidan stämmer bättre med sökordet", font: "Arial", size: 18, color: "1A1A1A" })] }),
              ]
            }),
          ]})
        ]
      }),

      sp(),

      // Städer bug notice
      new Table({
        width: { size: 9600, type: WidthType.DXA },
        columnWidths: [9600],
        rows: [new TableRow({ children: [new TableCell({
          borders,
          width: { size: 9600, type: WidthType.DXA },
          shading: { fill: RED_BG, type: ShadingType.CLEAR },
          margins: { top: 120, bottom: 120, left: 200, right: 200 },
          children: [
            new Paragraph({ children: [new TextRun({ text: "Bugg fixad — \"Städer\" i Googles snippet", font: "Arial", size: 20, bold: true, color: RED })] }),
            new Paragraph({ children: [new TextRun({ text: "Google hämtade footer-texten + rubriken <h4>Städer</h4> och kombinerade dem som snippet. Åtgärd: data-nosnippet lagd på footer-brand. Google läser nu bara meta description-taggen.", font: "Arial", size: 18, color: "1A1A1A" })] }),
          ]
        })]})],
      }),

      sp(),
      new Paragraph({ children: [new PageBreak()] }),

      h1("Huvudsidor"),
      sp(),
      buildTable(mainPages),

      sp(),
      new Paragraph({ children: [new PageBreak()] }),

      h1("Klubbsidor"),
      sp(),
      buildTable(clubPages),

      sp(),
      new Paragraph({ children: [new PageBreak()] }),

      h1("Så hanterar du SEO-texterna framåt"),
      sp(),
      h2("seo-config.json — ditt centrala SEO-verktyg"),
      p("Filen seo-config.json i din sajt-mapp är nu din enda källa för alla meta-taggar. Du behöver aldrig mer redigera HTML-filer direkt för att ändra titlar eller descriptions."),
      sp(),
      new Table({
        width: { size: 9600, type: WidthType.DXA },
        columnWidths: [4800, 4800],
        rows: [
          new TableRow({ children: [
            new TableCell({ borders, width: { size: 4800, type: WidthType.DXA }, shading: { fill: YELLOW_BG, type: ShadingType.CLEAR }, margins: { top: 120, bottom: 120, left: 200, right: 200 },
              children: [
                new Paragraph({ children: [new TextRun({ text: "Ändra en description", font: "Arial", size: 20, bold: true, color: "B7950B" })] }),
                sp(),
                new Paragraph({ children: [new TextRun({ text: "1. Öppna seo-config.json", font: "Arial", size: 18, color: "1A1A1A" })] }),
                new Paragraph({ children: [new TextRun({ text: "2. Hitta sidans namn (t.ex. \"stockholm.html\")", font: "Arial", size: 18, color: "1A1A1A" })] }),
                new Paragraph({ children: [new TextRun({ text: "3. Ändra \"description\"-värdet", font: "Arial", size: 18, color: "1A1A1A" })] }),
                new Paragraph({ children: [new TextRun({ text: "4. Spara — kör sedan: node apply-seo.js", font: "Arial", size: 18, color: "1A1A1A" })] }),
              ]
            }),
            new TableCell({ borders, width: { size: 4800, type: WidthType.DXA }, shading: { fill: GREEN_BG, type: ShadingType.CLEAR }, margins: { top: 120, bottom: 120, left: 200, right: 200 },
              children: [
                new Paragraph({ children: [new TextRun({ text: "Lägg till ny sida", font: "Arial", size: 20, bold: true, color: GREEN })] }),
                sp(),
                new Paragraph({ children: [new TextRun({ text: "1. Öppna seo-config.json", font: "Arial", size: 18, color: "1A1A1A" })] }),
                new Paragraph({ children: [new TextRun({ text: "2. Kopiera ett befintligt block", font: "Arial", size: 18, color: "1A1A1A" })] }),
                new Paragraph({ children: [new TextRun({ text: "3. Byt filnamn och fyll i title/description", font: "Arial", size: 18, color: "1A1A1A" })] }),
                new Paragraph({ children: [new TextRun({ text: "4. Kör: node apply-seo.js", font: "Arial", size: 18, color: "1A1A1A" })] }),
              ]
            }),
          ]})
        ]
      }),
      sp(),
      p("Filen apply-seo.js finns i din sajt-mapp. Du kan också be Claude i Cowork att 'uppdatera SEO för [sidnamn]' — då uppdateras config-filen och skriptet körs automatiskt.", { italic: true, color: "666666" }),
    ]
  }]
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync('/sessions/nice-bold-heisenberg/mnt/loparklubbar/SEO-meta-descriptions.docx', buf);
  console.log('Word-dokument sparat: SEO-meta-descriptions.docx');
});
