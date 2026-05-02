"""Agent 2 – Procedural Knowledge Extraction Agent.

Converts a ``ParsedDocument`` into a ``ProceduralKnowledgeGraph`` by:

1. Concatenating block content into a full-document string.
2. Calling Claude (via Amazon Bedrock) with a structured extraction prompt
   that returns JSON matching our schema.
3. Parsing and validating the response with Pydantic.
4. Falling back to regex-based heuristics when Bedrock is unavailable
   (stub / offline mode).
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from typing import Any

from procviz.schemas import (
    Actor,
    ConfidenceLevel,
    DocumentDomain,
    ParsedDocument,
    PipelineState,
    ProceduralKnowledgeGraph,
    ProceduralStep,
    SpatialReference,
    TemporalConstraint,
    TemporalRelation,
)

logger = logging.getLogger(__name__)

_STUB_MODE = os.getenv("PROCVIZ_STUB_MODE", "false").lower() == "true"

_EXTRACTION_PROMPT = """\
You are an expert at extracting structured procedural knowledge from industrial documents.

Given the following document text, extract:
1. Ordered procedural steps (with actors, equipment, spatial references, duration, safety flags)
2. Actors/roles mentioned
3. Spatial references (zones, distances, directions)
4. Temporal constraints between steps (before/after/simultaneously)

Return ONLY valid JSON matching this exact schema:
{
  "steps": [
    {
      "step_id": "s1",
      "sequence_number": 1,
      "description": "...",
      "actors": ["actor_id"],
      "equipment": ["item"],
      "spatial_refs": ["ref_id"],
      "duration_seconds": null,
      "is_conditional": false,
      "condition_expression": null,
      "safety_flags": [],
      "confidence": 0.9
    }
  ],
  "actors": [
    {"actor_id": "a1", "name": "...", "role": "...", "equipment": []}
  ],
  "spatial_references": [
    {
      "ref_id": "r1",
      "label": "Zone B",
      "raw_text": "...",
      "zone_type": "zone",
      "distance_meters": null,
      "relative_to": null,
      "bearing": null
    }
  ],
  "temporal_constraints": [
    {
      "constraint_id": "tc1",
      "step_from": "s1",
      "step_to": "s2",
      "relation": "before",
      "raw_text": "..."
    }
  ],
  "extraction_confidence": 0.85
}

Document text:
---
{document_text}
---
"""

_SPATIAL_PATTERNS = [
    r"\b(\d+(?:\.\d+)?)\s*m(?:eter|etre)?s?\s+(?:from|of)\b",
    r"\b(?:zone|area|section|bay|room|ward)\s+[A-Z0-9\-]+\b",
    r"\b(?:north|south|east|west|downwind|upwind|upstream|downstream)\b",
    r"\b(?:entrance|exit|access point|doorway|corridor)\b",
]

_TEMPORAL_PATTERNS = [
    (r"\b(?:before|prior to)\b", TemporalRelation.BEFORE),
    (r"\b(?:after|following|once)\b", TemporalRelation.AFTER),
    (r"\b(?:simultaneously|at the same time|concurrently)\b", TemporalRelation.SIMULTANEOUSLY),
    (r"\b(?:during|while|as)\b", TemporalRelation.DURING),
]

_STEP_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:step\s*)?(\d+)[.\):\-]\s*(.+?)(?=\n\s*(?:step\s*)?\d+[.\):\-]|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def _heuristic_extract(document_text: str, document_id: str, domain: DocumentDomain) -> dict[str, Any]:
    """Regex/heuristic fallback extraction when Bedrock is unavailable."""
    steps: list[dict[str, Any]] = []
    spatial_refs: list[dict[str, Any]] = []
    temporal_constraints: list[dict[str, Any]] = []
    actors: list[dict[str, Any]] = [
        {"actor_id": "a1", "name": "Operator", "role": "Primary Operator", "equipment": []},
        {"actor_id": "a2", "name": "Supervisor", "role": "Supervisor", "equipment": []},
    ]

    step_matches = _STEP_PATTERN.findall(document_text)
    if not step_matches:
        sentences = [s.strip() for s in document_text.split(".") if len(s.strip()) > 20]
        step_matches = [(str(i + 1), s) for i, s in enumerate(sentences[:10])]

    for idx, (num, desc) in enumerate(step_matches):
        step_id = f"s{idx + 1}"
        flags: list[str] = []
        if any(kw in desc.lower() for kw in ("hazard", "danger", "caution", "warning", "safety")):
            flags.append("safety_critical")

        spatial_step_refs: list[str] = []
        for pattern in _SPATIAL_PATTERNS:
            for match in re.finditer(pattern, desc, re.IGNORECASE):
                ref_id = f"r{len(spatial_refs) + 1}"
                spatial_refs.append({
                    "ref_id": ref_id,
                    "label": match.group(0).strip(),
                    "raw_text": match.group(0),
                    "zone_type": "zone" if "zone" in match.group(0).lower() else "point",
                })
                spatial_step_refs.append(ref_id)

        steps.append({
            "step_id": step_id,
            "sequence_number": int(num),
            "description": desc.strip()[:500],
            "actors": ["a1"],
            "equipment": [],
            "spatial_refs": spatial_step_refs,
            "duration_seconds": None,
            "is_conditional": "if" in desc.lower() or "when" in desc.lower(),
            "condition_expression": None,
            "safety_flags": flags,
            "confidence": 0.65,
        })

        if idx > 0:
            for pattern, relation in _TEMPORAL_PATTERNS:
                if re.search(pattern, desc, re.IGNORECASE):
                    temporal_constraints.append({
                        "constraint_id": f"tc{len(temporal_constraints) + 1}",
                        "step_from": f"s{idx}",
                        "step_to": step_id,
                        "relation": relation.value,
                        "raw_text": desc[:100],
                    })
                    break

    return {
        "steps": steps,
        "actors": actors,
        "spatial_references": spatial_refs,
        "temporal_constraints": temporal_constraints,
        "extraction_confidence": 0.65,
    }


def _call_bedrock(document_text: str) -> dict[str, Any] | None:
    """Call Claude via Amazon Bedrock and return parsed JSON, or None on failure."""
    try:
        import boto3

        client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
        prompt = _EXTRACTION_PROMPT.format(document_text=document_text[:15000])
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        })
        response = client.invoke_model(
            modelId=os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        raw = json.loads(response["body"].read())
        text = raw["content"][0]["text"]
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        return json.loads(text[json_start:json_end])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Bedrock extraction failed: %s", exc)
        return None


def _build_graph(
    data: dict[str, Any],
    document_id: str,
    domain: DocumentDomain,
) -> ProceduralKnowledgeGraph:
    graph_id = str(uuid.uuid4())
    steps = [ProceduralStep(**s) for s in data.get("steps", [])]
    actors = [Actor(**a) for a in data.get("actors", [])]
    spatial_refs = [SpatialReference(**r) for r in data.get("spatial_references", [])]
    temporal_constraints = [
        TemporalConstraint(**tc) for tc in data.get("temporal_constraints", [])
    ]
    return ProceduralKnowledgeGraph(
        graph_id=graph_id,
        document_id=document_id,
        domain=domain,
        steps=steps,
        actors=actors,
        spatial_references=spatial_refs,
        temporal_constraints=temporal_constraints,
        extraction_confidence=data.get("extraction_confidence", 0.65),
    )


def run(state: PipelineState) -> PipelineState:
    """Extract procedural knowledge from the parsed document.

    Args:
        state: Must have ``parsed_document`` populated by Agent 1.

    Returns:
        Updated state with ``knowledge_graph`` populated.
    """
    state.current_agent = "extraction"
    doc = state.parsed_document
    if doc is None:
        state.errors.append("Extraction agent: parsed_document is missing.")
        return state

    document_text = "\n".join(b.content for b in doc.blocks)

    data: dict[str, Any] | None = None
    if not _STUB_MODE:
        data = _call_bedrock(document_text)

    if data is None:
        logger.info("Using heuristic extraction for document '%s'", doc.source_filename)
        data = _heuristic_extract(document_text, doc.document_id, doc.domain)

    try:
        state.knowledge_graph = _build_graph(data, doc.document_id, doc.domain)
        logger.info(
            "Extraction complete: %d steps, %d spatial refs",
            len(state.knowledge_graph.steps),
            len(state.knowledge_graph.spatial_references),
        )
    except Exception as exc:  # noqa: BLE001
        state.errors.append(f"Extraction schema validation failed: {exc}")

    return state
