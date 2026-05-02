"""FastAPI application — ProcViz REST API.

Endpoints:
  POST /api/pipeline/run       – Upload a document and run the full pipeline
  GET  /api/pipeline/{run_id}  – Poll pipeline status (stub: synchronous for now)
  GET  /api/spec/{spec_id}     – Retrieve a VisualSpecification by ID
  GET  /api/health             – Health check
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from procviz.orchestrator import run_pipeline
from procviz.schemas import DocumentDomain, PipelineState, VisualSpecification

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ProcViz API",
    description="Multi-agent document-to-visual-plan pipeline for industrial SOPs",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store (replace with DynamoDB / Redis in production)
_pipeline_results: dict[str, PipelineState] = {}
_spec_store: dict[str, VisualSpecification] = {}


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class PipelineRunResponse(BaseModel):
    run_id: str
    status: str
    errors: list[str]
    warnings: list[str]
    requires_human_review: bool
    spec_id: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version="0.1.0")


@app.post("/api/pipeline/run", response_model=PipelineRunResponse)
async def run_pipeline_endpoint(
    file: UploadFile = File(...),
    domain: DocumentDomain = Form(DocumentDomain.GENERIC),
) -> PipelineRunResponse:
    """Upload a document (PDF, DOCX, etc.) and run the ProcViz pipeline."""
    contents = await file.read()
    filename = file.filename or "document.pdf"

    logger.info("Starting pipeline for '%s' (domain=%s, size=%d bytes)", filename, domain, len(contents))

    try:
        state = run_pipeline(
            source_filename=filename,
            domain=domain,
            document_bytes=contents if contents else None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Pipeline failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    _pipeline_results[state.run_id] = state

    spec_id: Optional[str] = None
    if state.visual_spec is not None:
        spec_id = state.visual_spec.spec_id
        _spec_store[spec_id] = state.visual_spec

    return PipelineRunResponse(
        run_id=state.run_id,
        status="completed" if state.completed else "failed",
        errors=state.errors,
        warnings=state.warnings,
        requires_human_review=state.requires_human_review,
        spec_id=spec_id,
    )


@app.get("/api/pipeline/{run_id}", response_model=PipelineRunResponse)
def get_pipeline_status(run_id: str) -> PipelineRunResponse:
    """Retrieve status and result for a previous pipeline run."""
    state = _pipeline_results.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    spec_id: Optional[str] = None
    if state.visual_spec is not None:
        spec_id = state.visual_spec.spec_id

    return PipelineRunResponse(
        run_id=state.run_id,
        status="completed" if state.completed else "partial",
        errors=state.errors,
        warnings=state.warnings,
        requires_human_review=state.requires_human_review,
        spec_id=spec_id,
    )


@app.get("/api/spec/{spec_id}", response_model=VisualSpecification)
def get_visual_spec(spec_id: str) -> VisualSpecification:
    """Retrieve a VisualSpecification JSON for rendering by the React frontend."""
    spec = _spec_store.get(spec_id)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Spec '{spec_id}' not found.")
    return spec
