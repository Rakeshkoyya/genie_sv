"""Wiki API router — CRUD, agent operations, transformations, logs."""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func

from app.dependencies import DbSession, ApprovedUser
from app.models.source import InputSource
from app.models.wiki import Wiki, WikiPage, WikiTransformation
from app.schemas.wiki import (
    WikiCreate, WikiUpdate, WikiRead, WikiListResponse,
    WikiPageCreate, WikiPageUpdate, WikiPageRead, WikiPageListResponse,
    WikiGraphResponse,
    WikiIngestRequest, WikiQueryRequest, WikiQueryResponse,
    WikiLintReport,
    WikiTransformRequest, WikiTransformationRead, WikiTransformationListResponse,
    WikiLogRead, WikiLogListResponse,
)
from app.services import wiki_engine as engine
from app.services import wiki_agent as agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wikis", tags=["Wiki"])


# ═══════════════════════════════════════════════════════════════════
# Wiki CRUD
# ═══════════════════════════════════════════════════════════════════

@router.get("", response_model=WikiListResponse)
async def list_wikis(db: DbSession, user: ApprovedUser):
    wikis = await engine.list_wikis(db, user.id)
    return WikiListResponse(wikis=[WikiRead.model_validate(w) for w in wikis], total=len(wikis))


@router.post("", response_model=WikiRead, status_code=status.HTTP_201_CREATED)
async def create_wiki(body: WikiCreate, db: DbSession, user: ApprovedUser):
    wiki = await engine.get_or_create_wiki(
        db, user.id, body.dataset_id, name=body.name,
    )
    if body.description:
        wiki.description = body.description
    if body.schema_config:
        wiki.schema_config = body.schema_config
    await db.commit()
    await db.refresh(wiki)
    return WikiRead.model_validate(wiki)


@router.get("/{wiki_id}", response_model=WikiRead)
async def get_wiki(wiki_id: UUID, db: DbSession, user: ApprovedUser):
    wiki = await _get_user_wiki(db, wiki_id, user.id)
    return WikiRead.model_validate(wiki)


@router.put("/{wiki_id}", response_model=WikiRead)
async def update_wiki(wiki_id: UUID, body: WikiUpdate, db: DbSession, user: ApprovedUser):
    wiki = await _get_user_wiki(db, wiki_id, user.id)
    await engine.update_wiki(
        db, wiki, name=body.name, description=body.description,
        schema_config=body.schema_config,
    )
    await db.commit()
    await db.refresh(wiki)
    return WikiRead.model_validate(wiki)


@router.delete("/{wiki_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wiki(wiki_id: UUID, db: DbSession, user: ApprovedUser):
    wiki = await _get_user_wiki(db, wiki_id, user.id)
    await engine.delete_wiki(db, wiki)
    await db.commit()


# ═══════════════════════════════════════════════════════════════════
# Pages
# ═══════════════════════════════════════════════════════════════════

@router.get("/{wiki_id}/pages", response_model=WikiPageListResponse)
async def list_pages(
    wiki_id: UUID,
    db: DbSession,
    user: ApprovedUser,
    page_type: str | None = None,
    q: str | None = None,
    limit: int = Query(200, le=1000),
    offset: int = 0,
):
    await _get_user_wiki(db, wiki_id, user.id)

    if q:
        pages = await engine.search_pages(db, wiki_id, q, page_type=page_type, limit=limit)
        return WikiPageListResponse(
            pages=[WikiPageRead.model_validate(p) for p in pages],
            total=len(pages),
        )

    pages, total = await engine.list_pages(db, wiki_id, page_type=page_type, limit=limit, offset=offset)
    return WikiPageListResponse(
        pages=[WikiPageRead.model_validate(p) for p in pages],
        total=total,
    )


@router.get("/{wiki_id}/pages/{page_id}", response_model=WikiPageRead)
async def get_page(wiki_id: UUID, page_id: UUID, db: DbSession, user: ApprovedUser):
    await _get_user_wiki(db, wiki_id, user.id)
    page = await engine.get_page(db, page_id)
    if not page or page.wiki_id != wiki_id:
        raise HTTPException(status_code=404, detail="Page not found")
    return WikiPageRead.model_validate(page)


@router.put("/{wiki_id}/pages/{page_id}", response_model=WikiPageRead)
async def update_page(
    wiki_id: UUID, page_id: UUID, body: WikiPageUpdate,
    db: DbSession, user: ApprovedUser,
):
    await _get_user_wiki(db, wiki_id, user.id)
    page = await engine.get_page(db, page_id)
    if not page or page.wiki_id != wiki_id:
        raise HTTPException(status_code=404, detail="Page not found")
    await engine.update_page(db, page, title=body.title, content=body.content, frontmatter=body.frontmatter)
    if body.content is not None:
        await engine.sync_links_from_content(db, page)
    await db.commit()
    await db.refresh(page)
    return WikiPageRead.model_validate(page)


@router.delete("/{wiki_id}/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_page(wiki_id: UUID, page_id: UUID, db: DbSession, user: ApprovedUser):
    wiki = await _get_user_wiki(db, wiki_id, user.id)
    page = await engine.get_page(db, page_id)
    if not page or page.wiki_id != wiki_id:
        raise HTTPException(status_code=404, detail="Page not found")
    await engine.delete_page(db, page)
    await engine.refresh_stats(db, wiki)
    await db.commit()


@router.get("/{wiki_id}/graph", response_model=WikiGraphResponse)
async def get_graph(wiki_id: UUID, db: DbSession, user: ApprovedUser):
    await _get_user_wiki(db, wiki_id, user.id)
    graph = await engine.get_page_graph(db, wiki_id)
    return WikiGraphResponse(**graph)


# ═══════════════════════════════════════════════════════════════════
# Agent Operations
# ═══════════════════════════════════════════════════════════════════

@router.post("/{wiki_id}/ingest")
async def ingest_source(
    wiki_id: UUID,
    body: WikiIngestRequest,
    db: DbSession,
    user: ApprovedUser,
):
    wiki = await _get_user_wiki(db, wiki_id, user.id)
    source = await _get_user_source(db, body.source_id, user.id)

    return StreamingResponse(
        agent.ingest_source(db, wiki, source, model=body.model),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{wiki_id}/query", response_model=WikiQueryResponse)
async def query_wiki(
    wiki_id: UUID,
    body: WikiQueryRequest,
    db: DbSession,
    user: ApprovedUser,
):
    wiki = await _get_user_wiki(db, wiki_id, user.id)
    result = await agent.query_wiki(
        db, wiki, body.question, model=body.model, file_as_page=body.file_as_page,
    )
    return WikiQueryResponse(
        answer=result["answer"],
        cited_pages=[WikiPageRead.model_validate(p) for p in result["cited_pages"]],
        filed_page=WikiPageRead.model_validate(result["filed_page"]) if result.get("filed_page") else None,
    )


@router.post("/{wiki_id}/lint", response_model=WikiLintReport)
async def lint_wiki(wiki_id: UUID, db: DbSession, user: ApprovedUser):
    wiki = await _get_user_wiki(db, wiki_id, user.id)
    report = await agent.lint_wiki(db, wiki)
    return WikiLintReport(**report)


@router.post("/{wiki_id}/transform", response_model=WikiTransformationRead)
async def transform_wiki(
    wiki_id: UUID,
    body: WikiTransformRequest,
    db: DbSession,
    user: ApprovedUser,
):
    wiki = await _get_user_wiki(db, wiki_id, user.id)
    transformation = await agent.transform_content(
        db, wiki,
        transformation_type=body.transformation_type,
        title=body.title,
        scope=body.scope,
        config=body.config,
        model=body.model,
    )
    return WikiTransformationRead.model_validate(transformation)


# ═══════════════════════════════════════════════════════════════════
# Transformations
# ═══════════════════════════════════════════════════════════════════

@router.get("/{wiki_id}/transformations", response_model=WikiTransformationListResponse)
async def list_transformations(
    wiki_id: UUID, db: DbSession, user: ApprovedUser,
    transformation_type: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    await _get_user_wiki(db, wiki_id, user.id)
    stmt = select(WikiTransformation).where(WikiTransformation.wiki_id == wiki_id)
    count_stmt = select(func.count(WikiTransformation.id)).where(WikiTransformation.wiki_id == wiki_id)

    if transformation_type:
        stmt = stmt.where(WikiTransformation.transformation_type == transformation_type)
        count_stmt = count_stmt.where(WikiTransformation.transformation_type == transformation_type)

    total = (await db.execute(count_stmt)).scalar() or 0
    result = await db.execute(
        stmt.order_by(WikiTransformation.created_at.desc()).limit(limit).offset(offset)
    )
    items = list(result.scalars().all())
    return WikiTransformationListResponse(
        transformations=[WikiTransformationRead.model_validate(t) for t in items],
        total=total,
    )


@router.get("/{wiki_id}/transformations/{transformation_id}", response_model=WikiTransformationRead)
async def get_transformation(
    wiki_id: UUID, transformation_id: UUID, db: DbSession, user: ApprovedUser,
):
    await _get_user_wiki(db, wiki_id, user.id)
    result = await db.execute(
        select(WikiTransformation).where(
            WikiTransformation.id == transformation_id,
            WikiTransformation.wiki_id == wiki_id,
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Transformation not found")
    return WikiTransformationRead.model_validate(t)


@router.delete("/{wiki_id}/transformations/{transformation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transformation(
    wiki_id: UUID, transformation_id: UUID, db: DbSession, user: ApprovedUser,
):
    await _get_user_wiki(db, wiki_id, user.id)
    result = await db.execute(
        select(WikiTransformation).where(
            WikiTransformation.id == transformation_id,
            WikiTransformation.wiki_id == wiki_id,
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Transformation not found")
    await db.delete(t)
    await db.commit()


# ═══════════════════════════════════════════════════════════════════
# Logs
# ═══════════════════════════════════════════════════════════════════

@router.get("/{wiki_id}/logs", response_model=WikiLogListResponse)
async def list_logs(
    wiki_id: UUID, db: DbSession, user: ApprovedUser,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    await _get_user_wiki(db, wiki_id, user.id)
    logs, total = await engine.get_logs(db, wiki_id, limit=limit, offset=offset)
    return WikiLogListResponse(
        logs=[WikiLogRead.model_validate(l) for l in logs],
        total=total,
    )


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

async def _get_user_wiki(db: DbSession, wiki_id: UUID, user_id) -> Wiki:
    wiki = await engine.get_wiki(db, wiki_id)
    if not wiki or wiki.user_id != user_id:
        raise HTTPException(status_code=404, detail="Wiki not found")
    return wiki


async def _get_user_source(db: DbSession, source_id: UUID, user_id) -> InputSource:
    result = await db.execute(
        select(InputSource).where(InputSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    if not source or source.user_id != user_id:
        raise HTTPException(status_code=404, detail="Source not found")
    return source
