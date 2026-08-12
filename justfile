alias reuse := lint-reuse

default:
    @just --list

# Every gate
check: verify-input build-check coverage validate test lint lint-reuse

# Verify hash of vendored source input
verify-input:
    ./tools/verify_input.py

# Rebuild every source's dist/ file
build:
    ./sources/mcelroy/build.py

# Rebuild into memory and fail if the committed dist/ file differs
build-check:
    ./sources/mcelroy/build.py --check

# Every input line is mapped, dropped, or a build failure
coverage *sources:
    ./tools/coverage.py {{sources}}

# quick and dirty validator
validate *files:
    uv run --frozen esoterica-validate {{files}}

# The workspace's tests
test *args:
    uv run --frozen pytest {{args}}

# Formatting and lint, checked but not written
lint:
    uv run --frozen ruff format --check .
    uv run --frozen ruff check .

# Write the formatting and the fixable lint
fmt:
    uv run --frozen ruff format .
    uv run --frozen ruff check --fix .

lint-reuse:
    uvx reuse lint

# Self-test the deterministic TOML writer
emit-test:
    ./tools/emit.py

# Refuse to release a source under a version its built file does not state
release-check source version *args:
    ./tools/release_check.py {{source}} {{version}} {{args}}
