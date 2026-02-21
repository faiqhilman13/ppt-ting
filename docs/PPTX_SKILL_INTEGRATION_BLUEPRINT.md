# PPTX Skill Integration Blueprint

## Purpose
This document defines how to integrate the upgraded local PPTX skill (`C:/Users/faiqh/.codex/skills/pptx`) into this repository so we can implement in a fresh context window without rediscovery.

## Scope
Integrate three new capability paths while preserving current behavior and fallback safety:

1. HTML-first creative rendering (`html2pptx.js`)
2. High-volume template text replacement (`inventory.py` + `replace.py` + `rearrange.py`)
3. Deep OOXML unpack/edit/validate/pack workflow (`ooxml/scripts/*`)

Current baseline must remain functional:
- Scratch generation: `render_scratch_pptx(...)`
- Template-fidelity rendering: existing renderer flow

## Current Integration Points
- Scratch render dispatch: `backend/app/tasks.py` (calls `render_scratch_pptx`)
- Scratch renderer service: `scratch-renderer/src/server.js`
- Scratch backend client: `backend/app/services/scratch_render_client.py`
- Template renderer client path: `backend/app/services/render_client.py`

## Target Architecture
Add explicit render engines and route requests by engine.

Proposed engine enum:
- `scratch_native` (existing `scratch-renderer` builders)
- `scratch_html` (new HTML -> PPTX pipeline)
- `template_renderer` (existing template-fidelity renderer)
- `template_replace` (new inventory/replace pipeline)
- `template_ooxml` (new unpack/edit/validate/pack path)

## Phase Plan

### Phase 1: Scratch HTML Engine
Goal: allow high-fidelity creative slides using `html2pptx.js`.

Implementation:
- Add `render_engine` to request schema (`backend/app/schemas.py`).
- Add routing logic in `backend/app/tasks.py`:
  - scratch + `scratch_html` -> new scratch-renderer endpoint `/render-html`.
  - fallback to existing `scratch_native`.
- Extend `scratch-renderer/src/server.js`:
  - add `/render-html`.
  - call `scripts/html2pptx.js` with strict validation.
- Add backend client wrapper:
  - `backend/app/services/scratch_render_html_client.py` (or extend current client).

Acceptance:
- `scratch_html` jobs produce valid PPTX.
- On HTML render failure, logs warning and auto-fallback to `scratch_native`.

### Phase 2: Template Replace Engine
Goal: fast, high-volume text replacement using structured inventory.

Implementation:
- Add service `backend/app/services/template_replace_service.py`:
  - run `rearrange.py` (optional slide sequence),
  - run `inventory.py`,
  - generate replacement JSON from slots,
  - run `replace.py`,
  - run `inventory.py --issues-only` post-pass.
- Add engine route in `backend/app/tasks.py` for template mode.

Acceptance:
- bulk replacement is faster and preserves template layout.
- issue artifacts generated for overflow/overlap diagnostics.

### Phase 3: OOXML Engine + Validation Gate
Goal: advanced structural edits with schema-aware validation.

Implementation:
- Add service `backend/app/services/ooxml_service.py`:
  - `unpack.py` -> patch XML transforms -> `pack.py` -> `validate.py`.
- Add optional validation gate for all template outputs:
  - run OOXML validate before finalize.
  - configurable fail-open/fail-closed.

Acceptance:
- validation output attached to job events.
- render blocked only when configured fail-closed and critical errors found.

## Required API / Schema Changes
- `GenerateDeckRequest` and revision request:
  - add `render_engine: str | None` with defaults by mode.
- Optional engine-specific payload:
  - `html_spec` (for `scratch_html`)
  - `slide_sequence` (for `template_replace`)
  - `ooxml_patch_mode` (for `template_ooxml`)

## Job Event Logging (Must Add)
Add explicit events for observability:
- `render_engine_selected`
- `html_render_start` / `html_render_complete` / `html_render_fallback`
- `template_replace_inventory_start` / `template_replace_apply_complete`
- `template_replace_issues_detected`
- `ooxml_unpack_start` / `ooxml_validate_complete` / `ooxml_pack_complete`

## Safety Rules
- Keep existing rendering paths as default until each phase is stable.
- Every new engine must have automatic fallback to current stable path.
- Never block completion without writing clear failure reason to job events.

## Validation Checklist Per Phase
- `python -m compileall backend/app renderer/app`
- `docker compose up --build` (or targeted services)
- Generate one scratch and one template deck
- Verify:
  - download opens in PowerPoint
  - no missing text
  - citations and metadata remain intact
  - job events include engine-specific traces

## Fresh-Context Execution Order
1. Implement Phase 1 only and ship behind engine flag.
2. Add Phase 2 with default-off engine selection.
3. Add Phase 3 validate gate in monitor-only mode first.
4. Flip defaults only after comparing output quality and failure rate.
