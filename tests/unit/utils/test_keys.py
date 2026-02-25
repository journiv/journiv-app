import pytest

from app.utils.keys import generate_import_stable_key, generate_stable_key


def test_generate_stable_key_normalizes_text():
    key = generate_stable_key("activity", "  Héalth & Fitness  ")
    assert key == "activity_health_fitness"


def test_generate_stable_key_falls_back_when_name_empty():
    key = generate_stable_key("mood", "!!!")
    assert key == "mood_item"


def test_generate_stable_key_truncates_to_model_limit():
    key = generate_stable_key("activity", "a" * 500)
    assert len(key) == 100
    assert key.startswith("activity_")


def test_generate_stable_key_rejects_overlong_prefix():
    with pytest.raises(ValueError):
        generate_stable_key("p" * 100, "name")


def test_generate_import_stable_key_returns_none_for_empty_values():
    assert generate_import_stable_key("imp_goal", None) is None
    assert generate_import_stable_key("imp_goal", "") is None
    assert generate_import_stable_key("imp_goal", "   ") is None


def test_generate_import_stable_key_preserves_external_id_shape():
    key = generate_import_stable_key("imp_goal", "goal::A/B?C")
    assert key == "imp_goal:goal::A/B?C"


def test_generate_import_stable_key_truncates_with_hash_suffix():
    key = generate_import_stable_key("imp_goal", "x" * 300)
    assert key is not None
    assert len(key) == 100
    assert key.startswith("imp_goal:")
    # suffix pattern: :<12 hex chars>
    assert key[-13] == ":"
    assert all(ch in "0123456789abcdef" for ch in key[-12:])


def test_generate_import_stable_key_rejects_overlong_prefix_for_truncation_case():
    with pytest.raises(ValueError):
        generate_import_stable_key("p" * 86, "x" * 500)
