import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_azure.py"


def test_verify_azure_refuses_missing_azure_environment(tmp_path):
    env = os.environ.copy()
    for name in (
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_OPENAI_API_VERSION",
        "AZURE_OPENAI_ENABLED",
    ):
        env[name] = ""
    env["PYTHONPATH"] = str(REPO_ROOT / "backend")

    result = subprocess.run(
        [
            sys.executable,
            str(VERIFY_SCRIPT),
            "--assets",
            str(tmp_path / "missing_assets"),
            "--db-path",
            str(tmp_path / "verify.db"),
            "--uploads-dir",
            str(tmp_path / "uploads"),
            "--reports-dir",
            str(tmp_path / "reports"),
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Missing Azure environment variable(s)" in result.stderr
    assert "AZURE_OPENAI_ENDPOINT" in result.stderr
    assert "AZURE_OPENAI_API_KEY" in result.stderr
    assert "AZURE_OPENAI_DEPLOYMENT" in result.stderr
    assert "AZURE_OPENAI_API_VERSION" in result.stderr
    assert "AZURE_OPENAI_ENABLED=true" in result.stderr


def test_verify_azure_formats_human_readable_success_summary():
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from verify_azure import _format_summary

    summary = _format_summary(
        {
            "deployment": "heritage-gpt5-mini",
            "provider": "azure:heritage-gpt5-mini",
            "analysis_status": "complete",
            "latency_seconds": 1.234,
            "validated_indicator_count": 2,
            "evidence_sufficiency": "partial",
            "schema_validation_passed": True,
            "validation_passed": True,
            "preserved_failure_state": None,
        }
    )

    assert "Deployment: heritage-gpt5-mini" in summary
    assert "Provider: azure:heritage-gpt5-mini" in summary
    assert "Latency: 1.234 seconds" in summary
    assert "Validated indicators: 2" in summary
    assert "Evidence sufficiency: partial" in summary
    assert "Schema validation passed: yes" in summary


def test_verify_azure_formats_preserved_failure_state():
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from verify_azure import _format_summary

    summary = _format_summary(
        {
            "deployment": "heritage-gpt5-mini",
            "provider": "mock",
            "analysis_status": "mock",
            "latency_seconds": 0.75,
            "validated_indicator_count": 0,
            "evidence_sufficiency": "insufficient",
            "schema_validation_passed": False,
            "validation_passed": False,
            "preserved_failure_state": {
                "ai_analysis_status": "mock",
                "analysis_attempts": [
                    {
                        "status": "failed",
                        "provider": "azure:heritage-gpt5-mini",
                        "diagnostic": "transport_error",
                    }
                ],
            },
        }
    )

    assert "Schema validation passed: no" in summary
    assert "Preserved failure state:" in summary
    assert "azure:heritage-gpt5-mini" in summary
    assert "transport_error" in summary
