#!/usr/bin/env bash
#
# A script to fix all fixable issues with the code (linting, formatting)

# http://redsymbol.net/articles/unofficial-bash-strict-mode/ AKA "don't ignore errors"
set -euo pipefail

ruff check --fix
ruff format
