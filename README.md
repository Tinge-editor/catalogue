# Tinge public preset catalogue

This repository contains only approved, free Tinge presets intended for public distribution. Each package is a native Tinge JSON recipe. It currently contains eight original built-in looks. `catalogue/source.json` describes their versions, attribution and SHA-256 hashes; `catalogue/presets/` contains the package bytes. The source tree, Git history, pull requests and workflow logs are public when this repository is public. Never place drafts, paid or unreleased looks, private rights evidence, personal data or credentials here—even temporarily. A build filter cannot make committed content private.

## Validate and build

Python 3.9+ is required:

```sh
tools/validate.sh
```

The command runs tests and builds a site in a temporary directory. To retain output, choose a **new** directory:

```sh
TINGE_SITE_OUTPUT=/tmp/tinge-site tools/validate.sh
```

The build publishes the [preset licence and photo permission](https://tinge-editor.github.io/catalogue/preset-license.txt) (CC BY 4.0, covering the production looks and the experimental research looks, which carry the same author and licence text on their listing rows), the [privacy policy](https://tinge-editor.github.io/catalogue/privacy.html), and the [support page](https://tinge-editor.github.io/catalogue/support.html) from explicitly selected files in `public/`. Review the policy against the app release and current data practices before publishing.

The generated `catalogue.json` uses Tinge's v1 manifest format, or format 2 when a look sets the optional `collection` or `samplePath`/`sampleCredit` source fields (a JPEG of at most 300 KB, long edge 64–1600 px) and embeds each package. Approved packages are also available under `assets/<id>/<version>/<sha256>.json`. The current app uses the embedded bytes. `tools/verify_manifest.py` performs portable structural and integrity checks, including basic package versions and LUT structure. **It does not implement the full iOS preset validator and cannot alone prove compatibility.**

Before approving a release, independently validate the generated manifest against a reviewed iOS app checkout on macOS with Xcode command-line tools:

```sh
tools/verify_with_ios.sh /path/to/tinge-ios REVIEWED_IOS_COMMIT /tmp/tinge-site/catalogue.json
```

This compiles validator files from the specified reviewed Git commit into a temporary directory, without modifying the app checkout or publishing its source. Use a stable app commit and update it when coordinating an iOS contract change. Public CI cannot access the private app source and therefore runs only the portable checks. Use a required human review and protect the deployment environment until independent iOS validation has passed.

## Publish an approved look

Keep authoring, review, private submissions and rights evidence outside this repository. Only after approval, add a native JSON array containing exactly one free, public preset under `catalogue/presets/` and add its metadata and SHA-256 to `catalogue/source.json`. Source metadata is public; do not include confidential permission records. All source entries must be approved and free. Record an accurate public rights statement without implying a broader licence than the owner granted. A checksum verifies bytes, not authorship or rights.

The owner authorised a one-time replacement of the initial catalogue when applying the preset licence; only the exact previous and replacement snapshots are permitted by that exception. Update the version when a recipe or its metadata changes; never overwrite or delete an already published version or package. Set an older version's `listed` to `false` and retain it when listing an update. The validator compares previous source records in pull requests and main pushes, but branch protections and human review are essential. To roll back, switch the `listed` flags in a new commit while retaining all historical packages. To rename a look, publish it under a new ID and set every version of the old ID to `listed: false`; retired IDs stay in the source, are never reused, and can't be used by the experimental catalogue. Do not redeploy an old checkout, which could remove later asset URLs. Legal takedowns require a separate deliberate process; public copies cannot be recalled.

For LUT-based presets, source metadata must explicitly confirm sRGB input and output. Tinge can support other encodings, but this catalogue currently restricts publishing to confirmed sRGB. Do not assume a `.cube` identifies its colour encoding. The private iOS validator is required to verify full preset compatibility.

## GitHub Pages

The workflow runs on pull requests and on pushes to `main`; it deploys only when the repository variable `PAGES_PUBLICATION_ENABLED` is `true`. Configure Settings → Pages → GitHub Actions and protect the `github-pages` environment, require the CI check and review of every release, and disallow force pushes after initial setup. The workflow publishes the generated site, not the repository tree.

The production manifest URL is `https://tinge-editor.github.io/catalogue/catalogue.json`; verify public access after each release. Its path remains stable across catalogue changes when Pages hosts this repository at the expected project-site path. The mutable manifest must not be treated as permanently cached. GitHub Pages controls response headers; check actual behaviour rather than assuming custom cache settings. Versioned package URLs contain a content hash and must never be reused for different bytes.

Distribution rights are described in [NOTICE.md](NOTICE.md).
