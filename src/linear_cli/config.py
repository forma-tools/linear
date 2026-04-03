"""Configuration and credential access for Linear CLI."""

from .credentials import get_credential_store

API_URL = "https://api.linear.app/graphql"


def get_api_key() -> str | None:
    """Get Linear API key from credential store."""
    return get_credential_store().get("api_key")


def save_api_key(api_key: str) -> None:
    """Save Linear API key to credential store."""
    get_credential_store().set("api_key", api_key)


def delete_api_key() -> None:
    """Delete Linear API key from credential store."""
    get_credential_store().delete("api_key")


def get_auth_source() -> str:
    """Get the source of the current credential."""
    return get_credential_store().get_source("api_key")


def get_auth_status() -> dict:
    """Get authentication status."""
    return get_credential_store().status()
