#!/usr/bin/env bash
#
# This is one-stop-shop for checking everything there is to check in the project.

# http://redsymbol.net/articles/unofficial-bash-strict-mode/ AKA "don't ignore errors"
set -euo pipefail


echo Verifying types...
mypy src/spreadsheet_offset_tool

echo
echo Linting...
ruff check

echo
echo Verifying formatting...
ruff format --check

echo
echo "SUCCESS"
