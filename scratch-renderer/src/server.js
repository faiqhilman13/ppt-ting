const express = require("express");
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { resolveTheme } = require("./themes");
const { dispatch } = require("./builders");

const app = express();
app.use(express.json({ limit: "10mb" }));

app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

function resolveHtml2PptxModulePath() {
  const strict = String(process.env.PPTX_SKILL_STRICT || "false").toLowerCase() === "true";

  const direct = process.env.PPTX_HTML2PPTX_SCRIPT;
  if (direct && fs.existsSync(direct)) {
    return { path: direct, source: "env:PPTX_HTML2PPTX_SCRIPT" };
  }

  const skillRoot = process.env.PPTX_SKILL_ROOT;
  if (skillRoot) {
    const byRoot = path.join(skillRoot, "scripts", "html2pptx.js");
    if (fs.existsSync(byRoot)) {
      return { path: byRoot, source: "env:PPTX_SKILL_ROOT" };
    }
  }

  if (strict) {
    return null;
  }

  const bundled = path.join(__dirname, "scripts", "html2pptx.js");
  if (fs.existsSync(bundled)) {
    return { path: bundled, source: "bundled" };
  }

  const windowsDefault = "C:/Users/faiqh/.codex/skills/pptx/scripts/html2pptx.js";
  if (fs.existsSync(windowsDefault)) {
    return { path: windowsDefault, source: "host:windows_default" };
  }
  return null;
}

function materializeHtmlSlides(htmlSpec, tempDir) {
  const slides = Array.isArray(htmlSpec?.slides) ? htmlSpec.slides : [];
  if (!slides.length) {
    throw new Error("htmlSpec.slides is required for html rendering");
  }

  const htmlFiles = [];
  for (let i = 0; i < slides.length; i++) {
    const row = slides[i];
    if (typeof row === "string") {
      const filePath = path.join(tempDir, `slide-${i + 1}.html`);
      fs.writeFileSync(filePath, row, "utf8");
      htmlFiles.push(filePath);
      continue;
    }

    if (row && typeof row === "object") {
      if (row.path && fs.existsSync(row.path)) {
        htmlFiles.push(row.path);
        continue;
      }
      if (typeof row.html === "string" && row.html.trim()) {
        const filePath = path.join(tempDir, `slide-${i + 1}.html`);
        fs.writeFileSync(filePath, row.html, "utf8");
        htmlFiles.push(filePath);
        continue;
      }
    }

    throw new Error(`Invalid html slide at index ${i}`);
  }

  return htmlFiles;
}

app.post("/render", async (req, res) => {
  try {
    const { slides, title, theme: themeInput, outputPath } = req.body;
    if (!slides || !outputPath) {
      return res.status(400).json({ error: "slides and outputPath are required" });
    }

    const theme = resolveTheme(themeInput);
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

app.post("/render-html", async (req, res) => {
  let tempDir = null;
  try {
    const { title, outputPath, htmlSpec } = req.body || {};
    if (!outputPath) {
      return res.status(400).json({ error: "outputPath is required" });
    }

    const resolved = resolveHtml2PptxModulePath();
    if (!resolved) {
      return res.status(500).json({
        error: "html2pptx.js not found. In strict mode, configure PPTX_SKILL_ROOT or PPTX_HTML2PPTX_SCRIPT.",
      });
    }
    const html2pptxPath = resolved.path;
    console.log(`render-html using html2pptx from ${resolved.source}: ${html2pptxPath}`);

    // Lazy load to avoid hard dependency unless html endpoint is used.
    const html2pptx = require(html2pptxPath);

    const pres = new pptxgen();
    pres.layout = htmlSpec?.layout || "LAYOUT_16x9";
    pres.author = "PPT Ting";
    pres.title = title || "Untitled";

    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "scratch-html-"));
    const htmlFiles = materializeHtmlSlides(htmlSpec, tempDir);

    for (let i = 0; i < htmlFiles.length; i++) {
      await html2pptx(htmlFiles[i], pres, {
        tmpDir: htmlSpec?.tmpDir || tempDir,
      });
    }

    const buffer = await pres.write({ outputType: "nodebuffer" });
    const outDir = path.dirname(outputPath);
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(outputPath, buffer);

    return res.json({
      status: "ok",
      outputPath,
      slideCount: htmlFiles.length,
      html2pptxSource: resolved.source,
      html2pptxPath,
    });
  } catch (err) {
    console.error("Render html error:", err);
    return res.status(500).json({ error: err.message });
  } finally {
    if (tempDir && fs.existsSync(tempDir)) {
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  }
});

const PORT = process.env.PORT || 3002;
app.listen(PORT, () => {
  console.log(`scratch-renderer listening on port ${PORT}`);
});
