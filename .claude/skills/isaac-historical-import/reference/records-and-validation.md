# Build, validate, export (Steps 8–9)

`build-records` writes one draft per confirmed group (`drafts/`), listing every required value nobody
supplied. `validate` runs, per draft: the draft checks, an export dry run, the official schema and
exactness checks, and the offline portal check. Read `validation/<group id>.json` for the details.

## Record shape guidance

When a scientist asks "what should this record hold?", answer from the upstream record contract, not from memory: `~/.cache/isaac/portal-validator/<sha>/src/data/record_contract.json` (the pinned clone; `definition`, `kinds`, `procedure`, `never_a_record`) and the wiki page "What an ISAAC record is". One record is one result: one sample, one measurement, one set of conditions, the values that measurement produced, and the one work they come from.

## Verdicts, in plain words, and the fix

| Verdict | Tell the scientist | Fix |
|---|---|---|
| `incomplete` | "These required facts are still missing: …" (list them from the draft) | answer the blocking questions (Step 7: `bundle questions --blocking-only`), or approve the processing result and state its QC status (Step 6) |
| `invalid_official` | "A value is in the wrong form: …" (quote the validator's message) | correct that value with `decide --decision correct` |
| `portal_check_unavailable` | "The offline portal check is not installed, so this cannot count as ready." | `scripts/install_portal_validator.sh`, then `validate` again |
| `portal_check_degraded` | "The portal check ran only partly, so this cannot count as ready." | re-install the validator; if it persists, report it |
| `portal_hold` | "The portal would hold this record for a warning: …" | explain the warning; ask whether to fix or leave unexported |
| `portal_reject` | "The portal would reject this: …" | fix the stated value or leave it unexported |
| `exportable` | "Passes every check." | export |

`validation/<group>.json` also has a `schema_drift` block (differences between the vendored website schema and the pinned portal schema, such as an unknown temperature). It is information, not a verdict: the verdict it leads to is `invalid_official` or `portal_reject`, with the validator's own message. Quote the message.

Exit 1 from `validate` means at least one draft is not exportable; that is information, not an error.
After fixing, run `build-records` then `validate` again. Never hand-edit a draft or an evidence file.

## Export and upload

`export --out <records>` writes `<ULID>.json` and `<ULID>.evidence.json` for exportable drafts only
and lists the rest with their verdicts. Then `upload <records> --dry-run`: summarise records, target
endpoints and body sizes. State plainly: nothing was sent, this build cannot send, the key was not
read. Never ask for or print a portal key. Tell the scientist the records are in `<records>` and
the portal upload is theirs to do.
