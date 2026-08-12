alias reuse := lint-reuse

default:
    @just --list

# Every gate
check: verify-input validate lint-reuse

# Verify hash of vendored source input
verify-input:
    ./tools/verify_input.py

# quick and dirty validator
validate *files:
    ./tools/validate.py {{files}}

lint-reuse:
    uvx reuse lint

# TODO
#build:
