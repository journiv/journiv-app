"""Unit tests for PDF content sanitization guard."""

from app.services.pdf_service import PDFService


def test_sanitize_html_for_template_allows_safe_markup():
    html_content = "<p>Hello <strong>world</strong></p>"
    assert PDFService._sanitize_html_for_template(html_content) == html_content


def test_sanitize_html_for_template_escapes_suspicious_markup():
    html_content = '<p>hello</p><script>alert("x")</script>'
    sanitized = PDFService._sanitize_html_for_template(html_content)
    assert "<script>" not in sanitized
    assert "&lt;script&gt;" in sanitized
