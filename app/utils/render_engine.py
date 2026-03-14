"""
Delta-to-HTML render engine for converting Quill Delta JSON to sanitized HTML.

This module converts Quill Delta payloads into HTML fragments suitable for:
- PDF export (with print-specific page breaks)
- Web publishing (sanitized HTML for public pages)
"""
import html
import re
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse


def _normalize_header_level(value: Any) -> int:
    """Normalize header value to a safe HTML heading level."""
    try:
        level = int(value)
    except (TypeError, ValueError):
        return 1
    if level < 1 or level > 6:
        return 1
    return level


def _is_safe_url(
    url: str,
    *,
    allow_protocol_relative: bool = False,
    allow_plain_relative: bool = True,
    allow_fragment: bool = True,
    allowed_schemes: Optional[set[str]] = None,
) -> bool:
    """Validate URL scheme/shape before using it in href/src attributes."""
    if not isinstance(url, str):
        return False

    value = url.strip()
    if not value:
        return False

    lowered = value.lower()
    if lowered.startswith(("javascript:", "data:", "vbscript:")):
        return False

    if lowered.startswith("//"):
        return allow_protocol_relative

    parsed = urlparse(value)
    safe_schemes = allowed_schemes or {"http", "https", "mailto", "tel"}

    if parsed.scheme:
        return parsed.scheme.lower() in safe_schemes

    if value.startswith("/"):
        return True
    if value.startswith("#"):
        return allow_fragment
    return allow_plain_relative


def render_delta_to_html(
    delta: Optional[Dict[str, Any]],
    *,
    media_url_resolver: Optional[Callable[[str, str], str]] = None,
    print_mode: bool = False
) -> str:
    """
    Convert Quill Delta JSON to sanitized HTML fragment.

    Args:
        delta: Quill Delta structure (dict with "ops" list)
        media_url_resolver: Optional function that takes (media_type, media_id)
                          and returns the public URL for that media
        print_mode: If True, adds page-break hints for PDF generation

    Returns:
        Sanitized HTML fragment (no <html>/<head>, just content tags)

    Example Delta:
        {
            "ops": [
                {"insert": "Hello "},
                {"insert": "world", "attributes": {"bold": true}},
                {"insert": "\\n"}
            ]
        }

    Example Output:
        <p>Hello <strong>world</strong></p>
    """
    if not isinstance(delta, dict):
        return ""

    ops = delta.get("ops")
    if not isinstance(ops, list):
        return ""

    # Process ops into HTML blocks
    html_parts: List[str] = []
    current_block: List[str] = []
    current_block_type: Optional[str] = None  # 'p', 'h1', 'h2', etc.
    list_items: List[str] = []
    list_type: Optional[str] = None  # 'ul' or 'ol'
    code_block_lines: List[str] = []

    def flush_code_block():
        """Flush accumulated code block lines."""
        nonlocal code_block_lines
        if code_block_lines:
            code_content = html.escape('\n'.join(code_block_lines))
            html_parts.append(f'<pre><code>{code_content}</code></pre>')
            code_block_lines = []

    def flush_list():
        """Flush accumulated list items."""
        nonlocal list_items, list_type
        if list_items and list_type:
            items_html = ''.join(f'<li>{item}</li>' for item in list_items)
            html_parts.append(f'<{list_type}>{items_html}</{list_type}>')
            list_items = []
            list_type = None

    def flush_block():
        """Flush current text block as a paragraph or heading."""
        nonlocal current_block, current_block_type
        if current_block:
            content = ''.join(current_block).strip()
            if content:
                tag = current_block_type or 'p'
                html_parts.append(f'<{tag}>{content}</{tag}>')
            current_block = []
            current_block_type = None

    def take_current_block_content() -> str:
        """Consume buffered inline content without emitting a block wrapper."""
        nonlocal current_block, current_block_type
        if not current_block:
            return ""
        content = ''.join(current_block).strip()
        current_block = []
        current_block_type = None
        return content

    for op in ops:
        if not isinstance(op, dict):
            continue

        insert = op.get("insert")
        attributes = op.get("attributes") or {}
        if not isinstance(attributes, dict):
            attributes = {}

        # Handle text inserts
        if isinstance(insert, str):
            lines = insert.split('\n')

            for i, line in enumerate(lines):
                is_newline = (i < len(lines) - 1) or (i == 0 and not line)

                # Check for block-level formatting
                header = attributes.get("header")
                list_attr = attributes.get("list")
                blockquote = attributes.get("blockquote")
                code_block = attributes.get("code-block")

                if code_block:
                    # Code block: flush other blocks and accumulate lines
                    flush_block()
                    flush_list()
                    if line or code_block_lines:
                        code_block_lines.append(line)
                    if is_newline:
                        continue

                elif list_attr:
                    # List item
                    flush_code_block()

                    carried_content = ""
                    if is_newline and not line and current_block and (current_block_type in (None, 'p')):
                        carried_content = take_current_block_content()
                    else:
                        flush_block()

                    list_tag = 'ul' if list_attr == 'bullet' else 'ol'

                    if list_type and list_type != list_tag:
                        flush_list()

                    list_type = list_tag
                    formatted_line = carried_content or _apply_inline_formatting(line, attributes)
                    if formatted_line:
                        list_items.append(formatted_line)

                    if is_newline:
                        continue

                elif blockquote:
                    # Blockquote
                    flush_list()
                    flush_code_block()

                    carried_content = ""
                    if is_newline and not line and current_block and (current_block_type in (None, 'p')):
                        carried_content = take_current_block_content()

                    if current_block_type != 'blockquote':
                        flush_block()
                        current_block_type = 'blockquote'

                    formatted_line = carried_content or _apply_inline_formatting(line, attributes)
                    if formatted_line:
                        current_block.append(formatted_line)

                    if is_newline:
                        if carried_content:
                            flush_block()
                        elif current_block:
                            current_block.append('<br>')

                elif header:
                    # Heading
                    flush_list()
                    flush_code_block()

                    carried_content = ""
                    if is_newline and not line and current_block and (current_block_type in (None, 'p')):
                        carried_content = take_current_block_content()

                    header_tag = f'h{_normalize_header_level(header)}'

                    if current_block_type and current_block_type != header_tag:
                        flush_block()

                    current_block_type = header_tag
                    formatted_line = carried_content or _apply_inline_formatting(line, attributes)
                    if formatted_line:
                        current_block.append(formatted_line)

                    if is_newline:
                        flush_block()

                else:
                    # Regular paragraph
                    flush_list()
                    flush_code_block()

                    if current_block_type and current_block_type != 'p':
                        flush_block()

                    if line:
                        formatted_line = _apply_inline_formatting(line, attributes)
                        current_block.append(formatted_line)

                    if is_newline:
                        if current_block:
                            current_block.append('<br>')

        # Handle embed inserts (image, video)
        elif isinstance(insert, dict):
            # Flush any pending blocks before inserting media
            flush_block()
            flush_list()
            flush_code_block()

            # Handle image embeds
            if "image" in insert:
                image_id = insert["image"]
                if not isinstance(image_id, str):
                    continue
                if media_url_resolver:
                    image_url = media_url_resolver("image", image_id)
                else:
                    image_url = image_id  # Fallback: use ID as URL

                if _is_safe_url(
                    image_url,
                    allow_protocol_relative=True,
                    allow_plain_relative=False,
                    allow_fragment=False,
                    allowed_schemes={"http", "https"},
                ):
                    safe_url = html.escape(image_url, quote=True)
                    html_parts.append(f'<img src="{safe_url}" alt="">')

            # Handle video embeds
            elif "video" in insert:
                video_id = insert["video"]
                if not isinstance(video_id, str):
                    continue
                if media_url_resolver:
                    video_url = media_url_resolver("video", video_id)
                else:
                    video_url = video_id  # Fallback: use ID as URL

                if _is_safe_url(
                    video_url,
                    allow_protocol_relative=True,
                    allow_plain_relative=False,
                    allow_fragment=False,
                    allowed_schemes={"http", "https"},
                ):
                    safe_url = html.escape(video_url, quote=True)
                    html_parts.append(f'<video controls src="{safe_url}"></video>')

    # Flush any remaining blocks
    flush_block()
    flush_list()
    flush_code_block()

    # Join all HTML parts
    result = ''.join(html_parts)

    # Add print-specific page break hints before heading sections.
    if print_mode:
        result = _add_page_break_hints(result)

    return result


def _add_page_break_hints(html_fragment: str) -> str:
    """Insert page-break marker blocks before h1/h2 tags except the first heading."""
    if not html_fragment:
        return html_fragment

    pattern = re.compile(r"(<h[12]\b[^>]*>)", flags=re.IGNORECASE)
    seen_heading = False

    def _replacer(match: re.Match[str]) -> str:
        nonlocal seen_heading
        heading_tag = match.group(1)
        if not seen_heading:
            seen_heading = True
            return heading_tag
        return f'<div class="page-break"></div>{heading_tag}'

    return pattern.sub(_replacer, html_fragment)


def _apply_inline_formatting(text: str, attributes: Dict[str, Any]) -> str:
    """
    Apply inline formatting (bold, italic, link, code, etc.) to text.

    Args:
        text: Plain text to format
        attributes: Quill Delta attributes

    Returns:
        HTML-formatted text with inline tags
    """
    if not text:
        return ""

    # Escape HTML entities first
    formatted = html.escape(text)

    # Apply inline formatting in order
    if attributes.get("code"):
        formatted = f'<code>{formatted}</code>'

    if attributes.get("bold"):
        formatted = f'<strong>{formatted}</strong>'

    if attributes.get("italic"):
        formatted = f'<em>{formatted}</em>'

    if attributes.get("underline"):
        formatted = f'<u>{formatted}</u>'

    if attributes.get("strike"):
        formatted = f'<s>{formatted}</s>'

    link = attributes.get("link")
    if isinstance(link, str) and _is_safe_url(
        link,
        allow_protocol_relative=False,
        allow_plain_relative=True,
        allow_fragment=True,
        allowed_schemes={"http", "https", "mailto", "tel"},
    ):
        safe_link = html.escape(link, quote=True)
        formatted = f'<a href="{safe_link}" target="_blank" rel="noopener noreferrer">{formatted}</a>'

    return formatted
