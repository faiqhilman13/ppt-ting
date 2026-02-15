# Repository Guidelines

## Project Structure & Module Organization
- `backend/app/`: FastAPI API, Celery jobs, providers, agent logic, tools, and services.
  - Key folders: `providers/`, `services/`, `agent/`, `tools/`.
- `renderer/app/`: template-fidelity PPTX renderer (`python-pptx`) for token/shape/table mutations.
- `scratch-renderer/src/`: Node + PptxGenJS scratch deck renderer (`builders/`, `themes.js`, `server.js`).
- `frontend/src/`: React + Vite UI.
- `docs/`: architecture and upgrade docs.
- `storage/` and `workspace/`: runtime/generated artifacts; treat as non-source output.

## Build, Test, and Development Commands
- Full stack (recommended): `docker compose up --build`
- Core services only: `docker compose up -d --build backend worker renderer scratch-renderer`
- Backend local: `cd backend && uvicorn app.main:app --reload --port 8000`
- Worker local: `cd backend && celery -A app.celery_app.celery_app worker --loglevel=info --include app.tasks`
- Frontend local: `cd frontend && npm install && npm run dev`
- Scratch renderer local: `cd scratch-renderer && npm install && npm start`
- Fast compile smoke check: `python -m compileall backend/app renderer/app`

## Coding Style & Naming Conventions
- Python: PEP 8, 4-space indentation, type hints, `snake_case` for functions/files, `PascalCase` for classes.
- API schemas use Pydantic models; keep validation explicit.
- JavaScript (`scratch-renderer`): CommonJS (`require/module.exports`), `camelCase` vars/functions, one archetype builder per file.
- Keep prompt templates and tool contracts deterministic; avoid hidden side effects.

## Testing Guidelines
- No formal unit test suite yet; use integration and smoke checks.
- Validate health endpoints: `/health` (renderer/scratch-renderer) and `/docs` (backend).
- For PPT changes, run one generate + one revise flow and verify output deck rendering and citations.
- When touching quality/correction logic, inspect worker logs and `/api/jobs/{id}/events`.

## Commit & Pull Request Guidelines
- Follow Conventional Commit style used in repo history (`feat:`, `fix:`, `docs:`, `chore:`).
- Keep commits focused; include why + impact in PR description.
- PRs should include:
  - changed modules/paths,
  - verification steps/commands,
  - screenshots for frontend or deck visual changes,
  - any env/config updates (`backend/.env.example`, compose changes).

## Security & Configuration Tips
- Never commit real API keys; use `backend/.env` locally and keep `backend/.env.example` updated.
- Prefer internal Docker hostnames in services (`renderer`, `scratch-renderer`, `redis`) over localhost inside containers.
