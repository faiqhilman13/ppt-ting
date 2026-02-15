import { useEffect, useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000/api";
const ONLYOFFICE_BASE = import.meta.env.VITE_ONLYOFFICE_URL || "http://localhost:8080";

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response;
}

export default function App() {
  const [templates, setTemplates] = useState([]);
  const [docs, setDocs] = useState([]);
  const [templateName, setTemplateName] = useState("Company Template");
  const [templateFile, setTemplateFile] = useState(null);
  const [docFile, setDocFile] = useState(null);
  const [prompt, setPrompt] = useState("Create a 12-slide strategy deck about AI agents for enterprise operations.");
  const [creationMode, setCreationMode] = useState("template");
  const [scratchTheme, setScratchTheme] = useState("default");
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [selectedDocIds, setSelectedDocIds] = useState([]);
  const [slideCount, setSlideCount] = useState(12);
  const [provider, setProvider] = useState("openai");
  const [agentMode, setAgentMode] = useState("bounded");
  const [qualityProfile, setQualityProfile] = useState("balanced");
  const [maxCorrectionPasses, setMaxCorrectionPasses] = useState(1);
  const [job, setJob] = useState(null);
  const [jobEvents, setJobEvents] = useState([]);
  const [deck, setDeck] = useState(null);
  const [qualityReport, setQualityReport] = useState(null);
  const [revisePrompt, setRevisePrompt] = useState("Make tone more executive and concise.");
  const [editorConfig, setEditorConfig] = useState(null);
  const [cleanupReport, setCleanupReport] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [editorMountReady, setEditorMountReady] = useState(false);
  const latestVersionInfo = useMemo(() => {
    if (!deck?.versions?.length) return null;
    return deck.versions.find((row) => row.version === deck.latest_version) || deck.versions[0];
  }, [deck]);

  const canGenerate = useMemo(() => {
    if (prompt.trim().length <= 3) return false;
    if (creationMode === "template") return Boolean(selectedTemplateId);
    return true;
  }, [creationMode, selectedTemplateId, prompt]);

  const loadData = async () => {
    const [templateRows, docRows] = await Promise.all([api("/templates"), api("/docs")]);
    setTemplates(templateRows);
    setDocs(docRows);
    if (templateRows.length === 0) {
      setSelectedTemplateId("");
    } else if (!selectedTemplateId || !templateRows.some((row) => row.id === selectedTemplateId)) {
      setSelectedTemplateId(templateRows[0].id);
    }
  };

  useEffect(() => {
    loadData().catch((e) => setError(String(e.message || e)));
  }, []);

  useEffect(() => {
    if (!job || job.status === "completed" || job.status === "failed") return;
    const id = setInterval(async () => {
      try {
        const [latest, events] = await Promise.all([
          api(`/jobs/${job.id}`),
          api(`/jobs/${job.id}/events?limit=200`),
        ]);
        setJob(latest);
        setJobEvents(events);
        if (latest.status === "completed" && latest.deck_id) {
          const detail = await api(`/decks/${latest.deck_id}`);
          setDeck(detail);
          const version = detail.latest_version;
          try {
            const report = await api(`/decks/${latest.deck_id}/quality/${version}`);
            setQualityReport(report);
          } catch {
            setQualityReport(null);
          }
        }
      } catch (e) {
        setError(String(e.message || e));
      }
    }, 1500);
    return () => clearInterval(id);
  }, [job]);

  useEffect(() => {
    if (!editorConfig || !editorMountReady) return;

    const script = document.createElement("script");
    script.src = `${ONLYOFFICE_BASE}/web-apps/apps/api/documents/api.js`;
    script.async = true;

    script.onload = () => {
      if (!window.DocsAPI) return;
      if (window.__pptAgentDocEditor?.destroyEditor) {
        window.__pptAgentDocEditor.destroyEditor();
      }
      window.__pptAgentDocEditor = new window.DocsAPI.DocEditor("onlyoffice-editor", editorConfig);
    };

    document.body.appendChild(script);

    return () => {
      if (window.__pptAgentDocEditor?.destroyEditor) {
        window.__pptAgentDocEditor.destroyEditor();
      }
      window.__pptAgentDocEditor = null;
      script.remove();
    };
  }, [editorConfig, editorMountReady]);

  const uploadTemplate = async (e) => {
    e.preventDefault();
    if (!templateFile) return;
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("name", templateName);
      form.append("file", templateFile);
      await api("/templates", { method: "POST", body: form });
      setTemplateFile(null);
      await loadData();
    } catch (e2) {
      setError(String(e2.message || e2));
    } finally {
      setBusy(false);
    }
  };

  const uploadDoc = async (e) => {
    e.preventDefault();
    if (!docFile) return;
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", docFile);
      await api("/docs", { method: "POST", body: form });
      setDocFile(null);
      await loadData();
    } catch (e2) {
      setError(String(e2.message || e2));
    } finally {
      setBusy(false);
    }
  };

  const runGeneration = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await api("/decks/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          creation_mode: creationMode,
          template_id: creationMode === "template" ? selectedTemplateId : null,
          scratch_theme: creationMode === "scratch" ? scratchTheme : null,
          doc_ids: selectedDocIds,
          slide_count: Number(slideCount),
          provider,
          agent_mode: agentMode,
          quality_profile: qualityProfile,
          max_correction_passes: Number(maxCorrectionPasses),
        }),
      });
      setJob(result);
      setDeck(null);
      setJobEvents([]);
      setQualityReport(null);
      setEditorConfig(null);
    } catch (e2) {
      setError(String(e2.message || e2));
    } finally {
      setBusy(false);
    }
  };

  const deleteTemplate = async (templateId, templateName) => {
    if (!window.confirm(`Delete template "${templateName}"?`)) return;
    setBusy(true);
    setError("");
    try {
      await api(`/templates/${templateId}`, { method: "DELETE" });
      setCleanupReport(null);
      await loadData();
    } catch (e2) {
      setError(String(e2.message || e2));
    } finally {
      setBusy(false);
    }
  };

  const cleanupTemplates = async (dryRun) => {
    setBusy(true);
    setError("");
    try {
      const report = await api("/templates/cleanup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dry_run: dryRun,
          include_scratch: true,
          include_test: true,
          only_unreferenced: true,
        }),
      });
      setCleanupReport(report);
      if (!dryRun) {
        await loadData();
      }
    } catch (e2) {
      setError(String(e2.message || e2));
    } finally {
      setBusy(false);
    }
  };

  const runRevision = async () => {
    if (!deck) return;
    setBusy(true);
    setError("");
    try {
      const result = await api(`/decks/${deck.id}/revise`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: revisePrompt,
          provider,
          agent_mode: agentMode,
          quality_profile: qualityProfile,
          max_correction_passes: Number(maxCorrectionPasses),
        }),
      });
      setJob(result);
      setJobEvents([]);
      setQualityReport(null);
      setEditorConfig(null);
    } catch (e2) {
      setError(String(e2.message || e2));
    } finally {
      setBusy(false);
    }
  };

  const openEditorSession = async () => {
    if (!deck) return;
    try {
      const result = await api("/editor/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deck_id: deck.id }),
      });
      setEditorConfig(result.config);
      setEditorMountReady(true);
    } catch (e) {
      setError(String(e.message || e));
    }
  };

  const toggleDoc = (docId) => {
    setSelectedDocIds((prev) =>
      prev.includes(docId) ? prev.filter((id) => id !== docId) : [...prev, docId]
    );
  };

  return (
    <div className="page">
      <header>
        <h1>PowerPoint Agent</h1>
        <p>Prompt → Research + Citations → PPTX → Revision Loop</p>
      </header>

      {error && <div className="error">{error}</div>}

      <section className="grid">
        <div className="card">
          <h2>1) Upload Template</h2>
          <form onSubmit={uploadTemplate}>
            <input value={templateName} onChange={(e) => setTemplateName(e.target.value)} placeholder="Template name" />
            <input type="file" accept=".pptx" onChange={(e) => setTemplateFile(e.target.files?.[0] || null)} />
            <button disabled={busy || !templateFile}>Upload Template</button>
          </form>
          <ul>
            {templates.map((t) => (
              <li key={t.id}>
                <span>{t.name} ({t.status})</span>
                <button type="button" disabled={busy} onClick={() => deleteTemplate(t.id, t.name)}>
                  Delete
                </button>
              </li>
            ))}
          </ul>
          <div className="row">
            <button type="button" disabled={busy} onClick={() => cleanupTemplates(true)}>
              Preview Cleanup
            </button>
            <button type="button" disabled={busy} onClick={() => cleanupTemplates(false)}>
              Cleanup Hidden/Test Templates
            </button>
          </div>
          {cleanupReport && (
            <p>
              {cleanupReport.dry_run ? "Dry run" : "Cleanup"}: matched {cleanupReport.matched_ids.length}, deleted{" "}
              {cleanupReport.deleted_ids.length}, skipped {cleanupReport.skipped.length}.
            </p>
          )}
        </div>

        <div className="card">
          <h2>2) Upload Reference Docs</h2>
          <form onSubmit={uploadDoc}>
            <input type="file" accept=".txt,.md,.pdf,.docx" onChange={(e) => setDocFile(e.target.files?.[0] || null)} />
            <button disabled={busy || !docFile}>Upload Doc</button>
          </form>
          <div className="doc-list">
            {docs.map((doc) => (
              <label key={doc.id}>
                <input type="checkbox" checked={selectedDocIds.includes(doc.id)} onChange={() => toggleDoc(doc.id)} />
                {doc.filename}
              </label>
            ))}
          </div>
        </div>
      </section>

      <section className="card">
        <h2>3) Generate Deck</h2>
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={4} />
        <div className="row">
          <label>
            Mode
            <select value={creationMode} onChange={(e) => setCreationMode(e.target.value)}>
              <option value="template">template</option>
              <option value="scratch">scratch</option>
            </select>
          </label>
          <label>
            Template
            <select
              value={selectedTemplateId}
              onChange={(e) => setSelectedTemplateId(e.target.value)}
              disabled={creationMode !== "template"}
            >
              <option value="">Select template</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Scratch Theme
            <select
              value={scratchTheme}
              onChange={(e) => setScratchTheme(e.target.value)}
              disabled={creationMode !== "scratch"}
            >
              <option value="default">default</option>
              <option value="dark">dark</option>
              <option value="corporate">corporate</option>
            </select>
          </label>
          <label>
            Slides
            <input type="number" value={slideCount} min={1} max={30} onChange={(e) => setSlideCount(e.target.value)} />
          </label>
          <label>
            Provider
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              <option value="mock">mock</option>
              <option value="openai">openai</option>
              <option value="anthropic">anthropic</option>
            </select>
          </label>
          <label>
            Agent Mode
            <select value={agentMode} onChange={(e) => setAgentMode(e.target.value)}>
              <option value="bounded">bounded</option>
              <option value="off">off</option>
            </select>
          </label>
          <label>
            Quality Profile
            <select value={qualityProfile} onChange={(e) => setQualityProfile(e.target.value)}>
              <option value="fast">fast</option>
              <option value="balanced">balanced</option>
              <option value="high_fidelity">high_fidelity</option>
            </select>
          </label>
          <label>
            Max Corrections
            <input
              type="number"
              min={0}
              max={2}
              value={maxCorrectionPasses}
              onChange={(e) => setMaxCorrectionPasses(e.target.value)}
            />
          </label>
        </div>
        <button disabled={busy || !canGenerate} onClick={runGeneration}>Generate</button>
      </section>

      <section className="grid">
        <div className="card">
          <h2>Job Status</h2>
          {job ? (
            <>
              <p><strong>{job.status}</strong> | {job.phase}</p>
              <progress max="100" value={job.progress_pct} />
              <p>{job.progress_pct}%</p>
              {job.error_message && <p className="error">{job.error_message}</p>}
              {jobEvents.length > 0 && (
                <details>
                  <summary>Trace Events ({jobEvents.length})</summary>
                  <ul>
                    {jobEvents.slice(-40).map((event) => (
                      <li key={`${event.id}-${event.event_type}`}>
                        [{event.stage}] {event.event_type}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </>
          ) : (
            <p>No active job.</p>
          )}
        </div>

        <div className="card">
          <h2>4) Output + Revision</h2>
          {deck ? (
            <>
              <p>Deck ID: {deck.id}</p>
              <p>Latest Version: {deck.latest_version}</p>
              {latestVersionInfo?.warnings?.length > 0 && (
                <div className="error">
                  <strong>Warnings:</strong>
                  <ul>
                    {latestVersionInfo.warnings.map((w, idx) => (
                      <li key={`${idx}-${w}`}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}
              {qualityReport && (
                <div>
                  <p>
                    Quality Score: <strong>{qualityReport.score ?? "n/a"}</strong> | Passes Used:{" "}
                    <strong>{qualityReport.passes_used ?? 0}</strong>
                  </p>
                  {(qualityReport.issues?.qa_issues || []).length > 0 && (
                    <details>
                      <summary>QA Issues ({qualityReport.issues.qa_issues.length})</summary>
                      <pre>{JSON.stringify(qualityReport.issues.qa_issues.slice(0, 20), null, 2)}</pre>
                    </details>
                  )}
                </div>
              )}
              <a href={`${API_BASE}/decks/${deck.id}/download`} target="_blank" rel="noreferrer">
                Download .pptx
              </a>
              <textarea value={revisePrompt} onChange={(e) => setRevisePrompt(e.target.value)} rows={3} />
              <button disabled={busy} onClick={runRevision}>Run Revision Prompt</button>
              <button onClick={openEditorSession}>Create Editor Session Config</button>
              {editorConfig && (
                <>
                  <div id="onlyoffice-editor" style={{ height: "560px", marginTop: 12, border: "1px solid #e5e7eb" }} />
                  <details>
                    <summary>ONLYOFFICE Config JSON</summary>
                    <pre>{JSON.stringify(editorConfig, null, 2)}</pre>
                  </details>
                </>
              )}
            </>
          ) : (
            <p>No generated deck yet.</p>
          )}
        </div>
      </section>
    </div>
  );
}

