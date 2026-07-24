"""Minimal reviewer session, password, and CSRF helpers."""

import hashlib
import hmac
import secrets
import string
from urllib.parse import urlencode, urlsplit, urlunsplit

from fastapi import HTTPException, Request

from app.config import settings


SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64
SCRYPT_MAX_MEMORY = 64 * 1024 * 1024

SESSION_COOKIE_NAME = "heritagerisk_reviewer"
SESSION_REVIEWER_KEY = "reviewer_username"
SESSION_MAX_AGE_SECONDS = 8 * 60 * 60
SESSION_SECRET_KEY = (
    settings.session_secret_key.strip()
    if settings.session_secret_key.strip()
    else secrets.token_urlsafe(48)
)

CSRF_COOKIE_NAME = "heritagerisk_csrf"
CSRF_FORM_FIELD = "csrf_token"
_CSRF_TOKEN_CHARS = frozenset(string.ascii_letters + string.digits + "-_")


def hash_reviewer_password(
    password: str,
    *,
    salt: bytes | None = None,
) -> str:
    """Return a salted scrypt hash suitable for REVIEWER_PASSWORD_HASH."""
    if not password:
        raise ValueError("Reviewer password cannot be empty.")

    password_salt = salt or secrets.token_bytes(16)
    if len(password_salt) < 16:
        raise ValueError("Reviewer password salt must be at least 16 bytes.")

    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=password_salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
        maxmem=SCRYPT_MAX_MEMORY,
    )
    return (
        f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}$"
        f"{password_salt.hex()}${digest.hex()}"
    )


def _parse_reviewer_password_hash(
    encoded_hash: str,
) -> tuple[int, int, int, bytes, bytes] | None:
    try:
        algorithm, n_text, r_text, p_text, salt_hex, digest_hex = (
            encoded_hash.split("$")
        )
        n = int(n_text)
        r = int(r_text)
        p = int(p_text)
        salt = bytes.fromhex(salt_hex)
        expected_digest = bytes.fromhex(digest_hex)
    except (TypeError, ValueError):
        return None

    if (
        algorithm != "scrypt"
        or (n, r, p) != (SCRYPT_N, SCRYPT_R, SCRYPT_P)
        or len(salt) < 16
        or len(expected_digest) != SCRYPT_DKLEN
    ):
        return None
    return n, r, p, salt, expected_digest


def verify_reviewer_password(password: str, encoded_hash: str) -> bool:
    """Verify a password against the supported scrypt hash format."""
    if not password or not encoded_hash:
        return False

    parsed_hash = _parse_reviewer_password_hash(encoded_hash)
    if parsed_hash is None:
        return False
    n, r, p, salt, expected_digest = parsed_hash

    try:
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected_digest),
            maxmem=SCRYPT_MAX_MEMORY,
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(candidate, expected_digest)


def authenticate_reviewer(username: str, password: str) -> str | None:
    """Return the configured reviewer name only for valid credentials."""
    configured_username = settings.reviewer_username.strip()
    configured_hash = settings.reviewer_password_hash.strip()
    if not configured_username or not configured_hash:
        return None

    supplied_username = username.strip()
    username_matches = hmac.compare_digest(
        supplied_username,
        configured_username,
    )
    password_matches = verify_reviewer_password(password, configured_hash)
    return configured_username if username_matches and password_matches else None


def current_reviewer(request: Request) -> str | None:
    """Return the authenticated reviewer stored in the signed session."""
    configured_username = settings.reviewer_username.strip()
    configured_hash = settings.reviewer_password_hash.strip()
    if (
        not configured_username
        or not configured_hash
        or _parse_reviewer_password_hash(configured_hash) is None
    ):
        return None
    try:
        session_username = request.session.get(SESSION_REVIEWER_KEY)
    except AssertionError:
        return None
    if not isinstance(session_username, str):
        return None
    if not hmac.compare_digest(session_username, configured_username):
        return None
    return configured_username


def sign_in_reviewer(request: Request, username: str) -> None:
    """Replace the current session with one authenticated reviewer identity."""
    request.session.clear()
    request.session[SESSION_REVIEWER_KEY] = username


def sign_out_reviewer(request: Request) -> None:
    """Clear the signed reviewer session."""
    request.session.clear()


def safe_next_path(
    value: str | None,
    default: str = "/observations/review",
) -> str:
    """Return a local redirect path, rejecting absolute and ambiguous URLs."""
    if not value or "\\" in value or any(ord(char) < 32 for char in value):
        return default

    parsed = urlsplit(value)
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.fragment
        or not parsed.path.startswith("/")
        or parsed.path.startswith("//")
    ):
        return default
    return urlunsplit(("", "", parsed.path, parsed.query, ""))


def reviewer_login_url(request: Request) -> str:
    """Build a login URL that returns to the requested local path."""
    requested_path = "/observations/review"
    if request.method in {"GET", "HEAD"}:
        requested_path = request.url.path
        if request.url.query:
            requested_path = f"{requested_path}?{request.url.query}"
    return f"/reviewer/login?{urlencode({'next': requested_path})}"


def require_reviewer(request: Request) -> str:
    """FastAPI dependency that redirects unauthenticated reviewer requests."""
    reviewer = current_reviewer(request)
    if reviewer is None:
        raise HTTPException(
            status_code=303,
            detail="Reviewer login required.",
            headers={"Location": reviewer_login_url(request)},
        )
    return reviewer


def _valid_csrf_token(value: str | None) -> bool:
    return bool(
        isinstance(value, str)
        and 32 <= len(value) <= 128
        and all(char in _CSRF_TOKEN_CHARS for char in value)
    )


async def csrf_cookie_middleware(request: Request, call_next):
    """Expose one CSRF token to templates and mirror it in a browser cookie."""
    csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
    set_cookie = not _valid_csrf_token(csrf_token)
    if set_cookie:
        csrf_token = secrets.token_urlsafe(32)

    request.state.csrf_token = csrf_token
    response = await call_next(request)
    if set_cookie:
        response.set_cookie(
            CSRF_COOKIE_NAME,
            csrf_token,
            max_age=SESSION_MAX_AGE_SECONDS,
            path="/",
            httponly=False,
            samesite="lax",
        )
    return response


async def verify_csrf(request: Request) -> None:
    """FastAPI dependency implementing double-submit CSRF validation."""
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    try:
        form = await request.form()
        submitted_value = form.get(CSRF_FORM_FIELD)
    except (RuntimeError, ValueError):
        submitted_value = None
    submitted_token = (
        submitted_value if isinstance(submitted_value, str) else None
    )

    if (
        not _valid_csrf_token(cookie_token)
        or not _valid_csrf_token(submitted_token)
        or not hmac.compare_digest(cookie_token, submitted_token)
    ):
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing CSRF token.",
        )


async def require_reviewer_form(request: Request) -> str:
    """Authenticate a reviewer and validate a state-changing form request."""
    reviewer = require_reviewer(request)
    await verify_csrf(request)
    return reviewer
