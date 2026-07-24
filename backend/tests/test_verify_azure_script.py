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
        "AZURE_OPENAI_PRIMARY_DEPLOYMENT",
        "AZURE_OPENAI_ENABLED",
    ):
        env.pop(name, None)
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
    assert "AZURE_OPENAI_PRIMARY_DEPLOYMENT" in result.stderr
    assert "AZURE_OPENAI_ENABLED=true" in result.stderr
