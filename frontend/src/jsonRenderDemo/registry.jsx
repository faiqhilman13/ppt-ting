import React from "react";
import { defineRegistry } from "@json-render/react";
import { jsonRenderDemoCatalog } from "./catalog";

function DashboardPanel({ props, children }) {
  return (
    <div className="jr-panel">
      <div className="jr-panel-header">
        <div>
          <h3>{props.title}</h3>
          <p>{props.subtitle}</p>
        </div>
        <span className="jr-asof">As of {props.asOf}</span>
      </div>
      <div className="jr-panel-body">{children}</div>
    </div>
  );
}

function KpiStrip({ props }) {
  return (
    <div className="jr-kpi-strip">
      {props.items.map((item, idx) => (
        <div key={`${idx}-${item.label}`} className="jr-kpi">
          <span className="jr-kpi-label">{item.label}</span>
          <strong className="jr-kpi-value">{item.value}</strong>
          <span className="jr-kpi-delta">{item.delta || "\u00a0"}</span>
        </div>
      ))}
    </div>
  );
}

function LineChartCard({ props }) {
  const points = props.points || [];
  const width = 640;
  const height = 220;
  const padding = 28;
  const chartWidth = width - padding * 2;
  const chartHeight = height - padding * 2;

  if (!points.length) {
    return (
      <div className="jr-card">
        <h4>{props.title}</h4>
        <p className="jr-empty">No chart points available.</p>
      </div>
    );
  }

  const values = points.map((row) => row.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 1e-6);

  const svgPoints = points
    .map((point, idx) => {
      const x = padding + (idx * chartWidth) / Math.max(points.length - 1, 1);
      const y = padding + chartHeight - ((point.value - min) / range) * chartHeight;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <div className="jr-card">
      <div className="jr-chart-head">
        <h4>{props.title}</h4>
        <span>{props.yLabel}</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="jr-line-svg">
        <rect x={padding} y={padding} width={chartWidth} height={chartHeight} className="jr-line-grid" />
        <polyline points={svgPoints} className="jr-line-path" />
        {points.map((point, idx) => {
          const x = padding + (idx * chartWidth) / Math.max(points.length - 1, 1);
          const y = padding + chartHeight - ((point.value - min) / range) * chartHeight;
          return <circle key={`${point.label}-${idx}`} cx={x} cy={y} r={3} className="jr-line-dot" />;
        })}
      </svg>
      <div className="jr-axis-labels">
        {points.map((point, idx) => (
          <span key={`${point.label}-${idx}`}>{point.label}</span>
        ))}
      </div>
    </div>
  );
}

function BarChartCard({ props }) {
  const bars = props.bars || [];
  const max = Math.max(...bars.map((row) => row.value), 0);

  return (
    <div className="jr-card">
      <div className="jr-chart-head">
        <h4>{props.title}</h4>
        <span>{props.yLabel}</span>
      </div>
      {bars.length === 0 ? (
        <p className="jr-empty">No bar data available.</p>
      ) : (
        <div className="jr-bars">
          {bars.map((bar, idx) => {
            const widthPct = max > 0 ? Math.max((bar.value / max) * 100, 2) : 0;
            return (
              <div key={`${bar.label}-${idx}`} className="jr-bar-row">
                <span className="jr-bar-label">{bar.label}</span>
                <div className="jr-bar-track">
                  <div className="jr-bar-fill" style={{ width: `${widthPct}%` }} />
                </div>
                <span className="jr-bar-value">{bar.value.toFixed(2)}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function DataTableCard({ props }) {
  return (
    <div className="jr-card">
      <h4>{props.title}</h4>
      <div className="jr-table-wrap">
        <table className="jr-table">
          <thead>
            <tr>
              {props.columns.map((column, idx) => (
                <th key={`${column}-${idx}`}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {props.rows.map((row, idx) => (
              <tr key={`row-${idx}`}>
                {row.map((cell, cellIdx) => (
                  <td key={`cell-${idx}-${cellIdx}`}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function InsightCard({ props }) {
  return (
    <div className="jr-card jr-insight">
      <h4>{props.title}</h4>
      <p>{props.text}</p>
    </div>
  );
}

function FollowupsCard({ props }) {
  return (
    <div className="jr-card">
      <h4>Suggested follow-ups</h4>
      <ul className="jr-followups">
        {props.items.map((item, idx) => (
          <li key={`${idx}-${item}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export const { registry } = defineRegistry(jsonRenderDemoCatalog, {
  components: {
    DashboardPanel,
    KpiStrip,
    LineChartCard,
    BarChartCard,
    DataTableCard,
    InsightCard,
    FollowupsCard,
  },
});
