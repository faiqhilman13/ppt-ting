const express = require("express");
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");
const { getTheme } = require("./themes");
const { dispatch } = require("./builders");

const app = express();
app.use(express.json({ limit: "10mb" }));

app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

app.post("/render", async (req, res) => {
  try {
    const { slides, title, theme: themeName, outputPath } = req.body;
    if (!slides || !outputPath) {
      return res.status(400).json({ error: "slides and outputPath are required" });
    }

    const theme = getTheme(themeName);
    const pres = new pptxgen();
    pres.layout = "LAYOUT_16x9";
    pres.author = "PPT Ting";
    pres.title = title || "Untitled";

    for (let i = 0; i < slides.length; i++) {
      const { archetype, slots } = slides[i];
      dispatch(pres, {
        archetype: archetype || "general",
        slots: slots || {},
        slideIndex: i,
        totalSlides: slides.length,
        title: title || "Untitled",
        theme,
      });
    }

    const buffer = await pres.write({ outputType: "nodebuffer" });
    const outDir = path.dirname(outputPath);
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(outputPath, buffer);

    res.json({ status: "ok", outputPath, slideCount: slides.length });
  } catch (err) {
    console.error("Render error:", err);
    res.status(500).json({ error: err.message });
  }
});

const PORT = process.env.PORT || 3002;
app.listen(PORT, () => {
  console.log(`scratch-renderer listening on port ${PORT}`);
});
