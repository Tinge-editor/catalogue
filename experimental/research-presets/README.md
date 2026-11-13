# Experimental research looks

`catalogue.json` is an **experimental** v1 manifest of 25 looks for evaluation in Tinge (Manage Looks → Discover Looks → ⋯ → Connect Catalogue URL). It uses its own catalogue ID, `tinge-research`, and is separate from the production listing: it doesn't change `catalogue/source.json` or the production `catalogue.json`, and its look IDs don't collide with production IDs.

When this file is present, `tools/build.py` checks it (header, catalogue identity, ID collisions, 8 MB limit), copies it unchanged to `research-catalogue.json` in the site output and runs the catalogue validator on it. After deployment it is available at:

```
https://tinge-editor.github.io/catalogue/research-catalogue.json
```

The looks are experimental and not licensed for redistribution. To retire the listing, delete this directory.
