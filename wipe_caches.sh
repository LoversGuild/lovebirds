#!/bin/bash

# A simple script to delete all cache files from the build directory

DIR="$(dirname "$(realpath "${0}")")"

# Python bytecode
find "${DIR}" -name '__pycache__' -type d -prune -exec rm -rf {} +

# .pyc / .pyo (just in case)
find "${DIR}" -name '*.py[co]' -delete

# mypy cache
rm -rf "${DIR}"/.mypy_cache

# No pytest caches at the moment
# rm -rf "${DIR}"/.pytest_cache

# build artifacts
rm -rf "${DIR}"/build "${DIR}"/dist
