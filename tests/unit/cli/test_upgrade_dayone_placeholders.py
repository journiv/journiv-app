from app.cli.commands import upgrade as upgrade_cmd


def test_replace_dayone_placeholders_preserves_formatting():
    delta = {
        "ops": [
            {"insert": "Intro "},
            {"insert": "DAYONE_PHOTO:abc123", "attributes": {"bold": True}},
            {"insert": "\n", "attributes": {"header": 2}},
            {"insert": "tail DAYONE_VIDEO:vid456", "attributes": {"italic": True}},
        ]
    }
    placeholder_map = {"abc123": "media-1", "vid456": "media-2"}

    updated, changed = upgrade_cmd._replace_dayone_placeholders_in_delta(delta, placeholder_map)

    assert changed is True
    assert {"insert": "Intro "} in updated["ops"]
    assert {"insert": {"image": "media-1"}} in updated["ops"]
    assert {"insert": "\n", "attributes": {"header": 2}} in updated["ops"]
    assert {"insert": "tail ", "attributes": {"italic": True}} in updated["ops"]
    assert {"insert": {"video": "media-2"}} in updated["ops"]


def test_replace_dayone_placeholders_unmatched_tokens_kept():
    delta = {"ops": [{"insert": "DAYONE_PHOTO:missing"}]}
    placeholder_map = {}

    updated, changed = upgrade_cmd._replace_dayone_placeholders_in_delta(delta, placeholder_map)

    assert changed is False
    assert updated == delta
