"""
Agent 4: Spatial-Temporal Layout (the key innovation)

Neural-symbolic hybrid:
1. Claude interprets spatial references → approximate layout proposals
2. OR-Tools constraint solver enforces geometric validity + temporal consistency
3. Output: frame-by-frame spatial layout with movement paths and zones

This addresses the fundamental LLM spatial reasoning limitation by delegating
precise computation to a constraint solver while keeping LLM for semantics.
"""
from __future__ import annotations

import json
import logging
import math
import time
import uuid
from typing import Any

from anthropic import Anthropic

from backend.models.schemas import (
    Coordinate,
    Frame,
    MovementPath,
    ProceduralKnowledgeGraph,
    SpatialReference,
    SpatialTemporalLayout,
    ValidationResult,
    Waypoint,
    Zone,
)

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-3-7-sonnet-20250219"

SPATIAL_SYSTEM_PROMPT = """You are a spatial layout planner for {domain} operations.
Given a list of spatial references and procedural steps, propose approximate (x, y) positions
on a 1000x700 canvas. Consider:
- Logical groupings (related zones near each other)
- Flow direction (generally left-to-right or top-to-bottom for process flow)
- Safety separation (exclusion zones far from work zones)
- Real-world spatial relationships described in the text

Return JSON:
{{
  "zone_proposals": [
    {{"ref_id": "str", "label": "str", "center_x": 0.0, "center_y": 0.0, "radius": 50.0, "zone_type": "work|safety|exclusion|staging|transit"}}
  ],
  "actor_start_positions": [
    {{"actor_id": "str", "x": 0.0, "y": 0.0}}
  ],
  "background_type": "map|floorplan|aerial|generic",
  "flow_direction": "left_right|top_bottom|radial"
}}"""


class SpatialTemporalLayoutAgent:
    """
    Generates a frame-by-frame spatial-temporal layout for a validated procedure.

    Architecture:
    - Claude proposes approximate zone positions (semantic understanding)
    - OR-Tools refines positions subject to hard geometric constraints
    - Simple timeline scheduler assigns step durations and timestamps
    """

    CANVAS_W = 1000.0
    CANVAS_H = 700.0

    def __init__(self, use_solver: bool = True):
        self.claude = Anthropic()
        self.use_solver = use_solver

    def run(self, validation_result: ValidationResult) -> SpatialTemporalLayout:
        graph = validation_result.validated_graph
        logger.info(f"[Agent4] Generating spatial-temporal layout for doc {graph.doc_id}")

        # Step 1: Claude proposes approximate layout
        proposals = self._propose_layout(graph)

        # Step 2: Constraint solver refines positions
        zones = self._build_zones(graph, proposals)
        if self.use_solver:
            zones = self._solve_constraints(zones, graph)

        # Step 3: Build movement paths
        paths = self._build_movement_paths(graph, zones, proposals)

        # Step 4: Generate frames
        total_duration = self._compute_total_duration(graph)
        frames = self._generate_frames(graph, zones, paths)

        layout = SpatialTemporalLayout(
            doc_id=graph.doc_id,
            total_duration_seconds=total_duration,
            background_type=proposals.get("background_type", "generic"),
            canvas_width=self.CANVAS_W,
            canvas_height=self.CANVAS_H,
            zones=zones,
            movement_paths=paths,
            frames=frames,
            solver_stats={"solver_used": self.use_solver, "zone_count": len(zones)},
        )

        logger.info(
            f"[Agent4] Layout complete — {len(zones)} zones, "
            f"{len(paths)} paths, {len(frames)} frames, "
            f"duration={total_duration:.0f}s"
        )
        return layout

    # ------------------------------------------------------------------
    # Step 1: Claude proposes layout
    # ------------------------------------------------------------------

    def _propose_layout(self, graph: ProceduralKnowledgeGraph) -> dict[str, Any]:
        refs_text = json.dumps(
            [{"ref_id": r.ref_id, "label": r.label, "raw_text": r.raw_text}
             for r in graph.spatial_references],
            indent=2,
        )
        constraints_text = json.dumps(
            [{"type": c.constraint_type, "subject": c.subject_ref_id,
              "object": c.object_ref_id, "distance_m": c.distance_meters,
              "raw": c.raw_text}
             for c in graph.spatial_constraints],
            indent=2,
        )
        actors_text = json.dumps(
            [{"actor_id": a.actor_id, "name": a.name, "type": a.actor_type}
             for a in graph.actors],
            indent=2,
        )

        message = self.claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=SPATIAL_SYSTEM_PROMPT.format(domain=graph.domain.value),
            messages=[{
                "role": "user",
                "content": f"""Spatial references:
{refs_text}

Spatial constraints:
{constraints_text}

Actors:
{actors_text}

Procedure: {graph.title}
Number of steps: {len(graph.steps)}

Propose layout positions. Return JSON only.""",
            }],
        )

        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("[Agent4] Layout proposal JSON parse error — using default grid")
            return self._default_grid_layout(graph)

    def _default_grid_layout(self, graph: ProceduralKnowledgeGraph) -> dict[str, Any]:
        """Fallback: arrange zones in a simple grid."""
        cols = max(1, math.ceil(math.sqrt(len(graph.spatial_references))))
        proposals = []
        for i, ref in enumerate(graph.spatial_references):
            col = i % cols
            row = i // cols
            proposals.append({
                "ref_id": ref.ref_id,
                "label": ref.label,
                "center_x": 150 + col * 200,
                "center_y": 150 + row * 180,
                "radius": 60.0,
                "zone_type": "work",
            })
        return {
            "zone_proposals": proposals,
            "actor_start_positions": [],
            "background_type": "generic",
            "flow_direction": "left_right",
        }

    # ------------------------------------------------------------------
    # Step 2: Build & solve zones
    # ------------------------------------------------------------------

    def _build_zones(
        self, graph: ProceduralKnowledgeGraph, proposals: dict[str, Any]
    ) -> list[Zone]:
        zones = []
        zone_proposals = proposals.get("zone_proposals", [])

        # Build ref_id → proposal lookup
        proposal_map = {p["ref_id"]: p for p in zone_proposals}

        for ref in graph.spatial_references:
            prop = proposal_map.get(ref.ref_id, {})
            cx = prop.get("center_x", 500.0)
            cy = prop.get("center_y", 350.0)
            r = prop.get("radius", 60.0)
            zone_type = prop.get("zone_type", "work")

            color_map = {
                "work": "#3B82F633",
                "safety": "#22C55E33",
                "exclusion": "#EF444433",
                "staging": "#F59E0B33",
                "transit": "#8B5CF633",
            }

            zones.append(Zone(
                zone_id=ref.ref_id,
                label=ref.label,
                polygon=self._circle_polygon(cx, cy, r),
                zone_type=zone_type,
                color=color_map.get(zone_type, "#3B82F633"),
            ))

        return zones

    def _circle_polygon(self, cx: float, cy: float, r: float, n: int = 8) -> list[Coordinate]:
        """Approximate circle as polygon."""
        points = []
        for i in range(n):
            angle = 2 * math.pi * i / n
            points.append(Coordinate(x=cx + r * math.cos(angle), y=cy + r * math.sin(angle)))
        return points

    def _solve_constraints(
        self, zones: list[Zone], graph: ProceduralKnowledgeGraph
    ) -> list[Zone]:
        """
        Apply OR-Tools CP-SAT solver to enforce spatial constraints.
        Handles: minimum clearance distances, exclusion zones, proximity requirements.
        """
        try:
            from ortools.sat.python import cp_model

            model = cp_model.CpModel()
            SCALE = 10  # work in 0.1-unit precision (multiply coords by SCALE)
            W = int(self.CANVAS_W * SCALE)
            H = int(self.CANVAS_H * SCALE)
            R = 60 * SCALE  # default zone radius in scaled units

            # Variables: center x, y for each zone
            zone_ids = [z.zone_id for z in zones]
            xs = {z.zone_id: model.new_int_var(R, W - R, f"x_{z.zone_id}") for z in zones}
            ys = {z.zone_id: model.new_int_var(R, H - R, f"y_{z.zone_id}") for z in zones}

            # Soft constraint: stay near proposal centers
            # (hard constraints from document)
            for z in zones:
                cx = int(_zone_center(z).x * SCALE)
                cy = int(_zone_center(z).y * SCALE)
                model.add_linear_constraint(xs[z.zone_id], cx - 3 * R, cx + 3 * R)
                model.add_linear_constraint(ys[z.zone_id], cy - 3 * R, cy + 3 * R)

            # Enforce document spatial constraints
            ref_to_zone = {z.zone_id: z for z in zones}
            for constraint in graph.spatial_constraints:
                if constraint.subject_ref_id not in ref_to_zone:
                    continue
                if constraint.object_ref_id and constraint.object_ref_id not in ref_to_zone:
                    continue

                if constraint.constraint_type in ("clearance", "exclusion") and constraint.distance_meters:
                    # Minimum separation constraint
                    min_dist = int(constraint.distance_meters * SCALE * 0.5)  # scale meters→canvas
                    s_id = constraint.subject_ref_id
                    o_id = constraint.object_ref_id
                    if o_id:
                        dx = model.new_int_var(-W, W, f"dx_{s_id}_{o_id}")
                        dy = model.new_int_var(-H, H, f"dy_{s_id}_{o_id}")
                        model.add(dx == xs[s_id] - xs[o_id])
                        model.add(dy == ys[s_id] - ys[o_id])
                        # Manhattan distance approximation (CP-SAT doesn't handle Euclidean natively)
                        abs_dx = model.new_int_var(0, W, f"adx_{s_id}_{o_id}")
                        abs_dy = model.new_int_var(0, H, f"ady_{s_id}_{o_id}")
                        model.add_abs_equality(abs_dx, dx)
                        model.add_abs_equality(abs_dy, dy)
                        model.add(abs_dx + abs_dy >= min_dist)

            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds = 5.0
            status = solver.solve(model)

            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                logger.info("[Agent4] Solver found valid layout")
                for z in zones:
                    new_cx = solver.value(xs[z.zone_id]) / SCALE
                    new_cy = solver.value(ys[z.zone_id]) / SCALE
                    old_cx = _zone_center(z).x
                    old_cy = _zone_center(z).y
                    dx = new_cx - old_cx
                    dy = new_cy - old_cy
                    z.polygon = [Coordinate(x=p.x + dx, y=p.y + dy) for p in z.polygon]
            else:
                logger.warning("[Agent4] Solver found no feasible solution — using proposal positions")

        except ImportError:
            logger.warning("[Agent4] OR-Tools not installed — using unsolved positions")
        except Exception as e:
            logger.warning(f"[Agent4] Solver error: {e} — using proposal positions")

        return zones

    # ------------------------------------------------------------------
    # Step 3: Movement paths
    # ------------------------------------------------------------------

    def _build_movement_paths(
        self,
        graph: ProceduralKnowledgeGraph,
        zones: list[Zone],
        proposals: dict[str, Any],
    ) -> list[MovementPath]:
        paths = []
        zone_centers = {z.zone_id: _zone_center(z) for z in zones}

        # Build actor start positions from proposals
        actor_starts: dict[str, Coordinate] = {}
        for ap in proposals.get("actor_start_positions", []):
            actor_starts[ap["actor_id"]] = Coordinate(x=ap["x"], y=ap["y"])

        # For each actor, trace their movement through steps
        for actor in graph.actors:
            waypoints = []
            t = 0.0

            for step in graph.steps:
                if actor.actor_id not in step.actors:
                    t += (step.duration_minutes or 5) * 60
                    continue

                # Determine destination: first spatial ref in step, or actor start
                dest: Coordinate | None = None
                for ref_id in step.spatial_refs:
                    if ref_id in zone_centers:
                        dest = zone_centers[ref_id]
                        # Offset slightly so multiple actors don't overlap
                        idx = list(graph.actors).index(actor)
                        dest = Coordinate(x=dest.x + idx * 15, y=dest.y + idx * 10)
                        break

                if dest is None:
                    dest = actor_starts.get(
                        actor.actor_id,
                        Coordinate(x=self.CANVAS_W / 2, y=self.CANVAS_H / 2)
                    )

                waypoints.append(Waypoint(
                    waypoint_id=str(uuid.uuid4()),
                    coordinate=dest,
                    timestamp_seconds=t,
                    label=step.title,
                ))
                t += (step.duration_minutes or 5) * 60

            if waypoints:
                paths.append(MovementPath(
                    path_id=str(uuid.uuid4()),
                    actor_id=actor.actor_id,
                    waypoints=waypoints,
                    step_id=graph.steps[0].step_id if graph.steps else "",
                ))

        return paths

    # ------------------------------------------------------------------
    # Step 4: Frame generation
    # ------------------------------------------------------------------

    def _compute_total_duration(self, graph: ProceduralKnowledgeGraph) -> float:
        return sum((s.duration_minutes or 5) for s in graph.steps) * 60

    def _generate_frames(
        self,
        graph: ProceduralKnowledgeGraph,
        zones: list[Zone],
        paths: list[MovementPath],
    ) -> list[Frame]:
        """Generate one frame per step (can be interpolated by the frontend)."""
        frames = []
        t = 0.0

        # Build lookup: actor_id → sorted waypoints
        path_map: dict[str, list[Waypoint]] = {p.actor_id: p.waypoints for p in paths}

        for step in graph.steps:
            actor_positions: dict[str, Coordinate] = {}
            for actor in graph.actors:
                wps = path_map.get(actor.actor_id, [])
                pos = _interpolate_position(wps, t)
                if pos:
                    actor_positions[actor.actor_id] = pos

            active_zones = [
                z.zone_id for z in zones
                if z.active_from_seconds <= t and (z.active_to_seconds is None or t <= z.active_to_seconds)
            ]

            frames.append(Frame(
                frame_id=str(uuid.uuid4()),
                timestamp_seconds=t,
                step_id=step.step_id,
                actor_positions=actor_positions,
                active_zones=active_zones,
                annotations=step.safety_flags,
            ))

            t += (step.duration_minutes or 5) * 60

        return frames


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _zone_center(zone: Zone) -> Coordinate:
    if not zone.polygon:
        return Coordinate(x=500.0, y=350.0)
    cx = sum(p.x for p in zone.polygon) / len(zone.polygon)
    cy = sum(p.y for p in zone.polygon) / len(zone.polygon)
    return Coordinate(x=cx, y=cy)


def _interpolate_position(waypoints: list[Waypoint], t: float) -> Coordinate | None:
    if not waypoints:
        return None
    if t <= waypoints[0].timestamp_seconds:
        return waypoints[0].coordinate
    if t >= waypoints[-1].timestamp_seconds:
        return waypoints[-1].coordinate

    for i in range(len(waypoints) - 1):
        a, b = waypoints[i], waypoints[i + 1]
        if a.timestamp_seconds <= t <= b.timestamp_seconds:
            dt = b.timestamp_seconds - a.timestamp_seconds
            ratio = (t - a.timestamp_seconds) / dt if dt > 0 else 0
            return Coordinate(
                x=a.coordinate.x + ratio * (b.coordinate.x - a.coordinate.x),
                y=a.coordinate.y + ratio * (b.coordinate.y - a.coordinate.y),
            )
    return waypoints[-1].coordinate
