# The question page as a claude.ai artifact

`index.html` is one page that runs inside claude.ai. A scientist answers a beamtime's open questions a few at a
time. The page keeps its data in the artifact's shared store: `cards/<card_id>`, `meta/site`, `answers/<card_id>`
and `log/<auto>`. `seed.py` converts between the exported site and those documents. The card and answer formats
are in [`docs/question-site-contract.md`](../../../docs/question-site-contract.md).

The documents hold real beamtime details. Write them outside any git working tree.

## Operator steps

1. Export the questions: `isaac bundle site export <bundle_dir> --out <dir>`. This writes
   `<dir>/data/site-data.json` and the curve images.
2. Make the documents: `python3 seed.py cards <dir>/data/site-data.json <out_dir>`. It writes `meta/site.json` and
   one file per card, and prints the exact list of image files to upload.
3. Upload those image files as artifact assets. Each upload gives a URL.
4. Put the URLs in a small json file that maps the image path to its URL, for example
   `{"img/<sha>.png": "https://…"}`. Rerun step 2 with `--image-urls urls.json`. An image without a URL is left out
   of its card, never shown broken. A card document cannot hold an image itself (256 KiB limit).
5. Write the documents to the store in one batch: `meta/site` from `meta/site.json`, and `cards/<card_id>` from each
   file in `cards/`.
6. Give the artifact to the scientist. Answers save as they are given.
7. Later, read the store's `answers` and `log` collections into a folder, then run
   `python3 seed.py answers <dir>/data/site-data.json <read_dir> answers.json`.
8. Preview what the answers would record: `isaac bundle site import <bundle_dir> answers.json --site-data
   <dir>/data/site-data.json`. Read it, then add `--apply`.

An answer with a note on a card that covers several measurements is held by the import until someone has read the
note. The page tells the scientist so.
