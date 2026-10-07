# Copilot instructions for frame-map (ProcViz)

- **Backend:** Python 3.12, FastAPI, Pydantic v2, LangGraph, boto3 (Textract/Bedrock), Anthropic SDK, OR-Tools. From `backend/`: `pip install -r requirements.txt -r requirements-dev.txt`, `pytest`, `ruff check .`.
- **Frontend (deployed):** Vite 8 + React 18 + TypeScript + react-konva at the repo root. Node ≥ 22. `npm ci`, `npm run lint`, `npm run build`.
- **Two stacks:** v1 = root `src/` + `backend/api|agents|orchestrator`; v2 = `frontend/` + `backend/procviz`. Don't mix their APIs (`/api/jobs` vs `/api/pipeline`).
- **Architecture:** agents are pure `PipelineState -> PipelineState` functions wired in `procviz/orchestrator.py`. Every cloud call needs an offline stub. See `docs/ARCHITECTURE.md`.
- **Don't:** commit real documents or credentials, remove stub mode, or add network calls to tests.
- **When reviewing PRs:** check schema changes in `procviz/schemas/` are reflected in the agents that read them and in the renderer types (`src/types/`).
