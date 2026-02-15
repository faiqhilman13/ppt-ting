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

function getTheme(name) {
  return themes[(name || "").toLowerCase()] || themes.midnight_executive;
}

module.exports = { themes, getTheme };
