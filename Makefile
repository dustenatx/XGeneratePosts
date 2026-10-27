.PHONY: check audit sbom install-check

# Lint, format check, types and tests, all from uv.lock. CI's lint job runs this.
check:
	uv run --locked ruff check .
	uv run --locked ruff format --check .
	uv run --locked mypy
	uv run --locked pytest --cov=xgenerateposts --cov-report=term-missing --cov-fail-under=83

# pip-audit on the lock, exported with hashes so pip-audit doesn't resolve again.
audit:
	mkdir -p build
	uv export --locked --format requirements.txt --no-emit-project --quiet --output-file build/requirements-audit.txt
	uv run --locked pip-audit --strict --disable-pip --requirement build/requirements-audit.txt

# CycloneDX SBOM of the runtime dependencies (R43). uv's export is a preview feature.
sbom:
	mkdir -p build
	uv export --locked --format cyclonedx1.5 --no-dev --preview-features sbom-export --quiet --output-file build/sbom.cdx.json

# R42: build, install the wheel into a fresh venv with a temporary HOME, check xgp init.
install-check:
	bash scripts/install-check.sh
