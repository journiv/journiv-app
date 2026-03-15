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
