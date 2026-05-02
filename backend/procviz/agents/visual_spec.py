"""Agent 5 – Visual Specification Agent.

Converts a ``SpatialTemporalLayout`` into a ``VisualSpecification`` — the
SpaceDraft-compatible JSON payload consumed directly by the React/Konva
renderer.

Responsibilities:
* Map layout entities to typed visual elements (icons, labels, zone overlays)
* Generate animation keyframes from movement path waypoints
* Attach safety annotations and compliance notes from the enriched graph
* Produce metadata for QR-code embedding and offline access
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from procviz.schemas import (
    BoundingBox,
    Coordinate,
    DocumentDomain,
    EnrichedKnowledgeGraph,
    Keyframe,
    PipelineState,
    SpatialTemporalLayout,
    VisualElement,
    VisualSpecification,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Icon mapping by entity type + domain
# ---------------------------------------------------------------------------

_ICON_MAP: dict[str, dict[str, str]] = {
    "actor": {
        "mining": "hard_hat",
        "healthcare": "stethoscope",
        "defence": "soldier",
        "generic": "person",
    },
    "zone": {
        "mining": "explosion_zone",
        "healthcare": "quarantine_zone",
        "defence": "objective_zone",
        "generic": "zone",
    },
    "equipment": {
        "mining": "excavator",
        "healthcare": "hospital_bed",
        "defence": "vehicle",
        "generic": "gear",
    },
}

_ZONE_COLORS: dict[str, str] = {
    "mining": "rgba(245, 166, 35, 0.25)",
    "healthcare": "rgba(74, 144, 217, 0.20)",
    "defence": "rgba(126, 211, 33, 0.20)",
    "generic": "rgba(155, 155, 155, 0.20)",
}


def _icon_for(entity_type: str, domain: DocumentDomain) -> str:
    return _ICON_MAP.get(entity_type, {}).get(domain.value, "default")


def _zone_color(domain: DocumentDomain) -> str:
    return _ZONE_COLORS.get(domain.value, _ZONE_COLORS["generic"])


# ---------------------------------------------------------------------------
# Element builders
# ---------------------------------------------------------------------------

def _build_elements(
    layout: SpatialTemporalLayout,
    domain: DocumentDomain,
) -> list[VisualElement]:
    elements: list[VisualElement] = []

    for entity in layout.entities:
        if entity.entity_type == "zone":
            radius = entity.radius or 60.0
            elements.append(
                VisualElement(
                    element_id=f"zone-{entity.entity_id}",
                    element_type="zone",
                    color=entity.color or _zone_color(domain),
                    opacity=0.4,
                    coordinate=entity.coordinate,
                    bounding_box=BoundingBox(
                        x=entity.coordinate.x - radius,
                        y=entity.coordinate.y - radius,
                        width=radius * 2,
                        height=radius * 2,
                    ),
                    z_index=0,
                )
            )
        elif entity.entity_type == "actor":
            elements.append(
                VisualElement(
                    element_id=f"icon-{entity.entity_id}",
                    element_type="icon",
                    icon_name=_icon_for("actor", domain),
                    color=entity.color or "#4A90D9",
                    opacity=1.0,
                    coordinate=entity.coordinate,
                    bounding_box=BoundingBox(
                        x=entity.coordinate.x - 20,
                        y=entity.coordinate.y - 20,
                        width=40,
                        height=40,
                    ),
                    z_index=10,
                )
            )

        # Label for every entity
        elements.append(
            VisualElement(
                element_id=f"label-{entity.entity_id}",
                element_type="label",
                text=entity.label,
                color="#FFFFFF",
                opacity=0.9,
                coordinate=Coordinate(
                    x=entity.coordinate.x,
                    y=entity.coordinate.y + 30,
                ),
                z_index=20,
            )
        )

    # Path polylines
    for path in layout.paths:
        if path.waypoints:
            elements.append(
                VisualElement(
                    element_id=f"path-{path.path_id}",
                    element_type="path",
                    color="#4A90D9",
                    opacity=0.6,
                    coordinate=path.waypoints[0].coordinate,
                    z_index=5,
                )
            )

    return elements


def _build_keyframes(layout: SpatialTemporalLayout) -> list[Keyframe]:
    """Convert movement path waypoints to animation keyframes."""
    keyframes: list[Keyframe] = []
    for path in layout.paths:
        for waypoint in path.waypoints:
            keyframes.append(
                Keyframe(
                    element_id=f"icon-{path.actor_id}",
                    timestamp_seconds=waypoint.timestamp_seconds,
                    coordinate=waypoint.coordinate,
                )
            )
    return keyframes


def _build_safety_annotations(
    enriched: Optional[EnrichedKnowledgeGraph],
) -> list[str]:
    if enriched is None:
        return []
    return [
        f"[{issue.severity.upper()}] {issue.message}"
        for issue in enriched.issues
    ]


def _build_compliance_notes(
    enriched: Optional[EnrichedKnowledgeGraph],
) -> list[str]:
    if enriched is None:
        return []
    notes = list(enriched.regulatory_refs)
    notes.extend(enriched.enrichment_notes)
    return notes


def _generate_title(layout: SpatialTemporalLayout, domain: DocumentDomain) -> str:
    domain_label = domain.value.capitalize()
    return f"{domain_label} Procedure — Visual Plan"


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

def run(state: PipelineState) -> PipelineState:
    """Generate the visual specification from the spatial layout.

    Args:
        state: Must have ``spatial_layout`` populated by Agent 4.

    Returns:
        Updated state with ``visual_spec`` populated and ``completed=True``.
    """
    state.current_agent = "visual_spec"
    layout = state.spatial_layout
    if layout is None:
        state.errors.append("Visual spec agent: spatial_layout is missing.")
        return state

    domain = state.domain
    enriched = state.enriched_graph

    elements = _build_elements(layout, domain)
    keyframes = _build_keyframes(layout)
    safety_annotations = _build_safety_annotations(enriched)
    compliance_notes = _build_compliance_notes(enriched)

    spec_id = str(uuid.uuid4())
    state.visual_spec = VisualSpecification(
        spec_id=spec_id,
        layout_id=layout.layout_id,
        title=_generate_title(layout, domain),
        description=(
            f"Auto-generated visual plan for '{state.source_filename}' "
            f"({domain.value} domain). "
            f"{len(state.knowledge_graph.steps if state.knowledge_graph else [])} steps, "
            f"{len(layout.frames)} animation frames."
        ),
        domain=domain,
        canvas_width=layout.canvas_width,
        canvas_height=layout.canvas_height,
        background_image_url=layout.background_image_url,
        elements=elements,
        keyframes=keyframes,
        total_duration_seconds=layout.total_duration_seconds,
        safety_annotations=safety_annotations,
        compliance_notes=compliance_notes,
        metadata={
            "run_id": state.run_id,
            "source_filename": state.source_filename,
            "solver": layout.solver_used,
            "requires_human_review": state.requires_human_review,
        },
    )

    state.completed = True
    logger.info(
        "Visual spec complete: spec_id=%s, %d elements, %d keyframes",
        spec_id,
        len(elements),
        len(keyframes),
    )
    return state
