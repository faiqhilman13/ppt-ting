# Current Implementation and Improvement Plan

Status date: February 15, 2026

## What Is Implemented

### 1. End-to-End deck workflow

- Upload template (`POST /api/templates`)
- Upload documents (`POST /api/docs`)
- Generate deck job (`POST /api/decks/generate`)
- Poll job status (`GET /api/jobs/{job_id}`)
- List/get deck (`GET /api/decks`, `GET /api/decks/{deck_id}`)
- Download pptx (`GET /api/decks/{deck_id}/download`)
- Revise deck (`POST /api/decks/{deck_id}/revise`)

### 2. Template-fidelity rendering

- Renderer mutates template PPTX directly using `python-pptx`.
- Supports token replacement in text boxes and table cells.
- Supports placeholder auto-binding to shape text.
- Preserves native template design and objects not bound to slots.

### 3. Agentic orchestration

- Backend delegates long-running generation/revision to Celery worker.
- Job phases and progress are persisted in `DeckJob`.
- Research context combines uploaded docs and web search.

### 4. LLM provider abstraction

- Providers: `mock`, `openai`, `anthropic`
- Shared output contract:
  - `{"slides": [{"template_slide_index": int, "slots": {...}}]}`

### 5. Quality layer

- Slide archetype inference from slot patterns
- Archetype-specific guidance and sample payloads in prompts
- Slot type classification + character budget enforcement
- Deterministic normalization:
  - unresolved token cleanup
  - bullet normalization
  - citation normalization
  - missing-slot fallback fill

### 6. Optional editor integration

- ONLYOFFICE session config endpoint
- Callback persists manual edits as new deck versions

## Known Constraints

- Layout intelligence is token/placeholder-based; arbitrary shape semantic understanding is limited.
- Tables are text-replace based; no full semantic table planning engine yet.
- Local file storage and SQLite are not production-grade for concurrency and HA.
- Authentication/authorization is not implemented.
- Observability is minimal (no centralized tracing/metrics).

## Potential Improvements (Prioritized)

## P0 (Production readiness)

1. Add auth + RBAC
- API key or OAuth/JWT for all endpoints
- Org/project-level access controls on templates/decks/docs

2. Replace local state infrastructure
- Postgres for metadata
- Object storage (S3/GCS/Azure Blob) for binaries/manifests
- Managed queue/broker for worker durability

3. Add idempotency and retry safety
- Idempotency keys on generate/revise endpoints
- Dedup + safe retries for worker task execution

4. Improve error contracts
- Stable error codes and troubleshooting metadata
- Better user-facing failure diagnostics

## P1 (Slide quality and fidelity)

1. Advanced slot planning
- Build a `slot planner` that scores candidate content by slot fit and reading load
- Handle multi-column and mixed-layout templates more intentionally

2. Structured table synthesis
- Add table schema extraction from template (headers/rows expected)
- Generate cell-level values with constraints

3. Citation grounding
- Per-claim citation mapping (slot-level provenance)
- Confidence scoring and source freshness metadata

4. Better revision precision
- Targeted revisions by slide index and slot name
- Diff-aware revision prompts

## P2 (Agentic product features)

1. Multi-step planning agent
- Stage planning: outline -> slide intent -> slot fill -> render -> critique -> refine

2. Human-in-the-loop checks
- Optional approval gates before render/download
- Constraint checks for compliance language and banned terms

3. Design QA module
- Detect text overflow risk by shape dimensions
- Flag likely visual crowding and low contrast

4. Analytics and feedback loop
- Track user revisions and acceptance rates
- Use telemetry to optimize prompt templates and budgets

## P3 (Developer experience)

1. Full integration test suite
- API + worker + renderer end-to-end tests in CI

2. Contract tests for providers
- Validate provider output schema and fallback behavior

3. Environment templates
- `.env.example` completeness checks
- Startup preflight script

4. Infra packaging
- Helm/Terraform modules for cloud deployment

## Suggested Next Milestone

Implement a `Template Semantic Mapper`:
- Parse each slide’s editable regions into typed intent blocks (title, kicker, bullets, KPI card, table summary, citation).
- Feed this semantic map to the LLM planner.
- Add a post-render validator for overflow and missing mandatory slots.

This gives the biggest quality gain without sacrificing template fidelity.
