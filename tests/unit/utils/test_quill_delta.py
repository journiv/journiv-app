from app.utils.quill_delta import (
    extract_plain_text,
    extract_media_sources,
    replace_media_ids,
    wrap_plain_text,
)


def test_extract_plain_text_concatenates_strings():
    delta = {
        "ops": [
            {"insert": "Hello "},
            {"insert": {"image": "x"}},
            {"insert": "World"},
        ]
    }
    assert extract_plain_text(delta) == "Hello World"


def test_extract_plain_text_handles_invalid_delta():
    assert extract_plain_text(None) == ""
    assert extract_plain_text({"ops": "invalid"}) == ""


def test_wrap_plain_text():
    # Empty/None content produces Delta with just newline (required by Quill format)
    assert wrap_plain_text(None) == {"ops": [{"insert": "\n"}]}
    assert wrap_plain_text("") == {"ops": [{"insert": "\n"}]}

    # Text without trailing newline gets one added
    assert wrap_plain_text("Hi") == {"ops": [{"insert": "Hi\n"}]}

    # Text with trailing newline is preserved as-is
    assert wrap_plain_text("Hi\n") == {"ops": [{"insert": "Hi\n"}]}


def test_replace_media_ids_rewrites_and_sanitizes():
    delta = {"ops": [{"insert": {"image": "old-id", "video": "ignored"}}]}
    updated = replace_media_ids(delta, {"old-id": "new-id"})
    assert updated["ops"][0]["insert"] == {"image": "new-id"}


def test_replace_media_ids_invalid_delta():
    assert replace_media_ids(None, {"a": "b"}) == {"ops": []}
    assert replace_media_ids({"ops": "bad"}, {"a": "b"}) == {"ops": []}


def test_extract_media_sources_from_delta():
    delta = {
        "ops": [
            {"insert": "Some text"},
            {"insert": {"image": "image-id-1"}},
            {"insert": {"video": "video-id-1"}},
            {"insert": {"audio": "audio-id-1"}},
            {"insert": "More text"},
        ]
    }
    sources = extract_media_sources(delta)
    assert sources == ["image-id-1", "video-id-1", "audio-id-1"]


def test_extract_media_sources_handles_invalid_delta():
    assert extract_media_sources(None) == []
    assert extract_media_sources({"ops": "invalid"}) == []
    assert extract_media_sources({"ops": []}) == []


def test_extract_media_sources_filters_non_string_values():
    delta = {
        "ops": [
            {"insert": {"image": "valid-id"}},
            {"insert": {"video": 123}},  # Non-string value
            {"insert": {"audio": None}},  # None value
        ]
    }
    sources = extract_media_sources(delta)
    assert sources == ["valid-id"]
