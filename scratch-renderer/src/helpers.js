const SLIDE_W = 10;
const SLIDE_H = 5.625;
const MARGIN = 0.5;

function normalizeLines(text) {
  if (!text) return [];
  return text
    .split(/\n/)
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => l.replace(/^\s*(?:[•\-\*])\s*/, ""));
}

/** Fresh shadow object every call — PptxGenJS mutates in place (pitfall #7). */
function makeShadow(overrides) {
  return {
    type: "outer",
    color: "000000",
    blur: 6,
    offset: 2,
    angle: 135,
    opacity: 0.15,
    ...(overrides || {}),
  };
}

function addCard(slide, pres, x, y, w, h, theme, opts) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x,
    y,
    w,
    h,
    fill: { color: (opts && opts.fill) || theme.cardFill },
    shadow: makeShadow(),
    line: { color: (opts && opts.border) || theme.cardBorder, width: 1 },
  });
}

function addAccentBar(slide, pres, x, y, w, h, color) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x,
    y,
    w,
    h,
    fill: { color },
  });
}

/** Build a breakLine-delimited rich text array for bullets. */
function bulletTextArr(lines, opts) {
  return lines.map((text, i) => ({
    text,
    options: {
      bullet: true,
      breakLine: i < lines.length - 1,
      fontSize: (opts && opts.fontSize) || 13,
      fontFace: (opts && opts.fontFace) || "Calibri",
      color: (opts && opts.color) || "1E293B",
      ...(opts && opts.extra ? opts.extra : {}),
    },
  }));
}

/** Build a breakLine-delimited rich text array for plain paragraphs. */
function paraTextArr(lines, opts) {
  return lines.map((text, i) => ({
    text,
    options: {
      breakLine: i < lines.length - 1,
      fontSize: (opts && opts.fontSize) || 13,
      fontFace: (opts && opts.fontFace) || "Calibri",
      color: (opts && opts.color) || "1E293B",
      ...(opts && opts.extra ? opts.extra : {}),
    },
  }));
}

module.exports = {
  SLIDE_W,
  SLIDE_H,
  MARGIN,
  normalizeLines,
  makeShadow,
  addCard,
  addAccentBar,
  bulletTextArr,
  paraTextArr,
};
