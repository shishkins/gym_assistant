#!/usr/bin/env bash
#
# Everything CI checks, in CI's order, in one command.
#
#     ./scripts/check.sh
#
# Written after a red build caused by `ruff format`. `ruff check` and
# `ruff format --check` are different tools with similar names: the first
# finds mistakes, the second compares formatting, and passing one says
# nothing about the other. Running four commands by hand means eventually
# running three of them.
#
# Keep in step with .github/workflows/ci.yml.
set -uo pipefail

cd "$(dirname "$0")/.."

failed=0

step() {
    local name=$1
    shift
    printf '\n\033[1m== %s\033[0m\n' "$name"
    if "$@"; then
        printf '\033[32m   ok\033[0m\n'
    else
        printf '\033[31m   ПРОВАЛ\033[0m\n'
        failed=$((failed + 1))
    fi
}

step "ruff check"        uv run ruff check .
step "ruff format"       uv run ruff format --check .
step "mypy"              uv run mypy src/gym_assistant
step "alembic"           uv run alembic upgrade head
step "pytest"            uv run pytest -q

echo
if [ "$failed" -gt 0 ]; then
    printf '\033[31mПровалено проверок: %d. Пушить рано.\033[0m\n' "$failed"
    exit 1
fi
printf '\033[32mВсё чисто — то же, что проверит CI.\033[0m\n'
