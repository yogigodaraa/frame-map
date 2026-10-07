# frame-map (ProcViz)

[![CI](https://github.com/yogigodaraa/frame-map/actions/workflows/ci.yml/badge.svg)](https://github.com/yogigodaraa/frame-map/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Document → interactive spatial-temporal visual plan.**

Upload an industrial SOP, work instruction or operational order (PDF) and get back an animated
storyboard showing who does what, where and when. Built for mining, healthcare and defence
procedures.

**Live demo:** <https://frame-map.vercel.app>

## What it does

A five-agent [LangGraph](https://langchain-ai.github.io/langgraph/) pipeline turns unstructured
procedural text into a timeline of actors, actions, locations and dependencies, rendered on an
interactive canvas:

```text
ingestion → extraction → validation ─┬─ low confidence → human review ─┐
                                     └─ ok ────────────────────────────┴→ layout → visual spec
```

1. **Ingestion**: AWS Textract (OCR + layout), Docling fallback for complex tables
2. **Extraction**: Claude turns text into a procedural knowledge graph (JSON validated with Pydantic)
3. **Validation**: rule-based domain checks (missing safety flags, circular dependencies) and the human-review decision
4. **Layout**: in v1, Claude proposes positions and an OR-Tools CP-SAT model refines them. In v2 (proof of concept), a grid heuristic plus a minimum-clearance pass.
5. **Visual spec**: a JSON payload of elements and animation keyframes for the Konva renderer

Without AWS credentials the agents run in **stub mode** (deterministic placeholders and regex
heuristics), so the whole pipeline works offline. That's how the tests run.

## Two versions live in this repo

| | v1 (deployed) | v2 `procviz` (tested) |
|---|---|---|
| Frontend | Vite + React 18 at the repo root (`src/`) | Create React App in `frontend/` |
| Backend | `backend/api/main.py` + `backend/agents/` + `backend/orchestrator/` | `backend/procviz/` |
| API | `POST /api/jobs`, `GET /api/jobs/{id}`, `GET /api/jobs/{id}/spec`, `POST /api/jobs/{id}/review` | `POST /api/pipeline/run`, `GET /api/pipeline/{run_id}`, `GET /api/spec/{spec_id}` |
| LLM access | Anthropic API (`ANTHROPIC_API_KEY`) | Claude on Amazon Bedrock (`AWS_*`, `BEDROCK_MODEL_ID`) |
| Run by | `vercel.json`, `docker-compose.yml` | the test suite (`backend/tests/`) |

Consolidating these is an open decision (see issues).

## Screenshots

<!-- TODO: add a storyboard screenshot/GIF from the demo (synthetic SOP only) -->
_Coming soon. Try the live demo._

## Tech stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2, LangGraph, Anthropic SDK / boto3 (Bedrock, Textract), OR-Tools, Docling
- **Frontend (v1):** Vite 8, React 18, TypeScript, Konva / react-konva, React Dropzone, Tailwind CSS
- **Frontend (v2):** Create React App, React 19, react-konva, React Flow, axios

## Quickstart

```bash
git clone https://github.com/yogigodaraa/frame-map.git
cd frame-map
cp .env.example .env              # all keys optional: without them, agents use stub mode
```

**Backend**

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn procviz.main:app --reload --port 8000          # v2 API
# or, from the repo root:  uvicorn backend.api.main:app --reload   (v1 API)
```

**Frontend (v1, needs Node ≥ 22)**

```bash
npm ci
npm run dev                       # set VITE_API_URL to your backend
```

Or run both v1 services with `docker-compose up`.

### Tests and checks

```bash
cd backend && pytest && ruff check .      # 56 tests, all offline (stub mode)
npm run lint && npm run build             # root Vite app
```

## Architecture

Plain-language walkthrough: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Original build plan: [docs/PLAN.md](docs/PLAN.md).

## Project status

**Active work in progress (proof of concept).** The pipeline runs end to end in stub mode. Results
are kept in memory (no database). The human-review node logs a warning and continues; it
doesn't pause yet.

## Roadmap

- [ ] Choose v1 or v2 and remove the other stack
- [ ] Fix the `frontend/` (v2) lockfile and React 19 / react-konva 18 mismatch
- [ ] Real human-in-the-loop pause/resume for safety-critical domains
- [ ] Persist pipeline results (replace the in-memory store)
- [ ] Remove unused `faiss-cpu` / `sentence-transformers` from `requirements.txt`, or implement RAG validation with them

## License

MIT. See [LICENSE](LICENSE).
