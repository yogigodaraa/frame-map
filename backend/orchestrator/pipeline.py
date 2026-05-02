"""
ProcViz Pipeline Orchestrator

LangGraph-based supervisor that manages the 5-agent pipeline:
  ingestion → extraction → validation → layout → visual_spec

Features:
- Conditional branching (low confidence → human review)
- Human-in-the-loop checkpoints for safety-critical domains
- State persistence across long-running jobs
- Confidence-based escalation
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from backend.agents import (
    DocumentIngestionAgent,
    ProceduralExtractionAgent,
    DomainValidationAgent,
    SpatialTemporalLayoutAgent,
    VisualSpecificationAgent,
)
from backend.models.schemas import (
    ConfidenceLevel,
    DocumentDomain,
    PipelineState,
)

logger = logging.getLogger(__name__)

# Confidence thresholds
HUMAN_REVIEW_THRESHOLD = 0.60
ABORT_THRESHOLD = 0.30


class ProcVizPipeline:
    """
    Orchestrates the 5-agent ProcViz pipeline via LangGraph.

    Usage:
        pipeline = ProcVizPipeline(config)
        result = pipeline.run(pdf_bytes, filename, domain)
    """

    def __init__(
        self,
        s3_bucket: str,
        aws_region: str = "ap-southeast-2",
        use_solver: bool = True,
        generate_narration: bool = True,
        human_review_callback: Any | None = None,
    ):
        self.ingestion_agent = DocumentIngestionAgent(s3_bucket, aws_region)
        self.extraction_agent = ProceduralExtractionAgent()
        self.validation_agent = DomainValidationAgent()
        self.layout_agent = SpatialTemporalLayoutAgent(use_solver=use_solver)
        self.visual_agent = VisualSpecificationAgent(generate_narration=generate_narration)
        self.human_review_callback = human_review_callback

        self.graph = self._build_graph()
        self.checkpointer = MemorySaver()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        pdf_bytes: bytes,
        filename: str,
        domain: DocumentDomain = DocumentDomain.GENERIC,
        job_id: str | None = None,
    ) -> PipelineState:
        job_id = job_id or str(uuid.uuid4())
        logger.info(f"[Pipeline] Starting job {job_id} — {filename} ({domain})")

        initial_state = PipelineState(
            job_id=job_id,
            filename=filename,
            domain=domain,
        )

        config = {"configurable": {"thread_id": job_id}}
        final_state = self.graph.invoke(
            initial_state.model_dump(),
            config=config,
        )

        return PipelineState(**final_state)

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(dict)

        # Register nodes
        workflow.add_node("ingestion", self._node_ingestion)
        workflow.add_node("extraction", self._node_extraction)
        workflow.add_node("validation", self._node_validation)
        workflow.add_node("human_review", self._node_human_review)
        workflow.add_node("layout", self._node_layout)
        workflow.add_node("visual_spec", self._node_visual_spec)
        workflow.add_node("error_handler", self._node_error_handler)

        # Entry point
        workflow.set_entry_point("ingestion")

        # Edges
        workflow.add_edge("ingestion", "extraction")
        workflow.add_conditional_edges(
            "extraction",
            self._route_after_extraction,
            {
                "validate": "validation",
                "human_review": "human_review",
                "error": "error_handler",
            },
        )
        workflow.add_conditional_edges(
            "validation",
            self._route_after_validation,
            {
                "layout": "layout",
                "human_review": "human_review",
                "error": "error_handler",
            },
        )
        workflow.add_edge("human_review", "layout")
        workflow.add_edge("layout", "visual_spec")
        workflow.add_edge("visual_spec", END)
        workflow.add_edge("error_handler", END)

        return workflow.compile()

    # ------------------------------------------------------------------
    # Node implementations
    # ------------------------------------------------------------------

    def _node_ingestion(self, state: dict) -> dict:
        s = PipelineState(**state)
        logger.info(f"[Pipeline:{s.job_id}] Node: ingestion")
        s.current_step = "ingestion"
        try:
            # pdf_bytes must be injected before run() — stored in state for graph
            pdf_bytes = state.get("_pdf_bytes", b"")
            parsed = self.ingestion_agent.run(pdf_bytes, s.filename, s.domain)
            s.parsed_doc = parsed
            logger.info(f"[Pipeline:{s.job_id}] Ingestion complete — confidence={parsed.parse_confidence:.2f}")
        except Exception as e:
            logger.error(f"[Pipeline:{s.job_id}] Ingestion failed: {e}")
            s.errors.append(f"Ingestion error: {e}")
        return s.model_dump()

    def _node_extraction(self, state: dict) -> dict:
        s = PipelineState(**state)
        logger.info(f"[Pipeline:{s.job_id}] Node: extraction")
        s.current_step = "extraction"
        if not s.parsed_doc:
            s.errors.append("No parsed document — extraction skipped")
            return s.model_dump()
        try:
            graph = self.extraction_agent.run(s.parsed_doc)
            s.knowledge_graph = graph
            logger.info(
                f"[Pipeline:{s.job_id}] Extraction complete — "
                f"{len(graph.steps)} steps, confidence={graph.extraction_confidence:.2f}"
            )
        except Exception as e:
            logger.error(f"[Pipeline:{s.job_id}] Extraction failed: {e}")
            s.errors.append(f"Extraction error: {e}")
        return s.model_dump()

    def _node_validation(self, state: dict) -> dict:
        s = PipelineState(**state)
        logger.info(f"[Pipeline:{s.job_id}] Node: validation")
        s.current_step = "validation"
        if not s.knowledge_graph:
            s.errors.append("No knowledge graph — validation skipped")
            return s.model_dump()
        try:
            result = self.validation_agent.run(s.knowledge_graph)
            s.validation_result = result
            logger.info(
                f"[Pipeline:{s.job_id}] Validation complete — "
                f"score={result.compliance_score:.2f}, "
                f"issues={len(result.issues)}"
            )
        except Exception as e:
            logger.error(f"[Pipeline:{s.job_id}] Validation failed: {e}")
            s.errors.append(f"Validation error: {e}")
        return s.model_dump()

    def _node_human_review(self, state: dict) -> dict:
        s = PipelineState(**state)
        logger.info(f"[Pipeline:{s.job_id}] Node: human_review — awaiting review")
        s.current_step = "human_review"
        s.human_review_required = True

        if self.human_review_callback:
            try:
                updated_state = self.human_review_callback(s)
                if updated_state:
                    s = updated_state
                    s.human_review_required = False
            except Exception as e:
                logger.warning(f"[Pipeline:{s.job_id}] Human review callback error: {e}")

        return s.model_dump()

    def _node_layout(self, state: dict) -> dict:
        s = PipelineState(**state)
        logger.info(f"[Pipeline:{s.job_id}] Node: layout")
        s.current_step = "layout"
        if not s.validation_result:
            s.errors.append("No validation result — layout skipped")
            return s.model_dump()
        try:
            layout = self.layout_agent.run(s.validation_result)
            s.spatial_layout = layout
            logger.info(
                f"[Pipeline:{s.job_id}] Layout complete — "
                f"{len(layout.zones)} zones, {len(layout.frames)} frames"
            )
        except Exception as e:
            logger.error(f"[Pipeline:{s.job_id}] Layout failed: {e}")
            s.errors.append(f"Layout error: {e}")
        return s.model_dump()

    def _node_visual_spec(self, state: dict) -> dict:
        s = PipelineState(**state)
        logger.info(f"[Pipeline:{s.job_id}] Node: visual_spec")
        s.current_step = "visual_spec"
        if not s.spatial_layout or not s.validation_result:
            s.errors.append("Missing layout or validation — visual spec skipped")
            return s.model_dump()
        try:
            spec = self.visual_agent.run(s.spatial_layout, s.validation_result)
            s.visual_spec = spec
            logger.info(
                f"[Pipeline:{s.job_id}] Visual spec complete — "
                f"confidence={spec.confidence_level}"
            )
        except Exception as e:
            logger.error(f"[Pipeline:{s.job_id}] Visual spec failed: {e}")
            s.errors.append(f"Visual spec error: {e}")
        return s.model_dump()

    def _node_error_handler(self, state: dict) -> dict:
        s = PipelineState(**state)
        logger.error(f"[Pipeline:{s.job_id}] Error handler — errors: {s.errors}")
        s.current_step = "failed"
        return s.model_dump()

    # ------------------------------------------------------------------
    # Routing functions
    # ------------------------------------------------------------------

    def _route_after_extraction(self, state: dict) -> str:
        s = PipelineState(**state)
        if s.errors:
            return "error"
        if not s.knowledge_graph:
            return "error"
        conf = s.knowledge_graph.extraction_confidence
        if conf < ABORT_THRESHOLD:
            s.errors.append(f"Extraction confidence too low: {conf:.2f}")
            return "error"
        if conf < HUMAN_REVIEW_THRESHOLD:
            logger.info(f"[Pipeline] Low extraction confidence ({conf:.2f}) → human review")
            return "human_review"
        return "validate"

    def _route_after_validation(self, state: dict) -> str:
        s = PipelineState(**state)
        if s.errors:
            return "error"
        if not s.validation_result:
            return "error"
        has_critical = any(
            i.severity == "critical" for i in s.validation_result.issues
        )
        if has_critical:
            logger.info("[Pipeline] Critical validation issues → human review")
            return "human_review"
        return "layout"
