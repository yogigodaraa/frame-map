# frame-map (ProcViz)

**Document → Interactive Spatial-Temporal Visual Plan**

Upload an industrial SOP, work instruction, or operational order (PDF). Get back an animated storyboard showing who does what, where, and when.

## What it does

A 5-agent LangGraph pipeline that turns unstructured procedural text into a timeline of actors, actions, locations, and dependencies, rendered as an interactive canvas. Built for mining, healthcare, and defence procedural documents.

Pipeline stages: document ingestion → procedural extraction → domain validation → spatial-temporal layout → visual specification. Includes human-in-the-loop review checkpoints for safety-critical domains and confidence-based routing with Claude fallbacks when solvers time out.

## Tech stack

**Frontend** (repo root)
- Vite + React 18 + TypeScript
- Konva / react-konva for canvas rendering
- React Dropzone, Tailwind CSS

**Backend** (`backend/`)
- FastAPI (Python) + LangGraph
- Claude API for semantic reasoning
- AWS Textract for PDF parsing
- OR-Tools for spatial constraint solving
- FAISS for vector-based document validation

## Getting started

**Frontend**

```bash
npm install
npm run dev            # http://localhost:3000
```

**Backend**

```bash
cd backend
cp .env.example .env   # set API keys
docker-compose up      # http://localhost:8000
```

## API

- `POST /api/jobs` — submit a document
- `GET /api/jobs/{id}` — poll job status
- `GET /api/jobs/{id}/spec` — fetch visual spec

## Deploy

- **Frontend → Vercel** — connect repo; Vite auto-detected at root. Set `VITE_API_URL`; update `rewrites` in `vercel.json`.
- **Backend → Railway / AWS ECS** — Dockerfile + compose file included.

## Status

Active WIP. Phase 1–4 milestones documented in `docs/PLAN.md` (proof-of-concept through production specialization). Output compatible with SpaceDraft's rendering engine.
