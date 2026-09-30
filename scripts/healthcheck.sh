#!/bin/sh
set -eu
curl -fsS "http://127.0.0.1:${PORT:-8080}/health"
