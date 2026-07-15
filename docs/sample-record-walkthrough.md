# Sample record walkthrough

A guided tour of the one committed sample record and its evidence sidecar. It shows, concretely,
which values came from synthetic source metadata, which came from human-confirmed answers, what the
pipeline **refused to guess**, and how the deterministic checks (official validation, evidence
audit) and the non-gating advisory warning read this record.

This page reads the committed files; it does not regenerate them. To *run* the pipeline that
produces them, follow [`demo.md`](demo.md) — this walkthrough deliberately does not duplicate it.
For where each concept lives in the codebase, see
[`project-memory-map.md`](project-memory-map.md).

---

## Where the sample lives

| File | What it is |
|---|---|
| `docs/samples/01JQZ0SYNTHXANESDEMO000000.json` | The official ISAAC v1.05 **record** (validates, audits clean) |
| `docs/samples/01JQZ0SYNTHXANESDEMO000000.evidence.json` | The evidence **sidecar** (official JSON-path → source evidence) |
| `docs/samples/README.md` | States the files are synthetic and how they were produced |

The record id `01JQZ0SYNTHXANESDEMO000000` is fixed so the demo can regenerate the record
byte-for-byte (see [`demo.md`](demo.md) step [5]).

## What the sample represents

A **deliberately synthetic** XANES / HERFD-XAS characterization session. It is unmistakably not
real data, on purpose:

- The `timestamps` are dated to **year 2099** (`acquired_start_utc: "2099-03-01T18:30:00Z"`,
  `created_utc: "2099-03-05T20:15:00Z"`) — a fake beamline session.
- The proposal / session ids are `SYN-2099-000` / `2099_run_000`.
- The contributors are fictional (`Ada Lovelace`, `Grace Hopper`).
- The asset `sha256`s are obviously patterned stand-ins (`a3b0…`, `b3b0…`, `c3b0…`).

No real SLAC/SSRL data was read, committed, or shown to any model. The source fixtures are under
`tests/fixtures/synthetic/` (see that directory's `README.md`).

## What the record contains (high level)

| Block | Contents |
|---|---|
| top-level | `isaac_record_version: 1.05`, `record_type: evidence`, `record_domain: characterization`, `source_type: facility` |
| `system` | facility SSRL / org SLAC / beamline `15-2` / endstation `XES`; `technique: HERFD-XAS`; configuration (Si(311) mono, Von_Hamos spectrometer, Pilatus_100K detector, 6 scans) |
| `timestamps` | acquired start/end + created (all year-2099) |
| `sample` | material `Copper(II) Oxide` (`CuO2`), `pellet`, composition (mass fractions), 7.0 mm pellet |
| `context` | `ex_situ`, 298 K, `air` |
| `measurement` | one series `averaged_spectrum` — `incident_energy` (eV) vs. `absorption` (normalized) + `i0_monitor`; `qc.status: valid` |
| `assets` | 3 assets — processing notebook, reduced spectrum, raw scan set — each with `uri`, `media_type`, `sha256` |
| `descriptors` | one output descriptor `xanes_inflection_point_energy = 9001.2 eV` (σ 0.01) |
| `attribution` | two fictional contributors |

## Values from synthetic source metadata

Most fields trace to the synthetic campaign sheet `mock_campaign.csv`. In the sidecar these carry
`source_type: "spreadsheet"` with the exact sheet/field locator and the quoted source value.
Concrete examples (sidecar key → evidence):

| Record field (sidecar JSON-path key) | Evidence (from the sidecar) |
|---|---|
| `system.facility.facility_name` | `spreadsheet` · `mock_campaign.csv` · `Sheet 'Campaign Info', field=facility_name` · quote `"SSRL"` |
| `sample.material.formula` | `spreadsheet` · `mock_campaign.csv` · `Sheet 'Sample', field=formula` · quote `"CuO2"` |
| `system.configuration.n_scans` | `spreadsheet` · `mock_campaign.csv` · `Sheet 'Configurations', field=n_scans` · quote `"6"` |
| `context.temperature_K` | `spreadsheet` · `mock_campaign.csv` · `Sheet 'Configurations', field=temperature_K` · quote `"298"` |

A small number of fields are **derived by a documented rule**, not read from a cell — these carry
`source_type: "derivation"`, and the rule text is recorded so the inference is auditable, not
guessed:

- `system.domain` → `"experimental"`, rule: a facility-source record is a physical experiment, not
  a computation.
- `implicit:absorbing_element` → `"Cu"`, rule: the sole non-oxygen element in
  `sample.material.formula` (`CuO2` → `Cu`).

## Values from human-confirmed completion answers

The values the extractor could **not** get from the sheet or listing were supplied by the simulated
human answers in `tests/fixtures/synthetic/xanes_completion_answers.json` and recorded in the
sidecar as `source_type: "user_confirmation"` (with the question, answer, and timestamp). These
stand in for what a person types into `/isaac-complete`. Concrete examples, cross-checked between
the answers fixture and the sidecar:

| Answer (from `xanes_completion_answers.json`) | Record field / sidecar key | Sidecar evidence |
|---|---|---|
| `descriptor.value = 9001.2` (eV, σ 0.01) | `descriptors.outputs[…].xanes_inflection_point_energy` (`descriptors:xanes_inflection_point_energy`) | `user_confirmation` · answer `"9001.2"` |
| `asset_sha256[".../reduced/CuO2_merged.xdi"] = b3b0…b234` | `assets[…].sha256` (`assets:reduced_spectrum`) | `user_confirmation` · answer `"b3b0…b234"` (paired with a `file_listing` line for the URI) |
| `edge = "K"` | absorption edge (`implicit:edge`) | `user_confirmation` · answer `"K"` (plus a `derivation` note that edge needs scientific confirmation) |

The reduced spectrum itself (`measurement.series`) also comes from the answers fixture — the
extractor knows a spectrum is required but will not fabricate one. Each asset's `sha256` is a
separate confirmation: the URI is extracted from the file listing, but the hash is only ever
supplied by a human.

## What was refused / blocked before completion

Before any answers were applied, the deterministic draft builder surfaced exactly **five
`pending[]` blockers** — things it knew it needed and **refused to invent** (verbatim from the demo
driver / [`demo.md`](demo.md)):

1. `pending[asset]` — sha256 of `…/notebooks/xanes_reduction_v2.ipynb`
2. `pending[asset]` — sha256 of `…/reduced/CuO2_merged.xdi`
3. `pending[asset]` — sha256 of `…/raw/`
4. `pending[series]` — provide/point to the reduced spectrum so `measurement.series` can be built
5. `pending[descriptor]` — provide at least one descriptor (an `evidence` record requires descriptors)

The absorption `edge` was handled separately as a null `implicit[]` candidate (recorded, not
guessed) and was likewise answered by the human — its sidecar entry keeps both the derivation note
and the `user_confirmation`. This "refuse, then ask" moment is the point of the whole pipeline:
nothing scientific is filled in without evidence or a human answer.

## Why the evidence sidecar is separate from the record

The official ISAAC schema is `additionalProperties: false` throughout — there is **no slot for
per-field provenance** inside the record. So the record stays 100% schema-clean, and the evidence
lives alongside it in `…​.evidence.json`, keyed by official JSON-path (plus the namespaced
`assets:` / `descriptors:` / `implicit:` prefixes for the structured blocks, and — since Phase 21 —
`series:` / `qc:status` / `attribution:` prefixes for the block-level scientific claims, see below).
This is how auditability survives export without bending the standard. The sidecar is an assistant
audit artifact unless mentors adopt it as an official convention (decision D1 in
[`mentor-decisions.md`](mentor-decisions.md)). It is **not** an ISAAC record — do not validate it
with `--official`.

## Block-level evidence (series, QC, attribution)

Beyond the dotted scalar fields, four more sidecar keys carry evidence for **block-shaped** claims
that no single dotted path can express — a spectrum, a QC verdict, and each contributor:

| Sidecar key | What it evidences | Evidence in this sample |
|---|---|---|
| `series:averaged_spectrum` | `measurement.series[0]` — the reduced spectrum itself | `user_confirmation` — answer names the `.xdi` reduction it came from |
| `qc:status` | `measurement.qc.status` — the QC verdict | `spreadsheet` · `mock_campaign.csv` · `Sheet 'Configurations', field=qc_status` · quote `"valid"` |
| `attribution:Ada Lovelace\|curated_record` | first contributor in `attribution.contributors` | `spreadsheet` · `mock_campaign.csv` · `Sheet 'Campaign Info', field=lead_experimenter` |
| `attribution:Grace Hopper\|curated_record` | second contributor | `spreadsheet` · `mock_campaign.csv` · `Sheet 'Campaign Info', field=co_experimenter` |

Before Phase 21, none of these four were tracked: a spectrum, a QC verdict, and every contributor
could reach an exported record with zero evidence, and the audit had no way to notice. They are now
first-class **evidence targets** — the audit denominator below counts them, and export refuses if
any of them is uncovered (see `docs/superpowers/plans/2026-07-15-phase-21-close-truth-gap.md`).

## What official schema validation checks

```bash
.venv/bin/isaac validate docs/samples/01JQZ0SYNTHXANESDEMO000000.json --official
# PASS — valid against official ISAAC schema v1.05
```

`validate_official` (`src/isaac_records/official.py`) checks the record against the vendored v1.05
schema: **structure** (no unknown blocks — `additionalProperties: false`), **required fields**
(including conditional `if/then` rules such as `record_type=evidence ⇒ descriptors`), and
**vocabulary** (inline enums, anti-pattern descriptor names). Because the schema is closed, this
covers every hard (HTTP-400) rule the official portal enforces.

It does **not** check **scientific plausibility**. Schema validation is about shape and vocabulary,
not chemistry or physics — it does not verify, for example, that `sample.material.name` and
`sample.material.formula` are mutually consistent, or that a descriptor value is reasonable. Those
are questions for a human reviewer (validation stage 5), not the schema. The committed sample
demonstrates this deliberately: its material name `Copper(II) Oxide` is paired with the formula
`CuO2` (real copper(II) oxide is `CuO`) — a chemically inconsistent, unmistakably synthetic
combination that schema validation accepts, because chemical plausibility is outside its scope.

## What evidence audit checks

```bash
.venv/bin/isaac audit --records-dir docs/samples
# PASS  01JQZ0SYNTHXANESDEMO000000.json  (0 schema errors, evidence 33/33)
#
# 1 records audited, 0 failing official validation
```

`audit_records` (`src/isaac_records/audit.py`) does two things per record: (1) re-run official
schema validation, and (2) report **sidecar coverage**. Since Phase 21, coverage is an **honest,
record-derived** count: the denominator is enumerated from the record's own content, not from
whatever the sidecar happens to contain. It is **33 targets total** — **25 scalar** leaves (dotted
JSON-paths such as `system.facility.facility_name`, reached by walking the record and skipping
system-stamped/identity fields) **+ 8 block** targets (one each for `measurement.series[0]`,
`measurement.qc`, the 3 `assets[]`, the 1 descriptor, and the 2 `attribution.contributors[]`).
`evidence 33/33` means every one of those 33 targets has a sidecar entry — including the spectrum,
the QC verdict, and both contributors, which the pre-Phase-21 model never checked at all (see
[Block-level evidence](#block-level-evidence-series-qc-attribution) above). Coverage is **completeness
reporting, not a pass/fail verdict** — a record can be officially valid with lower coverage, and a
low-coverage record is not "invalid," just less audited. `implicit:` keys stay informational and are
never counted, expected, or dangling. The audit proves the record is schema-valid **and** its
evidence trail is intact against its own content; it does not judge the science.

A sidecar frozen from before Phase 21 (the legacy fixture at `tests/fixtures/legacy/`) audits the
same record honestly lower — `evidence 29/33`, uncovered: `series:averaged_spectrum`, `qc:status`,
and both `attribution:` keys — because those four block claims had no sidecar representation yet.
That is the intended behavior: an old sidecar is read without error, just scored against today's
fuller definition of "covered."

## What the advisory warning layer flags

```bash
.venv/bin/isaac validate docs/samples/01JQZ0SYNTHXANESDEMO000000.json --official --warnings
# PASS — valid against official ISAAC schema v1.05
#
# Advisory portal warnings (LOCAL seam — do NOT affect official validity or export):
#   ⚠ [NO_LINKS] links — record declares no relationships to other records (optional `links` block absent).
# (1 advisory warning(s) — non-gating)
```

This sample triggers **exactly one** advisory warning: `NO_LINKS`, because it declares no optional
`links` block relating it to other records. It is **non-gating** — the exit code stays `0` and the
record remains officially valid and audit-clean. The other implemented check
(`QC_NONVALID_WITHOUT_EVIDENCE`) does not fire, because `measurement.qc.status` is `valid`. This is
a **local heuristic seam, not** upstream portal parity — see [`portal-warnings.md`](portal-warnings.md).

## What Graphify can and cannot tell you about this sample

Graphify (the optional memory/query layer) is useful for **locating the code and docs that produced
each artifact** — for example, leads toward `export.py` (`build_sidecar`) for the sidecar,
`extract/draft_builder.py` for the `pending[]` blockers, `complete.py` for how answers became
`user_confirmation` evidence, and this walkthrough / [`demo.md`](demo.md) for the narrative. It
returns nodes with `src=<file> loc=L<line>` pointers you then open and confirm.

Graphify **cannot prove** anything about this record that decides truth: it does not establish that
the record is valid, that evidence coverage is complete, or that any value is correct. For those,
run the deterministic checks above (`isaac validate --official`, `isaac audit`) and read the sidecar
and schema. Graphify gives leads; the deterministic sources give truth. See
[`graphify-workflow.md`](graphify-workflow.md) and [`query-cookbook.md`](query-cookbook.md).

---

*Reproduce the artifacts this page describes:* [`demo.md`](demo.md). *Where everything lives:*
[`project-memory-map.md`](project-memory-map.md).
