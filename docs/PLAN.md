# ProcViz — Build Plan

## What We're Building

A 5-agent AI pipeline that takes industrial procedural documents (PDFs) and produces
interactive spatial-temporal visual plans — animated storyboards showing who does what,
where, and when. Target domains: mining, healthcare, defence.

---

## Architecture

```
PDF Upload
    ↓
[Agent 1] Document Ingestion       AWS Textract + Claude + Docling fallback
    ↓
[Agent 2] Procedural Extraction    Claude (fine-tuned) → ProceduralKnowledgeGraph
    ↓
    ├─ Low confidence → Human Review checkpoint
    ↓
[Agent 3] Domain Validation        RAG (FAISS + regulations) → ValidationResult
    ↓
    ├─ Critical issues → Human Review checkpoint
    ↓
[Agent 4] Spatial-Temporal Layout  Claude (semantic) + OR-Tools (geometric) → Frames
    ↓
[Agent 5] Visual Specification     → SpaceDraft-compatible JSON
    ↓
React/Konva Canvas + Timeline UI
```

Orchestrated by **LangGraph** with persistent state, conditional branching, and
human-in-the-loop checkpoints.

---

## Milestones

### Phase 1 — PoC (Weeks 1–4)
**Goal:** End-to-end pipeline working on a single mining SOP, no fine-tuning.

- [ ] Set up AWS Textract integration (Agent 1)
- [ ] Zero-shot Claude extraction with schema validation (Agent 2)
- [ ] Static domain regulation checks (Agent 3)
- [ ] Claude-only layout (no solver) (Agent 4)
- [ ] Basic React canvas with hardcoded test data (frontend)
- [ ] FastAPI with single-job endpoint
- [ ] Docker Compose working locally

**Success criteria:** Given a 5-10 page mining SOP PDF, produce a visual plan with
correct step sequencing and at least 3 spatial zones identified.

---

### Phase 2 — Integration (Weeks 5–8)
**Goal:** Full pipeline wired end-to-end with real documents.

- [ ] OR-Tools constraint solver integrated (Agent 4)
- [ ] FAISS vector store with domain regulations (Agent 3)
- [ ] Multi-chunk extraction with merging (Agent 2)
- [ ] Human review API + frontend UI
- [ ] Confidence-based routing in LangGraph
- [ ] Job polling + status in frontend
- [ ] Canvas renders real pipeline output (not hardcoded)
- [ ] Timeline with playback

**Success criteria:** Upload a real 20-page BHP procedure → interactive visual plan
in <3 minutes. Human review triggers correctly on low-confidence documents.

---

### Phase 3 — Domain Specialisation (Weeks 9–12)
**Goal:** Strong performance on all 3 target domains.

- [ ] Collect domain-specific training examples (10–20 per domain)
- [ ] Fine-tune Agent 2 via RAFT on mining/healthcare/defence SOPs
- [ ] Healthcare and defence domain regulation sets (Agent 3)
- [ ] Spatial templates for: open-cut mine, hospital ward, military convoy
- [ ] Background image support (upload site map/floor plan as backdrop)
- [ ] Narration voiceover (TTS integration)
- [ ] Multi-document fusion (SOP + site plan + equipment manual)

**Success criteria:** >70% extraction accuracy on held-out domain test set.

---

### Phase 4 — Research & Publication (Weeks 13–16)
**Goal:** Prepare academic contribution.

- [ ] Create domain SOP benchmark dataset (30+ documents, 3 domains)
- [ ] Evaluation framework (extraction recall/precision, spatial constraint satisfaction)
- [ ] Baseline comparisons (zero-shot GPT-4o, Qwen2-VL)
- [ ] Ablation study (with/without solver, with/without fine-tuning)
- [ ] Write-up targeting IEEE Transactions on Industrial Informatics or AAAI

---

## Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph 0.2+ |
| LLM | Anthropic Claude 3.7 (via Bedrock) |
| OCR / Layout | AWS Textract |
| Doc fallback | IBM Docling |
| Spatial solver | Google OR-Tools CP-SAT |
| Vector store | FAISS + sentence-transformers |
| API | FastAPI + Uvicorn |
| Frontend canvas | React-Konva |
| Process flow | React Flow |
| Styling | Tailwind CSS |
| Deploy | Docker Compose → AWS ECS |

---

## Key Risks

| Risk | Mitigation |
|---|---|
| Training data scarcity for fine-tuning | Start with zero-shot; synthetic data generation as bridge |
| OR-Tools solver timeout on complex layouts | 5s hard timeout; fallback to Claude-only positions |
| Textract accuracy on complex industrial diagrams | Docling fallback; flag for human review |
| SpaceDraft JSON format unknown | Build generic spec first; adapt Agent 5 output format once format confirmed |
| LLM spatial reasoning failures | Neural-symbolic split — LLM for semantics, solver for geometry |

---

## Immediate Next Steps

1. `cp .env.example .env` and fill in AWS + Anthropic keys
2. `docker-compose up` — verify API health at localhost:8000/api/health
3. Install frontend: `cd frontend && npm install && npm run dev`
4. Test Agent 1 with a sample PDF using the `/api/jobs` endpoint
5. Evaluate zero-shot extraction quality on 3 real SOPs
6. Decide: use Amazon Bedrock or direct Anthropic API
