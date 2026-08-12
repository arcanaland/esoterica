# Licensed MIT via REUSE.toml, like everything under tools/. This repo carries no inline
# SPDX headers — one mechanism, so there is nothing to drift.

# Recipes are the single source of truth for what this repo checks. CI invokes them rather
# than restating the commands, so a green local `just check` means the same thing a green
# pipeline does. Matches libarcana's arrangement.

alias reuse := lint-reuse

default:
    @just --list

# Every gate, in the order that fails cheapest first.
check: verify-input validate lint-reuse

# Verify each vendored source input against the sha256 its SOURCE.toml records.
verify-input:
    ./tools/verify_input.py

# Check built sources against the shallow subset of ESOTERICA.md §11.4 (see ADR-001).
# With no argument, globs sources/*/dist/*.toml and passes vacuously when there are none.
validate *files:
    ./tools/validate.py {{files}}

# Check that every path declares its copyright and licence (REUSE 3.3).
lint-reuse:
    uvx reuse lint

# No `build` recipe: there is no builder yet. The follow-up task adds `build` and `coverage`
# here alongside a `sources/*/build.py --check`, and `check` gains them.
