from app.data_transfer.dayone.models import DayOneVideo, DayOneEntry, DayOneExport
from app.schemas.dto import MediaDTO
from datetime import datetime, timezone

def test_media_dto_duration_float_validation():
    """Test that MediaDTO can handle float durations."""
    media_data = {
        "filename": "test.mp4",
        "media_type": "video",
        "file_size": 1024,
        "mime_type": "video/mp4",
        "duration": 20.315,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }

    media = MediaDTO(**media_data)
    assert media.duration == 20.315
    assert isinstance(media.duration, float)

def test_video_duration_float_validation():
    """Test that DayOneVideo can handle float durations, which are common in Day One exports."""
    # This data mirrors the error reported by a dayone user.
    # Input should be a valid integer, got a number with a fractional part [type=int_from_float, input_value=20.315, input_type=float]
    video_data = {
        "identifier": "test_id",
        "duration": 20.315,
        "type": "video/mp4"
    }

    video = DayOneVideo(**video_data)
    assert video.duration == 20.315
    assert isinstance(video.duration, float)

def test_entry_duration_float_validation():
    """Test that DayOneEntry can handle float durations."""
    entry_date = datetime.now()
    entry_data = {
        "uuid": "test_uuid",
        "creationDate": entry_date.isoformat(),
        "duration": 123.456
    }

    entry = DayOneEntry(**entry_data)
    assert entry.duration == 123.456

def test_export_with_float_durations():
    """Test that a full DayOneExport can be parsed with float durations."""
    export_data = {
        "entries": [
            {
                "uuid": "entry_1",
                "creationDate": datetime.now().isoformat(),
                "videos": [
                    {
                        "identifier": "video_1",
                        "duration": 20.315
                    }
                ],
                "duration": 20.315
            }
        ]
    }

    export = DayOneExport(**export_data)
    assert export.entries[0].videos[0].duration == 20.315
    assert export.entries[0].duration == 20.315
