"""
Agent 5: Visual Specification

Converts the spatial-temporal layout into a SpaceDraft-compatible JSON spec
that the React/Konva renderer can consume directly.

Also generates narration text for each step (for TTS/voiceover).
"""
from __future__ import annotations

import logging
import uuid

from anthropic import Anthropic

from backend.models.schemas import (
    Actor,
    ActorType,
    AnimationSequence,
    ConfidenceLevel,
    DocumentDomain,
    KeyFrame,
    ProceduralKnowledgeGraph,
    SpatialTemporalLayout,
    ValidationResult,
    VisualIcon,
    VisualSpecification,
)

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-3-7-sonnet-20250219"

ACTOR_ICON_MAP: dict[ActorType, str] = {
    ActorType.PERSON: "person",
    ActorType.ROLE: "person",
    ActorType.EQUIPMENT: "equipment",
    ActorType.VEHICLE: "vehicle",
    ActorType.SYSTEM: "system",
}

ACTOR_COLOR_MAP: dict[ActorType, str] = {
    ActorType.PERSON: "#3B82F6",    # blue
    ActorType.ROLE: "#8B5CF6",      # purple
    ActorType.EQUIPMENT: "#F59E0B", # amber
    ActorType.VEHICLE: "#EF4444",   # red
    ActorType.SYSTEM: "#10B981",    # green
}

DOMAIN_PALETTE: dict[DocumentDomain, dict[str, str]] = {
    DocumentDomain.MINING: {"primary": "#F59E0B", "secondary": "#78350F", "accent": "#EF4444"},
    DocumentDomain.HEALTHCARE: {"primary": "#3B82F6", "secondary": "#1E3A5F", "accent": "#22C55E"},
    DocumentDomain.DEFENCE: {"primary": "#4B5563", "secondary": "#111827", "accent": "#EF4444"},
    DocumentDomain.GENERIC: {"primary": "#6366F1", "secondary": "#1E1B4B", "accent": "#F59E0B"},
}


class VisualSpecificationAgent:
    """
    Produces the final VisualSpecification from layout + knowledge graph + validation.
    """

    def __init__(self, generate_narration: bool = True):
        self.claude = Anthropic()
        self.generate_narration = generate_narration

    def run(
        self,
        layout: SpatialTemporalLayout,
        validation_result: ValidationResult,
    ) -> VisualSpecification:
        graph = validation_result.validated_graph
        logger.info(f"[Agent5] Building visual spec for doc {graph.doc_id}")

        icons = self._build_icons(graph)
        sequences = self._build_sequences(graph, layout, icons)

        if self.generate_narration:
            sequences = self._add_narration(sequences, graph)

        # Determine overall confidence
        conf = graph.extraction_confidence
        if conf >= 0.85:
            confidence_level = ConfidenceLevel.HIGH
        elif conf >= 0.60:
            confidence_level = ConfidenceLevel.MEDIUM
        else:
            confidence_level = ConfidenceLevel.LOW

        spec = VisualSpecification(
            doc_id=graph.doc_id,
            title=graph.title,
            domain=graph.domain,
            total_duration_seconds=layout.total_duration_seconds,
            background_type=layout.background_type,
            canvas_width=layout.canvas_width,
            canvas_height=layout.canvas_height,
            icons=icons,
            zones=layout.zones,
            sequences=sequences,
            metadata={
                "palette": DOMAIN_PALETTE.get(graph.domain, DOMAIN_PALETTE[DocumentDomain.GENERIC]),
                "step_count": len(graph.steps),
                "actor_count": len(graph.actors),
                "spatial_ref_count": len(graph.spatial_references),
                "compliance_score": validation_result.compliance_score,
                "extraction_confidence": graph.extraction_confidence,
            },
            confidence_level=confidence_level,
            validation_issues=validation_result.issues,
        )

        logger.info(
            f"[Agent5] Spec complete — {len(icons)} icons, {len(sequences)} sequences, "
            f"confidence={confidence_level}"
        )
        return spec

    # ------------------------------------------------------------------

    def _build_icons(self, graph: ProceduralKnowledgeGraph) -> list[VisualIcon]:
        icons = []
        for actor in graph.actors:
            icons.append(VisualIcon(
                icon_id=f"icon_{actor.actor_id}",
                actor_id=actor.actor_id,
                icon_type=ACTOR_ICON_MAP.get(actor.actor_type, "person"),
                label=actor.name,
                color=ACTOR_COLOR_MAP.get(actor.actor_type, "#3B82F6"),
                size=32.0,
            ))
        return icons

    def _build_sequences(
        self,
        graph: ProceduralKnowledgeGraph,
        layout: SpatialTemporalLayout,
        icons: list[VisualIcon],
    ) -> list[AnimationSequence]:
        sequences = []
        icon_map = {i.actor_id: i for i in icons}

        t = 0.0
        for step in graph.steps:
            duration = (step.duration_minutes or 5) * 60
            end_t = t + duration

            # Find frames in this step's time window
            step_frames = [f for f in layout.frames if f.step_id == step.step_id]

            keyframes: list[KeyFrame] = []
            for frame in step_frames:
                for actor_id, position in frame.actor_positions.items():
                    icon = icon_map.get(actor_id)
                    if not icon:
                        continue
                    keyframes.append(KeyFrame(
                        keyframe_id=str(uuid.uuid4()),
                        timestamp_seconds=frame.timestamp_seconds,
                        icon_id=icon.icon_id,
                        position=position,
                        opacity=1.0,
                        scale=1.0,
                        annotation=step.title if frame.annotations else None,
                    ))

            sequences.append(AnimationSequence(
                sequence_id=str(uuid.uuid4()),
                step_id=step.step_id,
                step_title=step.title,
                start_seconds=t,
                end_seconds=end_t,
                keyframes=keyframes,
                narration=None,  # filled by _add_narration
            ))
            t = end_t

        return sequences

    def _add_narration(
        self,
        sequences: list[AnimationSequence],
        graph: ProceduralKnowledgeGraph,
    ) -> list[AnimationSequence]:
        """Generate short narration text for each step using Claude."""
        step_map = {s.step_id: s for s in graph.steps}
        steps_for_narration = [
            {"step_id": seq.step_id, "title": seq.step_title,
             "description": step_map.get(seq.step_id, {}).description if seq.step_id in step_map else ""}
            for seq in sequences[:20]  # limit
        ]

        import json
        prompt = f"""Generate short, clear narration text (1-2 sentences) for each step of this {graph.domain.value} procedure.
The narration will be read aloud as a voiceover.
Use plain language. Focus on the action and who does it.

Steps:
{json.dumps(steps_for_narration, indent=2)}

Return JSON: [{{"step_id": "str", "narration": "str"}}]"""

        message = self.claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            narrations = {item["step_id"]: item["narration"] for item in json.loads(raw)}
            for seq in sequences:
                if seq.step_id in narrations:
                    seq.narration = narrations[seq.step_id]
        except Exception as e:
            logger.warning(f"[Agent5] Narration parse error: {e}")

        return sequences
