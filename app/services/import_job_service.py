"""
Service for managing Immich import jobs.
Handles both link-only and copy mode imports.
"""
import asyncio
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

import aiofiles
import aiofiles.os
import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, col, select

from app.core.encryption import decrypt_token
from app.core.http_client import get_http_client
from app.core.logging_config import log_error, log_info, log_warning
from app.core.media_signing import normalize_delta_media_ids
from app.core.scoped_cache import ScopedCache
from app.integrations import immich
from app.models.entry import Entry
from app.models.enums import ImportSourceType, JobStatus, MediaType, UploadStatus
from app.models.import_job import ImportJob
from app.models.integration import ImportMode, Integration, IntegrationProvider
from app.models.moment import Moment, MomentMedia
from app.models.user import User
from app.services.media_service import MediaService
from app.utils.quill_delta import extract_plain_text

# Batch size for parallel downloads (configurable in future)
COPY_MODE_BATCH_SIZE = 3

# Media type mapping from Immich asset types
IMMICH_TYPE_TO_MEDIA_TYPE = {
    "IMAGE": MediaType.IMAGE,
    "VIDEO": MediaType.VIDEO,
    "AUDIO": MediaType.AUDIO,
}

# Shared cache instance
_normalize_cache: Optional[ScopedCache] = None


def _map_immich_type_to_media_type(immich_type: str) -> MediaType:
    """Map Immich asset type to MediaType enum."""
    return IMMICH_TYPE_TO_MEDIA_TYPE.get(immich_type, MediaType.UNKNOWN)


class ImportJobService:
    """Service for managing Immich import jobs (supports both link-only and copy modes)."""

    def __init__(self, session: Session):
        global _normalize_cache
        self.session = session
        self.media_service = MediaService(session)
        self._immich_provider = "immich"
        if _normalize_cache is None:
            _normalize_cache = ScopedCache("immich_entry_normalize")
        self._normalize_cache = _normalize_cache

    def _maybe_normalize_entry_delta(
        self,
        moment_id: Optional[uuid.UUID],
        session: Session,
        *,
        debounce_seconds: int = 2,
        commit: bool = False,
    ) -> None:
        """
        Normalize entry delta if needed (syncs media IDs between delta and MomentMedia).

        Args:
            moment_id: The ID of the moment whose entry delta should be normalized.
            session: The database session to use.
            debounce_seconds: Minimum time in seconds between normalizations for same entry.
            commit: Whether to commit the session after adding changes.
                    Default is False to allow batching transactions.
        """
        if moment_id is None:
            return
        cache_key = str(moment_id)
        cached = self._normalize_cache.get(cache_key, "debounce") or {}
        last_ts = cached.get("ts")
        now = time.time()
        if isinstance(last_ts, (int, float)) and now - last_ts < debounce_seconds:
            return

        self._normalize_cache.set(cache_key, "debounce", {"ts": now}, ttl_seconds=debounce_seconds)

        # Find the entry associated with this moment
        entry = session.exec(
            select(Entry).where(Entry.moment_id == moment_id)
        ).first()
        if not entry or not entry.content_delta:
            return

        media_items = session.exec(
            select(MomentMedia).where(MomentMedia.moment_id == moment_id)
        ).all()
        # Expunge media items from session so they are not flushed on commit.
        # We only need them for reading (mapping asset IDs to media UUIDs).
        # Without this, a concurrent session (e.g. Celery worker) updating
        # file_path would be overwritten when this session commits.
        for m in media_items:
            session.expunge(m)
        normalized = normalize_delta_media_ids(entry.content_delta, list(media_items))
        if normalized != entry.content_delta:
            entry.content_delta = normalized
            plain_text = extract_plain_text(normalized)
            entry.content_plain_text = plain_text or None
            entry.word_count = len(plain_text.split()) if plain_text else 0
            session.add(entry)
            if commit:
                session.commit()

    def _get_existing_external_media(
        self,
        moment_id: uuid.UUID,
        asset_id: str,
        session: Optional[Session] = None
    ) -> Optional[MomentMedia]:
        active_session = session or self.session
        return active_session.exec(
            select(MomentMedia)
            .where(MomentMedia.moment_id == moment_id)
            .where(MomentMedia.external_provider == self._immich_provider)
            .where(MomentMedia.external_asset_id == asset_id)
        ).first()

    @staticmethod
    def _normalize_asset_ids(asset_ids: Iterable[str]) -> list[str]:
        """Normalize asset IDs for deterministic comparisons."""
        normalized = []
        for asset_id in asset_ids:
            value = str(asset_id).strip()
            if value:
                normalized.append(value)
        return sorted(set(normalized))

    def get_active_immich_job_for_assets(
        self,
        user_id: uuid.UUID,
        moment_id: uuid.UUID,
        asset_ids: list[str],
    ) -> Optional[ImportJob]:
        """
        Return an active Immich job with the same asset set for this moment, if it exists.

        Active statuses are PENDING and RUNNING.
        """
        requested_assets = self._normalize_asset_ids(asset_ids)
        if not requested_assets:
            return None

        active_jobs = self.session.exec(
            select(ImportJob)
            .where(ImportJob.user_id == user_id)
            .where(ImportJob.moment_id == moment_id)
            .where(ImportJob.source_type == ImportSourceType.IMMICH)
            .where(col(ImportJob.status).in_([JobStatus.PENDING, JobStatus.RUNNING]))
            .order_by(col(ImportJob.created_at).desc())
        ).all()

        for job in active_jobs:
            raw_assets = (job.result_data or {}).get("asset_ids")
            if not isinstance(raw_assets, list):
                continue
            if self._normalize_asset_ids(raw_assets) == requested_assets:
                return job
        return None

    def _resolve_media_type_from_asset(self, asset_type: Optional[str]) -> MediaType:
        return _map_immich_type_to_media_type(asset_type or "OTHER")

    def _extract_immich_metadata(self, asset_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract and normalize metadata from Immich asset data.
        Returns a dictionary with normalized fields.
        """
        exif_info = asset_data.get("exifInfo") or {}

        # Determine media type
        immich_type = asset_data.get("type", "OTHER")
        media_type = _map_immich_type_to_media_type(immich_type)

        # Parse taken_at
        taken_at_str = exif_info.get("dateTimeOriginal") or asset_data.get("createdAt")
        taken_at = None
        if taken_at_str:
            try:
                taken_at = datetime.fromisoformat(taken_at_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError) as e:
                log_warning(f"Failed to parse date: {e}")

        # Extract dimensions and duration
        width = exif_info.get("exifImageWidth") or asset_data.get("width")
        height = exif_info.get("exifImageHeight") or asset_data.get("height")
        duration = self._parse_duration_seconds(asset_data.get("duration"))
        file_size = exif_info.get("fileSizeInByte") or asset_data.get("fileSizeInByte")

        # Get filename and mime type
        filename = (
            asset_data.get("originalFileName") or
            asset_data.get("originalPath") or
            f"Asset {str(asset_data.get('id', ''))[:8]}"
        )
        mime_type = asset_data.get("mimeType") or "application/octet-stream"

        # Build external metadata
        external_metadata = {
            "type": immich_type,
            "mimeType": mime_type,
            "thumbUrl": asset_data.get("thumbUrl") or f"/api/v1/integrations/immich/proxy/{asset_data.get('id')}/thumbnail",
            "width": width,
            "height": height,
            "exif": exif_info
        }

        return {
            "media_type": media_type,
            "taken_at": taken_at,
            "width": width,
            "height": height,
            "duration": duration,
            "file_size": file_size,
            "original_filename": filename,
            "mime_type": mime_type,
            "external_metadata": external_metadata
        }

    def _upsert_entry_media(
        self,
        moment_id: uuid.UUID,
        user_id: uuid.UUID,
        asset_id: str,
        asset_data: Optional[Dict[str, Any]] = None,
        file_info: Optional[Dict[str, Any]] = None,
        upload_status: UploadStatus = UploadStatus.PROCESSING,
        session: Optional[Session] = None,
        commit: bool = True
    ) -> MomentMedia:
        """
        Create or update MomentMedia for an external asset.
        """
        active_session = session or self.session
        existing = self._get_existing_external_media(moment_id, asset_id, session=active_session)

        # Extract normalized metadata if asset_data is provided
        metadata = self._extract_immich_metadata(asset_data) if asset_data else {}

        # Combine if we have file_info from local save
        file_path = (file_info or {}).get("file_path")
        file_size = (file_info or {}).get("file_size") or metadata.get("file_size")
        checksum = (file_info or {}).get("checksum")
        thumbnail_path = (file_info or {}).get("thumbnail_path")
        display_path = (file_info or {}).get("display_path")

        if existing:
            # Update existing record
            if metadata.get("media_type") and existing.media_type == MediaType.UNKNOWN:
                existing.media_type = metadata["media_type"]

            if metadata.get("original_filename"):
                existing.original_filename = metadata["original_filename"]

            if metadata.get("taken_at"):
                existing.external_created_at = metadata["taken_at"]

            if metadata.get("mime_type"):
                existing.mime_type = metadata["mime_type"]

            if metadata.get("external_metadata"):
                if not existing.external_metadata:
                    existing.external_metadata = metadata["external_metadata"]
                else:
                    existing.external_metadata = {**existing.external_metadata, **metadata["external_metadata"]}

            if file_path:
                existing.file_path = file_path
            if file_size:
                existing.file_size = file_size
            if checksum:
                existing.checksum = checksum
            if thumbnail_path:
                existing.thumbnail_path = thumbnail_path
            if display_path:
                existing.display_path = display_path

            existing.upload_status = upload_status

            active_session.add(existing)
            if commit:
                active_session.commit()
                active_session.refresh(existing)
            return existing

        # Create new record directly with moment_id
        media = MomentMedia(
            moment_id=moment_id,
            media_type=metadata.get("media_type", MediaType.UNKNOWN),
            file_path=file_path,
            file_size=file_size,
            original_filename=metadata.get("original_filename") or f"Immich asset {asset_id[:8]}",
            mime_type=metadata.get("mime_type") or "application/octet-stream",
            thumbnail_path=thumbnail_path,
            display_path=display_path,
            checksum=checksum,
            duration=metadata.get("duration"),
            width=metadata.get("width"),
            height=metadata.get("height"),
            alt_text=f"Immich asset: {metadata.get('original_filename', asset_id)}",
            upload_status=upload_status,
            external_provider=self._immich_provider,
            external_asset_id=asset_id,
            external_created_at=metadata.get("taken_at"),
            external_metadata=metadata.get("external_metadata", {}),
        )

        active_session.add(media)
        if commit:
            active_session.commit()
            active_session.refresh(media)

        log_info(f"Media added to moment {moment_id} for user {user_id}: {media.id}")

        # Trigger addition to Immich album only for committed records.
        if (
            commit
            and media.external_provider == "immich"
            and not media.file_path
            and media.external_asset_id
        ):
            try:
                from app.core.celery_app import celery_app
                celery_app.send_task(
                    "app.integrations.tasks.add_assets_to_album_task",
                    args=[str(user_id), "immich", [media.external_asset_id]]
                )
            except Exception as exc:
                log_warning(f"Failed to trigger album asset addition task: {exc}")

        return media

    def create_placeholder_media(
        self,
        moment_id: uuid.UUID,
        user_id: uuid.UUID,
        asset_id: str,
        integration: Integration,
        asset_payload: Optional[Any] = None,
        session: Optional[Session] = None,
        commit: bool = True,
    ) -> MomentMedia:
        """
        Create a placeholder MomentMedia record for an Immich asset.
        """
        asset_data = None
        if asset_payload:
            # Handle both dict and object (Pydantic/etc)
            if hasattr(asset_payload, "dict"):
                asset_data = asset_payload.dict()
            elif isinstance(asset_payload, dict):
                asset_data = asset_payload
            else:
                # Fallback: try to extract common fields if it's an object
                asset_data = {
                    "id": asset_id,
                    "type": getattr(asset_payload, "type", None),
                    "title": getattr(asset_payload, "title", None),
                    "taken_at": getattr(asset_payload, "taken_at", None),
                    "thumbUrl": getattr(asset_payload, "thumb_url", None),
                    "originalUrl": getattr(asset_payload, "original_url", None),
                    "metadata": getattr(asset_payload, "metadata", None),
                }

        upload_status = (
            UploadStatus.COMPLETED
            if integration.import_mode == ImportMode.LINK_ONLY
            else UploadStatus.PROCESSING
        )

        return self._upsert_entry_media(
            moment_id=moment_id,
            user_id=user_id,
            asset_id=asset_id,
            asset_data=asset_data,
            upload_status=upload_status,
            session=session,
            commit=commit,
        )

    def _mark_media_failed(
        self,
        moment_id: Optional[uuid.UUID],
        asset_id: str,
        session: Session,
        error_message: Optional[str] = None,
        commit: bool = True
    ) -> None:
        if moment_id is None:
            return
        media = self._get_existing_external_media(moment_id, asset_id, session=session)
        if not media:
            return
        media.upload_status = UploadStatus.FAILED
        if error_message:
            media.processing_error = error_message[:1000]
        session.add(media)
        if commit:
            session.commit()

    def create_job(
        self,
        user_id: uuid.UUID,
        moment_id: uuid.UUID,
        asset_ids: list[str],
        *,
        commit: bool = True,
    ) -> ImportJob:
        """
        Create a new import job record for Immich.
        """
        existing_job = self.get_active_immich_job_for_assets(
            user_id=user_id,
            moment_id=moment_id,
            asset_ids=asset_ids,
        )
        if existing_job is not None:
            log_info(
                "Reusing existing active Immich import job",
                user_id=str(user_id),
                moment_id=str(moment_id),
                job_id=str(existing_job.id),
            )
            return existing_job

        job = ImportJob(
            user_id=user_id,
            moment_id=moment_id,
            source_type=ImportSourceType.IMMICH,
            result_data={"asset_ids": asset_ids},
            total_items=len(asset_ids),
            status=JobStatus.PENDING
        )
        self.session.add(job)
        if commit:
            self.session.commit()
            self.session.refresh(job)

        log_info(
            f"Created Immich import job {job.id} for user {user_id}: "
            f"{len(asset_ids)} assets to moment {moment_id}"
        )

        return job

    def get_job(self, job_id: uuid.UUID, user_id: uuid.UUID) -> Optional[ImportJob]:
        """
        Get import job by ID and user ID.
        """
        return self.session.exec(
            select(ImportJob)
            .where(ImportJob.id == job_id)
            .where(ImportJob.user_id == user_id)
        ).first()



    async def _fetch_with_retry(
        self,
        url: str,
        headers: Dict[str, str],
        method: str = "GET",
        json_data: Optional[Dict[str, Any]] = None,
        max_retries: int = 2,
        timeout: float = 30.0
    ) -> Optional[httpx.Response]:
        """
        Generic HTTP request helper with exponential backoff retry logic.
        """
        for attempt in range(max_retries + 1):
            try:
                client = await get_http_client()
                if method == "GET":
                    response = await client.get(url, headers=headers, timeout=timeout)
                elif method == "POST":
                    response = await client.post(url, headers=headers, json=json_data, timeout=timeout)
                else:
                    raise ValueError(f"Unsupported method: {method}")

                if response.status_code in (401, 403):
                    log_error(f"Authentication failed for {url}: {response.status_code}")
                    return response

                if response.status_code == 404:
                    return response

                # Retry on transient errors (5xx)
                if response.status_code >= 500 and attempt < max_retries:
                    wait_time = 2 ** attempt
                    log_warning(f"Retry {attempt + 1}/{max_retries} for {url} after {wait_time}s (server error {response.status_code})")
                    await asyncio.sleep(wait_time)
                    continue

                response.raise_for_status()
                return response

            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    log_warning(f"Retry {attempt + 1}/{max_retries} for {url} after {wait_time}s ({type(e).__name__})")
                    await asyncio.sleep(wait_time)
                    continue
                log_error(f"Final failure for {url} after {max_retries + 1} attempts: {e}")
            except Exception as e:
                log_error(f"Unexpected error for {url}: {e}")
                if attempt < max_retries:
                    continue
                break
        return None

    @staticmethod
    async def _save_bytes_to_path(content: bytes, target_path: Path) -> None:
        """Write bytes to a target path atomically via a temp file."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target_path.with_suffix(".tmp")
        async with aiofiles.open(tmp_path, "wb") as f:
            await f.write(content)
            await f.flush()
        await aiofiles.os.rename(tmp_path, target_path)

    def _create_link_only_media(
        self,
        moment_id: uuid.UUID,
        user_id: uuid.UUID,
        asset_id: str,
        asset_metadata: dict,
        integration: Integration,
        session: Optional[Session] = None,
        commit: bool = True
    ):
        """
        Create or update MomentMedia record for link-only Immich asset.
        """
        media = self._upsert_entry_media(
            moment_id=moment_id,
            user_id=user_id,
            asset_id=asset_id,
            asset_data=asset_metadata,
            upload_status=UploadStatus.COMPLETED,
            session=session,
            commit=commit
        )
        log_info(f"Updated link-only MomentMedia for Immich asset {asset_id}")
        return media

    async def create_and_process_job_async(
        self,
        user_id: uuid.UUID,
        moment_id: uuid.UUID,
        asset_ids: list[str],
        assets: Optional[list[Any]] = None
    ) -> ImportJob:
        """
        Create an import job for async processing (copy mode).

        Creates placeholder media records first, then the job.
        """
        from app.core.database import engine

        # Use a short-lived session for placeholder + job creation to avoid blocking on long-lived transactions from entry updates.
        thread_session = Session(engine)
        try:
            thread_service = ImportJobService(thread_session)

            # Fetch integration needed for placeholders
            integration = thread_session.exec(
                select(Integration)
                .where(Integration.user_id == user_id)
                .where(Integration.provider == IntegrationProvider.IMMICH)
            ).first()

            if not integration:
                raise ValueError("Immich integration not found")

            existing_job = thread_service.get_active_immich_job_for_assets(
                user_id=user_id,
                moment_id=moment_id,
                asset_ids=asset_ids,
            )
            if existing_job is not None:
                log_info(
                    "Skipping duplicate Immich import request; active job exists",
                    user_id=str(user_id),
                    moment_id=str(moment_id),
                    job_id=str(existing_job.id),
                )
                return existing_job

            assets_by_id = {}
            if assets:
                assets_by_id = {
                    (asset.id if hasattr(asset, "id") else asset.get("id")): asset
                    for asset in assets
                }
            for asset_id in asset_ids:
                try:
                    thread_service.create_placeholder_media(
                        moment_id=moment_id,
                        user_id=user_id,
                        asset_id=asset_id,
                        integration=integration,
                        asset_payload=assets_by_id.get(asset_id),
                        session=thread_session,
                        commit=False,
                    )
                except Exception as e:
                    log_warning(f"Failed to create placeholder for {asset_id}: {e}")
                    # Continue - job will try to process anyway

            job = thread_service.create_job(
                user_id=user_id,
                moment_id=moment_id,
                asset_ids=asset_ids,
                commit=False,
            )
            thread_session.commit()
            thread_session.refresh(job)
            return job
        except SQLAlchemyError as exc:
            thread_session.rollback()
            log_error(exc)
            raise
        finally:
            thread_session.close()

    async def process_copy_job_async(
        self,
        job_id: uuid.UUID
    ) -> None:
        """
        Background task to process copy-mode import job.

        Two-phase approach:
        1. Phase 1: Download thumbnails in parallel batches (for quick UI display)
        2. Phase 2: Download originals in parallel batches
        """
        from app.core.database import engine

        # Create new session for background task
        thread_session = Session(engine)
        job: ImportJob | None = None
        try:
            thread_service = ImportJobService(thread_session)
            # Fetch job
            job = thread_session.exec(
                select(ImportJob)
                .where(ImportJob.id == job_id)
            ).first()

            if not job:
                log_error(f"Import job {job_id} not found")
                return

            if job.moment_id is None:
                raise ValueError(f"Import job {job_id} missing moment_id")

            # Mark as processing
            job.mark_running()
            thread_session.add(job)
            thread_session.commit()

            log_info(
                f"Processing copy-mode import job {job_id}: "
                f"{job.total_items} assets"
            )

            # Get user and integration
            user = thread_session.get(User, job.user_id)
            if not user:
                raise ValueError(f"User {job.user_id} not found")

            integration = thread_session.exec(
                select(Integration)
                .where(Integration.user_id == job.user_id)
                .where(Integration.provider == IntegrationProvider.IMMICH)
            ).first()

            if not integration or not integration.is_active:
                raise ValueError("Immich integration not active")

            # Decrypt API key
            api_key = decrypt_token(integration.access_token_encrypted)
            base_url = integration.base_url.rstrip('/')

            # Get asset IDs
            result_data = job.result_data or {}
            asset_ids = result_data.get("asset_ids", [])

            # Phase 1: Download thumbnails in parallel batches
            thumbnail_cache = await thread_service._process_thumbnail_phase(
                job=job,
                asset_ids=asset_ids,
                base_url=base_url,
                api_key=api_key,
                integration=integration,
                session=thread_session
            )

            # Phase 2: Download originals in parallel batches
            # Only creates MomentMedia if original succeeds (with thumbnail if available)
            await thread_service._process_original_phase(
                job=job,
                asset_ids=asset_ids,
                base_url=base_url,
                api_key=api_key,
                integration=integration,
                session=thread_session,
                thumbnail_cache=thumbnail_cache
            )

            # Final status update
            if job.failed_items == 0 and job.status not in {JobStatus.FAILED, JobStatus.PARTIAL, JobStatus.CANCELLED}:
                job.mark_completed()
            thread_session.add(job)
            thread_session.commit()

            log_info(
                f"Copy-mode import job {job_id} completed: "
                f"{job.processed_items} succeeded, {job.failed_items} failed"
            )

        except Exception as e:
            log_error(e)
            if job is not None:
                job.mark_failed(str(e)[:2000])
                thread_session.add(job)
                thread_session.commit()
        finally:
            thread_session.close()

    async def process_link_only_job_async(
        self,
        job_id: uuid.UUID
    ) -> None:
        """
        Background task to process link-only import jobs.

        Fetches metadata from Immich and updates placeholder MomentMedia records.
        """
        from app.core.database import engine

        thread_session = Session(engine)
        job: ImportJob | None = None
        try:
            thread_service = ImportJobService(thread_session)
            job = thread_session.exec(
                select(ImportJob)
                .where(ImportJob.id == job_id)
            ).first()

            if not job:
                log_error(f"Import job {job_id} not found")
                return

            if job.moment_id is None:
                raise ValueError(f"Import job {job_id} missing moment_id")

            job.mark_running()
            thread_session.add(job)
            thread_session.commit()

            user = thread_session.get(User, job.user_id)
            if not user:
                raise ValueError(f"User {job.user_id} not found")

            integration = thread_session.exec(
                select(Integration)
                .where(Integration.user_id == job.user_id)
                .where(Integration.provider == IntegrationProvider.IMMICH)
            ).first()

            if not integration or not integration.is_active:
                raise ValueError("Immich integration not active")

            api_key = decrypt_token(integration.access_token_encrypted)
            base_url = integration.base_url.rstrip('/')
            result_data = job.result_data or {}
            asset_ids = result_data.get("asset_ids", [])

            processed = 0
            failed = 0
            failed_asset_ids = []

            for asset_id in asset_ids:
                try:
                    asset_metadata = await immich.get_asset_info(
                        base_url=base_url,
                        api_key=api_key,
                        asset_id=asset_id
                    )

                    if asset_metadata:
                        thread_service._create_link_only_media(
                            moment_id=job.moment_id,
                            user_id=job.user_id,
                            asset_id=asset_id,
                            asset_metadata=asset_metadata,
                            integration=integration,
                            session=thread_session,
                            commit=False
                        )
                        thread_service._maybe_normalize_entry_delta(job.moment_id, thread_session, commit=False)
                        processed += 1
                    else:
                        thread_service._mark_media_failed(job.moment_id, asset_id, thread_session, commit=False)
                        failed += 1
                        failed_asset_ids.append(asset_id)
                except Exception as e:
                    log_error(e)
                    thread_service._mark_media_failed(job.moment_id, asset_id, thread_session, str(e), commit=False)
                    failed += 1
                    failed_asset_ids.append(asset_id)

                job.update_progress(processed, len(asset_ids), failed)
                thread_session.add(job)
                thread_session.commit()

            if failed_asset_ids:
                if job.result_data is None:
                    job.result_data = {}
                job.result_data["failed_asset_ids"] = failed_asset_ids

            if job.failed_items == 0 and job.status not in {JobStatus.FAILED, JobStatus.PARTIAL, JobStatus.CANCELLED}:
                job.mark_completed()
            thread_session.add(job)
            thread_session.commit()

        except Exception as e:
            log_error(e)
            if job is not None:
                job.mark_failed(str(e))
                thread_session.add(job)
                thread_session.commit()
        finally:
            thread_session.close()



    async def _process_thumbnail_phase(
        self,
        job: ImportJob,
        asset_ids: list[str],
        base_url: str,
        api_key: str,
        integration: Integration,
        session: Session
    ) -> dict:
        """
        Phase 1: Download thumbnails in parallel batches.

        Downloads and saves thumbnails for quick UI display.
        Does NOT create MomentMedia records yet - that happens in Phase 2 only if original succeeds.
        """
        if job.moment_id is None:
            raise ValueError(f"Import job {job.id} missing moment_id")

        moment_id = job.moment_id
        batch_size = COPY_MODE_BATCH_SIZE
        thumbnail_cache = {}

        for i in range(0, len(asset_ids), batch_size):
            batch = asset_ids[i:i + batch_size]
            tasks = [
                self._download_and_save_thumbnail(
                    asset_id=asset_id,
                    base_url=base_url,
                    api_key=api_key,
                    user_id=str(job.user_id),
                    moment_id=moment_id,
                    integration=integration,
                    session=session
                )
                for asset_id in batch
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for asset_id, result in zip(batch, results, strict=False):
                if isinstance(result, Exception):
                    log_error(result)
                    # Record error but don't fail yet - original might succeed
                    thumbnail_cache[asset_id] = None
                elif result and result[0] and result[1]:
                    # Thumbnail downloaded successfully - cache for Phase 2
                    thumbnail_path, asset_metadata = result
                    thumbnail_cache[asset_id] = (thumbnail_path, asset_metadata)
                else:
                    thumbnail_cache[asset_id] = None

        return thumbnail_cache

    async def _process_original_phase(
        self,
        job: ImportJob,
        asset_ids: list[str],
        base_url: str,
        api_key: str,
        integration: Integration,
        session: Session,
        thumbnail_cache: dict
    ) -> None:
        """
        Phase 2: Download originals in parallel batches.

        Creates MomentMedia records ONLY if original download succeeds.
        Includes thumbnail_path if thumbnail was downloaded in Phase 1.

        Each parallel task gets its own DB session to prevent
        race conditions when persisting MomentMedia records.
        """
        from app.core.database import engine

        if job.moment_id is None:
            raise ValueError(f"Import job {job.id} missing moment_id")

        moment_id = job.moment_id
        batch_size = COPY_MODE_BATCH_SIZE

        async def _process_single_asset(current_asset_id: str):
            with Session(engine) as task_session:
                task_service = ImportJobService(task_session)
                return await task_service._download_and_save_original(
                    asset_id=current_asset_id,
                    base_url=base_url,
                    api_key=api_key,
                    user_id=str(job.user_id),
                    moment_id=moment_id,
                    integration=integration,
                    session=task_session,
                    thumbnail_info=thumbnail_cache.get(current_asset_id),
                    commit=True
                )

        for i in range(0, len(asset_ids), batch_size):
            batch = asset_ids[i:i + batch_size]
            tasks = [
                _process_single_asset(asset_id)
                for asset_id in batch
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            processed = 0
            failed = 0
            for asset_id, result in zip(batch, results, strict=False):
                if isinstance(result, Exception):
                    log_error(result)
                    self._mark_media_failed(job.moment_id, asset_id, session, str(result), commit=False)
                    failed += 1
                elif result is None:
                    self._mark_media_failed(job.moment_id, asset_id, session, commit=False)
                    failed += 1
                else:
                    processed += 1
                    self._maybe_normalize_entry_delta(job.moment_id, session, commit=False)

            # Update job progress after each batch and commit to ensure persistence
            job.update_progress(job.processed_items + processed, job.total_items, job.failed_items + failed)
            session.add(job)
            session.commit()

    async def _download_and_save_thumbnail(
        self,
        asset_id: str,
        base_url: str,
        api_key: str,
        user_id: str,
        moment_id: uuid.UUID,
        integration: Integration,
        session: Session
    ) -> Tuple[Optional[bytes], Optional[dict]]:
        """
        Download thumbnail from Immich.
        Returns thumbnail content and metadata for Phase 2 to save with correct filename.
        """
        asset_metadata: Optional[dict] = None
        try:
            # Fetch asset metadata
            asset_metadata = await immich.get_asset_info(base_url, api_key, asset_id)
            if not asset_metadata:
                return None, None

            # Download thumbnail
            response = await self._fetch_with_retry(
                f"{base_url}/api/assets/{asset_id}/thumbnail",
                headers={"x-api-key": api_key},
                timeout=30.0
            )

            if not response or response.status_code != 200:
                log_warning(f"Failed to download thumbnail for asset {asset_id}")
                return None, asset_metadata

            thumbnail_content = response.content
            log_info(f"Downloaded thumbnail for asset {asset_id}")
            return thumbnail_content, asset_metadata

        except Exception as e:
            log_error(f"Error in _download_and_save_thumbnail for {asset_id}: {e}")
            return None, asset_metadata

    async def _download_and_save_original(
        self,
        asset_id: str,
        base_url: str,
        api_key: str,
        user_id: str,
        moment_id: uuid.UUID,
        integration: Integration,
        session: Session,
        thumbnail_info: Optional[Tuple[Optional[bytes], Optional[dict]]] = None,
        commit: bool = True
    ) -> Optional[dict]:
        """
        Download original asset from Immich and save to local storage.
        If thumbnail_info is provided, saves thumbnail with Journiv naming convention.
        """
        try:
            # Get metadata from thumbnail info or fetch it
            asset_metadata = (thumbnail_info[1] if thumbnail_info else None) or \
                            await immich.get_asset_info(base_url, api_key, asset_id)

            if not asset_metadata:
                log_warning(f"Metadata not found for asset {asset_id}")
                return None

            # Download original
            metadata = self._extract_immich_metadata(asset_metadata)
            filename = metadata["original_filename"]

            # Stream download to temp file to avoid OOM on large videos
            import os
            import tempfile
            temp_file_path = None

            try:
                client = await get_http_client()
                async with client.stream(
                    "GET",
                    f"{base_url}/api/assets/{asset_id}/original",
                    headers={"x-api-key": api_key},
                    timeout=120.0,
                ) as response:
                        if response.status_code != 200:
                            log_warning(f"Failed to download original for asset {asset_id}: {response.status_code}")
                            return None

                        with tempfile.NamedTemporaryFile(delete=False) as tmp:
                            temp_file_path = tmp.name

                        async with aiofiles.open(temp_file_path, 'wb') as f:
                            async for chunk in response.aiter_bytes():
                                await f.write(chunk)

                # Save using streaming-support method
                # Note: Validation happens during save/processing
                saved_info = await self.media_service.save_uploaded_file(
                    original_filename=filename,
                    user_id=user_id,
                    media_type=metadata["media_type"],
                    file_path=temp_file_path
                )

            except Exception as e:
                log_warning(f"Failed to process original for asset {asset_id}: {e}")
                return None
            finally:
                # Cleanup temp file
                if temp_file_path and Path(temp_file_path).exists():
                    try:
                        os.unlink(temp_file_path)
                    except Exception as e:
                        log_warning(f"Failed to remove temp file {temp_file_path}: {e}")

            # Save thumbnail with Journiv naming convention if available
            if thumbnail_info and thumbnail_info[0]:
                try:
                    thumbnail_content = thumbnail_info[0]
                    media_type = metadata["media_type"]

                    # Get the actual stored filename from saved_info
                    stored_filename = Path(saved_info["file_path"]).name

                    # Generate thumbnail filename using Journiv's convention
                    # For images: thumb_{filename} (e.g., thumb_{checksum}.jpg)
                    # For videos: thumb_{stem}.jpg (e.g., thumb_{checksum}.jpg)
                    if media_type == MediaType.IMAGE:
                        thumbnail_filename = f"thumb_{stored_filename}"
                    elif media_type == MediaType.VIDEO:
                        # For videos, use stem + .jpg extension
                        thumbnail_filename = f"thumb_{Path(stored_filename).stem}.jpg"
                    else:
                        thumbnail_filename = f"thumb_{stored_filename}"

                    thumbnail_path_obj = self.media_service._get_thumbnail_path(
                        thumbnail_filename,
                        media_type,
                        user_id=str(user_id)
                    )

                    if thumbnail_path_obj:
                        await self._save_bytes_to_path(thumbnail_content, thumbnail_path_obj)
                        thumbnail_path = str(thumbnail_path_obj.relative_to(self.media_service.media_root))
                        saved_info["thumbnail_path"] = thumbnail_path
                        log_info(f"Saved thumbnail for asset {asset_id}: {thumbnail_path}")
                    else:
                        log_warning(f"Cannot save thumbnail for media type: {media_type}")
                except Exception as e:
                    log_warning(f"Failed to save thumbnail for asset {asset_id}: {e}")
                    # Continue without thumbnail - not critical

            # Download web-compatible preview from Immich for HEIC/HEIF files.
            # get_asset_url("original") returns thumbnail?size=preview (JPEG/WebP),
            # avoiding the need for local pillow-heif transcoding.
            try:
                mime_type = metadata.get("mime_type", "")
                file_ext = Path(filename).suffix.lower()

                if file_ext in MediaService.HEIC_EXTENSIONS or mime_type in MediaService.HEIC_MIME_TYPES:
                    preview_url = immich.get_asset_url(base_url, asset_id, "original")
                    response = await self._fetch_with_retry(
                        preview_url, headers={"x-api-key": api_key}, timeout=30.0,
                    )

                    if response and response.status_code == 200:
                        stored_path = self.media_service.media_root / saved_info["file_path"]
                        display_path_obj = MediaService._build_display_path(stored_path)
                        await self._save_bytes_to_path(response.content, display_path_obj)

                        saved_info["display_path"] = str(display_path_obj.relative_to(self.media_service.media_root))
                        log_info(f"Saved display version for HEIC asset {asset_id}: {saved_info['display_path']}")
                    else:
                        log_warning(f"Failed to download preview for HEIC asset {asset_id}")
            except Exception as e:
                log_warning(f"Failed to save display version for HEIC asset {asset_id}: {e}")

            # Upsert record
            media = self._upsert_entry_media(
                moment_id=moment_id,
                user_id=uuid.UUID(user_id),
                asset_id=asset_id,
                asset_data=asset_metadata,
                file_info=saved_info,
                upload_status=UploadStatus.COMPLETED,
                session=session,
                commit=commit
            )

            # Post-process
            try:
                self.media_service.process_uploaded_file(
                    media_id=str(media.id),
                    file_path=saved_info["full_file_path"],
                    user_id=str(user_id)
                )
            except Exception as e:
                log_warning(f"Processing failed for asset {asset_id}: {e}")

            log_info(f"Successfully imported original for asset {asset_id}")
            return asset_metadata

        except Exception as e:
            log_error(f"Error in _download_and_save_original for {asset_id}: {e}", exc_info=True)
            return None

    @staticmethod
    def _parse_duration_seconds(raw_duration: Optional[object]) -> Optional[float]:
        """Convert Immich duration values into float seconds."""
        if raw_duration is None:
            return None
        if isinstance(raw_duration, (int, float)):
            return float(raw_duration)
        if not isinstance(raw_duration, str):
            return None
        value = raw_duration.strip()
        if not value:
            return None
        if ":" not in value:
            try:
                return float(value)
            except ValueError:
                return None

        # Expected format: HH:MM:SS(.mmm)
        parts = value.split(":")
        if len(parts) != 3:
            return None
        try:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
        except ValueError:
            return None
        return float(hours * 3600 + minutes * 60 + seconds)


    async def repair_thumbnails_async(
        self,
        user_id: uuid.UUID,
        asset_ids: list[str]
    ) -> None:
        """
        Background task to repair missing thumbnails for Immich media.

        Downloads thumbnails from Immich and updates MomentMedia records.
        """
        from app.core.database import engine

        # Create new session for background task
        thread_session = Session(engine)
        try:
            # Get user and integration
            user = thread_session.get(User, user_id)
            if not user:
                log_error(f"User {user_id} not found for thumbnail repair")
                return

            integration = thread_session.exec(
                select(Integration)
                .where(Integration.user_id == user_id)
                .where(Integration.provider == IntegrationProvider.IMMICH)
            ).first()

            if not integration or not integration.is_active:
                log_error(f"Immich integration not active for user {user_id}")
                return

            # Decrypt API key
            api_key = decrypt_token(integration.access_token_encrypted)
            base_url = integration.base_url.rstrip('/')

            repaired_count = 0
            failed_count = 0

            # Process in batches
            batch_size = COPY_MODE_BATCH_SIZE
            for i in range(0, len(asset_ids), batch_size):
                batch = asset_ids[i:i + batch_size]
                tasks = [
                    self._repair_single_thumbnail(
                        asset_id=asset_id,
                        base_url=base_url,
                        api_key=api_key,
                        user_id=user_id,
                        session=thread_session
                    )
                    for asset_id in batch
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)

                for _asset_id, result in zip(batch, results, strict=False):
                    if isinstance(result, Exception):
                        log_error(result)
                        failed_count += 1
                    elif result:
                        repaired_count += 1
                    else:
                        failed_count += 1

            log_info(
                f"Thumbnail repair completed for user {user_id}: "
                f"{repaired_count} repaired, {failed_count} failed"
            )

        except Exception as e:
            log_error(e)
        finally:
            thread_session.close()

    async def _repair_single_thumbnail(
        self,
        asset_id: str,
        base_url: str,
        api_key: str,
        user_id: uuid.UUID,
        session: Session
    ) -> bool:
        """
        Repair thumbnail for a single asset.
        """
        try:
            # Find MomentMedia record
            media = session.exec(
                select(MomentMedia)
                .join(Moment, col(Moment.id) == col(MomentMedia.moment_id))
                .where(col(Moment.user_id) == user_id)
                .where(col(MomentMedia.external_asset_id) == asset_id)
                .where(MomentMedia.external_provider == "immich")
            ).first()

            if not media:
                log_warning(f"MomentMedia not found for asset {asset_id}")
                return False

            # Get integration (should already be fetched, but ensure we have it)
            integration = session.exec(
                select(Integration)
                .where(Integration.user_id == user_id)
                .where(Integration.provider == IntegrationProvider.IMMICH)
            ).first()

            if not integration:
                log_warning(f"Integration not found for user {user_id}")
                return False

            if media.moment_id is None:
                log_warning(f"MomentMedia missing moment_id for asset {asset_id}")
                return False

            # Download thumbnail
            thumbnail_content, _ = await self._download_and_save_thumbnail(
                asset_id=asset_id,
                base_url=base_url,
                api_key=api_key,
                user_id=str(user_id),
                moment_id=media.moment_id,
                integration=integration,
                session=session
            )

            if thumbnail_content:
                try:
                    stored_filename = Path(media.file_path or "").name
                    if not stored_filename:
                        log_warning(f"Missing file path for asset {asset_id}")
                        return False

                    if media.media_type == MediaType.IMAGE:
                        thumbnail_filename = f"thumb_{stored_filename}"
                    elif media.media_type == MediaType.VIDEO:
                        thumbnail_filename = f"thumb_{Path(stored_filename).stem}.jpg"
                    else:
                        thumbnail_filename = f"thumb_{stored_filename}"

                    thumbnail_path_obj = self.media_service._get_thumbnail_path(
                        thumbnail_filename,
                        media.media_type,
                        user_id=str(user_id)
                    )

                    if not thumbnail_path_obj:
                        log_warning(f"Cannot save thumbnail for media type: {media.media_type}")
                        return False

                    thumbnail_path_obj.parent.mkdir(parents=True, exist_ok=True)
                    tmp_thumbnail_path = thumbnail_path_obj.with_suffix(".tmp")
                    async with aiofiles.open(tmp_thumbnail_path, 'wb') as f:
                        await f.write(thumbnail_content)
                        await f.flush()
                    await aiofiles.os.rename(tmp_thumbnail_path, thumbnail_path_obj)

                    thumbnail_path = str(thumbnail_path_obj.relative_to(self.media_service.media_root))
                except Exception as e:
                    log_warning(f"Failed to save thumbnail for asset {asset_id}: {e}")
                    return False

                # Update MomentMedia record
                media.thumbnail_path = thumbnail_path
                session.add(media)
                session.commit()
                log_info(f"Repaired thumbnail for asset {asset_id}")
                return True
            else:
                log_warning(f"Failed to download thumbnail for asset {asset_id}")
                return False

        except Exception as e:
            log_error(e)
            return False
