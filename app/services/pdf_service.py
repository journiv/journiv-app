"""
PDF export service using WeasyPrint.

Converts journal entries to PDF format using the Delta-to-HTML render engine.
"""

import html
import logging
import re
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote
from uuid import UUID

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlmodel import Session, col, select

from app.core.config import settings
from app.core.logging_config import LogCategory
from app.core.media_signing import attach_signed_urls_to_delta
from app.models.entry import Entry
from app.models.moment import Moment, MomentMedia
from app.utils.render_engine import render_delta_to_html

logger = logging.getLogger(LogCategory.EXPORT)

# Template directory path
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


def build_content_disposition(filename: str) -> str:
    """
    Build an RFC 6266/RFC 5987 safe Content-Disposition value.

    Includes both:
    - filename="<ascii-fallback>"
    - filename*=UTF-8''<percent-encoded-utf8>
    """
    original = Path(
        (filename or "download.pdf").replace("\r", "").replace("\n", "")
    ).name
    original = original.replace('"', "")
    if not original:
        original = "download.pdf"
    if not original.lower().endswith(".pdf"):
        original = f"{original}.pdf"

    ascii_fallback = original.encode("ascii", "ignore").decode("ascii")
    ascii_fallback = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_fallback).strip("._")
    if not ascii_fallback:
        ascii_fallback = "download"
    if not ascii_fallback.lower().endswith(".pdf"):
        ascii_fallback = f"{ascii_fallback}.pdf"

    utf8_encoded = quote(original, safe="")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{utf8_encoded}"


class PDFService:
    """
    Service for generating PDFs from journal entries.

    Uses WeasyPrint to convert HTML to PDF with print-optimized styling.
    """

    def __init__(self):
        """Initialize PDF service with Jinja2 template environment."""
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    @staticmethod
    def _sanitize_html_for_template(content_html: str) -> str:
        """
        Defense-in-depth guard for values rendered with template `content|safe`.

        The primary sanitizer is render_delta_to_html. This method ensures unsafe
        patterns never pass through if upstream assumptions are violated.
        """
        if not content_html:
            return ""

        suspicious_pattern = re.compile(
            r"(?is)"
            r"<\s*(script|iframe|object|embed|link|meta)\b"
            r"|on[a-z0-9_-]+\s*="
            r"|javascript:"
            r"|vbscript:"
            r"|data:\s*text/html"
        )
        if suspicious_pattern.search(content_html):
            logger.warning(
                "Potentially unsafe HTML detected in PDF content; escaping content."
            )
            return f"<p>{html.escape(content_html)}</p>"

        return content_html

    @staticmethod
    def _is_uuid_identifier(value: str) -> bool:
        try:
            UUID(str(value))
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _is_trusted_internal_media_reference(value: str) -> bool:
        if not isinstance(value, str):
            return False
        candidate = value.strip()
        if not candidate:
            return False
        if PDFService._is_uuid_identifier(candidate):
            return True
        return candidate.startswith("/api/v1/media/") or candidate.startswith(
            "/api/v1/integrations/immich/proxy/"
        )

    @classmethod
    def _sanitize_delta_media_references_for_pdf(
        cls,
        delta_content: dict,
        *,
        media_url_resolver: Optional[Callable[[str, str], str]],
    ) -> dict:
        """
        Strip untrusted media references when no resolver is provided.

        Without a resolver, render_engine may treat image/video values as URLs.
        To prevent SSRF, only trusted internal references are kept.
        """
        if media_url_resolver is not None:
            return delta_content

        delta = deepcopy(delta_content) if isinstance(delta_content, dict) else {"ops": []}
        ops = delta.get("ops")
        if not isinstance(ops, list):
            return {"ops": []}

        dropped = 0
        sanitized_ops = []
        for op in ops:
            if not isinstance(op, dict):
                continue
            insert = op.get("insert")
            if not isinstance(insert, dict):
                sanitized_ops.append(op)
                continue

            embed_type = None
            embed_value = None
            if "image" in insert:
                embed_type = "image"
                embed_value = insert.get("image")
            elif "video" in insert:
                embed_type = "video"
                embed_value = insert.get("video")

            if embed_type is None:
                sanitized_ops.append(op)
                continue

            if isinstance(embed_value, str) and cls._is_trusted_internal_media_reference(embed_value):
                sanitized_ops.append(op)
            else:
                dropped += 1

        if dropped:
            logger.warning(
                "Dropped %s untrusted media embed(s) from PDF delta without resolver.",
                dropped,
            )
        delta["ops"] = sanitized_ops
        return delta

    def generate_pdf(
        self,
        *,
        title: str,
        delta_content: dict,
        date: Optional[str] = None,
        location: Optional[str] = None,
        tags: Optional[str] = None,
        media_url_resolver: Optional[Callable[[str, str], str]] = None,
        base_url: Optional[str] = None,
    ) -> bytes:
        """
        Generate a PDF from an entry's Delta content.

        Args:
            title: Entry title
            delta_content: Quill Delta JSON content
            date: Optional formatted date string
            location: Optional location string
            tags: Optional comma-separated tags string
            media_url_resolver: Optional function to resolve media IDs to URLs
            base_url: Optional base URL for resolving relative URLs in the PDF

        Returns:
            PDF file as bytes

        Raises:
            Exception: If PDF generation fails
        """
        try:
            # Import WeasyPrint here to avoid import errors if not installed
            from weasyprint import HTML

            sanitized_delta = self._sanitize_delta_media_references_for_pdf(
                delta_content,
                media_url_resolver=media_url_resolver,
            )

            # Render Delta to HTML fragment
            content_html = render_delta_to_html(
                sanitized_delta,
                media_url_resolver=media_url_resolver,
                print_mode=True,
            )
            content_html = self._sanitize_html_for_template(content_html)

            # Load template
            template = self.jinja_env.get_template("pdf_export.html")

            # Render full HTML document
            html_content = template.render(
                title=title or "Untitled Entry",
                content=content_html,
                date=date,
                location=location,
                tags=tags,
            )

            # Generate PDF using WeasyPrint
            logger.info(
                "Generating PDF (title_length=%s, delta_ops=%s)",
                len(title or ""),
                len(sanitized_delta.get("ops", [])) if isinstance(sanitized_delta, dict) else 0,
            )
            html = (
                HTML(string=html_content, base_url=base_url)
                if base_url
                else HTML(string=html_content)
            )
            pdf_bytes = html.write_pdf()

            logger.info(f"PDF generated successfully, size: {len(pdf_bytes)} bytes")
            return pdf_bytes

        except ImportError as e:
            logger.error(f"WeasyPrint not installed: {e}")
            raise RuntimeError(
                "PDF generation requires WeasyPrint. "
                "Install with: pip install weasyprint"
            ) from e
        except Exception as e:
            logger.error(f"PDF generation failed: {e}", exc_info=True)
            raise

    def generate_pdf_stream(
        self,
        *,
        title: str,
        delta_content: dict,
        date: Optional[str] = None,
        location: Optional[str] = None,
        tags: Optional[str] = None,
        media_url_resolver: Optional[Callable[[str, str], str]] = None,
        base_url: Optional[str] = None,
    ) -> BytesIO:
        """
        Generate a PDF and return as BytesIO stream.

        Same as generate_pdf but returns a file-like object for streaming.

        Args:
            title: Entry title
            delta_content: Quill Delta JSON content
            date: Optional formatted date string
            location: Optional location string
            tags: Optional comma-separated tags string
            media_url_resolver: Optional function to resolve media IDs to URLs

        Returns:
            BytesIO stream containing PDF data
        """
        pdf_bytes = self.generate_pdf(
            title=title,
            delta_content=delta_content,
            date=date,
            location=location,
            tags=tags,
            media_url_resolver=media_url_resolver,
            base_url=base_url,
        )

        stream = BytesIO(pdf_bytes)
        stream.seek(0)
        return stream


class PDFEntryNotFoundError(Exception):
    """Raised when an entry is not found for PDF export."""


class EntryPDFService:
    """Service responsible for entry retrieval and PDF export orchestration."""

    def __init__(self, session: Session):
        self.session = session
        self.pdf_service = PDFService()

    @staticmethod
    def _get_base_url() -> str:
        return f"{settings.domain_scheme}://{settings.domain_name}".rstrip("/")

    @staticmethod
    def _extract_moment_metadata(
        moment: Optional[Moment],
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        if not moment:
            return None, None, None

        date_str = (
            moment.logged_date_tz.strftime("%B %d, %Y")
            if moment.logged_date_tz
            else None
        )
        tags_str = ", ".join(tag.name for tag in moment.tags) if moment.tags else None
        location_str = (
            moment.location_json.get("name")
            if isinstance(moment.location_json, dict)
            else None
        )
        return date_str, tags_str, location_str

    @staticmethod
    def _build_filename(entry: Entry, *, include_public_id: bool = False) -> str:
        raw_name = (
            entry.slug
            or (entry.public_id if include_public_id else None)
            or str(entry.id)[:8]
        )
        name = Path(str(raw_name)).name.replace("\\", "_").replace("/", "_")
        name = re.sub(r"[\x00-\x1f\x7f]+", "", name)
        name = name.replace("..", "_")
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(" .-_")
        if not name:
            name = str(entry.id)[:8]
        name = name[:100]
        return f"{name}.pdf"

    def _render_entry_pdf(
        self,
        *,
        entry: Entry,
        moment: Optional[Moment],
        delta_payload: dict,
        media_url_resolver: Optional[Callable[[str, str], str]] = None,
    ) -> BytesIO:
        date_str, tags_str, location_str = self._extract_moment_metadata(moment)
        return self.pdf_service.generate_pdf_stream(
            title=entry.title or "Untitled Entry",
            delta_content=delta_payload,
            date=date_str,
            location=location_str,
            tags=tags_str,
            media_url_resolver=media_url_resolver,
            base_url=self._get_base_url(),
        )

    def generate_owned_entry_pdf(
        self,
        *,
        entry_id: UUID,
        user_id: UUID,
    ) -> tuple[BytesIO, str]:
        entry = self.session.exec(
            select(Entry).where(Entry.id == entry_id, Entry.user_id == user_id)
        ).first()
        if not entry:
            raise PDFEntryNotFoundError("Entry not found or access denied")

        moment = self.session.get(Moment, entry.moment_id) if entry.moment_id else None
        delta_payload = entry.content_delta or {"ops": []}

        if entry.moment_id:
            moment_media = list(
                self.session.exec(
                    select(MomentMedia).where(MomentMedia.moment_id == entry.moment_id)
                ).all()
            )
            if moment_media:
                hydrated_delta = attach_signed_urls_to_delta(
                    delta_payload,
                    moment_media,
                    str(user_id),
                )
                if hydrated_delta is not None:
                    delta_payload = hydrated_delta

        pdf_stream = self._render_entry_pdf(
            entry=entry,
            moment=moment,
            delta_payload=delta_payload,
        )
        return pdf_stream, self._build_filename(entry)

    def generate_published_entry_pdf(self, *, identifier: str) -> tuple[BytesIO, str]:
        entry = self.session.exec(
            select(Entry).where(
                Entry.is_published == True,  # noqa: E712
                (col(Entry.public_id) == identifier) | (col(Entry.slug) == identifier),
            )
        ).first()
        if not entry:
            raise PDFEntryNotFoundError("Entry not found or not published")

        moment = self.session.get(Moment, entry.moment_id) if entry.moment_id else None

        def media_url_resolver(media_type: str, media_id: str) -> str:
            _ = media_type
            return f"/pub/media/{media_id}"

        pdf_stream = self._render_entry_pdf(
            entry=entry,
            moment=moment,
            delta_payload=entry.content_delta or {"ops": []},
            media_url_resolver=media_url_resolver,
        )
        return pdf_stream, self._build_filename(entry, include_public_id=True)
