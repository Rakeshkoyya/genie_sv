"""Wiki agent — LLM-powered agentic operations: ingest, query, lint, transform."""

import json
import logging
import re
import time
import uuid
from datetime import datetime
from textwrap import dedent
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.config import get_settings
from app.models.source import InputSource
from app.models.wiki import (
    Wiki, WikiPage, WikiPageLink, WikiSourcePage,
    WikiPageType, WikiLogOperation,
    WikiTransformation, WikiTransformationType, WikiTransformationStatus,
)
from app.services.llm import call_llm
from app.services import wiki_engine as engine

logger = logging.getLogger(__name__)
settings = get_settings()


# ═══════════════════════════════════════════════════════════════════
# LLM helper
# ═══════════════════════════════════════════════════════════════════

async def _ask_llm(prompt: str, model: str | None = None) -> str:
    """Simple text-in / text-out LLM call."""
    model = model or settings.openrouter_model
    result = await call_llm(prompt=prompt, model=model)
    if isinstance(result, list):
        return str(result)
    return result


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ═══════════════════════════════════════════════════════════════════
# INGEST — source → wiki pages
# ═══════════════════════════════════════════════════════════════════

INGEST_ANALYZE_PROMPT = dedent("""\
You are an expert content analyst. You will be given the full text of a source document.
Analyze it and return a JSON object (no markdown fences) with exactly this structure:

{{
  "content_type": "academic|narrative|technical|legal|business|general",
  "title": "A concise title for this source",
  "summary": "A comprehensive 3-5 paragraph summary of the entire document",
  "topics": [
    {{
      "name": "Topic Name",
      "description": "One-line description",
      "subtopics": ["Sub 1", "Sub 2"]
    }}
  ],
  "entities": [
    {{
      "name": "Entity Name",
      "type": "person|place|concept|term|formula|date|organisation|event",
      "description": "One-line description",
      "related_to": ["Other Entity Name"]
    }}
  ],
  "key_facts": ["Fact 1", "Fact 2"],
  "relationships": [
    {{
      "from": "Entity/Topic A",
      "to": "Entity/Topic B",
      "relation": "describes how they relate"
    }}
  ]
}}

Be exhaustive — do NOT omit topics, entities, or facts. This will be used to build a
knowledge wiki, so completeness matters more than brevity.

SOURCE DOCUMENT:
{source_text}
""")

INGEST_PAGE_PLAN_PROMPT = dedent("""\
You are a wiki architect. Given an analysis of a source document AND a list of existing
wiki pages, decide which pages to CREATE and which to UPDATE.

Rules:
- Create a "source_summary" page for this source.
- For each important entity, create or update an "entity" page.
- For each major topic, create or update a "concept" page.
- If there is a natural high-level overview, create or update the "overview" page.
- Add [[Wikilinks]] to related pages inside the content.
- Use markdown format (not HTML or XML).
- Each page's content should be self-contained and thorough.

Return a JSON object (no markdown fences):
{{
  "pages": [
    {{
      "action": "create" | "update",
      "slug": "page-slug",
      "title": "Page Title",
      "page_type": "entity|concept|source_summary|topic_summary|overview",
      "content": "Full markdown content of the page with [[Wikilinks]]",
      "tags": ["tag1", "tag2"],
      "update_reason": "Only if action=update — what changed"
    }}
  ]
}}

EXISTING WIKI PAGES:
{existing_pages}

SOURCE ANALYSIS:
{analysis}

SOURCE TITLE: {source_name}
""")


async def ingest_source(
    db: AsyncSession,
    wiki: Wiki,
    source: InputSource,
    model: str | None = None,
) -> AsyncGenerator[str, None]:
    """Multi-step ingest pipeline. Yields SSE events."""
    start = time.time()
    model = model or settings.openrouter_model
    source_text = source.extracted_text or ""

    if not source_text.strip():
        yield _sse({"step": "error", "message": "Source has no extracted text."})
        return

    # ── Step 1: Analyze ─────────────────────────────────────────
    yield _sse({"step": "analyzing", "message": "Analyzing source content…"})

    analysis_raw = await _ask_llm(
        INGEST_ANALYZE_PROMPT.format(source_text=source_text[:80_000]),
        model=model,
    )
    try:
        analysis = _parse_json(analysis_raw)
    except Exception:
        logger.warning("Failed to parse analysis JSON, using raw text")
        analysis = {"summary": analysis_raw, "topics": [], "entities": []}

    yield _sse({"step": "analyzing", "message": "Analysis complete", "complete": True})

    # ── Step 2: Plan pages ──────────────────────────────────────
    yield _sse({"step": "planning", "message": "Planning wiki pages…"})

    existing_pages, _ = await engine.list_pages(db, wiki.id, limit=5000)
    existing_info = json.dumps(
        [{"slug": p.slug, "title": p.title, "page_type": p.page_type.value}
         for p in existing_pages],
        indent=2,
    )

    plan_raw = await _ask_llm(
        INGEST_PAGE_PLAN_PROMPT.format(
            existing_pages=existing_info,
            analysis=json.dumps(analysis, indent=2),
            source_name=source.name,
        ),
        model=model,
    )
    try:
        plan = _parse_json(plan_raw)
    except Exception:
        logger.warning("Failed to parse page plan JSON, creating summary only")
        plan = {
            "pages": [{
                "action": "create",
                "slug": engine.slugify(source.name),
                "title": f"Summary: {source.name}",
                "page_type": "source_summary",
                "content": analysis.get("summary", analysis_raw),
                "tags": [],
            }]
        }

    yield _sse({"step": "planning", "message": f"Planned {len(plan.get('pages', []))} pages", "complete": True})

    # ── Step 3: Create / update pages ───────────────────────────
    pages_planned = plan.get("pages", [])
    created_ids: list[str] = []
    updated_ids: list[str] = []

    for i, page_spec in enumerate(pages_planned):
        action = page_spec.get("action", "create")
        slug = page_spec.get("slug", f"page-{i}")
        title = page_spec.get("title", slug)
        page_type = page_spec.get("page_type", "concept")
        content = page_spec.get("content", "")
        tags = page_spec.get("tags", [])

        yield _sse({
            "step": "creating_pages",
            "message": f"{'Updating' if action == 'update' else 'Creating'}: {title}",
            "progress": i + 1,
            "total": len(pages_planned),
        })

        if action == "update":
            existing = await engine.get_page_by_slug(db, wiki.id, slug)
            if existing:
                # Merge content — append new info under a heading
                merged = existing.content.rstrip() + f"\n\n---\n\n_Updated from: {source.name}_\n\n{content}"
                await engine.update_page(
                    db, existing, content=merged,
                    frontmatter={**existing.frontmatter, "tags": list(set(existing.frontmatter.get("tags", []) + tags)),
                                 "source_refs": existing.frontmatter.get("source_refs", []) + [source.name]},
                )
                await engine.link_source_to_page(db, source.id, existing.id)
                await engine.sync_links_from_content(db, existing)
                updated_ids.append(str(existing.id))
                continue

        page = await engine.create_page(
            db, wiki.id, title, page_type, content,
            frontmatter={"tags": tags, "source_refs": [source.name]},
            slug=slug,
        )
        await engine.link_source_to_page(db, source.id, page.id)
        await engine.sync_links_from_content(db, page)
        created_ids.append(str(page.id))

    yield _sse({"step": "creating_pages", "message": "Pages ready", "complete": True})

    # ── Step 4: Update index ────────────────────────────────────
    yield _sse({"step": "indexing", "message": "Updating index…"})
    await engine.regenerate_index_page(db, wiki)
    await engine.refresh_stats(db, wiki)
    yield _sse({"step": "indexing", "message": "Index updated", "complete": True})

    # ── Step 5: Log ─────────────────────────────────────────────
    duration_ms = int((time.time() - start) * 1000)
    await engine.append_log(
        db, wiki.id, WikiLogOperation.ingest,
        f"Ingested source: {source.name}",
        {
            "source_id": str(source.id),
            "source_name": source.name,
            "pages_created": created_ids,
            "pages_updated": updated_ids,
            "duration_ms": duration_ms,
            "model": model,
        },
    )
    await db.commit()

    yield _sse({
        "step": "done",
        "message": f"Ingested into {len(created_ids)} new + {len(updated_ids)} updated pages",
        "pages_created": len(created_ids),
        "pages_updated": len(updated_ids),
        "complete": True,
    })


# ═══════════════════════════════════════════════════════════════════
# QUERY — search wiki → synthesise answer
# ═══════════════════════════════════════════════════════════════════

QUERY_SYNTHESIZE_PROMPT = dedent("""\
You are a knowledgeable research assistant. Answer the user's question using ONLY the
wiki pages provided below. Cite pages using [[Page Title]] wikilinks.

If the answer is not fully covered by the wiki, say so and suggest what additional
sources might help.

WIKI PAGES:
{pages_content}

QUESTION:
{question}
""")


async def query_wiki(
    db: AsyncSession,
    wiki: Wiki,
    question: str,
    model: str | None = None,
    file_as_page: bool = False,
) -> dict:
    """Search wiki pages and synthesise an answer."""
    model = model or settings.openrouter_model

    # Search
    results = await engine.search_pages(db, wiki.id, question, limit=10)

    # If search returns nothing, fall back to all pages (small wiki)
    if not results:
        results, _ = await engine.list_pages(db, wiki.id, limit=30)

    pages_content = "\n\n---\n\n".join(
        f"## [[{p.title}]]\n\n{p.content}" for p in results
    )

    answer = await _ask_llm(
        QUERY_SYNTHESIZE_PROMPT.format(
            pages_content=pages_content,
            question=question,
        ),
        model=model,
    )

    filed_page = None
    if file_as_page:
        filed_page = await engine.create_page(
            db, wiki.id,
            title=f"Q: {question[:80]}",
            page_type=WikiPageType.analysis,
            content=f"**Question:** {question}\n\n**Answer:**\n\n{answer}",
            frontmatter={"tags": ["query-answer"], "question": question},
        )
        await engine.sync_links_from_content(db, filed_page)
        await engine.regenerate_index_page(db, wiki)

    await engine.append_log(
        db, wiki.id, WikiLogOperation.query,
        f"Query: {question[:100]}",
        {"question": question, "pages_searched": len(results), "filed_page_id": str(filed_page.id) if filed_page else None},
    )
    await db.commit()

    return {
        "answer": answer,
        "cited_pages": results,
        "filed_page": filed_page,
    }


# ═══════════════════════════════════════════════════════════════════
# LINT — health-check the wiki
# ═══════════════════════════════════════════════════════════════════

async def lint_wiki(db: AsyncSession, wiki: Wiki) -> dict:
    """Analyse wiki health: orphans, broken links, gaps."""
    pages, page_count = await engine.list_pages(db, wiki.id, limit=5000)
    slug_map = {p.slug: p for p in pages}
    page_ids = {p.id for p in pages}

    issues = []

    # Find orphan pages (no inbound links, not index/overview)
    for page in pages:
        if page.page_type in (WikiPageType.index, WikiPageType.overview):
            continue
        inbound = await db.execute(
            select(func.count(WikiPageLink.id)).where(
                WikiPageLink.target_page_id == page.id
            )
        )
        if (inbound.scalar() or 0) == 0:
            issues.append({
                "type": "orphan_page",
                "severity": "warning",
                "message": f"Page '{page.title}' has no inbound links",
                "page_id": str(page.id),
                "page_title": page.title,
                "suggestion": "Add [[wikilinks]] from related pages",
            })

    # Find broken wikilinks
    for page in pages:
        titles = engine.WIKILINK_RE.findall(page.content)
        for raw_title in titles:
            slug = engine.slugify(raw_title.strip())
            if slug not in slug_map:
                issues.append({
                    "type": "broken_link",
                    "severity": "error",
                    "message": f"Page '{page.title}' links to non-existent '[[{raw_title.strip()}]]'",
                    "page_id": str(page.id),
                    "page_title": page.title,
                    "suggestion": f"Create a page for '{raw_title.strip()}' or fix the link",
                })

    # Count links
    link_count = 0
    for page in pages:
        lc = await db.execute(
            select(func.count(WikiPageLink.id)).where(
                WikiPageLink.source_page_id == page.id
            )
        )
        link_count += lc.scalar() or 0

    orphan_count = sum(1 for i in issues if i["type"] == "orphan_page")

    summary = f"Wiki has {page_count} pages, {link_count} links, {orphan_count} orphans, {len(issues)} issues total."

    await engine.append_log(
        db, wiki.id, WikiLogOperation.lint, summary,
        {"issue_count": len(issues), "orphan_count": orphan_count},
    )
    await db.commit()

    return {
        "issues": issues,
        "summary": summary,
        "page_count": page_count,
        "link_count": link_count,
        "orphan_count": orphan_count,
    }


# ═══════════════════════════════════════════════════════════════════
# TRANSFORM — wiki content → different content forms
# ═══════════════════════════════════════════════════════════════════

TRANSFORMATION_PROMPTS: dict[str, str] = {
    "concept_map": dedent("""\
        Create a detailed concept map from the following wiki content.
        Return a JSON object with:
        {{
          "nodes": [{{"id": "n1", "label": "Concept", "type": "main|sub|detail"}}],
          "edges": [{{"from": "n1", "to": "n2", "label": "relationship"}}]
        }}
        Include ALL concepts and relationships. Be exhaustive.

        WIKI CONTENT:
        {content}"""),

    "qa_exercises": dedent("""\
        Create comprehensive questions and exercises from the following wiki content.
        Include multiple types:
        1. Short answer questions (10-15)
        2. Multiple choice questions (5-10)
        3. True/False questions (5-10)
        4. Fill in the blanks (5-10)
        5. Long answer / essay questions (3-5)
        6. Application/scenario-based questions (2-3)

        Group them by topic. Include an answer key at the end.
        Use markdown formatting.

        WIKI CONTENT:
        {content}"""),

    "story": dedent("""\
        Rewrite the following wiki content as an engaging narrative story.
        Use storytelling techniques: characters, scenes, tension, resolution.
        The factual content must remain accurate — you are teaching through story.
        Make it vivid and memorable. Use markdown formatting.

        WIKI CONTENT:
        {content}"""),

    "podcast_transcript": dedent("""\
        Convert the following wiki content into a podcast transcript between
        two hosts: Alex (the expert) and Sam (the curious learner).
        Make it conversational, engaging, with natural back-and-forth.
        Include an intro, topic segments, and a wrap-up.
        Format: **Alex:** / **Sam:** speaker tags.

        WIKI CONTENT:
        {content}"""),

    "video_script": dedent("""\
        Create a video script from the following wiki content.
        Include:
        - **INTRO** with hook
        - **SCENES** with [VISUAL] descriptions and [NARRATION] text
        - **TRANSITIONS** between topics
        - **OUTRO** with summary and call-to-action
        Use markdown formatting.

        WIKI CONTENT:
        {content}"""),

    "flashcards": dedent("""\
        Create spaced-repetition flashcards from the following wiki content.
        Return a JSON array:
        [
          {{"front": "Question or prompt", "back": "Answer", "tags": ["topic1"], "difficulty": "easy|medium|hard"}}
        ]
        Create 30-50 cards covering ALL topics comprehensively.
        Mix factual recall, conceptual understanding, and application.

        WIKI CONTENT:
        {content}"""),

    "quiz": dedent("""\
        Create a comprehensive quiz from the following wiki content.
        Include:
        1. Multiple Choice (10 questions, 4 options each, mark correct with ✓)
        2. True or False (10 questions)
        3. Short Answer (5 questions)
        4. Match the Following (5 pairs)

        Include a separate ANSWER KEY section at the end.
        Use markdown formatting.

        WIKI CONTENT:
        {content}"""),

    "slide_deck": dedent("""\
        Create a presentation slide deck in Marp-compatible markdown from
        the following wiki content.

        Use `---` to separate slides. Include:
        - Title slide
        - Agenda/overview slide
        - One slide per major topic (with bullet points, NOT paragraphs)
        - Diagram/visual description slides (describe what should be shown)
        - Summary slide
        - Q&A slide

        Keep text concise — max 5 bullet points per slide, max 8 words per point.

        WIKI CONTENT:
        {content}"""),

    "mind_map": dedent("""\
        Create a hierarchical mind map from the following wiki content.
        Return a JSON object:
        {{
          "root": "Central Topic",
          "children": [
            {{
              "label": "Branch 1",
              "children": [
                {{"label": "Sub-item", "children": []}}
              ]
            }}
          ]
        }}
        Be exhaustive — include ALL topics, subtopics, and key details.

        WIKI CONTENT:
        {content}"""),

    "character_story": dedent("""\
        Teach the following wiki content through a character-driven story.
        Create a protagonist who learns about these topics through their journey.
        Make each topic a chapter/episode in their adventure.
        Keep all facts accurate. Use vivid descriptions and dialogue.
        Use markdown formatting with chapter headings.

        WIKI CONTENT:
        {content}"""),

    "advanced_summary": dedent("""\
        Create a multi-level summary of the following wiki content:

        ## Executive Summary (2-3 sentences)
        ## Key Takeaways (5-7 bullet points)
        ## Detailed Summary (comprehensive, organized by topic)
        ## Critical Analysis (strengths, weaknesses, gaps in the content)
        ## Connections & Implications (how topics relate to each other and broader context)

        Use markdown formatting.

        WIKI CONTENT:
        {content}"""),

    "comparison_table": dedent("""\
        Create comparison tables from the following wiki content.
        Identify all entities/concepts that can be meaningfully compared.
        For each comparison, create a markdown table with relevant attributes as rows.

        Format:
        ## Comparison: X vs Y
        | Attribute | X | Y |
        |-----------|---|---|
        | ... | ... | ... |

        Include as many comparisons as the content supports.

        WIKI CONTENT:
        {content}"""),
}


async def transform_content(
    db: AsyncSession,
    wiki: Wiki,
    transformation_type: str,
    title: str | None = None,
    scope: dict | None = None,
    config: dict | None = None,
    model: str | None = None,
) -> WikiTransformation:
    """Generate a content transformation from wiki pages."""
    model = model or settings.openrouter_model
    t_type = WikiTransformationType(transformation_type)
    scope = scope or {}
    config = config or {}

    # Gather scoped content
    page_ids = scope.get("page_ids", [])
    tags = scope.get("tags", [])
    query = scope.get("query", "")

    if page_ids:
        pages = []
        for pid in page_ids:
            p = await engine.get_page(db, uuid.UUID(pid))
            if p:
                pages.append(p)
    elif query:
        pages = await engine.search_pages(db, wiki.id, query, limit=20)
    elif tags:
        all_pages, _ = await engine.list_pages(db, wiki.id, limit=5000)
        pages = [p for p in all_pages if set(tags) & set(p.frontmatter.get("tags", []))]
    else:
        # Default: all non-index pages
        all_pages, _ = await engine.list_pages(db, wiki.id, limit=5000)
        pages = [p for p in all_pages if p.page_type != WikiPageType.index]

    content = "\n\n---\n\n".join(
        f"## {p.title}\n\n{p.content}" for p in pages
    )

    if not content.strip():
        raise ValueError("No wiki content found in the specified scope.")

    # Create transformation record
    auto_title = title or f"{t_type.value.replace('_', ' ').title()} — {wiki.name}"
    transformation = WikiTransformation(
        wiki_id=wiki.id,
        title=auto_title,
        transformation_type=t_type,
        scope=scope,
        config=config,
        status=WikiTransformationStatus.processing,
    )
    db.add(transformation)
    await db.flush()

    # Get the prompt template
    prompt_template = TRANSFORMATION_PROMPTS.get(transformation_type)
    if not prompt_template:
        transformation.status = WikiTransformationStatus.error
        transformation.error_message = f"Unknown transformation type: {transformation_type}"
        await db.commit()
        return transformation

    prompt = prompt_template.format(content=content[:100_000])

    try:
        result = await _ask_llm(prompt, model=model)
        transformation.content = result
        transformation.status = WikiTransformationStatus.completed
    except Exception as e:
        logger.error("Transform failed: %s", e)
        transformation.status = WikiTransformationStatus.error
        transformation.error_message = str(e)

    await engine.append_log(
        db, wiki.id, WikiLogOperation.transform,
        f"Generated {transformation_type}: {auto_title}",
        {
            "transformation_id": str(transformation.id),
            "type": transformation_type,
            "pages_used": len(pages),
            "model": model,
        },
    )
    await db.commit()
    return transformation


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _parse_json(text: str) -> dict:
    """Extract and parse the first JSON object from LLM output."""
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    text = re.sub(r"\n?```\s*$", "", text)
    # Find the first { ... } or [ ... ]
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == start_char:
                depth += 1
            elif text[i] == end_char:
                depth -= 1
                if depth == 0:
                    return json.loads(text[start:i + 1])
    return json.loads(text)
