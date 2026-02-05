"""
Day One RichText parser.

Converts Day One richText JSON format to clean Markdown.
"""
import json
import re
from typing import Any, Dict, List, Optional

from app.core.logging_config import log_warning


class DayOneRichTextParser:
    """
    Parser for Day One richText format.

    Day One stores rich content as a JSON string containing:
    - contents: array of text blocks with attributes
    - meta: metadata (ignored during conversion)

    Example richText structure:
    {
        "contents": [
            {
                "attributes": {"line": {"header": 1}},
                "text": "My Title\\n"
            },
            {
                "attributes": {"line": {"header": 0}},
                "text": "Paragraph text\\n"
            },
            {
                "embeddedObjects": [
                    {"identifier": "UUID", "type": "photo"}
                ]
            }
        ],
        "meta": {...}
    }
    """

    # Placeholder prefix for media references during import
    # Format: DAYONE_PHOTO:md5_hash or DAYONE_VIDEO:md5_hash
    PLACEHOLDER_PREFIX = "DAYONE_"

    @staticmethod
    def parse_richtext(richtext_json: str) -> Optional[Dict[str, Any]]:
        """
        Parse Day One richText JSON string.

        Args:
            richtext_json: JSON string from Day One richText field

        Returns:
            Parsed richText dict with 'contents' and 'meta', or None if invalid
        """
        if not richtext_json or not richtext_json.strip():
            return None

        try:
            richtext = json.loads(richtext_json)
            return richtext
        except (json.JSONDecodeError, TypeError) as e:
            log_warning(f"Failed to parse richText JSON: {e}")
            return None

    @staticmethod
    def extract_title(richtext: Dict[str, Any]) -> Optional[str]:
        """
        Extract title from richText contents.

        Rules:
        1. Use the first content block with attributes.line.header == 1
        2. Remove trailing newlines
        3. Strip markdown formatting characters (#, *, etc.)
        4. Trim to max 60 characters
        5. Return None if no title text found

        Args:
            richtext: Parsed richText dict

        Returns:
            Extracted title string, or None if no title text found
        """
        contents = richtext.get("contents", [])
        if not contents:
            return None

        title = None

        for block in contents:
            if "attributes" not in block or "line" not in block["attributes"]:
                continue
            header_level = block["attributes"]["line"].get("header")
            if header_level == 1 and "text" in block and block["text"].strip():
                title = block["text"]
                break

        if not title:
            return None

        # Clean up title
        title = title.rstrip('\n')  # Remove trailing newlines
        title = DayOneRichTextParser._strip_markdown(title)  # Remove markdown chars
        title = title.strip()  # Trim whitespace

        # Truncate to 60 chars
        if len(title) > 60:
            title = title[:60].strip()

        return title if title else None

    @staticmethod
    def convert_to_markdown(
        richtext: Dict[str, Any],
        photos: Optional[List[Any]] = None,
        videos: Optional[List[Any]] = None,
        entry_id: Optional[str] = None
    ) -> str:
        """
        Convert Day One richText to clean Markdown.

        Conversion rules:
        - attributes.line.header:N → "#" * N + " text" (H1-H6, but Journiv only displays H1-H3)
        - attributes.bold → **text**
        - attributes.italic → *text*
        - attributes.underline → <u>text</u> (HTML fallback)
        - attributes.strikethrough → ~~text~~
        - attributes.inlineCode → `text`
        - attributes.highlightedColor → ==text== (Journiv's highlight syntax)
        - attributes.line.listStyle:bulleted → "- text"
        - attributes.line.listStyle:numbered → "1. text"
        - attributes.line.listStyle:checkbox → "- [ ] text" or "- [x] text"
        - attributes.line.quote → "> text"
        - attributes.line.codeBlock → "```\ntext\n```"
        - embeddedObjects with type:photo/video → DAYONE_PHOTO:{md5} placeholder
        - embeddedObjects with type:horizontalRuleLine → "---"
        - Ignore meta, version, small-lines-removed

        Args:
            richtext: Parsed richText dict
            photos: List of DayOnePhoto objects for resolving embedded media
            videos: List of DayOneVideo objects for resolving embedded media
            entry_id: Journiv entry ID for media paths (not Day One UUID)

        Returns:
            Clean Markdown string
        """
        contents = richtext.get("contents", [])
        if not contents:
            return ""

        # Build media lookup map: identifier -> media object (photos + videos)
        media_map: Dict[str, Any] = {}
        for photo in photos or []:
            media_map[photo.identifier] = photo
        for video in videos or []:
            media_map[video.identifier] = video

        markdown_lines = []
        current_line = ""  # Accumulate inline text segments
        in_code_block = False
        code_block_lines = []

        for i, block in enumerate(contents):
            # Handle text blocks with attributes
            if "text" in block:
                raw_text = block["text"]
                text = raw_text.rstrip('\n')
                has_newline = raw_text.endswith('\n')

                # Get attributes
                attrs = block.get("attributes", {})
                line_attrs = attrs.get("line", {})

                # Handle code blocks (multi-line)
                is_code_block = line_attrs.get("codeBlock", False)
                if is_code_block:
                    if not in_code_block:
                        # Flush any pending content before starting code block
                        if current_line:
                            markdown_lines.append(current_line)
                            current_line = ""
                        in_code_block = True
                        code_block_lines = []

                    code_block_lines.append(text)

                    # Check if next block is also a code block
                    is_last_in_code_block = True
                    if i + 1 < len(contents):
                        next_block = contents[i + 1]
                        if "text" in next_block:
                            next_attrs = next_block.get("attributes", {})
                            next_line_attrs = next_attrs.get("line", {})
                            if next_line_attrs.get("codeBlock", False):
                                is_last_in_code_block = False

                    if is_last_in_code_block:
                        # End of code block - flush it
                        code_content = "\n".join(code_block_lines)
                        markdown_lines.append(f"```\n{code_content}\n```")
                        in_code_block = False
                        code_block_lines = []

                    continue

                # Handle headers (H1-H6, though Journiv only renders H1-H3)
                header_level = line_attrs.get("header", 0)
                if header_level > 0:
                    # Flush current line if any
                    if current_line:
                        markdown_lines.append(current_line)
                        current_line = ""

                    # Clamp to H6 max (standard markdown)
                    header_level = min(header_level, 6)
                    header_prefix = "#" * header_level
                    markdown_lines.append(f"{header_prefix} {text}")
                    continue

                # Handle list styles
                list_style = line_attrs.get("listStyle")
                is_quote = line_attrs.get("quote", False)
                indent_level = line_attrs.get("indentLevel", 0)

                # Build line prefix for lists/quotes
                # indent_level starts at 1 for first level, 2 for nested, etc.
                # Each level adds 2 spaces, so level 1 = no indent, level 2 = 2 spaces, etc.
                line_prefix = ""
                if list_style == "bulleted":
                    line_prefix = "  " * max(0, indent_level - 1) + "- "
                elif list_style == "numbered":
                    # Use the list index if provided, otherwise default to 1
                    list_index = line_attrs.get("listIndex", 1)
                    line_prefix = "  " * max(0, indent_level - 1) + f"{list_index}. "
                elif list_style == "checkbox":
                    checked = line_attrs.get("checked", False)
                    checkbox = "[x]" if checked else "[ ]"
                    line_prefix = "  " * max(0, indent_level - 1) + f"- {checkbox} "
                elif is_quote:
                    line_prefix = "> "

                # Apply inline formatting to text
                formatted_text = text

                # Inline code (highest priority - wraps text)
                if attrs.get("inlineCode"):
                    formatted_text = f"`{formatted_text}`"
                else:
                    # Other inline formatting (only if not inline code)
                    if attrs.get("bold"):
                        formatted_text = f"**{formatted_text}**"
                    if attrs.get("italic"):
                        formatted_text = f"*{formatted_text}*"
                    if attrs.get("underline"):
                        formatted_text = f"<u>{formatted_text}</u>"
                    if attrs.get("strikethrough"):
                        formatted_text = f"~~{formatted_text}~~"

                # Highlight (Journiv uses ==text== syntax)
                # Day One uses highlightedColor attribute with color value
                if attrs.get("highlightedColor"):
                    formatted_text = f"=={formatted_text}=="

                # Accumulate text in current line
                current_line += formatted_text

                # If text ends with newline or has line-level formatting, flush the line
                if has_newline or line_prefix:
                    if line_prefix:
                        current_line = line_prefix + current_line
                    markdown_lines.append(current_line)
                    current_line = ""

            # Handle embedded objects (photos/videos/horizontal rules)
            if "embeddedObjects" in block:
                # Flush current line before adding media
                if current_line:
                    markdown_lines.append(current_line)
                    current_line = ""

                for obj in block["embeddedObjects"]:
                    obj_type = obj.get("type")

                    # Handle horizontal rule
                    if obj_type == "horizontalRuleLine":
                        markdown_lines.append("---")
                        continue

                    # Handle photos and videos
                    if obj_type not in {"photo", "video"}:
                        continue

                    identifier = obj.get("identifier")

                    # Look up media in entry photos/videos
                    media = media_map.get(identifier)
                    if not media:
                        log_warning(
                            f"Embedded {obj_type} {identifier} not found in entry media list",
                            media_id=identifier
                        )
                        continue

                    # Resolve filename using md5
                    if getattr(media, "md5", None):
                        placeholder = media.md5
                    else:
                        placeholder = identifier

                    # Always use placeholder that will be replaced after entry creation
                    # Format: DAYONE_PHOTO:{md5_hash} / DAYONE_VIDEO:{md5_hash}
                    prefix = "PHOTO" if obj_type == "photo" else "VIDEO"
                    markdown_lines.append(f"{DayOneRichTextParser.PLACEHOLDER_PREFIX}{prefix}:{placeholder}")

        # Flush any remaining text
        if current_line:
            markdown_lines.append(current_line)

        # Join all lines with newlines
        markdown = "\n\n".join(markdown_lines)
        return markdown.strip()

    @staticmethod
    def replace_photo_placeholders(content: str, photo_map: Dict[str, str]) -> str:
        """
        Replace Day One photo placeholders with Journiv media shortcode format.

        Placeholders format: DAYONE_PHOTO:{md5_hash} or DAYONE_VIDEO:{md5_hash}
        Replacement format: ![[media:{media_id}]]

        Args:
            content: Markdown content with placeholders
            photo_map: Dict mapping md5 hash -> media_id (UUID)

        Returns:
            Content with placeholders replaced
        """
        import re

        def replace_placeholder(match):
            md5_hash = match.group(1)
            media_id = photo_map.get(md5_hash)
            if media_id:
                return f"![[media:{media_id}]]"
            else:
                # Photo not found, remove placeholder silently
                return ""

        # Replace all DAYONE_* placeholders
        pattern = rf'{DayOneRichTextParser.PLACEHOLDER_PREFIX}(?:PHOTO|VIDEO|MEDIA):([\w-]+)'
        content = re.sub(pattern, replace_placeholder, content)

        # Clean up any double newlines created by removed placeholders
        content = re.sub(r'\n\n\n+', '\n\n', content)

        return content.strip()

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """
        Strip markdown formatting characters from text.

        Removes: #, *, _, `, etc.

        Args:
            text: Text with potential markdown formatting

        Returns:
            Plain text without markdown characters
        """
        # Remove inline markdown (bold, italic, etc.) - process longer patterns first
        # to avoid partial matches
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Bold **text**
        text = re.sub(r'__([^_]+)__', r'\1', text)      # Bold __text__
        text = re.sub(r'\*([^*]+)\*', r'\1', text)      # Italic *text*
        text = re.sub(r'_([^_]+)_', r'\1', text)        # Italic _text_
        text = re.sub(r'`([^`]+)`', r'\1', text)        # Code `text`

        # Remove leading/trailing markdown chars
        text = re.sub(r'^[#*_`~\-]+\s*', '', text)  # Leading
        text = re.sub(r'\s*[#*_`~\-]+$', '', text)  # Trailing

        return text.strip()
