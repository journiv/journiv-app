"""
Person service for people and moment-people operations.
"""
import os
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from types import ModuleType
from typing import List, Optional, Sequence, Tuple
from urllib.parse import quote

from sqlalchemy import case, desc, func, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, delete, select

from app.core.config import settings
from app.core.db_utils import normalize_uuid_list
from app.core.logging_config import log_error, log_info
from app.core.time_utils import utc_now
from app.models.immich_asset_face import ImmichAssetFace
from app.models.moment import Moment
from app.models.moment_person_link import MomentPersonLink
from app.models.person import Person
from app.models.person_external_identity import PersonExternalIdentity
from app.models.person_group import PersonGroup
from app.models.person_group_link import PersonGroupLink
from app.schemas.person import (
    PersonCreate,
    PersonGroupSummaryResponse,
    PersonResponse,
    PersonSort,
    PersonUpdate,
)
from app.services.moment_lookup import MomentNotFoundError

try:
    from PIL import Image as _PILImage
    from PIL import UnidentifiedImageError as _PILUnidentifiedImageError
except ImportError:  # pragma: no cover
    Image: ModuleType | None = None
    UnidentifiedImageError: type[Exception] = ValueError
else:
    Image = _PILImage
    UnidentifiedImageError = _PILUnidentifiedImageError

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass


class PersonService:
    """Service class for people operations."""

    PROFILE_IMAGE_MAX_BYTES = 10 * 1024 * 1024
    PROFILE_IMAGE_FORMAT_TO_EXTENSION = {
        "JPEG": ".jpg",
        "PNG": ".png",
        "WEBP": ".webp",
        "HEIF": ".heic",
        "HEIC": ".heic",
    }

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _normalize_name(name: str) -> str:
        return " ".join((name or "").strip().split()).lower()

    @staticmethod
    def _clean_name(name: str) -> str:
        cleaned = " ".join((name or "").strip().split())
        if not cleaned:
            raise ValueError("Person name cannot be empty")
        return cleaned

    @staticmethod
    def _escape_like_term(term: str) -> str:
        return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def _commit(self) -> None:
        try:
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

    @staticmethod
    def _profile_image_root() -> Path:
        return Path(settings.media_root).resolve()

    @classmethod
    def build_profile_image_url(cls, person: Person) -> Optional[str]:
        if not person.profile_image_path:
            return None
        version = int((person.updated_at or person.created_at or utc_now()).timestamp())
        encoded_path = quote(person.profile_image_path.replace("\\", "/"), safe="/")
        return f"/media/{encoded_path}?v={version}"

    @classmethod
    def _validate_profile_image_bytes(
        cls, image_bytes: bytes
    ) -> tuple[str, tuple[int, int]]:
        if not image_bytes:
            raise ValueError("Profile image file is empty")
        if len(image_bytes) > cls.PROFILE_IMAGE_MAX_BYTES:
            raise ValueError("Profile image must be 10 MB or smaller")
        if Image is None:
            raise RuntimeError("Pillow is required for profile image uploads")

        try:
            with Image.open(BytesIO(image_bytes)) as image:
                image.verify()
            with Image.open(BytesIO(image_bytes)) as image:
                image_format = (image.format or "").upper()
                size = image.size
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValueError("Uploaded file is not a valid image") from exc

        extension = cls.PROFILE_IMAGE_FORMAT_TO_EXTENSION.get(image_format)
        if extension is None:
            raise ValueError("Unsupported profile image format")
        if size[0] <= 0 or size[1] <= 0:
            raise ValueError("Profile image must have valid dimensions")
        return extension, size

    @classmethod
    def validate_profile_image_bytes(
        cls, image_bytes: bytes
    ) -> tuple[str, tuple[int, int]]:
        return cls._validate_profile_image_bytes(image_bytes)

    @classmethod
    def _profile_image_relative_path(
        cls, user_id: uuid.UUID, person_id: uuid.UUID, extension: str
    ) -> Path:
        return Path("people") / str(user_id) / str(person_id) / f"profile{extension}"

    @classmethod
    def _delete_profile_image_file(cls, relative_path: Optional[str]) -> None:
        if not relative_path:
            return
        media_root = cls._profile_image_root()
        target_path = (media_root / relative_path).resolve()
        if not target_path.is_relative_to(media_root):
            raise ValueError("Profile image path escapes media root")
        target_path.unlink(missing_ok=True)
        for parent in target_path.parents:
            if parent == media_root:
                break
            try:
                parent.rmdir()
            except OSError:
                break

    @classmethod
    def _write_profile_image(
        cls,
        *,
        user_id: uuid.UUID,
        person_id: uuid.UUID,
        image_bytes: bytes,
        extension: str,
    ) -> str:
        media_root = cls._profile_image_root()
        relative_path = cls._profile_image_relative_path(user_id, person_id, extension)
        target_path = (media_root / relative_path).resolve()
        if not target_path.is_relative_to(media_root):
            raise ValueError("Profile image path escapes media root")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target_path.with_suffix(f"{target_path.suffix}.{uuid.uuid4().hex}.tmp")
        with open(tmp_path, "wb") as handle:
            handle.write(image_bytes)
        os.replace(tmp_path, target_path)
        return relative_path.as_posix()

    @staticmethod
    def _is_duplicate_person_name_error(exc: IntegrityError) -> bool:
        raw_message = str(getattr(exc, "orig", exc)).lower()
        return (
            "uq_person_user_normalized_name" in raw_message
            or "unique constraint failed: person.user_id, person.normalized_name" in raw_message
            or "person_user_id_normalized_name_key" in raw_message
        )

    def _person_stats_subquery(self, user_id: uuid.UUID):
        return (
            select(
                col(MomentPersonLink.person_id).label("person_id"),
                func.count(func.distinct(col(MomentPersonLink.moment_id))).label("memory_count"),
                func.max(col(Moment.logged_at_utc)).label("last_seen_at_utc"),
            )
            .join(Person, col(Person.id) == col(MomentPersonLink.person_id))
            .join(Moment, col(Moment.id) == col(MomentPersonLink.moment_id))
            .where(col(Person.user_id) == user_id)
            .group_by(col(MomentPersonLink.person_id))
            .subquery()
        )

    def _list_people_statement(
        self,
        *,
        user_id: uuid.UUID,
        include_archived: bool,
        search: Optional[str],
        sort: PersonSort,
    ):
        stats = self._person_stats_subquery(user_id)
        memory_count = func.coalesce(col(stats.c.memory_count), 0)
        last_seen = col(stats.c.last_seen_at_utc)

        statement = (
            select(Person, memory_count.label("memory_count"), last_seen.label("last_seen_at_utc"))
            .outerjoin(stats, col(stats.c.person_id) == col(Person.id))
            .where(col(Person.user_id) == user_id)
            .options(selectinload(Person.groups))  # type: ignore[arg-type]
        )

        if not include_archived:
            statement = statement.where(col(Person.archived_at).is_(None))

        if search:
            escaped = self._escape_like_term(search.strip())
            if escaped:
                pattern = f"%{escaped}%"
                statement = statement.where(
                    or_(
                        col(Person.name).ilike(pattern, escape="\\"),
                        col(Person.nickname).ilike(pattern, escape="\\"),
                    )
                )

        if sort == PersonSort.frequent:
            statement = statement.order_by(desc(memory_count), func.lower(col(Person.name)).asc())
        elif sort == PersonSort.recent:
            statement = statement.order_by(
                case((last_seen.is_(None), 1), else_=0),
                desc(last_seen),
                func.lower(col(Person.name)).asc(),
            )
        else:
            statement = statement.order_by(func.lower(col(Person.name)).asc())

        return statement

    def _validate_group_ids(self, user_id: uuid.UUID, group_ids: Sequence[uuid.UUID]) -> List[uuid.UUID]:
        requested_ids = list(dict.fromkeys(group_ids))
        if not requested_ids:
            return []

        groups = self.session.exec(
            select(PersonGroup.id).where(
                col(PersonGroup.user_id) == user_id,
                col(PersonGroup.id).in_(requested_ids),
            )
        ).all()
        if len(groups) != len(requested_ids):
            raise ValueError("One or more groups were not found")
        return requested_ids

    def _replace_person_groups(
        self,
        *,
        user_id: uuid.UUID,
        person_id: uuid.UUID,
        group_ids: Sequence[uuid.UUID],
    ) -> None:
        requested_ids = self._validate_group_ids(user_id, group_ids)
        current_links = self.session.exec(
            select(PersonGroupLink).where(col(PersonGroupLink.person_id) == person_id)
        ).all()
        current_ids = {link.person_group_id for link in current_links}
        requested_set = set(requested_ids)

        for link in current_links:
            if link.person_group_id not in requested_set:
                self.session.delete(link)
        for group_id in requested_ids:
            if group_id not in current_ids:
                self.session.add(PersonGroupLink(person_group_id=group_id, person_id=person_id))

    @staticmethod
    def _row_to_response(row: Tuple[Person, int, Optional[datetime]]) -> PersonResponse:
        person, memory_count, last_seen_at_utc = row
        groups = sorted(
            (person.groups or []),
            key=lambda group: (group.position, (group.name or "").lower()),
        )
        return PersonResponse(
            id=person.id,
            user_id=person.user_id,
            name=person.name,
            nickname=person.nickname,
            note=person.note,
            profile_image_url=PersonService.build_profile_image_url(person),
            archived_at=person.archived_at,
            memory_count=int(memory_count or 0),
            last_seen_at_utc=last_seen_at_utc,
            groups=[
                PersonGroupSummaryResponse(
                    id=group.id,
                    name=group.name,
                    color_value=group.color_value,
                    icon=group.icon,
                )
                for group in groups
            ],
            created_at=person.created_at,
            updated_at=person.updated_at,
        )

    def _get_owned_moment(self, user_id: uuid.UUID, moment_id: uuid.UUID) -> Moment:
        moment = self.session.exec(
            select(Moment).where(col(Moment.id) == moment_id, col(Moment.user_id) == user_id)
        ).first()
        if not moment:
            raise MomentNotFoundError("Moment not found")
        return moment

    def _get_owned_person(
        self,
        user_id: uuid.UUID,
        person_id: uuid.UUID,
        *,
        include_archived: bool = True,
    ) -> Person:
        statement = select(Person).where(col(Person.id) == person_id, col(Person.user_id) == user_id)
        if not include_archived:
            statement = statement.where(col(Person.archived_at).is_(None))
        person = self.session.exec(statement).first()
        if not person:
            raise ValueError("Person not found")
        return person

    def list_people(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None,
        sort: PersonSort = PersonSort.by_name,
        include_archived: bool = False,
    ) -> List[PersonResponse]:
        statement = self._list_people_statement(
            user_id=user_id,
            include_archived=include_archived,
            search=search,
            sort=sort,
        ).offset(offset).limit(limit)
        rows = self.session.exec(statement).all()
        return [self._row_to_response(row) for row in rows]

    def get_person(
        self,
        user_id: uuid.UUID,
        person_id: uuid.UUID,
        *,
        include_archived: bool = True,
    ) -> PersonResponse:
        stats = self._person_stats_subquery(user_id)
        statement = (
            select(
                Person,
                func.coalesce(col(stats.c.memory_count), 0).label("memory_count"),
                col(stats.c.last_seen_at_utc).label("last_seen_at_utc"),
            )
            .outerjoin(stats, col(stats.c.person_id) == col(Person.id))
            .where(col(Person.user_id) == user_id, col(Person.id) == person_id)
            .options(selectinload(Person.groups))  # type: ignore[arg-type]
        )
        if not include_archived:
            statement = statement.where(col(Person.archived_at).is_(None))
        row = self.session.exec(statement).first()
        if not row:
            raise ValueError("Person not found")
        return self._row_to_response(row)

    def _find_by_normalized_name(self, user_id: uuid.UUID, normalized_name: str) -> Optional[Person]:
        return self.session.exec(
            select(Person).where(
                col(Person.user_id) == user_id,
                col(Person.normalized_name) == normalized_name,
            )
        ).first()

    def create_person(self, user_id: uuid.UUID, person_data: PersonCreate) -> PersonResponse:
        cleaned_name = self._clean_name(person_data.name)
        normalized = self._normalize_name(cleaned_name)
        existing = self._find_by_normalized_name(user_id, normalized)
        requested_group_ids = self._validate_group_ids(user_id, person_data.group_ids)

        if existing:
            if existing.archived_at is not None:
                existing.archived_at = None
                existing.name = cleaned_name
                existing.nickname = person_data.nickname
                existing.note = person_data.note
                existing.updated_at = utc_now()
                self.session.add(existing)
                self._replace_person_groups(
                    user_id=user_id,
                    person_id=existing.id,
                    group_ids=requested_group_ids,
                )
                self._commit()
                self.session.refresh(existing)
                return self.get_person(user_id, existing.id, include_archived=True)
            raise ValueError("Person with this name already exists")

        person = Person(
            user_id=user_id,
            name=cleaned_name,
            normalized_name=normalized,
            nickname=person_data.nickname,
            note=person_data.note,
        )
        self.session.add(person)
        self._replace_person_groups(
            user_id=user_id,
            person_id=person.id,
            group_ids=requested_group_ids,
        )
        try:
            self._commit()
        except IntegrityError as exc:
            if self._is_duplicate_person_name_error(exc):
                raise ValueError("Person with this name already exists") from None
            raise
        self.session.refresh(person)
        return self.get_person(user_id, person.id, include_archived=True)

    def update_person(
        self,
        user_id: uuid.UUID,
        person_id: uuid.UUID,
        person_data: PersonUpdate,
    ) -> PersonResponse:
        person = self._get_owned_person(user_id, person_id, include_archived=True)
        fields_set = person_data.model_fields_set

        if "name" in fields_set and person_data.name is not None:
            cleaned_name = self._clean_name(person_data.name)
            normalized = self._normalize_name(cleaned_name)
            existing = self._find_by_normalized_name(user_id, normalized)
            if existing and existing.id != person.id:
                raise ValueError("Person with this name already exists")
            person.name = cleaned_name
            person.normalized_name = normalized

        if "nickname" in fields_set:
            person.nickname = person_data.nickname.strip() if person_data.nickname else None
        if "note" in fields_set:
            person.note = person_data.note
        if "group_ids" in fields_set:
            self._replace_person_groups(
                user_id=user_id,
                person_id=person.id,
                group_ids=person_data.group_ids or [],
            )

        person.updated_at = utc_now()
        self.session.add(person)
        try:
            self._commit()
        except IntegrityError as exc:
            if self._is_duplicate_person_name_error(exc):
                raise ValueError("Person with this name already exists") from None
            raise
        self.session.refresh(person)
        return self.get_person(user_id, person.id, include_archived=True)

    def upload_profile_image(
        self,
        user_id: uuid.UUID,
        person_id: uuid.UUID,
        image_bytes: bytes,
    ) -> PersonResponse:
        person = self._get_owned_person(user_id, person_id, include_archived=True)
        extension, _ = self._validate_profile_image_bytes(image_bytes)
        previous_path = person.profile_image_path
        relative_path = self._write_profile_image(
            user_id=user_id,
            person_id=person.id,
            image_bytes=image_bytes,
            extension=extension,
        )
        person.profile_image_path = relative_path
        person.updated_at = utc_now()
        self.session.add(person)
        self._commit()
        self.session.refresh(person)
        if previous_path and previous_path != relative_path:
            self._delete_profile_image_file(previous_path)
        return self.get_person(user_id, person.id, include_archived=True)

    def remove_profile_image(
        self,
        user_id: uuid.UUID,
        person_id: uuid.UUID,
    ) -> PersonResponse:
        person = self._get_owned_person(user_id, person_id, include_archived=True)
        previous_path = person.profile_image_path
        person.profile_image_path = None
        person.updated_at = utc_now()
        self.session.add(person)
        self._commit()
        self.session.refresh(person)
        self._delete_profile_image_file(previous_path)
        return self.get_person(user_id, person.id, include_archived=True)

    def archive_person(self, user_id: uuid.UUID, person_id: uuid.UUID) -> None:
        person = self._get_owned_person(user_id, person_id, include_archived=True)
        if person.archived_at is None:
            person.archived_at = utc_now()
            person.updated_at = utc_now()
            self.session.add(person)
            self._commit()
        log_info(f"Archived person {person_id} for user {user_id}")

    def restore_person(self, user_id: uuid.UUID, person_id: uuid.UUID) -> PersonResponse:
        person = self._get_owned_person(user_id, person_id, include_archived=True)
        person.archived_at = None
        person.updated_at = utc_now()
        self.session.add(person)
        try:
            self._commit()
        except IntegrityError as exc:
            if self._is_duplicate_person_name_error(exc):
                raise ValueError("Person with this name already exists") from None
            raise
        self.session.refresh(person)
        return self.get_person(user_id, person.id, include_archived=True)

    def merge_people(
        self,
        user_id: uuid.UUID,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
    ) -> PersonResponse:
        if source_id == target_id:
            raise ValueError("Cannot merge a person into itself")

        source = self._get_owned_person(user_id, source_id, include_archived=True)
        target = self._get_owned_person(user_id, target_id, include_archived=True)
        if target.archived_at is not None:
            raise ValueError("Cannot merge into an archived person")

        source_moment_ids = self.session.exec(
            select(MomentPersonLink.moment_id).where(col(MomentPersonLink.person_id) == source.id)
        ).all()
        if source_moment_ids:
            normalized_moment_ids = normalize_uuid_list(source_moment_ids)
            existing_target_moment_ids = set(
                self.session.exec(
                    select(MomentPersonLink.moment_id).where(
                        col(MomentPersonLink.person_id) == target.id,
                        col(MomentPersonLink.moment_id).in_(normalized_moment_ids),
                    )
                ).all()
            )
            for moment_id in source_moment_ids:
                if moment_id not in existing_target_moment_ids:
                    self.session.add(
                        MomentPersonLink(moment_id=moment_id, person_id=target.id)
                    )
            self.session.exec(
                delete(MomentPersonLink).where(
                    col(MomentPersonLink.person_id) == source.id,
                    col(MomentPersonLink.moment_id).in_(normalized_moment_ids),
                )
            )

        source_group_ids = self.session.exec(
            select(PersonGroupLink.person_group_id).where(col(PersonGroupLink.person_id) == source.id)
        ).all()
        if source_group_ids:
            normalized_group_ids = normalize_uuid_list(source_group_ids)
            existing_target_group_ids = set(
                self.session.exec(
                    select(PersonGroupLink.person_group_id).where(
                        col(PersonGroupLink.person_id) == target.id,
                        col(PersonGroupLink.person_group_id).in_(normalized_group_ids),
                    )
                ).all()
            )
            for group_id in source_group_ids:
                if group_id not in existing_target_group_ids:
                    self.session.add(
                        PersonGroupLink(
                            person_group_id=group_id,
                            person_id=target.id,
                        )
                    )
            self.session.exec(
                delete(PersonGroupLink).where(
                    col(PersonGroupLink.person_id) == source.id,
                    col(PersonGroupLink.person_group_id).in_(normalized_group_ids),
                )
            )

        source_identities = self.session.exec(
            select(PersonExternalIdentity).where(
                col(PersonExternalIdentity.person_id) == source.id
            )
        ).all()
        for identity in source_identities:
            target_identity = self.session.exec(
                select(PersonExternalIdentity).where(
                    PersonExternalIdentity.person_id == target.id,
                    PersonExternalIdentity.integration_id == identity.integration_id,
                    PersonExternalIdentity.provider == identity.provider,
                )
            ).first()
            if target_identity:
                self.session.delete(identity)
                cached_faces = self.session.exec(
                    select(ImmichAssetFace).where(
                        ImmichAssetFace.integration_id == identity.integration_id,
                        ImmichAssetFace.external_person_id == identity.external_person_id,
                    )
                ).all()
                for face in cached_faces:
                    face.person_id = None
                    face.updated_at = utc_now()
                    self.session.add(face)
            else:
                identity.person_id = target.id
                identity.updated_at = utc_now()
                self.session.add(identity)
                cached_faces = self.session.exec(
                    select(ImmichAssetFace).where(
                        ImmichAssetFace.integration_id == identity.integration_id,
                        ImmichAssetFace.external_person_id == identity.external_person_id,
                    )
                ).all()
                for face in cached_faces:
                    face.person_id = target.id if identity.sync_enabled else None
                    face.updated_at = utc_now()
                    self.session.add(face)

        source.archived_at = utc_now()
        source.updated_at = utc_now()
        self.session.add(source)
        self._commit()
        return self.get_person(user_id, target.id, include_archived=True)

    def get_moment_people(
        self,
        moment_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        include_archived: bool = False,
    ) -> List[PersonResponse]:
        self._get_owned_moment(user_id, moment_id)
        statement = (
            self._list_people_statement(
                user_id=user_id,
                include_archived=include_archived,
                search=None,
                sort=PersonSort.by_name,
            )
            .join(MomentPersonLink, col(MomentPersonLink.person_id) == col(Person.id))
            .where(col(MomentPersonLink.moment_id) == moment_id)
        )
        rows = self.session.exec(statement).all()
        return [self._row_to_response(row) for row in rows]

    def replace_moment_people(
        self,
        moment_id: uuid.UUID,
        person_ids: Sequence[uuid.UUID],
        user_id: uuid.UUID,
    ) -> List[PersonResponse]:
        self._get_owned_moment(user_id, moment_id)
        requested_ids = list(dict.fromkeys(person_ids))

        if requested_ids:
            people = self.session.exec(
                select(Person).where(
                    col(Person.user_id) == user_id,
                    col(Person.archived_at).is_(None),
                    col(Person.id).in_(requested_ids),
                )
            ).all()
            if len(people) != len(requested_ids):
                raise ValueError("One or more people were not found")

        current_links = self.session.exec(
            select(MomentPersonLink).where(col(MomentPersonLink.moment_id) == moment_id)
        ).all()
        current_ids = {link.person_id for link in current_links}
        requested_set = set(requested_ids)

        to_remove = [link for link in current_links if link.person_id not in requested_set]
        to_add = [person_id for person_id in requested_ids if person_id not in current_ids]

        for link in to_remove:
            self.session.delete(link)
        for person_id in to_add:
            self.session.add(MomentPersonLink(moment_id=moment_id, person_id=person_id))

        if to_remove or to_add or (not requested_ids and current_links):
            self._commit()

        return self.get_moment_people(moment_id, user_id)

    def remove_person_from_moment(
        self,
        moment_id: uuid.UUID,
        person_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        self._get_owned_moment(user_id, moment_id)
        self._get_owned_person(user_id, person_id, include_archived=True)
        link = self.session.exec(
            select(MomentPersonLink).where(
                col(MomentPersonLink.moment_id) == moment_id,
                col(MomentPersonLink.person_id) == person_id,
            )
        ).first()
        if not link:
            return False
        self.session.delete(link)
        self._commit()
        return True
