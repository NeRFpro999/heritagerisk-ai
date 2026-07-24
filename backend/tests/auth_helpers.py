"""Shared reviewer-login and CSRF helpers for route tests."""

from typing import Any

from fastapi.testclient import TestClient

from app.auth import (
    CSRF_COOKIE_NAME,
    CSRF_FORM_FIELD,
    hash_reviewer_password,
)
from app.config import settings


TEST_REVIEWER_USERNAME = "test.reviewer"
TEST_REVIEWER_PASSWORD = "fake-reviewer-password"
TEST_REVIEWER_PASSWORD_HASH = hash_reviewer_password(
    TEST_REVIEWER_PASSWORD,
    salt=b"heritagerisk-test-salt",
)


def configure_test_reviewer() -> tuple[str, str]:
    """Install one fake reviewer credential and return the prior settings."""
    previous = (settings.reviewer_username, settings.reviewer_password_hash)
    settings.reviewer_username = TEST_REVIEWER_USERNAME
    settings.reviewer_password_hash = TEST_REVIEWER_PASSWORD_HASH
    return previous


def restore_test_reviewer(previous: tuple[str, str]) -> None:
    """Restore reviewer settings after a test fixture finishes."""
    settings.reviewer_username, settings.reviewer_password_hash = previous


def csrf_token(client: TestClient) -> str:
    """Prime and return the CSRF cookie used by form posts."""
    client.get("/")
    token = client.cookies.get(CSRF_COOKIE_NAME)
    assert token
    return token


def csrf_data(
    client: TestClient,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return form data with the current double-submit token."""
    form_data = dict(data or {})
    form_data[CSRF_FORM_FIELD] = csrf_token(client)
    return form_data


def post_form(
    client: TestClient,
    url: str,
    *,
    data: dict[str, Any] | None = None,
    files=None,
    follow_redirects: bool = True,
):
    """POST ordinary form data with a valid CSRF token."""
    return client.post(
        url,
        data=csrf_data(client, data),
        files=files,
        follow_redirects=follow_redirects,
    )


def login_reviewer(
    client: TestClient,
    *,
    next_path: str = "/observations/review",
):
    """Authenticate the configured fake reviewer through the real login route."""
    response = post_form(
        client,
        "/reviewer/login",
        data={
            "username": TEST_REVIEWER_USERNAME,
            "password": TEST_REVIEWER_PASSWORD,
            "next_path": next_path,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == next_path
    return response
