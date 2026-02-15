const {
  SLIDE_W,
  MARGIN,
  normalizeLines,
  makeShadow,
  addCard,
  addAccentBar,
} = require("../helpers");

const VARIANT_COUNT = 3;

function build(pres, ctx, variant) {
  const { slots, theme } = ctx;
  const slide = pres.addSlide();
  slide.background = { color: theme.background };

  const heading = slots.TITLE || "Key Metrics";
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

  // KPI items: try to extract number+label from bullet lines
  const kpis = bullets.slice(0, 4).map((line) => {
    const match = line.match(/^([\d,.%$+\-]+)\s*[:\-–—]\s*(.+)/);
    if (match) return { value: match[1], label: match[2] };
    return { value: "", label: line };
  });

  if (variant === 0) {
    // 3 KPI cards in a row
    const count = Math.min(kpis.length, 3) || 1;
    const gap = 0.3;
    const cardW = (SLIDE_W - MARGIN * 2 - gap * (count - 1)) / count;

    for (let i = 0; i < count; i++) {
      const x = MARGIN + i * (cardW + gap);
      const kpi = kpis[i] || { value: "—", label: "" };

      addCard(slide, pres, x, 1.3, cardW, 3.2, theme);
      addAccentBar(slide, pres, x, 1.3, cardW, 0.06, theme.primary);

      if (kpi.value) {
        slide.addText(kpi.value, {
          x: x + 0.2,
          y: 1.6,
          w: cardW - 0.4,
          h: 1.2,
          fontSize: 40,
          fontFace: theme.headerFont,
          color: theme.primary,
          bold: true,
          align: "center",
          valign: "middle",
        });
      }

      slide.addText(kpi.label, {
        x: x + 0.2,
        y: kpi.value ? 2.9 : 1.7,
        w: cardW - 0.4,
        h: kpi.value ? 1.3 : 2.5,
        fontSize: kpi.value ? 13 : 14,
        fontFace: theme.bodyFont,
        color: theme.text,
        align: "center",
        valign: "top",
      });
    }
  } else if (variant === 1) {
    // Hero stat: one big number on left, details on right
    const hero = kpis[0] || { value: "—", label: "Key Metric" };
    const rest = kpis.slice(1);

    const heroW = 4;
    addCard(slide, pres, MARGIN, 1.2, heroW, 3.6, theme, { fill: theme.primary });

    slide.addText(hero.value || "—", {
      x: MARGIN + 0.3,
      y: 1.5,
      w: heroW - 0.6,
      h: 1.8,
      fontSize: 56,
      fontFace: theme.headerFont,
      color: theme.textLight,
      bold: true,
      align: "center",
      valign: "middle",
    });

    slide.addText(hero.label, {
      x: MARGIN + 0.3,
      y: 3.3,
      w: heroW - 0.6,
      h: 1.2,
      fontSize: 14,
      fontFace: theme.bodyFont,
      color: theme.textLight,
      align: "center",
      valign: "top",
    });

    // Secondary metrics on right
    const rightX = MARGIN + heroW + 0.3;
    const rightW = SLIDE_W - rightX - MARGIN;
    if (rest.length) {
      const rowH = Math.min(1.1, 3.6 / rest.length);
      for (let i = 0; i < rest.length; i++) {
        const y = 1.2 + i * rowH;
        addCard(slide, pres, rightX, y + 0.05, rightW, rowH - 0.1, theme);

        if (rest[i].value) {
          slide.addText(rest[i].value, {
            x: rightX + 0.15,
            y: y + 0.08,
            w: 1.5,
            h: rowH - 0.16,
            fontSize: 22,
            fontFace: theme.headerFont,
            color: theme.primary,
            bold: true,
            valign: "middle",
          });
          slide.addText(rest[i].label, {
            x: rightX + 1.7,
            y: y + 0.08,
            w: rightW - 2,
            h: rowH - 0.16,
            fontSize: 12,
            fontFace: theme.bodyFont,
            color: theme.text,
            valign: "middle",
          });
        } else {
          slide.addText(rest[i].label, {
            x: rightX + 0.2,
            y: y + 0.08,
            w: rightW - 0.4,
            h: rowH - 0.16,
            fontSize: 12,
            fontFace: theme.bodyFont,
            color: theme.text,
            valign: "middle",
          });
        }
      }
    }
  } else {
    // 2×2 grid
    const count = Math.min(kpis.length, 4) || 1;
    const cols = count <= 2 ? count : 2;
    const rows = Math.ceil(count / cols);
    const gap = 0.25;
    const cardW = (SLIDE_W - MARGIN * 2 - gap * (cols - 1)) / cols;
    const totalH = 3.6;
    const cardH = (totalH - gap * (rows - 1)) / rows;

    for (let i = 0; i < count; i++) {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const x = MARGIN + col * (cardW + gap);
      const y = 1.2 + row * (cardH + gap);
      const kpi = kpis[i];

      addCard(slide, pres, x, y, cardW, cardH, theme);

      if (kpi.value) {
        slide.addText(kpi.value, {
          x: x + 0.15,
          y: y + 0.15,
          w: cardW - 0.3,
          h: cardH * 0.5,
          fontSize: 32,
          fontFace: theme.headerFont,
          color: theme.primary,
          bold: true,
          align: "center",
          valign: "middle",
        });
        slide.addText(kpi.label, {
          x: x + 0.15,
          y: y + cardH * 0.5 + 0.1,
          w: cardW - 0.3,
          h: cardH * 0.4,
          fontSize: 12,
          fontFace: theme.bodyFont,
          color: theme.text,
          align: "center",
          valign: "top",
        });
      } else {
        slide.addText(kpi.label, {
          x: x + 0.2,
          y: y + 0.1,
          w: cardW - 0.4,
          h: cardH - 0.2,
          fontSize: 13,
          fontFace: theme.bodyFont,
          color: theme.text,
          valign: "middle",
          align: "center",
        });
      }
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
