const {
  SLIDE_W,
  MARGIN,
  normalizeLines,
  makeShadow,
  addCard,
  addAccentBar,
  bulletTextArr,
} = require("../helpers");

const VARIANT_COUNT = 3;

function build(pres, ctx, variant) {
  const { slots, theme } = ctx;
  const slide = pres.addSlide();
  slide.background = { color: theme.background };

  const heading = slots.TITLE || "Executive Summary";
  const bullets = normalizeLines(slots.BULLET_1 || "");
  const body = (slots.BODY_1 || "").trim();
  const citation = (slots.CITATION || "").trim();

  // Top accent bar
  addAccentBar(slide, pres, 0, 0, SLIDE_W, 0.05, theme.primary);

  // Title
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

  if (variant === 0) {
    // Left callout card with body, right bullets
    const cardW = 3.8;
    addCard(slide, pres, MARGIN, 1.15, cardW, 3.6, theme);
    addAccentBar(slide, pres, MARGIN, 1.15, 0.07, 3.6, theme.primary);

    if (body) {
      slide.addText(body, {
        x: MARGIN + 0.25,
        y: 1.3,
        w: cardW - 0.4,
        h: 3.3,
        fontSize: 12,
        fontFace: theme.bodyFont,
        color: theme.text,
        valign: "top",
      });
    }

    if (bullets.length) {
      addCard(slide, pres, MARGIN + cardW + 0.3, 1.15, SLIDE_W - MARGIN * 2 - cardW - 0.3, 3.6, theme);
      slide.addText(bulletTextArr(bullets, { color: theme.text, fontFace: theme.bodyFont }), {
        x: MARGIN + cardW + 0.5,
        y: 1.3,
        w: SLIDE_W - MARGIN * 2 - cardW - 0.7,
        h: 3.3,
        valign: "top",
        paraSpaceAfter: 6,
      });
    }
  } else if (variant === 1) {
    // Top callout bar, bullets below in two columns
    if (body) {
      addCard(slide, pres, MARGIN, 1.15, SLIDE_W - MARGIN * 2, 1.1, theme, { fill: theme.primary });
      slide.addText(body, {
        x: MARGIN + 0.2,
        y: 1.2,
        w: SLIDE_W - MARGIN * 2 - 0.4,
        h: 1.0,
        fontSize: 13,
        fontFace: theme.bodyFont,
        color: theme.textLight,
        valign: "middle",
      });
    }

    const bY = body ? 2.5 : 1.15;
    const bH = body ? 2.5 : 3.6;
    const colW = (SLIDE_W - MARGIN * 2 - 0.3) / 2;
    const half = Math.ceil(bullets.length / 2);
    const left = bullets.slice(0, half);
    const right = bullets.slice(half);

    if (left.length) {
      addCard(slide, pres, MARGIN, bY, colW, bH, theme);
      slide.addText(bulletTextArr(left, { color: theme.text, fontFace: theme.bodyFont }), {
        x: MARGIN + 0.2,
        y: bY + 0.15,
        w: colW - 0.4,
        h: bH - 0.3,
        valign: "top",
        paraSpaceAfter: 6,
      });
    }
    if (right.length) {
      addCard(slide, pres, MARGIN + colW + 0.3, bY, colW, bH, theme);
      slide.addText(bulletTextArr(right, { color: theme.text, fontFace: theme.bodyFont }), {
        x: MARGIN + colW + 0.5,
        y: bY + 0.15,
        w: colW - 0.4,
        h: bH - 0.3,
        valign: "top",
        paraSpaceAfter: 6,
      });
    }
  } else {
    // Three equal-width key-point cards
    const items = bullets.length >= 3 ? bullets : (body || "").split(/\.\s+/).filter(Boolean);
    const count = Math.min(items.length, 3) || 1;
    const gap = 0.25;
    const cardW = (SLIDE_W - MARGIN * 2 - gap * (count - 1)) / count;

    for (let i = 0; i < count; i++) {
      const x = MARGIN + i * (cardW + gap);
      addCard(slide, pres, x, 1.15, cardW, 3.6, theme);
      addAccentBar(slide, pres, x, 1.15, cardW, 0.06, theme.primary);

      // Number badge
      slide.addText(String(i + 1), {
        x: x + 0.2,
        y: 1.4,
        w: 0.45,
        h: 0.45,
        fontSize: 18,
        fontFace: theme.headerFont,
        color: theme.textLight,
        bold: true,
        align: "center",
        valign: "middle",
        shape: pres.shapes.OVAL,
        fill: { color: theme.primary },
      });

      slide.addText(items[i] || "", {
        x: x + 0.15,
        y: 2.1,
        w: cardW - 0.3,
        h: 2.4,
        fontSize: 12,
        fontFace: theme.bodyFont,
        color: theme.text,
        valign: "top",
      });
    }
  }

  // Citation footer
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
