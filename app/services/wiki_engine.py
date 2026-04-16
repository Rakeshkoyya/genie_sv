"""Wiki engine — core CRUD operations, search, and link management."""

import logging
import re
import uuid
from datetime import datetime

from sqlalchemy import select, func, delete, text, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.wiki import (
    Wiki, WikiPage, WikiPageLink, WikiSourcePage, WikiLog,
    WikiPageType, WikiLogOperation,
)

logger = logging.getLogger(__name__)


def slugify(title: str) -> str:
    """Convert a page title to a URL-safe slug."""
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "untitled"


# ── Wiki CRUD ───────────────────────────────────────────────────────

async def get_or_create_wiki(
    db: AsyncSession,
    user_id: uuid.UUID,
    dataset_id: uuid.UUID,
    name: str | None = None,
) -> Wiki:
    """Return the wiki for a dataset, creating it if it doesn't exist."""
    stmt = select(Wiki).where(
        Wiki.user_id == user_id, Wiki.dataset_id == dataset_id
    )
    result = await db.execute(stmt)
    wiki = result.scalar_one_or_none()
    if wiki:
        return wiki

    wiki = Wiki(
        user_id=user_id,
        dataset_id=dataset_id,
        name=name or "Wiki",
        stats={"page_count": 0, "source_count": 0},
    )
    db.add(wiki)
    await db.flush()
    return wiki


async def get_wiki(db: AsyncSession, wiki_id: uuid.UUID) -> Wiki | None:
    stmt = select(Wiki).where(Wiki.id == wiki_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_wikis(db: AsyncSession, user_id: uuid.UUID) -> list[Wiki]:
    stmt = select(Wiki).where(Wiki.user_id == user_id).order_by(Wiki.updated_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_wiki(
    db: AsyncSession, wiki: Wiki, *, name: str | None = None,
    description: str | None = None, schema_config: dict | None = None,
) -> Wiki:
    if name is not None:
        wiki.name = name
    if description is not None:
        wiki.description = description
    if schema_config is not None:
        wiki.schema_config = schema_config
    await db.flush()
    return wiki


async def delete_wiki(db: AsyncSession, wiki: Wiki) -> None:
    await db.delete(wiki)
    await db.flush()


# ── Page CRUD ───────────────────────────────────────────────────────

async def create_page(
    db: AsyncSession,
    wiki_id: uuid.UUID,
    title: str,
    page_type: WikiPageType | str,
    content: str = "",
    frontmatter: dict | None = None,
    slug: str | None = None,
) -> WikiPage:
    if isinstance(page_type, str):
        try:
            page_type = WikiPageType(page_type)
        except ValueError:
            page_type = WikiPageType.entity
    if slug is None:
        slug = slugify(title)

    # Ensure slug uniqueness within wiki
    base_slug = slug
    counter = 1
    while True:
        exists = await db.execute(
            select(WikiPage.id).where(
                WikiPage.wiki_id == wiki_id, WikiPage.slug == slug
            )
        )
        if not exists.scalar_one_or_none():
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    page = WikiPage(
        wiki_id=wiki_id,
        title=title,
        slug=slug,
        page_type=page_type,
        content=content,
        frontmatter=frontmatter or {},
    )
    db.add(page)
    await db.flush()
    return page


async def get_page(db: AsyncSession, page_id: uuid.UUID) -> WikiPage | None:
    stmt = select(WikiPage).where(WikiPage.id == page_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_page_by_slug(
    db: AsyncSession, wiki_id: uuid.UUID, slug: str
) -> WikiPage | None:
    stmt = select(WikiPage).where(
        WikiPage.wiki_id == wiki_id, WikiPage.slug == slug
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_pages(
    db: AsyncSession,
    wiki_id: uuid.UUID,
    page_type: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[WikiPage], int]:
    base = select(WikiPage).where(WikiPage.wiki_id == wiki_id)
    count_q = select(func.count(WikiPage.id)).where(WikiPage.wiki_id == wiki_id)

    if page_type:
        base = base.where(WikiPage.page_type == page_type)
        count_q = count_q.where(WikiPage.page_type == page_type)

    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(
        base.order_by(WikiPage.title).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), total


async def update_page(
    db: AsyncSession,
    page: WikiPage,
    *,
    title: str | None = None,
    content: str | None = None,
    frontmatter: dict | None = None,
) -> WikiPage:
    if title is not None:
        page.title = title
        page.slug = slugify(title)
    if content is not None:
        page.content = content
    if frontmatter is not None:
        page.frontmatter = frontmatter
    page.updated_at = datetime.utcnow()
    await db.flush()
    return page


async def delete_page(db: AsyncSession, page: WikiPage) -> None:
    await db.delete(page)
    await db.flush()


# ── Full-text search ────────────────────────────────────────────────

async def search_pages(
    db: AsyncSession,
    wiki_id: uuid.UUID,
    query: str,
    page_type: str | None = None,
    limit: int = 20,
) -> list[WikiPage]:
    """Search wiki pages using PostgreSQL full-text search."""
    ts_query = func.plainto_tsquery("english", query)

    stmt = (
        select(WikiPage)
        .where(
            WikiPage.wiki_id == wiki_id,
            text("search_vector @@ plainto_tsquery('english', :q)")
        )
        .params(q=query)
        .order_by(
            text("ts_rank(search_vector, plainto_tsquery('english', :q)) DESC")
        )
        .params(q=query)
        .limit(limit)
    )

    if page_type:
        stmt = stmt.where(WikiPage.page_type == page_type)

    result = await db.execute(stmt)
    return list(result.scalars().all())


# ── Link management ─────────────────────────────────────────────────

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


async def sync_links_from_content(db: AsyncSession, page: WikiPage) -> int:
    """Parse [[wikilinks]] from page content and sync link records.

    Returns the number of links created.
    """
    # Delete existing outbound links for this page
    await db.execute(
        delete(WikiPageLink).where(WikiPageLink.source_page_id == page.id)
    )

    titles = WIKILINK_RE.findall(page.content)
    if not titles:
        return 0

    created = 0
    seen_targets: set[uuid.UUID] = set()
    for raw_title in titles:
        title = raw_title.strip()
        slug = slugify(title)
        target = await get_page_by_slug(db, page.wiki_id, slug)
        if target and target.id != page.id and target.id not in seen_targets:
            seen_targets.add(target.id)
            link = WikiPageLink(
                source_page_id=page.id,
                target_page_id=target.id,
                link_text=title,
            )
            db.add(link)
            created += 1

    await db.flush()
    return created


async def get_page_graph(
    db: AsyncSession, wiki_id: uuid.UUID
) -> dict:
    """Return graph data (nodes + edges) for visualisation."""
    pages, _ = await list_pages(db, wiki_id, limit=5000)

    links_stmt = (
        select(WikiPageLink)
        .join(WikiPage, WikiPageLink.source_page_id == WikiPage.id)
        .where(WikiPage.wiki_id == wiki_id)
    )
    links = list((await db.execute(links_stmt)).scalars().all())

    # Count inbound + outbound per page
    link_counts: dict[uuid.UUID, int] = {}
    for link in links:
        link_counts[link.source_page_id] = link_counts.get(link.source_page_id, 0) + 1
        link_counts[link.target_page_id] = link_counts.get(link.target_page_id, 0) + 1

    nodes = [
        {
            "id": str(p.id),
            "title": p.title,
            "slug": p.slug,
            "page_type": p.page_type.value if hasattr(p.page_type, "value") else p.page_type,
            "link_count": link_counts.get(p.id, 0),
        }
        for p in pages
    ]
    edges = [
        {
            "source": str(l.source_page_id),
            "target": str(l.target_page_id),
            "link_text": l.link_text,
        }
        for l in links
    ]
    return {"nodes": nodes, "edges": edges}


# ── Source-page mapping ─────────────────────────────────────────────

async def link_source_to_page(
    db: AsyncSession, source_id: uuid.UUID, page_id: uuid.UUID
) -> None:
    existing = await db.execute(
        select(WikiSourcePage).where(
            WikiSourcePage.source_id == source_id,
            WikiSourcePage.page_id == page_id,
        )
    )
    if not existing.scalar_one_or_none():
        db.add(WikiSourcePage(source_id=source_id, page_id=page_id))
        await db.flush()


# ── Wiki log ────────────────────────────────────────────────────────

async def append_log(
    db: AsyncSession,
    wiki_id: uuid.UUID,
    operation: WikiLogOperation | str,
    summary: str,
    details: dict | None = None,
) -> WikiLog:
    if isinstance(operation, str):
        operation = WikiLogOperation(operation)
    log = WikiLog(
        wiki_id=wiki_id,
        operation=operation,
        summary=summary,
        details=details or {},
    )
    db.add(log)
    await db.flush()
    return log


async def get_logs(
    db: AsyncSession,
    wiki_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[WikiLog], int]:
    count = (
        await db.execute(
            select(func.count(WikiLog.id)).where(WikiLog.wiki_id == wiki_id)
        )
    ).scalar() or 0

    result = await db.execute(
        select(WikiLog)
        .where(WikiLog.wiki_id == wiki_id)
        .order_by(WikiLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), count


# ── Stats helper ────────────────────────────────────────────────────

async def refresh_stats(db: AsyncSession, wiki: Wiki) -> None:
    """Recompute and persist wiki stats."""
    page_count = (
        await db.execute(
            select(func.count(WikiPage.id)).where(WikiPage.wiki_id == wiki.id)
        )
    ).scalar() or 0

    source_count = (
        await db.execute(
            select(func.count(func.distinct(WikiSourcePage.source_id)))
            .join(WikiPage, WikiSourcePage.page_id == WikiPage.id)
            .where(WikiPage.wiki_id == wiki.id)
        )
    ).scalar() or 0

    link_count = (
        await db.execute(
            select(func.count(WikiPageLink.id))
            .join(WikiPage, WikiPageLink.source_page_id == WikiPage.id)
            .where(WikiPage.wiki_id == wiki.id)
        )
    ).scalar() or 0

    wiki.stats = {
        **wiki.stats,
        "page_count": page_count,
        "source_count": source_count,
        "link_count": link_count,
    }
    await db.flush()


# ── Index page ──────────────────────────────────────────────────────

async def regenerate_index_page(db: AsyncSession, wiki: Wiki) -> WikiPage:
    """Create or update the wiki's index page from all existing pages."""
    pages, _ = await list_pages(db, wiki.id, limit=5000)

    # Group by type
    by_type: dict[str, list[WikiPage]] = {}
    for p in pages:
        ptype = p.page_type.value if hasattr(p.page_type, "value") else p.page_type
        if ptype == "index":
            continue
        by_type.setdefault(ptype, []).append(p)

    lines = [f"# {wiki.name} — Index\n"]
    type_labels = {
        "overview": "Overview",
        "source_summary": "Source Summaries",
        "entity": "Entities",
        "concept": "Concepts",
        "topic_summary": "Topic Summaries",
        "comparison": "Comparisons",
        "analysis": "Analyses",
    }
    for ptype in ["overview", "source_summary", "entity", "concept", "topic_summary", "comparison", "analysis"]:
        group = by_type.get(ptype, [])
        if not group:
            continue
        lines.append(f"\n## {type_labels.get(ptype, ptype.title())}\n")
        for p in sorted(group, key=lambda x: x.title):
            tags = p.frontmatter.get("tags", [])
            tag_str = f" — {', '.join(tags)}" if tags else ""
            lines.append(f"- [[{p.title}]]{tag_str}")

    content = "\n".join(lines)

    index = await get_page_by_slug(db, wiki.id, "index")
    if index:
        index.content = content
        index.updated_at = datetime.utcnow()
        await db.flush()
        return index

    return await create_page(
        db, wiki.id, f"{wiki.name} — Index", WikiPageType.index, content, slug="index"
    )
