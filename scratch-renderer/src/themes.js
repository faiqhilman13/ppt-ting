const themes = {
  midnight_executive: {
    primary: "1E2761",
    secondary: "3949AB",
    accent: "E8B931",
    background: "F8FAFC",
    darkBackground: "1E2761",
    text: "1E293B",
    textLight: "F8FAFC",
    muted: "94A3B8",
    cardFill: "FFFFFF",
    cardBorder: "E2E8F0",
    headerFont: "Georgia",
    bodyFont: "Calibri",
  },
  warm_terracotta: {
    primary: "B85042",
    secondary: "E07A5F",
    accent: "F2CC8F",
    background: "FAF8F5",
    darkBackground: "3D2016",
    text: "3D2016",
    textLight: "FAF8F5",
    muted: "A8998A",
    cardFill: "FFFFFF",
    cardBorder: "E8DDD3",
    headerFont: "Cambria",
    bodyFont: "Calibri",
  },
  teal_trust: {
    primary: "028090",
    secondary: "05B4A4",
    accent: "F18F01",
    background: "F0FDFA",
    darkBackground: "042F2E",
    text: "134E4A",
    textLight: "F0FDFA",
    muted: "94A3B8",
    cardFill: "FFFFFF",
    cardBorder: "CCFBF1",
    headerFont: "Trebuchet MS",
    bodyFont: "Calibri",
  },
};

const THEME_KEYS = [
  "primary", "secondary", "accent", "background", "darkBackground",
  "text", "textLight", "muted", "cardFill", "cardBorder",
  "headerFont", "bodyFont",
];

const HEX6_RE = /^[0-9A-Fa-f]{6}$/;

const ALLOWED_FONTS = new Set([
  "Arial", "Calibri", "Georgia", "Cambria",
  "Trebuchet MS", "Verdana", "Tahoma", "Times New Roman",
]);

/**
 * Resolve a theme from either a preset name string or a full theme object.
 * Missing/invalid properties are filled from midnight_executive defaults.
 */
function resolveTheme(input) {
  if (!input || typeof input === "string") {
    return themes[(input || "").toLowerCase()] || themes.midnight_executive;
  }

  if (typeof input === "object" && !Array.isArray(input)) {
    const fallback = themes.midnight_executive;
    const result = {};
    for (const key of THEME_KEYS) {
      const value = (input[key] || "").toString().trim();
      if (key === "headerFont" || key === "bodyFont") {
        result[key] = ALLOWED_FONTS.has(value) ? value : fallback[key];
      } else {
        const cleaned = value.replace(/^#/, "");
        result[key] = HEX6_RE.test(cleaned) ? cleaned : fallback[key];
      }
    }
    return result;
  }

  return themes.midnight_executive;
}

function getTheme(name) {
  return resolveTheme(name);
}

module.exports = { themes, getTheme, resolveTheme };
