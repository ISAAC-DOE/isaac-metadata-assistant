# ISAAC import summary: SYN_BL00_2100-31_Upgrade

> **This is not a validated official ISAAC record.** It is what the deterministic
> readers extracted from your files, with the evidence for each value. Nothing
> here is confirmed by a scientist, and nothing has been checked against the
> official ISAAC schema.

Bundle `01M82NNP032XKDKZ757BTBMN9C` · 2026-11-22T22:22:49Z · isaac.local-import-bundle 1.14.0 · folder

## Counts

- Files: 9 inventoried, 0 unread or refused
- Runs: 4 (0 share a legacy number with another run; all are kept)
- 1 processed file whose scan title states an average of several spectra, beside the SPEC acquisitions (the scientists' averages, e.g. .mca files), kept as rough reference results, not records (0 with a proposed link to a run by legacy number, 1 unlinked). Not counted as runs; no question is asked about them.
- Values: 42 — 2 extracted, 14 need review, 4 conflicting, 22 unmapped (kept as evidence)
- Conflicts: 4 · Missing values: 98 (nothing defaulted) · Questions: 43
- People named in the sources: 0 (evidence, not the naming profile)
- This summary shows no parser value except in conflicts, so a blind cross-check (`isaac bundle crosscheck-plan`) is still possible after reading it.

## Run groups

- not in a file-name group: 3 runs (run-001, run-002, run-003); 0 distinct sample-name reading(s)

## Runs

| Run | Legacy | Scans | Conflicts | Flag |
|---|---|---|---|---|
| run-001 | — | 1 | 2 |  |
| run-002 | — | 1 | 2 |  |
| run-003 | — | 0 | 0 |  |
| run-004 | — | 1 | 0 |  |

## Needs review

- conf-001 (run-001): field_disagreement — 4 readings kept
- conf-002 (run-001): field_disagreement — 2 readings kept
- conf-003 (run-002): field_disagreement — 4 readings kept
- conf-004 (run-002): field_disagreement — 2 readings kept
- `context.electrochemistry.potential_setpoint_V`: 3 value(s) need review
- `measurement.series[].channels[].name`: 3 value(s) need review
- `measurement.series[].independent_variables[].values`: 2 value(s) need review
- `assets[].uri`: 1 value(s) need review
- `links[].rel`: 1 value(s) need review
- `timestamps.acquired_start_utc`: 1 value(s) need review

## Unread files

Every inventoried file had a reader.

## Readiness

Stage: extracted. Values eligible for an official record: 0 (only scientist-confirmed values can be). Official record ready: no.

Review the conflicts and the values that need review with the scientist who ran the beamtime, and look at the unread files. No value here is confirmed, and none is eligible for an official record until a scientist confirms it.
