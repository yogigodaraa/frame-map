"""Tests for the FastAPI REST endpoints."""
from __future__ import annotations

import io
import os
import pytest

os.environ["PROCVIZ_STUB_MODE"] = "true"

from fastapi.testclient import TestClient

from procviz.main import app

client = TestClient(app)


class TestHealthEndpoint:
    def test_health_ok(self):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestPipelineRun:
    def test_run_returns_run_id(self):
        file_content = b"Step 1: Ensure ventilation.\nStep 2: Check blast face."
        response = client.post(
            "/api/pipeline/run",
            files={"file": ("test_sop.pdf", io.BytesIO(file_content), "application/pdf")},
            data={"domain": "mining"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["status"] == "completed"

    def test_run_returns_spec_id(self):
        file_content = b"Step 1: Do something."
        response = client.post(
            "/api/pipeline/run",
            files={"file": ("sop.pdf", io.BytesIO(file_content), "application/pdf")},
            data={"domain": "generic"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("spec_id") is not None


class TestPipelineStatus:
    def test_get_status_after_run(self):
        file_content = b"Step 1: Apply PPE."
        run_resp = client.post(
            "/api/pipeline/run",
            files={"file": ("health.pdf", io.BytesIO(file_content), "application/pdf")},
            data={"domain": "healthcare"},
        )
        run_id = run_resp.json()["run_id"]

        status_resp = client.get(f"/api/pipeline/{run_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["run_id"] == run_id

    def test_unknown_run_id_returns_404(self):
        response = client.get("/api/pipeline/nonexistent-run-id")
        assert response.status_code == 404


class TestSpecRetrieval:
    def test_get_spec_after_run(self):
        file_content = b"Step 1: Convoy check."
        run_resp = client.post(
            "/api/pipeline/run",
            files={"file": ("convoy.pdf", io.BytesIO(file_content), "application/pdf")},
            data={"domain": "defence"},
        )
        spec_id = run_resp.json()["spec_id"]

        spec_resp = client.get(f"/api/spec/{spec_id}")
        assert spec_resp.status_code == 200
        spec = spec_resp.json()
        assert spec["spec_id"] == spec_id
        assert "elements" in spec
        assert "keyframes" in spec

    def test_unknown_spec_id_returns_404(self):
        response = client.get("/api/spec/nonexistent-spec")
        assert response.status_code == 404
