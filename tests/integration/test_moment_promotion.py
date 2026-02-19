"""
Integration test for moment promotion logic.
"""
from tests.integration.helpers import sample_jpeg_bytes
from tests.lib import ApiUser, JournivApiClient


def test_promote_moment_to_entry_links_moment_and_media(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    """
    Promote a quick log (moment) to a full entry.
    Verify that:
    1. The entry is linked to the original moment.
    2. The moment metadata (primary mood) is updated during promotion.
    3. Media stays owned by the original moment (moment-first).
    4. No duplicate moment or entry is created.
    """
    token = api_user.access_token

    # 1. Create a journal
    journal = api_client.create_journal(token, title="Promotion Test Journal")

    # 2. Create a quick log (moment)
    mood = api_client.create_mood(token, name="Excited", score=5)
    moment = api_client.create_moment(
        token,
        note="Quick log that will be promoted",
        primary_mood_id=mood["id"],
        mood_activity=[{"mood_id": mood["id"]}]
    )
    moment_id = moment["id"]

    # 3. Attach media to the moment
    media = api_client.upload_media(
        token,
        moment_id=moment_id,
        filename="quick-log.jpg",
        content=sample_jpeg_bytes(),
        content_type="image/jpeg"
    )
    media_id = media["id"]

    # 4. Promote to entry by creating an entry with moment_id and updated mood
    new_mood = api_client.create_mood(token, name="Super Excited", score=5)
    entry = api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Promoted Entry",
        content="This entry was promoted from a quick log.",
        moment_id=moment_id,
        primary_mood_id=new_mood["id"]
    )

    # 5. Verify entry response
    assert entry["moment_id"] == moment_id

    # 6. Verify moment mood was updated during promotion
    all_moments = api_client.request("GET", "/moments", token=token).json()["items"]
    updated_moment = next((m for m in all_moments if m["id"] == moment_id), None)
    assert updated_moment is not None, f"Moment {moment_id} not found in /moments"
    assert updated_moment["primary_mood_id"] == new_mood["id"]
    assert updated_moment["entry"]["id"] == entry["id"]

    # 7. Verify media remains linked to the original moment (moment-first media ownership)
    moment_media_list = api_client.request(
        "GET",
        f"/moments/{moment_id}/media",
        token=token,
        expected=(200,),
    ).json()
    promoted_media = next((m for m in moment_media_list if m["id"] == media_id), None)
    assert promoted_media is not None, "Media should be visible in the moment's media list"
    assert promoted_media["moment_id"] == moment_id, "Media ownership must remain on the original moment"

    # 8. Verify NO duplicate moments and entries
    all_moments = api_client.list_moments(token)
    assert len(all_moments) == 1, "There should still be only one moment after promotion"
    assert all_moments[0]["id"] == moment_id
    all_entries = api_client.list_entries(token)
    assert len(all_entries) == 1, "Promotion should not create duplicate entries"
    assert all_entries[0]["id"] == entry["id"]
    assert all_entries[0]["moment_id"] == moment_id
