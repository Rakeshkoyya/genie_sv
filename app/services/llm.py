"""LLM service for calling OpenRouter API."""

import logging
import re
import httpx
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

BASE_SYSTEM_PROMPT = """You are a helpful assistant. You are given the content of one or more documents. Answer the user's prompt based on the provided content. Be thorough and well-structured in your response."""

DEFAULT_RESPONSE_FORMAT = """Wrap your entire response in <response></response> XML tags. Structure your content using:
- <heading>Text</heading> for main headings
- <subheading>Text</subheading> for sub headings
- <bold>text</bold> for emphasis
- "- Item" for bullet lists
- "1. Item" for numbered lists
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
    response_format: str | None = None
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
        media_parts: list[dict[str, Any]] | None = None
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
        media_parts: list[dict[str, Any]] | None = None
    ) -> list[str]:
        """Execute a chain of prompts sequentially.
        
        Args:
            sources: Concatenated source content
            steps: List of dicts with 'prompt' and optional 'format' keys
            model: Optional model override
            media_parts: Optional image parts for multimodal
            
        Returns:
            List of extracted responses for each step
        """
        results = []
        for step in steps:
            response = await self.generate(
                sources=sources,
                prompt=step["prompt"],
                format_text=step.get("format"),
                model=model,
                media_parts=media_parts
            )
            results.append(response)
        return results
