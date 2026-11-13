# Experimental research looks

`catalogue.json` is an **experimental** format-2 manifest of 16 engine-11 looks (version 0.2.1) for evaluation in Tinge (Manage Looks → Discover Looks → ⋯ → Connect Catalogue URL). The looks use look dials (`macros`) instead of separate Soft/Bold/Warm/Cool listings, and are grouped into collections: Portrait film, Everyday film, Slide and landscape, Cinema, Black and white, and Faded and instant. They need a Tinge build that reads engine 11 and catalogue format 2.

It uses its own catalogue ID, `tinge-research`, and is separate from the production listing: it doesn't change `catalogue/source.json` or the production `catalogue.json`, and its look IDs don't collide with production IDs.

When this file is present, `tools/build.py` checks it (header, catalogue identity, ID collisions, 8 MB limit), copies it unchanged to `research-catalogue.json` in the site output and runs the catalogue validator on it. After deployment it is available at:

```
https://tinge-editor.github.io/catalogue/research-catalogue.json
```

The looks are experimental, but they carry the same licence as the production catalogue: each listing row has author `Tinge` and the production CC BY 4.0 text, and the [preset licensing notice](../../public/preset-license.txt) covers them. Anyone may use them; sharing a look or an adaptation (a fork, a recipe export or a `.cube`) must credit Tinge and indicate changes, and photos edited with them may be shared without attribution. As in production, the rights are on the listing row and the packages carry none. The research listing is not versioned like production: a new build replaces it, and looks folded into another look's dials (for example the old Soft and Rich variants) are no longer listed. To retire the listing, delete this directory.
