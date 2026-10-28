# Reading what code could not (Step 4)

`<isaac> bundle list <bundle> unread --limit 50 --offset 0` — each entry has a path, a reason code and
`source_type`. Work through them in this order, and tell the scientist which you are on.

1. **Logbooks, beamtime notes, proposals, spreadsheets that look like a sample list** (docx, xlsx,
   pdf, txt with prose). These hold sample names, conditions and who did what.
2. **Slides and reports** (pptx, pdf): figures and captions often state conditions.
3. **Images** (png/jpg/tif): open with Read; describe only what is visible; a plot is not a value.
4. Everything else last. Instrument binaries you cannot open are reported, not guessed.

## Tools

- Word/PowerPoint/Excel: `<python> -m isaac_api.local_import.extract <file> --root <folder> --out <bundle>/extracted`
  (or `--from-bundle <bundle>/unread_files.json --root <folder> --limit 20` for a batch). It prints a JSON
  manifest: text in reading order, tables as rows, every embedded image written to disk with its
  position, alt text and caption, bounded previews for sheets (the bound is stated), and counters for
  anything cut. Read the text file it names; open images with Read.
- PDFs: Read with a page range of at most 20 pages (`pages: "1-20"`). The manifest lists ranges.
- Plain text: Read directly (use offset/limit for long files).
- Never run or open a file with any other program. Macros and scripts are only ever read as text.

## Recording what you found

For each fact that bears on a record, `annotate` it: `--target <candidate or missing-value id>`,
`--value`, `--source-id`, `--excerpt-locator` (file, page/slide/sheet/line), `--model`,
`--rationale` with the quote. If no id fits, tell the scientist in words and add it as a note to
their answer in Step 7. Never present your reading as confirmed.
