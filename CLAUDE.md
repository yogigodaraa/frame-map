# CLAUDE.md

## What this is

ProcViz: a five-agent LangGraph pipeline (FastAPI backend) that turns industrial SOP PDFs into
animated spatial-temporal storyboards rendered with Konva. Walkthrough: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**There are two stacks in this repo.** Ask which one before editing:
- **v1 (deployed):** root Vite app (`src/`) → `backend/api/main.py` → `backend/agents/`, `backend/orchestrator/`
- **v2 (tested):** `frontend/` (CRA) → `backend/procviz/`

## Commands

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt   # Python 3.12
pytest                     # 56 tests, offline (stub mode, no AWS needed)
ruff check .               # rules in backend/ruff.toml
uvicorn procviz.main:app --reload --port 8000

# root Vite app (Node >= 22)
npm ci && npm run dev
npm run lint && npm run build
```

## Conventions

- Every agent is `run(state: PipelineState) -> PipelineState`; the schemas in `procviz/schemas/` are the contract between agents.
- Every cloud call (Textract, Bedrock) must keep an offline stub path, so tests stay credential-free.
- Add new graph nodes in `procviz/orchestrator.py::build_graph`, and add a test in `tests/test_pipeline.py`.

## Do not

- Never commit real SOPs, customer documents or AWS credentials. Use synthetic sample procedures.
- Don't remove stub mode or make tests depend on network access.
- Don't edit `frontend/package-lock.json` by hand (it's out of sync; see issues).
