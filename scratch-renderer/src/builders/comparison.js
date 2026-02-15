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

function _splitBullets(bullets) {
  const half = Math.ceil(bullets.length / 2);
  return [bullets.slice(0, half), bullets.slice(half)];
}

function build(pres, ctx, variant) {
  const { slots, theme } = ctx;
  const slide = pres.addSlide();
  slide.background = { color: theme.background };

  const heading = slots.TITLE || "Comparison";
  const bullets = normalizeLines(slots.BULLET_1 || "");
  const body = (slots.BODY_1 || "").trim();
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

  const [leftBullets, rightBullets] = _splitBullets(bullets);
  const contentY = 1.15;
  const contentH = 3.6;

  if (variant === 0) {
    // Two equal-width cards
    const gap = 0.3;
    const colW = (SLIDE_W - MARGIN * 2 - gap) / 2;

    addCard(slide, pres, MARGIN, contentY, colW, contentH, theme);
    addAccentBar(slide, pres, MARGIN, contentY, colW, 0.06, theme.primary);
    addCard(slide, pres, MARGIN + colW + gap, contentY, colW, contentH, theme);
    addAccentBar(slide, pres, MARGIN + colW + gap, contentY, colW, 0.06, theme.secondary);

    if (leftBullets.length) {
      slide.addText(bulletTextArr(leftBullets, { color: theme.text, fontFace: theme.bodyFont }), {
        x: MARGIN + 0.2,
        y: contentY + 0.25,
        w: colW - 0.4,
        h: contentH - 0.5,
        valign: "top",
        paraSpaceAfter: 6,
      });
    }
    if (rightBullets.length) {
      slide.addText(bulletTextArr(rightBullets, { color: theme.text, fontFace: theme.bodyFont }), {
        x: MARGIN + colW + gap + 0.2,
        y: contentY + 0.25,
        w: colW - 0.4,
        h: contentH - 0.5,
        valign: "top",
        paraSpaceAfter: 6,
      });
    }
  } else if (variant === 1) {
    // Left-weighted 60/40
    const gap = 0.3;
    const leftW = (SLIDE_W - MARGIN * 2 - gap) * 0.6;
    const rightW = (SLIDE_W - MARGIN * 2 - gap) * 0.4;

    addCard(slide, pres, MARGIN, contentY, leftW, contentH, theme);
    addAccentBar(slide, pres, MARGIN, contentY, 0.07, contentH, theme.primary);

    const leftContent = leftBullets.length
      ? bulletTextArr(leftBullets, { color: theme.text, fontFace: theme.bodyFont })
      : [{ text: body || "", options: { fontSize: 12, fontFace: theme.bodyFont, color: theme.text } }];

    slide.addText(leftContent, {
      x: MARGIN + 0.25,
      y: contentY + 0.15,
      w: leftW - 0.5,
      h: contentH - 0.3,
      valign: "top",
      paraSpaceAfter: 6,
    });

    addCard(slide, pres, MARGIN + leftW + gap, contentY, rightW, contentH, theme, {
      fill: theme.primary,
    });
    if (rightBullets.length) {
      slide.addText(bulletTextArr(rightBullets, { color: theme.textLight, fontFace: theme.bodyFont }), {
        x: MARGIN + leftW + gap + 0.2,
        y: contentY + 0.2,
        w: rightW - 0.4,
        h: contentH - 0.4,
        valign: "top",
        paraSpaceAfter: 6,
      });
    } else if (body) {
      slide.addText(body, {
        x: MARGIN + leftW + gap + 0.2,
        y: contentY + 0.2,
        w: rightW - 0.4,
        h: contentH - 0.4,
        fontSize: 12,
        fontFace: theme.bodyFont,
        color: theme.textLight,
        valign: "top",
      });
    }
  } else {
    // Horizontal stack with central accent divider
    const gap = 0.3;
    const colW = (SLIDE_W - MARGIN * 2 - gap) / 2;

    addCard(slide, pres, MARGIN, contentY, colW, contentH, theme);
    addCard(slide, pres, MARGIN + colW + gap, contentY, colW, contentH, theme);

    // Central divider
    const divX = MARGIN + colW + gap / 2 - 0.02;
    addAccentBar(slide, pres, divX, contentY + 0.3, 0.04, contentH - 0.6, theme.accent);

    // Column headers
    slide.addText("Option A", {
      x: MARGIN + 0.15,
      y: contentY + 0.15,
      w: colW - 0.3,
      h: 0.4,
      fontSize: 14,
      fontFace: theme.headerFont,
      color: theme.primary,
      bold: true,
    });
    slide.addText("Option B", {
      x: MARGIN + colW + gap + 0.15,
      y: contentY + 0.15,
      w: colW - 0.3,
      h: 0.4,
      fontSize: 14,
      fontFace: theme.headerFont,
      color: theme.secondary,
      bold: true,
    });

    if (leftBullets.length) {
      slide.addText(bulletTextArr(leftBullets, { color: theme.text, fontFace: theme.bodyFont }), {
        x: MARGIN + 0.2,
        y: contentY + 0.65,
        w: colW - 0.4,
        h: contentH - 0.9,
        valign: "top",
        paraSpaceAfter: 6,
      });
    }
    if (rightBullets.length) {
      slide.addText(bulletTextArr(rightBullets, { color: theme.text, fontFace: theme.bodyFont }), {
        x: MARGIN + colW + gap + 0.2,
        y: contentY + 0.65,
        w: colW - 0.4,
        h: contentH - 0.9,
        valign: "top",
        paraSpaceAfter: 6,
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
