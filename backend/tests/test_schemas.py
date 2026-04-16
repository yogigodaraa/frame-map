"""Tests for the ProcViz data schemas."""
from __future__ import annotations

import pytest

from procviz.schemas import (
    Actor,
    BoundingBox,
    ConfidenceLevel,
    Coordinate,
    DocumentBlock,
    DocumentDomain,
    EnrichedKnowledgeGraph,
    Keyframe,
    LayoutEntity,
    LayoutFrame,
    MovementPath,
    ParsedDocument,
    PipelineState,
    ProceduralKnowledgeGraph,
    ProceduralStep,
    SpatialReference,
    SpatialTemporalLayout,
    TemporalConstraint,
    TemporalRelation,
    ValidationIssue,
    VisualElement,
    VisualSpecification,
    Waypoint,
)


class TestCoordinate:
    def test_basic(self):
        c = Coordinate(x=10.0, y=20.0)
        assert c.x == 10.0
        assert c.y == 20.0


class TestBoundingBox:
    def test_basic(self):
        bb = BoundingBox(x=0, y=0, width=100, height=50)
        assert bb.width == 100


class TestDocumentBlock:
    def test_defaults(self):
        block = DocumentBlock(
            block_id="b1",
            block_type="text",
            content="Step 1: Do something.",
            page_number=1,
        )
        assert block.confidence == 1.0
        assert block.bounding_box is None

    def test_confidence_clamped(self):
        with pytest.raises(Exception):
            DocumentBlock(
                block_id="b1",
                block_type="text",
                content="x",
                page_number=1,
                confidence=1.5,  # > 1.0 should fail validation
            )


class TestParsedDocument:
    def test_empty_blocks(self):
        doc = ParsedDocument(
            document_id="d1",
            source_filename="test.pdf",
            domain=DocumentDomain.MINING,
            total_pages=5,
        )
        assert doc.blocks == []
        assert doc.metadata == {}


class TestProceduralStep:
    def test_defaults(self):
        step = ProceduralStep(
            step_id="s1",
            sequence_number=1,
            description="Ensure ventilation is active.",
        )
        assert step.is_conditional is False
        assert step.safety_flags == []
        assert step.actors == []


class TestProceduralKnowledgeGraph:
    def test_empty_graph(self):
        graph = ProceduralKnowledgeGraph(
            graph_id="g1",
            document_id="d1",
            domain=DocumentDomain.HEALTHCARE,
        )
        assert graph.steps == []
        assert graph.actors == []

    def test_with_steps(self):
        step = ProceduralStep(
            step_id="s1",
            sequence_number=1,
            description="Apply PPE before entering the operating theatre.",
        )
        actor = Actor(actor_id="a1", name="Nurse", role="Scrub Nurse")
        graph = ProceduralKnowledgeGraph(
            graph_id="g1",
            document_id="d1",
            domain=DocumentDomain.HEALTHCARE,
            steps=[step],
            actors=[actor],
        )
        assert len(graph.steps) == 1
        assert graph.actors[0].role == "Scrub Nurse"


class TestEnrichedKnowledgeGraph:
    def test_no_issues(self):
        graph = ProceduralKnowledgeGraph(
            graph_id="g1",
            document_id="d1",
            domain=DocumentDomain.GENERIC,
        )
        enriched = EnrichedKnowledgeGraph(graph=graph)
        assert enriched.issues == []
        assert enriched.requires_human_review is False
        assert enriched.overall_confidence == ConfidenceLevel.MEDIUM

    def test_with_issues(self):
        issue = ValidationIssue(
            issue_id="v1",
            severity="error",
            message="Missing ventilation step.",
        )
        graph = ProceduralKnowledgeGraph(
            graph_id="g1",
            document_id="d1",
            domain=DocumentDomain.MINING,
        )
        enriched = EnrichedKnowledgeGraph(graph=graph, issues=[issue])
        assert len(enriched.issues) == 1


class TestSpatialTemporalLayout:
    def test_defaults(self):
        layout = SpatialTemporalLayout(
            layout_id="l1",
            graph_id="g1",
        )
        assert layout.canvas_width == 1920.0
        assert layout.canvas_height == 1080.0
        assert layout.frames == []


class TestVisualSpecification:
    def test_basic(self):
        spec = VisualSpecification(
            spec_id="vs1",
            layout_id="l1",
            title="Mining Procedure",
            description="Test",
            domain=DocumentDomain.MINING,
        )
        assert spec.total_duration_seconds == 0.0
        assert spec.elements == []


class TestPipelineState:
    def test_initial(self):
        state = PipelineState(
            run_id="r1",
            source_filename="mine_sop.pdf",
        )
        assert state.domain == DocumentDomain.GENERIC
        assert state.completed is False
        assert state.errors == []
        assert state.current_agent == "ingestion"

    def test_serialization_roundtrip(self):
        state = PipelineState(
            run_id="r1",
            source_filename="test.pdf",
            domain=DocumentDomain.DEFENCE,
        )
        dumped = state.model_dump()
        restored = PipelineState(**dumped)
        assert restored.run_id == "r1"
        assert restored.domain == DocumentDomain.DEFENCE
