
import pytest
import uuid
from datetime import datetime
from app.schemas.entry import EntryMediaResponse, QuillDelta, QuillOp
from app.models.enums import MediaType, UploadStatus

def test_entry_media_response_url_computation():
    """
    Verify that EntryMediaResponse correctly handles serialization
    for both local and link-only media.

    The schema excludes internal fields like external_provider and external_asset_id
    from serialization. URLs are provided via signed_url fields, not a computed url field.
    """
    entry_id = uuid.uuid4()
    media_id = uuid.uuid4()

    # Case 1: Link-only Media (Immich)
    # No file_path, has external_provider and external_asset_id
    link_only_media = EntryMediaResponse(
        id=media_id,
        entry_id=entry_id,
        created_at=datetime.utcnow(),
        media_type=MediaType.IMAGE,
        mime_type="image/jpeg",
        upload_status=UploadStatus.COMPLETED,
        file_path=None,
        external_provider="immich",
        external_asset_id="asset-123",
        external_url=None
    )

    dumped = link_only_media.model_dump()

    # Verify external fields are excluded from serialization
    assert "external_provider" not in dumped, "external_provider should be excluded from dump"
    assert "external_asset_id" not in dumped, "external_asset_id should be excluded from dump"
    assert "external_url" not in dumped, "external_url should be excluded from dump"

    # Verify internal file paths are excluded
    assert "file_path" not in dumped, "file_path should be excluded from dump"
    assert "thumbnail_path" not in dumped, "thumbnail_path should be excluded from dump"

    # Verify the response has the expected fields
    assert "id" in dumped
    assert "entry_id" in dumped
    assert "media_type" in dumped
    assert dumped["id"] == media_id

    # Case 2: Local Media
    local_media = EntryMediaResponse(
        id=media_id,
        entry_id=entry_id,
        created_at=datetime.utcnow(),
        media_type=MediaType.IMAGE,
        mime_type="image/jpeg",
        upload_status=UploadStatus.COMPLETED,
        file_path="/local/path/to/file.jpg",
        file_size=1024
    )

    dumped_local = local_media.model_dump()

    # Verify file_path is excluded from serialization
    assert "file_path" not in dumped_local, "file_path should be excluded from dump"
    assert "thumbnail_path" not in dumped_local, "thumbnail_path should be excluded from dump"

    # Verify the response has the expected fields
    assert "id" in dumped_local
    assert "entry_id" in dumped_local
    assert dumped_local["id"] == media_id


def test_quill_delta_appends_newline():
    delta = QuillDelta.model_validate({"ops": [{"insert": "Hello"}]})
    assert delta.ops[-1].insert == "\n"
    assert len(delta.ops) == 2


def test_quill_delta_empty_ops_defaults():
    delta = QuillDelta.model_validate({"ops": []})
    assert delta.ops
    assert delta.ops[-1].insert == "\n"


def test_quill_delta_rejects_invalid_embed():
    with pytest.raises(ValueError):
        QuillOp.model_validate({"insert": {"unknown": "x"}})
