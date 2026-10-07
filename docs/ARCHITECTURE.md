# Architecture

How ProcViz turns a PDF procedure into an animated storyboard. This guide follows the **v2
`backend/procviz/`** code, which has tests. v1 (`backend/agents/` + `backend/orchestrator/`)
follows the same five stages with different plumbing. See the README's comparison table.

## The big picture

```text
POST /api/pipeline/run  (procviz/main.py)
        │  PDF bytes, domain
        ▼
run_pipeline()  (procviz/orchestrator.py), a LangGraph StateGraph over one PipelineState
        │
        ├─ ingestion    ParsedDocument          Textract → Docling fallback → stub
        ├─ extraction   ProceduralKnowledgeGraph Claude (Bedrock) JSON → Pydantic; regex fallback
        ├─ validation   enriched graph + flags   rule checks; sets requires_human_review
        │      └─ (requires_human_review?) ──▶ human_review (logs a warning for now)
        ├─ layout       SpatialTemporalLayout    grid heuristic + clearance pass (PoC)
        └─ visual_spec  VisualSpecification      elements + animation keyframes
        ▼
in-memory stores (_pipeline_results, _spec_store) → GET /api/pipeline/{id}, GET /api/spec/{id}
```

## Key ideas

### 1. One state object flows through every node

`PipelineState` (in `procviz/schemas/`) holds everything: the parsed document, the knowledge
graph, the layout, the spec, `errors` and `requires_human_review`. Each node is a function
`PipelineState → PipelineState`. The wrappers in `orchestrator.py` convert to and from the plain
dicts LangGraph passes around (`model_dump()` / `PipelineState(**state)`).

**Concept: typed state.** Pydantic validates the state at every hop, so a bug in one agent
fails loudly at the boundary instead of producing a corrupted storyboard three steps later.

### 2. LangGraph = a small state machine

`build_graph()` registers the nodes, sets the entry point, and adds edges. The only branch is
`add_conditional_edges("validation", _route_after_validation, …)`: if validation decided a human
should check the result, the graph detours through `human_review`. Today that node logs and
continues. A real version would *interrupt* the graph and resume once someone approves.

### 3. Neural-symbolic layout (the target design)

LLMs are good at reading "the operator stands 5 m from the conveyor" but bad at geometry. The
design is: **Claude proposes** rough positions, then **OR-Tools (CP-SAT)** enforces hard rules
(stay on the canvas, no overlaps, minimum clearance). "LLM proposes, solver disposes" is a pattern
worth remembering.

- **v1** (`backend/agents/spatial_temporal_layout.py`) implements it: a Claude call, then a CP-SAT model with integer x/y variables per zone.
- **v2** (`backend/procviz/agents/layout.py`) is still a proof of concept: it checks that OR-Tools is installed, places entities on a grid, then nudges actors away from zones to keep a minimum clearance.

### 4. Stub mode everywhere

Every cloud call (Textract, Bedrock) has an offline fallback: deterministic placeholders or regex
heuristics. That's why `pytest` passes with no credentials, and why the demo still renders
without AWS.

## Modules

| Path | Role |
|---|---|
| `procviz/main.py` | FastAPI app: run a pipeline, poll a run, fetch a spec. In-memory stores. |
| `procviz/orchestrator.py` | Graph construction (`build_graph`) and `run_pipeline()` |
| `procviz/agents/ingestion.py` | Agent 1: PDF → `ParsedDocument` (Textract / Docling / stub) |
| `procviz/agents/extraction.py` | Agent 2: text → `ProceduralKnowledgeGraph` (Bedrock Claude / regex fallback) |
| `procviz/agents/validation.py` | Agent 3: domain checks, enrichment, human-review decision |
| `procviz/agents/layout.py` | Agent 4: positions + time-ordered frames (grid heuristic + clearance pass; see v1 for the solver version) |
| `procviz/agents/visual_spec.py` | Agent 5: renderer-ready JSON with keyframes and safety annotations |
| `procviz/schemas/` | All Pydantic models, the contract between agents |
| `tests/` | `test_schemas`, `test_agents`, `test_pipeline`, `test_api`: all offline |

## Configuration

| Variable | Used by | Effect |
|---|---|---|
| `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | ingestion, extraction (v2) | Enables Textract + Bedrock. Absent → stub mode. |
| `BEDROCK_MODEL_ID` | extraction (v2) | Claude model on Bedrock |
| `ANTHROPIC_API_KEY` | v1 agents | Direct Anthropic API |
| `USE_SOLVER`, `GENERATE_NARRATION` | v1 | Feature toggles |
| `VITE_API_URL` | root frontend | Backend base URL |

## Where to start reading

1. `backend/tests/test_pipeline.py`: the whole pipeline in a few assertions.
2. `backend/procviz/orchestrator.py`: about 100 lines, the clearest LangGraph example in the repo.
3. `backend/agents/spatial_temporal_layout.py` (v1): the neural-symbolic layout in practice.
