def test_instance_config_returns_public_settings(api_client):
    response = api_client.request("GET", "/instance/config", expected=(200,))
    payload = response.json()

    assert "import_export_max_file_size_mb" in payload
    assert "disable_signup" in payload
    assert isinstance(payload["import_export_max_file_size_mb"], int)
    assert isinstance(payload["disable_signup"], bool)


def test_instance_config_exposes_plus_capability(api_client):
    """The public config carries a Plus capability block for UI gating."""
    payload = api_client.request("GET", "/instance/config", expected=(200,)).json()

    assert "plus" in payload
    plus = payload["plus"]
    assert isinstance(plus["available"], bool)
    assert plus["tier"] in {"member", "supporter", "believer"}
    assert plus["upgrade_url"].startswith("http")
    # No license is registered in the test instance.
    assert plus["tier"] == "member"
    # Non-sensitive block only — never the signed license or binding details.
    assert "signed_license" not in plus
    assert "install_id" not in plus
