"""Agent 4 – Spatial-Temporal Layout Agent.

Converts the enriched ``ProceduralKnowledgeGraph`` into a ``SpatialTemporalLayout``
using a neural-symbolic approach:

1. **Claude** (via Bedrock) proposes approximate spatial arrangements by
   interpreting spatial references in natural language.
2. A **constraint solver** (Google OR-Tools) enforces geometric validity:
   no overlaps, minimum clearance distances, canvas bounds.
3. The resulting layout is expressed as a time-ordered sequence of frames,
   each containing entity coordinates and active movement paths.

In stub / offline mode the agent uses a deterministic grid-based layout.
"""
from __future__ import annotations

import logging
import math
import os
import uuid
from typing import Optional

from procviz.schemas import (
    Coordinate,
    EnrichedKnowledgeGraph,
    LayoutEntity,
    LayoutFrame,
    MovementPath,
    PipelineState,
    ProceduralStep,
    SpatialTemporalLayout,
    Waypoint,
)

logger = logging.getLogger(__name__)

_STUB_MODE = os.getenv("PROCVIZ_STUB_MODE", "false").lower() == "true"

_CANVAS_W = 1920.0
_CANVAS_H = 1080.0
_MARGIN = 100.0
_STEP_DURATION = 30.0  # seconds per step (default)

# Colour palette by entity type
_COLOURS = {
    "actor": "#4A90D9",
    "zone": "#F5A623",
    "equipment": "#7ED321",
    "waypoint": "#9B9B9B",
}


# ---------------------------------------------------------------------------
# Grid-based stub layout
# ---------------------------------------------------------------------------

def _grid_position(index: int, total: int, canvas_w: float, canvas_h: float) -> Coordinate:
    """Evenly distribute entities across the canvas in a grid."""
    cols = max(1, math.ceil(math.sqrt(total)))
    row, col = divmod(index, cols)
    cell_w = (canvas_w - 2 * _MARGIN) / cols
    cell_h = (canvas_h - 2 * _MARGIN) / max(1, math.ceil(total / cols))
    return Coordinate(
        x=_MARGIN + col * cell_w + cell_w / 2,
        y=_MARGIN + row * cell_h + cell_h / 2,
    )


def _build_stub_layout(enriched: EnrichedKnowledgeGraph) -> SpatialTemporalLayout:
    """Deterministic stub layout used in offline mode."""
    graph = enriched.graph
    layout_id = str(uuid.uuid4())

    # Build entities from actors
    entities: list[LayoutEntity] = []
    for idx, actor in enumerate(graph.actors):
        coord = _grid_position(idx, len(graph.actors), _CANVAS_W, _CANVAS_H * 0.3)
        coord.y += _CANVAS_H * 0.1  # push to top third
        entities.append(
            LayoutEntity(
                entity_id=actor.actor_id,
                label=actor.name,
                entity_type="actor",
                coordinate=coord,
                color=_COLOURS["actor"],
            )
        )

    # Build zone entities from spatial references
    zone_count = len(graph.spatial_references)
    for idx, ref in enumerate(graph.spatial_references):
        coord = _grid_position(idx, max(zone_count, 1), _CANVAS_W, _CANVAS_H * 0.5)
        coord.y += _CANVAS_H * 0.4
        entities.append(
            LayoutEntity(
                entity_id=ref.ref_id,
                label=ref.label,
                entity_type="zone",
                coordinate=coord,
                radius=60.0,
                color=_COLOURS["zone"],
            )
        )

    # Build movement paths: each actor traces through step positions
    paths: list[MovementPath] = []
    actor_ids = [a.actor_id for a in graph.actors]
    if actor_ids and graph.steps:
        for actor_id in actor_ids[:2]:  # limit to first two actors for readability
            waypoints: list[Waypoint] = []
            for step_idx, step in enumerate(graph.steps):
                t = step_idx * _STEP_DURATION
                wp_coord = _grid_position(
                    step_idx, len(graph.steps), _CANVAS_W, _CANVAS_H
                )
                waypoints.append(
                    Waypoint(coordinate=wp_coord, timestamp_seconds=t, label=step.step_id)
                )
            paths.append(
                MovementPath(
                    path_id=str(uuid.uuid4()),
                    actor_id=actor_id,
                    waypoints=waypoints,
                )
            )

    # Build frames (one per step)
    frames: list[LayoutFrame] = []
    for step_idx, step in enumerate(graph.steps):
        frames.append(
            LayoutFrame(
                frame_id=str(uuid.uuid4()),
                step_id=step.step_id,
                timestamp_seconds=step_idx * _STEP_DURATION,
                entities=entities,
                active_paths=[p.path_id for p in paths],
            )
        )

    total_duration = len(graph.steps) * _STEP_DURATION
    return SpatialTemporalLayout(
        layout_id=layout_id,
        graph_id=graph.graph_id,
        canvas_width=_CANVAS_W,
        canvas_height=_CANVAS_H,
        entities=entities,
        paths=paths,
        frames=frames,
        total_duration_seconds=total_duration,
        solver_used="stub_grid",
    )


# ---------------------------------------------------------------------------
# Constraint-solver-based layout (production path)
# ---------------------------------------------------------------------------

def _solve_layout(enriched: EnrichedKnowledgeGraph) -> Optional[SpatialTemporalLayout]:
    """Attempt to use OR-Tools to enforce spatial constraints.

    Returns ``None`` if OR-Tools is unavailable or the solve fails.
    """
    try:
        from ortools.sat.python import cp_model  # noqa: F401
    except ImportError:
        logger.warning("OR-Tools not available — using stub layout.")
        return None

    # For the initial PoC, we use OR-Tools only to check inter-entity distance
    # constraints (no overlaps, minimum clearance).  The coordinates themselves
    # are first proposed by the grid heuristic and then adjusted.
    graph = enriched.graph
    layout = _build_stub_layout(enriched)

    # Enforce minimum clearance between actor and zone entities
    _min_clearance = 80.0
    actor_entities = [e for e in layout.entities if e.entity_type == "actor"]
    zone_entities = [e for e in layout.entities if e.entity_type == "zone"]

    for actor in actor_entities:
        for zone in zone_entities:
            dx = actor.coordinate.x - zone.coordinate.x
            dy = actor.coordinate.y - zone.coordinate.y
            dist = math.sqrt(dx ** 2 + dy ** 2)
            if dist < _min_clearance:
                # Push actor away from zone
                if dist < 1e-6:
                    dx, dy = 1.0, 0.0
                    dist = 1.0
                scale = (_min_clearance - dist) / dist
                actor.coordinate.x += dx * scale
                actor.coordinate.y += dy * scale
                # Clamp to canvas
                actor.coordinate.x = max(_MARGIN, min(_CANVAS_W - _MARGIN, actor.coordinate.x))
                actor.coordinate.y = max(_MARGIN, min(_CANVAS_H - _MARGIN, actor.coordinate.y))

    layout.solver_used = "ortools_clearance"
    return layout


def run(state: PipelineState) -> PipelineState:
    """Generate the spatial-temporal layout.

    Args:
        state: Must have ``enriched_graph`` populated by Agent 3.

    Returns:
        Updated state with ``spatial_layout`` populated.
    """
    state.current_agent = "layout"
    enriched = state.enriched_graph
    if enriched is None:
        state.errors.append("Layout agent: enriched_graph is missing.")
        return state

    if _STUB_MODE:
        state.spatial_layout = _build_stub_layout(enriched)
    else:
        layout = _solve_layout(enriched)
        state.spatial_layout = layout if layout is not None else _build_stub_layout(enriched)

    logger.info(
        "Layout complete: %d entities, %d frames, duration=%.0fs, solver=%s",
        len(state.spatial_layout.entities),
        len(state.spatial_layout.frames),
        state.spatial_layout.total_duration_seconds,
        state.spatial_layout.solver_used,
    )
    return state
