# Portal-style advisory warnings (soft-warning seam)

**Status:** implemented as a **local advisory seam** in Phase 8 — **not** official portal parity.
**Rule that never bends:** the official ISAAC schema is the **hard gate**; these warnings are
**advisory and non-gating** — they never change what counts as valid and never block export.

---

## 1. Two tiers, one hard gate

The official ISAAC portal validates records in two tiers:

1. **Hard rules (HTTP-400).** Unknown blocks, bad vocabulary, anti-pattern descriptor names,
   conditional required fields. In this repo these are **fully covered** by JSON-Schema validation
   against the vendored official schema (`schema/isaac_record_v1.json`, v1.05) in
   `src/isaac_records/official.py`. **This is the authority. It gates export.**
2. **Soft warnings.** A separate advisory tier the upstream portal ships in `portal/validation.py`
   (codes like `NO_LINKS`, `MISSING_PH`, `GALVANOSTATIC_NO_POTENTIAL`, `FE_SUM_EXCEEDS_UNITY`).
   These do **not** reject a record — they flag things a human may want to look at.

Phase 8 adds a **local stand-in for tier 2**: `src/isaac_records/portal_warnings.py`. It is a small,
clearly-labelled advisory seam — **not** a reproduction of the upstream validator.

```
1. Draft no-guessing validation   (draft_validator.py)   — gates authoring
2. Official ISAAC schema           (official.py, v1.05)   — gates export        ← HARD GATE (truth)
3. Portal-style advisory warnings  (portal_warnings.py)   — ADVISORY, non-gating ← this doc
4. AI scientific consistency review (review.py)           — advisory placeholder
5. Human review of anything flagged                       — the decider
```

## 2. What it does

`portal_warnings(record) -> PortalWarningReport` runs a small set of read-only checks over a record
and returns **structured warnings**. It:

- **never mutates** the record;
- **never decides validity** — the report has no `.ok` / `.valid` / `.passed` / `.errors`;
- **never blocks export** — nothing in the export/validation/audit path imports it (enforced by
  `test_truth_path_does_not_import_portal_warnings`);
- **never uses Graphify.**

### Checks implemented (deliberately minimal)

| Code | Fires when | Grounding | Fires on the synthetic sample? |
|---|---|---|---|
| `NO_LINKS` | the optional `links` block is absent/empty (record declares no relationship to other records) | `links` is an optional schema block; reuses the documented upstream code name | **Yes** — the sample has no `links` |
| `QC_NONVALID_WITHOUT_EVIDENCE` | `measurement.qc.status != "valid"` but `qc.evidence` is missing | the schema itself notes `qc.evidence` is "REQUIRED in practice when status != valid" but does **not** hard-enforce it | No — sample `qc.status` is `valid` |

These are **local heuristics**, not verified byte-for-byte against the upstream portal. They were
chosen because each is grounded in the vendored schema's own optional structure / documented
conventions and requires **no scientific guessing** and **no second domain**.

## 3. How to run it

```bash
# Hard official validation, then the advisory soft-warnings underneath it:
.venv/bin/isaac validate docs/samples/01JQZ0SYNTHXANESDEMO000000.json --official --warnings
```

```text
PASS — valid against official ISAAC schema v1.05

Advisory portal warnings (LOCAL seam — do NOT affect official validity or export):
  ⚠ [NO_LINKS] links — record declares no relationships to other records (optional `links` block absent).
(1 advisory warning(s) — non-gating)
```

The exit code is **0** — the record is officially valid, and the advisory warning does not change
that. That is the whole point: a **valid, audit-clean record can still carry soft warnings**, and
they are informational only. The `--warnings` flag prints the advisory tier *after* the hard result
and is never folded into the exit code. Programmatically, call
`isaac_records.portal_warnings.portal_warnings(record)`.

## 4. What this is NOT (honesty)

- **Not official portal parity.** The upstream `portal/validation.py` is **not vendored** in this
  repo. This module does not reproduce its full rule set, its exact codes, or its exact semantics.
- **Not a gate.** It cannot reject a record or block an export. Only the official schema does that.
- **Not domain-complete.** Most documented upstream codes (`MISSING_PH`,
  `GALVANOSTATIC_NO_POTENTIAL`, `FE_SUM_EXCEEDS_UNITY`) are electrochemistry-specific and out of
  scope for the current single characterization/XANES path — they are intentionally **not**
  implemented (implementing them now would mean guessing domain rules we don't yet own).
- **Not AI review.** Stage 4 (`review.py`) remains a separate advisory placeholder.

## 5. Current limitations

- Two checks only; both are local heuristics grounded in the vendored schema, not the upstream
  validator.
- No provenance record for upstream codes because the upstream code is not vendored here.
- Warning wording/codes may diverge from the real portal until parity work is done.

## 6. What mentors still need to decide

This maps to **D2** in [`mentor-decisions.md`](mentor-decisions.md):

- **Vendor the real thing?** Decide whether to vendor + review the upstream `portal/validation.py`
  (with provenance in `schema/PROVENANCE.md`) to replace these local heuristics with true parity.
- **How much reconciliation?** If vendored, decide how closely our codes/messages must match the
  portal's, and whether the electrochemistry-domain codes matter before a second domain exists.
- **Keep it non-gating?** Confirm the standing rule that this tier stays advisory forever — it must
  never gate export even after parity, unless a future user-approved policy explicitly wires it in.

Until those decisions, this remains a **non-gating advisory seam**: useful for surfacing soft issues
in the demo, honest about not being the official portal.
