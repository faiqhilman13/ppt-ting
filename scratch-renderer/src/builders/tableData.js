const {
  SLIDE_W,
  MARGIN,
  normalizeLines,
  addCard,
  addAccentBar,
} = require("../helpers");

const VARIANT_COUNT = 2;

function _parseTableRows(text) {
  const lines = normalizeLines(text);
  // Try to detect delimiter-separated rows (pipe, tab, or comma)
  return lines.map((line) => {
    if (line.includes("|")) return line.split("|").map((c) => c.trim()).filter(Boolean);
    if (line.includes("\t")) return line.split("\t").map((c) => c.trim());
    if (line.includes(",") && line.split(",").length >= 2)
      return line.split(",").map((c) => c.trim());
    return [line];
  });
}

function build(pres, ctx, variant) {
  const { slots, theme } = ctx;
  const slide = pres.addSlide();
  slide.background = { color: theme.background };

  const heading = slots.TITLE || "Data";
  const body = (slots.BODY_1 || "").trim();
  const bullets = normalizeLines(slots.BULLET_1 || "");
  const citation = (slots.CITATION || "").trim();

  addAccentBar(slide, pres, 0, 0, SLIDE_W, 0.05, theme.primary);

  slide.addText(heading, {
    x: MARGIN,
    y: 0.25,
    w: SLIDE_W - MARGIN * 2,
    h: 0.7,
    fontSize: 26,
    fontFace: theme.headerFont,
    color: theme.text,
    bold: true,
    margin: 0,
  });

  // Parse bullets/body into table rows
  const rawRows = _parseTableRows(slots.BULLET_1 || body || "");
  const maxCols = Math.max(...rawRows.map((r) => r.length), 1);

  // Build PptxGenJS table rows
  const tableRows = rawRows.map((cells, ri) => {
    const isHeader = ri === 0;
    const padded = [...cells];
    while (padded.length < maxCols) padded.push("");
    return padded.map((cell) => ({
      text: cell,
      options: {
        fontSize: 11,
        fontFace: theme.bodyFont,
        color: isHeader ? theme.textLight : theme.text,
        bold: isHeader,
        fill: { color: isHeader ? theme.primary : ri % 2 === 0 ? theme.cardFill : theme.background },
        border: { pt: 0.5, color: theme.cardBorder },
        valign: "middle",
        margin: [4, 6, 4, 6],
      },
    }));
  });

  if (variant === 0) {
    // Full-width table
    const tableW = SLIDE_W - MARGIN * 2;
    if (tableRows.length) {
      slide.addTable(tableRows, {
        x: MARGIN,
        y: 1.2,
        w: tableW,
        border: { pt: 0.5, color: theme.cardBorder },
        autoPage: false,
      });
    }
  } else {
    // Table + side summary card
    const tableW = (SLIDE_W - MARGIN * 2) * 0.65;
    const summaryX = MARGIN + tableW + 0.3;
    const summaryW = SLIDE_W - summaryX - MARGIN;

    if (tableRows.length) {
      slide.addTable(tableRows, {
        x: MARGIN,
        y: 1.2,
        w: tableW,
        border: { pt: 0.5, color: theme.cardBorder },
        autoPage: false,
      });
    }

    // Summary card
    addCard(slide, pres, summaryX, 1.2, summaryW, 3.5, theme);
    addAccentBar(slide, pres, summaryX, 1.2, summaryW, 0.06, theme.accent);

    slide.addText("Summary", {
      x: summaryX + 0.15,
      y: 1.35,
      w: summaryW - 0.3,
      h: 0.45,
      fontSize: 14,
      fontFace: theme.headerFont,
      color: theme.primary,
      bold: true,
    });

    const summaryText = body || bullets.join("\n") || "";
    if (summaryText) {
      slide.addText(summaryText, {
        x: summaryX + 0.15,
        y: 1.85,
        w: summaryW - 0.3,
        h: 2.7,
        fontSize: 11,
        fontFace: theme.bodyFont,
        color: theme.text,
        valign: "top",
      });
    }
  }

  if (citation) {
    slide.addText(citation, {
      x: MARGIN,
      y: 5.05,
      w: SLIDE_W - MARGIN * 2,
      h: 0.4,
      fontSize: 8,
      fontFace: theme.bodyFont,
      color: theme.muted,
      italic: true,
    });
  }
}

module.exports = { build, VARIANT_COUNT };
