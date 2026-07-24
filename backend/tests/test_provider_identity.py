from app.provider_identity import (
    PROVIDER_AZURE,
    PROVIDER_MOCK,
    PROVIDER_UNKNOWN,
    azure_provider_name,
    provider_identity,
)


def test_provider_identity_handles_current_legacy_and_unknown_values():
    assert provider_identity("azure:mydeploy") == PROVIDER_AZURE
    assert provider_identity("azure_openai") == PROVIDER_AZURE
    assert provider_identity(" Azure:MyDeploy ") == PROVIDER_AZURE
    assert provider_identity("mock") == PROVIDER_MOCK
    assert provider_identity("azure:") == PROVIDER_UNKNOWN
    assert provider_identity("other-provider") == PROVIDER_UNKNOWN
    assert provider_identity(None) == PROVIDER_UNKNOWN


def test_azure_provider_name_uses_deployment_or_unconfigured_marker():
    assert azure_provider_name("mydeploy") == "azure:mydeploy"
    assert azure_provider_name("  mydeploy  ") == "azure:mydeploy"
    assert azure_provider_name("") == "azure:unconfigured"
    assert azure_provider_name(None) == "azure:unconfigured"
