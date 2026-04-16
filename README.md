# frame-map / ProcViz

> **Document → Interactive Spatial-Temporal Visual Plan**

Upload an industrial SOP, work instruction, or operational order (PDF).
Get back an animated storyboard showing who does what, where, and when —
compatible with SpaceDraft's rendering engine.

---

## Quick Start

```bash
# Frontend (Vercel / local)
npm install
npm run dev          # http://localhost:3000

# Backend (Docker / Railway)
cp .env.example .env
docker-compose up    # http://localhost:8000
```

## Deploy

*Frontend → Vercel*
- Connect repo, Vercel auto-detects Vite at root
- Set `VITE_API_URL` env var to your backend URL
- Update the `rewrites` destination in `vercel.json`

*Backend → Railway / AWS ECS*
- `docker build -f backend/Dockerfile -t procviz-api ./backend`
- Set env vars from `.env.example`

## Architecture

5-agent LangGraph pipeline:

```
Agent 1: Document Ingestion    → ParsedDocument
Agent 2: Procedural Extraction → ProceduralKnowledgeGraph
Agent 3: Domain Validation     → ValidationResult
Agent 4: Spatial-Temporal      → SpatialTemporalLayout (neural-symbolic)
Agent 5: Visual Specification  → VisualSpecification (SpaceDraft JSON)
```

See [`docs/PLAN.md`](docs/PLAN.md) for the full build plan and milestones.

## Target Domains

- ⛏️ Mining (Rio Tinto, BHP, Alcoa procedures)
- 🏥 Healthcare (clinical pathways, emergency protocols)
- 🛡️ Defence (CONOPS, operational orders, convoy plans)

## Stack

Python · LangGraph · Claude API · AWS Textract · OR-Tools · FastAPI · React · Konva · Tailwind
