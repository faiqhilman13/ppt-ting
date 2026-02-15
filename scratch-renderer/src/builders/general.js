const {
  SLIDE_W,
  MARGIN,
  normalizeLines,
  makeShadow,
  addCard,
  addAccentBar,
  bulletTextArr,
  paraTextArr,
} = require("../helpers");

const VARIANT_COUNT = 3;

function build(pres, ctx, variant) {
  const { slots, theme } = ctx;
  const slide = pres.addSlide();
  slide.background = { color: theme.background };

  const heading = slots.TITLE || "Overview";
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

  const contentY = 1.15;
  const contentH = 3.6;

  if (variant === 0) {
    // Accent sidebar + content card
    const sideW = 0.08;
    const cardW = SLIDE_W - MARGIN * 2;

    addCard(slide, pres, MARGIN, contentY, cardW, contentH, theme);
    addAccentBar(slide, pres, MARGIN, contentY, sideW, contentH, theme.primary);

    const textParts = [];
    if (body) {
      textParts.push(
        ...paraTextArr([body], {
          color: theme.text,
          fontFace: theme.bodyFont,
          fontSize: 13,
          extra: { breakLine: true },
        })
      );
    }
    if (bullets.length) {
      textParts.push(
        ...bulletTextArr(bullets, { color: theme.text, fontFace: theme.bodyFont })
      );
    }

    if (textParts.length) {
      slide.addText(textParts, {
        x: MARGIN + sideW + 0.3,
        y: contentY + 0.15,
        w: cardW - sideW - 0.6,
        h: contentH - 0.3,
        valign: "top",
        paraSpaceAfter: 6,
      });
    }
  } else if (variant === 1) {
    // Two-column layout: body left, bullets right
    const gap = 0.3;
    const colW = (SLIDE_W - MARGIN * 2 - gap) / 2;

    // Left column
    addCard(slide, pres, MARGIN, contentY, colW, contentH, theme);
    addAccentBar(slide, pres, MARGIN, contentY, colW, 0.06, theme.primary);

    if (body) {
      slide.addText(body, {
        x: MARGIN + 0.2,
        y: contentY + 0.2,
        w: colW - 0.4,
        h: contentH - 0.35,
        fontSize: 12,
        fontFace: theme.bodyFont,
        color: theme.text,
        valign: "top",
      });
    } else if (bullets.length) {
      const half = Math.ceil(bullets.length / 2);
      slide.addText(bulletTextArr(bullets.slice(0, half), { color: theme.text, fontFace: theme.bodyFont }), {
        x: MARGIN + 0.2,
        y: contentY + 0.2,
        w: colW - 0.4,
        h: contentH - 0.35,
        valign: "top",
        paraSpaceAfter: 6,
      });
    }

    // Right column
    addCard(slide, pres, MARGIN + colW + gap, contentY, colW, contentH, theme);
    addAccentBar(slide, pres, MARGIN + colW + gap, contentY, colW, 0.06, theme.secondary || theme.primary);

    if (bullets.length) {
      const startIdx = body ? 0 : Math.ceil(bullets.length / 2);
      const rightBullets = body ? bullets : bullets.slice(startIdx);
      if (rightBullets.length) {
        slide.addText(bulletTextArr(rightBullets, { color: theme.text, fontFace: theme.bodyFont }), {
          x: MARGIN + colW + gap + 0.2,
          y: contentY + 0.2,
          w: colW - 0.4,
          h: contentH - 0.35,
          valign: "top",
          paraSpaceAfter: 6,
        });
      }
    } else if (body) {
      // Split body into two halves
      const sentences = body.split(/\.\s+/);
      const secondHalf = sentences.slice(Math.ceil(sentences.length / 2)).join(". ");
      if (secondHalf) {
        slide.addText(secondHalf, {
          x: MARGIN + colW + gap + 0.2,
          y: contentY + 0.2,
          w: colW - 0.4,
          h: contentH - 0.35,
          fontSize: 12,
          fontFace: theme.bodyFont,
          color: theme.text,
          valign: "top",
        });
      }
    }
  } else {
    // Single full card with structured layout
    addCard(slide, pres, MARGIN, contentY, SLIDE_W - MARGIN * 2, contentH, theme);

    // Subtitle band across top of card
    slide.addShape(pres.shapes.RECTANGLE, {
      x: MARGIN,
      y: contentY,
      w: SLIDE_W - MARGIN * 2,
      h: 0.5,
      fill: { color: theme.primary, transparency: 8 },
    });

    if (body) {
      slide.addText(body, {
        x: MARGIN + 0.25,
        y: contentY + 0.08,
        w: SLIDE_W - MARGIN * 2 - 0.5,
        h: 0.4,
        fontSize: 12,
        fontFace: theme.bodyFont,
        color: theme.primary,
        bold: true,
        valign: "middle",
      });
    }

    if (bullets.length) {
      slide.addText(bulletTextArr(bullets, { color: theme.text, fontFace: theme.bodyFont }), {
        x: MARGIN + 0.3,
        y: contentY + 0.65,
        w: SLIDE_W - MARGIN * 2 - 0.6,
        h: contentH - 0.9,
        valign: "top",
        paraSpaceAfter: 6,
      });
    } else if (body && !bullets.length) {
      // Body in the main area if no bullets
      slide.addText(body, {
        x: MARGIN + 0.3,
        y: contentY + 0.6,
        w: SLIDE_W - MARGIN * 2 - 0.6,
        h: contentH - 0.8,
        fontSize: 13,
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
