const { SLIDE_W, SLIDE_H, MARGIN, makeShadow, addAccentBar } = require("../helpers");

const VARIANT_COUNT = 3;

function build(pres, ctx, variant) {
  const { slots, theme, title } = ctx;
  const slide = pres.addSlide();
  const heading = slots.TITLE || title || "Section";
  const sub = slots.SUBTITLE || slots.BODY_1 || "";

  if (variant === 0) {
    // Full dark background, centered title + subtitle
    slide.background = { color: theme.darkBackground };
    addAccentBar(slide, pres, 0, 0, SLIDE_W, 0.06, theme.accent);

    slide.addText(heading, {
      x: 1,
      y: 1.6,
      w: 8,
      h: 1.2,
      fontSize: 36,
      fontFace: theme.headerFont,
      color: theme.textLight,
      bold: true,
      align: "center",
      valign: "middle",
    });

    if (sub) {
      slide.addText(sub, {
        x: 1.5,
        y: 3.0,
        w: 7,
        h: 1,
        fontSize: 15,
        fontFace: theme.bodyFont,
        color: theme.muted,
        align: "center",
        valign: "top",
      });
    }

    // Decorative bottom accent line
    addAccentBar(slide, pres, 3.5, 4.8, 3, 0.04, theme.accent);
  } else if (variant === 1) {
    // Dark background, left-aligned with thick accent bar on left
    slide.background = { color: theme.darkBackground };
    addAccentBar(slide, pres, MARGIN, 1.2, 0.08, 2.8, theme.accent);

    slide.addText(heading, {
      x: MARGIN + 0.35,
      y: 1.4,
      w: 7,
      h: 1.2,
      fontSize: 34,
      fontFace: theme.headerFont,
      color: theme.textLight,
      bold: true,
      align: "left",
      valign: "middle",
    });

    if (sub) {
      slide.addText(sub, {
        x: MARGIN + 0.35,
        y: 2.7,
        w: 7,
        h: 1,
        fontSize: 14,
        fontFace: theme.bodyFont,
        color: theme.muted,
        align: "left",
        valign: "top",
      });
    }
  } else {
    // Split: left half dark with title, right half accent with number/subtitle
    slide.background = { color: theme.darkBackground };

    // Right accent panel
    slide.addShape(pres.shapes.RECTANGLE, {
      x: SLIDE_W / 2,
      y: 0,
      w: SLIDE_W / 2,
      h: SLIDE_H,
      fill: { color: theme.accent },
    });

    slide.addText(heading, {
      x: MARGIN,
      y: 1.6,
      w: SLIDE_W / 2 - MARGIN - 0.3,
      h: 1.4,
      fontSize: 32,
      fontFace: theme.headerFont,
      color: theme.textLight,
      bold: true,
      align: "left",
      valign: "middle",
    });

    if (sub) {
      slide.addText(sub, {
        x: SLIDE_W / 2 + 0.5,
        y: 1.8,
        w: SLIDE_W / 2 - 1,
        h: 2,
        fontSize: 14,
        fontFace: theme.bodyFont,
        color: theme.darkBackground,
        align: "left",
        valign: "middle",
      });
    }
  }
}

module.exports = { build, VARIANT_COUNT };
