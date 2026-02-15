const {
  SLIDE_W,
  SLIDE_H,
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

  const heading = slots.TITLE || "Timeline";
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

  const steps = bullets.slice(0, 5); // Cap at 5 steps for readability
  if (!steps.length) return;

  if (variant === 0) {
    // Horizontal flow with numbered circles + connector line
    const usableW = SLIDE_W - MARGIN * 2;
    const stepW = usableW / steps.length;
    const circleY = 1.6;
    const circleR = 0.5;
    const textY = circleY + circleR + 0.35;

    // Connector line across all circles
    if (steps.length > 1) {
      const lineX = MARGIN + stepW / 2;
      const lineW = usableW - stepW;
      slide.addShape(pres.shapes.LINE, {
        x: lineX,
        y: circleY + circleR / 2,
        w: lineW,
        h: 0,
        line: { color: theme.cardBorder, width: 2 },
      });
    }

    for (let i = 0; i < steps.length; i++) {
      const cx = MARGIN + stepW * i + stepW / 2 - circleR / 2;

      // Numbered circle
      slide.addText(String(i + 1), {
        x: cx,
        y: circleY,
        w: circleR,
        h: circleR,
        shape: pres.shapes.OVAL,
        fill: { color: theme.primary },
        fontSize: 18,
        fontFace: theme.headerFont,
        color: theme.textLight,
        bold: true,
        align: "center",
        valign: "middle",
      });

      // Step text
      slide.addText(steps[i], {
        x: MARGIN + stepW * i + 0.1,
        y: textY,
        w: stepW - 0.2,
        h: 2.8,
        fontSize: 11,
        fontFace: theme.bodyFont,
        color: theme.text,
        align: "center",
        valign: "top",
      });
    }
  } else {
    // Vertical list with accent bars
    const startY = 1.2;
    const rowH = Math.min(0.8, (SLIDE_H - startY - 0.6) / steps.length);

    for (let i = 0; i < steps.length; i++) {
      const y = startY + i * rowH;

      // Accent dot
      addAccentBar(slide, pres, MARGIN + 0.15, y + rowH / 2 - 0.04, 0.08, 0.08, theme.primary);

      // Vertical connector
      if (i < steps.length - 1) {
        addAccentBar(
          slide,
          pres,
          MARGIN + 0.175,
          y + rowH / 2 + 0.04,
          0.03,
          rowH - 0.08,
          theme.cardBorder
        );
      }

      // Number
      slide.addText(String(i + 1), {
        x: MARGIN + 0.5,
        y: y,
        w: 0.4,
        h: rowH,
        fontSize: 16,
        fontFace: theme.headerFont,
        color: theme.primary,
        bold: true,
        valign: "middle",
      });

      // Card with text
      addCard(slide, pres, MARGIN + 1.1, y + 0.05, SLIDE_W - MARGIN * 2 - 1.2, rowH - 0.1, theme);
      slide.addText(steps[i], {
        x: MARGIN + 1.3,
        y: y + 0.05,
        w: SLIDE_W - MARGIN * 2 - 1.6,
        h: rowH - 0.1,
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
