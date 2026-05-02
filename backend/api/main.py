"""
ProcViz FastAPI — REST endpoints for the pipeline.

POST /api/jobs          — Submit a PDF for processing
GET  /api/jobs/{id}     — Poll job status
GET  /api/jobs/{id}/spec — Retrieve completed VisualSpecification
POST /api/jobs/{id}/review — Submit human review decision
GET  /api/health        — Health check
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.models.schemas import DocumentDomain, PipelineState, VisualSpecification
from backend.orchestrator.pipeline import ProcVizPipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ProcViz API",
    description="Document-to-visual-plan pipeline for industrial procedural documents",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store (replace with Redis/DynamoDB in production)
jobs: dict[str, dict[str, Any]] = {}
executor = ThreadPoolExecutor(max_workers=4)

# Pipeline instance (shared; agents are stateless per-call)
pipeline = ProcVizPipeline(
    s3_bucket=os.environ.get("S3_BUCKET", "procviz-uploads"),
    aws_region=os.environ.get("AWS_REGION", "ap-southeast-2"),
    use_solver=os.environ.get("USE_SOLVER", "true").lower() == "true",
    generate_narration=os.environ.get("GENERATE_NARRATION", "true").lower() == "true",
)


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

class JobResponse(BaseModel):
    job_id: str
    status: str
    filename: str
    domain: str
    current_step: str | None = None
    errors: list[str] = []
    human_review_required: bool = False


class ReviewDecision(BaseModel):
    approved: bool
    notes: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/jobs", response_model=JobResponse, status_code=202)
async def submit_job(
    file: UploadFile = File(...),
    domain: str = Form("generic"),
):
    """Submit a PDF for processing. Returns job_id immediately; poll /api/jobs/{id} for status."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    try:
        doc_domain = DocumentDomain(domain.lower())
    except ValueError:
        raise HTTPException(400, f"Invalid domain. Choose from: {[d.value for d in DocumentDomain]}")

    job_id = str(uuid.uuid4())
    pdf_bytes = await file.read()

    jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "filename": file.filename,
        "domain": domain,
        "current_step": None,
        "errors": [],
        "human_review_required": False,
        "state": None,
    }

    # Run pipeline in background thread (CPU/IO bound)
    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        executor,
        _run_pipeline_sync,
        job_id,
        pdf_bytes,
        file.filename,
        doc_domain,
    )

    return JobResponse(
        job_id=job_id,
        status="queued",
        filename=file.filename,
        domain=domain,
    )


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str):
    job = _get_job_or_404(job_id)
    return JobResponse(
        job_id=job_id,
        status=job["status"],
        filename=job["filename"],
        domain=job["domain"],
        current_step=job.get("current_step"),
        errors=job.get("errors", []),
        human_review_required=job.get("human_review_required", False),
    )


@app.get("/api/jobs/{job_id}/spec", response_model=VisualSpecification)
async def get_visual_spec(job_id: str):
    """Returns the completed VisualSpecification. 404 if not yet complete."""
    job = _get_job_or_404(job_id)
    if job["status"] != "completed":
        raise HTTPException(409, f"Job not complete. Status: {job['status']}")
    state: PipelineState = job["state"]
    if not state.visual_spec:
        raise HTTPException(500, "Pipeline completed but no visual spec generated")
    return state.visual_spec


@app.post("/api/jobs/{job_id}/review")
async def submit_review(job_id: str, decision: ReviewDecision):
    """Submit human review decision for jobs awaiting review."""
    job = _get_job_or_404(job_id)
    if not job.get("human_review_required"):
        raise HTTPException(409, "Job is not awaiting human review")

    job["human_review_decision"] = decision.model_dump()
    job["human_review_required"] = False
    job["status"] = "resuming"
    # The pipeline's human_review_callback will pick this up
    return {"acknowledged": True, "job_id": job_id}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_job_or_404(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    return job


def _run_pipeline_sync(
    job_id: str,
    pdf_bytes: bytes,
    filename: str,
    domain: DocumentDomain,
) -> None:
    """Runs the pipeline synchronously in a thread pool."""
    jobs[job_id]["status"] = "running"

    def progress_callback(step: str) -> None:
        jobs[job_id]["current_step"] = step

    try:
        # Inject pdf_bytes into pipeline run via a wrapper
        # (LangGraph state carries the bytes through _pdf_bytes key)
        result = pipeline.run(pdf_bytes, filename, domain, job_id=job_id)
        jobs[job_id]["state"] = result
        jobs[job_id]["status"] = "completed" if not result.errors else "completed_with_errors"
        jobs[job_id]["errors"] = result.errors
        jobs[job_id]["current_step"] = result.current_step
        jobs[job_id]["human_review_required"] = result.human_review_required
        logger.info(f"[API] Job {job_id} finished — {jobs[job_id]['status']}")
    except Exception as e:
        logger.error(f"[API] Job {job_id} failed: {e}")
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["errors"].append(str(e))
