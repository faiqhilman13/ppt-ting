const {
  SLIDE_W,
  SLIDE_H,
  MARGIN,
  normalizeLines,
  makeShadow,
  addCard,
  addAccentBar,
  bulletTextArr,
} = require("../helpers");

const VARIANT_COUNT = 2;

function build(pres, ctx, variant) {
  const { slots, theme, title } = ctx;
  const slide = pres.addSlide();

  const heading = slots.TITLE || "Thank You";
  const body = (slots.BODY_1 || "").trim();
  const bullets = normalizeLines(slots.BULLET_1 || "");
  const subtitle = slots.SUBTITLE || "";

  if (variant === 0) {
    // Stacked: dark top with title, light bottom with CTA card + bullets
    slide.background = { color: theme.background };

    // Dark header band
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0,
      y: 0,
      w: SLIDE_W,
      h: 2.2,
      fill: { color: theme.darkBackground },
    });

    slide.addText(heading, {
      x: MARGIN,
      y: 0.5,
      w: SLIDE_W - MARGIN * 2,
      h: 0.9,
      fontSize: 32,
      fontFace: theme.headerFont,
      color: theme.textLight,
      bold: true,
      align: "center",
      valign: "middle",
    });

    if (subtitle) {
      slide.addText(subtitle, {
        x: MARGIN,
        y: 1.4,
        w: SLIDE_W - MARGIN * 2,
        h: 0.5,
        fontSize: 14,
        fontFace: theme.bodyFont,
        color: theme.muted,
        align: "center",
      });
    }

    // CTA card
    if (body || bullets.length) {
      addCard(slide, pres, 1, 2.6, SLIDE_W - 2, 2.5, theme);
      addAccentBar(slide, pres, 1, 2.6, SLIDE_W - 2, 0.06, theme.accent);

      if (body) {
        slide.addText(body, {
          x: 1.3,
          y: 2.8,
          w: SLIDE_W - 2.6,
          h: bullets.length ? 0.9 : 2.1,
          fontSize: 13,
          fontFace: theme.bodyFont,
          color: theme.text,
          valign: "top",
        });
      }

      if (bullets.length) {
        slide.addText(bulletTextArr(bullets, { color: theme.text, fontFace: theme.bodyFont }), {
          x: 1.3,
          y: body ? 3.7 : 2.8,
          w: SLIDE_W - 2.6,
          h: body ? 1.2 : 2.1,
          valign: "top",
          paraSpaceAfter: 4,
        });
      }
    }
  } else {
    // Split: left CTA panel (dark), right next steps (light)
    slide.background = { color: theme.background };

    const leftW = SLIDE_W * 0.45;

    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0,
      y: 0,
      w: leftW,
      h: SLIDE_H,
      fill: { color: theme.darkBackground },
    });

    slide.addText(heading, {
      x: 0.4,
      y: 1.2,
      w: leftW - 0.8,
      h: 1.2,
      fontSize: 30,
      fontFace: theme.headerFont,
      color: theme.textLight,
      bold: true,
      valign: "middle",
    });

    if (body) {
      slide.addText(body, {
        x: 0.4,
        y: 2.6,
        w: leftW - 0.8,
        h: 2,
        fontSize: 12,
        fontFace: theme.bodyFont,
        color: theme.muted,
        valign: "top",
      });
    }

    // Accent divider
    addAccentBar(slide, pres, leftW - 0.04, 0, 0.08, SLIDE_H, theme.accent);

    // Right side: next steps
    const rightX = leftW + 0.4;
    const rightW = SLIDE_W - leftW - 0.8;

    if (bullets.length) {
      slide.addText("Next Steps", {
        x: rightX,
        y: 0.6,
        w: rightW,
        h: 0.6,
        fontSize: 20,
        fontFace: theme.headerFont,
        color: theme.text,
        bold: true,
      });

      slide.addText(bulletTextArr(bullets, { color: theme.text, fontFace: theme.bodyFont, fontSize: 12 }), {
        x: rightX,
        y: 1.3,
        w: rightW,
        h: 3.5,
        valign: "top",
        paraSpaceAfter: 8,
      });
    } else if (subtitle) {
      slide.addText(subtitle, {
        x: rightX,
        y: 1.5,
        w: rightW,
        h: 2.5,
        fontSize: 14,
        fontFace: theme.bodyFont,
        color: theme.text,
        valign: "middle",
        align: "center",
      });
    }
  }
}

module.exports = { build, VARIANT_COUNT };
