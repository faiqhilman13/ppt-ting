# PPT Ting - Template-Fidelity PowerPoint Agent

PPT Ting is an agentic app that generates and revises PowerPoint decks from natural-language prompts while preserving a company template 1:1.

The system uses a strict separation of concerns:
- Layout/design fidelity is handled by a renderer that mutates the uploaded `.pptx` template directly.
- AI models only generate slot content (title/body/bullets/citations), not slide layout.
- A deterministic quality pass normalizes and validates content before rendering.

## Repository Structure

- `frontend/` - React + Vite UI
- `backend/` - FastAPI orchestrator + Celery jobs + SQLite metadata
- `renderer/` - FastAPI PPTX renderer (`python-pptx`)
- `storage/` - Runtime artifacts (local only, git-ignored)
- `docker-compose.yml` - Full local stack
- `docs/ARCHITECTURE.md` - Architecture + sequence diagrams
- `docs/IMPLEMENTATION_AND_IMPROVEMENTS.md` - Current state + roadmap

## Core Capabilities

- Upload internal PPTX templates
- Parse slide bindings from:
  - explicit tokens like `{{TITLE}}`, `{{BODY_1}}`, `{{CITATION}}`
  - auto-binded placeholders when tokens are absent
- Generate decks from prompt + optional uploaded docs + web research
- Generate/review deck outlines before content generation (`/api/decks/outline`)
- Revise existing decks with follow-up prompts
- Download generated `.pptx`
- Optional ONLYOFFICE editing flow

## Prerequisites

- Docker Desktop running
- `docker compose` available
- Optional API keys in `backend/.env`:
  - `MINIMAX_API_KEY=...` (for MiniMax generation via Anthropic-compatible API)
  - `MINIMAX_MODEL=MiniMax-M2.5` (default)
  - `MINIMAX_MAX_TOKENS=8192` (default)
  - `MINIMAX_BASE_URL=https://api.minimax.io/anthropic` (default)
  - `OPENAI_API_KEY=...` (for OpenAI generation)
  - `ANTHROPIC_API_KEY=...` (for Anthropic generation)
  - `EXA_API_KEY=...` (for Exa web research + asset metadata)
  - `OPENAI_MODEL=gpt-5-mini` (default)
  - `ANTHROPIC_MODEL=claude-sonnet-4-20250514` (default)
  - `ANTHROPIC_MAX_TOKENS=8192` (default)
  - `DEFAULT_LLM_PROVIDER=minimax` (recommended when using MiniMax)
  - `SCRATCH_THEME=default` (`default`/`dark`/`corporate`)
  - `PPTX_SKILL_ROOT=...` (optional override path to a local `pptx` skill folder)

If no API key is set, backend falls back to deterministic `mock` provider.

## Quick Start (Docker, recommended)

1. Clone this repo and open project root:

```bash
cd /path/to/ppt-ting
```

2. Create env file:

```bash
cp backend/.env.example backend/.env 2>/dev/null || touch backend/.env
```

3. Start core services:

```bash
docker compose up --build
```

4. Optional: include ONLYOFFICE profile:

```bash
docker compose --profile editor up --build
```

5. Open apps:
- Frontend: `http://localhost:5173`
- Backend docs: `http://localhost:8000/docs`
- Renderer health: `http://localhost:3001/health`
- ONLYOFFICE (optional): `http://localhost:8080`

## View Logs

```bash
docker compose logs -f --tail=200
```

To view one service only:

```bash
docker compose logs -f backend
```

## Service Ports

- `frontend`: `5173`
- `backend`: `8000`
- `renderer`: `3001`
- `redis`: `6379`
- `onlyoffice` (optional): `8080`

## End-to-End Test Flow

1. Upload a template from UI (`.pptx` with tokens/placeholders).
2. Upload optional source documents (`.txt`, `.md`, `.pdf`, `.docx`, etc depending extractor support).
3. Prompt generation (example):
   - `Create a 10-slide executive deck on Topic X with risks, roadmap, and KPI impact.`
4. Poll job status until `completed`.
5. Download output PPTX.
6. Submit a revision prompt:
   - `Tighten slide 3 and make tone more investor-facing.`
7. Download revised version.

## API Endpoints

- `POST /api/templates`
- `GET /api/templates`
- `POST /api/docs`
- `GET /api/docs`
- `POST /api/decks/generate`
- `POST /api/decks/{deck_id}/revise`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/events`
- `GET /api/decks`
- `GET /api/decks/{deck_id}`
- `GET /api/decks/{deck_id}/download`
- `GET /api/decks/{deck_id}/quality/{version}`
- `POST /api/search`
- `POST /api/editor/session`
- `POST /api/editor/callback`

Generation/revision request controls:
- `agent_mode`: `off | bounded`
- `quality_profile`: `fast | balanced | high_fidelity`
- `max_correction_passes`: `0..2` (bounded by server policy)

## Local Development (Without Docker)

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Worker

```bash
cd backend
source .venv/bin/activate
celery -A app.celery_app.celery_app worker --loglevel=info --include app.tasks
```

### Renderer

```bash
cd renderer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 3001
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Notes

- This repo intentionally does not commit runtime storage output.
- SQLite DB and generated artifacts are written under `storage/` during runtime.
- For template fidelity, prefer explicit tokens in text/table cells.

## Additional Docs

- Architecture: `docs/ARCHITECTURE.md`
- Implementation status and improvement plan: `docs/IMPLEMENTATION_AND_IMPROVEMENTS.md`
