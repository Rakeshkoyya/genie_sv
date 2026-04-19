"""DocAgent agentic orchestrator service.

4-step flow:
  1. Analyze  – parse source document, understand structure
  2. Plan     – LLM designs the output document layout and sections
  3. Generate – LLM produces structured JSON content per the plan
  4. Format   – formatter layer converts JSON → .docx
"""

import json
import logging
import re
from typing import Any

import httpx

from app.config import get_settings
from app.schemas.docagent import (
    AnalysisResult,
    DocumentSchema,
    PlanResult,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# ═══════════════════════════════════════════════════════════════════
#  System prompts for each agent step
# ═══════════════════════════════════════════════════════════════════

ANALYZE_SYSTEM_PROMPT = """You are a document analysis expert. Analyze the provided source document and return a JSON object with the following structure — nothing else:

{
  "document_type": "<type of document, e.g. report, textbook chapter, article, data sheet>",
  "key_topics": ["topic1", "topic2", ...],
  "structure_summary": "<brief description of how the source is organized>",
  "content_density": "<low | medium | high>",
  "recommended_sections": ["section name 1", "section name 2", ...],
  "total_length_estimate": "<short | medium | long>"
}

Be thorough in identifying all topics. Respond ONLY with valid JSON."""

PLAN_SYSTEM_PROMPT = """You are a world-class document architect specialising in ultra-compact, exam-ready study notes. Given:
1. An analysis of the source material
2. The user's request for what document to create
3. (Optional) class level, subject, and chapter number

Design a complete document plan. You MUST respond with ONLY valid JSON matching this schema:

{
  "document_title": "The title for the generated document",
  "document_subtitle": "Optional subtitle or null",
  "chapter_number": <integer chapter number or null>,
  "color_scheme": {
    "primary": "#hex color for level-1 headings",
    "secondary": "#hex color for level-2 headings",
    "accent": "#hex color for highlights and table headers",
    "text": "#hex for body text (usually dark gray/black)"
  },
  "sections": [
    {
      "section_number": 1,
      "heading": "Section Heading",
      "description": "What this section covers and how it should be written",
      "content_type": "narrative | table | list | mixed",
      "estimated_blocks": 5
    }
  ],
  "design_notes": "Overall design guidance — tone, density, visual style"
}

CRITICAL RULES:
- The ENTIRE document MUST fit in 3–5 pages. Plan accordingly — be ruthlessly concise.
- The color_scheme MUST use the exact hex values from the COLOR PALETTE provided in the user context — do NOT invent your own colors
- Plan sections that map to the source material's actual topic numbering (e.g. 3.1, 3.2, 3.3)
- Vary content types: use tables for comparisons/data, lists for key points, narrative for concepts
- Make the document ULTRA-DENSE and COMPACT — maximize information per page, ZERO wasted space
- MUST end with a ⚡ RAPID RECALL section covering every topic (30-60 concise points, miss nothing)
- Respond ONLY with valid JSON"""

GENERATE_SYSTEM_PROMPT = """You are an expert at creating ultra-compact, exam-ready study notes. You produce structured JSON that will be rendered into a professional Word document.

You MUST respond with ONLY valid JSON matching this schema:

{
  "title": {"text": "CH X — CHAPTER TITLE", "bold": true, "color": "#hex", "font_size": 14},
  "subtitle": {"text": "Class Y Subject | Source | Dense Exam Notes", "italic": true, "color": "#hex", "font_size": 9},
  "page_margin_inches": 0.6,
  "blocks": [
    // HEADING block — use numbered headings matching chapter structure
    {
      "type": "heading",
      "level": 1,  // 1=section (e.g. "3.1 TOPIC"), 2=subsection (e.g. "3.1.1 Subtopic"), 3=sub-sub
      "text": "3.1 LAWS OF CHEMICAL COMBINATION",
      "color": "#hex",
      "alignment": "left",
      "underline": false
    },
    // PARAGRAPH block — dense text with ▸ bullet prefix, bold key terms
    {
      "type": "paragraph",
      "runs": [
        {"text": "▸ ", "bold": true, "color": "#hex"},
        {"text": "Key Term", "bold": true, "underline": true},
        {"text": ": definition or explanation packed tightly", "bold": false}
      ],
      "alignment": "left"
    },
    // TABLE block — compact, no extra padding
    {
      "type": "table",
      "headers": [
        {"text": "Column 1", "bold": true, "color": "#ffffff", "bg_color": "#hex", "alignment": "center"},
        {"text": "Column 2", "bold": true, "color": "#ffffff", "bg_color": "#hex", "alignment": "center"}
      ],
      "rows": [
        [{"text": "Cell 1"}, {"text": "Cell 2"}]
      ],
      "header_bg_color": "#hex",
      "striped": true,
      "border_color": "#cccccc"
    },
    // BULLET LIST block — for dense point-form facts
    {
      "type": "bullet_list",
      "items": [
        {"text": "Key Term = definition (concise)", "bold": false},
        {"text": "Important fact → consequence", "bold": false}
      ]
    },
    // NUMBERED LIST block
    {
      "type": "numbered_list",
      "items": [
        {"text": "Step one"},
        {"text": "Step two"}
      ]
    },
    // HORIZONTAL RULE — thin separator between sections
    {"type": "horizontal_rule"},
    // PAGE BREAK — ONLY between truly major parts, not every section
    {"type": "page_break"}
  ]
}

═══════════════════════════════════════════════════════
FORMATTING & DENSITY RULES (CRITICAL — FOLLOW EXACTLY)
═══════════════════════════════════════════════════════

HEADINGS:
- Level 1 headings: "X.Y TOPIC NAME" (chapter-numbered, ALL CAPS, colored, bold) — font_size 12
- Level 2 headings: "X.Y.Z Subtopic Name" — font_size 10
- Level 3 headings: "X.Y.Z.W Detail" — font_size 9
- Where X = chapter number provided in the context
- NEVER use large font sizes. Title max 14pt, subtitle 9pt, headings 10-12pt
- NO gaps between heading and content

PARAGRAPHS & POINTS:
- Use "▸ " (triangle bullet) prefix for each fact/point in paragraph runs
- Bold and underline key terms/definitions on first mention
- Use arrows → for cause-effect, = for definitions
- Pack multiple related facts into one paragraph with multiple ▸ runs
- NO empty paragraphs, NO spacers, NO extra blank lines

TABLES:
- Tables MUST be compact — small font (font_size 8-9 in cells)
- Headers colored with white text
- Use striped rows
- Tables are for comparisons, data, formulas — NOT for single-column lists

LISTS:
- Use numbered_list for sequential items, bullet_list for non-sequential
- Each item must be self-contained and concise

RAPID RECALL SECTION (CRITICAL — MUST APPEAR AT END):
- MUST be the LAST section of the document, titled "⚡ RAPID RECALL"
- Must cover EVERY topic and sub-topic from the entire chapter — miss NOTHING
- 30-60 single-line points (one fact per line, ultra-compressed)
- Format: numbered_list, each item = "TopicName → key fact / definition / formula"
- Use symbols: →, =, ∴, ∵, ⚡, ★ to compress meaning
- NO explanations, NO full sentences — keyword chains only
- Group related facts on the same line with ; separator
- This section alone should let a student recall the ENTIRE chapter

OVERALL:
- Entire document MUST fit in 3-5 pages
- Use ONLY the exact hex colors from the COLOR PALETTE provided in context — never invent your own
- The color_scheme in the plan already contains the correct palette — apply those exact values
- NO page_break unless separating truly distinct major parts
- NO spacer blocks at all
- Horizontal rules only between major sections
- Color scheme must be used consistently
- Produce COMPLETE, THOROUGH content from source — no placeholders
- Respond ONLY with valid JSON"""


def _extract_json(raw: str) -> dict:
    """Extract JSON from LLM response, handling markdown code fences and common LLM errors."""
    # Try to find JSON in code fences
    fence_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", raw)
    if fence_match:
        raw = fence_match.group(1)

    # Strip leading/trailing whitespace
    raw = raw.strip()

    # Attempt 1: direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Attempt 2: fix common LLM issues
    fixed = raw
    # Remove trailing commas before } or ]
    fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
    # Remove control characters (except \n, \r, \t)
    fixed = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Attempt 3: find the outermost balanced { ... }
    brace_start = raw.find("{")
    if brace_start >= 0:
        depth = 0
        in_string = False
        escape_next = False
        last_brace = -1
        for i in range(brace_start, len(raw)):
            ch = raw[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                if in_string:
                    escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    last_brace = i
                    break
        if last_brace > brace_start:
            substr = raw[brace_start : last_brace + 1]
            substr = re.sub(r",\s*([}\]])", r"\1", substr)
            try:
                return json.loads(substr)
            except json.JSONDecodeError:
                pass

    # Attempt 4: truncated JSON — aggressively repair
    if brace_start >= 0:
        truncated = raw[brace_start:]
        # Strip trailing incomplete string (ends mid-value)
        # Find the last complete key-value by looking for last valid closing char
        # First close any open string
        in_str = False
        esc = False
        last_safe = 0
        for i, ch in enumerate(truncated):
            if esc:
                esc = False
                continue
            if ch == '\\' and in_str:
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
            if not in_str and ch in ('}', ']', '"'):
                # After a closing quote check if next non-ws is : , } ]
                last_safe = i
        # Cut at last safe position and try to close
        candidate = truncated[: last_safe + 1]
        # Remove any trailing comma
        candidate = candidate.rstrip().rstrip(",")
        # Remove trailing partial after last complete value
        # Strip trailing incomplete key (e.g. ,"partial_key  )
        candidate = re.sub(r',\s*"[^"]*$', '', candidate)
        candidate = re.sub(r",\s*$", "", candidate)
        # Remove trailing commas before closers
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
        # Count and close unclosed brackets/braces
        depth_brace = 0
        depth_bracket = 0
        in_str2 = False
        esc2 = False
        for ch in candidate:
            if esc2:
                esc2 = False
                continue
            if ch == '\\' and in_str2:
                esc2 = True
                continue
            if ch == '"':
                in_str2 = not in_str2
            if not in_str2:
                if ch == '{':
                    depth_brace += 1
                elif ch == '}':
                    depth_brace -= 1
                elif ch == '[':
                    depth_bracket += 1
                elif ch == ']':
                    depth_bracket -= 1
        candidate += "]" * max(depth_bracket, 0)
        candidate += "}" * max(depth_brace, 0)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM response. First 500 chars: {raw[:500]}")


async def _call_llm(
    system_prompt: str,
    user_prompt: str,
    model: str,
    api_key: str | None = None,
    max_tokens: int = 16000,
) -> str:
    """Call OpenRouter LLM with system + user messages."""
    api_key = api_key or settings.openrouter_api_key
    if not api_key:
        raise ValueError("OpenRouter API key is not configured")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}

    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        if not response.is_success:
            error_data = response.json() if response.content else {}
            error_msg = (
                error_data.get("error", {}).get("message", "")
                or f"API error: {response.status_code}"
            )
            raise ValueError(error_msg)

        data = response.json()
        if "error" in data:
            raise ValueError(data["error"].get("message", "API returned an error"))

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content or ""


async def _call_llm_json(
    system_prompt: str,
    user_prompt: str,
    model: str,
    api_key: str | None = None,
    max_tokens: int = 16000,
    retries: int = 2,
) -> dict:
    """Call LLM and parse JSON response with automatic retry on parse failure."""
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            raw = await _call_llm(system_prompt, user_prompt, model, api_key, max_tokens=max_tokens)
            return _extract_json(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            logger.warning(
                "LLM JSON parse failed (attempt %d/%d): %s",
                attempt, retries, str(exc)[:200],
            )
            # Bump max_tokens on retry in case of truncation
            max_tokens = min(max_tokens + 4000, 32000)
    raise ValueError(f"Failed to get valid JSON after {retries} attempts: {last_error}")


class DocAgentService:
    """Agentic orchestrator for document generation."""

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or settings.openrouter_model
        self.api_key = api_key or settings.openrouter_api_key

    # ── Step 1: Analyze ──────────────────────────────────────────

    async def analyze(self, source_text: str) -> AnalysisResult:
        """Analyze the source document to understand its structure and content."""
        logger.info("DocAgent step 1/4: Analyzing source document (%d chars)", len(source_text))

        truncated = source_text[:80_000]  # Keep within context limits
        user_prompt = f"Analyze this document:\n\n{truncated}"

        data = await _call_llm_json(ANALYZE_SYSTEM_PROMPT, user_prompt, self.model, self.api_key, max_tokens=4000)
        return AnalysisResult(**data)

    # ── Step 2: Plan ─────────────────────────────────────────────

    async def plan(
        self,
        analysis: AnalysisResult,
        user_prompt: str,
        source_text: str,
        class_level: str | None = None,
        subject: str | None = None,
        chapter_number: int | None = None,
        color_palette: dict[str, str] | None = None,
    ) -> PlanResult:
        """Design the document layout and section structure."""
        logger.info("DocAgent step 2/4: Planning document structure")

        context_lines = []
        if class_level:
            context_lines.append(f"CLASS LEVEL: {class_level}")
        if subject:
            context_lines.append(f"SUBJECT: {subject}")
        if chapter_number:
            context_lines.append(f"CHAPTER NUMBER: {chapter_number} (use this for section numbering: {chapter_number}.1, {chapter_number}.1.1, etc.)")
        if color_palette:
            context_lines.append(
                f"COLOR PALETTE (MUST USE EXACTLY — do NOT choose your own):\n"
                f"  primary (level-1 headings): {color_palette['primary']}\n"
                f"  secondary (level-2 headings): {color_palette['secondary']}\n"
                f"  accent (table headers, highlights): {color_palette['accent']}\n"
                f"  text (body text): {color_palette['text']}"
            )
        context_block = "\n".join(context_lines)

        prompt = f"""SOURCE ANALYSIS:
{analysis.model_dump_json(indent=2)}

{context_block}

USER REQUEST:
{user_prompt}

SOURCE MATERIAL (first 40000 chars):
{source_text[:40_000]}

Design an ultra-compact document plan (3-5 pages total) that fulfills the user's request.
Use chapter number {chapter_number or 'N/A'} for section numbering (e.g. {chapter_number or 'X'}.1, {chapter_number or 'X'}.2, {chapter_number or 'X'}.2.1).
IMPORTANT: Always include a final section called '⚡ RAPID RECALL' — 30-60 numbered single-line key facts covering every topic of the chapter."""

        data = await _call_llm_json(PLAN_SYSTEM_PROMPT, prompt, self.model, self.api_key, max_tokens=4000)
        return PlanResult(**data)

    # ── Step 3: Generate ─────────────────────────────────────────

    async def generate(
        self,
        plan: PlanResult,
        analysis: AnalysisResult,
        user_prompt: str,
        source_text: str,
        class_level: str | None = None,
        subject: str | None = None,
        chapter_number: int | None = None,
        color_palette: dict[str, str] | None = None,
    ) -> DocumentSchema:
        """Generate the full structured document content."""
        logger.info("DocAgent step 3/4: Generating document content")

        context_lines = []
        if class_level:
            context_lines.append(f"CLASS LEVEL: {class_level}")
        if subject:
            context_lines.append(f"SUBJECT: {subject}")
        if chapter_number:
            context_lines.append(f"CHAPTER NUMBER: {chapter_number} (all section headings MUST start with {chapter_number}.X)")
        if color_palette:
            context_lines.append(
                f"COLOR PALETTE (MUST USE EXACTLY — do NOT invent your own colors):\n"
                f"  primary = {color_palette['primary']}  → use for level-1 headings, title color\n"
                f"  secondary = {color_palette['secondary']}  → use for level-2/3 headings, subtitle color\n"
                f"  accent = {color_palette['accent']}  → use for table header bg_color, bold key terms, ▸ bullets\n"
                f"  text = {color_palette['text']}  → use for body text"
            )
        context_block = "\n".join(context_lines)

        prompt = f"""DOCUMENT PLAN:
{plan.model_dump_json(indent=2)}

SOURCE ANALYSIS:
{analysis.model_dump_json(indent=2)}

{context_block}

USER REQUEST:
{user_prompt}

SOURCE MATERIAL:
{source_text[:60_000]}

Generate the COMPLETE document content as structured JSON.
CRITICAL REMINDERS:
- Document MUST fit in 3-5 pages — be ruthlessly compact
- Title max 14pt, headings 10-12pt, body 9-10pt
- Page margins: 0.6 inches
- Use chapter number {chapter_number or 'N/A'} for ALL section numbering ({chapter_number or 'X'}.1, {chapter_number or 'X'}.1.1, etc.)
- Use ▸ triangle bullets for key facts in paragraph runs
- Bold + underline key terms on first mention
- Tables with small font (8-9pt), colored headers, striped rows
- NO spacers, NO empty paragraphs, NO excessive page breaks
- ZERO wasted space — pack information as tightly as possible
- MUST include a final ⚡ RAPID RECALL section: 30-60 numbered points covering EVERY topic in the chapter
- Each rapid recall point = one line, keyword → fact chain, miss nothing
- Produce EVERY section from the plan — do not skip any"""

        data = await _call_llm_json(GENERATE_SYSTEM_PROMPT, prompt, self.model, self.api_key, max_tokens=16000)
        return DocumentSchema(**data)

    # ── Full Pipeline ────────────────────────────────────────────

    async def run_pipeline(
        self,
        source_text: str,
        user_prompt: str,
        on_status: Any = None,
        class_level: str | None = None,
        subject: str | None = None,
        chapter_number: int | None = None,
        color_palette: dict[str, str] | None = None,
    ) -> tuple[DocumentSchema, AnalysisResult, PlanResult]:
        """Run the complete 4-step pipeline (steps 1-3; step 4 is formatting)."""

        # Step 1: Analyze
        if on_status:
            await on_status("analyzing")
        analysis = await self.analyze(source_text)

        # Step 2: Plan
        if on_status:
            await on_status("planning")
        plan = await self.plan(
            analysis, user_prompt, source_text,
            class_level=class_level, subject=subject, chapter_number=chapter_number,
            color_palette=color_palette,
        )

        # Step 3: Generate
        if on_status:
            await on_status("generating")
        document = await self.generate(
            plan, analysis, user_prompt, source_text,
            class_level=class_level, subject=subject, chapter_number=chapter_number,
            color_palette=color_palette,
        )

        return document, analysis, plan
