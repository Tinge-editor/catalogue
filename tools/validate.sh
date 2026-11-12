#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/tinge-validation.XXXXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
export TINGE_VALIDATOR="$(pwd)/tools/verify_manifest.py"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
site_output="${TINGE_SITE_OUTPUT:-$build_dir/site}"
python3 tools/build.py catalogue/source.json "$site_output" --validator "$TINGE_VALIDATOR" "$@"
