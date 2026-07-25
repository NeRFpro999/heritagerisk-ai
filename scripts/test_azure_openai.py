"""Local smoke test for the Azure OpenAI GPT-5-mini deployment.

Loads settings from .env/environment variables and prints only the model
response when the call succeeds.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, OpenAI


PROMPT = "Reply with one short sentence confirming HeritageRisk AI can call Azure OpenAI."


def _load_local_env() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    load_dotenv(repo_root / ".env", override=False)


def _required_env(name: str, message: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(message, file=sys.stderr)
        raise SystemExit(1)
    return value


def _normalise_endpoint(endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith("/openai/v1"):
        return f"{endpoint}/"
    return f"{endpoint}/openai/v1/"


def _azure_error_message(exc: APIStatusError) -> str:
    try:
        data = exc.response.json()
    except ValueError:
        return exc.response.text.strip()

    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        message = str(error.get("message", "")).strip()
        code = str(error.get("code", "")).strip()
        if code and message:
            return f"{code}: {message}"
        return message or code

    return str(data).strip()


def _print_api_error(exc: APIStatusError) -> None:
    status_code = exc.status_code
    if status_code in {401, 403}:
        print(
            "Azure OpenAI request failed with 401/403: key or permission problem. "
            "Check AZURE_OPENAI_API_KEY and deployment access.",
            file=sys.stderr,
        )
    elif status_code == 404:
        print(
            "Azure OpenAI request failed with 404: probably wrong deployment name, "
            "wrong endpoint, or the deployment is not ready.",
            file=sys.stderr,
        )
    elif status_code == 400:
        message = _azure_error_message(exc)
        detail = f" Azure error: {message}" if message else ""
        print(
            "Azure OpenAI request failed with 400: check endpoint, deployment, "
            f"and request format.{detail}",
            file=sys.stderr,
        )
    else:
        print(
            f"Azure OpenAI request failed with status {status_code}. "
            "Check the endpoint, deployment, and Azure resource status.",
            file=sys.stderr,
        )


def main() -> int:
    _load_local_env()

    api_key = _required_env("AZURE_OPENAI_API_KEY", "Missing AZURE_OPENAI_API_KEY.")
    endpoint = _normalise_endpoint(
        _required_env("AZURE_OPENAI_ENDPOINT", "Missing AZURE_OPENAI_ENDPOINT.")
    )
    deployment = _required_env(
        "AZURE_OPENAI_DEPLOYMENT",
        "Missing AZURE_OPENAI_DEPLOYMENT.",
    )
    api_version = _required_env(
        "AZURE_OPENAI_API_VERSION",
        "Missing AZURE_OPENAI_API_VERSION.",
    )
    if api_version.lower() != "v1":
        print(
            "AZURE_OPENAI_API_VERSION must be v1 for the configured endpoint.",
            file=sys.stderr,
        )
        return 1

    client = OpenAI(
        api_key=api_key,
        base_url=endpoint,
    )

    try:
        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {
                    "role": "developer",
                    "content": "You are a concise smoke-test responder.",
                },
                {
                    "role": "user",
                    "content": PROMPT,
                }
            ],
            max_completion_tokens=200,
        )
    except APIStatusError as exc:
        _print_api_error(exc)
        return 1
    except APIConnectionError:
        print(
            "Azure OpenAI connection failed. Check AZURE_OPENAI_ENDPOINT and network access.",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"Azure OpenAI test failed with {type(exc).__name__}.", file=sys.stderr)
        return 1

    content = (response.choices[0].message.content or "").strip()
    if not content:
        print("Azure OpenAI returned an empty response.", file=sys.stderr)
        return 1

    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
