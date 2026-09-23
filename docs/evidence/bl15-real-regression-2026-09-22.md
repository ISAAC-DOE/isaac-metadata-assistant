# BL15-2 real-corpus regression — 2026-09-22 (aggregate counts only)

**What this is.** A local run of the 2026-09-22 Historical Import pipeline (branch
`feat/historical-import-ui` @ `01b513ff`) over the owner-supplied private BL15-2 archive, to
check the new semantics against real data. **Only structural counts and concept names are
recorded here** — no value, note prose, filename token beyond what `docs/evidence/bl15-2-corpus-characterization-2026-09-16.md`
§0 already permits, or person. The archive was copied to the session scratchpad (outside the
repository), read by a throwaway local backend on port 8201 with
`ISAAC_HISTORICAL_FILE_INGESTION=staging_directory` + `ISAAC_HISTORICAL_STAGING_ROOT` (a
configuration no deploy artifact sets — `EXT-13` is unchanged), and nothing was sent to any
external service or model provider. Workspace and staging copy are ephemeral scratch.

| Check | Result |
|---|---|
| Staged archive offered / attached / parsed / reconstructed | 1 / 200 / 200 / 200 (HTTP) |
| Measurement units / sample groups / unattached sources | 94 / 10 / 15 |
| Candidates | **200**: 74 sources agree · 51 single source · **44 varies** · **31 sources conflict** |
| Field conflicts by concept | acquisition_timestamp 9 · sample_position 9 · spec_user_string 7 · filter 2 · legacy_run_or_file_number 2 · cycling_state 2 |
| "Varies" (per-scan / per-item / per-file — not conflicts) | detector_column 9 · motor_position 9 · emission_energy 8 · acquisition_target 7 · unknown_token 4 · scan_command 3 · counting_time 2 · energy_grid 2 |
| Structural conflicts | duplicate_legacy_number 1 · macro_declared_never_acquired 9 |
| Convention applicability | 1,192 sources under `ssrl_bl152_herfd_echem_naming` v1 · 0 ambiguous · `selected_by_operator: false` |
| HERFD primary-signal selector | 90 proposed (suggestions) · 4 unresolved · `writes_a_record_field: false` |
| Temperature | `status: not_recorded` · `automatic_proposal: false` · `automatic_value: null` · no nominal rule enabled |
| Data Quality Notes | 17 bound to a measurement · 6 unbound · `writes_qc_status: false` |
| Python-repr / `[object Object]` in the session payload | 0 / 0 |
| Add to Experiment (new record, `create_runs: true`) | 90 Runs created · 90 proposals (all `timestamps.acquired_start_utc`) · **0 nominal offers** · 0 temperature values written · 90 run origins recorded |
| Re-add the same import | 0 Runs created · 90 matched by acquisition identity · **0 duplicate proposals** |
| Legacy number 32 | carried by **2 distinct Runs** (both acquisitions preserved); no other legacy number is shared |

**Open, for the domain owner:** whether the 9 `acquisition_timestamp` and 9 `sample_position`
conflicts are genuine source disagreements or legitimate scan-to-scan variation. The pipeline
surfaces them as conflicts (conservative: preserve every reading, choose nothing); promoting
either concept to a per-scan cardinality is a scientific decision, not an engineering one.
