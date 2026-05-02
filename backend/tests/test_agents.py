"""Integration tests for each agent in stub mode."""
from __future__ import annotations

import os
import pytest

# Force stub mode for all agent tests
os.environ["PROCVIZ_STUB_MODE"] = "true"

from procviz.agents import extraction, ingestion, layout, validation, visual_spec
from procviz.schemas import DocumentDomain, PipelineState


@pytest.fixture
def empty_state():
    return PipelineState(
        run_id="test-run-001",
        source_filename="mine_shutdown_sop.pdf",
        domain=DocumentDomain.MINING,
    )


@pytest.fixture
def state_after_ingestion(empty_state):
    return ingestion.run(empty_state)


@pytest.fixture
def state_after_extraction(state_after_ingestion):
    return extraction.run(state_after_ingestion)


@pytest.fixture
def state_after_validation(state_after_extraction):
    return validation.run(state_after_extraction)


@pytest.fixture
def state_after_layout(state_after_validation):
    return layout.run(state_after_validation)


@pytest.fixture
def state_after_visual_spec(state_after_layout):
    return visual_spec.run(state_after_layout)


# ---------------------------------------------------------------------------
# Agent 1: Ingestion
# ---------------------------------------------------------------------------

class TestIngestionAgent:
    def test_populates_parsed_document(self, state_after_ingestion):
        assert state_after_ingestion.parsed_document is not None

    def test_stub_blocks_present(self, state_after_ingestion):
        doc = state_after_ingestion.parsed_document
        assert len(doc.blocks) > 0

    def test_domain_preserved(self, state_after_ingestion):
        doc = state_after_ingestion.parsed_document
        assert doc.domain == DocumentDomain.MINING

    def test_domain_detection_mining(self):
        state = PipelineState(
            run_id="r2",
            source_filename="bhp_blast_procedure.pdf",
        )
        state = ingestion.run(state)
        assert state.parsed_document.domain == DocumentDomain.MINING

    def test_domain_detection_healthcare(self):
        state = PipelineState(
            run_id="r3",
            source_filename="patient_triage_protocol.pdf",
        )
        state = ingestion.run(state)
        assert state.parsed_document.domain == DocumentDomain.HEALTHCARE

    def test_domain_detection_defence(self):
        state = PipelineState(
            run_id="r4",
            source_filename="convoy_conops_briefing.pdf",
        )
        state = ingestion.run(state)
        assert state.parsed_document.domain == DocumentDomain.DEFENCE

    def test_missing_document_bytes_uses_stub(self):
        state = PipelineState(
            run_id="r5",
            source_filename="sop.pdf",
        )
        result = ingestion.run(state, document_bytes=None)
        assert result.parsed_document is not None
        assert result.parsed_document.metadata.get("stub") is True


# ---------------------------------------------------------------------------
# Agent 2: Extraction
# ---------------------------------------------------------------------------

class TestExtractionAgent:
    def test_populates_knowledge_graph(self, state_after_extraction):
        assert state_after_extraction.knowledge_graph is not None

    def test_steps_present(self, state_after_extraction):
        assert len(state_after_extraction.knowledge_graph.steps) > 0

    def test_actors_present(self, state_after_extraction):
        assert len(state_after_extraction.knowledge_graph.actors) > 0

    def test_no_errors(self, state_after_extraction):
        assert state_after_extraction.errors == []

    def test_missing_parsed_doc_records_error(self):
        state = PipelineState(run_id="r6", source_filename="x.pdf")
        result = extraction.run(state)
        assert any("parsed_document is missing" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Agent 3: Validation
# ---------------------------------------------------------------------------

class TestValidationAgent:
    def test_populates_enriched_graph(self, state_after_validation):
        assert state_after_validation.enriched_graph is not None

    def test_issues_is_list(self, state_after_validation):
        assert isinstance(state_after_validation.enriched_graph.issues, list)

    def test_regulatory_refs_mining(self, state_after_validation):
        refs = state_after_validation.enriched_graph.regulatory_refs
        assert any("ISO 45001" in r for r in refs)

    def test_missing_graph_records_error(self):
        state = PipelineState(run_id="r7", source_filename="x.pdf")
        result = validation.run(state)
        assert any("knowledge_graph is missing" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Agent 4: Layout
# ---------------------------------------------------------------------------

class TestLayoutAgent:
    def test_populates_spatial_layout(self, state_after_layout):
        assert state_after_layout.spatial_layout is not None

    def test_frames_match_steps(self, state_after_layout):
        layout_obj = state_after_layout.spatial_layout
        kg = state_after_layout.knowledge_graph
        assert len(layout_obj.frames) == len(kg.steps)

    def test_canvas_dimensions(self, state_after_layout):
        layout_obj = state_after_layout.spatial_layout
        assert layout_obj.canvas_width == 1920.0
        assert layout_obj.canvas_height == 1080.0

    def test_entities_within_canvas(self, state_after_layout):
        layout_obj = state_after_layout.spatial_layout
        for entity in layout_obj.entities:
            assert 0 <= entity.coordinate.x <= layout_obj.canvas_width
            assert 0 <= entity.coordinate.y <= layout_obj.canvas_height

    def test_missing_enriched_graph_records_error(self):
        state = PipelineState(run_id="r8", source_filename="x.pdf")
        result = layout.run(state)
        assert any("enriched_graph is missing" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Agent 5: Visual Specification
# ---------------------------------------------------------------------------

class TestVisualSpecAgent:
    def test_populates_visual_spec(self, state_after_visual_spec):
        assert state_after_visual_spec.visual_spec is not None

    def test_completed_flag(self, state_after_visual_spec):
        assert state_after_visual_spec.completed is True

    def test_elements_present(self, state_after_visual_spec):
        assert len(state_after_visual_spec.visual_spec.elements) > 0

    def test_spec_has_domain(self, state_after_visual_spec):
        assert state_after_visual_spec.visual_spec.domain == DocumentDomain.MINING

    def test_spec_title_contains_domain(self, state_after_visual_spec):
        title = state_after_visual_spec.visual_spec.title
        assert "Mining" in title

    def test_metadata_has_run_id(self, state_after_visual_spec):
        meta = state_after_visual_spec.visual_spec.metadata
        assert meta.get("run_id") == "test-run-001"

    def test_missing_layout_records_error(self):
        state = PipelineState(run_id="r9", source_filename="x.pdf")
        result = visual_spec.run(state)
        assert any("spatial_layout is missing" in e for e in result.errors)
