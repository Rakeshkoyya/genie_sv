"""Document export service for generating DOCX and TXT files."""

import io
import re
from typing import Any
from docx import Document
from docx.shared import Pt, Twips
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


DEFAULT_FONT = "Calibri"
DEFAULT_SIZE = Pt(11)


def sanitize_filename(name: str) -> str:
    """Sanitize a filename by removing invalid characters.
    
    Args:
        name: Original filename
        
    Returns:
        Sanitized filename
    """
    sanitized = re.sub(r"[^a-zA-Z0-9\s\-_]", "", name).strip()
    return sanitized if sanitized else "document"


def create_docx(title: str, results: list[dict[str, Any]]) -> bytes:
    """Create a DOCX document from generation results.
    
    Args:
        title: Document title
        results: List of dicts with 'name' and 'content' keys
        
    Returns:
        DOCX file bytes
    """
    doc = Document()
    
    # Set default font for document
    style = doc.styles["Normal"]
    style.font.name = DEFAULT_FONT
    style.font.size = DEFAULT_SIZE
    
    # Title
    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_para.add_run(title)
    title_run.bold = True
    title_run.font.size = Pt(24)
    title_run.font.name = DEFAULT_FONT
    
    # Add each result
    for i, result in enumerate(results):
        content = result.get("content", "")
        _add_parsed_content(doc, content)
        
        # Add spacing between sections
        if i < len(results) - 1:
            doc.add_paragraph()
    
    # Save to bytes
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def _add_parsed_content(doc: Document, text: str) -> None:
    """Parse response content and add to document.
    
    Handles:
    - <heading>text</heading>
    - <subheading>text</subheading>
    - <bold>text</bold>
    - Numbered lists (1. Item)
    - Bullet lists (- Item)
    - Markdown headings (#, ##, ###)
    
    Args:
        doc: Document to add content to
        text: Response text to parse
    """
    lines = text.split("\n")
    
    for line in lines:
        trimmed = line.strip()
        
        # Empty line -> add spacing
        if not trimmed:
            para = doc.add_paragraph()
            para.paragraph_format.space_after = Pt(4)
            continue
        
        # <heading>text</heading>
        heading_match = re.match(r"^<heading>(.*?)</heading>$", trimmed)
        if heading_match:
            para = doc.add_paragraph()
            run = para.add_run(heading_match.group(1).strip())
            run.bold = True
            run.font.size = Pt(14)
            run.font.name = DEFAULT_FONT
            para.paragraph_format.space_before = Pt(12)
            para.paragraph_format.space_after = Pt(6)
            continue
        
        # <subheading>text</subheading>
        sub_match = re.match(r"^<subheading>(.*?)</subheading>$", trimmed)
        if sub_match:
            para = doc.add_paragraph()
            run = para.add_run(sub_match.group(1).strip())
            run.bold = True
            run.font.size = Pt(12)
            run.font.name = DEFAULT_FONT
            para.paragraph_format.space_before = Pt(10)
            para.paragraph_format.space_after = Pt(5)
            continue
        
        # Numbered list: 1. Item text
        num_match = re.match(r"^(\d+)[.)]\s+(.+)", trimmed)
        if num_match:
            para = doc.add_paragraph(style="List Number")
            _add_inline_bold(para, num_match.group(2))
            para.paragraph_format.space_after = Pt(4)
            continue
        
        # Bullet list: - Item text or • Item text
        bullet_match = re.match(r"^[-•*]\s+(.+)", trimmed)
        if bullet_match:
            para = doc.add_paragraph(style="List Bullet")
            _add_inline_bold(para, bullet_match.group(1))
            para.paragraph_format.space_after = Pt(4)
            continue
        
        # Markdown headings fallback
        md_match = re.match(r"^(#{1,3})\s+(.+)", trimmed)
        if md_match:
            level = len(md_match.group(1))
            para = doc.add_paragraph()
            run = para.add_run(md_match.group(2))
            run.bold = True
            run.font.size = Pt(14 if level == 1 else 12 if level == 2 else 11)
            run.font.name = DEFAULT_FONT
            para.paragraph_format.space_before = Pt(10)
            para.paragraph_format.space_after = Pt(5)
            continue
        
        # Regular text
        para = doc.add_paragraph()
        _add_inline_bold(para, trimmed)
        para.paragraph_format.space_after = Pt(4)


def _add_inline_bold(para, text: str) -> None:
    """Add text to paragraph, handling inline <bold> and **bold** tags.
    
    Args:
        para: Paragraph to add text to
        text: Text with potential bold markers
    """
    # Split on bold patterns
    parts = re.split(r"(<bold>[\s\S]*?</bold>|\*\*[\s\S]*?\*\*)", text)
    
    for part in parts:
        if not part:
            continue
        
        # XML bold
        xml_match = re.match(r"^<bold>([\s\S]*?)</bold>$", part)
        if xml_match:
            run = para.add_run(xml_match.group(1))
            run.bold = True
            run.font.name = DEFAULT_FONT
            continue
        
        # Markdown bold
        md_match = re.match(r"^\*\*([\s\S]*?)\*\*$", part)
        if md_match:
            run = para.add_run(md_match.group(1))
            run.bold = True
            run.font.name = DEFAULT_FONT
            continue
        
        # Regular text
        run = para.add_run(part)
        run.font.name = DEFAULT_FONT


def create_txt(title: str, content: str) -> bytes:
    """Create a plain text file from content.
    
    Strips XML/HTML tags and normalizes formatting.
    
    Args:
        title: Document title
        content: Content text
        
    Returns:
        TXT file bytes (UTF-8 encoded)
    """
    # Strip XML tags
    text = re.sub(r"</?response>", "", content)
    text = re.sub(r"<heading>(.*?)</heading>", r"\n\n\1\n", text)
    text = re.sub(r"<subheading>(.*?)</subheading>", r"\n\1\n", text)
    text = re.sub(r"<bold>(.*?)</bold>", r"\1", text)
    
    # Build final text
    final_text = f"{title}\n{'=' * len(title)}\n\n{text.strip()}"
    
    return final_text.encode("utf-8")


class DocumentExportService:
    """Service class for document export operations."""
    
    def create_docx(self, title: str, results: list[dict[str, Any]]) -> bytes:
        """Create a DOCX document.
        
        Args:
            title: Document title
            results: List of dicts with 'name' and 'content' keys
            
        Returns:
            DOCX file bytes
        """
        return create_docx(title, results)
    
    def create_txt(self, title: str, content: str) -> bytes:
        """Create a plain text document.
        
        Args:
            title: Document title
            content: Content text
            
        Returns:
            TXT file bytes
        """
        return create_txt(title, content)
