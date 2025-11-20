"""
Seed data into the OLD version of Journiv for upgrade testing.

This script creates realistic data in the old version that will be
validated after upgrading to the new version.
"""
from datetime import date, timedelta
from tests.lib import JournivApiError
from tests.upgrade.helpers import (
    register_user,
    login,
    create_journal,
    create_entry,
    create_tag,
    get_moods,
    create_mood_log,
    upload_media,
    get_user_settings,
    wait_for_ready,
    get_entries,
    get_journals,
    get_tags,
    get_mood_logs
)


# Test user credentials (stored for verification after upgrade)
TEST_EMAIL = "upgrade-test@journiv.com"
TEST_PASSWORD = "NotRealPassword123"
TEST_NAME = "Upgrade"


def test_wait_for_application():
    """Wait for the old version to be ready."""
    print("\n=== Waiting for OLD version to be ready ===")
    wait_for_ready(max_attempts=30, delay=2)


def test_register_test_user():
    """Register the test user in the old version."""
    print(f"\n=== Registering test user: {TEST_EMAIL} ===")

    # If the user already exists we can reuse it to keep the step idempotent.
    try:
        token = login(TEST_EMAIL, TEST_PASSWORD)
        if token:
            print("User already exists, skipping registration")
            return
    except JournivApiError as exc:
        if exc.status != 401:
            raise

    result = register_user(
        email=TEST_EMAIL,
        password=TEST_PASSWORD,
        name=TEST_NAME
    )

    assert "id" in result or "user" in result or "access_token" in result
    print(f"User registered successfully")


def test_seed_data():
    """Seed comprehensive test data into the old version."""
    print(f"\n=== Seeding data into OLD version ===")

    # Login
    print(f"Logging in as {TEST_EMAIL}...")
    token = login(TEST_EMAIL, TEST_PASSWORD)
    assert token, "Failed to get access token"
    print(f"Login successful")

    # Create 2 journals
    print("\nCreating journals...")
    journal1 = create_journal(token, "Work Journal", "#3B82F6")  # blue
    journal2 = create_journal(token, "Personal Journal", "#22C55E")  # green

    print(f"Created journal 1: {journal1['title']} (ID: {journal1['id']})")
    print(f"Created journal 2: {journal2['title']} (ID: {journal2['id']})")

    # Create entries in journal 1
    print("\nCreating entries in Work Journal...")
    entry1_j1 = create_entry(
        token,
        journal1["id"],
        "Monday Meeting Notes",
        "Discussed Q4 objectives and team alignment. Key action items: 1) Review proposal 2) Schedule follow-up",
        (date.today() - timedelta(days=2)).isoformat()
    )

    entry2_j1 = create_entry(
        token,
        journal1["id"],
        "Project Planning",
        "Started planning the new feature rollout. Need to coordinate with design team and set up user testing sessions.",
        (date.today() - timedelta(days=1)).isoformat()
    )

    print(f"Created entry: {entry1_j1['title']}")
    print(f"Created entry: {entry2_j1['title']}")

    # Create entries in journal 2
    print("\nCreating entries in Personal Journal...")
    entry1_j2 = create_entry(
        token,
        journal2["id"],
        "Weekend Reflection",
        "Had a great weekend hiking with friends. Feeling refreshed and ready for the week ahead.",
        (date.today() - timedelta(days=3)).isoformat()
    )

    entry2_j2 = create_entry(
        token,
        journal2["id"],
        "Daily Gratitude",
        "Grateful for: good health, supportive family, meaningful work, and a warm home.",
        date.today().isoformat()
    )

    print(f"Created entry: {entry1_j2['title']}")
    print(f"Created entry: {entry2_j2['title']}")

    # Create tags
    print("\nCreating tags...")
    tag1 = create_tag(token, "work", "#3B82F6")  # blue
    tag2 = create_tag(token, "planning", "#8B5CF6")  # purple
    tag3 = create_tag(token, "personal", "#22C55E")  # green
    tag4 = create_tag(token, "gratitude", "#EAB308")  # yellow

    print(f"Created tag: {tag1['name']}")
    print(f"Created tag: {tag2['name']}")
    print(f"Created tag: {tag3['name']}")
    print(f"Created tag: {tag4['name']}")

    # Get system moods
    print("\nGetting system moods...")
    try:
        moods = get_moods(token)
        if len(moods) > 0:
            print(f"Found {len(moods)} system moods")

            # Use first available mood
            mood_id = moods[0]["id"]
            mood_name = moods[0].get("name", "Unknown")

            # Create mood logs for entries
            print(f"\nCreating mood logs (using mood: {mood_name})...")
            try:
                mood_log1 = create_mood_log(
                    token,
                    entry1_j1["id"],
                    mood_id,
                    "Productive meeting",
                    (date.today() - timedelta(days=2)).isoformat()
                )
                print(f"Created mood log for entry: {entry1_j1['title']}")
            except Exception as e:
                print(f"Mood logs not supported in this version (skipping): {e}")

            try:
                mood_log2 = create_mood_log(
                    token,
                    entry1_j2["id"],
                    mood_id,
                    "Feeling great after hiking",
                    (date.today() - timedelta(days=3)).isoformat()
                )
                print(f"Created mood log for entry: {entry1_j2['title']}")
            except Exception as e:
                print(f" Mood logs not supported in this version (skipping)")

            try:
                mood_log3 = create_mood_log(
                    token,
                    entry2_j2["id"],
                    mood_id,
                    "Peaceful and grateful",
                    date.today().isoformat()
                )
                print(f"Created mood log for entry: {entry2_j2['title']}")
            except Exception as e:
                print(f" Mood logs not supported in this version (skipping)")
        else:
            print("No system moods available (may not be supported in this version)")
    except Exception as e:
        print(f"Mood system not available in OLD version (skipping): {e}")

    # Upload simple text media file
    print("\nUploading media file...")
    media_content = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07"
        b"\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
        b"\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00\xff\xd9"
    )

    try:
        media = upload_media(
            token,
            entry2_j1["id"],
            "upgrade-test-image.jpg",
            media_content,
            "Test image for upgrade validation"
        )
        print(f"Uploaded media file: {media.get('original_filename', 'upgrade-test-image.jpg')}")
    except AssertionError as e:
        print(f"Media upload failed (may not be critical): {e}")
        # Continue - media upload is optional

    # Verify settings are accessible
    print("\nVerifying user settings...")
    settings = get_user_settings(token)
    assert "email" in settings or "id" in settings
    print(f"User settings accessible")

    # Final verification counts
    print("\n=== Verification Summary ===")
    journals = get_journals(token)
    entries = get_entries(token)
    tags = get_tags(token)

    try:
        mood_logs = get_mood_logs(token)
    except Exception:
        mood_logs = []

    print(f"Journals created: {len(journals)}")
    print(f"Entries created: {len(entries)}")
    print(f"Tags created: {len(tags)}")
    print(f"Mood logs created: {len(mood_logs)}")

    # Assertions
    assert len(journals) >= 2, f"Expected at least 2 journals, got {len(journals)}"
    assert len(entries) >= 4, f"Expected at least 4 entries, got {len(entries)}"
    assert len(tags) >= 4, f"Expected at least 4 tags, got {len(tags)}"
    # Mood logs are optional - not all old versions support this feature

    print("\n================================================")
    print("Data seeding completed successfully")
    print("================================================\n")


if __name__ == "__main__":
    # Can be run directly or via pytest
    test_wait_for_application()
    test_register_test_user()
    test_seed_data()
    print("\nAll seeding operations completed!")
