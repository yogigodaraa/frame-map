"""End-to-end pipeline integration test (stub mode)."""
from __future__ import annotations

import os
import pytest

os.environ["PROCVIZ_STUB_MODE"] = "true"

from procviz.orchestrator import run_pipeline
from procviz.schemas import DocumentDomain


class TestFullPipeline:
    def test_mining_pipeline_completes(self):
        state = run_pipeline(
            source_filename="mine_shutdown_sop.pdf",
            domain=DocumentDomain.MINING,
        )
        assert state.completed is True
        assert state.visual_spec is not None

    def test_healthcare_pipeline_completes(self):
        state = run_pipeline(
            source_filename="patient_triage_protocol.pdf",
            domain=DocumentDomain.HEALTHCARE,
        )
        assert state.completed is True
        assert state.visual_spec is not None

    def test_defence_pipeline_completes(self):
        state = run_pipeline(
            source_filename="convoy_conops.pdf",
            domain=DocumentDomain.DEFENCE,
        )
        assert state.completed is True
        assert state.visual_spec is not None

    def test_generic_pipeline_completes(self):
        state = run_pipeline(
            source_filename="general_sop.pdf",
        )
        assert state.completed is True

    def test_pipeline_spec_is_valid(self):
        state = run_pipeline(
            source_filename="test_procedure.pdf",
            domain=DocumentDomain.MINING,
        )
        spec = state.visual_spec
        assert spec is not None
        assert spec.canvas_width == 1920.0
        assert spec.canvas_height == 1080.0
        assert len(spec.elements) > 0
        assert spec.total_duration_seconds > 0

    def test_pipeline_metadata_includes_run_id(self):
        state = run_pipeline(
            source_filename="test.pdf",
            domain=DocumentDomain.MINING,
        )
        assert state.visual_spec.metadata["run_id"] == state.run_id

    def test_pipeline_errors_do_not_crash(self):
        """Empty filename should still complete in stub mode."""
        state = run_pipeline(
            source_filename="",
            domain=DocumentDomain.GENERIC,
        )
        # Pipeline should attempt to complete without raising exceptions
        assert state is not None
