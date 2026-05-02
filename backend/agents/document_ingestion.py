"""
Agent 1: Document Ingestion & Parsing

Combines AWS Textract (OCR + layout) with Claude structured output for
procedural element extraction. Falls back to Docling for complex tables.

Input:  raw PDF bytes + domain hint
Output: ParsedDocument
"""
from __future__ import annotations

import io
import uuid
import logging
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from anthropic import Anthropic
from pydantic import ValidationError

from backend.models.schemas import (
    DocumentBlock,
    DocumentDomain,
    BoundingBox,
    ParsedDocument,
)

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-3-7-sonnet-20250219"


class DocumentIngestionAgent:
    """
    Ingests a PDF and returns a ParsedDocument.

    Steps:
    1. Upload to S3 (if not already there)
    2. Run AWS Textract async job
    3. Post-process with Claude for semantic block typing
    4. Fall back to Docling if Textract table confidence < 0.7
    """

    def __init__(
        self,
        s3_bucket: str,
        aws_region: str = "ap-southeast-2",
        use_docling_fallback: bool = True,
    ):
        self.s3_bucket = s3_bucket
        self.textract = boto3.client("textract", region_name=aws_region)
        self.s3 = boto3.client("s3", region_name=aws_region)
        self.claude = Anthropic()
        self.use_docling_fallback = use_docling_fallback

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, pdf_bytes: bytes, filename: str, domain: DocumentDomain) -> ParsedDocument:
        doc_id = str(uuid.uuid4())
        s3_key = f"uploads/{doc_id}/{filename}"

        logger.info(f"[Agent1] Uploading {filename} → s3://{self.s3_bucket}/{s3_key}")
        self._upload_to_s3(pdf_bytes, s3_key)

        logger.info("[Agent1] Starting Textract analysis…")
        raw_blocks = self._run_textract(s3_key)

        logger.info("[Agent1] Enriching blocks with Claude…")
        typed_blocks = self._enrich_with_claude(raw_blocks, domain)

        # Docling fallback for tables with low confidence
        if self.use_docling_fallback:
            typed_blocks = self._docling_table_fallback(typed_blocks, pdf_bytes)

        raw_text = "\n".join(b.content for b in typed_blocks if b.block_type == "text")
        page_count = max((b.bbox.page for b in typed_blocks if b.bbox), default=1)
        avg_conf = sum(b.confidence for b in typed_blocks) / max(len(typed_blocks), 1)

        return ParsedDocument(
            doc_id=doc_id,
            filename=filename,
            domain=domain,
            page_count=page_count,
            blocks=typed_blocks,
            raw_text=raw_text,
            parse_confidence=round(avg_conf, 3),
            parser_used="textract+claude",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _upload_to_s3(self, pdf_bytes: bytes, s3_key: str) -> None:
        self.s3.put_object(
            Bucket=self.s3_bucket,
            Key=s3_key,
            Body=pdf_bytes,
            ContentType="application/pdf",
        )

    def _run_textract(self, s3_key: str) -> list[DocumentBlock]:
        """Start async Textract job and poll until complete."""
        response = self.textract.start_document_analysis(
            DocumentLocation={"S3Object": {"Bucket": self.s3_bucket, "Name": s3_key}},
            FeatureTypes=["TABLES", "FORMS", "LAYOUT"],
        )
        job_id = response["JobId"]

        import time
        while True:
            result = self.textract.get_document_analysis(JobId=job_id)
            status = result["JobStatus"]
            if status == "SUCCEEDED":
                break
            if status == "FAILED":
                raise RuntimeError(f"Textract job {job_id} failed")
            time.sleep(3)

        blocks: list[DocumentBlock] = []
        page_map: dict[str, int] = {}

        for block in result.get("Blocks", []):
            if block["BlockType"] == "PAGE":
                page_map[block["Id"]] = block.get("Page", 1)

        for block in result.get("Blocks", []):
            btype = block["BlockType"]
            if btype not in ("LINE", "TABLE", "FIGURE"):
                continue

            geo = block.get("Geometry", {}).get("BoundingBox", {})
            page = block.get("Page", 1)
            bbox = BoundingBox(
                x=geo.get("Left", 0) * 1000,
                y=geo.get("Top", 0) * 700,
                width=geo.get("Width", 0) * 1000,
                height=geo.get("Height", 0) * 700,
                page=page,
            )

            content = block.get("Text", "")
            if btype == "TABLE":
                content = "[TABLE]"  # will be enriched by Claude or Docling
            elif btype == "FIGURE":
                content = "[FIGURE]"

            blocks.append(
                DocumentBlock(
                    block_id=block["Id"],
                    block_type=btype.lower(),
                    content=content,
                    bbox=bbox,
                    confidence=block.get("Confidence", 100) / 100,
                )
            )

        return blocks

    def _enrich_with_claude(
        self, blocks: list[DocumentBlock], domain: DocumentDomain
    ) -> list[DocumentBlock]:
        """
        Ask Claude to re-type and clean blocks, identifying:
        - headers, procedure steps, safety warnings, tables, figures
        """
        text_sample = "\n".join(
            f"[{i}] {b.content[:200]}" for i, b in enumerate(blocks[:80])
        )
        prompt = f"""You are analysing a {domain.value} procedural document.
Classify each numbered block below as one of:
  header | procedure_step | safety_warning | table | figure | metadata | text

Return JSON array: [{{"index": 0, "block_type": "header", "cleaned_content": "..."}}]
Only return the JSON array, nothing else.

Blocks:
{text_sample}
"""
        message = self.claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        try:
            enrichments = json.loads(message.content[0].text)
            for item in enrichments:
                idx = item["index"]
                if 0 <= idx < len(blocks):
                    blocks[idx] = blocks[idx].model_copy(update={
                        "block_type": item.get("block_type", blocks[idx].block_type),
                        "content": item.get("cleaned_content", blocks[idx].content),
                    })
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning(f"[Agent1] Claude enrichment parse error: {e}")

        return blocks

    def _docling_table_fallback(
        self, blocks: list[DocumentBlock], pdf_bytes: bytes
    ) -> list[DocumentBlock]:
        """Replace low-confidence TABLE blocks with Docling-extracted tables."""
        low_conf_tables = [b for b in blocks if b.block_type == "table" and b.confidence < 0.7]
        if not low_conf_tables:
            return blocks

        try:
            from docling.document_converter import DocumentConverter
            converter = DocumentConverter()
            result = converter.convert_stream(io.BytesIO(pdf_bytes), mime_type="application/pdf")
            docling_tables = [
                t.export_to_markdown() for t in result.document.tables
            ]
            for i, block in enumerate(low_conf_tables):
                if i < len(docling_tables):
                    idx = next(j for j, b in enumerate(blocks) if b.block_id == block.block_id)
                    blocks[idx] = blocks[idx].model_copy(update={
                        "content": docling_tables[i],
                        "confidence": 0.9,
                    })
                    logger.info(f"[Agent1] Docling replaced table {block.block_id}")
        except ImportError:
            logger.warning("[Agent1] Docling not installed — skipping table fallback")
        except Exception as e:
            logger.warning(f"[Agent1] Docling fallback error: {e}")

        return blocks
