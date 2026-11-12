#!/bin/bash
# Validate a generated manifest against a pinned app commit without modifying or publishing the app.
set -euo pipefail
if [ "$#" -ne 3 ]; then
  echo 'Usage: tools/verify_with_ios.sh IOS_GIT_REPOSITORY IOS_COMMIT GENERATED_CATALOGUE_JSON' >&2
  exit 2
fi
repo="$1"
revision="$2"
manifest="$3"
work="$(mktemp -d "${TMPDIR:-/tmp}/tinge-ios-check.XXXXXXXX")"
trap 'rm -rf "$work"' EXIT
for path in Tinge/Models/Preset.swift Tinge/Models/AdvancedAdjustments.swift Tinge/Models/CubeLUT.swift Tinge/Services/PresetTransfer.swift Tinge/Services/CommunityCatalog.swift tools/ValidateCommunityCatalog.swift; do
  git -C "$repo" show "$revision:$path" > "$work/$(basename "$path")"
done
export CLANG_MODULE_CACHE_PATH="$work/cache" SWIFT_MODULECACHE_PATH="$work/cache"
xcrun swiftc -O -module-cache-path "$work/cache" "$work"/*.swift -o "$work/validate"
"$work/validate" "$manifest"
