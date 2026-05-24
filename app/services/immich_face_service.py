"""
Service for Immich person mappings and face suggestions.
"""
import re
import time
import uuid
from typing import Any, Iterable, Optional
from urllib.parse import urlencode

import httpx
from sqlmodel import Session, col, delete, select

from app.core.config import settings
from app.core.encryption import decrypt_token
from app.core.logging_config import log_error
from app.core.media_signing import build_signed_query
from app.core.time_utils import utc_now
from app.integrations import immich
from app.integrations.schemas import (
    ImmichBatchFacesResponse,
    ImmichFaceResponse,
    ImmichImportMode,
    ImmichPeopleImportItem,
    ImmichPeopleImportResponse,
    ImmichPeopleImportResult,
    ImmichPeopleListResponse,
    ImmichPersonResponse,
    MomentImmichPeopleSuggestionsResponse,
)
from app.models.immich_asset_face import ImmichAssetFace
from app.models.integration import Integration, IntegrationProvider
from app.models.moment import Moment, MomentMedia
from app.models.moment_person_link import MomentPersonLink
from app.models.person import Person
from app.models.person_external_identity import PersonExternalIdentity
from app.schemas.person import PersonCreate, PersonSummaryResponse
from app.services.person_service import PersonService


class ImmichFaceService:
    """Coordinates Immich people import, face cache refresh, and suggestions."""

    _batch_concurrency = 4

    def __init__(self, session: Session):
        self.session = session

    def _get_integration(self, user_id: uuid.UUID) -> Integration:
        integration = self.session.exec(
            select(Integration).where(
                col(Integration.user_id) == user_id,
                Integration.provider == IntegrationProvider.IMMICH,
            )
        ).first()
        if not integration:
            raise ValueError("Immich integration not found. Please connect Immich first.")
        if not integration.is_active:
            raise ValueError("Immich integration is inactive. Please reconnect.")
        return integration

    @staticmethod
    def _api_key(integration: Integration) -> str:
        try:
            return decrypt_token(integration.access_token_encrypted)
        except Exception as exc:
            raise ValueError("Failed to decrypt Immich credentials") from exc

    @staticmethod
    def _person_summary(person: Person) -> PersonSummaryResponse:
        return PersonSummaryResponse(
            id=person.id,
            name=person.name,
            nickname=person.nickname,
            profile_image_url=PersonService.build_profile_image_url(person),
        )

    @staticmethod
    def _person_thumbnail_url(external_person_id: str, user_id: uuid.UUID) -> str:
        expires_at = int(time.time()) + settings.media_thumbnail_signed_url_ttl_seconds
        query = build_signed_query(
            IntegrationProvider.IMMICH.value,
            "person-thumbnail",
            external_person_id,
            str(user_id),
            expires_at,
        )
        return (
            f"/api/v1/integrations/{IntegrationProvider.IMMICH.value}/proxy/people/"
            f"{external_person_id}/thumbnail?{urlencode(query)}"
        )

    def _identity_map(
        self,
        integration_id: uuid.UUID,
        external_person_ids: Iterable[str],
    ) -> dict[str, tuple[PersonExternalIdentity, Optional[Person]]]:
        ids = [external_id for external_id in set(external_person_ids) if external_id]
        if not ids:
            return {}
        rows = self.session.exec(
            select(PersonExternalIdentity, Person)
            .join(Person, col(Person.id) == col(PersonExternalIdentity.person_id), isouter=True)
            .where(
                PersonExternalIdentity.integration_id == integration_id,
                col(PersonExternalIdentity.external_person_id).in_(ids),
            )
        ).all()
        return {identity.external_person_id: (identity, person) for identity, person in rows}

    def _build_immich_person_response(
        self,
        user_id: uuid.UUID,
        person_data: dict[str, Any],
        mapped: dict[str, tuple[PersonExternalIdentity, Optional[Person]]],
    ) -> ImmichPersonResponse:
        external_person_id = str(person_data.get("id") or "")
        identity, person = mapped.get(external_person_id, (None, None))
        return ImmichPersonResponse(
            external_person_id=external_person_id,
            name=person_data.get("name") or None,
            thumbnail_url=self._person_thumbnail_url(external_person_id, user_id) if external_person_id else None,
            is_hidden=bool(person_data.get("isHidden")),
            is_favorite=bool(person_data.get("isFavorite")),
            feature_face_asset_id=person_data.get("featureFaceAssetId"),
            mapped_person=self._person_summary(person) if person else None,
            sync_enabled=bool(identity.sync_enabled) if identity else False,
        )

    async def list_immich_people(
        self,
        user_id: uuid.UUID,
        *,
        page: int,
        limit: int,
        search: Optional[str],
        include_hidden: bool,
        mapped_filter: str,
    ) -> ImmichPeopleListResponse:
        integration = self._get_integration(user_id)
        api_key = self._api_key(integration)
        if mapped_filter in {"mapped", "unmapped"}:
            raw_page = 1
            raw_limit = max(limit, 100)
            filtered_total = 0
            page_start = (page - 1) * limit
            filtered_people: list[ImmichPersonResponse] = []
            has_raw_more = True

            while has_raw_more:
                people, raw_total, has_raw_more = await immich.list_people(
                    integration.base_url,
                    api_key,
                    page=raw_page,
                    limit=raw_limit,
                    search=search,
                    include_hidden=include_hidden,
                )
                if raw_page * raw_limit >= raw_total:
                    has_raw_more = False
                if not people:
                    break
                external_ids = [str(person.get("id")) for person in people if person.get("id")]
                mapped = self._identity_map(integration.id, external_ids)
                for person in people:
                    if not person.get("id"):
                        continue
                    response = self._build_immich_person_response(user_id, person, mapped)
                    if mapped_filter == "mapped" and response.mapped_person is None:
                        continue
                    if mapped_filter == "unmapped" and response.mapped_person is not None:
                        continue
                    if filtered_total >= page_start and len(filtered_people) < limit:
                        filtered_people.append(response)
                    filtered_total += 1
                raw_page += 1

            return ImmichPeopleListResponse(
                people=filtered_people,
                page=page,
                limit=limit,
                total=filtered_total,
                has_more=filtered_total > page_start + limit,
            )

        people, total, has_more = await immich.list_people(
            integration.base_url,
            api_key,
            page=page,
            limit=limit,
            search=search,
            include_hidden=include_hidden,
        )
        external_ids = [str(person.get("id")) for person in people if person.get("id")]
        mapped = self._identity_map(integration.id, external_ids)
        responses = [
            self._build_immich_person_response(user_id, person, mapped)
            for person in people
            if person.get("id")
        ]
        return ImmichPeopleListResponse(
            people=responses,
            page=page,
            limit=limit,
            total=total,
            has_more=has_more,
        )

    def _upsert_identity(
        self,
        *,
        user_id: uuid.UUID,
        integration: Integration,
        person_id: uuid.UUID,
        person_data: dict[str, Any],
        sync_enabled: bool,
    ) -> PersonExternalIdentity:
        external_person_id = str(person_data.get("id") or "")
        if not external_person_id:
            raise ValueError("Immich person is missing an ID")

        existing = self.session.exec(
            select(PersonExternalIdentity).where(
                PersonExternalIdentity.integration_id == integration.id,
                PersonExternalIdentity.external_person_id == external_person_id,
            )
        ).first()
        now = utc_now()
        if existing and existing.person_id != person_id:
            raise ValueError("Immich person is already linked to another Journiv person")

        if not existing:
            existing = PersonExternalIdentity(
                user_id=user_id,
                person_id=person_id,
                integration_id=integration.id,
                provider=IntegrationProvider.IMMICH.value,
                external_person_id=external_person_id,
            )

        existing.external_name = person_data.get("name") or None
        existing.feature_face_asset_id = person_data.get("featureFaceAssetId")
        existing.is_hidden = bool(person_data.get("isHidden"))
        existing.is_favorite = bool(person_data.get("isFavorite"))
        existing.sync_enabled = sync_enabled
        existing.raw_metadata = person_data
        existing.last_synced_at = now
        existing.updated_at = now
        self.session.add(existing)
        self._resolve_cached_person(external_person_id, integration.id, person_id if sync_enabled else None)
        return existing

    def _resolve_cached_person(
        self,
        external_person_id: str,
        integration_id: uuid.UUID,
        person_id: Optional[uuid.UUID],
    ) -> None:
        faces = self.session.exec(
            select(ImmichAssetFace).where(
                ImmichAssetFace.integration_id == integration_id,
                ImmichAssetFace.external_person_id == external_person_id,
            )
        ).all()
        now = utc_now()
        for face in faces:
            face.person_id = person_id
            face.updated_at = now
            self.session.add(face)

    def _get_owned_person_for_thumbnail(self, user_id: uuid.UUID, person_id: uuid.UUID) -> Person:
        person = self.session.exec(
            select(Person).where(
                Person.id == person_id,
                Person.user_id == user_id,
                Person.archived_at.is_(None),  # type: ignore[union-attr]
            )
        ).first()
        if person is None:
            raise ValueError("Person not found")
        return person

    async def _copy_immich_thumbnail_to_person(
        self,
        *,
        integration: Integration,
        api_key: str,
        user_id: uuid.UUID,
        person_id: uuid.UUID,
        external_person_id: str,
    ) -> None:
        person = self._get_owned_person_for_thumbnail(user_id, person_id)
        if person.profile_image_path:
            return

        try:
            image_bytes = await immich.get_person_thumbnail_bytes(
                integration.base_url,
                api_key,
                external_person_id,
                max_bytes=PersonService.PROFILE_IMAGE_MAX_BYTES,
            )
            extension, _ = PersonService.validate_profile_image_bytes(image_bytes)
            person.profile_image_path = PersonService._write_profile_image(
                user_id=user_id,
                person_id=person.id,
                image_bytes=image_bytes,
                extension=extension,
            )
            person.updated_at = utc_now()
            self.session.add(person)
        except Exception as exc:
            log_error(f"Failed to copy Immich person thumbnail for {external_person_id}: {exc}")

    async def import_people(
        self,
        user_id: uuid.UUID,
        items: list[ImmichPeopleImportItem],
    ) -> ImmichPeopleImportResponse:
        integration = self._get_integration(user_id)
        api_key = self._api_key(integration)
        person_service = PersonService(self.session)
        results: list[ImmichPeopleImportResult] = []

        for item in items:
            try:
                if item.mode == ImmichImportMode.ignore:
                    results.append(ImmichPeopleImportResult(external_person_id=item.external_person_id, mode=item.mode))
                    continue

                immich_person = await immich.get_person(integration.base_url, api_key, item.external_person_id)
                if not immich_person:
                    raise ValueError("Immich person not found")

                existing_identity = self.session.exec(
                    select(PersonExternalIdentity).where(
                        PersonExternalIdentity.integration_id == integration.id,
                        PersonExternalIdentity.external_person_id == item.external_person_id,
                    )
                ).first()
                if existing_identity and (
                    item.mode == ImmichImportMode.create
                    or item.person_id is None
                    or existing_identity.person_id != item.person_id
                ):
                    raise ValueError("Immich person is already linked to a Journiv person")

                if item.mode == ImmichImportMode.create:
                    display_name = (item.name or immich_person.get("name") or "").strip()
                    if not display_name:
                        display_name = f"Immich person {item.external_person_id[:8]}"
                    created = person_service.create_person(
                        user_id,
                        PersonCreate(
                            name=display_name,
                            nickname=item.nickname,
                            group_ids=item.group_ids,
                        ),
                    )
                    person_id = created.id
                else:
                    if item.person_id is None:
                        raise ValueError("person_id is required when linking")
                    person_service._get_owned_person(user_id, item.person_id, include_archived=False)
                    person_id = item.person_id

                await self._copy_immich_thumbnail_to_person(
                    integration=integration,
                    api_key=api_key,
                    user_id=user_id,
                    person_id=person_id,
                    external_person_id=item.external_person_id,
                )
                self._upsert_identity(
                    user_id=user_id,
                    integration=integration,
                    person_id=person_id,
                    person_data=immich_person,
                    sync_enabled=item.sync_enabled,
                )
                self.session.commit()
                person = person_service._get_owned_person(user_id, person_id, include_archived=False)
                results.append(
                    ImmichPeopleImportResult(
                        external_person_id=item.external_person_id,
                        mode=item.mode,
                        person=self._person_summary(person),
                    )
                )
            except Exception as exc:
                self.session.rollback()
                results.append(
                    ImmichPeopleImportResult(
                        external_person_id=item.external_person_id,
                        mode=item.mode,
                        error=str(exc),
                    )
                )

        return ImmichPeopleImportResponse(results=results)

    def _face_response(
        self,
        face: ImmichAssetFace,
        people_by_id: dict[uuid.UUID, Person],
        identities_by_external_id: dict[str, PersonExternalIdentity],
    ) -> ImmichFaceResponse:
        person = people_by_id.get(face.person_id) if face.person_id else None
        identity = identities_by_external_id.get(face.external_person_id or "")
        suggested = bool(person and identity and identity.sync_enabled and not face.is_hidden)
        thumbnail_url = (
            self._person_thumbnail_url(face.external_person_id, face.user_id)
            if face.external_person_id else None
        )
        return ImmichFaceResponse(
            external_face_id=face.external_face_id,
            external_asset_id=face.external_asset_id,
            external_person_id=face.external_person_id,
            person=self._person_summary(person) if person else None,
            suggested=suggested,
            thumbnail_url=thumbnail_url,
            bounding_box_x1=face.bounding_box_x1,
            bounding_box_y1=face.bounding_box_y1,
            bounding_box_x2=face.bounding_box_x2,
            bounding_box_y2=face.bounding_box_y2,
            image_width=face.image_width,
            image_height=face.image_height,
            source_type=face.source_type,
            is_hidden=face.is_hidden,
            last_synced_at=face.last_synced_at,
        )

    def _responses_for_faces(self, faces: list[ImmichAssetFace]) -> list[ImmichFaceResponse]:
        person_ids = [face.person_id for face in faces if face.person_id]
        people_by_id = {}
        if person_ids:
            people = self.session.exec(
                select(Person).where(col(Person.id).in_(list(set(person_ids))))
            ).all()
            people_by_id = {person.id: person for person in people}

        external_ids = [face.external_person_id for face in faces if face.external_person_id]
        identities = self._identity_map(faces[0].integration_id, external_ids) if faces else {}
        identities_by_external_id = {
            external_id: identity
            for external_id, (identity, _person) in identities.items()
        }
        return [self._face_response(face, people_by_id, identities_by_external_id) for face in faces]

    def _cached_faces(self, integration_id: uuid.UUID, asset_id: str) -> list[ImmichAssetFace]:
        return list(self.session.exec(
            select(ImmichAssetFace)
            .where(
                ImmichAssetFace.integration_id == integration_id,
                ImmichAssetFace.external_asset_id == asset_id,
            )
            .order_by(col(ImmichAssetFace.created_at))
        ).all())

    async def _refresh_faces(
        self,
        *,
        user_id: uuid.UUID,
        integration: Integration,
        asset_id: str,
        api_key: str,
    ) -> list[ImmichAssetFace]:
        face_data = await immich.get_asset_faces(integration.base_url, api_key, asset_id)
        person_ids = [
            str(face.get("person", {}).get("id"))
            for face in face_data
            if isinstance(face.get("person"), dict) and face.get("person", {}).get("id")
        ]
        identities = self._identity_map(integration.id, person_ids)
        now = utc_now()
        faces: list[ImmichAssetFace] = []
        seen_face_ids: set[str] = set()

        for item in face_data:
            external_face_id = str(item.get("id") or "")
            if not external_face_id:
                continue
            seen_face_ids.add(external_face_id)
            person_value = item.get("person")
            person_data: dict[str, Any] = person_value if isinstance(person_value, dict) else {}
            external_person_id = str(person_data.get("id")) if person_data.get("id") else None
            identity, _person = identities.get(external_person_id or "", (None, None))
            resolved_person_id = identity.person_id if identity and identity.sync_enabled else None

            face = self.session.exec(
                select(ImmichAssetFace).where(
                    ImmichAssetFace.integration_id == integration.id,
                    ImmichAssetFace.external_face_id == external_face_id,
                )
            ).first()
            if not face:
                face = ImmichAssetFace(
                    user_id=user_id,
                    integration_id=integration.id,
                    external_asset_id=asset_id,
                    external_face_id=external_face_id,
                    last_synced_at=now,
                )
            face.external_asset_id = asset_id
            face.external_person_id = external_person_id
            face.person_id = resolved_person_id
            face.bounding_box_x1 = item.get("boundingBoxX1")
            face.bounding_box_y1 = item.get("boundingBoxY1")
            face.bounding_box_x2 = item.get("boundingBoxX2")
            face.bounding_box_y2 = item.get("boundingBoxY2")
            face.image_width = item.get("imageWidth")
            face.image_height = item.get("imageHeight")
            face.source_type = item.get("sourceType")
            face.is_hidden = bool(person_data.get("isHidden"))
            face.raw_metadata = item
            face.last_synced_at = now
            face.updated_at = now
            self.session.add(face)
            faces.append(face)

        stale_statement = delete(ImmichAssetFace).where(
            col(ImmichAssetFace.integration_id) == integration.id,
            col(ImmichAssetFace.external_asset_id) == asset_id,
        )
        if seen_face_ids:
            stale_statement = stale_statement.where(
                ~col(ImmichAssetFace.external_face_id).in_(seen_face_ids)
            )
        self.session.exec(stale_statement)
        self.session.commit()
        return self._cached_faces(integration.id, asset_id)

    async def get_asset_faces(
        self,
        user_id: uuid.UUID,
        asset_id: str,
        *,
        refresh: bool = False,
    ) -> list[ImmichFaceResponse]:
        integration = self._get_integration(user_id)
        cached = self._cached_faces(integration.id, asset_id)
        if cached and not refresh:
            return self._responses_for_faces(cached)
        api_key = self._api_key(integration)
        faces = await self._refresh_faces(
            user_id=user_id,
            integration=integration,
            asset_id=asset_id,
            api_key=api_key,
        )
        return self._responses_for_faces(faces)

    async def get_batch_faces(
        self,
        user_id: uuid.UUID,
        asset_ids: list[str],
        *,
        refresh: bool = False,
    ) -> ImmichBatchFacesResponse:
        results: dict[str, list[ImmichFaceResponse]] = {}
        errors: dict[str, str] = {}

        for asset_id in dict.fromkeys(asset_ids):
            try:
                results[asset_id] = await self.get_asset_faces(user_id, asset_id, refresh=refresh)
            except Exception as exc:
                log_error(exc, user_id=user_id, asset_id=asset_id)
                errors[asset_id] = str(exc)
        return ImmichBatchFacesResponse(results=results, errors=errors)

    async def get_moment_suggestions(
        self,
        user_id: uuid.UUID,
        moment_id: uuid.UUID,
    ) -> MomentImmichPeopleSuggestionsResponse:
        moment = self.session.exec(
            select(Moment).where(Moment.id == moment_id, Moment.user_id == user_id)
        ).first()
        if not moment:
            raise ValueError("Moment not found")

        media_rows = self.session.exec(
            select(MomentMedia.external_asset_id)
            .where(
                MomentMedia.moment_id == moment_id,
                MomentMedia.external_provider == IntegrationProvider.IMMICH.value,
                col(MomentMedia.external_asset_id).is_not(None),
            )
        ).all()
        asset_ids = [asset_id for asset_id in media_rows if asset_id]
        if not asset_ids:
            return MomentImmichPeopleSuggestionsResponse(people=[], source_asset_ids={})

        existing_person_ids = set(
            self.session.exec(
                select(MomentPersonLink.person_id).where(MomentPersonLink.moment_id == moment_id)
            ).all()
        )
        batch = await self.get_batch_faces(user_id, asset_ids, refresh=False)
        people_by_id: dict[uuid.UUID, PersonSummaryResponse] = {}
        source_asset_ids: dict[str, list[str]] = {}
        for asset_id, faces in batch.results.items():
            for face in faces:
                if not face.suggested or face.person is None or face.person.id in existing_person_ids:
                    continue
                people_by_id[face.person.id] = face.person
                source_asset_ids.setdefault(str(face.person.id), []).append(asset_id)

        return MomentImmichPeopleSuggestionsResponse(
            people=sorted(people_by_id.values(), key=lambda person: person.name.lower()),
            source_asset_ids=source_asset_ids,
        )


async def fetch_immich_person_thumbnail(
    user_id: uuid.UUID,
    external_person_id: str,
) -> httpx.Response:
    """Fetch a streamed Immich person thumbnail using stored Journiv credentials."""
    from app.integrations.service import _get_proxy_client, get_integration_credentials

    if not re.match(r"^[a-zA-Z0-9_-]+$", external_person_id):
        raise ValueError("Invalid Immich person ID format")

    base_url, encrypted_token = await get_integration_credentials(user_id, IntegrationProvider.IMMICH)
    api_key = decrypt_token(encrypted_token)
    url = immich.get_person_thumbnail_url(base_url, external_person_id)
    client = await _get_proxy_client()
    return await client.send(
        client.build_request("GET", url, headers={"x-api-key": api_key}),
        stream=True,
    )
