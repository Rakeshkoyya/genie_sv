"""LLM service for calling OpenRouter API."""

import json
import logging
import re
import httpx
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

BASE_SYSTEM_PROMPT = """You are a helpful assistant. You are given the content of one or more documents. Answer the user's prompt based on the provided content. Be thorough and well-structured in your response."""

MASTER_PLANNER_PROMPT = """You are a world-class professional workbook designer for the education system. You will be given:
1. The content of a chapter/document (source material)
2. A numbered list of workbook sections to generate, each with:
   - The user's original prompt (what to generate)
   - The response format template (the expected output structure and XML tags)

YOUR TASK:
Analyze the source material deeply, then for EACH numbered section produce TWO outputs:
  A) An OPTIMISED PROMPT — a refined version of the user's prompt
  B) An EXPANDED FORMAT — the response format template expanded with real content structure from the source

The KEY IDEA: instead of telling the LLM "generate 5 pages" or "write 30 questions", you ENCODE the exact scope directly into the response format itself. The format becomes the blueprint — the LLM only needs to fill it in.

═══════════════════════════════════════════════════════
STEP 1 — ANALYSIS (do this first, internally)
═══════════════════════════════════════════════════════
- Infer the target grade/class level and age group from the content's language complexity, vocabulary, and subject matter.
- Infer the subject area.
- Extract ALL topics and subtopics from the chapter with their key concepts.
- Count the number of major topics found. This is your TOPIC_COUNT.
- Estimate the chapter's density: SHORT (1-3 topics), MEDIUM (4-7 topics), LONG (8+ topics).

═══════════════════════════════════════════════════════
STEP 2 — GRADE-LEVEL SCALING
═══════════════════════════════════════════════════════
Use the detected grade to decide the SCALE of expansion for each section.

| Grade       | Item density per section | Tone                          |
|-------------|-------------------------|-------------------------------|
| Class 1-3   | Minimal (fewest items)  | Playful, emojis 🎨🌟, simple |
| Class 4-5   | Light                   | Simple but structured         |
| Class 6-8   | Moderate                | Balanced fun and rigor        |
| Class 9-10  | Dense                   | Exam-focused, analytical      |
| Class 11-12 | Heavy                   | Board-exam level, critical    |

This affects HOW MANY placeholders/slots you put into the expanded format for each section.

═══════════════════════════════════════════════════════
STEP 3 — EXPAND EACH RESPONSE FORMAT
═══════════════════════════════════════════════════════
This is the core task. For each section, take the user's response format template and EXPAND it by:

1. REPLACE generic placeholders with REAL content from the source:
   - [Main Topic 1] → actual topic name from the chapter (e.g. "Oceans and Marine Life")
   - [Subtopic 1a] → actual subtopic (e.g. "Types of marine organisms")
   - [Question text] → keep as [Question text] but SET the exact count
   - [Detail or key concept] → keep as placeholder but set per-topic count

2. SET EXACT ITEM COUNTS by replicating placeholder lines:
   - If the template shows `<label>1.</label> [Question text]` through `<label>10.</label>`,
     and you decide this section needs 25 questions, expand it to show all 25 label lines.
   - Group items by topic where the section's purpose benefits from it.

3. ADD TOPIC-SPECIFIC STRUCTURE:
   - If a section covers multiple topics, replicate the repeating block per topic.
   - For concept maps: list the actual topics as nodes.
   - For glossary: create topic-grouped subsections with the real headings.
   - For questions: create sub-sections per question type with exact counts.

4. KEEP ALL XML TAGS from the original format intact. Do NOT invent new tag types.
   You can replicate existing tags and fill in real headings/topics/counts.

EXAMPLE — Questions format expansion:
Original template:
  <heading>Section A: Concept-Based Questions</heading>
  <instruction>Answer in one word or one line.</instruction>
  <label>1.</label> [Question text]
  ...
  <label>10.</label> [Question text]

Expanded (for Class 6, 9 topics, moderate density):
  <heading>Section A: Concept-Based Questions</heading>
  <instruction>Answer in one word or one line. Cover all 9 topics from the chapter.</instruction>
  <label>1.</label> [Question about Oceans and Continents]
  <label>2.</label> [Question about Distribution of Water and Land]
  <label>3.</label> [Question about Marine Life]
  <label>4.</label> [Question about Ocean Disasters and Safety]
  <label>5.</label> [Question about Continents and Counts]
  <label>6.</label> [Question about Islands and Antarctica]
  <label>7.</label> [Question about Oceans and Life on Earth]
  <label>8.</label> [Question about Climate and Oxygen]
  <label>9.</label> [Question about Pollution and Ocean Protection]
  <label>10.</label> [Question about any topic - analytical]
  <hr/>
  <heading>Section B: Fact-Based Questions</heading>
  <instruction>Answer in one word or one phrase.</instruction>
  <label>11.</label> [Fact question]
  <label>12.</label> [Fact question]
  ...
  <label>20.</label> [Fact question]

EXAMPLE — Concept mapping format expansion:
Original template:
  1. <bold>[Main Topic 1]</bold>
  1.1 [Subtopic 1a]
  1.1.1 [Detail]
  2. <bold>[Main Topic 2]</bold>
  ...

Expanded (for 9-topic geography chapter):
  1. <bold>Oceans and Continents</bold>
  1.1 [Key concept or subtopic]
  1.2 [Key concept or subtopic]
  2. <bold>Distribution of Water and Land</bold>
  2.1 [Key concept or subtopic]
  2.2 [Key concept or subtopic]
  3. <bold>Marine Life</bold>
  3.1 [Key concept or subtopic]
  3.2 [Key concept or subtopic]
  ... (one block per topic, 2-3 subtopics each — compact)

═══════════════════════════════════════════════════════
STEP 4 — OPTIMISE EACH PROMPT
═══════════════════════════════════════════════════════
For the optimised prompt (inside <prompt_N> tags):
- PRESERVE the original intent and ALL original instructions.
- ADD the detected grade level and tone calibration.
- ADD the list of topics extracted from the source that this section MUST cover.
- ADD a note: "Follow the expanded response format exactly — it defines the scope and structure."
- Do NOT add page budgets, word limits, or item counts in the prompt — those are already encoded in the format.

═══════════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════════
Wrap each section's outputs in numbered XML tags:
<prompt_1>
[Optimised prompt for section 1]
</prompt_1>
<format_1>
[Expanded format for section 1, or NONE if original was empty]
</format_1>
<prompt_2>
[Optimised prompt for section 2]
</prompt_2>
<format_2>
[Expanded format for section 2, or NONE if original was empty]
</format_2>
... and so on for all N sections.

AFTER all the prompt/format pairs, output a structured plan summary:
<plan_summary>
{{
  "detected_grade": "Class X-Y",
  "detected_subject": "Subject Name",
  "chapter_density": "SHORT|MEDIUM|LONG",
  "topic_count": N,
  "topics": ["Topic 1", "Topic 2", "..."],
  "sections": [
    {{"name": "Section 1 Name", "strategy": "Brief description of what was expanded — e.g. 10 concept Qs + 15 fact Qs across 9 topics"}},
    {{"name": "Section 2 Name", "strategy": "e.g. Hierarchical map with 9 topic nodes, 2-3 subtopics each"}}
  ]
}}
</plan_summary>

SOURCE MATERIAL:
{sources}

WORKBOOK SECTIONS TO PLAN:
{steps_description}

Now analyse the source, expand each response format with real content structure, optimise each prompt, and output the plan summary."""

DEFAULT_RESPONSE_FORMAT = """Wrap your entire response in <response></response> XML tags. Structure your content using:
- <title>Text</title> for the document/chapter title (centered, large, bold)
- <heading>Text</heading> for main section headings
- <subheading>Text</subheading> for sub section headings
- <instruction>Text</instruction> for italic instructions (e.g. "Answer the following:")
- <bold>text</bold> for bold emphasis
- <italic>text</italic> for italic text
- <underline>text</underline> for underlined text
- <label>Q1.</label> for bold question number labels
- "1. Item" for numbered lists
- "- Item" for bullet lists
- <blank/> for a fill-in-the-blank line
- <hr/> for a horizontal separator line
- <pagebreak/> for a page break
- <space lines="N"/> for N blank lines of writing space
- <indent>text</indent> for indented text
- <box title="Optional Title">content</box> for a bordered box (tips, notes, answer keys)
- <table><row><cell>A</cell><cell>B</cell></row></table> for tables
Do NOT use markdown."""

RESPONSE_FORMAT_INSTRUCTIONS = """Follow the provided formatting example exactly. Wrap your entire response in <response></response> tags.
The formatting example below shows how the response should be structured and formatted.
Pay close attention to the example and mimic the structure, tags, and formatting shown.
Do NOT deviate from the provided formatting rules.
Do NOT use markdown or any formatting not specified in the example.
Output only the expected content wrapped in <response> tags with no extra text.

FORMATTING EXAMPLE:"""


def build_final_prompt(
    sources: str,
    user_query: str,
    response_format: str | None = None,
) -> str:
    """Build the final prompt with sources, query, and format instructions.
    
    Args:
        sources: Concatenated source content
        user_query: The user's prompt/question
        response_format: Optional custom format template
        
    Returns:
        Complete prompt string ready for LLM
    """
    format_section = (
        f"{RESPONSE_FORMAT_INSTRUCTIONS}\n{response_format}"
        if response_format
        else DEFAULT_RESPONSE_FORMAT
    )
    
    return f"""{BASE_SYSTEM_PROMPT}

INPUT SOURCES:
{sources or "(No sources provided)"}

USER QUERY:
{user_query}

RESPONSE INSTRUCTIONS:
{format_section}"""


def extract_response_content(content: str) -> str:
    """Extract content from <response> tags.
    
    Args:
        content: Raw LLM response
        
    Returns:
        Extracted content or original if no tags found
    """
    match = re.search(r"<response>([\s\S]*?)</response>", content)
    if match:
        return match.group(1).strip()
    return content.strip()


async def call_llm(
    prompt: str,
    model: str | None = None,
    media_parts: list[dict[str, Any]] | None = None,
    api_key: str | None = None
) -> str | list[dict[str, Any]]:
    """Call the OpenRouter LLM API.
    
    Args:
        prompt: The text prompt to send
        model: Model identifier (defaults to settings.openrouter_model)
        media_parts: Optional list of image parts for multimodal
        api_key: Optional API key (defaults to settings.openrouter_api_key)
        
    Returns:
        The LLM response content (str) or list of image parts for image models
        
    Raises:
        httpx.HTTPStatusError: If API returns an error
        ValueError: If response is malformed
    """
    api_key = api_key or settings.openrouter_api_key
    model = model or settings.openrouter_model
    
    if not api_key:
        raise ValueError("OpenRouter API key is not configured")
    
    # Build message content
    if media_parts:
        user_content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        user_content.extend(media_parts)
    else:
        user_content = prompt  # type: ignore
    
    messages = [{"role": "user", "content": user_content}]
    payload: dict[str, Any] = {"model": model, "messages": messages}

    logger.info("call_llm → model=%s, media_parts=%d, prompt_len=%d",
                model, len(media_parts) if media_parts else 0, len(prompt))

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
            logger.error("OpenRouter HTTP %s — full response: %s", response.status_code, error_data)
            error_msg = error_data.get("error", {}).get("message", f"API error: {response.status_code}")
            raise ValueError(error_msg)
        
        data = response.json()
        
        # Check for error in response body (200 but still an error)
        if "error" in data:
            logger.error("OpenRouter returned error in body: %s", data["error"])
            raise ValueError(data["error"].get("message", "API returned an error"))
        
        message = data.get("choices", [{}])[0].get("message", {})
        content = message.get("content", "")

        # Some models (e.g. Gemini image) return images in a separate field
        images = message.get("images")
        if images and isinstance(images, list):
            return images  # Return raw list so caller can extract image URLs

        return content or ""


class LLMService:
    """Service class for LLM operations."""
    
    def __init__(self, api_key: str | None = None, model: str | None = None):
        """Initialize LLM service.
        
        Args:
            api_key: OpenRouter API key
            model: Default model to use
        """
        self.api_key = api_key or settings.openrouter_api_key
        self.model = model or settings.openrouter_model
    
    async def generate(
        self,
        sources: str,
        prompt: str,
        format_text: str | None = None,
        model: str | None = None,
        media_parts: list[dict[str, Any]] | None = None,
    ) -> str:
        """Generate content from sources using a prompt.
        
        Args:
            sources: Concatenated source content
            prompt: User's prompt/question
            format_text: Optional response format template
            model: Optional model override
            media_parts: Optional image parts for multimodal
            
        Returns:
            Extracted response content
        """
        final_prompt = build_final_prompt(sources, prompt, format_text)
        raw_response = await call_llm(
            final_prompt,
            model=model or self.model,
            media_parts=media_parts,
            api_key=self.api_key
        )
        return extract_response_content(raw_response)
    
    async def generate_chain(
        self,
        sources: str,
        steps: list[dict[str, str]],
        model: str | None = None,
        media_parts: list[dict[str, Any]] | None = None,
        chain_name: str | None = None,
        chain_description: str | None = None,
    ) -> list[str]:
        """Execute a chain of prompts with workbook plan optimisation.
        
        Calls the workbook planner first, then generates ALL sections in a
        single LLM call using the mega-prompt approach.
        
        Args:
            sources: Concatenated source content
            steps: List of dicts with 'prompt', 'name', and optional 'format' keys
            model: Optional model override
            media_parts: Optional image parts for multimodal
            chain_name: Name of the prompt chain (for planner context)
            chain_description: Description of the prompt chain
            
        Returns:
            List of extracted responses for each step
        """
        use_model = model or self.model
        
        # Step 0: Create workbook plan — returns optimised prompts/formats per step
        plan = await self.create_workbook_plan(
            sources=sources,
            steps=steps,
            chain_name=chain_name,
            chain_description=chain_description,
            model=use_model,
        )
        planned_steps = plan["steps"]
        
        # Step 1: Generate all sections in a single LLM call
        return await self.generate_all_sections(
            sources=sources,
            planned_steps=planned_steps,
            step_names=[s.get("name", f"Section {i+1}") for i, s in enumerate(steps)],
            model=use_model,
            media_parts=media_parts,
        )
    
    async def generate_all_sections(
        self,
        sources: str,
        planned_steps: list[dict[str, str | None]],
        step_names: list[str] | None = None,
        model: str | None = None,
        media_parts: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        """Generate ALL workbook sections in a single LLM call.
        
        Builds a mega-prompt that combines all section prompts and response
        formats, instructing the LLM to wrap each section's output in
        <response_N> tags. Uses the model's large context window (400K).
        
        Args:
            sources: Concatenated source content
            planned_steps: List of dicts with 'prompt' and 'format' keys (from planner)
            step_names: Optional display names for each section
            model: Optional model override
            media_parts: Optional image parts for multimodal
            
        Returns:
            List of extracted response contents, one per section
        """
        use_model = model or self.model
        names = step_names or [f"Section {i+1}" for i in range(len(planned_steps))]
        
        # Build the mega-prompt with all sections
        section_blocks = []
        for idx, (planned, name) in enumerate(zip(planned_steps, names)):
            tag_num = idx + 1
            prompt_text = planned["prompt"]
            format_text = planned.get("format")
            
            block = f"""
{'='*60}
SECTION {tag_num}: {name}
{'='*60}

PROMPT:
{prompt_text}

"""
            if format_text:
                block += f"""{RESPONSE_FORMAT_INSTRUCTIONS}
{format_text}

"""
            else:
                block += f"""{DEFAULT_RESPONSE_FORMAT}

"""
            
            block += f"""Wrap your ENTIRE response for this section in <response_{tag_num}></response_{tag_num}> tags.
"""
            section_blocks.append(block)
        
        mega_prompt = f"""{BASE_SYSTEM_PROMPT}

INPUT SOURCES:
{sources or "(No sources provided)"}

You must generate content for {len(planned_steps)} sections of a workbook. Each section has its own prompt and response format.
Generate ALL sections in order. Wrap each section's output in its designated <response_N> tags.
Do NOT skip any section. Do NOT merge sections together.

{"".join(section_blocks)}

IMPORTANT: Generate ALL {len(planned_steps)} sections. Each section MUST be wrapped in its own <response_N> tags (from <response_1> to <response_{len(planned_steps)}>).
Start generating now."""
        
        logger.info("generate_all_sections → model=%s, sections=%d, prompt_len=%d",
                     use_model, len(planned_steps), len(mega_prompt))
        
        # Use longer timeout for mega-call (large output expected)
        raw_response = await call_llm(
            mega_prompt,
            model=use_model,
            media_parts=media_parts,
            api_key=self.api_key,
        )
        
        # Extract each section's response from <response_N> tags
        results = []
        for idx in range(len(planned_steps)):
            tag_num = idx + 1
            match = re.search(
                rf"<response_{tag_num}>([\s\S]*?)</response_{tag_num}>", raw_response
            )
            if match:
                results.append(match.group(1).strip())
            else:
                logger.warning("generate_all_sections: <response_%d> not found in LLM output", tag_num)
                results.append(f"[Section {tag_num}: {names[idx]} — content not generated]")
        
        logger.info("generate_all_sections: extracted %d/%d sections successfully",
                     sum(1 for r in results if not r.startswith("[Section")), len(planned_steps))
        return results
    
    async def create_workbook_plan(
        self,
        sources: str,
        steps: list[dict[str, str]],
        chain_name: str | None = None,
        chain_description: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Analyse source material and produce optimised prompts/formats per step.
        
        The planner LLM receives all step prompts and their response formats,
        then returns a refined version of each that embeds topic coverage,
        item counts, difficulty calibration, and structural guidance — all
        tailored to the detected grade level and source content.
        
        Args:
            sources: Concatenated source content
            steps: List of dicts with 'prompt', 'name', and optional 'format' keys
            chain_name: Name of the prompt chain
            chain_description: Description of the prompt chain
            model: Model to use for planning
            
        Returns:
            Dict with:
              - 'steps': list of dicts with 'prompt' and 'format' keys (optimised)
              - 'summary': dict with plan metadata (grade, pages, sections, etc.)
            Falls back to originals if extraction fails for any step.
        """
        # Build the steps description for the planner
        steps_lines = []
        for idx, step in enumerate(steps):
            name = step.get("name", f"Step {idx + 1}")
            prompt_text = step["prompt"]
            format_text = step.get("format") or "(No response format provided)"
            steps_lines.append(
                f"[Section {idx + 1}: {name}]\n"
                f"USER PROMPT:\n{prompt_text}\n\n"
                f"RESPONSE FORMAT TEMPLATE:\n{format_text}"
            )
        
        steps_description = "\n\n" + ("=" * 60 + "\n\n").join(steps_lines)
        
        chain_context = ""
        if chain_name:
            chain_context += f"Workbook Name: {chain_name}\n"
        if chain_description:
            chain_context += f"Workbook Description: {chain_description}\n"
        if chain_context:
            steps_description = f"{chain_context}\n{steps_description}"
        
        planner_prompt = MASTER_PLANNER_PROMPT.format(
            sources=sources or "(No sources provided)",
            steps_description=steps_description,
        )
        
        logger.info("create_workbook_plan → model=%s, steps=%d, sources_len=%d",
                     model or self.model, len(steps), len(sources or ""))
        
        try:
            raw_response = await call_llm(
                planner_prompt,
                model=model or self.model,
                api_key=self.api_key,
            )
        except Exception as exc:
            logger.warning("Workbook planner LLM call failed, using original prompts: %s", exc)
            return {
                "steps": [{"prompt": s["prompt"], "format": s.get("format")} for s in steps],
                "summary": None,
            }
        
        # Extract optimised prompts and formats from tagged XML
        planned_steps: list[dict[str, str | None]] = []
        for idx in range(len(steps)):
            tag_num = idx + 1
            
            # Extract <prompt_N>...</prompt_N>
            prompt_match = re.search(
                rf"<prompt_{tag_num}>([\s\S]*?)</prompt_{tag_num}>", raw_response
            )
            optimised_prompt = (
                prompt_match.group(1).strip() if prompt_match
                else steps[idx]["prompt"]  # fallback to original
            )
            
            # Extract <format_N>...</format_N>
            format_match = re.search(
                rf"<format_{tag_num}>([\s\S]*?)</format_{tag_num}>", raw_response
            )
            if format_match:
                fmt_text = format_match.group(1).strip()
                optimised_format = None if fmt_text.upper() == "NONE" else fmt_text
            else:
                optimised_format = steps[idx].get("format")  # fallback to original
            
            planned_steps.append({
                "prompt": optimised_prompt,
                "format": optimised_format,
            })
            
            if not prompt_match:
                logger.warning("Workbook planner: <prompt_%d> not found, using original", tag_num)
            if not format_match:
                logger.warning("Workbook planner: <format_%d> not found, using original", tag_num)
        
        # Extract plan summary JSON
        summary = None
        summary_match = re.search(
            r"<plan_summary>([\s\S]*?)</plan_summary>", raw_response
        )
        if summary_match:
            try:
                summary = json.loads(summary_match.group(1).strip())
            except json.JSONDecodeError as exc:
                logger.warning("Workbook planner: <plan_summary> JSON parse failed: %s", exc)
        else:
            logger.warning("Workbook planner: <plan_summary> not found in response")
        
        logger.info("Workbook plan created: %d steps optimised, summary=%s",
                     len(planned_steps), "yes" if summary else "no")
        return {"steps": planned_steps, "summary": summary}
