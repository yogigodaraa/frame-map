"""
Agent 3: Domain Knowledge & Validation

RAG-augmented agent that:
1. Retrieves relevant regulations/standards from domain knowledge base
2. Cross-references extracted procedures against requirements
3. Flags inconsistencies, verifies completeness
4. Enriches the graph with equipment dimensions, spatial templates, etc.

Uses a FAISS vector store for domain knowledge retrieval.
"""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from anthropic import Anthropic

from backend.models.schemas import (
    DocumentDomain,
    ProceduralKnowledgeGraph,
    ValidationIssue,
    ValidationResult,
)

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-3-7-sonnet-20250219"

# Domain regulation summaries — in production these live in a vector store
DOMAIN_REGULATIONS: dict[DocumentDomain, list[str]] = {
    DocumentDomain.MINING: [
        "ISO 45001: All hazardous tasks require identification of control measures",
        "WHS Reg 2017 s.54: Exclusion zones must be established around blast areas",
        "Mine Safety Act: Ventilation requirements — minimum 0.5 m/s airflow in working areas",
        "WHS Reg 2017 s.70: All personnel must be accounted for before blasting",
        "ICMM Guidance: Emergency evacuation routes must be marked and unobstructed",
    ],
    DocumentDomain.HEALTHCARE: [
        "NSQHS Standard 3: Hand hygiene must occur at 5 moments of care",
        "AS/NZS 4187: Reprocessing of reusable medical devices requires 3-stage process",
        "NSQHS Standard 6: Medication administration requires two-person verification for high-risk",
        "Infection Control Guidelines: PPE donning sequence: gown → mask → goggles → gloves",
        "Emergency Procedures: Code Blue response team must assemble within 3 minutes",
    ],
    DocumentDomain.DEFENCE: [
        "STANAG 2014: Operations orders must include Situation, Mission, Execution, Service Support, Command",
        "Joint Pub 3-0: All manoeuvre elements require comms check before execution",
        "STANAG 2934: Convoy spacing minimum 100m between vehicles in hostile areas",
        "LAND 400 Requirements: Personnel must not enter cleared zone until EOD confirms safe",
        "ADF OP Safety: ROE must be briefed to all personnel before operation",
    ],
    DocumentDomain.GENERIC: [
        "ISO 9001: Procedures must include acceptance criteria for each step",
        "General Safety: PPE requirements must be specified for each hazardous step",
    ],
}

# Spatial templates for common facility types
SPATIAL_TEMPLATES: dict[str, dict[str, Any]] = {
    "open_cut_mine": {
        "zones": ["blast_zone", "exclusion_zone", "muster_point", "haul_road", "processing_plant"],
        "typical_exclusion_radius_meters": 500,
    },
    "hospital_ward": {
        "zones": ["patient_bay", "nurses_station", "medication_room", "clean_utility", "dirty_utility"],
        "typical_room_width_meters": 4.2,
    },
    "military_convoy": {
        "zones": ["start_point", "release_point", "rally_point", "danger_area", "objective"],
        "typical_vehicle_spacing_meters": 100,
    },
}

VALIDATION_SYSTEM_PROMPT = """You are a {domain} safety and compliance expert.
Review the extracted procedural knowledge against the provided regulations.
Identify:
1. Missing safety requirements
2. Incomplete steps (missing actors, equipment, spatial refs)
3. Regulatory non-compliance
4. Logical inconsistencies in sequencing
5. Missing exception handling

Return JSON with this structure:
{{
  "issues": [
    {{
      "issue_id": "str",
      "severity": "critical|warning|info",
      "step_id": "str|null",
      "regulation_ref": "str|null",
      "description": "str",
      "recommendation": "str|null"
    }}
  ],
  "compliance_score": 0.0,
  "enrichments": {{}}
}}"""


class DomainValidationAgent:
    """
    Validates and enriches a ProceduralKnowledgeGraph against domain regulations.
    """

    def __init__(self, knowledge_base_path: str | None = None):
        self.claude = Anthropic()
        self.kb_path = Path(knowledge_base_path) if knowledge_base_path else None
        self._vector_store = None  # lazy-loaded

    def run(self, graph: ProceduralKnowledgeGraph) -> ValidationResult:
        logger.info(f"[Agent3] Validating graph for doc {graph.doc_id} (domain: {graph.domain})")

        regulations = self._retrieve_regulations(graph)
        issues, compliance_score, enrichments = self._validate_with_claude(graph, regulations)

        # Always add structural checks
        structural_issues = self._structural_checks(graph)
        issues.extend(structural_issues)

        # Recalculate score after structural
        if structural_issues:
            critical_count = sum(1 for i in structural_issues if i.severity == "critical")
            compliance_score = max(0.0, compliance_score - (critical_count * 0.1))

        enriched_graph = self._enrich_graph(graph, enrichments)
        is_valid = compliance_score >= 0.7 and not any(
            i.severity == "critical" for i in issues
        )

        logger.info(
            f"[Agent3] Validation complete — score={compliance_score:.2f}, "
            f"issues={len(issues)}, valid={is_valid}"
        )

        return ValidationResult(
            doc_id=graph.doc_id,
            is_valid=is_valid,
            issues=issues,
            enrichments=enrichments,
            compliance_score=round(compliance_score, 3),
            validated_graph=enriched_graph,
        )

    # ------------------------------------------------------------------

    def _retrieve_regulations(self, graph: ProceduralKnowledgeGraph) -> list[str]:
        """Retrieve relevant regulations. Falls back to static domain list."""
        # In production: embed step descriptions → query FAISS → return top-k chunks
        regs = DOMAIN_REGULATIONS.get(graph.domain, DOMAIN_REGULATIONS[DocumentDomain.GENERIC])

        # Add generic regulations too
        if graph.domain != DocumentDomain.GENERIC:
            regs = regs + DOMAIN_REGULATIONS[DocumentDomain.GENERIC]

        return regs

    def _validate_with_claude(
        self,
        graph: ProceduralKnowledgeGraph,
        regulations: list[str],
    ) -> tuple[list[ValidationIssue], float, dict[str, Any]]:
        steps_summary = json.dumps(
            [{"step_id": s.step_id, "title": s.title, "description": s.description,
              "actors": s.actors, "safety_flags": s.safety_flags}
             for s in graph.steps[:30]],  # limit for context
            indent=2,
        )
        regs_text = "\n".join(f"- {r}" for r in regulations)

        message = self.claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=VALIDATION_SYSTEM_PROMPT.format(domain=graph.domain.value),
            messages=[{
                "role": "user",
                "content": f"""Regulations:
{regs_text}

Extracted procedures ({len(graph.steps)} steps):
{steps_summary}

Spatial references found: {[r.label for r in graph.spatial_references]}
Actors: {[a.name for a in graph.actors]}

Review for compliance and completeness. Return JSON only.""",
            }],
        )

        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("[Agent3] Claude validation JSON parse error")
            result = {"issues": [], "compliance_score": 0.5, "enrichments": {}}

        issues = []
        for item in result.get("issues", []):
            try:
                issues.append(ValidationIssue(
                    issue_id=item.get("issue_id", str(uuid.uuid4())),
                    severity=item.get("severity", "warning"),
                    step_id=item.get("step_id"),
                    regulation_ref=item.get("regulation_ref"),
                    description=item.get("description", ""),
                    recommendation=item.get("recommendation"),
                ))
            except Exception as e:
                logger.warning(f"[Agent3] Issue parse error: {e}")

        compliance_score = float(result.get("compliance_score", 0.5))
        enrichments = result.get("enrichments", {})
        return issues, compliance_score, enrichments

    def _structural_checks(self, graph: ProceduralKnowledgeGraph) -> list[ValidationIssue]:
        """Rule-based structural checks that don't require LLM."""
        issues = []

        if not graph.steps:
            issues.append(ValidationIssue(
                issue_id=str(uuid.uuid4()),
                severity="critical",
                description="No procedural steps extracted from document",
                recommendation="Verify document is a procedural/SOP document",
            ))

        if not graph.actors:
            issues.append(ValidationIssue(
                issue_id=str(uuid.uuid4()),
                severity="warning",
                description="No actors/roles identified",
                recommendation="Document may lack explicit role assignments",
            ))

        # Check for steps missing actors
        for step in graph.steps:
            if not step.actors and not step.safety_flags:
                issues.append(ValidationIssue(
                    issue_id=str(uuid.uuid4()),
                    severity="info",
                    step_id=step.step_id,
                    description=f"Step '{step.title}' has no assigned actor",
                    recommendation="Assign responsibility to a role or person",
                ))

        # Check for orphaned spatial refs
        step_ref_ids = {ref for step in graph.steps for ref in step.spatial_refs}
        defined_ref_ids = {ref.ref_id for ref in graph.spatial_references}
        orphaned = step_ref_ids - defined_ref_ids
        if orphaned:
            issues.append(ValidationIssue(
                issue_id=str(uuid.uuid4()),
                severity="warning",
                description=f"Steps reference undefined spatial refs: {orphaned}",
                recommendation="Verify spatial reference labels are consistent",
            ))

        return issues

    def _enrich_graph(
        self, graph: ProceduralKnowledgeGraph, enrichments: dict[str, Any]
    ) -> ProceduralKnowledgeGraph:
        """Add domain-derived enrichments to the graph (spatial templates, equipment dims, etc.)."""
        # Apply spatial templates if facility type detected
        facility = enrichments.get("facility_type")
        if facility and facility in SPATIAL_TEMPLATES:
            template = SPATIAL_TEMPLATES[facility]
            logger.info(f"[Agent3] Applying spatial template for: {facility}")
            # In full implementation: pre-populate zone coordinates from template
            _ = template  # used in layout agent

        return graph  # graph is enriched in-place via enrichments dict passed to layout agent
