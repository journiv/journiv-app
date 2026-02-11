"""
Convert Daylio HTML notes to Quill Delta.
"""
from __future__ import annotations

import html
from html.parser import HTMLParser
from typing import Dict, List, Optional


class _DaylioHtmlToDeltaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ops: List[Dict] = []
        self.inline_attrs: Dict[str, bool] = {}
        self.list_stack: List[str] = []
        self.pending_list_type: Optional[str] = None
        self.last_was_newline = True

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in {"b", "strong"}:
            self.inline_attrs["bold"] = True
        elif tag in {"i", "em"}:
            self.inline_attrs["italic"] = True
        elif tag == "u":
            self.inline_attrs["underline"] = True
        elif tag in {"strike", "s", "del"}:
            self.inline_attrs["strike"] = True
        elif tag == "br":
            self._insert_newline()
        elif tag == "div":
            if not self.last_was_newline:
                self._insert_newline()
        elif tag == "ul":
            self.list_stack.append("bullet")
        elif tag == "ol":
            self.list_stack.append("ordered")
        elif tag == "li":
            if not self.last_was_newline:
                self._insert_newline()
            self.pending_list_type = self.list_stack[-1] if self.list_stack else None

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"b", "strong"}:
            self.inline_attrs.pop("bold", None)
        elif tag in {"i", "em"}:
            self.inline_attrs.pop("italic", None)
        elif tag == "u":
            self.inline_attrs.pop("underline", None)
        elif tag in {"strike", "s", "del"}:
            self.inline_attrs.pop("strike", None)
        elif tag == "div":
            if not self.last_was_newline:
                self._insert_newline()
        elif tag == "li":
            self._insert_newline(list_type=self.pending_list_type)
            self.pending_list_type = None
        elif tag in {"ul", "ol"}:
            if self.list_stack:
                self.list_stack.pop()

    def handle_data(self, data: str) -> None:
        if not data:
            return
        text = html.unescape(data).replace("\xa0", " ")
        if not text:
            return
        if text.strip() == "" and self.last_was_newline:
            return
        self._insert_text(text)

    def _insert_text(self, text: str) -> None:
        if not text:
            return
        op: Dict[str, object] = {"insert": text}
        if self.inline_attrs:
            op["attributes"] = dict(self.inline_attrs)
        self.ops.append(op)
        self.last_was_newline = text.endswith("\n")

    def _insert_newline(self, list_type: Optional[str] = None) -> None:
        attrs = {}
        if list_type:
            attrs["list"] = list_type
        op: Dict[str, object] = {"insert": "\n"}
        if attrs:
            op["attributes"] = attrs
        self.ops.append(op)
        self.last_was_newline = True


def html_to_delta(html_text: Optional[str]) -> Dict[str, List[Dict]]:
    """
    Convert Daylio HTML note to Quill Delta ops.
    """
    if not html_text:
        return {"ops": [{"insert": "\n"}]}
    parser = _DaylioHtmlToDeltaParser()
    parser.feed(html_text)
    if not parser.ops:
        return {"ops": [{"insert": "\n"}]}
    if not parser.ops[-1].get("insert", "").endswith("\n"):
        parser.ops.append({"insert": "\n"})
    return {"ops": parser.ops}
