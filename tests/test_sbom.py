"""R43, R49: the SBOM covers the runtime dependencies and the optional extras, never the
dev tools."""

import json
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEV_ONLY = {"pytest", "pytest-cov", "ruff", "mypy", "pip-audit"}


def test_sbom_lists_the_extras_and_no_dev_only_package():
    uv = shutil.which("uv")
    assert uv, "uv must be on PATH to export the SBOM"
    result = subprocess.run(  # noqa: S603 - fixed argv list, no shell
        [
            uv,
            "export",
            "--locked",
            "--all-extras",
            "--format",
            "cyclonedx1.5",
            "--no-dev",
            "--preview-features",
            "sbom-export",
            "--quiet",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    sbom = json.loads(result.stdout)
    assert sbom["metadata"]["component"]["name"] == "xgenerateposts"
    names = {component["name"] for component in sbom["components"]}
    assert "anthropic" in names
    assert not names & DEV_ONLY
