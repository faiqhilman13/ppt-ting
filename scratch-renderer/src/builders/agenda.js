const {
  SLIDE_W,
  MARGIN,
  normalizeLines,
  makeShadow,
  addCard,
  addAccentBar,
} = require("../helpers");

const VARIANT_COUNT = 2;

function build(pres, ctx, variant) {
  const { slots, theme } = ctx;
  const slide = pres.addSlide();
  slide.background = { color: theme.background };

  const heading = slots.TITLE || "Agenda";
  const bullets = normalizeLines(slots.BULLET_1 || slots.BODY_1 || "");
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

  const items = bullets.slice(0, 6);
  if (!items.length) return;

  if (variant === 0) {
    // Numbered accent circles on left, text right
    const startY = 1.3;
    const rowH = Math.min(0.72, 3.5 / items.length);

    for (let i = 0; i < items.length; i++) {
      const y = startY + i * rowH;

      // Numbered circle
      slide.addText(String(i + 1), {
        x: MARGIN + 0.2,
        y: y + 0.05,
        w: 0.42,
        h: 0.42,
        shape: pres.shapes.OVAL,
        fill: { color: theme.primary },
        fontSize: 16,
        fontFace: theme.headerFont,
        color: theme.textLight,
        bold: true,
        align: "center",
        valign: "middle",
      });

      // Text card
      addCard(slide, pres, MARGIN + 0.9, y, SLIDE_W - MARGIN * 2 - 1, rowH - 0.08, theme);
      slide.addText(items[i], {
        x: MARGIN + 1.1,
        y: y,
        w: SLIDE_W - MARGIN * 2 - 1.4,
        h: rowH - 0.08,
        fontSize: 13,
        fontFace: theme.bodyFont,
        color: theme.text,
        valign: "middle",
      });
    }
  } else {
    // Two-column grid of cards
    const cols = 2;
    const gap = 0.3;
    const cardW = (SLIDE_W - MARGIN * 2 - gap) / cols;
    const rows = Math.ceil(items.length / cols);
    const rowH = Math.min(1.1, 3.6 / rows);
    const startY = 1.2;

    for (let i = 0; i < items.length; i++) {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const x = MARGIN + col * (cardW + gap);
      const y = startY + row * (rowH + 0.1);

      addCard(slide, pres, x, y, cardW, rowH, theme);
      addAccentBar(slide, pres, x, y, 0.06, rowH, theme.primary);

      // Number
      slide.addText(String(i + 1) + ".", {
        x: x + 0.2,
        y: y + 0.08,
        w: 0.5,
        h: rowH - 0.16,
        fontSize: 20,
        fontFace: theme.headerFont,
        color: theme.primary,
        bold: true,
        valign: "top",
      });

      // Text
      slide.addText(items[i], {
        x: x + 0.7,
        y: y + 0.1,
        w: cardW - 0.95,
        h: rowH - 0.2,
        fontSize: 12,
        fontFace: theme.bodyFont,
        color: theme.text,
        valign: "middle",
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
