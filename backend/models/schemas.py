"""
ProcViz Pydantic schemas — the shared data contract across all agents.
"""
from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DocumentDomain(str, Enum):
    MINING = "mining"
    HEALTHCARE = "healthcare"
    DEFENCE = "defence"
    GENERIC = "generic"


class ConfidenceLevel(str, Enum):
    HIGH = "high"      # ≥0.85 — auto-proceed
    MEDIUM = "medium"  # 0.60–0.84 — flag for review
    LOW = "low"        # <0.60 — escalate to human


class ConstraintType(str, Enum):
    BEFORE = "before"
    AFTER = "after"
    SIMULTANEOUS = "simultaneous"
    WITHIN = "within"
    CLEARANCE = "clearance"
    PROXIMITY = "proximity"
    EXCLUSION = "exclusion"


class ActorType(str, Enum):
    PERSON = "person"
    ROLE = "role"
    EQUIPMENT = "equipment"
    VEHICLE = "vehicle"
    SYSTEM = "system"


# ---------------------------------------------------------------------------
# Document Ingestion (Agent 1 output)
# ---------------------------------------------------------------------------

class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float
    page: int = 0


class DocumentBlock(BaseModel):
    block_id: str
    block_type: str  # text | table | figure | header | footer
    content: str
    bbox: BoundingBox | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    doc_id: str
    filename: str
    domain: DocumentDomain
    page_count: int
    blocks: list[DocumentBlock]
    raw_text: str
    parse_confidence: float = Field(ge=0.0, le=1.0)
    parser_used: str  # textract | docling | combined


# ---------------------------------------------------------------------------
# Procedural Extraction (Agent 2 output)
# ---------------------------------------------------------------------------

class Actor(BaseModel):
    actor_id: str
    name: str
    actor_type: ActorType
    properties: dict[str, Any] = Field(default_factory=dict)


class SpatialReference(BaseModel):
    ref_id: str
    label: str          # "Zone B", "western access point"
    raw_text: str       # verbatim from document
    resolved: bool = False
    coordinates: tuple[float, float] | None = None  # resolved later by Agent 4
    properties: dict[str, Any] = Field(default_factory=dict)


class TemporalConstraint(BaseModel):
    constraint_id: str
    constraint_type: ConstraintType
    subject_step_id: str
    object_step_id: str | None = None
    duration_minutes: float | None = None
    raw_text: str


class SpatialConstraint(BaseModel):
    constraint_id: str
    constraint_type: ConstraintType
    subject_ref_id: str
    object_ref_id: str | None = None
    distance_meters: float | None = None
    raw_text: str


class ProceduralStep(BaseModel):
    step_id: str
    sequence_number: int
    title: str
    description: str
    actors: list[str] = Field(default_factory=list)   # actor_ids
    equipment: list[str] = Field(default_factory=list)
    spatial_refs: list[str] = Field(default_factory=list)  # ref_ids
    safety_flags: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)   # if/when conditions
    outputs: list[str] = Field(default_factory=list)
    duration_minutes: float | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class ConditionalBranch(BaseModel):
    branch_id: str
    condition: str
    from_step_id: str
    true_step_id: str
    false_step_id: str | None = None


class ProceduralKnowledgeGraph(BaseModel):
    doc_id: str
    domain: DocumentDomain
    title: str
    actors: list[Actor]
    steps: list[ProceduralStep]
    temporal_constraints: list[TemporalConstraint]
    spatial_constraints: list[SpatialConstraint]
    spatial_references: list[SpatialReference]
    branches: list[ConditionalBranch]
    extraction_confidence: float = Field(ge=0.0, le=1.0)
    extraction_issues: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Domain Validation (Agent 3 output)
# ---------------------------------------------------------------------------

class ValidationIssue(BaseModel):
    issue_id: str
    severity: str  # critical | warning | info
    step_id: str | None = None
    regulation_ref: str | None = None
    description: str
    recommendation: str | None = None


class ValidationResult(BaseModel):
    doc_id: str
    is_valid: bool
    issues: list[ValidationIssue]
    enrichments: dict[str, Any] = Field(default_factory=dict)  # added spatial templates, equipment dims, etc.
    compliance_score: float = Field(ge=0.0, le=1.0)
    validated_graph: ProceduralKnowledgeGraph


# ---------------------------------------------------------------------------
# Spatial-Temporal Layout (Agent 4 output)
# ---------------------------------------------------------------------------

class Coordinate(BaseModel):
    x: float  # canvas units (0–1000)
    y: float


class Waypoint(BaseModel):
    waypoint_id: str
    coordinate: Coordinate
    timestamp_seconds: float
    label: str | None = None


class MovementPath(BaseModel):
    path_id: str
    actor_id: str
    waypoints: list[Waypoint]
    step_id: str


class Zone(BaseModel):
    zone_id: str
    label: str
    polygon: list[Coordinate]   # convex hull vertices
    zone_type: str              # safety | work | exclusion | staging
    active_from_seconds: float = 0.0
    active_to_seconds: float | None = None
    color: str = "#FF000033"


class Frame(BaseModel):
    frame_id: str
    timestamp_seconds: float
    step_id: str
    actor_positions: dict[str, Coordinate]   # actor_id → position
    active_zones: list[str]                  # zone_ids
    annotations: list[str] = Field(default_factory=list)


class SpatialTemporalLayout(BaseModel):
    doc_id: str
    total_duration_seconds: float
    background_type: str  # map | floorplan | aerial | generic
    canvas_width: float = 1000.0
    canvas_height: float = 700.0
    zones: list[Zone]
    movement_paths: list[MovementPath]
    frames: list[Frame]
    solver_stats: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Visual Specification (Agent 5 output — SpaceDraft-compatible)
# ---------------------------------------------------------------------------

class VisualIcon(BaseModel):
    icon_id: str
    actor_id: str
    icon_type: str   # person | vehicle | equipment | zone
    label: str
    color: str = "#3B82F6"
    size: float = 32.0


class KeyFrame(BaseModel):
    keyframe_id: str
    timestamp_seconds: float
    icon_id: str
    position: Coordinate
    opacity: float = 1.0
    scale: float = 1.0
    annotation: str | None = None


class AnimationSequence(BaseModel):
    sequence_id: str
    step_id: str
    step_title: str
    start_seconds: float
    end_seconds: float
    keyframes: list[KeyFrame]
    narration: str | None = None


class VisualSpecification(BaseModel):
    """
    Final output — can be consumed by the React canvas renderer
    or adapted to SpaceDraft's proprietary JSON format.
    """
    doc_id: str
    title: str
    domain: DocumentDomain
    total_duration_seconds: float
    background_type: str
    canvas_width: float
    canvas_height: float
    icons: list[VisualIcon]
    zones: list[Zone]
    sequences: list[AnimationSequence]
    metadata: dict[str, Any] = Field(default_factory=dict)
    confidence_level: ConfidenceLevel
    validation_issues: list[ValidationIssue] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline state (shared across LangGraph nodes)
# ---------------------------------------------------------------------------

class PipelineState(BaseModel):
    job_id: str
    filename: str
    domain: DocumentDomain
    parsed_doc: ParsedDocument | None = None
    knowledge_graph: ProceduralKnowledgeGraph | None = None
    validation_result: ValidationResult | None = None
    spatial_layout: SpatialTemporalLayout | None = None
    visual_spec: VisualSpecification | None = None
    errors: list[str] = Field(default_factory=list)
    human_review_required: bool = False
    current_step: str = "ingestion"
