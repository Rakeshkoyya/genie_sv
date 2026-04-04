"""Utility functions for prompt building."""

import base64
from typing import Any


def format_sources_text(sources: list[dict[str, Any]]) -> str:
    """Format source documents into a combined text block.
    
    Args:
        sources: List of source dicts with 'name' and 'extracted_text' keys
        
    Returns:
        Formatted sources text with separators
    """
    text_parts = []
    
    for source in sources:
        name = source.get("name", "Unnamed")
        text = source.get("extracted_text", "")
        if text:
            text_parts.append(f"[{name}]\n{text}")
    
    return "\n\n---\n\n".join(text_parts)


def prepare_media_parts(
    sources: list[dict[str, Any]],
    max_size: int = 5 * 1024 * 1024
) -> list[dict[str, Any]]:
    """Prepare image sources as base64 media parts for multimodal LLM.
    
    Args:
        sources: List of source dicts with 'type', 'content', 'metadata' keys
        max_size: Maximum file size for base64 encoding (default 5MB)
        
    Returns:
        List of media part dicts for LLM API
    """
    parts = []
    
    for source in sources:
        if source.get("type") != "image":
            continue
        
        content = source.get("content")
        if not content or len(content) > max_size:
            continue
        
        # Get MIME type from metadata
        metadata = source.get("metadata", {})
        mime_type = metadata.get("mimeType", "image/png")
        
        # Encode as base64 data URI
        b64 = base64.b64encode(content).decode("utf-8")
        data_uri = f"data:{mime_type};base64,{b64}"
        
        parts.append({
            "type": "image_url",
            "image_url": {"url": data_uri}
        })
    
    return parts


def combine_chain_results(results: list[str], separator: str = "\n\n---\n\n") -> str:
    """Combine multiple chain step results into a single string.
    
    Args:
        results: List of result strings
        separator: Separator between results
        
    Returns:
        Combined result string
    """
    return separator.join(results)
