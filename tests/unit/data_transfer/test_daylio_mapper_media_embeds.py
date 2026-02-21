from datetime import datetime, timezone

from app.data_transfer.daylio.mappers import DaylioToJournivMapper
from app.data_transfer.daylio.models import DaylioDayEntry
from app.schemas.dto import MomentMediaDTO


def _media_dto(external_id: str, media_type: str) -> MomentMediaDTO:
    now = datetime.now(timezone.utc)
    return MomentMediaDTO(
        filename=f"{external_id}.{media_type}",
        file_path=f"assets/{external_id}",
        media_type=media_type,
        file_size=123,
        mime_type="application/octet-stream",
        checksum=None,
        width=None,
        height=None,
        duration=None,
        alt_text=None,
        file_metadata=None,
        thumbnail_path=None,
        upload_status="completed",
        created_at=now,
        updated_at=now,
        external_id=external_id,
    )


def test_map_entry_appends_media_embeds_for_daylio_entry() -> None:
    day_entry = DaylioDayEntry(
        datetime=1738368000000,
        year=2025,
        month=1,
        day=1,
        hour=8,
        minute=0,
        note="Imported note",
        note_title="Imported title",
    )

    entry = DaylioToJournivMapper._map_entry(
        day_entry,
        import_timestamp=datetime.now(timezone.utc),
        journal_external_id="journal-1",
        media_items=[
            _media_dto("asset-image-1", "image"),
            _media_dto("asset-audio-2", "audio"),
        ],
    )

    ops = entry.content_delta["ops"]
    assert {"insert": {"image": "asset-image-1"}} in ops
    assert {"insert": {"audio": "asset-audio-2"}} in ops
    assert ops[-1] == {"insert": "\n"}


def test_map_entry_without_media_keeps_text_only_delta() -> None:
    day_entry = DaylioDayEntry(
        datetime=1738368000000,
        year=2025,
        month=1,
        day=1,
        hour=8,
        minute=0,
        note="Text only",
    )

    entry = DaylioToJournivMapper._map_entry(
        day_entry,
        import_timestamp=datetime.now(timezone.utc),
        journal_external_id="journal-1",
        media_items=[],
    )

    ops = entry.content_delta["ops"]
    assert {"insert": {"image": "asset-image-1"}} not in ops
    assert {"insert": {"audio": "asset-audio-2"}} not in ops
