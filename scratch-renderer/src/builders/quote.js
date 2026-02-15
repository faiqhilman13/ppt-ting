const {
  SLIDE_W,
  SLIDE_H,
  MARGIN,
  addAccentBar,
} = require("../helpers");

const VARIANT_COUNT = 2;

function build(pres, ctx, variant) {
  const { slots, theme } = ctx;
  const slide = pres.addSlide();

  const quoteText = slots.BODY_1 || slots.BULLET_1 || slots.TITLE || "";
  const attribution = slots.SUBTITLE || slots.CITATION || "";

  if (variant === 0) {
    // Light background with large decorative quote mark
    slide.background = { color: theme.background };
    addAccentBar(slide, pres, 0, 0, SLIDE_W, 0.05, theme.primary);

    // Large decorative opening quote mark
    slide.addText("\u201C", {
      x: 0.8,
      y: 0.6,
      w: 1.5,
      h: 1.5,
      fontSize: 120,
      fontFace: theme.headerFont,
      color: theme.primary,
      bold: true,
      valign: "top",
    });

    // Quote text
    slide.addText(quoteText, {
      x: 1.2,
      y: 1.6,
      w: 7.6,
      h: 2.4,
      fontSize: 20,
      fontFace: theme.headerFont,
      color: theme.text,
      italic: true,
      valign: "middle",
    });

    // Attribution
    if (attribution) {
      addAccentBar(slide, pres, 1.2, 4.1, 1.5, 0.03, theme.primary);
      slide.addText(attribution, {
        x: 1.2,
        y: 4.2,
        w: 7.6,
        h: 0.6,
        fontSize: 13,
        fontFace: theme.bodyFont,
        color: theme.muted,
        valign: "top",
      });
    }
  } else {
    // Dark background with centered text
    slide.background = { color: theme.darkBackground };

    // Accent corners
    addAccentBar(slide, pres, 0, 0, SLIDE_W, 0.06, theme.accent);
    addAccentBar(slide, pres, 0, SLIDE_H - 0.06, SLIDE_W, 0.06, theme.accent);

    // Quote text centered
    slide.addText(quoteText, {
      x: 1.5,
      y: 1.0,
      w: 7,
      h: 2.8,
      fontSize: 22,
      fontFace: theme.headerFont,
      color: theme.textLight,
      italic: true,
      align: "center",
      valign: "middle",
    });

    // Attribution
    if (attribution) {
      slide.addText("\u2014 " + attribution, {
        x: 1.5,
        y: 4.0,
        w: 7,
        h: 0.6,
        fontSize: 13,
        fontFace: theme.bodyFont,
        color: theme.muted,
        align: "center",
      });
    }
  }
}

module.exports = { build, VARIANT_COUNT };
