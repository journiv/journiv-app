"""
Verify data integrity after upgrading from OLD to NEW version.

This script validates that all data seeded in the old version
is still accessible and correct after the upgrade.
"""
from tests.upgrade.helpers import (
    login,
    get_journals,
    get_entries,
    get_tags,
    get_mood_logs,
    get_user_settings,
    wait_for_ready,
    http_get
)


# Test user credentials (same as seeding)
TEST_EMAIL = "upgrade-test@journiv.com"
TEST_PASSWORD = "NotRealPassword123"


def test_wait_for_new_version():
    """Wait for the new version to be ready."""
    print("\n=== Waiting for NEW version to be ready ===")
    wait_for_ready(max_attempts=30, delay=2)


def test_health_endpoint():
    """Verify health endpoint returns 200 (no migration issues)."""
    print("\n=== Checking health endpoint ===")

    response = http_get("/health")
    assert response.status_code == 200, f"Health check failed: {response.status_code}"

    # Try to parse response
    try:
        health_data = response.json()
        print(f"✓ Health check passed: {health_data}")
    except Exception:
        print(f"✓ Health check passed (status 200)")


def test_login_with_old_credentials():
    """Verify login still works with old credentials."""
    print(f"\n=== Logging in with old credentials: {TEST_EMAIL} ===")

    token = login(TEST_EMAIL, TEST_PASSWORD)
    assert token, "Failed to login with old credentials"

    print(f"Login successful with old credentials")
    return token


def test_verify_journals_exist():
    """Verify journals still exist after upgrade."""
    print("\n=== Verifying journals ===")

    token = login(TEST_EMAIL, TEST_PASSWORD)
    journals = get_journals(token)

    print(f"Found {len(journals)} journals")
    assert len(journals) >= 2, f"Expected at least 2 journals, found {len(journals)}"

    # Verify journal structure
    for journal in journals[:2]:
        assert "id" in journal, "Journal missing 'id' field"
        assert "title" in journal, "Journal missing 'title' field"
        print(f"Journal: {journal['title']}")

    print(f"All journals verified")


def test_verify_entries_exist():
    """Verify entries still exist after upgrade."""
    print("\n=== Verifying entries ===")

    token = login(TEST_EMAIL, TEST_PASSWORD)
    entries = get_entries(token)

    print(f"Found {len(entries)} entries")
    assert len(entries) >= 4, f"Expected at least 4 entries, found {len(entries)}"

    # Verify entry structure
    for entry in entries[:4]:
        assert "id" in entry, "Entry missing 'id' field"
        assert "title" in entry or "content" in entry, "Entry missing title/content"

        title = entry.get("title", "Untitled")
        print(f"Entry: {title}")

    print(f"All entries verified")


def test_verify_tags_exist():
    """Verify tags still exist after upgrade."""
    print("\n=== Verifying tags ===")

    token = login(TEST_EMAIL, TEST_PASSWORD)
    tags = get_tags(token)

    print(f"Found {len(tags)} tags")
    assert len(tags) >= 4, f"Expected at least 4 tags, found {len(tags)}"

    # Verify tag structure
    for tag in tags[:4]:
        assert "id" in tag, "Tag missing 'id' field"
        assert "name" in tag, "Tag missing 'name' field"
        print(f"Tag: {tag['name']}")

    print(f"All tags verified")


def test_verify_mood_logs_exist():
    """Verify mood logs still exist after upgrade (if they were created)."""
    print("\n=== Verifying mood logs ===")

    token = login(TEST_EMAIL, TEST_PASSWORD)

    try:
        mood_logs = get_mood_logs(token)
        print(f"Found {len(mood_logs)} mood logs")

        if len(mood_logs) > 0:
            # Verify mood log structure if they exist
            for mood_log in mood_logs[:min(3, len(mood_logs))]:
                assert "id" in mood_log, "Mood log missing 'id' field"
                assert "mood_id" in mood_log or "entry_id" in mood_log, "Mood log missing mood_id/entry_id"

                notes = mood_log.get("notes", "No notes")
                print(f"Mood log: {notes[:50]}")

            print(f"All mood logs verified")
        else:
            print("No mood logs found (may not have been created in OLD version)")
    except Exception as e:
        print(f"Mood logs not available (skipping verification): {e}")


def test_verify_user_settings_readable():
    """Verify user settings are still readable."""
    print("\n=== Verifying user settings ===")

    token = login(TEST_EMAIL, TEST_PASSWORD)
    settings = get_user_settings(token)

    assert "email" in settings or "id" in settings, "Settings missing required fields"
    print(f"User settings accessible")

    # Check if email matches
    if "email" in settings:
        assert settings["email"] == TEST_EMAIL, f"Email mismatch: {settings['email']} != {TEST_EMAIL}"
        print(f"Email verified: {settings['email']}")


def test_verify_data_integrity():
    """Comprehensive data integrity check."""
    print("\n=== Comprehensive Data Integrity Check ===")

    token = login(TEST_EMAIL, TEST_PASSWORD)

    # Get all data
    journals = get_journals(token)
    entries = get_entries(token)
    tags = get_tags(token)

    try:
        mood_logs = get_mood_logs(token)
    except Exception:
        mood_logs = []

    # Verify counts
    print(f"\nData counts after upgrade:")
    print(f"  Journals: {len(journals)}")
    print(f"  Entries: {len(entries)}")
    print(f"  Tags: {len(tags)}")
    print(f"  Mood logs: {len(mood_logs)}")

    assert len(journals) >= 2, "Missing journals after upgrade"
    assert len(entries) >= 4, "Missing entries after upgrade"
    assert len(tags) >= 4, "Missing tags after upgrade"

    print(f"\nData integrity verified")


def test_verify_new_api_functionality():
    """Verify that new API functionality still works."""
    print("\n=== Testing New API Functionality ===")

    token = login(TEST_EMAIL, TEST_PASSWORD)

    # Test that we can still read data (API compatibility)
    response = http_get("/entries/", token, params={"limit": 10})
    assert response.status_code == 200, f"API call failed: {response.status_code}"

    print(f"New API calls work correctly")


def test_no_data_loss():
    """Final verification that no data was lost during upgrade."""
    print("\n=== Final Data Loss Check ===")

    token = login(TEST_EMAIL, TEST_PASSWORD)

    journals = get_journals(token)
    entries = get_entries(token)
    tags = get_tags(token)

    try:
        mood_logs = get_mood_logs(token)
    except Exception:
        mood_logs = []

    # These should match or exceed what we seeded
    expected_journals = 2
    expected_entries = 4
    expected_tags = 4

    print(f"\nExpected vs Actual:")
    print(f"  Journals: {expected_journals} → {len(journals)}")
    print(f"  Entries: {expected_entries} → {len(entries)}")
    print(f"  Tags: {expected_tags} → {len(tags)}")
    print(f"  Mood logs: {len(mood_logs)} (optional - depends on OLD version features)")

    assert len(journals) >= expected_journals, f"Data loss detected: journals {len(journals)} < {expected_journals}"
    assert len(entries) >= expected_entries, f"Data loss detected: entries {len(entries)} < {expected_entries}"
    assert len(tags) >= expected_tags, f"Data loss detected: tags {len(tags)} < {expected_tags}"

    print(f"\n================================================")
    print("NO DATA LOSS - Upgrade successful!")
    print("================================================\n")


if __name__ == "__main__":
    # Can be run directly or via pytest
    test_wait_for_new_version()
    test_health_endpoint()
    test_login_with_old_credentials()
    test_verify_journals_exist()
    test_verify_entries_exist()
    test_verify_tags_exist()
    test_verify_mood_logs_exist()
    test_verify_user_settings_readable()
    test_verify_data_integrity()
    test_verify_new_api_functionality()
    test_no_data_loss()
    print("\nAll verification tests passed!")
