"""LangGraph supervisor orchestrator for the ProcViz pipeline.

Graph topology (sequential with conditional branching):

    ingestion → extraction → validation ─┬─(low confidence / errors)→ [human_review checkpoint]
                                          └─(ok)─────────────────────→ layout → visual_spec → END

State is a ``PipelineState`` Pydantic model persisted across nodes.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from langgraph.graph import END, StateGraph

from procviz.agents import ingestion, extraction, validation, layout, visual_spec
from procviz.schemas import DocumentDomain, PipelineState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node wrappers (LangGraph nodes receive and return dict-like state)
# ---------------------------------------------------------------------------

def _node_ingestion(state: dict[str, Any], document_bytes: bytes | None = None) -> dict[str, Any]:
    ps = PipelineState(**state)
    ps = ingestion.run(ps, document_bytes=document_bytes)
    return ps.model_dump()


def _node_extraction(state: dict[str, Any]) -> dict[str, Any]:
    ps = PipelineState(**state)
    ps = extraction.run(ps)
    return ps.model_dump()


def _node_validation(state: dict[str, Any]) -> dict[str, Any]:
    ps = PipelineState(**state)
    ps = validation.run(ps)
    return ps.model_dump()


def _node_layout(state: dict[str, Any]) -> dict[str, Any]:
    ps = PipelineState(**state)
    ps = layout.run(ps)
    return ps.model_dump()


def _node_visual_spec(state: dict[str, Any]) -> dict[str, Any]:
    ps = PipelineState(**state)
    ps = visual_spec.run(ps)
    return ps.model_dump()


def _node_human_review(state: dict[str, Any]) -> dict[str, Any]:
    """Human-in-the-loop checkpoint.

    In a production deployment this node would pause execution and send a
    notification (email / Slack / SpaceDraft alert) to a domain expert.
    For the PoC it logs a warning and continues.
    """
    ps = PipelineState(**state)
    logger.warning(
        "HUMAN REVIEW REQUIRED for run_id=%s — errors: %s",
        ps.run_id,
        ps.errors,
    )
    return ps.model_dump()


# ---------------------------------------------------------------------------
# Routing conditions
# ---------------------------------------------------------------------------

def _route_after_validation(state: dict[str, Any]) -> str:
    ps = PipelineState(**state)
    if ps.requires_human_review:
        return "human_review"
    return "layout"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph(document_bytes: bytes | None = None) -> Any:
    """Build and compile the LangGraph pipeline.

    Args:
        document_bytes: Raw document bytes forwarded to the ingestion node.

    Returns:
        A compiled LangGraph ``CompiledGraph`` ready to ``invoke()``.
    """
    workflow = StateGraph(dict)

    # Register nodes
    def ingestion_node(state: dict[str, Any]) -> dict[str, Any]:
        return _node_ingestion(state, document_bytes=document_bytes)

    workflow.add_node("ingestion", ingestion_node)
    workflow.add_node("extraction", _node_extraction)
    workflow.add_node("validation", _node_validation)
    workflow.add_node("human_review", _node_human_review)
    workflow.add_node("layout", _node_layout)
    workflow.add_node("visual_spec", _node_visual_spec)

    # Set entry point
    workflow.set_entry_point("ingestion")

    # Sequential edges
    workflow.add_edge("ingestion", "extraction")
    workflow.add_edge("extraction", "validation")

    # Conditional branch after validation
    workflow.add_conditional_edges(
        "validation",
        _route_after_validation,
        {
            "human_review": "human_review",
            "layout": "layout",
        },
    )

    # Human review always proceeds to layout
    workflow.add_edge("human_review", "layout")
    workflow.add_edge("layout", "visual_spec")
    workflow.add_edge("visual_spec", END)

    return workflow.compile()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_pipeline(
    source_filename: str,
    domain: DocumentDomain = DocumentDomain.GENERIC,
    document_bytes: bytes | None = None,
) -> PipelineState:
    """Execute the full ProcViz pipeline.

    Args:
        source_filename: Original filename (used for domain detection heuristics).
        domain: Explicit domain override (optional).
        document_bytes: Raw document bytes.  Pass ``None`` to use stub mode.

    Returns:
        Completed ``PipelineState`` with ``visual_spec`` populated.
    """
    run_id = str(uuid.uuid4())
    initial_state = PipelineState(
        run_id=run_id,
        source_filename=source_filename,
        domain=domain,
    ).model_dump()

    graph = build_graph(document_bytes=document_bytes)
    final_state_dict = graph.invoke(initial_state)
    final_state = PipelineState(**final_state_dict)

    if final_state.errors:
        logger.error("Pipeline completed with errors: %s", final_state.errors)
    else:
        logger.info("Pipeline completed successfully: run_id=%s", run_id)

    return final_state
