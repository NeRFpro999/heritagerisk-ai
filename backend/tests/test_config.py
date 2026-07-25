import logging


def test_enabled_but_missing_azure_config_warns_and_stays_mock(caplog):
    from app.config import Settings

    with caplog.at_level(logging.WARNING, logger="app.config"):
        settings = Settings(
            {
                "AZURE_OPENAI_ENABLED": "true",
                "AZURE_OPENAI_ENDPOINT": "https://fake.openai.azure.com/",
                "AZURE_OPENAI_API_KEY": "",
                "AZURE_OPENAI_DEPLOYMENT": "",
                "AZURE_OPENAI_API_VERSION": "",
            }
        )

    assert settings.azure_openai_requested is True
    assert settings.azure_openai_enabled is False
    assert settings.ai_analysis_enabled is False
    assert settings.azure_credentials_present is False
    assert settings.azure_missing_variables == (
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_OPENAI_API_VERSION",
    )
    assert "Mock analysis remains active" in caplog.text
    for name in settings.azure_missing_variables:
        assert name in caplog.text


def test_complete_v1_azure_config_enables_live_path(caplog):
    from app.config import Settings

    with caplog.at_level(logging.WARNING, logger="app.config"):
        settings = Settings(
            {
                "AZURE_OPENAI_ENABLED": "true",
                "AZURE_OPENAI_ENDPOINT": "https://fake.openai.azure.com/",
                "AZURE_OPENAI_API_KEY": "fake-key",
                "AZURE_OPENAI_DEPLOYMENT": "heritage-gpt5-mini",
                "AZURE_OPENAI_API_VERSION": "v1",
            }
        )

    assert settings.azure_openai_requested is True
    assert settings.azure_openai_enabled is True
    assert settings.ai_analysis_enabled is True
    assert settings.azure_credentials_present is True
    assert settings.azure_missing_variables == ()
    assert caplog.text == ""


def test_non_v1_api_version_warns_and_stays_mock(caplog):
    from app.config import Settings

    with caplog.at_level(logging.WARNING, logger="app.config"):
        settings = Settings(
            {
                "AZURE_OPENAI_ENABLED": "true",
                "AZURE_OPENAI_ENDPOINT": "https://fake.openai.azure.com/",
                "AZURE_OPENAI_API_KEY": "fake-key",
                "AZURE_OPENAI_DEPLOYMENT": "heritage-gpt5-mini",
                "AZURE_OPENAI_API_VERSION": "2024-10-21",
            }
        )

    assert settings.azure_openai_enabled is False
    assert settings.azure_credentials_present is False
    assert "AZURE_OPENAI_API_VERSION must be 'v1'" in caplog.text
