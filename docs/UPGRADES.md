# Agentic Upgrade Specification

Status date: February 15, 2026

Execution backlog: `docs/UPGRADES_BACKLOG.md`

## 1. Purpose

This document defines the implementation plan to move the PPT Agent from:
- Strong but mostly linear orchestration
- To a bounded, tool-using agent pipeline with iterative quality control

Target quality outcome:
- Template-based generation: from ~80% to 92-95% acceptance
- Scratch (no-template) generation: from ~60% to 80-88% acceptance

## 2. Problem Statement

Current backend behavior is LLM-orchestrated but not fully agentic:
- Prompt -> structured JSON -> render -> done
- Fixed research call (Exa) and fixed deterministic quality rewrite
- No dynamic tool selection and no visual correction loop
- Skill docs are injected into prompts, but script workflows are not executed as runtime tools

Main quality gaps:
- Template mode: difficult edge cases (complex shapes, residual overflow, partial layout mismatch)
- Scratch mode: weak design composition (layout, visual hierarchy, component richness)
- Limited introspection into generation quality prior to final output

## 3. Goals and Non-Goals

### Goals

1. Introduce a bounded agent loop with explicit planning, tool execution, and critique.
2. Execute runtime tools for PPTX editing and validation instead of prompt-only guidance.
3. Add visual QA and automatic correction pass(es).
4. Improve scratch generation with a true layout/component system.
5. Provide clear observability: step-level events, tool runs, quality signals.
6. Preserve deterministic fallback behavior and production safety.

### Non-Goals

1. Unbounded autonomous behavior.
2. Unlimited retries or unconstrained cost/latency.
3. Replacing all current deterministic code paths in one release.
4. Introducing non-portable infra dependencies in phase 1.

## 4. Target Architecture

## 4.1 High-Level Flow

1. Intake
2. Plan
3. Execute tools
4. Generate content
5. Render
6. Visual QA
7. Optional auto-fix pass
8. Persist artifacts and trace

## 4.2 Runtime Roles

1. Planner
- Produces bounded step plan from request + template manifest + constraints
- Chooses tool path per slide/deck (renderer path vs OOXML path)

2. Executor
- Runs approved tools
- Captures artifacts (manifest snapshots, thumbnails, patched decks)

3. Critic
- Scores output against quality gates (fit, overlap, contrast, completeness)
- Requests max N correction passes (default 1, max 2)

## 4.3 Safety and Bounds

1. Max plan steps per job: default 12
2. Max correction passes: default 1
3. Max tool runtime per call: configurable timeout per tool
4. Max concurrent tool calls: bounded by worker config
5. Hard failover to deterministic renderer path when tool step fails

## 5. Tooling Design

## 5.1 Tool Interface Contract

Every tool implements:
- `name`
- `input_schema` (JSON schema)
- `run(input) -> ToolResult`
- `ToolResult` fields:
  - `ok: bool`
  - `summary: str`
  - `artifacts: dict[str, str]` (paths/ids)
  - `metrics: dict[str, float|int|str]`
  - `warnings: list[str]`
  - `error: str|None`

## 5.2 Initial Tool Set (P0/P1)

1. Research tools
- `research.exa_search` (already present logic, formalized as tool)
- `research.route_sources` (per-slide source selection)

2. Template/PPTX tools
- `pptx.inspect_inventory` (shape/text inventory extraction)
- `pptx.replace_text_preserve_format`
- `pptx.validate_layout` (overflow and structural checks)
- `pptx.ooxml_unpack`
- `pptx.ooxml_patch`
- `pptx.ooxml_validate`
- `pptx.ooxml_pack`

3. Render/QA tools
- `render.template_render`
- `render.scratch_render`
- `render.thumbnail_grid`
- `qa.visual_check` (vision-assisted issue detection)
- `qa.content_check` (slot completeness, citation presence, budget checks)

4. Scratch composition tools
- `scratch.layout_select`
- `scratch.component_compose`
- `scratch.theme_apply`

## 5.3 Tool Runner

Add a `ToolRunner` service:
- White-listed tool registry
- Input schema validation before execution
- Standardized output capture
- Retry policy by tool type
- Audit logging (start/end/duration/input hash/result hash)

## 6. Template Mode Upgrade Specification

## 6.1 Runtime Decision

Planner decides per deck/slide:
- Path A: current renderer path (fast, simple)
- Path B: OOXML/replace tool path (high fidelity for complex templates)

Decision signals:
- Number of freeform text shapes
- Presence of grouped shapes and table-heavy slides
- Placeholder sparsity
- Prior overflow/fidelity failure pattern for this template

## 6.2 Execution Path

1. Parse manifest and shape inventory
2. Generate slot payloads
3. Apply replace-preserve-format tool
4. Validate structural and overflow constraints
5. Render and run visual QA
6. If fail and correction budget available: revise targeted slots and re-apply

## 6.3 Acceptance Criteria

1. No style-destructive replacements (`shape.text = ...` style failures blocked)
2. No unresolved template tokens
3. Overflow regressions prevented or flagged with hard warning
4. Citation slots populated when required

## 7. Scratch Mode Upgrade Specification

## 7.1 Component Layout System

Replace generic placeholder flow with componentized composition:
- Hero title
- KPI cards
- Two-column comparison
- Timeline/process
- Quote/highlight
- Section break
- Data summary card

Each component has:
- Geometry rules
- Typography rules
- Color token usage
- Content density constraints

## 7.2 Theme Packs

Ship theme packs as versioned assets:
- `default`, `dark`, `corporate` baseline packs
- Optional brand pack support (future)

Each theme defines:
- Color tokens
- Font pairings
- Shape styles
- Spacing scale
- Motion/transition policy (optional)

## 7.3 Layout Selection Policy

Inputs:
- Slide archetype
- Narrative role/key message
- Bullet count/body length
- Visual density target

Output:
- Chosen component/layout id
- Slot-to-component binding map

## 7.4 Acceptance Criteria

1. Every scratch slide includes at least one visual component beyond plain text
2. Theme tokens are consistently applied across all slides
3. No white-only fallback unless explicitly requested
4. Readability thresholds pass (contrast, minimum font size, spacing)

## 8. Visual QA Loop

## 8.1 QA Checks

1. Overflow/cutoff
2. Text overlap
3. Low contrast
4. Edge/margin collisions
5. Missing section hierarchy cues
6. Citation/footer collisions

## 8.2 Correction Loop

1. Produce issue list with slide and shape references
2. Generate targeted correction instructions
3. Re-run limited tool steps for affected slides
4. Re-check until pass or correction budget exhausted

## 8.3 Acceptance Criteria

1. QA runs on every generation and revision job
2. At least one automated correction attempt when critical issues detected
3. Final quality report contains issue list and resolution status

## 9. API and Data Model Changes

## 9.1 API Additions

1. `POST /api/decks/generate` enhancements
- Add `agent_mode: "off" | "bounded"` (default `"bounded"` for new deployments)
- Add `quality_profile: "fast" | "balanced" | "high_fidelity"`
- Add `max_correction_passes` override (bounded by server policy)

2. `GET /api/jobs/{job_id}/events`
- Returns ordered step/tool events for observability UI

3. `GET /api/decks/{deck_id}/quality/{version}`
- Returns structured quality report including visual QA results

## 9.2 Database Additions

1. `job_events`
- `id`, `job_id`, `ts`, `stage`, `event_type`, `payload_json`, `severity`

2. `tool_runs`
- `id`, `job_id`, `tool_name`, `status`, `duration_ms`, `input_hash`, `output_hash`, `artifact_json`, `error`

3. `quality_reports`
- `id`, `deck_id`, `version`, `score`, `issues_json`, `passes_used`, `created_at`

## 9.3 Storage Artifacts

1. Thumbnails per version
2. Intermediate manifests per correction pass
3. Tool output artifacts (inventory files, validation reports)

## 10. Observability and Logging

1. Keep high-level lifecycle logs
2. Add structured agent trace events
3. Add tool run metrics
4. Add per-provider call timing and parsed output previews
5. Add debug mode for extended payload previews with redaction rules

## 11. Evaluation Harness

## 11.1 Golden Set

Create benchmark decks:
- Template-heavy (complex layouts, grouped objects, tables)
- Scratch style-heavy
- Revision scenarios

## 11.2 Metrics

1. Template fidelity score
2. Overflow incidence
3. Visual defect count per deck
4. Citation coverage
5. Human acceptance rate
6. Avg correction passes
7. Cost and latency by profile

## 11.3 Release Gate

No phase progression unless:
- Template mode acceptance >= 90% on golden set
- Scratch mode acceptance >= 75% (phase 1), >= 80% (phase 2)
- Regression budget not exceeded for latency/cost

## 12. Rollout Plan

## Phase 0: Foundations (1 sprint)

1. Tool interface + runner
2. Job event and tool run persistence
3. Agent mode flagging and hard limits
4. No functional behavior switch yet

## Phase 1: Quality Levers (1-2 sprints)

1. Visual QA loop
2. Source routing per slide
3. Template high-fidelity tool path for selected templates
4. Initial scratch component layouts

## Phase 2: Agentic Compose (1-2 sprints)

1. Planner/executor/critic bounded loop
2. Dynamic path selection per deck
3. Correction pass policy by quality profile

## Phase 3: Productization (1 sprint)

1. UI for quality reports and step trace
2. Outline and plan review UX
3. Controls for style/density/quality profile

## 13. Risks and Mitigations

1. Risk: latency/cost increase from extra passes
- Mitigation: quality profiles + strict pass limits + per-tool timeout

2. Risk: overfitting to golden set
- Mitigation: rotating benchmark corpus and production telemetry sampling

3. Risk: tool failures creating brittle pipeline
- Mitigation: deterministic fallback path and tool health checks

4. Risk: noisy logs and sensitive payload exposure
- Mitigation: redaction, preview limits, env-gated verbosity

## 14. Immediate Implementation Backlog

1. Add `ToolRunner` and initial tool registry.
2. Implement `job_events` and `tool_runs` tables plus APIs.
3. Integrate visual QA tool and one correction pass.
4. Introduce scratch component library (hero, KPI cards, two-column, timeline).
5. Add `agent_mode` and `quality_profile` request fields.
6. Build golden-set evaluator and CI score report.

## 15. Definition of Done

1. Template decks: >= 92% acceptance on golden benchmark.
2. Scratch decks: >= 80% acceptance on golden benchmark.
3. Every job has full step trace and tool-run audit.
4. Visual QA + correction loop enabled in bounded mode.
5. Deterministic fallback path remains available and tested.
