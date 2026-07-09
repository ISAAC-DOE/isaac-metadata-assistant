# Validation, audit & warning model (UI handoff)

The UI display model for the three deterministic signals the pipeline produces — plus Graphify. These three
signals do **three different jobs** and must never be collapsed into a single "status" light. Getting this
right is the difference between a UI a scientist trusts and one that quietly misleads.

Ground truth: [`../cli.md`](../cli.md) "How to interpret validation output", [`../portal-warnings.md`](../portal-warnings.md),
[`../sample-record-walkthrough.md`](../sample-record-walkthrough.md). Companion:
[product-context.md](product-context.md) and [data-governance-and-safety.md](data-governance-and-safety.md).

---

## The three signals, three different jobs

| Signal | Source of truth | What it means | Gates export? |
|---|---|---|---|
| **Official schema validation** | `isaac validate --official` (`official.py`, v1.05) | Deterministic **PASS/FAIL** verdict — valid against the vendored official ISAAC schema. | **Yes.** This is the hard gate; the same check gates `isaac export`. |
| **Evidence audit** | `isaac audit` (`audit.py`) | Sidecar **coverage** (`evidence N/N`): every evidence path resolves to a real field, 0 dangling. Provenance assurance on top of a PASS. | No — it is not a validity re-vote. |
| **Advisory warnings** | `isaac validate --official --warnings` (`portal_warnings.py`) | `⚠ [CODE] …` soft notes a human may want to look at. | **Never.** Non-gating; does not change the exit code. |

The trap to design against: a naive UI shows one green/red badge. That conflates "is it valid?", "is its
evidence intact?", and "are there soft notes?" — three orthogonal questions. Give each its own indicator.

## Hard failure vs. soft warning

- **A warning does not mean the record is invalid.** A record can be officially valid, audit-clean, and
  still carry advisory warnings. The committed sample does exactly this: PASS, `evidence 26/26`, and one
  `⚠ [NO_LINKS]` warning. The UI must not render a warning with failure semantics (red, blocked, error icon).
- **Zero warnings does not prove portal acceptance.** The advisory warnings are two local heuristics
  (`NO_LINKS`, `QC_NONVALID_WITHOUT_EVIDENCE`), **not** the upstream `portal/validation.py` — which is not
  vendored in this repo. A clean local run is **not** a portal sign-off. Never phrase absence of warnings as
  "accepted by ISAAC" or "portal-clean".
- **Only official validation (and the export gate it backs) decides validity.** Audit reports coverage;
  warnings are reviewer context. Design the hierarchy so official PASS/FAIL is visually dominant.

## Evidence coverage and sidecar separation

- Export produces **two** files: the official record (`records/<ULID>.json`) and its evidence sidecar
  (`records/<ULID>.evidence.json`). They are different kinds of thing.
- **Validate the record, not the sidecar.** The sidecar is an assistant audit artifact; it is *not* an ISAAC
  record and **fails official validation by design** (running `isaac validate <ULID>.evidence.json --official`
  is a known mistake). A UI must never offer or imply "validate this sidecar." `isaac audit` already handles
  this correctly: it validates the record and *separately* reports sidecar coverage.
- **Coverage counts the dotted JSON-path keys.** In the sample, `evidence 26/26` means all 26 direct field
  entries resolve. The namespaced `assets:` / `descriptors:` / `implicit:` keys are provenance for structured
  blocks and are not part of that count — don't surface "26/26" as if it were a completeness percentage of
  the whole record.

## Why Graphify does not validate

Graphify is the **memory plane**. It finds related docs/records and navigates the codebase; it returns nodes
with `src=<file> loc=L<line>` leads you then open and confirm. It **cannot** establish that a record is
valid, that coverage is complete, or that a value is correct. The **truth plane is Graphify-free**, enforced
by `test_core_never_imports_graphify`. In the UI, Graphify output must be visually and semantically separate
from the three deterministic signals — a "leads / context" surface, never a status verdict.

## Recommended UI states

For each state: what the UI should **say**, what it must **not** say, and the underlying **source of truth**.
Visual semantics are suggestions for the designer, not requirements.

### Validation PASS
- **Suggested visual:** solid success color, checkmark, prominent (this is the headline signal).
- **Say:** "Valid against official ISAAC schema v1.05."
- **Do not say:** "Approved by ISAAC," "portal-validated," "accepted" — schema-valid is not portal sign-off.
- **Source:** `isaac validate <record> --official` → exit `0`.

### Validation FAIL (with error list)
- **Suggested visual:** solid error color, blocked/stop icon; list each schema error with its JSON path.
- **Say:** "Invalid against official ISAAC schema v1.05," then the specific errors. Export is blocked.
- **Do not say:** vague "something went wrong." Show the real schema errors; do not offer a `--force` (none
  exists) or any "export anyway" path.
- **Source:** `isaac validate <record> --official` → exit `1`.

### Audit PASS
- **Suggested visual:** secondary success indicator, distinct from the validation badge (e.g. a coverage
  chip `evidence 26/26`).
- **Say:** "Evidence audit clean — all N evidence paths resolve (0 dangling)."
- **Do not say:** "audit passed" as a synonym for "valid." Audit is coverage, not the validity verdict.
- **Source:** `isaac audit --records-dir <dir>`.

### Audit missing / dangling evidence
- **Suggested visual:** caution indicator on the coverage chip; list the unresolved JSON-path keys.
- **Say:** "Evidence audit found N/M paths resolved — K evidence entries do not map to a real field."
- **Do not say:** "record is invalid" (a record can be schema-valid with a coverage gap) — but do flag it as
  an integrity issue to fix by re-exporting from the corrected draft, never by hand-editing `records/`.
- **Source:** `isaac audit` coverage output.

### Advisory warning(s) present
- **Suggested visual:** low-emphasis informational treatment (amber/neutral "note" chip, `⚠` glyph) — clearly
  *not* an error state. Keep it subordinate to the PASS badge.
- **Say:** "1 advisory warning (non-gating): `NO_LINKS` — record declares no relationships to other records."
- **Do not say:** anything implying invalidity or portal rejection; do not fold it into a pass/fail count.
- **Source:** `isaac validate <record> --official --warnings` (printed after the hard result; exit code
  unchanged). See [`../portal-warnings.md`](../portal-warnings.md).

### Graphify explanation available
- **Suggested visual:** a separate "context / related" panel, visually distinct from the status signals;
  each item shows its `src=<file> loc=L<line>` lead.
- **Say:** "Related (from project memory — verify against the cited file): …"
- **Do not say:** present a graph lead as a fact, a validity claim, or a scientific value. Always name the
  file to open and confirm.
- **Source:** Graphify (`graphify query/explain/path`) — memory plane, leads only.

### Graphify unavailable / stale
- **Suggested visual:** quiet, non-blocking notice on the context panel; the rest of the UI works normally.
- **Say:** "Project memory is unavailable / may be out of date — answering from source files directly."
- **Do not say:** fabricate graph output, or block the task. Graceful degradation: the deterministic pipeline
  does not depend on Graphify.
- **Source:** freshness helper `python scripts/check_graphify_freshness.py` → prints `fresh` / `stale` /
  `missing`, exits `0` / `1` / `2`. See [`../query-safety-checklist.md`](../query-safety-checklist.md).

## Copy guidance (exact-tone examples)

Honest phrasing the UI can reuse verbatim. The pattern: name the schema and version, never imply an external
authority the tool doesn't have.

| Situation | Good copy | Avoid |
|---|---|---|
| Official PASS | "Valid against official ISAAC schema v1.05." | "Approved by ISAAC," "Portal-validated," "Certified." |
| Official FAIL | "Invalid against official ISAAC schema v1.05 — 2 errors. Export blocked." | "Rejected by ISAAC," "Failed portal." |
| Audit clean | "Evidence audit clean — 26/26 evidence paths resolve." | "Fully complete record," "100% verified." |
| Warning present | "1 advisory warning (non-gating) — does not affect validity or export." | "1 issue found," "1 error." |
| No warnings | "No advisory warnings from the local seam." | "Portal-clean," "Accepted by ISAAC," "No issues." |
| Blocker open | "Awaiting confirmation: sha256 of `…/CuO2_merged.xdi`. Not exportable until answered." | "Auto-filling…," "Estimated value." |
| Graphify lead | "Related (project memory — open the cited file to confirm): `export.py` L83." | "Graphify says this record is valid." |
| Graphify down | "Project memory unavailable — answered from source files." | (silently showing nothing, or inventing a graph result) |

Rule of thumb for every status string: **name the deterministic source** (schema v1.05, the audit, the local
warning seam) so the claim is checkable, and never borrow authority from the upstream portal, from Graphify,
or from the AI itself.
