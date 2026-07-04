# examples/

Drop the real project artifacts here (they are gitignored by default — SLAC data governance):

- the Excel metadata sheet (Campaign Info / Configurations / File List / Vocabulary tabs)
- the SSRL web-form screenshots (session details, sample details, conditions)
- the ISAAC narrative PDF
- a raw scan file listing (e.g. `ls -R` output of the campaign folder)

`/isaac-draft` reads from this directory. Extraction evidence will cite these files
by name and locator (sheet/cell, page, screenshot region), so keep filenames stable.
