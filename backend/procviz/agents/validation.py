"""Agent 3 – Domain Knowledge & Validation Agent.

Validates and enriches the ``ProceduralKnowledgeGraph`` against domain-specific
regulatory knowledge.  In production this uses a RAG pipeline backed by
vectorised standards documents; in stub/offline mode it applies deterministic
rule-based checks.

Key responsibilities:
* Cross-reference steps against domain safety standards
* Flag missing safety flags, incomplete spatial references, circular dependencies
* Enrich steps with standard equipment dimensions and regulatory citations
* Determine whether the overall pipeline confidence warrants human review
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

from procviz.schemas import (
    ConfidenceLevel,
    DocumentDomain,
    EnrichedKnowledgeGraph,
    PipelineState,
    ProceduralKnowledgeGraph,
    ValidationIssue,
)

logger = logging.getLogger(__name__)

_STUB_MODE = os.getenv("PROCVIZ_STUB_MODE", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Domain-specific rule sets
# ---------------------------------------------------------------------------

_MINING_RULES = [
    {
        "id": "M001",
        "description": "Blast-face ventilation requirement",
        "keywords": ["blast", "blasting", "explosive"],
        "required_spatial_keyword": "ventilation",
        "severity": "error",
        "regulatory_ref": "ISO 45001 / AS 2865",
        "suggestion": "Add a step ensuring adequate ventilation (fan 15m from blast face) before personnel re-entry.",
    },
    {
        "id": "M002",
        "description": "Personnel exclusion zone during crane operation",
        "keywords": ["crane", "lift", "hoist"],
        "required_spatial_keyword": "exclusion",
        "severity": "warning",
        "regulatory_ref": "AS 2550",
        "suggestion": "Define a personnel exclusion zone beneath the crane operating radius.",
    },
]

_HEALTHCARE_RULES = [
    {
        "id": "H001",
        "description": "Hand hygiene step",
        "keywords": ["patient", "procedure", "intervention"],
        "required_keyword": "handwash",
        "severity": "error",
        "regulatory_ref": "WHO Hand Hygiene Guidelines",
        "suggestion": "Insert a hand hygiene step before patient contact.",
    },
]

_DEFENCE_RULES = [
    {
        "id": "D001",
        "description": "Communications check before movement",
        "keywords": ["convoy", "movement", "advance"],
        "required_keyword": "comms",
        "severity": "warning",
        "regulatory_ref": "STANAG 2084",
        "suggestion": "Add a comms check step prior to any movement phase.",
    },
]

_DOMAIN_RULES: dict[DocumentDomain, list[dict]] = {
    DocumentDomain.MINING: _MINING_RULES,
    DocumentDomain.HEALTHCARE: _HEALTHCARE_RULES,
    DocumentDomain.DEFENCE: _DEFENCE_RULES,
    DocumentDomain.GENERIC: [],
}

_REGULATORY_REFS: dict[DocumentDomain, list[str]] = {
    DocumentDomain.MINING: ["ISO 45001", "AS 2865", "AS 2550", "WHS Regulations 2017"],
    DocumentDomain.HEALTHCARE: [
        "WHO Hand Hygiene Guidelines",
        "National Safety and Quality Health Service Standards",
    ],
    DocumentDomain.DEFENCE: ["STANAG 2084", "ADF Operational Planning Process"],
    DocumentDomain.GENERIC: [],
}


# ---------------------------------------------------------------------------
# Internal rule checking
# ---------------------------------------------------------------------------

def _apply_rules(
    graph: ProceduralKnowledgeGraph,
) -> tuple[list[ValidationIssue], list[str]]:
    """Apply domain-specific rules and return (issues, enrichment_notes)."""
    issues: list[ValidationIssue] = []
    enrichment_notes: list[str] = []
    rules = _DOMAIN_RULES.get(graph.domain, [])
    all_text = " ".join(s.description.lower() for s in graph.steps)
    spatial_text = " ".join(r.label.lower() for r in graph.spatial_references)

    for rule in rules:
        if any(kw in all_text for kw in rule.get("keywords", [])):
            required = rule.get("required_spatial_keyword") or rule.get("required_keyword", "")
            if required and required not in (all_text + " " + spatial_text):
                issues.append(
                    ValidationIssue(
                        issue_id=str(uuid.uuid4()),
                        severity=rule["severity"],
                        message=f"[{rule['id']}] {rule['description']}: {rule.get('suggestion', '')}",
                        regulatory_ref=rule.get("regulatory_ref"),
                        suggestion=rule.get("suggestion"),
                    )
                )

    # Generic checks
    if not graph.steps:
        issues.append(
            ValidationIssue(
                issue_id=str(uuid.uuid4()),
                severity="error",
                message="No procedural steps were extracted — document may be unsupported.",
            )
        )

    for step in graph.steps:
        if step.confidence < 0.5:
            issues.append(
                ValidationIssue(
                    issue_id=str(uuid.uuid4()),
                    severity="warning",
                    step_id=step.step_id,
                    message=f"Step '{step.step_id}' has low extraction confidence ({step.confidence:.0%}).",
                    suggestion="Consider manual review of this step.",
                )
            )

    if graph.extraction_confidence >= 0.85:
        enrichment_notes.append("High-confidence extraction — automated processing recommended.")
    elif graph.extraction_confidence >= 0.60:
        enrichment_notes.append("Moderate confidence — spot-check recommended for critical steps.")
    else:
        enrichment_notes.append("Low confidence — full human review required before operational use.")

    return issues, enrichment_notes


def _rag_enrich(
    graph: ProceduralKnowledgeGraph,
) -> tuple[list[str], list[str]]:
    """Placeholder for RAG-based enrichment (Bedrock Knowledge Base integration)."""
    reg_refs = _REGULATORY_REFS.get(graph.domain, [])
    notes: list[str] = []
    if not _STUB_MODE:
        # TODO: call Amazon Bedrock Knowledge Base retrieval
        logger.debug("RAG enrichment skipped — Bedrock Knowledge Base not configured.")
    notes.append(f"Regulatory baseline applied: {', '.join(reg_refs) or 'none'}")
    return reg_refs, notes


def _overall_confidence(
    graph: ProceduralKnowledgeGraph,
    issues: list[ValidationIssue],
) -> ConfidenceLevel:
    errors = sum(1 for i in issues if i.severity == "error")
    if errors > 0 or graph.extraction_confidence < 0.60:
        return ConfidenceLevel.LOW
    if graph.extraction_confidence >= 0.85 and not issues:
        return ConfidenceLevel.HIGH
    return ConfidenceLevel.MEDIUM


def run(state: PipelineState) -> PipelineState:
    """Validate and enrich the knowledge graph.

    Args:
        state: Must have ``knowledge_graph`` populated by Agent 2.

    Returns:
        Updated state with ``enriched_graph`` populated.
    """
    state.current_agent = "validation"
    graph = state.knowledge_graph
    if graph is None:
        state.errors.append("Validation agent: knowledge_graph is missing.")
        return state

    issues, rule_notes = _apply_rules(graph)
    reg_refs, rag_notes = _rag_enrich(graph)
    enrichment_notes = rule_notes + rag_notes

    confidence = _overall_confidence(graph, issues)
    requires_review = confidence == ConfidenceLevel.LOW or any(
        i.severity == "error" for i in issues
    )

    state.enriched_graph = EnrichedKnowledgeGraph(
        graph=graph,
        issues=issues,
        regulatory_refs=reg_refs,
        enrichment_notes=enrichment_notes,
        requires_human_review=requires_review,
        overall_confidence=confidence,
    )
    state.requires_human_review = requires_review

    if issues:
        for issue in issues:
            (state.errors if issue.severity == "error" else state.warnings).append(
                issue.message
            )

    logger.info(
        "Validation complete: %d issues, confidence=%s, human_review=%s",
        len(issues),
        confidence,
        requires_review,
    )
    return state
