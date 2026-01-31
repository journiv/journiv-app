from datetime import datetime

from app.data_transfer.dayone.mappers import DayOneToJournivMapper
from app.data_transfer.dayone.models import DayOneEntry, DayOnePhoto, DayOneVideo


def test_map_entry_allows_missing_title_and_content():
    entry = DayOneEntry(
        uuid="entry-1",
        text=None,
        rich_text=None,
        creation_date=datetime.utcnow(),
    )

    dto = DayOneToJournivMapper.map_entry(entry)

    # Empty content produces valid Quill Delta with newline (required by Quill format)
    assert dto.content_delta == {"ops": [{"insert": "\n"}]}
    assert dto.content_plain_text is None
    assert dto.title is None


def test_map_entry_preserves_import_metadata_pruned():
    entry = DayOneEntry(
        uuid="entry-1",
        text="Plain text should be dropped",
        rich_text='{"contents":[{"text":"Title\\n"}],"meta":{"version":1}}',
        creation_date=datetime.utcnow(),
        time_zone="America/Los_Angeles",
        tags=["Welcome-Entry"],
        creationDeviceModel="MacBookAir10,1",
        photos=[
            DayOnePhoto(
                identifier="PHOTO-1",
                md5="abcdef1234567890abcdef1234567890",
                type="jpeg",
                width=1024,
                height=768,
            )
        ],
        videos=[
            DayOneVideo(
                identifier="VIDEO-1",
                md5="fedcba0987654321fedcba0987654321",
                type="mov",
                duration=10,
            )
        ],
    )

    dto = DayOneToJournivMapper.map_entry(entry)
    import_metadata = dto.import_metadata

    assert import_metadata is not None
    assert import_metadata["source"] == "dayone"
    assert import_metadata["normalized_timezone"] == "America/Los_Angeles"

    raw_dayone = import_metadata["raw_dayone"]
    assert "text" not in raw_dayone
    assert raw_dayone.get("richText") is not None
    assert raw_dayone.get("creationDeviceModel") == "MacBookAir10,1"
    assert raw_dayone.get("tags") == ["Welcome-Entry"]

    photos = raw_dayone.get("photos")
    assert photos == [{"identifier": "PHOTO-1", "md5": "abcdef1234567890abcdef1234567890"}]

    videos = raw_dayone.get("videos")
    assert videos == [{"identifier": "VIDEO-1", "md5": "fedcba0987654321fedcba0987654321"}]


def test_map_entry_maps_dayone_is_pinned():
    entry = DayOneEntry(
        uuid="entry-2",
        text="Pinned entry",
        rich_text=None,
        creation_date=datetime.utcnow(),
        is_pinned=True,
    )

    dto = DayOneToJournivMapper.map_entry(entry)
    assert dto.is_pinned is True
