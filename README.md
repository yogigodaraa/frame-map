# frame-map · ProcViz

**ProcViz** is a multi-agent AI pipeline that converts unstructured industrial
procedural documents (SOPs, work instructions, operational orders) into
interactive, spatially-grounded, time-sequenced visual storyboards — directly
addressing the document-to-visual-plan gap identified at the intersection of
document AI, spatial-temporal reasoning, and visual collaboration platforms.

---

## Architecture

```
PDF / DOCX
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│              LangGraph Supervisor Orchestrator                      │
│                                                                     │
│  Agent 1: Document Ingestion & Parsing                              │
│    AWS Textract (OCR + layout)  →  ParsedDocument                  │
│                                                                     │
│  Agent 2: Procedural Knowledge Extraction                           │
│    Claude via Bedrock  →  ProceduralKnowledgeGraph                  │
│    (steps, actors, spatial refs, temporal constraints)              │
│                                                                     │
│  Agent 3: Domain Knowledge & Validation                             │
│    RAG + rule-based  →  EnrichedKnowledgeGraph                      │
│    (ISO 45001, WHO, STANAG cross-references, issue flagging)        │
│                                                                     │
│  Agent 4: Spatial-Temporal Layout                                   │
│    Claude (high-level) + OR-Tools (constraint solver)               │
│    →  SpatialTemporalLayout (frame-by-frame coordinates)            │
│                                                                     │
│  Agent 5: Visual Specification                                      │
│    →  VisualSpecification (SpaceDraft-compatible JSON)              │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
React + Konva canvas renderer
(animated spatial plan with timeline playback)
```

### Target verticals
| Domain | Example document | Visual output |
|---|---|---|
| ⛏️ Mining | Mine shutdown SOP (BHP/Rio Tinto) | Animated site map with equipment movements & exclusion zones |
| 🏥 Healthcare | Clinical pathway / emergency drill | Hospital floor plan with patient flow & staff positioning |
| 🎖️ Defence | CONOPS / convoy order | Digital sand table briefing with phase-by-phase animation |

---

## Repository structure

```
frame-map/
├── backend/
│   ├── procviz/
│   │   ├── agents/
│   │   │   ├── ingestion.py       # Agent 1 — AWS Textract + stub fallback
│   │   │   ├── extraction.py      # Agent 2 — Claude / heuristic extraction
│   │   │   ├── validation.py      # Agent 3 — domain rules + RAG enrichment
│   │   │   ├── layout.py          # Agent 4 — OR-Tools constraint solver
│   │   │   └── visual_spec.py     # Agent 5 — SpaceDraft-compatible JSON
│   │   ├── schemas/
│   │   │   └── __init__.py        # All Pydantic data models
│   │   ├── orchestrator.py        # LangGraph supervisor graph
│   │   └── main.py                # FastAPI REST API
│   ├── tests/
│   │   ├── test_schemas.py
│   │   ├── test_agents.py
│   │   ├── test_pipeline.py
│   │   └── test_api.py
│   ├── requirements.txt
│   └── pyproject.toml
└── frontend/
    └── src/
        ├── api/procviz.ts         # REST client
        ├── components/
        │   ├── App.tsx            # Root component
        │   ├── UploadPanel.tsx    # Document upload + domain selector
        │   └── CanvasRenderer.tsx # Konva canvas + timeline animation
        └── types/index.ts         # TypeScript mirrors of Pydantic schemas
```

---

## Quick start

### Backend

```bash
cd backend
pip install -r requirements.txt

# Run in stub mode (no AWS credentials required)
PROCVIZ_STUB_MODE=true uvicorn procviz.main:app --reload

# Run with real AWS Textract + Bedrock
AWS_REGION=us-east-1 uvicorn procviz.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
REACT_APP_API_URL=http://localhost:8000 npm start
```

### Tests

```bash
cd backend
PROCVIZ_STUB_MODE=true python -m pytest tests/ -v
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `PROCVIZ_STUB_MODE` | `false` | Skip AWS calls; use deterministic stubs |
| `AWS_REGION` | `us-east-1` | AWS region for Textract + Bedrock |
| `BEDROCK_MODEL_ID` | `anthropic.claude-3-5-sonnet-20241022-v2:0` | Claude model for extraction |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `REACT_APP_API_URL` | `http://localhost:8000` | Backend base URL for frontend |

---

## Key design decisions

* **Stub mode** — every agent degrades gracefully to deterministic stubs when
  AWS credentials are absent, so the full pipeline can be exercised locally or
  in CI without cloud access.

* **Neural-symbolic spatial layout** — Agent 4 uses Claude for high-level
  spatial reasoning and Google OR-Tools for geometric constraint enforcement
  (no overlaps, minimum clearance zones), directly addressing the LLM spatial
  reasoning limitations documented in SpatialBench (2025).

* **Confidence-based routing** — the LangGraph supervisor conditionally routes
  low-confidence extractions through a human-in-the-loop checkpoint before
  proceeding to layout generation.

* **SpaceDraft-compatible output** — the `VisualSpecification` JSON schema is
  designed to feed directly into SpaceDraft's proprietary motion logic and
  spatial pathing renderer, as well as the bundled React/Konva renderer.
