# Validator upload guide

18 files to run through the app's **Standalone Validator**, one at a time.

**Where:** Governance & Safety → **Validator** tab.
**How:** press **Upload JSON File**, pick the file, then press **Validate**. You can also paste the
file's text straight into the *Candidate record (JSON)* box instead of uploading.

The screen accepts JSON up to 512 KB. It checks the record against the official ISAAC schema v1.05
and shows either a green **PASS** or a red **FAIL** with a *Schema Errors* list of paths and messages.
It never saves, changes, or stores anything you put in it.

**About export:** this screen has no export button — it only reports a verdict. The line to watch is
on the verdict card itself: a failing record says **"Export blocked"**, and a passing record says
this is the same gate that backs export. So "export availability" below means what the verdict card
tells you about export, not a button on this screen.

**Two files are expected to pass even though they should not.** Files 5 and 6 are the point of the
exercise, not mistakes in the exercise. Read their rows carefully and record what you see.

**One file chooser note:** the picker is set to JSON files, so file 16 (`.txt`) will not appear in the
default list. On macOS you can still reach it by changing the file-type dropdown in the chooser to
show all files. If that is awkward, open the `.txt` in a text editor and paste its contents into the
box instead — the outcome is the same.

---

## 1. `complete-valid-record.json`

- **What to do:** upload, then Validate. Do this one first.
- **Expected upload outcome:** loads into the box without complaint.
- **Expected validation state:** **PASS** — valid against official ISAAC schema v1.05.
- **Expected visible issue:** none. No *Schema Errors* section appears.
- **Expected export availability:** not blocked — the verdict card states this is the same gate that
  backs export.
- **Repair action:** none needed.
- **Expected result after repair:** n/a.

This is the baseline. If this one fails, stop and report it, because every other file in the package
is this record with one or three deliberate changes.

## 2. `missing-required-information.json`

- **What to do:** upload, then Validate.
- **Expected upload outcome:** loads normally.
- **Expected validation state:** **FAIL**, 1 error.
- **Expected visible issue:** one row at path `$` reading `'source_type' is a required property`.
- **Expected export availability:** **Export blocked.**
- **Repair action:** add the record's origin field back at the top level, e.g. a line
  `"source_type": "facility",` next to `"record_domain"`.
- **Expected result after repair:** PASS.

## 3. `missing-nested-information.json`

- **What to do:** upload, then Validate.
- **Expected upload outcome:** loads normally.
- **Expected validation state:** **FAIL**, 1 error.
- **Expected visible issue:** one row at path `timestamps` reading
  `'created_utc' is a required property`. Note that the error names the block, not the document root —
  the timestamps block is present, it is the field inside it that is missing.
- **Expected export availability:** **Export blocked.**
- **Repair action:** inside the `timestamps` block, add
  `"created_utc": "2026-03-05T09:12:00Z"`.
- **Expected result after repair:** PASS.

## 4. `missing-conditional-information.json`

- **What to do:** upload, then Validate.
- **Expected upload outcome:** loads normally.
- **Expected validation state:** **FAIL**, 1 error.
- **Expected visible issue:** one row at path `$` reading `'descriptors' is a required property`.
- **Expected export availability:** **Export blocked.**
- **Repair action:** this one is worth understanding rather than fixing quickly. `descriptors` is not
  required of every record — it becomes required *because* this record's type is `evidence`. Either
  add a descriptors block back, or change the record type. Changing the type is a change of scientific
  meaning, so the intended repair is to restore the descriptors block.
- **Expected result after repair:** PASS once a complete descriptors block is present. You can copy
  the block from file 1.

This is the rule-dependent case: nothing about the missing field is wrong on its own, only in
combination with another field's value.

## 5. `invalid-date-time.json` — expected to expose a gap

- **What to do:** upload, then Validate.
- **Expected upload outcome:** loads normally.
- **Expected validation state:** **PASS.** That is what will happen, and it is wrong.
- **Expected visible issue:** none shown — and that is the finding. The record's required creation
  timestamp holds the text `not-a-date`, which is not a date at all. The current checks do not test
  the shape of date fields, so nothing is reported.
- **Expected export availability:** not blocked. A record with an unusable timestamp would pass this
  gate today.
- **Repair action:** none — do not "fix" this file. Record the observation: a required timestamp
  containing `not-a-date` was accepted.
- **Expected result after repair:** n/a.

## 6. `empty-measurement-series.json` — expected to expose a gap

- **What to do:** upload, then Validate.
- **Expected upload outcome:** loads normally.
- **Expected validation state:** **PASS.** That is what will happen, and it is wrong.
- **Expected visible issue:** none shown — and that is the finding. The measurement block is present
  and its quality section is intact, but the list of measured series is empty, so the record contains
  no measured points whatsoever. The current checks require the list to exist, not to contain
  anything.
- **Expected export availability:** not blocked. An empty measurement would pass this gate today.
- **Repair action:** none — do not "fix" this file. Record the observation: a record with no
  measurement data was accepted.
- **Expected result after repair:** n/a.

## 7. `missing-evidence.json`

- **What to do:** upload, then Validate.
- **Expected upload outcome:** loads normally.
- **Expected validation state:** **FAIL**, 1 error.
- **Expected visible issue:** one row at path `descriptors.outputs.0.descriptors.0` reading
  `'uncertainty' is a required property`.
- **Expected export availability:** **Export blocked.**
- **Repair action:** the first derived quantity states a value (an edge position of 8979.4 eV) with no
  uncertainty attached. Add an uncertainty block to it, e.g.
  `"uncertainty": { "sigma": 0.2, "unit": "eV", "basis": "assumed" }`.
- **Expected result after repair:** PASS.

Worth knowing while reading the result: the official record format has no place to attach evidence to
an individual field. The nearest thing it does insist on, whenever a derived quantity asserts a value,
is that the value carry an uncertainty — including a note of where that uncertainty came from. That is
the requirement this file breaks.

## 8. `missing-confirmation.json`

- **What to do:** upload, then Validate.
- **Expected upload outcome:** loads normally.
- **Expected validation state:** **FAIL**, 1 error.
- **Expected visible issue:** one row at path `measurement.qc` reading
  `'status' is a required property`.
- **Expected export availability:** **Export blocked.**
- **Repair action:** the quality section carries a written justification but never states the
  conclusion. Add `"status": "valid",` inside the `qc` block. The permitted words are `valid`,
  `compromised`, `failed` and `pending`.
- **Expected result after repair:** PASS.

Worth knowing while reading the result: the official record format has no "confirmation" concept —
that idea belongs to drafting, not to the finished record. The closest thing the finished record
requires is this quality status, which is the record's own affirmation of its state.

## 9. `invalid-controlled-value.json`

- **What to do:** upload, then Validate.
- **Expected upload outcome:** loads normally.
- **Expected validation state:** **FAIL**, 1 error.
- **Expected visible issue:** one row at path `system.technique` reading
  `'XANES' is not one of [...]`, followed by the full list of permitted techniques.
- **Expected export availability:** **Export blocked.**
- **Repair action:** change `"technique": "XANES"` to `"technique": "XAS"`.
- **Expected result after repair:** PASS.

A realistic mistake: XANES is the everyday name for the near-edge region of the measurement, but the
controlled list only admits the parent technique, XAS.

## 10. `invalid-field-type.json`

- **What to do:** upload, then Validate.
- **Expected upload outcome:** loads normally.
- **Expected validation state:** **FAIL**, 1 error.
- **Expected visible issue:** one row at path `context.temperature_K` reading
  `'297.5' is not of type 'number'`.
- **Expected export availability:** **Export blocked.**
- **Repair action:** remove the quotation marks around the temperature so it reads
  `"temperature_K": 297.5`.
- **Expected result after repair:** PASS.

The number is right; only its form is wrong. This is what a spreadsheet export typically produces.

## 11. `unknown-field.json`

- **What to do:** upload, then Validate.
- **Expected upload outcome:** loads normally.
- **Expected validation state:** **FAIL**, 1 error.
- **Expected visible issue:** one row at path `sample.material` reading
  `Additional properties are not allowed ('purity_percent' was unexpected)`.
- **Expected export availability:** **Export blocked.**
- **Repair action:** two honest options. Remove the `"purity_percent": 99.99` line; or, if the number
  matters, move it somewhere the format deliberately leaves open — the material's free-text `notes`,
  or the sample's composition block.
- **Expected result after repair:** PASS.

The material description is a closed list of fields: a plausible, useful extra field is still
rejected. That is deliberate, and it is why new fields have to be requested rather than added.

## 12. `multiple-issues.json`

- **What to do:** upload, then Validate.
- **Expected upload outcome:** loads normally.
- **Expected validation state:** **FAIL**, **3** errors.
- **Expected visible issue:** three rows, one of each kind, listed in path order:
  - `$` — `'record_domain' is a required property`
  - `context.temperature_K` — `'ambient' is not of type 'number'`
  - `system.instrument` — `Additional properties are not allowed ('serial_number' was unexpected)`
- **Expected export availability:** **Export blocked**, and the card should say *3 errors*, not 1.
- **Repair action:** all three: add `"record_domain": "characterization",` at the top level; replace
  `"temperature_K": "ambient"` with a number such as `297.5`; delete the instrument's
  `"serial_number"` line.
- **Expected result after repair:** PASS, but only after all three are fixed. Fixing one or two
  should reduce the count rather than clear it — worth checking one at a time.

The thing to confirm here is that every issue is reported at once. Nothing should stop at the first
problem.

## 13. `unicode-and-escaping.json`

- **What to do:** upload, then Validate.
- **Expected upload outcome:** loads normally, with accented text, Chinese characters, an emoji and
  quotation marks visible in the box.
- **Expected validation state:** **PASS.**
- **Expected visible issue:** none from the validator. What to look at instead is the display: the
  accents, the Chinese characters and the emoji should all render correctly and not turn into boxes,
  question marks or escape codes. Text is deliberately included that contains double quotes,
  backslashes, tabs, line breaks, guillemets, dashes and a check mark.
- **Expected export availability:** not blocked.
- **Repair action:** none needed.
- **Expected result after repair:** n/a.

## 14. `large-valid-record.json`

- **What to do:** upload, then Validate. Expect a brief pause while the file loads into the box.
- **Expected upload outcome:** accepted. The file is 181,163 bytes — about 177 KB — comfortably inside
  the 512 KB limit, so no size warning should appear.
- **Expected validation state:** **PASS.**
- **Expected visible issue:** none from the validator. What to watch is responsiveness: this record
  carries one full spectrum of 2,600 energy points with two recorded channels, 7,800 numbers in all.
  Note anything that feels slow, freezes, or scrolls badly.
- **Expected export availability:** not blocked.
- **Repair action:** none needed.
- **Expected result after repair:** n/a.

## 15. `malformed-json.json`

- **What to do:** upload, then Validate.
- **Expected upload outcome:** the file loads into the box — the screen does not judge it at upload
  time. Pressing **Validate** is what triggers the refusal.
- **Expected validation state:** **not validated at all.** You should see an amber warning reading
  *"That isn't valid JSON — check for a missing bracket, quote, or trailing comma."* You should **not**
  see a green PASS or a red FAIL card, because nothing was checked.
- **Expected visible issue:** the warning above, and no *Schema Errors* section.
- **Expected export availability:** n/a — nothing was validated, so no verdict about export is made.
- **Repair action:** the file stops mid-way through the measurement block, leaving brackets unclosed.
  A hand repair is possible but tedious; the point of this file is the refusal, not the repair.
- **Expected result after repair:** if you did close the structure correctly it would be validated
  like any other record; this file is not intended to be repaired.

The distinction to confirm: "unreadable" and "invalid" are different outcomes and should look
different. A red FAIL card here would be wrong.

## 16. `unsupported-file.txt`

- **What to do:** press **Upload JSON File** and look for this file. It should not be offered in the
  default list, because the chooser is limited to JSON. If you can force it through (change the
  chooser's file-type dropdown to all files), do so and then press **Validate**. Otherwise open it in
  a text editor and paste its contents into the box.
- **Expected upload outcome:** ideally not selectable at all. If forced through, the plain text loads
  into the box.
- **Expected validation state:** **not validated at all** — the same amber
  *"That isn't valid JSON..."* warning as file 15.
- **Expected visible issue:** that warning. No PASS, no FAIL, no *Schema Errors*.
- **Expected export availability:** n/a.
- **Repair action:** none — this is not a record and cannot become one by editing.
- **Expected result after repair:** n/a.

## 17. `duplicate-of-complete-valid-record.json`

- **What to do:** upload, then Validate. Do this straight after file 1 if you can, so the comparison
  is fresh.
- **Expected upload outcome:** loads normally.
- **Expected validation state:** **PASS** — identical to file 1, right down to the same record
  identifier.
- **Expected visible issue:** none. In particular, **no duplicate warning is expected, and its absence
  is not a defect.** This screen holds no collection of records, saves nothing, and compares nothing
  against anything else, so it has nothing to detect a duplicate against. Telling you two identical
  records are identical is only meaningful somewhere that keeps them.
- **Expected export availability:** not blocked.
- **Repair action:** none needed.
- **Expected result after repair:** n/a.

What this file is really for is to confirm that checking the same content twice gives the same answer
and leaves nothing behind. Keep it for the day there is a path that imports and keeps records — that
is where duplicate handling has to be tested.

## 18. `repairable-record.json`

- **What to do:** upload, Validate, read the error, fix it **in the box**, then press **Validate**
  again without re-uploading.
- **Expected upload outcome:** loads normally.
- **Expected validation state:** **FAIL**, 1 error.
- **Expected visible issue:** one row at path `measurement.qc.status` reading
  `'OK' is not one of ['valid', 'compromised', 'failed', 'pending']`.
- **Expected export availability:** **Export blocked.**
- **Repair action:** exactly one edit. In the box, find `"status": "OK"` inside the measurement
  quality block and change `OK` to `valid`, so it reads `"status": "valid"`. Change nothing else.
- **Expected result after repair:** press **Validate** again → **PASS**, and the *Schema Errors*
  section disappears.

This is the round trip: read the path, make the edit, re-check, go green. If the second Validate does
not clear the error section, that is the finding.

---

## Quick reference

| # | File | Expected outcome |
|---|---|---|
| 1 | `complete-valid-record.json` | PASS |
| 2 | `missing-required-information.json` | FAIL — 1 error |
| 3 | `missing-nested-information.json` | FAIL — 1 error |
| 4 | `missing-conditional-information.json` | FAIL — 1 error |
| 5 | `invalid-date-time.json` | PASS — **and that is the finding** |
| 6 | `empty-measurement-series.json` | PASS — **and that is the finding** |
| 7 | `missing-evidence.json` | FAIL — 1 error |
| 8 | `missing-confirmation.json` | FAIL — 1 error |
| 9 | `invalid-controlled-value.json` | FAIL — 1 error |
| 10 | `invalid-field-type.json` | FAIL — 1 error |
| 11 | `unknown-field.json` | FAIL — 1 error |
| 12 | `multiple-issues.json` | FAIL — 3 errors |
| 13 | `unicode-and-escaping.json` | PASS |
| 14 | `large-valid-record.json` | PASS |
| 15 | `malformed-json.json` | refused as unreadable — no verdict card |
| 16 | `unsupported-file.txt` | not offered by the chooser; refused as unreadable if forced |
| 17 | `duplicate-of-complete-valid-record.json` | PASS, no duplicate warning |
| 18 | `repairable-record.json` | FAIL — 1 error, then PASS after one edit |

---

## What is in these files

Every field name in them comes from the official ISAAC schema. Every value was written by hand for
this exercise. Nothing was copied from, or derived from, any stored record collection.

The measurements they describe are illustrative and are labelled as such inside the records
themselves. They are physically reasonable for a copper K-edge measurement — the absorption edge sits
near 8979 eV — but they are not a measurement of anything, and must not be quoted as one.
