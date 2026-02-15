# Agentic Upgrade Backlog

Status date: February 15, 2026  
Source spec: `docs/UPGRADES.md`

## Estimation Model

- `S` = 1-2 dev days
- `M` = 3-5 dev days
- `L` = 6-10 dev days
- `XL` = 11-15 dev days

Assumptions:
- 1 backend engineer full-time
- 1 frontend engineer part-time
- Existing infra (Redis/Celery/FastAPI/sqlite) remains in place during initial rollout

## Milestone Plan

1. `P0 Foundations` (target: 1 sprint)
2. `P1 Quality Levers` (target: 1-2 sprints)
3. `P2 Agentic Compose` (target: 1-2 sprints)
4. `P3 Productization` (target: 1 sprint)

---

## P0 Foundations

### AGT-001 Tool Interface + Runner
- Phase: `P0`
- Effort: `L`
- Owner: Backend
- Dependencies: None
- Scope:
  - Add tool contract types and registry.
  - Add `ToolRunner` with schema validation + timeout + result normalization.
  - Add safe execution wrapper so tool failures do not crash jobs.
- Deliverables:
  - `backend/app/tools/base.py`
  - `backend/app/tools/registry.py`
  - `backend/app/tools/runner.py`
- Acceptance criteria:
  - Tools can be registered and executed by name.
  - Invalid input fails with structured error.
  - Timeout and exception handling return standardized `ToolResult`.

### AGT-002 Job Events Persistence
- Phase: `P0`
- Effort: `M`
- Owner: Backend
- Dependencies: AGT-001
- Scope:
  - Add `job_events` table and write helper.
  - Persist planner/executor/critic and stage transition events.
- Deliverables:
  - Model + migration/update bootstrap in `backend/app/models.py`
  - Event service in `backend/app/services/job_events.py`
- Acceptance criteria:
  - Every generate/revise job writes ordered event records.
  - Event payloads include phase, timestamps, and summary metadata.

### AGT-003 Tool Run Audit Persistence
- Phase: `P0`
- Effort: `M`
- Owner: Backend
- Dependencies: AGT-001
- Scope:
  - Add `tool_runs` table.
  - Record each tool run with status, duration, hashes, and artifact refs.
- Deliverables:
  - Model + write API for `tool_runs`
  - Instrument `ToolRunner` to emit audit rows
- Acceptance criteria:
  - All tool invocations are queryable by `job_id`.
  - Failed runs contain normalized error payload.

### AGT-004 Generate API Controls
- Phase: `P0`
- Effort: `S`
- Owner: Backend
- Dependencies: None
- Scope:
  - Extend generate request with:
    - `agent_mode: off|bounded`
    - `quality_profile: fast|balanced|high_fidelity`
    - `max_correction_passes`
- Deliverables:
  - Schema updates in `backend/app/schemas.py`
  - API validation in `backend/app/main.py`
- Acceptance criteria:
  - Request parsing and bounds enforcement works.
  - Defaults are backward compatible with existing clients.

### AGT-005 Job Events API
- Phase: `P0`
- Effort: `S`
- Owner: Backend
- Dependencies: AGT-002
- Scope:
  - Add `GET /api/jobs/{job_id}/events`.
- Deliverables:
  - Endpoint + response schema
- Acceptance criteria:
  - Returns chronologically ordered events.
  - Supports basic pagination or bounded response length.

---

## P1 Quality Levers

### AGT-101 Visual QA Tool (First Pass)
- Phase: `P1`
- Effort: `L`
- Owner: Backend
- Dependencies: AGT-001
- Scope:
  - Add `render.thumbnail_grid` tool.
  - Add `qa.visual_check` tool returning issue list:
    - overflow
    - overlap
    - contrast
    - edge collision
- Deliverables:
  - Tools under `backend/app/tools/render_*` and `backend/app/tools/qa_*`
- Acceptance criteria:
  - QA tool returns structured issue objects with slide references.
  - Tool output persisted in `tool_runs`.

### AGT-102 Correction Loop (1 Pass)
- Phase: `P1`
- Effort: `L`
- Owner: Backend
- Dependencies: AGT-101, AGT-004
- Scope:
  - Add single correction pass when critical issues detected.
  - Restrict pass count by request and server limit.
- Deliverables:
  - Loop logic in `backend/app/tasks.py`
- Acceptance criteria:
  - If critical issue found, one correction attempt executes.
  - Final quality report indicates pass outcome.

### AGT-103 Research Routing Toolization
- Phase: `P1`
- Effort: `M`
- Owner: Backend
- Dependencies: AGT-001
- Scope:
  - Move current routing logic to tool form (`research.route_sources`).
  - Log selected sources per slide in events.
- Deliverables:
  - Research routing tool + tests
- Acceptance criteria:
  - Slide-level source routing uses top-k selection.
  - Event trace includes source titles by slide.

### AGT-104 Template High-Fidelity Path (Pilot)
- Phase: `P1`
- Effort: `XL`
- Owner: Backend
- Dependencies: AGT-001, AGT-101
- Scope:
  - Add conditional tool path for template decks:
    - inventory extraction
    - preserve-format replacement
    - validation
  - Keep existing renderer path as fallback.
- Deliverables:
  - Planner decision hook in generation job
  - Tool-backed template pipeline implementation
- Acceptance criteria:
  - Complex template pilot set shows improved fidelity vs baseline.
  - Hard fallback to renderer when tool path fails.

### AGT-105 Scratch Component Library v1
- Phase: `P1`
- Effort: `XL`
- Owner: Backend
- Dependencies: AGT-004
- Scope:
  - Implement component-based scratch builder:
    - hero
    - KPI cards
    - two-column
    - timeline
    - section break
  - Add deterministic layout selection policy.
- Deliverables:
  - New scratch composition module (or substantial `scratch_pptx_service` refactor)
- Acceptance criteria:
  - No plain text-only slides unless explicitly requested.
  - Theme token consistency across scratch output.

---

## P2 Agentic Compose

### AGT-201 Planner Module
- Phase: `P2`
- Effort: `L`
- Owner: Backend
- Dependencies: AGT-001, AGT-004
- Scope:
  - Implement bounded planner producing step list:
    - stage
    - tool
    - inputs
    - budget constraints
- Deliverables:
  - `backend/app/agent/planner.py`
- Acceptance criteria:
  - Planner output is deterministic/validated.
  - Steps capped by policy.

### AGT-202 Executor Module
- Phase: `P2`
- Effort: `M`
- Owner: Backend
- Dependencies: AGT-201
- Scope:
  - Execute planner steps via `ToolRunner`.
  - Persist events and tool runs.
- Deliverables:
  - `backend/app/agent/executor.py`
- Acceptance criteria:
  - Partial failure handling works with policy-based fallback.

### AGT-203 Critic Module
- Phase: `P2`
- Effort: `M`
- Owner: Backend
- Dependencies: AGT-101, AGT-202
- Scope:
  - Evaluate output quality report and determine correction actions.
- Deliverables:
  - `backend/app/agent/critic.py`
- Acceptance criteria:
  - Critic issues actionable fix instructions.
  - Max correction pass policy is respected.

### AGT-204 Agent Orchestrator Integration
- Phase: `P2`
- Effort: `L`
- Owner: Backend
- Dependencies: AGT-201, AGT-202, AGT-203
- Scope:
  - Wire planner/executor/critic into generate/revise jobs under `agent_mode=bounded`.
- Deliverables:
  - Orchestrator entrypoints in `backend/app/tasks.py`
- Acceptance criteria:
  - `agent_mode=off` preserves current behavior.
  - `agent_mode=bounded` runs full orchestrated pipeline.

---

## P3 Productization

### AGT-301 Quality Report API
- Phase: `P3`
- Effort: `S`
- Owner: Backend
- Dependencies: AGT-102
- Scope:
  - Add `GET /api/decks/{deck_id}/quality/{version}`.
- Deliverables:
  - Endpoint + schema + storage wiring
- Acceptance criteria:
  - Returns scores, issues, corrections applied.

### AGT-302 Frontend Trace UI
- Phase: `P3`
- Effort: `M`
- Owner: Frontend
- Dependencies: AGT-005
- Scope:
  - Add job event timeline panel.
  - Show tool runs and quality summaries.
- Deliverables:
  - Updates in `frontend/src/App.jsx` and related components
- Acceptance criteria:
  - User can inspect full generation trace by job.

### AGT-303 Frontend Quality Controls
- Phase: `P3`
- Effort: `S`
- Owner: Frontend
- Dependencies: AGT-004
- Scope:
  - Expose `agent_mode`, `quality_profile`, `max_correction_passes` in generation UI.
- Acceptance criteria:
  - Controls are sent in request payload.
  - Defaults match backend.

### AGT-304 Golden-Set Evaluator
- Phase: `P3`
- Effort: `L`
- Owner: Backend
- Dependencies: AGT-104, AGT-105
- Scope:
  - Add benchmark runner and report output.
- Deliverables:
  - `scripts/eval_golden_set.py` (or equivalent)
  - Dataset manifest in `workspace/` or `docs/fixtures/`
- Acceptance criteria:
  - Produces repeatable metric report for release gating.

---

## Cross-Cutting Tasks

### AGT-401 Security and Redaction
- Effort: `M`
- Scope:
  - Redact API keys/sensitive source snippets in traces/logs.
  - Add safe preview truncation.
- Acceptance criteria:
  - Sensitive tokens never appear in logs/events.

### AGT-402 Reliability and Idempotency
- Effort: `M`
- Scope:
  - Add idempotency keys for generate/revise.
  - Add safe retry semantics for worker crashes.
- Acceptance criteria:
  - Duplicate request handling is deterministic.

### AGT-403 Automated Tests
- Effort: `L`
- Scope:
  - Add unit/integration coverage for tools, orchestrator, and APIs.
- Acceptance criteria:
  - CI validates core paths and schema contracts.

---

## Critical Path

1. AGT-001 -> AGT-002 -> AGT-005
2. AGT-101 -> AGT-102
3. AGT-105 (scratch quality uplift)
4. AGT-104 (template fidelity uplift)
5. AGT-201/202/203/204 (agent orchestration)

## Recommended Sprint Slice

### Sprint 1
- AGT-001, AGT-002, AGT-003, AGT-004, AGT-005

### Sprint 2
- AGT-101, AGT-102, AGT-103

### Sprint 3
- AGT-105, AGT-104 (pilot templates)

### Sprint 4
- AGT-201, AGT-202, AGT-203, AGT-204

### Sprint 5
- AGT-301, AGT-302, AGT-303, AGT-304, AGT-401, AGT-402, AGT-403

## Exit Criteria by Phase

### Exit P0
- Tool runner active and auditable
- Job event API available
- Request controls available and validated

### Exit P1
- Visual QA loop active with one correction pass
- Scratch output no longer text-only
- Template pilot fidelity improvement demonstrated

### Exit P2
- Bounded agent orchestration live behind flag
- Deterministic fallback path proven in failure tests

### Exit P3
- Trace and quality visible in UI
- Golden-set evaluator integrated into release flow
