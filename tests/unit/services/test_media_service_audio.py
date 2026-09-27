"""
Tests for audio-only WebM/MP4 handling in MediaService (browser dictation).

libmagic reports `video/webm` / `video/mp4` for an audio-only container, so the
worker must decide audio-vs-video from the streams (ffprobe), move the file to
the audio directory, and fill in duration and waveform peaks. These tests use
real ffmpeg-generated files: the regression that matters is a real video WebM
that must stay a video.
"""
import shutil
import subprocess
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlmodel import Session, create_engine

from app.core.config import Settings
from app.core.exceptions import InvalidFileTypeError
from app.models.base import BaseModel
from app.models.entry import Entry
from app.models.enums import JournalColor, MediaType, UploadStatus
from app.models.journal import Journal
from app.models.moment import Moment, MomentMedia
from app.models.user import User
from app.services import media_service as media_service_module
from app.services.audio_waveform import WAVEFORM_BUCKETS, extract_waveform
from app.services.media_service import MediaService
from app.services.media_storage_service import MediaStorageService
from app.utils.import_export.media_handler import MediaHandler

pytestmark = [
    pytest.mark.media,
    pytest.mark.skipif(
        shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
        reason="ffmpeg/ffprobe not installed",
    ),
]


def _ffmpeg(*args: str, stdout=None) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *args],
        check=True,
        stdout=stdout,
        stderr=subprocess.PIPE,
    )


@pytest.fixture(scope="module")
def fixtures_dir(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("audio_fixtures")
    sine = ["-f", "lavfi", "-i", "sine=frequency=440:duration=1"]
    _ffmpeg(*sine, "-c:a", "libopus", "-f", "webm", str(root / "audio_only.webm"))
    # Written to a pipe like MediaRecorder does: no container duration.
    with open(root / "live.webm", "wb") as out:
        _ffmpeg(*sine, "-c:a", "libopus", "-f", "webm", "-", stdout=out)
    # M4A brand (libmagic: audio/x-m4a) and plain isom brand (libmagic: video/mp4).
    _ffmpeg(*sine, "-c:a", "aac", "-f", "ipod", str(root / "audio_only.m4a"))
    # Opus is legal in MP4 too; stored as `.m4a` it is its own conversion target.
    _ffmpeg(*sine, "-c:a", "libopus", "-f", "mp4", str(root / "opus_in_mp4.m4a"))
    _ffmpeg(*sine, "-c:a", "aac", "-f", "mp4", str(root / "audio_isom.mp4"))
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc=duration=1:size=64x64:rate=10",
        "-f", "webm", str(root / "video_real.webm"),
    )
    _ffmpeg(
        "-f", "lavfi", "-i", "anullsrc=r=8000:cl=mono", "-t", "1",
        "-c:a", "libopus", "-f", "webm", str(root / "silent.webm"),
    )
    _ffmpeg(*sine, str(root / "tone.wav"))
    (root / "garbage.webm").write_bytes(b"\x1a\x45\xdf\xa3" + b"not really a webm" * 20)
    return root


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture
def test_user(test_db: Session) -> User:
    user = User(
        email=f"audio_{uuid.uuid4().hex[:8]}@example.com",
        password="hashed_password",
        name="Audio Test User",
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def test_entry(test_db: Session, test_user: User) -> Entry:
    journal = Journal(user_id=test_user.id, title="Journal", color=JournalColor.BLUE)
    test_db.add(journal)
    test_db.commit()
    test_db.refresh(journal)
    moment = Moment(user_id=test_user.id, logged_timezone="UTC")
    test_db.add(moment)
    test_db.commit()
    test_db.refresh(moment)
    entry = Entry(
        journal_id=journal.id,
        moment_id=moment.id,
        user_id=test_user.id,
        title="Entry",
        content_delta={"ops": [{"insert": "Test\n"}]},
        content_plain_text="Test",
        word_count=1,
    )
    test_db.add(entry)
    test_db.commit()
    test_db.refresh(entry)
    return entry


@pytest.fixture
def service(tmp_path, test_db, monkeypatch) -> MediaService:
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setattr(media_service_module.settings, "media_root", str(media_root))
    svc = MediaService(session=test_db)
    svc.media_root = media_root
    svc.media_storage_service = MediaStorageService(media_root, test_db)
    return svc


def _stage_upload(
    service: MediaService,
    session: Session,
    user: User,
    entry: Entry,
    source: Path,
    *,
    filename: str,
    directory: str = "videos",
    mime_type: str = "video/webm",
    media_type: MediaType = MediaType.VIDEO,
) -> MomentMedia:
    """Put a file where the upload endpoint would have left it, as PENDING."""
    directory_path = service.media_root / str(user.id) / directory
    directory_path.mkdir(parents=True, exist_ok=True)
    stored = directory_path / filename
    shutil.copy(source, stored)
    media = MomentMedia(
        moment_id=entry.moment_id,
        media_type=media_type,
        mime_type=mime_type,
        upload_status=UploadStatus.PENDING,
        file_path=str(stored.relative_to(service.media_root)),
        original_filename=filename,
        file_size=stored.stat().st_size,
    )
    session.add(media)
    session.commit()
    session.refresh(media)
    return media


def _process(service: MediaService, session: Session, user: User, media: MomentMedia) -> MomentMedia:
    service.process_uploaded_file(
        media_id=str(media.id),
        file_path=str(service.media_root / media.file_path),
        user_id=str(user.id),
    )
    session.expire_all()
    return session.get(MomentMedia, media.id)


# ─── Task 0.1: allowlists ────────────────────────────────────────────

class TestAudioAllowlists:
    def test_default_mime_allowlist_covers_dictation_containers(self):
        allowed = Settings.validate_allowed_media_types(None)
        for mime in ("audio/webm", "audio/mp4", "audio/opus", "audio/aac", "audio/x-m4a"):
            assert mime in allowed
        assert allowed.count("audio/aac") == 1

    def test_default_extension_allowlist_adds_opus(self):
        allowed = Settings.validate_allowed_file_extensions(None)
        assert ".opus" in allowed
        assert ".webm" in allowed and ".m4a" in allowed

    def test_webm_and_mp4_stay_video_fallbacks(self):
        assert ".webm" in MediaHandler.VIDEO_EXTENSIONS
        assert ".mp4" in MediaHandler.VIDEO_EXTENSIONS
        assert ".webm" not in MediaHandler.AUDIO_EXTENSIONS
        assert ".mp4" not in MediaHandler.AUDIO_EXTENSIONS
        assert ".opus" in MediaHandler.AUDIO_EXTENSIONS

    @pytest.mark.parametrize("sniffed", ["audio/webm", "audio/mp4"])
    def test_streamed_upload_accepts_audio_containers(self, service, sniffed):
        with patch.object(service, "_detect_mime", return_value=sniffed):
            service._validate_streamed_upload(1024, "dictation.webm", b"header")

    @pytest.mark.parametrize(
        "name", ["audio_only.webm", "live.webm", "audio_only.m4a", "audio_isom.mp4"]
    )
    def test_real_recorder_output_passes_streamed_validation(
        self, service, fixtures_dir, name
    ):
        """Unpatched: the real 2048-byte header sniff against the real allowlist."""
        source = fixtures_dir / name
        header = source.read_bytes()[:2048]
        service._validate_streamed_upload(source.stat().st_size, name, header)

    def test_streamed_upload_still_rejects_unknown_types(self, service):
        with patch.object(service, "_detect_mime", return_value="audio/x-unknown"):
            with pytest.raises(InvalidFileTypeError):
                service._validate_streamed_upload(1024, "dictation.webm", b"header")


# ─── Task 0.2: probe_streams ─────────────────────────────────────────

class TestProbeStreams:
    def test_audio_only_webm(self, service, fixtures_dir):
        result = service.probe_streams(fixtures_dir / "audio_only.webm")
        assert result["ok"] is True
        assert result["has_audio"] is True and result["has_video"] is False
        assert result["duration"] == pytest.approx(1.0, abs=0.1)

    def test_audio_only_m4a(self, service, fixtures_dir):
        result = service.probe_streams(fixtures_dir / "audio_only.m4a")
        assert (result["ok"], result["has_audio"], result["has_video"]) == (True, True, False)

    def test_reports_the_audio_codec_and_channels(self, service, fixtures_dir):
        webm = service.probe_streams(fixtures_dir / "audio_only.webm")
        m4a = service.probe_streams(fixtures_dir / "audio_only.m4a")
        assert (webm["audio_codec"], webm["audio_channels"]) == ("opus", 1)
        assert (m4a["audio_codec"], m4a["audio_channels"]) == ("aac", 1)

    def test_video_webm(self, service, fixtures_dir):
        result = service.probe_streams(fixtures_dir / "video_real.webm")
        assert (result["ok"], result["has_video"]) == (True, True)

    def test_live_recording_has_no_container_duration(self, service, fixtures_dir):
        result = service.probe_streams(fixtures_dir / "live.webm")
        assert result["ok"] is True
        assert result["duration"] is None

    def test_failed_probe_is_not_reported_as_no_video(self, service, fixtures_dir, tmp_path):
        for path in (fixtures_dir / "garbage.webm", tmp_path / "missing.webm"):
            result = service.probe_streams(path)
            assert result == {
                "ok": False, "has_video": False, "has_audio": False, "duration": None,
                "audio_codec": None, "audio_channels": None,
            }

    def test_timeout_is_a_failed_probe(self, service, fixtures_dir):
        with patch(
            "app.services.media_service.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ffprobe", timeout=1),
        ):
            assert service.probe_streams(fixtures_dir / "audio_only.webm")["ok"] is False


# ─── Task 0.3: waveform peaks ────────────────────────────────────────

class TestExtractWaveform:
    def test_returns_exactly_400_bounded_ints(self, fixtures_dir):
        result = extract_waveform(fixtures_dir / "audio_only.webm", timeout=30)
        assert result is not None
        assert len(result.peaks) == WAVEFORM_BUCKETS == 400
        assert all(isinstance(p, int) and 0 <= p <= 100 for p in result.peaks)
        assert max(result.peaks) == 100
        assert result.duration == pytest.approx(1.0, abs=0.1)

    def test_silence_is_400_zeros_not_none(self, fixtures_dir):
        result = extract_waveform(fixtures_dir / "silent.webm", timeout=30)
        assert result is not None
        assert result.peaks == [0] * 400

    def test_undecodable_file_is_none(self, fixtures_dir):
        assert extract_waveform(fixtures_dir / "garbage.webm", timeout=30) is None

    def test_video_without_audio_is_none(self, fixtures_dir):
        assert extract_waveform(fixtures_dir / "video_real.webm", timeout=30) is None

    def test_decoded_duration_when_container_has_none(self, fixtures_dir):
        result = extract_waveform(fixtures_dir / "live.webm", timeout=30)
        assert result is not None
        assert result.duration == pytest.approx(1.0, abs=0.1)


# ─── Task 0.2: process_uploaded_file ─────────────────────────────────

class TestProcessAudioOnlyContainer:
    def test_audio_only_webm_becomes_audio_as_m4a(
        self, service, test_db, test_user, test_entry, fixtures_dir
    ):
        media = _stage_upload(
            service, test_db, test_user, test_entry,
            fixtures_dir / "audio_only.webm", filename="dictation.webm",
        )
        old_path = service.media_root / media.file_path

        done = _process(service, test_db, test_user, media)

        assert done.upload_status == UploadStatus.COMPLETED
        assert done.media_type == MediaType.AUDIO
        assert done.mime_type == "audio/mp4"
        assert done.duration == pytest.approx(1.0, abs=0.1)
        assert done.width is None and done.height is None
        assert done.thumbnail_path is None
        assert len(done.waveform_peaks) == 400
        assert done.file_path == f"{test_user.id}/audio/dictation.m4a"
        assert done.original_filename == "dictation.m4a"
        stored = service.media_root / done.file_path
        assert stored.exists()
        assert done.file_size == stored.stat().st_size
        assert not old_path.exists()
        assert not old_path.parent.exists()  # empty videos/ directory is tidied
        assert not (service.media_root / str(test_user.id) / "audio" / "dictation.webm").exists()

    def test_audio_only_mp4_becomes_audio_mp4(
        self, service, test_db, test_user, test_entry, fixtures_dir
    ):
        """libmagic says video/mp4 for a plain-brand MP4 holding only AAC."""
        media = _stage_upload(
            service, test_db, test_user, test_entry,
            fixtures_dir / "audio_isom.mp4", filename="dictation.mp4", mime_type="video/mp4",
        )
        done = _process(service, test_db, test_user, media)
        assert done.upload_status == UploadStatus.COMPLETED
        assert done.media_type == MediaType.AUDIO
        assert done.mime_type == "audio/mp4"
        # Already AAC: moved, never re-encoded.
        assert done.file_path == f"{test_user.id}/audio/dictation.mp4"

    def test_m4a_brand_is_normalised_to_audio_mp4(
        self, service, test_db, test_user, test_entry, fixtures_dir
    ):
        """libmagic says audio/x-m4a for an M4A-branded file."""
        media = _stage_upload(
            service, test_db, test_user, test_entry,
            fixtures_dir / "audio_only.m4a", filename="dictation.m4a",
            directory="audio", mime_type="audio/x-m4a", media_type=MediaType.AUDIO,
        )
        done = _process(service, test_db, test_user, media)
        assert done.media_type == MediaType.AUDIO
        assert done.mime_type == "audio/mp4"
        assert done.duration == pytest.approx(1.0, abs=0.1)

    def test_live_recording_duration_falls_back_to_decoded_length(
        self, service, test_db, test_user, test_entry, fixtures_dir
    ):
        media = _stage_upload(
            service, test_db, test_user, test_entry,
            fixtures_dir / "live.webm", filename="live.webm",
        )
        done = _process(service, test_db, test_user, media)
        assert done.media_type == MediaType.AUDIO
        assert done.duration == pytest.approx(1.0, abs=0.1)

    def test_silent_recording_stores_zeros(
        self, service, test_db, test_user, test_entry, fixtures_dir
    ):
        media = _stage_upload(
            service, test_db, test_user, test_entry,
            fixtures_dir / "silent.webm", filename="silent.webm",
        )
        done = _process(service, test_db, test_user, media)
        assert done.waveform_peaks == [0] * 400

    def test_real_video_webm_is_still_video_and_not_moved(
        self, service, test_db, test_user, test_entry, fixtures_dir
    ):
        media = _stage_upload(
            service, test_db, test_user, test_entry,
            fixtures_dir / "video_real.webm", filename="clip.webm",
        )
        original_path = media.file_path

        done = _process(service, test_db, test_user, media)

        assert done.upload_status == UploadStatus.COMPLETED
        assert done.media_type == MediaType.VIDEO
        assert done.mime_type == "video/webm"
        assert done.file_path == original_path
        assert (service.media_root / original_path).exists()
        assert done.waveform_peaks is None
        assert done.duration == pytest.approx(1.0, abs=0.1)  # §2.3 for video too
        assert (done.width, done.height) == (64, 64)

    def test_native_audio_gets_duration_and_peaks_without_moving(
        self, service, test_db, test_user, test_entry, fixtures_dir
    ):
        media = _stage_upload(
            service, test_db, test_user, test_entry,
            fixtures_dir / "tone.wav", filename="tone.wav",
            directory="audio", mime_type="audio/wav", media_type=MediaType.AUDIO,
        )
        original_path = media.file_path
        done = _process(service, test_db, test_user, media)
        assert done.media_type == MediaType.AUDIO
        assert done.file_path == original_path
        assert done.duration == pytest.approx(1.0, abs=0.1)
        assert len(done.waveform_peaks) == 400

    def test_probe_failure_on_ambiguous_container_never_completes_as_video(
        self, service, test_db, test_user, test_entry, fixtures_dir
    ):
        media = _stage_upload(
            service, test_db, test_user, test_entry,
            fixtures_dir / "audio_only.webm", filename="dictation.webm",
        )
        original_path = media.file_path
        failed_probe = {"ok": False, "has_video": False, "has_audio": False, "duration": None}

        with patch.object(service, "probe_streams", return_value=failed_probe):
            done = _process(service, test_db, test_user, media)

        assert done.upload_status == UploadStatus.FAILED
        assert done.processing_error
        assert done.media_type == MediaType.VIDEO  # never blessed, never relabelled
        assert done.file_path == original_path
        assert (service.media_root / original_path).exists()

    def test_container_with_no_playable_stream_is_rejected(
        self, service, test_db, test_user, test_entry, fixtures_dir
    ):
        media = _stage_upload(
            service, test_db, test_user, test_entry,
            fixtures_dir / "audio_only.webm", filename="empty.webm",
        )
        empty_probe = {"ok": True, "has_video": False, "has_audio": False, "duration": None}

        with patch.object(service, "probe_streams", return_value=empty_probe):
            done = _process(service, test_db, test_user, media)

        assert done.upload_status == UploadStatus.FAILED
        assert "no playable" in done.processing_error
        assert done.media_type == MediaType.VIDEO

    def test_commit_failure_after_move_puts_the_file_back(
        self, service, test_db, test_user, test_entry, fixtures_dir
    ):
        media = _stage_upload(
            service, test_db, test_user, test_entry,
            fixtures_dir / "audio_only.webm", filename="dictation.webm",
        )
        original_path = media.file_path
        audio_path = service.media_root / str(test_user.id) / "audio" / "dictation.webm"

        with patch.object(
            service, "_update_media_metadata", side_effect=RuntimeError("db went away")
        ):
            done = _process(service, test_db, test_user, media)

        assert done.upload_status == UploadStatus.FAILED
        assert done.file_path == original_path
        assert (service.media_root / original_path).exists()
        assert not audio_path.exists()
        assert not audio_path.with_suffix(".m4a").exists()
        assert not audio_path.parent.exists()

    def test_reprocessing_identical_bytes_adopts_the_existing_audio_file(
        self, service, test_db, test_user, test_entry, fixtures_dir
    ):
        """Storage is keyed by checksum, so the audio path may already exist."""
        first = _stage_upload(
            service, test_db, test_user, test_entry,
            fixtures_dir / "audio_only.webm", filename="same.webm",
        )
        _process(service, test_db, test_user, first)

        second = _stage_upload(
            service, test_db, test_user, test_entry,
            fixtures_dir / "audio_only.webm", filename="same.webm",
        )
        stale_video_path = service.media_root / second.file_path

        done = _process(service, test_db, test_user, second)

        assert done.upload_status == UploadStatus.COMPLETED
        assert done.media_type == MediaType.AUDIO
        assert done.mime_type == "audio/mp4"
        assert done.file_path == f"{test_user.id}/audio/same.m4a"
        assert (service.media_root / done.file_path).exists()
        assert not stale_video_path.exists()
        assert not (service.media_root / str(test_user.id) / "audio" / "same.webm").exists()

    def test_records_sharing_the_stored_file_follow_the_move(
        self, service, test_db, test_user, test_entry, fixtures_dir
    ):
        media = _stage_upload(
            service, test_db, test_user, test_entry,
            fixtures_dir / "audio_only.webm", filename="shared.webm",
        )
        sibling = MomentMedia(
            moment_id=test_entry.moment_id,
            media_type=MediaType.VIDEO,
            mime_type="video/webm",
            upload_status=UploadStatus.PENDING,
            file_path=media.file_path,
            original_filename="Morning walk.webm",
            file_size=media.file_size,
        )
        test_db.add(sibling)
        test_db.commit()

        done = _process(service, test_db, test_user, media)
        test_db.expire_all()

        moved_sibling = test_db.get(MomentMedia, sibling.id)
        assert moved_sibling.file_path == done.file_path
        assert moved_sibling.mime_type == "audio/mp4"
        assert moved_sibling.file_size == done.file_size
        assert moved_sibling.original_filename == "Morning walk.m4a"
        # The sibling's own queued task then finds the file at its recorded path.
        finished = _process(service, test_db, test_user, sibling)
        assert finished.upload_status == UploadStatus.COMPLETED
        assert finished.media_type == MediaType.AUDIO


# ─── Conversion to M4A (iOS Safari cannot reliably play WebM) ────────

class TestConvertToM4a:
    def test_converted_file_is_aac_with_moov_first(
        self, service, test_db, test_user, test_entry, fixtures_dir
    ):
        media = _stage_upload(
            service, test_db, test_user, test_entry,
            fixtures_dir / "live.webm", filename="voice-note.webm",
        )
        done = _process(service, test_db, test_user, media)

        stored = service.media_root / done.file_path
        probe = service.probe_streams(stored)
        assert (probe["audio_codec"], probe["audio_channels"]) == ("aac", 1)
        assert probe["duration"] == pytest.approx(1.0, abs=0.1)
        data = stored.read_bytes()
        assert data.index(b"moov") < data.index(b"mdat")  # +faststart

    def test_failed_conversion_keeps_the_original_recording(
        self, service, test_db, test_user, test_entry, fixtures_dir
    ):
        media = _stage_upload(
            service, test_db, test_user, test_entry,
            fixtures_dir / "audio_only.webm", filename="dictation.webm",
        )
        real_run = subprocess.run

        def ffmpeg_fails(cmd, *args, **kwargs):
            if cmd[0] == "ffmpeg":
                return subprocess.CompletedProcess(cmd, 1, "", "encoder unavailable")
            return real_run(cmd, *args, **kwargs)

        with patch("app.services.media_service.subprocess.run", side_effect=ffmpeg_fails):
            done = _process(service, test_db, test_user, media)

        audio_dir = service.media_root / str(test_user.id) / "audio"
        assert done.upload_status == UploadStatus.COMPLETED
        assert done.media_type == MediaType.AUDIO
        assert done.mime_type == "audio/webm"
        assert done.file_path == f"{test_user.id}/audio/dictation.webm"
        assert (service.media_root / done.file_path).exists()
        assert sorted(p.name for p in audio_dir.iterdir()) == ["dictation.webm"]

    def test_aac_is_not_reencoded(
        self, service, test_db, test_user, test_entry, fixtures_dir
    ):
        media = _stage_upload(
            service, test_db, test_user, test_entry,
            fixtures_dir / "audio_only.m4a", filename="dictation.m4a",
            directory="audio", mime_type="audio/x-m4a", media_type=MediaType.AUDIO,
        )
        before = (service.media_root / media.file_path).read_bytes()
        done = _process(service, test_db, test_user, media)
        assert done.file_path == media.file_path
        assert (service.media_root / done.file_path).read_bytes() == before


class TestOpusAlreadyNamedM4a:
    def test_recording_is_kept_when_it_is_its_own_target(
        self, service, test_db, test_user, test_entry, fixtures_dir
    ):
        media = _stage_upload(
            service, test_db, test_user, test_entry,
            fixtures_dir / "opus_in_mp4.m4a", filename="dictation.m4a",
            directory="audio", mime_type="audio/mp4", media_type=MediaType.AUDIO,
        )
        before = (service.media_root / media.file_path).read_bytes()

        done = _process(service, test_db, test_user, media)

        assert done.upload_status == UploadStatus.COMPLETED
        assert done.file_path == media.file_path
        assert (service.media_root / done.file_path).read_bytes() == before


class TestExistingConversionTarget:
    @pytest.mark.parametrize("occupant", ["opus_in_mp4.m4a", "garbage.webm"])
    def test_recording_is_kept_when_the_target_is_not_aac(
        self, service, test_db, test_user, test_entry, fixtures_dir, occupant
    ):
        media = _stage_upload(
            service, test_db, test_user, test_entry,
            fixtures_dir / "audio_only.webm", filename="dictation.webm",
        )
        audio_dir = service.media_root / str(test_user.id) / "audio"
        audio_dir.mkdir(parents=True)
        shutil.copy(fixtures_dir / occupant, audio_dir / "dictation.m4a")

        done = _process(service, test_db, test_user, media)

        assert done.upload_status == UploadStatus.COMPLETED
        assert done.mime_type == "audio/webm"
        assert done.file_path == f"{test_user.id}/audio/dictation.webm"
        assert (service.media_root / done.file_path).exists()

    def test_existing_aac_is_adopted_with_its_duration(
        self, service, test_db, test_user, test_entry, fixtures_dir
    ):
        media = _stage_upload(
            service, test_db, test_user, test_entry,
            fixtures_dir / "live.webm", filename="dictation.webm",
        )
        audio_dir = service.media_root / str(test_user.id) / "audio"
        audio_dir.mkdir(parents=True)
        shutil.copy(fixtures_dir / "audio_only.m4a", audio_dir / "dictation.m4a")

        done = _process(service, test_db, test_user, media)

        assert done.file_path == f"{test_user.id}/audio/dictation.m4a"
        assert done.mime_type == "audio/mp4"
        assert done.duration == pytest.approx(1.0, abs=0.1)
        assert not (audio_dir / "dictation.webm").exists()


class TestNameForStoredFile:
    @pytest.mark.parametrize(
        ("filename", "stored", "expected"),
        [
            ("note.webm", "u/audio/abc.m4a", "note.m4a"),
            ("Note.WEBM", "u/audio/abc.m4a", "Note.m4a"),
            ("note.m4a", "u/audio/abc.m4a", "note.m4a"),
            # Not a media extension: the whole name is kept.
            ("Walk 1.5", "u/audio/abc.m4a", "Walk 1.5.m4a"),
            (None, "u/audio/abc.m4a", None),
            ("note.webm", None, "note.webm"),
        ],
    )
    def test_takes_the_stored_extension(self, filename, stored, expected):
        assert MediaService._name_for_stored_file(filename, stored) == expected
