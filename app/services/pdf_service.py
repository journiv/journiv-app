"""
PDF export service using WeasyPrint.

Converts journal entries to PDF format using the Delta-to-HTML render engine.
"""

import html
import logging
import re
import time
from copy import deepcopy
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import quote
from uuid import UUID

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlmodel import Session, col, select

from app.core.config import settings
from app.core.logging_config import LogCategory
from app.core.media_signing import (
    signed_url_for_immich,
    signed_url_for_journiv,
)
from app.models.entry import Entry
from app.models.moment import Moment, MomentMedia
from app.services.media_service import MediaService
from app.utils.quill_delta import extract_media_sources
from app.utils.render_engine import render_delta_to_html

logger = logging.getLogger(LogCategory.EXPORT)

# Template directory path
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
_MEDIA_ID_PATTERN = re.compile(
    r"([a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12})",
    re.IGNORECASE,
)


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

        if PDFService._contains_unsafe_html_elements(content_html):
            logger.warning(
                "Potentially unsafe HTML detected in PDF content; escaping content."
            )
            return f"<p>{html.escape(content_html)}</p>"

        return content_html

    @staticmethod
    def _contains_unsafe_html_elements(content_html: str) -> bool:
        """Inspect parsed HTML elements/attributes for unsafe constructs."""

        class _UnsafeHtmlDetector(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.found_unsafe = False
                self._blocked_tags = {"script", "iframe", "object", "embed", "link", "meta"}

            def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
                self._check(tag, attrs)

            def handle_startendtag(
                self, tag: str, attrs: list[tuple[str, Optional[str]]]
            ) -> None:
                self._check(tag, attrs)

            def _check(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
                if self.found_unsafe:
                    return

                tag_name = (tag or "").strip().lower()
                if tag_name in self._blocked_tags:
                    self.found_unsafe = True
                    return

                for attr_name, attr_value in attrs:
                    name = (attr_name or "").strip().lower()
                    value = (attr_value or "").strip().lower()

                    if name.startswith("on"):
                        self.found_unsafe = True
                        return
                    if value.startswith("javascript:") or value.startswith("vbscript:"):
                        self.found_unsafe = True
                        return
                    if value.startswith("data:text/html"):
                        self.found_unsafe = True
                        return

        parser = _UnsafeHtmlDetector()
        try:
            parser.feed(content_html)
            parser.close()
        except Exception:
            # Invalid markup in a `|safe` path is treated as unsafe.
            return True
        return parser.found_unsafe

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
        attachment_items: Optional[list[dict[str, Any]]] = None,
        media_url_resolver: Optional[Callable[[str, str], str]] = None,
        base_url: Optional[str] = None,
        suppress_media_types: Optional[set[str]] = None,
        media_preview_resolver: Optional[Callable[[str, str], Optional[str]]] = None,
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
                suppress_media_types=suppress_media_types,
                media_preview_resolver=media_preview_resolver,
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
                attachment_items=attachment_items or [],
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
        attachment_items: Optional[list[dict[str, Any]]] = None,
        media_url_resolver: Optional[Callable[[str, str], str]] = None,
        base_url: Optional[str] = None,
        suppress_media_types: Optional[set[str]] = None,
        media_preview_resolver: Optional[Callable[[str, str], Optional[str]]] = None,
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
            attachment_items=attachment_items,
            media_url_resolver=media_url_resolver,
            base_url=base_url,
            suppress_media_types=suppress_media_types,
            media_preview_resolver=media_preview_resolver,
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
        self.media_service = MediaService(session=session)

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

    @staticmethod
    def _extract_media_id(source: str, media_items: list[MomentMedia]) -> Optional[str]:
        if not isinstance(source, str):
            return None

        stripped = source.strip()
        if not stripped:
            return None

        media_ids = {str(item.id) for item in media_items if item.id}
        if stripped in media_ids:
            return stripped

        match = _MEDIA_ID_PATTERN.search(stripped)
        if match:
            candidate = match.group(1)
            if candidate in media_ids:
                return candidate

        return None

    def _resolve_local_media_uri(self, media: MomentMedia) -> Optional[str]:
        if not media.file_path:
            return None

        try:
            if media.media_type.value == "image" and media.display_path:
                root = self.media_service.media_root.resolve()
                display_full_path = (root / media.display_path).resolve()
                display_full_path.relative_to(root)
                if display_full_path.exists():
                    return display_full_path.as_uri()
        except Exception:
            logger.warning(
                "Failed to resolve display media path for PDF export",
                exc_info=True,
            )

        try:
            return self.media_service.get_media_file_path(media).as_uri()
        except Exception:
            logger.warning(
                "Failed to resolve local media path for PDF export",
                extra={"media_id": str(media.id)},
                exc_info=True,
            )
            return None

    def _resolve_local_thumbnail_uri(self, media: MomentMedia) -> Optional[str]:
        if not media.thumbnail_path:
            return None

        try:
            return self.media_service.get_media_thumbnail_path(media).as_uri()
        except Exception:
            logger.warning(
                "Failed to resolve local thumbnail path for PDF export",
                extra={"media_id": str(media.id)},
                exc_info=True,
            )
            return None

    def _build_media_url_resolver(
        self,
        *,
        media_items: list[MomentMedia],
        user_id: Optional[UUID] = None,
        public_fallback: bool = False,
        variant: str = "original",
    ) -> Callable[[str, str], str]:
        media_by_id = {str(item.id): item for item in media_items if item.id}
        base_url = self._get_base_url()
        if variant == "thumbnail":
            ttl_seconds = max(settings.media_thumbnail_signed_url_ttl_seconds, 300)
        else:
            ttl_seconds = max(settings.media_signed_url_ttl_seconds, 300)
        signed_url_expires_at = int(time.time()) + ttl_seconds

        def resolver(media_type: str, media_source: str) -> str:
            media_id = self._extract_media_id(media_source, media_items)
            if media_id:
                media = media_by_id.get(media_id)
                if media:
                    local_uri: Optional[str] = None
                    if variant == "thumbnail":
                        local_uri = self._resolve_local_thumbnail_uri(media)
                    elif media_type == "image":
                        local_uri = self._resolve_local_media_uri(media)
                    if local_uri:
                        return local_uri

                    if user_id is not None:
                        if media.external_provider == "immich" and media.external_asset_id:
                            return f"{base_url}{signed_url_for_immich(str(media.external_asset_id), str(user_id), variant, signed_url_expires_at)}"
                        return f"{base_url}{signed_url_for_journiv(media_id, str(user_id), variant, signed_url_expires_at)}"

                    if public_fallback:
                        if variant == "thumbnail":
                            return ""
                        return f"{base_url}/pub/media/{media_id}"

            if media_source.startswith("/"):
                return f"{base_url}{media_source}"

            return media_source

        return resolver

    def _collect_inline_media_ids(
        self,
        *,
        delta_payload: dict,
        media_items: list[MomentMedia],
    ) -> set[str]:
        inline_media_ids: set[str] = set()
        for source in extract_media_sources(delta_payload):
            media_id = self._extract_media_id(source, media_items)
            if media_id:
                inline_media_ids.add(media_id)
        return inline_media_ids

    def _collect_attachment_items(
        self,
        *,
        delta_payload: dict,
        media_items: list[MomentMedia],
        media_url_resolver: Optional[Callable[[str, str], str]],
        thumbnail_url_resolver: Optional[Callable[[str, str], str]] = None,
    ) -> list[dict[str, Any]]:
        if media_url_resolver is None:
            return []

        inline_media_ids = self._collect_inline_media_ids(
            delta_payload=delta_payload,
            media_items=media_items,
        )
        items: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for media in media_items:
            media_type_value = getattr(media.media_type, "value", str(media.media_type)).lower()
            if not media.id:
                continue
            media_id = str(media.id)
            is_inline = media_id in inline_media_ids

            try:
                source_url = media_url_resolver(media_type_value, media_id)
            except Exception:
                logger.warning(
                    "Failed to resolve media attachment for PDF export",
                    extra={"media_id": media_id},
                    exc_info=True,
                )
                continue

            if not source_url:
                continue

            if media_type_value in {"image", "video"} and is_inline:
                continue

            key = (media_type_value, source_url)
            if key in seen:
                continue
            seen.add(key)

            item: dict[str, Any] = {
                "kind": media_type_value,
                "url": source_url,
                "label": media.original_filename or f"{media_type_value.title()} attachment",
                "alt_text": media.alt_text or "",
            }

            if media_type_value == "video" and thumbnail_url_resolver is not None:
                try:
                    preview_url = thumbnail_url_resolver("video", media_id)
                except Exception:
                    preview_url = None
                if preview_url:
                    item["preview_url"] = preview_url

            items.append(item)

        return items

    def _render_entry_pdf(
        self,
        *,
        entry: Entry,
        moment: Optional[Moment],
        delta_payload: dict,
        attachment_items: Optional[list[dict[str, Any]]] = None,
        media_url_resolver: Optional[Callable[[str, str], str]] = None,
        suppress_media_types: Optional[set[str]] = None,
        media_preview_resolver: Optional[Callable[[str, str], Optional[str]]] = None,
    ) -> BytesIO:
        date_str, tags_str, location_str = self._extract_moment_metadata(moment)
        return self.pdf_service.generate_pdf_stream(
            title=entry.title or "Untitled Entry",
            delta_content=delta_payload,
            date=date_str,
            location=location_str,
            tags=tags_str,
            attachment_items=attachment_items,
            media_url_resolver=media_url_resolver,
            base_url=self._get_base_url(),
            suppress_media_types=suppress_media_types,
            media_preview_resolver=media_preview_resolver,
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
        media_url_resolver: Optional[Callable[[str, str], str]] = None
        attachment_items: list[dict[str, Any]] = []
        suppress_media_types = {"audio"}
        media_preview_resolver: Optional[Callable[[str, str], Optional[str]]] = None

        if entry.moment_id:
            moment_media = list(
                self.session.exec(
                    select(MomentMedia).where(MomentMedia.moment_id == entry.moment_id)
                ).all()
            )
            if moment_media:
                media_url_resolver = self._build_media_url_resolver(
                    media_items=moment_media,
                    user_id=user_id,
                )
                thumbnail_url_resolver = self._build_media_url_resolver(
                    media_items=moment_media,
                    user_id=user_id,
                    variant="thumbnail",
                )
                media_preview_resolver = thumbnail_url_resolver
                attachment_items = self._collect_attachment_items(
                    delta_payload=delta_payload,
                    media_items=moment_media,
                    media_url_resolver=media_url_resolver,
                    thumbnail_url_resolver=thumbnail_url_resolver,
                )

        pdf_stream = self._render_entry_pdf(
            entry=entry,
            moment=moment,
            delta_payload=delta_payload,
            attachment_items=attachment_items,
            media_url_resolver=media_url_resolver,
            suppress_media_types=suppress_media_types,
            media_preview_resolver=media_preview_resolver,
        )
        return pdf_stream, self._build_filename(entry)

    def generate_published_entry_pdf(self, *, identifier: str) -> tuple[BytesIO, str]:
        entry = self.session.exec(
            select(Entry).where(
                col(Entry.is_published).is_(True),
                col(Entry.public_id) == identifier,
            )
        ).first()
        if not entry:
            entry = self.session.exec(
                select(Entry).where(
                    col(Entry.is_published).is_(True),
                    col(Entry.slug) == identifier,
                )
            ).first()
        if not entry:
            raise PDFEntryNotFoundError("Entry not found or not published")

        moment = self.session.get(Moment, entry.moment_id) if entry.moment_id else None
        media_url_resolver: Optional[Callable[[str, str], str]] = None
        attachment_items: list[dict[str, Any]] = []
        suppress_media_types = {"audio"}
        media_preview_resolver: Optional[Callable[[str, str], Optional[str]]] = None
        if entry.moment_id:
            moment_media = list(
                self.session.exec(
                    select(MomentMedia).where(MomentMedia.moment_id == entry.moment_id)
                ).all()
            )
            if moment_media:
                media_url_resolver = self._build_media_url_resolver(
                    media_items=moment_media,
                    public_fallback=True,
                )
                thumbnail_url_resolver = self._build_media_url_resolver(
                    media_items=moment_media,
                    public_fallback=True,
                    variant="thumbnail",
                )
                media_preview_resolver = thumbnail_url_resolver
                attachment_items = self._collect_attachment_items(
                    delta_payload=entry.content_delta or {"ops": []},
                    media_items=moment_media,
                    media_url_resolver=media_url_resolver,
                    thumbnail_url_resolver=thumbnail_url_resolver,
                )

        pdf_stream = self._render_entry_pdf(
            entry=entry,
            moment=moment,
            delta_payload=entry.content_delta or {"ops": []},
            attachment_items=attachment_items,
            media_url_resolver=media_url_resolver,
            suppress_media_types=suppress_media_types,
            media_preview_resolver=media_preview_resolver,
        )
        return pdf_stream, self._build_filename(entry, include_public_id=True)
