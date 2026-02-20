import { useMemo, useState } from "react";
import {
  ActionProvider,
  Renderer,
  StateProvider,
  VisibilityProvider,
} from "@json-render/react";
import { registry } from "./registry";

async function queryDemo(apiBase, payload) {
  const response = await fetch(`${apiBase}/demo/json-render/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

export default function JsonRenderDemo({ apiBase, provider }) {
  const [query, setQuery] = useState("Show a trend chart for DBS and include a small data table.");
  const [maxPoints, setMaxPoints] = useState(12);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [renderKey, setRenderKey] = useState(0);

  const canRun = useMemo(() => query.trim().length >= 2 && !busy, [query, busy]);

  const run = async () => {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const next = await queryDemo(apiBase, {
        query,
        max_points: Number(maxPoints),
        provider: provider || null,
        agentic: true,
      });
      setResult(next);
      setRenderKey((prev) => prev + 1);
    } catch (err) {
      setResult(null);
      setError(String(err?.message || err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card section jr-demo-shell">
      <div className="jr-demo-header">
        <h2>JSON Render Demo</h2>
        <p>Query fake SQLite market data and render chart/table specs returned by the backend.</p>
        <p className="jr-provider">Provider: {provider || "default"}</p>
      </div>

      <div className="form-row">
        <div style={{ gridColumn: "span 3" }}>
          <label>Demo Query</label>
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Ask for trend, comparison, or fundamentals table"
          />
        </div>
        <div>
          <label>Max Points</label>
          <input
            type="number"
            value={maxPoints}
            min={6}
            max={24}
            onChange={(event) => setMaxPoints(Number(event.target.value))}
          />
        </div>
      </div>

      <div className="row">
        <button type="button" className="btn-accent" disabled={!canRun} onClick={run}>
          {busy ? "Querying..." : "Run JSON Render Query"}
        </button>
      </div>

      {error && <div className="error" style={{ marginTop: "14px" }}>{error}</div>}

      {result && (
        <div className="jr-demo-output">
          <div className="jr-demo-meta">
            <span className="status status-completed">intent: {result.intent}</span>
            <span className="jr-sources">sources: {result.data_sources.join(", ")}</span>
          </div>
          <p className="jr-narrative">{result.narrative}</p>

          <StateProvider key={renderKey} initialState={result.state || {}}>
            <ActionProvider handlers={{}}>
              <VisibilityProvider>
                <Renderer spec={result.spec} registry={registry} />
              </VisibilityProvider>
            </ActionProvider>
          </StateProvider>

          <details>
            <summary>Raw response JSON</summary>
            <pre>{JSON.stringify(result, null, 2)}</pre>
          </details>
        </div>
      )}
    </section>
  );
}
