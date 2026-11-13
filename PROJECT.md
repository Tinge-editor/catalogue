# Catalogue contract

Tinge provides a free, public static preset catalogue. Client photo processing, preset installation and full-resolution export remain local. No account or photo upload is required to use installed looks.

The v1 manifest has `formatVersion`, `catalogID`, `title`, `isDemo`, and `looks`. The compatibility field `isDemo` is always `false` for published catalogues. A look has `id`, `version`, `name`, `description`, `author`, `license`, `categories`, `sha256`, and `package`; the last field is base64 of one native Tinge JSON preset array. The checksum covers those exact bytes. The catalogue client validates the whole manifest before replacing its last good local snapshot. Installed presets are independent of later listing changes.

Only approved free assets belong in this public repository. Preserve versioned files and hashes, and treat Git history and pull requests as public. Run the portable checks and the independent iOS compatibility validation described in the README before publication. Do not claim the portable checker is equivalent to the private iOS validator.
