"""
Unit tests for MediaStorageService reference counting and deduplication.
"""
import uuid
from io import BytesIO

import pytest
from sqlmodel import Session, create_engine

from app.models.entry import Entry
from app.models.moment import MomentMedia
from app.models.enums import JournalColor, MediaType
from app.models.journal import Journal
from app.models.moment import Moment
from app.models.user import User
from app.services.media_storage_service import MediaStorageService


@pytest.fixture
def temp_media_root(tmp_path):
    """Create a temporary media root directory."""
    media_root = tmp_path / "media"
    media_root.mkdir()
    return media_root


@pytest.fixture
def test_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")

    # Create all tables
    from app.models.base import BaseModel
    BaseModel.metadata.create_all(engine)

    session = Session(engine)
    yield session
    session.close()


@pytest.fixture
def test_user(test_db: Session):
    """Create a test user."""
    user = User(
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        password="hashed_password",
        name="Test User",
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def test_journal(test_db: Session, test_user: User):
    """Create a test journal."""
    journal = Journal(
        user_id=test_user.id,
        title="Test Journal",
        color=JournalColor.BLUE,
    )
    test_db.add(journal)
    test_db.commit()
    test_db.refresh(journal)
    return journal


@pytest.fixture
def test_entries(test_db: Session, test_journal: Journal):
    """Create two test entries."""
    moment_a = Moment(user_id=test_journal.user_id, logged_timezone="UTC")
    moment_b = Moment(user_id=test_journal.user_id, logged_timezone="UTC")
    test_db.add(moment_a)
    test_db.add(moment_b)
    test_db.commit()
    test_db.refresh(moment_a)
    test_db.refresh(moment_b)

    entry_a = Entry(
        journal_id=test_journal.id,
        user_id=test_journal.user_id,
        moment_id=moment_a.id,
        title="Entry A",
        content="Test content A",
    )
    entry_b = Entry(
        journal_id=test_journal.id,
        user_id=test_journal.user_id,
        moment_id=moment_b.id,
        title="Entry B",
        content="Test content B",
    )
    test_db.add(entry_a)
    test_db.add(entry_b)
    test_db.commit()
    test_db.refresh(entry_a)
    test_db.refresh(entry_b)
    return entry_a, entry_b


def create_test_image_bytes():
    """Create a simple test image (1x1 pixel JPEG)."""
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07"
        b"\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
        b"\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00\xff\xd9"
    )


def test_media_deduplication_stores_one_file(temp_media_root, test_db, test_user):
    """Test that uploading the same file twice only stores one physical file."""
    storage_service = MediaStorageService(temp_media_root, test_db)

    image_bytes = create_test_image_bytes()
    user_id = str(test_user.id)

    # Upload the same file twice
    path1, checksum1, was_dedup1 = storage_service.store_media(
        source=BytesIO(image_bytes),
        user_id=user_id,
        media_type="images",
        extension=".jpg"
    )

    path2, checksum2, was_dedup2 = storage_service.store_media(
        source=BytesIO(image_bytes),
        user_id=user_id,
        media_type="images",
        extension=".jpg"
    )

    # Both should have the same checksum and path
    assert checksum1 == checksum2
    assert path1 == path2
    assert was_dedup1 is False  # First upload is not deduplicated
    assert was_dedup2 is True   # Second upload is deduplicated

    # Only one physical file should exist
    full_path = temp_media_root / path1
    assert full_path.exists()

    # Count files in the directory
    files = list(temp_media_root.rglob("*.jpg"))
    assert len(files) == 1


def test_reference_counting_prevents_premature_deletion(
    temp_media_root, test_db, test_user, test_journal, test_entries
):
    """
    Test that files with multiple references are not deleted until all references are removed.

    This is the core test for the bug fix.
    """
    storage_service = MediaStorageService(temp_media_root, test_db)

    entry_a, entry_b = test_entries
    image_bytes = create_test_image_bytes()
    user_id = str(test_user.id)

    # Store the image (will be used by both entries)
    relative_path, checksum, _ = storage_service.store_media(
        source=BytesIO(image_bytes),
        user_id=user_id,
        media_type="images",
        extension=".jpg"
    )

    full_path = temp_media_root / relative_path
    assert full_path.exists()

    # Create two media records pointing to the same file
    media_a = MomentMedia(
        moment_id=entry_a.moment_id,
        media_type=MediaType.IMAGE,
        file_path=relative_path,
        original_filename="test.jpg",
        file_size=len(image_bytes),
        mime_type="image/jpeg",
        checksum=checksum,
    )
    media_b = MomentMedia(
        moment_id=entry_b.moment_id,
        media_type=MediaType.IMAGE,
        file_path=relative_path,
        original_filename="test.jpg",
        file_size=len(image_bytes),
        mime_type="image/jpeg",
        checksum=checksum,
    )

    test_db.add(media_a)
    test_db.add(media_b)
    test_db.commit()

    # Delete media_a's database record
    test_db.delete(media_a)
    test_db.commit()

    # Try to delete the physical file - should NOT delete because media_b still references it
    was_deleted = storage_service.delete_media(
        relative_path=relative_path,
        checksum=checksum,
        user_id=user_id,
        force=False
    )

    assert was_deleted is False, "File should NOT be deleted (still has 1 reference)"
    assert full_path.exists(), "Physical file should still exist"

    # Delete media_b's database record
    test_db.delete(media_b)
    test_db.commit()

    # Now try to delete the physical file - should succeed (no more references)
    was_deleted = storage_service.delete_media(
        relative_path=relative_path,
        checksum=checksum,
        user_id=user_id,
        force=False
    )

    assert was_deleted is True, "File should be deleted (no more references)"
    assert not full_path.exists(), "Physical file should be deleted"


def test_delete_without_db_raises_error_when_not_forced(temp_media_root):
    """Test that delete_media raises RuntimeError when db=None and force=False."""
    storage_service = MediaStorageService(temp_media_root, db=None)

    image_bytes = create_test_image_bytes()
    user_id = str(uuid.uuid4())

    # Store the image
    relative_path, checksum, _ = storage_service.store_media(
        source=BytesIO(image_bytes),
        user_id=user_id,
        media_type="images",
        extension=".jpg"
    )

    # Attempting to delete without db and without force should raise RuntimeError
    with pytest.raises(RuntimeError, match="Cannot perform safe deletion"):
        storage_service.delete_media(
            relative_path=relative_path,
            checksum=checksum,
            user_id=user_id,
            force=False
        )


def test_delete_without_db_allows_forced_deletion(temp_media_root):
    """Test that delete_media works with force=True even when db=None."""
    storage_service = MediaStorageService(temp_media_root, db=None)

    image_bytes = create_test_image_bytes()
    user_id = str(uuid.uuid4())

    # Store the image
    relative_path, checksum, _ = storage_service.store_media(
        source=BytesIO(image_bytes),
        user_id=user_id,
        media_type="images",
        extension=".jpg"
    )

    full_path = temp_media_root / relative_path
    assert full_path.exists()

    # Force delete should work even without db
    was_deleted = storage_service.delete_media(
        relative_path=relative_path,
        checksum=checksum,
        user_id=user_id,
        force=True
    )

    assert was_deleted is True
    assert not full_path.exists()


def test_force_delete_ignores_reference_count(
    temp_media_root, test_db, test_user, test_journal, test_entries
):
    """Test that force=True deletes the file regardless of reference count."""
    storage_service = MediaStorageService(temp_media_root, test_db)

    entry_a, entry_b = test_entries
    image_bytes = create_test_image_bytes()
    user_id = str(test_user.id)

    # Store the image
    relative_path, checksum, _ = storage_service.store_media(
        source=BytesIO(image_bytes),
        user_id=user_id,
        media_type="images",
        extension=".jpg"
    )

    full_path = temp_media_root / relative_path

    # Create two media records
    media_a = MomentMedia(
        moment_id=entry_a.moment_id,
        media_type=MediaType.IMAGE,
        file_path=relative_path,
        original_filename="test.jpg",
        file_size=len(image_bytes),
        mime_type="image/jpeg",
        checksum=checksum,
    )
    media_b = MomentMedia(
        moment_id=entry_b.moment_id,
        media_type=MediaType.IMAGE,
        file_path=relative_path,
        original_filename="test.jpg",
        file_size=len(image_bytes),
        mime_type="image/jpeg",
        checksum=checksum,
    )

    test_db.add(media_a)
    test_db.add(media_b)
    test_db.commit()

    # Force delete should work even with 2 references
    was_deleted = storage_service.delete_media(
        relative_path=relative_path,
        checksum=checksum,
        user_id=user_id,
        force=True
    )

    assert was_deleted is True
    assert not full_path.exists()


def test_reference_count_is_user_scoped(temp_media_root, test_db):
    """Test that reference counting is scoped per user."""
    storage_service = MediaStorageService(temp_media_root, test_db)

    # Create two users
    user1 = User(
        email=f"user1_{uuid.uuid4().hex[:8]}@example.com",
        password="hashed_password",
        name="User One",
    )
    user2 = User(
        email=f"user2_{uuid.uuid4().hex[:8]}@example.com",
        password="hashed_password",
        name="User Two",
    )
    test_db.add(user1)
    test_db.add(user2)
    test_db.commit()

    # Create journals for each user
    journal1 = Journal(user_id=user1.id, title="Journal 1", color=JournalColor.BLUE)
    journal2 = Journal(user_id=user2.id, title="Journal 2", color=JournalColor.BLUE)
    test_db.add(journal1)
    test_db.add(journal2)
    test_db.commit()

    # Create entries for each user
    moment1 = Moment(user_id=user1.id, logged_timezone="UTC")
    moment2 = Moment(user_id=user2.id, logged_timezone="UTC")
    test_db.add(moment1)
    test_db.add(moment2)
    test_db.commit()
    test_db.refresh(moment1)
    test_db.refresh(moment2)

    entry1 = Entry(
        journal_id=journal1.id,
        user_id=user1.id,
        moment_id=moment1.id,
        title="Entry 1",
        content="Content 1",
    )
    entry2 = Entry(
        journal_id=journal2.id,
        user_id=user2.id,
        moment_id=moment2.id,
        title="Entry 2",
        content="Content 2",
    )
    test_db.add(entry1)
    test_db.add(entry2)
    test_db.commit()

    image_bytes = create_test_image_bytes()

    # Each user stores the same image in their own space
    path1, checksum1, _ = storage_service.store_media(
        source=BytesIO(image_bytes),
        user_id=str(user1.id),
        media_type="images",
        extension=".jpg"
    )

    path2, checksum2, _ = storage_service.store_media(
        source=BytesIO(image_bytes),
        user_id=str(user2.id),
        media_type="images",
        extension=".jpg"
    )

    # Different users get different paths (user isolation)
    assert path1 != path2
    assert str(user1.id) in path1
    assert str(user2.id) in path2

    # Same content, same checksum
    assert checksum1 == checksum2

    # Create media records
    media1 = MomentMedia(
        moment_id=entry1.moment_id,
        media_type=MediaType.IMAGE,
        file_path=path1,
        original_filename="test.jpg",
        file_size=len(image_bytes),
        mime_type="image/jpeg",
        checksum=checksum1,
    )
    media2 = MomentMedia(
        moment_id=entry2.moment_id,
        media_type=MediaType.IMAGE,
        file_path=path2,
        original_filename="test.jpg",
        file_size=len(image_bytes),
        mime_type="image/jpeg",
        checksum=checksum2,
    )
    test_db.add(media1)
    test_db.add(media2)
    test_db.commit()

    # Delete user1's media - should delete because only 1 reference for user1
    test_db.delete(media1)
    test_db.commit()

    was_deleted = storage_service.delete_media(
        relative_path=path1,
        checksum=checksum1,
        user_id=str(user1.id),
        force=False
    )

    assert was_deleted is True
    assert not (temp_media_root / path1).exists()

    # User2's file should still exist (separate user scope)
    assert (temp_media_root / path2).exists()


def test_store_media_rejects_path_traversal_in_extension(temp_media_root, test_db, test_user):
    """Test that store_media rejects path traversal attempts in extension parameter."""
    storage_service = MediaStorageService(temp_media_root, test_db)
    image_bytes = create_test_image_bytes()
    user_id = str(test_user.id)

    malicious_extensions = [
        "/../../../etc/passwd.jpg",
        "..\\..\\..\\windows\\system32\\config\\sam.jpg",
        "../evil.jpg",
        "..\\evil.jpg",
        ".jpg/../evil",
    ]

    for malicious_ext in malicious_extensions:
        with pytest.raises(ValueError, match="extension contains invalid path characters"):
            storage_service.store_media(
                source=BytesIO(image_bytes),
                user_id=user_id,
                media_type="images",
                extension=malicious_ext
            )
