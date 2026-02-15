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
          scratch_theme: null,
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
        <p>AI-powered deck generation with template fidelity</p>
      </header>

      {error && <div className="error">{error}</div>}

      <section className="grid">
        <div className="card">
          <h2>Upload Template</h2>
          <form onSubmit={uploadTemplate}>
            <label>Template Name</label>
            <input
              type="text"
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
              placeholder="Enter template name"
            />
            <label style={{ marginTop: "12px" }}>PPTX File</label>
            <input
              type="file"
              accept=".pptx"
              onChange={(e) => setTemplateFile(e.target.files?.[0] || null)}
            />
            <div className="row">
              <button type="submit" disabled={busy || !templateFile} className="btn-primary">
                {busy ? "Uploading..." : "Upload Template"}
              </button>
            </div>
          </form>
          
          {templates.length > 0 && (
            <div className="template-list">
              <label style={{ marginBottom: "8px" }}>Your Templates</label>
              {templates.map((t) => (
                <div key={t.id} className="template-item">
                  <span className="template-name">{t.name}</span>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span className="template-status">{t.status}</span>
                    <button
                      type="button"
                      className="btn-ghost btn-sm"
                      disabled={busy}
                      onClick={() => deleteTemplate(t.id, t.name)}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="row" style={{ marginTop: "16px" }}>
            <button type="button" className="btn-secondary btn-sm" disabled={busy} onClick={() => cleanupTemplates(true)}>
              Preview Cleanup
            </button>
            <button type="button" className="btn-secondary btn-sm" disabled={busy} onClick={() => cleanupTemplates(false)}>
              Cleanup Hidden
            </button>
          </div>
          {cleanupReport && (
            <p style={{ fontSize: "0.85rem", color: "var(--color-text-secondary)", marginTop: "12px" }}>
              {cleanupReport.dry_run ? "Dry run" : "Cleanup"}: matched {cleanupReport.matched_ids.length}, deleted {cleanupReport.deleted_ids.length}, skipped {cleanupReport.skipped.length}.
            </p>
          )}
        </div>

        <div className="card">
          <h2>Reference Documents</h2>
          <form onSubmit={uploadDoc}>
            <input
              type="file"
              accept=".txt,.md,.pdf,.docx"
              onChange={(e) => setDocFile(e.target.files?.[0] || null)}
            />
            <div className="row">
              <button type="submit" disabled={busy || !docFile} className="btn-primary">
                {busy ? "Uploading..." : "Upload Document"}
              </button>
            </div>
          </form>
          
          {docs.length > 0 ? (
            <div className="doc-list">
              {docs.map((doc) => (
                <label key={doc.id}>
                  <input
                    type="checkbox"
                    checked={selectedDocIds.includes(doc.id)}
                    onChange={() => toggleDoc(doc.id)}
                  />
                  {doc.filename}
                </label>
              ))}
            </div>
          ) : (
            <p className="empty-state">No documents uploaded yet</p>
          )}
        </div>
      </section>

      <section className="card section">
        <h2>Generate Deck</h2>
        <label>Your Prompt</label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Describe the deck you want to create..."
        />
        
        <div className="form-row">
          <div>
            <label>Creation Mode</label>
            <select value={creationMode} onChange={(e) => setCreationMode(e.target.value)}>
              <option value="template">Use Template</option>
              <option value="scratch">From Scratch</option>
            </select>
          </div>
          
          <div>
            <label>Template</label>
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
          </div>
          
          <div>
            <label>Slide Count</label>
            <input
              type="number"
              value={slideCount}
              min={1}
              max={30}
              onChange={(e) => setSlideCount(Number(e.target.value))}
            />
          </div>
          
          <div>
            <label>Provider</label>
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              <option value="mock">Mock</option>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
            </select>
          </div>
        </div>
        
        <div className="form-row">
          <div>
            <label>Agent Mode</label>
            <select value={agentMode} onChange={(e) => setAgentMode(e.target.value)}>
              <option value="bounded">Bounded</option>
              <option value="off">Off</option>
            </select>
          </div>
          
          <div>
            <label>Quality Profile</label>
            <select value={qualityProfile} onChange={(e) => setQualityProfile(e.target.value)}>
              <option value="fast">Fast</option>
              <option value="balanced">Balanced</option>
              <option value="high_fidelity">High Fidelity</option>
            </select>
          </div>
          
          <div>
            <label>Max Corrections</label>
            <input
              type="number"
              min={0}
              max={2}
              value={maxCorrectionPasses}
              onChange={(e) => setMaxCorrectionPasses(Number(e.target.value))}
            />
          </div>
        </div>
        
        <button disabled={busy || !canGenerate} onClick={runGeneration} className="btn-primary" style={{ width: "100%", marginTop: "8px" }}>
          {busy ? "Generating..." : "Generate Deck"}
        </button>
      </section>

      <section className="grid">
        <div className="card">
          <h2>Job Status</h2>
          {job ? (
            <>
              <div className="job-info">
                <div className="job-info-item">
                  <span className="job-info-label">Status</span>
                  <span className={`status status-${job.status}`}>{job.status}</span>
                </div>
                <div className="job-info-item">
                  <span className="job-info-label">Phase</span>
                  <span className="job-info-value">{job.phase}</span>
                </div>
                <div className="job-info-item">
                  <span className="job-info-label">Progress</span>
                  <span className="job-info-value">{job.progress_pct}%</span>
                </div>
              </div>
              
              <div className="progress-wrapper">
                <progress max="100" value={job.progress_pct} />
              </div>
              
              {job.error_message && (
                <div className="error" style={{ marginTop: "12px" }}>
                  {job.error_message}
                </div>
              )}
              
              {jobEvents.length > 0 && (
                <details>
                  <summary>Trace Events ({jobEvents.length})</summary>
                  <ul>
                    {jobEvents.slice(-40).map((event) => (
                      <li key={`${event.id}-${event.event_type}`} style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem" }}>
                        <span style={{ color: "var(--color-text-secondary)" }}>[{event.stage}]</span>
                        <span>{event.event_type}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </>
          ) : (
            <p className="empty-state">No active job</p>
          )}
        </div>

        <div className="card">
          <h2>Output & Revision</h2>
          {deck ? (
            <>
              <div className="job-info">
                <div className="job-info-item">
                  <span className="job-info-label">Deck ID</span>
                  <span className="job-info-value">{deck.id.slice(0, 8)}...</span>
                </div>
                <div className="job-info-item">
                  <span className="job-info-label">Version</span>
                  <span className="job-info-value">v{deck.latest_version}</span>
                </div>
              </div>
              
              {latestVersionInfo?.warnings?.length > 0 && (
                <div className="warning-box">
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
                  <div className="quality-badge">
                    <span className="quality-badge-value">{qualityReport.score ?? "N/A"}</span>
                    <span style={{ color: "#b45309", fontSize: "0.8rem" }}>Quality Score</span>
                  </div>
                  
                  {(qualityReport.issues?.qa_issues || []).length > 0 && (
                    <details>
                      <summary>QA Issues ({qualityReport.issues.qa_issues.length})</summary>
                      <pre>{JSON.stringify(qualityReport.issues.qa_issues.slice(0, 10), null, 2)}</pre>
                    </details>
                  )}
                </div>
              )}
              
              <a
                href={`${API_BASE}/decks/${deck.id}/download`}
                target="_blank"
                rel="noreferrer"
                className="btn-primary"
                style={{ display: "block", textAlign: "center", marginTop: "16px", textDecoration: "none" }}
              >
                Download PPTX
              </a>
              
              <label style={{ marginTop: "16px" }}>Revision Prompt</label>
              <textarea
                value={revisePrompt}
                onChange={(e) => setRevisePrompt(e.target.value)}
                rows={2}
              />
              
              <div className="row">
                <button disabled={busy} onClick={runRevision} className="btn-secondary">
                  Run Revision
                </button>
                <button onClick={openEditorSession} className="btn-ghost">
                  Editor Config
                </button>
              </div>
              
              {editorConfig && (
                <>
                  <div id="onlyoffice-editor" />
                  <details style={{ marginTop: "12px" }}>
                    <summary>ONLYOFFICE Config</summary>
                    <pre>{JSON.stringify(editorConfig, null, 2)}</pre>
                  </details>
                </>
              )}
            </>
          ) : (
            <p className="empty-state">Generate a deck to see output here</p>
          )}
        </div>
      </section>
    </div>
  );
}
