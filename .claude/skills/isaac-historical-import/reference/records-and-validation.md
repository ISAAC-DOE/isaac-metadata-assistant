# Build, validate, export (Steps 8–9)

`build-records` writes one draft per confirmed group (`drafts/`), listing every required value nobody
supplied. `validate` runs, per draft: the draft checks, an export dry run, the official schema and
exactness checks, and the offline portal check. Read `validation/<group id>.json` for the details.

## Record shape guidance

When a scientist asks "what should this record hold?", answer from the upstream record contract, not from memory: `~/.cache/isaac/portal-validator/<sha>/src/data/record_contract.json` (the pinned clone; `definition`, `kinds`, `procedure`, `never_a_record`) and the wiki page "What an ISAAC record is". One record is one result: one sample, one measurement, one set of conditions, the values that measurement produced, and the one work they come from.

## Verdicts, in plain words, and the fix

| Verdict | Tell the scientist | Fix |
|---|---|---|
| `incomplete` | "These required facts are still missing: …" (list them from `missing_required`) | answer the blocking questions (Step 7: `bundle questions --blocking-only`). `measurement.series`, `measurement.qc.status` and `descriptors.outputs` are listed as missing until the group's processing result is approved; the file's `processing_fix` says so. The fix is Step 6: show the curve, and approve it only when the scientist does, with the QC status they choose. `processing_fix` holds a template (`--qc-status <value>`): never run it as it is. Correcting a value never supplies them. When it says to re-run `isaac process`, add `--source <folder>` |
| `invalid_official` | "A value is in the wrong form: …" (quote the validator's message) | correct that value with `decide --decision correct` |
| `portal_check_unavailable` | "The offline portal check is not installed, so this cannot count as ready." | `scripts/install_portal_validator.sh`, then `validate` again |
| `portal_check_degraded` | "The portal check ran only partly, so this cannot count as ready." | re-install the validator; if it persists, report it |
| `portal_hold` | "The portal would hold this record for a warning: …" | explain the warning; ask whether to fix or leave unexported |
| `portal_reject` | "The portal would reject this: …" | fix the stated value or leave it unexported |
| `exportable` | "Passes every check." | export |

`validation/<group>.json` also has a `website_schema` result and a `schema_drift` block: how the
record fares against the website's older schema (vendored v1.05, July) beside the pinned portal
schema. Both are for information only and gate nothing; the verdict comes from the portal schema and
the portal check. An unknown temperature is the usual case: the record says `temperature_K: null`
with `temperature_basis: not_reported`, which the portal accepts and v1.05 does not. The drift text
then says so, and that this does not block the local export; `blocked_by_schema_drift: true` is about
the website schema only: the record can still be `exportable`. Tell the scientist so in plain words. The temperature stays an optional question if
they know it; never press for one to clear this note, and never default one.

Exit 1 from `validate` means at least one draft is not exportable; that is information, not an error.
After fixing, run `build-records` then `validate` again. Never hand-edit a draft or an evidence file.

## Export and upload

`export --out <records>` writes `<ULID>.json`, `<ULID>.evidence.json` and a `<ULID>.artifacts/` folder
(the processing files) for exportable drafts only and lists the rest with their verdicts. Its index is
`<records>/isaac-export/index.json`. Exporting again into the same `--out` reuses each unchanged record's id (`export: unchanged`); a changed record gets a new id and the old one is moved to `isaac-export/superseded/` (`export: replaced`); a record whose group is now refused or no longer confirmed is moved to `isaac-export/withdrawn/` (listed under `withdrawn`; if it was uploaded already, the portal still holds it) — say which. Then `upload <records> --dry-run`: summarise records, target
endpoints and body sizes. State plainly: nothing was sent, this build cannot send, the key was not
read. Never ask for or print a portal key. Tell the scientist the records are in `<records>` and
the portal upload is theirs to do.
