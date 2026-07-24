"""Classify persisted AI provider strings consistently."""

from typing import Literal


PROVIDER_AZURE = "azure"
PROVIDER_MOCK = "mock"
PROVIDER_UNKNOWN = "unknown"

ProviderIdentity = Literal["azure", "mock", "unknown"]


def azure_provider_name(deployment: object) -> str:
    """Return the persisted Azure provider name without inventing a deployment."""
    if isinstance(deployment, str) and deployment.strip():
        return f"azure:{deployment.strip()}"
    return "azure:unconfigured"


def provider_identity(provider_str: object) -> ProviderIdentity:
    """Return the provider family for current, legacy, or unknown values."""
    if not isinstance(provider_str, str):
        return PROVIDER_UNKNOWN

    normalized = provider_str.strip().casefold()
    if normalized == "mock":
        return PROVIDER_MOCK
    if normalized == "azure_openai":
        return PROVIDER_AZURE

    prefix, separator, deployment = normalized.partition(":")
    if prefix == "azure" and separator and deployment.strip():
        return PROVIDER_AZURE
    return PROVIDER_UNKNOWN
