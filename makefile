# DepDiff — local development helpers
.PHONY: install test lint typecheck format clean build redteam

install:
pip install -e ".[dev]"

test:
python3 -m pytest

lint:
ruff check src tests

typecheck:
mypy src

format:
ruff format src tests

clean:
rm -rf dist build src/depdiff.egg-info __pycache__ .pytest_cache .mypy_cache .ruff_cache
find . -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

build:
python3 -m build

redteam:
bash scripts/red_team.sh

check: lint typecheck test redteam
