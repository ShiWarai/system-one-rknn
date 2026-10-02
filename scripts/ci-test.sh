#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
ruff check app tests
python -m unittest discover -s tests -v
