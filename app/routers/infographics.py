"""Infographics generation router with SSE streaming."""

import base64
import json
import logging
import time
from textwrap import dedent
from uuid import UUID
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from pydantic import BaseModel

from app.dependencies import DbSession, ApprovedUser
from app.models.source import InputSource
from app.models.export import ExportedDocument, ExportFormat
from app.services.llm import LLMService, call_llm
from app.services.storage import StorageService
from app.utils.prompt_builder import format_sources_text
from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/genie/infographics", tags=["Infographics"])
settings = get_settings()


class InfographicsRequest(BaseModel):
    source_ids: list[UUID] = []
    dataset_id: UUID | None = None
    model: str = settings.openrouter_model
    dimension_id: str = "1:1"
    style: str = "professional"
    detail_level: str = "standard"
    filename: str = "infographic"


DIMENSIONS = {
    "1:1":  {"width": 1024, "height": 1024, "label": "Square (1:1)"},
    "16:9": {"width": 1344, "height": 768,  "label": "Widescreen (16:9)"},
    "9:16": {"width": 768,  "height": 1344, "label": "Portrait (9:16)"},
    "4:3":  {"width": 1184, "height": 864,  "label": "Standard (4:3)"},
    "3:2":  {"width": 1248, "height": 832,  "label": "Photo (3:2)"},
}

IMAGE_MODELS = list(dict.fromkeys(m for m in [
    settings.openrouter_image_model,
    "google/gemini-3.1-flash-image-preview",
] if m))


def _extract_image_data_url(response) -> str | None:
    """Extract a data-URL from the LLM response.

    Gemini image models return a list:
        [{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}]
    """
    if isinstance(response, list):
        for part in response:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "image_url":
                url_obj = part.get("image_url", {})
                url = url_obj.get("url", "") if isinstance(url_obj, dict) else url_obj
                if isinstance(url, str) and url.startswith("data:image/"):
                    return url
    if isinstance(response, str) and response.startswith("data:image/"):
        return response
    return None


def _decode_data_url(data_url: str) -> tuple[bytes, str]:
    """Decode a data-URL into (bytes, mime_type)."""
    header, payload = data_url.split(",", 1)
    mime_type = header.split(":")[1].split(";")[0]
    return base64.b64decode(payload), mime_type


async def _generate_image(prompt: str) -> tuple[bytes, str, str, str]:
    """Try each image model until one returns an image.

    Returns (image_bytes, mime_type, data_url, model_used).
    """
    errors: list[str] = []
    for model in IMAGE_MODELS:
        try:
            logger.info("Trying image model: %s", model)
            raw = await call_llm(prompt=prompt, model=model)
            data_url = _extract_image_data_url(raw)
            if not data_url:
                logger.warning("%s returned no image. Response type=%s, preview=%s",
                               model, type(raw).__name__, str(raw)[:200])
                errors.append(f"{model}: no image in response")
                continue
            image_bytes, mime = _decode_data_url(data_url)
            logger.info("Image generated with %s (%d bytes, %s)", model, len(image_bytes), mime)
            return image_bytes, mime, data_url, model
        except Exception as exc:
            logger.error("Image model %s failed: %s", model, exc)
            errors.append(f"{model}: {exc}")
    raise ValueError("All image models failed — " + " | ".join(errors))


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def generate_infographic_stream(
    user_id: UUID,
    sources_text: str,
    media_parts: list[dict],
    request: InfographicsRequest,
    db,
) -> AsyncGenerator[str, None]:
    """Three-step pipeline: summarise → design prompt → generate image."""
    llm = LLMService()
    storage = StorageService()
    text_model = request.model or settings.openrouter_model
    dimension = DIMENSIONS.get(request.dimension_id, DIMENSIONS["1:1"])

    logger.info("Starting infographic: text_model=%s, sources_text=%d chars, media_parts=%d",
                text_model, len(sources_text), len(media_parts))

    try:
        # ── Step 1: Summarise sources ───────────────────────────────
        yield _sse({"step": 1, "message": "Analyzing content…"})

        summary = await llm.generate(
            sources=sources_text,
            media_parts=media_parts or None,
            prompt=dedent("""\
                Create a complete recall summary of the provided source content.
                Include ALL major topics, subtopics, and key points.

                Structure:
                1) Main Topics
                2) Key Points by Topic
                3) Critical Facts and Numbers
                4) Relationships between topics
                5) Final Snapshot for quick recall

                Be accurate, specific, and complete."""),
            model=text_model,
        )
        logger.info("Summary generated (%d chars)", len(summary))
        yield _sse({"step": 1, "message": "Content analyzed", "complete": True})

        # ── Step 2: Generate image prompt ───────────────────────────
        yield _sse({"step": 2, "message": "Designing infographic…"})

        design_prompt = await llm.generate(
            sources="",
            prompt=dedent(f"""\
                You are an expert in visualization of complex concepts.
                Convert the summary below into an image-generation prompt for
                an infographic that uses graphical drawings and text labels.

                Summary:
                {summary}

                Constraints — Style: {request.style}, Detail: {request.detail_level},
                Canvas: {dimension['width']}×{dimension['height']} ({dimension['label']}).

                Requirements:
                1) Layout, sections, and information hierarchy
                2) Graphics/icons/diagrams for each main topic
                3) Textual overlays (titles, callouts, labels) with key facts
                4) Visual storytelling — easy to recall
                5) All main topics from the summary must appear

                Output only the final image-generation prompt."""),
            model=text_model,
        )
        yield _sse({"step": 2, "message": "Design ready", "complete": True})

        # ── Step 3: Generate image ──────────────────────────────────
        yield _sse({"step": 3, "message": "Generating infographic image…"})

        image_bytes, image_mime, image_data_url, image_model = await _generate_image(
            dedent(f"""\
                Generate a single infographic image based on this description:

                {design_prompt}

                Dimensions: {dimension['width']}×{dimension['height']}.""")
        )
        yield _sse({"step": 3, "message": "Image generated", "complete": True})

        # ── Step 4: Store ───────────────────────────────────────────
        yield _sse({"step": 4, "message": "Saving…"})

        filename = f"{request.filename}.png"
        storage_path = f"{user_id}/{int(time.time() * 1000)}_{filename}"

        await storage.upload(settings.exports_bucket, storage_path, image_bytes, image_mime)

        export = ExportedDocument(
            user_id=user_id,
            dataset_id=request.dataset_id,
            format=ExportFormat.png,
            storage_path=storage_path,
            filename=filename,
            file_size=len(image_bytes),
        )
        db.add(export)
        await db.commit()
        await db.refresh(export)

        yield _sse({"step": 4, "message": "Saved", "complete": True, "export_id": str(export.id)})

        # ── Final event (consumed by frontend) ─────────────────────
        yield _sse({
            "complete": True,
            "export_id": str(export.id),
            "filename": filename,
            "image_url": image_data_url,
            "summary": summary,
            "image_prompt": design_prompt,
            "text_model": text_model,
            "image_model": image_model,
        })

    except Exception as e:
        logger.exception("Infographic generation failed")
        yield _sse({"error": str(e)})


@router.post("")
async def generate_infographic(
    data: InfographicsRequest,
    user: ApprovedUser,
    db: DbSession,
):
    """Generate an infographic from sources using SSE streaming."""
    storage = StorageService()
    source_texts = []
    media_parts: list[dict] = []

    if data.source_ids:
        result = await db.execute(
            select(InputSource).where(
                InputSource.id.in_(data.source_ids),
                InputSource.user_id == user.id,
            )
        )
        for source in result.scalars().all():
            # Always include extracted text when available
            if source.extracted_text:
                source_texts.append({"name": source.name, "extracted_text": source.extracted_text})

            # For PDFs/images, also attach the raw file as base64 so the LLM
            # can read scanned / image-based documents directly.
            if source.storage_path and source.type in ("pdf", "image"):
                try:
                    file_bytes = await storage.download(settings.input_files_bucket, source.storage_path)
                    b64 = base64.b64encode(file_bytes).decode()
                    if source.type == "pdf":
                        # OpenRouter expects 'file' content type for PDFs
                        media_parts.append({
                            "type": "file",
                            "file": {"filename": source.name, "file_data": f"data:application/pdf;base64,{b64}"},
                        })
                    else:
                        media_parts.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        })
                    logger.info("Attached source %s (%s, %d bytes)", source.name, source.type, len(file_bytes))
                except Exception as exc:
                    logger.warning("Could not download source %s: %s", source.name, exc)

    if not source_texts and not media_parts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No source content available")

    return StreamingResponse(
        generate_infographic_stream(user.id, format_sources_text(source_texts), media_parts, data, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
