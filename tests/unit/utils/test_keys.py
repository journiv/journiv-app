from app.utils.keys import generate_stable_key


def test_generate_stable_key_normalizes_text():
    key = generate_stable_key("activity", "  Héalth & Fitness  ")
    assert key == "activity_health_fitness"


def test_generate_stable_key_falls_back_when_name_empty():
    key = generate_stable_key("mood", "!!!")
    assert key == "mood_item"
