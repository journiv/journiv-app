"""
Tests for Delta-to-HTML render engine.
"""
from app.utils.render_engine import render_delta_to_html


def test_render_empty_delta():
    """Test rendering empty delta."""
    assert render_delta_to_html(None) == ""
    assert render_delta_to_html({}) == ""
    assert render_delta_to_html({"ops": []}) == ""


def test_render_plain_text():
    """Test rendering plain text paragraph."""
    delta = {
        "ops": [
            {"insert": "Hello world\n"}
        ]
    }
    result = render_delta_to_html(delta)
    assert result == "<p>Hello world<br></p>"


def test_render_bold_text():
    """Test rendering bold text."""
    delta = {
        "ops": [
            {"insert": "Hello "},
            {"insert": "world", "attributes": {"bold": True}},
            {"insert": "\n"}
        ]
    }
    result = render_delta_to_html(delta)
    assert "<strong>world</strong>" in result
    assert "Hello" in result


def test_render_italic_text():
    """Test rendering italic text."""
    delta = {
        "ops": [
            {"insert": "Hello "},
            {"insert": "world", "attributes": {"italic": True}},
            {"insert": "\n"}
        ]
    }
    result = render_delta_to_html(delta)
    assert "<em>world</em>" in result


def test_render_link():
    """Test rendering hyperlinks."""
    delta = {
        "ops": [
            {"insert": "Visit "},
            {"insert": "Google", "attributes": {"link": "https://google.com"}},
            {"insert": "\n"}
        ]
    }
    result = render_delta_to_html(delta)
    assert '<a href="https://google.com"' in result
    assert 'target="_blank"' in result
    assert 'rel="noopener noreferrer"' in result
    assert "Google</a>" in result


def test_render_header():
    """Test rendering headers."""
    delta_h1 = {
        "ops": [
            {"insert": "Main Title", "attributes": {"header": 1}},
            {"insert": "\n"}
        ]
    }
    result = render_delta_to_html(delta_h1)
    assert "<h1>Main Title</h1>" in result

    delta_h2 = {
        "ops": [
            {"insert": "Subtitle", "attributes": {"header": 2}},
            {"insert": "\n"}
        ]
    }
    result = render_delta_to_html(delta_h2)
    assert "<h2>Subtitle</h2>" in result


def test_render_bullet_list():
    """Test rendering bullet lists."""
    delta = {
        "ops": [
            {"insert": "First item", "attributes": {"list": "bullet"}},
            {"insert": "\n"},
            {"insert": "Second item", "attributes": {"list": "bullet"}},
            {"insert": "\n"}
        ]
    }
    result = render_delta_to_html(delta)
    assert "<ul>" in result
    assert "<li>First item</li>" in result
    assert "<li>Second item</li>" in result
    assert "</ul>" in result


def test_render_ordered_list():
    """Test rendering ordered lists."""
    delta = {
        "ops": [
            {"insert": "First", "attributes": {"list": "ordered"}},
            {"insert": "\n"},
            {"insert": "Second", "attributes": {"list": "ordered"}},
            {"insert": "\n"}
        ]
    }
    result = render_delta_to_html(delta)
    assert "<ol>" in result
    assert "<li>First</li>" in result
    assert "<li>Second</li>" in result
    assert "</ol>" in result


def test_render_blockquote():
    """Test rendering blockquotes."""
    delta = {
        "ops": [
            {"insert": "This is a quote", "attributes": {"blockquote": True}},
            {"insert": "\n"}
        ]
    }
    result = render_delta_to_html(delta)
    assert "<blockquote>This is a quote" in result
    assert "</blockquote>" in result


def test_render_code_block():
    """Test rendering code blocks."""
    delta = {
        "ops": [
            {"insert": "def hello():", "attributes": {"code-block": True}},
            {"insert": "\n"},
            {"insert": "    print('world')", "attributes": {"code-block": True}},
            {"insert": "\n"}
        ]
    }
    result = render_delta_to_html(delta)
    assert "<pre><code>" in result
    assert "def hello():" in result
    assert "print(&#x27;world&#x27;)" in result  # Escaped quotes
    assert "</code></pre>" in result


def test_render_inline_code():
    """Test rendering inline code."""
    delta = {
        "ops": [
            {"insert": "Use "},
            {"insert": "console.log()", "attributes": {"code": True}},
            {"insert": " for debugging\n"}
        ]
    }
    result = render_delta_to_html(delta)
    assert "<code>console.log()</code>" in result


def test_render_image():
    """Test rendering image embeds."""
    delta = {
        "ops": [
            {"insert": {"image": "media-123"}},
            {"insert": "\n"}
        ]
    }

    # Without media URL resolver, raw ID is not a safe URL and is skipped
    result = render_delta_to_html(delta)
    assert '<img src=' not in result

    # With media URL resolver
    def resolver(media_type, media_id):
        return f"/pub/media/{media_id}"

    result = render_delta_to_html(delta, media_url_resolver=resolver)
    assert '<img src="/pub/media/media-123"' in result


def test_render_image_in_print_mode_allows_file_uri():
    """Test rendering image embeds in print mode with local file URIs."""
    delta = {
        "ops": [
            {"insert": {"image": "media-123"}},
            {"insert": "\n"}
        ]
    }

    def resolver(media_type, media_id):
        return "file:///tmp/media-123.jpg"

    result = render_delta_to_html(delta, media_url_resolver=resolver, print_mode=True)
    assert '<img src="file:///tmp/media-123.jpg"' in result


def test_render_video():
    """Test rendering video embeds."""
    delta = {
        "ops": [
            {"insert": {"video": "video-456"}},
            {"insert": "\n"}
        ]
    }

    def resolver(media_type, media_id):
        return f"/pub/media/{media_id}"

    result = render_delta_to_html(delta, media_url_resolver=resolver)
    assert '<video controls src="/pub/media/video-456"' in result


def test_render_video_in_print_mode_as_placeholder():
    """Test rendering video embeds in print mode without a preview thumbnail."""
    delta = {
        "ops": [
            {"insert": {"video": "video-456"}},
            {"insert": "\n"}
        ]
    }

    def resolver(media_type, media_id):
        return f"/pub/media/{media_id}"

    result = render_delta_to_html(delta, media_url_resolver=resolver, print_mode=True)
    assert "<video controls" not in result
    assert "Video attachment" in result
    assert 'href="/pub/media/video-456"' not in result


def test_render_video_in_print_mode_with_preview():
    """Test rendering inline video previews in print mode."""
    delta = {
        "ops": [
            {"insert": {"video": "video-456"}},
            {"insert": "\n"}
        ]
    }

    def resolver(media_type, media_id):
        return f"/pub/media/{media_id}"

    def preview_resolver(media_type, media_id):
        return f"/pub/media/{media_id}/thumb.jpg"

    result = render_delta_to_html(
        delta,
        media_url_resolver=resolver,
        media_preview_resolver=preview_resolver,
        print_mode=True,
    )
    assert 'class="media-preview media-preview-video"' in result
    assert 'src="/pub/media/video-456/thumb.jpg"' in result
    assert 'href="/pub/media/video-456"' not in result
    assert "media-video-glyph" in result


def test_render_video_in_print_mode_can_be_suppressed():
    """Test suppressing inline print rendering for video embeds."""
    delta = {
        "ops": [
            {"insert": {"video": "video-456"}},
            {"insert": "\n"}
        ]
    }

    def resolver(media_type, media_id):
        return f"/pub/media/{media_id}"

    result = render_delta_to_html(
        delta,
        media_url_resolver=resolver,
        print_mode=True,
        suppress_media_types={"video"},
    )
    assert "Video:" not in result
    assert 'href="/pub/media/video-456"' not in result


def test_render_audio_in_print_mode_as_link():
    """Test rendering audio embeds in print mode."""
    delta = {
        "ops": [
            {"insert": {"audio": "audio-789"}},
            {"insert": "\n"}
        ]
    }

    def resolver(media_type, media_id):
        return f"/pub/media/{media_id}"

    result = render_delta_to_html(delta, media_url_resolver=resolver, print_mode=True)
    assert "Audio:" in result
    assert 'href="/pub/media/audio-789"' in result


def test_render_complex_formatting():
    """Test rendering with multiple inline formats."""
    delta = {
        "ops": [
            {"insert": "This is "},
            {"insert": "bold and italic", "attributes": {"bold": True, "italic": True}},
            {"insert": "\n"}
        ]
    }
    result = render_delta_to_html(delta)
    # Both tags should be present (order may vary)
    assert "<strong>" in result
    assert "<em>" in result
    assert "bold and italic" in result


def test_html_escaping():
    """Test that HTML entities are properly escaped."""
    delta = {
        "ops": [
            {"insert": "<script>alert('xss')</script>\n"}
        ]
    }
    result = render_delta_to_html(delta)
    # Script tags should be escaped
    assert "<script>" not in result
    assert "&lt;script&gt;" in result
    assert "alert(&#x27;xss&#x27;)" in result


def test_url_escaping():
    """Test that dangerous URL schemes are blocked."""
    delta = {
        "ops": [
            {"insert": "Click", "attributes": {"link": "javascript:alert('xss')"}},
            {"insert": "\n"}
        ]
    }
    result = render_delta_to_html(delta)
    assert "javascript:alert" not in result
    assert "<a " not in result


def test_render_multiple_paragraphs():
    """Test rendering multiple paragraphs."""
    delta = {
        "ops": [
            {"insert": "First paragraph\n"},
            {"insert": "Second paragraph\n"}
        ]
    }
    result = render_delta_to_html(delta)
    # Current implementation treats consecutive newlines as line breaks in same paragraph
    assert "<p>" in result
    assert "First paragraph" in result
    assert "Second paragraph" in result


def test_render_mixed_list_and_non_list_paragraphs():
    """
    Test the bug described in issue #362:
    When multiple paragraphs are selected and list formatting is applied,
    only the last paragraph should get the list attribute in a buggy frontend.
    
    This tests the backend's ability to handle a delta with mixed list and non-list items.
    The expected behavior is that ONLY list items should appear in a list, while
    non-list items should appear as plain paragraphs.
    
    Example scenario:
    - User has: "Para 1", "Para 2", "Para 3"
    - User selects all and clicks "Numbered List"
    - Buggy frontend produces: Para1 (list), Para2 (no list), Para3 (list)
    - Result: Two separate lists with Para2 in between
    """
    delta = {
        "ops": [
            {"insert": "Para 1", "attributes": {"list": "ordered"}},
            {"insert": "\n"},
            {"insert": "Para 2"},  # NO list attribute - should be plain paragraph
            {"insert": "\n"},
            {"insert": "Para 3", "attributes": {"list": "ordered"}},
            {"insert": "\n"}
        ]
    }
    result = render_delta_to_html(delta)
    
    # Should have TWO separate ordered lists (because Para 2 breaks them)
    assert result.count("<ol>") == 2, f"Expected 2 ordered lists, got: {result}"
    assert result.count("</ol>") == 2, f"Expected 2 closing </ol> tags, got: {result}"
    
    # Para 1 should be in a list
    assert "<li>Para 1</li>" in result
    
    # Para 2 should be in a plain paragraph (not in a list)
    assert "<p>Para 2<br></p>" in result
    
    # Para 3 should be in a list (second list)
    assert "<li>Para 3</li>" in result
    
    # The HTML should have the structure: <ol><li>Para 1</li></ol><p>Para 2</p><ol><li>Para 3</li></ol>
    expected_structure = "<ol><li>Para 1</li></ol><p>Para 2<br></p><ol><li>Para 3</li></ol>"
    assert result == expected_structure, f"Expected: {expected_structure}\nGot: {result}"


def test_render_all_paragraphs_with_list_formatting():
    """
    Test the correct scenario: when all paragraphs get list formatting,
    they should all appear in a single list.
    """
    delta = {
        "ops": [
            {"insert": "Para 1", "attributes": {"list": "ordered"}},
            {"insert": "\n"},
            {"insert": "Para 2", "attributes": {"list": "ordered"}},
            {"insert": "\n"},
            {"insert": "Para 3", "attributes": {"list": "ordered"}},
            {"insert": "\n"}
        ]
    }
    result = render_delta_to_html(delta)
    
    # Should have ONE ordered list
    assert result.count("<ol>") == 1
    assert result.count("</ol>") == 1
    
    # All items should be list items
    assert "<li>Para 1</li>" in result
    assert "<li>Para 2</li>" in result
    assert "<li>Para 3</li>" in result
    
    expected = "<ol><li>Para 1</li><li>Para 2</li><li>Para 3</li></ol>"
    assert result == expected, f"Expected: {expected}\nGot: {result}"


def test_render_mixed_bullet_and_ordered_lists():
    """
    Test switching between bullet and ordered lists.
    Each list type change should create a new list.
    """
    delta = {
        "ops": [
            {"insert": "Item 1", "attributes": {"list": "bullet"}},
            {"insert": "\n"},
            {"insert": "Item 2", "attributes": {"list": "bullet"}},
            {"insert": "\n"},
            {"insert": "Item A", "attributes": {"list": "ordered"}},
            {"insert": "\n"},
            {"insert": "Item B", "attributes": {"list": "ordered"}},
            {"insert": "\n"}
        ]
    }
    result = render_delta_to_html(delta)
    
    # Should have one bullet list and one ordered list
    assert result.count("<ul>") == 1
    assert result.count("</ul>") == 1
    assert result.count("<ol>") == 1
    assert result.count("</ol>") == 1
    
    # Check content
    assert "<li>Item 1</li>" in result
    assert "<li>Item 2</li>" in result
    assert "<li>Item A</li>" in result
    assert "<li>Item B</li>" in result
    
    # Verify order
    expected = "<ul><li>Item 1</li><li>Item 2</li></ul><ol><li>Item A</li><li>Item B</li></ol>"
    assert result == expected, f"Expected: {expected}\nGot: {result}"


def test_render_list_followed_by_paragraph_followed_by_list():
    """
    Test list, then paragraph, then list again.
    This should create two separate lists.
    """
    delta = {
        "ops": [
            {"insert": "List item 1", "attributes": {"list": "ordered"}},
            {"insert": "\n"},
            {"insert": "Plain paragraph"},
            {"insert": "\n"},
            {"insert": "List item 2", "attributes": {"list": "ordered"}},
            {"insert": "\n"}
        ]
    }
    result = render_delta_to_html(delta)
    
    # Should have two ordered lists
    assert result.count("<ol>") == 2
    assert result.count("</ol>") == 2
    
    # Plain paragraph should be in <p> tags
    assert "<p>Plain paragraph<br></p>" in result
    
    # Check list items
    assert "<li>List item 1</li>" in result
    assert "<li>List item 2</li>" in result
    
    expected = "<ol><li>List item 1</li></ol><p>Plain paragraph<br></p><ol><li>List item 2</li></ol>"
    assert result == expected, f"Expected: {expected}\nGot: {result}"


def test_render_list_with_formatting():
    """
    Test that inline formatting works with list items.
    Note: In Quill Delta, each text segment that's part of a list item
    should have the list attribute.
    """
    delta = {
        "ops": [
            {"insert": "Item with bold", "attributes": {"bold": True, "list": "ordered"}},
            {"insert": "\n"},
            {"insert": "Item with italic", "attributes": {"italic": True, "list": "ordered"}},
            {"insert": "\n"}
        ]
    }
    result = render_delta_to_html(delta)
    
    # Should have one ordered list
    assert result.count("<ol>") == 1
    assert result.count("</ol>") == 1
    
    # Check formatting is preserved in list items
    assert "<strong>Item with bold</strong>" in result
    assert "<em>Item with italic</em>" in result
