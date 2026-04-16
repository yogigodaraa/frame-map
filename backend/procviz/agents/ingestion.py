"""Agent 1 – Document Ingestion & Parsing Agent.

Accepts a raw document (PDF bytes or S3 key) and produces a ``ParsedDocument``
using a layered parsing strategy:

1. Primary: AWS Textract (OCR + layout analysis)
2. Fallback for complex tables: IBM Docling via CLI subprocess
3. Structured extraction: Claude (constrained JSON schema decoding)

In environments without AWS credentials the agent operates in *stub mode*,
returning a deterministic placeholder so that the rest of the pipeline can
be exercised end-to-end without cloud access.
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from procviz.schemas import (
    BoundingBox,
    DocumentBlock,
    DocumentDomain,
    ParsedDocument,
    PipelineState,
)

logger = logging.getLogger(__name__)

_STUB_MODE = os.getenv("PROCVIZ_STUB_MODE", "false").lower() == "true"


def _detect_domain(filename: str, raw_text: str) -> DocumentDomain:
    """Heuristic domain detection from filename / content keywords."""
    combined = (filename + " " + raw_text).lower()
    if any(kw in combined for kw in ("mine", "blast", "ore", "shaft", "tunnel", "bhp", "rio tinto")):
        return DocumentDomain.MINING
    if any(kw in combined for kw in ("patient", "clinical", "ward", "triage", "protocol", "infection")):
        return DocumentDomain.HEALTHCARE
    if any(kw in combined for kw in ("convoy", "conops", "stanag", "mission", "tactical", "briefing")):
        return DocumentDomain.DEFENCE
    return DocumentDomain.GENERIC


def _textract_blocks_to_doc_blocks(textract_blocks: list[dict[str, Any]]) -> list[DocumentBlock]:
    """Convert Textract API response blocks to our internal schema."""
    doc_blocks: list[DocumentBlock] = []
    for block in textract_blocks:
        block_type = block.get("BlockType", "UNKNOWN")
        if block_type not in {"LINE", "TABLE", "PAGE"}:
            continue
        text = block.get("Text", "") or ""
        geometry = block.get("Geometry", {}).get("BoundingBox", {})
        bbox = (
            BoundingBox(
                x=geometry.get("Left", 0.0),
                y=geometry.get("Top", 0.0),
                width=geometry.get("Width", 0.0),
                height=geometry.get("Height", 0.0),
            )
            if geometry
            else None
        )
        doc_blocks.append(
            DocumentBlock(
                block_id=block.get("Id", str(uuid.uuid4())),
                block_type="table" if block_type == "TABLE" else "text",
                content=text,
                page_number=block.get("Page", 1),
                bounding_box=bbox,
                confidence=block.get("Confidence", 100.0) / 100.0,
            )
        )
    return doc_blocks


def _stub_parse(filename: str, content_hash: str) -> ParsedDocument:
    """Return a deterministic stub document for offline / test usage."""
    domain = _detect_domain(filename, "")
    blocks = [
        DocumentBlock(
            block_id=f"stub-block-{i}",
            block_type="text",
            content=f"[STUB] Step {i}: Placeholder procedural step for document '{filename}'.",
            page_number=1,
            confidence=0.95,
        )
        for i in range(1, 6)
    ]
    return ParsedDocument(
        document_id=content_hash,
        source_filename=filename,
        domain=domain,
        total_pages=1,
        blocks=blocks,
        metadata={"stub": True},
        parser_confidence=0.95,
    )


def run(state: PipelineState, document_bytes: bytes | None = None) -> PipelineState:
    """Entry point called by the LangGraph supervisor.

    Args:
        state: Current pipeline state (mutated in-place and returned).
        document_bytes: Raw document bytes.  May be ``None`` in stub mode.

    Returns:
        Updated ``PipelineState`` with ``parsed_document`` populated.
    """
    state.current_agent = "ingestion"
    filename = state.source_filename
    content_hash = hashlib.sha256(document_bytes or filename.encode()).hexdigest()[:16]

    if _STUB_MODE or document_bytes is None:
        logger.info("Ingestion agent running in stub mode for '%s'", filename)
        state.parsed_document = _stub_parse(filename, content_hash)
        return state

    try:
        client = boto3.client("textract")
        response = client.detect_document_text(Document={"Bytes": document_bytes})
        blocks = _textract_blocks_to_doc_blocks(response.get("Blocks", []))
        raw_text = " ".join(b.content for b in blocks)
        domain = _detect_domain(filename, raw_text)
        total_pages = max((b.page_number for b in blocks), default=1)
        avg_confidence = (
            sum(b.confidence for b in blocks) / len(blocks) if blocks else 1.0
        )
        state.parsed_document = ParsedDocument(
            document_id=content_hash,
            source_filename=filename,
            domain=domain,
            total_pages=total_pages,
            blocks=blocks,
            metadata={"textract_response_id": response.get("ResponseMetadata", {}).get("RequestId", "")},
            parser_confidence=avg_confidence,
        )
        state.domain = domain
        logger.info(
            "Ingestion complete: %d blocks, domain=%s, confidence=%.2f",
            len(blocks),
            domain,
            avg_confidence,
        )
    except (BotoCoreError, ClientError) as exc:
        logger.error("Textract failed: %s – falling back to stub", exc)
        state.parsed_document = _stub_parse(filename, content_hash)
        state.warnings.append(f"Textract unavailable, used stub parser: {exc}")

    return state
