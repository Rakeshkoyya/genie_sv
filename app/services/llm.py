"""LLM service for calling OpenRouter API."""

import logging
import re
import httpx
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

BASE_SYSTEM_PROMPT = """You are a helpful assistant. You are given the content of one or more documents. Answer the user's prompt based on the provided content. Be thorough and well-structured in your response."""

MASTER_PLANNER_PROMPT = """You are an expert educational content planner. You will be given:
1. The content of a chapter/document (source material)
2. A list of content generation steps that will be executed sequentially to produce a workbook
3. Optional metadata about the target grade and subject (if provided by the user)

Your job is to analyze the source material and create a MASTER PLAN that will guide each step's execution.

{metadata_section}

ANALYSIS REQUIRED:
- If grade/subject metadata is provided above, use it as ground truth. Do NOT override it with your own guess.
- If grade/subject is NOT provided, infer the target grade/class level and age group from the content's language complexity, vocabulary, and subject matter. Also infer the subject area.
- Extract ALL topics and subtopics from the chapter with their key concepts
- Estimate the chapter's length and density (short/medium/long)
- Assess complexity level (basic recall, conceptual understanding, analytical, etc.)

PLANNING REQUIRED:
For each generation step listed below, specify:
- Exactly how many items/questions/entries to generate (calibrated to grade level and chapter length)
- Which topics and subtopics that step must cover (ensure full coverage across all steps)
- The appropriate difficulty and language level for the detected grade
- Approximate target page count for that section
- Any special instructions (tone, emoji usage, formatting density, etc.)

CALIBRATION RULES:
- Lower grades (Class 1-5): Simpler language, more emojis and visuals, shorter answers, more fun elements, smaller total workbook (15-25 pages)
- Middle grades (Class 6-8): Moderate complexity, balanced fun and rigor, medium workbook (25-40 pages)
- Higher grades (Class 9-12): Advanced vocabulary, analytical depth, comprehensive coverage, larger workbook (35-60 pages)
- Short chapters (< 5 topics): Scale down proportionally, avoid padding
- Long chapters (> 10 topics): Ensure breadth without excessive repetition
- IMPORTANT: The workbook should feel complete and thorough but NOT overwhelming for the target grade level

SOURCE MATERIAL:
{sources}

GENERATION STEPS TO PLAN:
{steps_description}

Now output the master plan. Be specific with numbers and targets — do NOT be vague.
Output your plan between <masterplan> and </masterplan> tags."""

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
    master_plan: str | None = None,
    step_context: str | None = None,
) -> str:
    """Build the final prompt with sources, query, and format instructions.
    
    Args:
        sources: Concatenated source content
        user_query: The user's prompt/question
        response_format: Optional custom format template
        master_plan: Optional master plan from planner (injected for chain steps)
        step_context: Optional current step context (e.g. "Step 2 of 7 — Glossary")
        
    Returns:
        Complete prompt string ready for LLM
    """
    format_section = (
        f"{RESPONSE_FORMAT_INSTRUCTIONS}\n{response_format}"
        if response_format
        else DEFAULT_RESPONSE_FORMAT
    )
    
    plan_section = ""
    if master_plan:
        plan_section = f"\nMASTER PLAN:\n{master_plan}\n"
        if step_context:
            plan_section += f"\nCURRENT STEP: {step_context}\nFollow the master plan's guidance for this specific step. Generate exactly the amount and type of content specified in the plan for this step.\n"
    
    return f"""{BASE_SYSTEM_PROMPT}
{plan_section}
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

    async with httpx.AsyncClient(timeout=120.0) as client:
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
        master_plan: str | None = None,
        step_context: str | None = None,
    ) -> str:
        """Generate content from sources using a prompt.
        
        Args:
            sources: Concatenated source content
            prompt: User's prompt/question
            format_text: Optional response format template
            model: Optional model override
            media_parts: Optional image parts for multimodal
            master_plan: Optional master plan for chain-aware generation
            step_context: Optional current step context string
            
        Returns:
            Extracted response content
        """
        final_prompt = build_final_prompt(sources, prompt, format_text, master_plan, step_context)
        # print("=== SINGLE GENERATE - FINAL PROMPT ===")
        # print(f"Prompt (user_query): {prompt[:500]}")
        # print(f"Format text present: {format_text is not None}")
        # print(f"Format text: {format_text[:500] if format_text else 'None'}")
        # print(f"Final prompt length: {len(final_prompt)}")
        # print(f"Final prompt:\n{final_prompt[:2000]}")
        # print("=== END SINGLE GENERATE PROMPT ===")
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
        grade: str | None = None,
        subject: str | None = None,
    ) -> list[str]:
        """Execute a chain of prompts sequentially with master plan orchestration.
        
        Before running steps, calls the master planner to analyze the source
        and create a per-step execution plan. The plan is injected into every
        step so the LLM knows the full context, target audience, and exactly
        how much content to generate.
        
        Args:
            sources: Concatenated source content
            steps: List of dicts with 'prompt', 'name', and optional 'format' keys
            model: Optional model override
            media_parts: Optional image parts for multimodal
            chain_name: Name of the prompt chain (for planner context)
            chain_description: Description of the prompt chain
            grade: Optional grade/class level hint (e.g. "Class 4")
            subject: Optional subject hint (e.g. "Science")
            
        Returns:
            List of extracted responses for each step
        """
        use_model = model or self.model
        
        # Step 0: Create master plan
        master_plan = await self.create_master_plan(
            sources=sources,
            steps=steps,
            chain_name=chain_name,
            chain_description=chain_description,
            model=use_model,
            grade=grade,
            subject=subject,
        )
        
        # Execute each step with the master plan injected
        results = []
        total = len(steps)
        for idx, step in enumerate(steps):
            step_name = step.get("name", f"Step {idx + 1}")
            step_context = f"Step {idx + 1} of {total} — \"{step_name}\""
            
            response = await self.generate(
                sources=sources,
                prompt=step["prompt"],
                format_text=step.get("format"),
                model=use_model,
                media_parts=media_parts,
                master_plan=master_plan,
                step_context=step_context,
            )
            results.append(response)
        return results
    
    async def create_master_plan(
        self,
        sources: str,
        steps: list[dict[str, str]],
        chain_name: str | None = None,
        chain_description: str | None = None,
        model: str | None = None,
        grade: str | None = None,
        subject: str | None = None,
    ) -> str:
        """Analyze source material and create an execution plan for all chain steps.
        
        Args:
            sources: Concatenated source content
            steps: List of dicts with 'prompt' and 'name' keys
            chain_name: Name of the prompt chain
            chain_description: Description of the prompt chain
            model: Model to use for planning
            grade: Optional grade/class hint provided by user
            subject: Optional subject hint provided by user
            
        Returns:
            The master plan text to inject into each step's prompt
        """
        # Build metadata section based on what the user provided
        metadata_parts = []
        if grade or subject:
            metadata_parts.append("USER-PROVIDED METADATA (use as ground truth):")
            if grade:
                metadata_parts.append(f"- Target Grade/Class: {grade}")
            if subject:
                metadata_parts.append(f"- Subject: {subject}")
            metadata_section = "\n".join(metadata_parts)
        else:
            metadata_section = "No grade or subject metadata provided. You MUST infer the grade level and subject from the content's language complexity, vocabulary, concepts, and subject matter."
        
        # Build the steps description for the planner
        steps_lines = []
        for idx, step in enumerate(steps):
            name = step.get("name", f"Step {idx + 1}")
            # Include a truncated version of the prompt so the planner understands intent
            prompt_preview = step["prompt"][:500]
            steps_lines.append(f"[Step {idx + 1}: {name}]\nPrompt: {prompt_preview}")
        
        steps_description = "\n\n".join(steps_lines)
        
        chain_context = ""
        if chain_name:
            chain_context += f"Chain Name: {chain_name}\n"
        if chain_description:
            chain_context += f"Chain Description: {chain_description}\n"
        if chain_context:
            steps_description = f"{chain_context}\n{steps_description}"
        
        planner_prompt = MASTER_PLANNER_PROMPT.format(
            sources=sources or "(No sources provided)",
            steps_description=steps_description,
            metadata_section=metadata_section,
        )
        
        logger.info("create_master_plan → model=%s, steps=%d, sources_len=%d",
                     model or self.model, len(steps), len(sources or ""))
        
        raw_response = await call_llm(
            planner_prompt,
            model=model or self.model,
            api_key=self.api_key,
        )
        
        # Extract content from <masterplan> tags
        match = re.search(r"<masterplan>([\s\S]*?)</masterplan>", raw_response)
        plan = match.group(1).strip() if match else raw_response.strip()
        
        logger.info("Master plan created: %d chars", len(plan))
        return plan
