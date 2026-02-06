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
    def convert_to_delta(
        richtext: Dict[str, Any],
        photos: Optional[List[Any]] = None,
        videos: Optional[List[Any]] = None,
        entry_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Convert Day One richText to Quill Delta format.

        Embedded media are represented as image/video embeds with Day One identifiers
        (md5 hash preferred), which are replaced after media import.
        """
        contents = richtext.get("contents", [])
        if not contents:
            return {"ops": [{"insert": "\n"}]}

        media_map: Dict[str, Any] = {}
        for photo in photos or []:
            media_map[photo.identifier] = photo
        for video in videos or []:
            media_map[video.identifier] = video

        ops: List[Dict[str, Any]] = []

        def append_text(text: str, attrs: Optional[Dict[str, Any]] = None) -> None:
            if text == "":
                return
            op: Dict[str, Any] = {"insert": text}
            if attrs:
                op["attributes"] = attrs
            ops.append(op)

        def append_newline(attrs: Optional[Dict[str, Any]] = None) -> None:
            op: Dict[str, Any] = {"insert": "\n"}
            if attrs:
                op["attributes"] = attrs
            ops.append(op)

        for block in contents:
            if "text" in block:
                raw_text = block["text"]
                has_newline = raw_text.endswith("\n")
                text = raw_text.rstrip("\n").rstrip()

                attrs = block.get("attributes", {})
                line_attrs = attrs.get("line", {})

                inline_attrs: Dict[str, Any] = {}
                if attrs.get("bold"):
                    inline_attrs["bold"] = True
                if attrs.get("italic"):
                    inline_attrs["italic"] = True
                if attrs.get("underline"):
                    inline_attrs["underline"] = True
                if attrs.get("strikethrough"):
                    inline_attrs["strike"] = True
                if attrs.get("inlineCode"):
                    inline_attrs["code"] = True
                if attrs.get("highlightedColor"):
                    inline_attrs["background"] = attrs.get("highlightedColor")

                is_code_block = line_attrs.get("codeBlock", False)
                header_level = line_attrs.get("header", 0)
                list_style = line_attrs.get("listStyle")
                is_quote = line_attrs.get("quote", False)
                indent_level = line_attrs.get("indentLevel", 0)

                if text:
                    append_text(text, inline_attrs or None)

                line_format: Dict[str, Any] = {}
                if is_code_block:
                    line_format["code-block"] = True
                elif header_level:
                    line_format["header"] = min(header_level, 6)
                elif list_style == "bulleted":
                    line_format["list"] = "bullet"
                elif list_style == "numbered":
                    line_format["list"] = "ordered"
                elif list_style == "checkbox":
                    checked = line_attrs.get("checked", False)
                    line_format["list"] = "checked" if checked else "unchecked"
                elif is_quote:
                    line_format["blockquote"] = True

                if indent_level and indent_level > 1:
                    line_format["indent"] = indent_level - 1

                if has_newline or line_format:
                    append_newline(line_format or None)

            if "embeddedObjects" in block:
                for obj in block["embeddedObjects"]:
                    obj_type = obj.get("type")

                    if obj_type == "horizontalRuleLine":
                        append_text("---")
                        append_newline()
                        continue

                    if obj_type not in {"photo", "video"}:
                        continue

                    identifier = obj.get("identifier")
                    media = media_map.get(identifier)
                    if not media:
                        log_warning(
                            f"Embedded {obj_type} {identifier} not found in entry media list",
                            media_id=identifier
                        )
                        continue

                    placeholder = getattr(media, "md5", None) or identifier
                    key = "image" if obj_type == "photo" else "video"
                    ops.append({"insert": {key: placeholder}})
                    append_newline()

        if not ops:
            return {"ops": [{"insert": "\n"}]}

        last_insert = ops[-1].get("insert")
        if isinstance(last_insert, dict):
            append_newline()
        elif isinstance(last_insert, str) and not last_insert.endswith("\n"):
            append_newline()

        return {"ops": ops}

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
