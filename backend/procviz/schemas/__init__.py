"""
ProcViz data schemas — Pydantic models shared across all agents.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class DocumentDomain(str, Enum):
    MINING = "mining"
    HEALTHCARE = "healthcare"
    DEFENCE = "defence"
    GENERIC = "generic"


class TemporalRelation(str, Enum):
    BEFORE = "before"
    AFTER = "after"
    DURING = "during"
    SIMULTANEOUSLY = "simultaneously"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"


class ConfidenceLevel(str, Enum):
    HIGH = "high"      # >= 0.85
    MEDIUM = "medium"  # >= 0.60
    LOW = "low"        # < 0.60


# ---------------------------------------------------------------------------
# Primitive building blocks
# ---------------------------------------------------------------------------

class Coordinate(BaseModel):
    x: float = Field(..., description="Horizontal position in canvas units")
    y: float = Field(..., description="Vertical position in canvas units")


class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class Waypoint(BaseModel):
    coordinate: Coordinate
    timestamp_seconds: float = Field(
        ..., description="Time offset from sequence start (seconds)"
    )
    label: Optional[str] = None


# ---------------------------------------------------------------------------
# Document ingestion (Agent 1)
# ---------------------------------------------------------------------------

class DocumentBlock(BaseModel):
    """A single parsed block from the source document."""
    block_id: str
    block_type: str = Field(
        ..., description="text | table | diagram | image | heading"
    )
    content: str
    page_number: int
    bounding_box: Optional[BoundingBox] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ParsedDocument(BaseModel):
    """Structured representation of an ingested document (Agent 1 output)."""
    document_id: str
    source_filename: str
    domain: DocumentDomain
    total_pages: int
    blocks: list[DocumentBlock] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    parser_confidence: float = Field(default=1.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Procedural knowledge extraction (Agent 2)
# ---------------------------------------------------------------------------

class Actor(BaseModel):
    actor_id: str
    name: str
    role: str
    equipment: list[str] = Field(default_factory=list)


class SpatialReference(BaseModel):
    """A spatial entity extracted from procedural text."""
    ref_id: str
    label: str
    raw_text: str
    zone_type: Optional[str] = None   # zone | point | path | clearance
    distance_meters: Optional[float] = None
    relative_to: Optional[str] = None  # ref_id of anchor entity
    bearing: Optional[str] = None      # e.g. "downwind", "north"


class TemporalConstraint(BaseModel):
    """A temporal dependency between two procedural steps."""
    constraint_id: str
    step_from: str
    step_to: str
    relation: TemporalRelation
    raw_text: str


class ProceduralStep(BaseModel):
    step_id: str
    sequence_number: int
    description: str
    actors: list[str] = Field(default_factory=list)  # actor_id refs
    equipment: list[str] = Field(default_factory=list)
    spatial_refs: list[str] = Field(default_factory=list)  # SpatialReference ids
    duration_seconds: Optional[float] = None
    is_conditional: bool = False
    condition_expression: Optional[str] = None
    safety_flags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ProceduralKnowledgeGraph(BaseModel):
    """Structured procedural knowledge extracted by Agent 2."""
    graph_id: str
    document_id: str
    domain: DocumentDomain
    steps: list[ProceduralStep] = Field(default_factory=list)
    actors: list[Actor] = Field(default_factory=list)
    spatial_references: list[SpatialReference] = Field(default_factory=list)
    temporal_constraints: list[TemporalConstraint] = Field(default_factory=list)
    extraction_confidence: float = Field(default=1.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Domain validation (Agent 3)
# ---------------------------------------------------------------------------

class ValidationIssue(BaseModel):
    issue_id: str
    severity: str  # error | warning | info
    step_id: Optional[str] = None
    message: str
    regulatory_ref: Optional[str] = None
    suggestion: Optional[str] = None


class EnrichedKnowledgeGraph(BaseModel):
    """Agent 3 output: validated + enriched procedural graph."""
    graph: ProceduralKnowledgeGraph
    issues: list[ValidationIssue] = Field(default_factory=list)
    regulatory_refs: list[str] = Field(default_factory=list)
    enrichment_notes: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    overall_confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM


# ---------------------------------------------------------------------------
# Spatial-temporal layout (Agent 4)
# ---------------------------------------------------------------------------

class LayoutEntity(BaseModel):
    """A positioned entity in the spatial layout."""
    entity_id: str
    label: str
    entity_type: str  # actor | zone | equipment | waypoint
    coordinate: Coordinate
    radius: Optional[float] = None  # for circular zones
    bounding_box: Optional[BoundingBox] = None
    color: Optional[str] = None


class MovementPath(BaseModel):
    """Animated movement path for an actor or equipment."""
    path_id: str
    actor_id: str
    waypoints: list[Waypoint]


class LayoutFrame(BaseModel):
    """Snapshot of the spatial layout at a point in time."""
    frame_id: str
    step_id: str
    timestamp_seconds: float
    entities: list[LayoutEntity] = Field(default_factory=list)
    active_paths: list[str] = Field(default_factory=list)  # path_ids


class SpatialTemporalLayout(BaseModel):
    """Agent 4 output: frame-by-frame spatial layout."""
    layout_id: str
    graph_id: str
    canvas_width: float = 1920.0
    canvas_height: float = 1080.0
    background_image_url: Optional[str] = None
    entities: list[LayoutEntity] = Field(default_factory=list)
    paths: list[MovementPath] = Field(default_factory=list)
    frames: list[LayoutFrame] = Field(default_factory=list)
    total_duration_seconds: float = 0.0
    solver_used: str = "constraint_solver"


# ---------------------------------------------------------------------------
# Visual specification (Agent 5)
# ---------------------------------------------------------------------------

class VisualElement(BaseModel):
    """A single visual element for the React canvas."""
    element_id: str
    element_type: str   # icon | label | zone | path | annotation
    icon_name: Optional[str] = None
    text: Optional[str] = None
    color: str = "#4A90D9"
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    coordinate: Coordinate
    bounding_box: Optional[BoundingBox] = None
    z_index: int = 0


class Keyframe(BaseModel):
    """Animation keyframe for a visual element."""
    element_id: str
    timestamp_seconds: float
    coordinate: Optional[Coordinate] = None
    opacity: Optional[float] = None
    color: Optional[str] = None


class VisualSpecification(BaseModel):
    """
    Agent 5 output: SpaceDraft-compatible JSON specification.
    Consumed directly by the React/Konva renderer.
    """
    spec_id: str
    layout_id: str
    title: str
    description: str
    domain: DocumentDomain
    canvas_width: float = 1920.0
    canvas_height: float = 1080.0
    background_image_url: Optional[str] = None
    elements: list[VisualElement] = Field(default_factory=list)
    keyframes: list[Keyframe] = Field(default_factory=list)
    total_duration_seconds: float = 0.0
    safety_annotations: list[str] = Field(default_factory=list)
    compliance_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pipeline state (shared LangGraph state)
# ---------------------------------------------------------------------------

class PipelineState(BaseModel):
    """Mutable state passed between agents in the LangGraph workflow."""
    run_id: str
    source_filename: str
    domain: DocumentDomain = DocumentDomain.GENERIC

    # Progressive outputs
    parsed_document: Optional[ParsedDocument] = None
    knowledge_graph: Optional[ProceduralKnowledgeGraph] = None
    enriched_graph: Optional[EnrichedKnowledgeGraph] = None
    spatial_layout: Optional[SpatialTemporalLayout] = None
    visual_spec: Optional[VisualSpecification] = None

    # Control flow
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    current_agent: str = "ingestion"
    completed: bool = False
