"""
Agent 2: Procedural Knowledge Extraction

Fine-tuned (RAFT-style) Claude model extracts structured procedural knowledge:
- Ordered steps with actors, equipment, spatial refs, temporal constraints
- Conditional branching
- Safety constraints
- Outputs a ProceduralKnowledgeGraph
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from anthropic import Anthropic

from backend.models.schemas import (
    Actor,
    ActorType,
    ConditionalBranch,
    ConfidenceLevel,
    DocumentDomain,
    ParsedDocument,
    ProceduralKnowledgeGraph,
    ProceduralStep,
    SpatialConstraint,
    SpatialReference,
    TemporalConstraint,
    ConstraintType,
)

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-3-7-sonnet-20250219"

# System prompt — would be replaced with fine-tuned model endpoint in production
EXTRACTION_SYSTEM_PROMPT = """You are an expert industrial procedure analyst specialising in {domain} documents.
Your task is to extract structured procedural knowledge from the document text provided.

Extract:
1. ACTORS — people, roles, equipment, vehicles involved
2. STEPS — ordered procedural steps with all attributes
3. SPATIAL_REFS — all spatial references (zone names, distances, directions, landmarks)
4. TEMPORAL_CONSTRAINTS — sequencing constraints between steps
5. SPATIAL_CONSTRAINTS — spatial constraints between references
6. BRANCHES — conditional logic (if/when branching)

Be exhaustive. Capture every spatial reference verbatim (e.g. "15 meters from blast face").
Flag low-confidence extractions.

Return ONLY valid JSON matching the schema provided. No markdown, no explanation."""

EXTRACTION_SCHEMA = {
    "actors": [{"actor_id": "str", "name": "str", "actor_type": "person|role|equipment|vehicle|system"}],
    "steps": [{
        "step_id": "str", "sequence_number": "int", "title": "str", "description": "str",
        "actors": ["actor_id"], "equipment": ["str"], "spatial_refs": ["ref_id"],
        "safety_flags": ["str"], "conditions": ["str"], "outputs": ["str"],
        "duration_minutes": "float|null", "confidence": "float"
    }],
    "spatial_references": [{"ref_id": "str", "label": "str", "raw_text": "str"}],
    "temporal_constraints": [{
        "constraint_id": "str", "constraint_type": "before|after|simultaneous|within",
        "subject_step_id": "str", "object_step_id": "str|null",
        "duration_minutes": "float|null", "raw_text": "str"
    }],
    "spatial_constraints": [{
        "constraint_id": "str", "constraint_type": "clearance|proximity|exclusion",
        "subject_ref_id": "str", "object_ref_id": "str|null",
        "distance_meters": "float|null", "raw_text": "str"
    }],
    "branches": [{
        "branch_id": "str", "condition": "str",
        "from_step_id": "str", "true_step_id": "str", "false_step_id": "str|null"
    }],
}


class ProceduralExtractionAgent:
    """
    Extracts a ProceduralKnowledgeGraph from a ParsedDocument.

    For long documents, chunks the text and merges extractions.
    Confidence-based escalation flags low-quality extractions.
    """

    def __init__(self, chunk_size: int = 6000, fine_tuned_model: str | None = None):
        self.claude = Anthropic()
        self.chunk_size = chunk_size
        self.model = fine_tuned_model or CLAUDE_MODEL

    def run(self, parsed_doc: ParsedDocument) -> ProceduralKnowledgeGraph:
        logger.info(f"[Agent2] Extracting procedures from doc {parsed_doc.doc_id}")

        chunks = self._chunk_text(parsed_doc.raw_text)
        logger.info(f"[Agent2] Processing {len(chunks)} chunk(s)")

        all_extractions: list[dict[str, Any]] = []
        for i, chunk in enumerate(chunks):
            logger.info(f"[Agent2] Extracting chunk {i+1}/{len(chunks)}")
            extraction = self._extract_chunk(chunk, parsed_doc.domain)
            all_extractions.append(extraction)

        merged = self._merge_extractions(all_extractions)
        graph = self._build_graph(merged, parsed_doc)

        logger.info(
            f"[Agent2] Extracted {len(graph.steps)} steps, "
            f"{len(graph.spatial_references)} spatial refs, "
            f"confidence={graph.extraction_confidence:.2f}"
        )
        return graph

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks for context continuity."""
        words = text.split()
        chunk_words = self.chunk_size // 5  # ~5 chars/word
        overlap = chunk_words // 4
        chunks = []
        i = 0
        while i < len(words):
            chunk = " ".join(words[i: i + chunk_words])
            chunks.append(chunk)
            i += chunk_words - overlap
        return chunks or [text]

    def _extract_chunk(self, text: str, domain: DocumentDomain) -> dict[str, Any]:
        system = EXTRACTION_SYSTEM_PROMPT.format(domain=domain.value)
        user_msg = f"""Document text:
---
{text}
---

Extract all procedural knowledge. Return JSON matching this schema:
{json.dumps(EXTRACTION_SCHEMA, indent=2)}"""

        message = self.claude.messages.create(
            model=self.model,
            max_tokens=8192,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )

        raw = message.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"[Agent2] JSON parse error: {e}")
            return {"steps": [], "actors": [], "spatial_references": [],
                    "temporal_constraints": [], "spatial_constraints": [], "branches": []}

    def _merge_extractions(self, extractions: list[dict[str, Any]]) -> dict[str, Any]:
        """Merge multi-chunk extractions, de-duplicating by ID."""
        merged: dict[str, Any] = {
            "actors": [], "steps": [], "spatial_references": [],
            "temporal_constraints": [], "spatial_constraints": [], "branches": [],
        }
        seen: dict[str, set[str]] = {k: set() for k in merged}

        for extraction in extractions:
            for key in merged:
                for item in extraction.get(key, []):
                    item_id = item.get(f"{key[:-1]}_id") or item.get("step_id") or item.get("branch_id")
                    if item_id and item_id not in seen[key]:
                        merged[key].append(item)
                        seen[key].add(item_id)
                    elif not item_id:
                        # Generate a stable ID
                        item[f"{key[:-1]}_id"] = str(uuid.uuid4())
                        merged[key].append(item)

        # Re-sequence steps
        merged["steps"].sort(key=lambda s: s.get("sequence_number", 9999))
        for i, step in enumerate(merged["steps"]):
            step["sequence_number"] = i + 1

        return merged

    def _build_graph(
        self, merged: dict[str, Any], parsed_doc: ParsedDocument
    ) -> ProceduralKnowledgeGraph:
        actors = [
            Actor(
                actor_id=a.get("actor_id", str(uuid.uuid4())),
                name=a.get("name", "Unknown"),
                actor_type=ActorType(a.get("actor_type", "person")),
            )
            for a in merged.get("actors", [])
        ]

        steps = []
        for s in merged.get("steps", []):
            try:
                steps.append(ProceduralStep(**s))
            except Exception as e:
                logger.warning(f"[Agent2] Step parse error: {e} — {s}")

        spatial_refs = [
            SpatialReference(
                ref_id=r.get("ref_id", str(uuid.uuid4())),
                label=r.get("label", ""),
                raw_text=r.get("raw_text", ""),
            )
            for r in merged.get("spatial_references", [])
        ]

        temporal = []
        for t in merged.get("temporal_constraints", []):
            try:
                temporal.append(TemporalConstraint(**t))
            except Exception as e:
                logger.warning(f"[Agent2] Temporal constraint error: {e}")

        spatial_c = []
        for sc in merged.get("spatial_constraints", []):
            try:
                spatial_c.append(SpatialConstraint(**sc))
            except Exception as e:
                logger.warning(f"[Agent2] Spatial constraint error: {e}")

        branches = []
        for b in merged.get("branches", []):
            try:
                branches.append(ConditionalBranch(**b))
            except Exception as e:
                logger.warning(f"[Agent2] Branch error: {e}")

        confidences = [s.confidence for s in steps] or [0.5]
        avg_conf = sum(confidences) / len(confidences)
        issues = []
        if avg_conf < 0.6:
            issues.append(f"Low average extraction confidence: {avg_conf:.2f}")
        if not steps:
            issues.append("No procedural steps extracted — document may be non-procedural")
        if not spatial_refs:
            issues.append("No spatial references found")

        return ProceduralKnowledgeGraph(
            doc_id=parsed_doc.doc_id,
            domain=parsed_doc.domain,
            title=parsed_doc.filename,
            actors=actors,
            steps=steps,
            temporal_constraints=temporal,
            spatial_constraints=spatial_c,
            spatial_references=spatial_refs,
            branches=branches,
            extraction_confidence=round(avg_conf, 3),
            extraction_issues=issues,
        )
