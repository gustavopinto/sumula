#!/usr/bin/env bash
# Conta linhas de código do projeto usando cloc.
# Exclui todas as pastas ocultas (iniciadas com '.') encontradas na raiz.

cd "$(dirname "$0")"

hidden=$(find . -maxdepth 1 -mindepth 1 -name '.*' -type d | sed 's|^\./||' | tr '\n' ',' | sed 's/,$//')

cloc . --exclude-dir="$hidden" "$@"
