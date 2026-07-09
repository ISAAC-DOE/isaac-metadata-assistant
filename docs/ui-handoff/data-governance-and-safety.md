# Data governance & safety (UI handoff)

Governance and safety constraints a future UI must respect. The rule that governs everything: **synthetic
only by default; real or private data is approval-gated and must never enter git, an LLM, or any external
service without explicit written approval.** A UI makes data *easier to move* — which makes these boundaries
more important, not less.

Ground truth: [`../data-governance.md`](../data-governance.md), repo [`../../README.md`](../../README.md)
"Data governance", project `CLAUDE.md` §6 / `AGENTS.md` §10, [`../../SECURITY.md`](../../SECURITY.md).
Companion: [product-context.md](product-context.md), [validation-audit-warning-model.md](validation-audit-warning-model.md).

---

## Synthetic-only default

All shipped data is **unmistakably fake**. The committed demo is a fictional **year-2099** CuO / Cu K-edge
XANES session with fictional people (`Ada Lovelace`, `Grace Hopper`) and obviously patterned stand-in
`sha256`s. The year-2099 date is deliberate — it makes the data impossible to mistake for real.

Safe-to-commit, synthetic assets:

- `tests/fixtures/synthetic/` — the mock campaign sheet, raw scan listing, and simulated completion answers
  that drive the demo.
- `docs/samples/` — the committed official record + evidence sidecar produced by the demo.
- `tests/fixtures/official/` — the upstream ISAAC golden records, copied verbatim (public,
  provenance-documented in [`../../schema/PROVENANCE.md`](../../schema/PROVENANCE.md)).

A UI built for demos should default to this synthetic corpus and make it obvious that it is fake.

## Real / private data is approval-gated

No real or sanitized SLAC/SSRL artifacts, and no private data, may be processed without **explicit written
data-governance approval** that names (a) exactly which artifacts, (b) whether they may leave SLAC machines,
and (c) whether they may be committed (default: never). This covers real experiment spreadsheets, beamline
web-form screenshots, proposal/narrative PDFs, raw data files and raw file listings, private notes or
internal identifiers, and any secrets/keys/credentials/`.env`.

`examples/` is the directory where real input artifacts would go. It is **gitignored** (`examples/*` with
only `examples/README.md` tracked) and must be treated as sensitive. Real artifacts placed there stay local
and never leave the machine through git.

## What the UI must block or warn about

These are hard product boundaries, not styling choices. A UI should make each of them impossible-by-default
or gated behind an explicit, logged approval:

- **Upload of real data.** There is no real-data pipeline today. Any future upload surface must refuse real
  artifacts unless a governance approval is on record, and must never auto-commit or auto-sync them.
- **Indexing private data into Graphify.** Never index real or private artifacts into the knowledge graph.
  Graphify is derived and can leak provenance; keep it synthetic-only.
- **Sending content to external services.** Sending real or private artifacts to an LLM (including Claude) or
  any external API is **not allowed by default**. The deterministic core is LLM-free; the Claude skills are an
  assistant layer, and using them on real data means a model reads it — which requires separate approval
  (mentor decisions D3/D4).
- **Sharing artifacts before sidecar review.** A record's evidence sidecar can carry identifying provenance
  (real file paths, archive URIs, hashes). Do not offer a one-click "share/export" that bypasses a review of
  what the sidecar contains.

## Local-first recommendation

The first UI should be **local-only**:

- No cloud storage of records, drafts, evidence, or source artifacts unless explicitly approved.
- No secrets, keys, or credentials handled or stored by the UI.
- **No telemetry by default** — no analytics, crash reporting, or usage beacons that could exfiltrate file
  names, field values, or provenance.
- Work against the local repo and the local CLI; treat "leaving this machine" as a governance event, not a
  default behavior.

## Clear user-facing warnings

Suggested placement and copy for governance surfaces (wording is a starting point, not a mandate):

- **Persistent mode banner (always visible).** "Synthetic mode — demo data only. Do not load real
  experiment data." Keep it visible so the operator always knows which regime they're in.
- **Before any file load / upload dialog.** "Only synthetic or approved data may be loaded. Real SLAC/SSRL or
  private artifacts require written data-governance approval." Require an explicit acknowledgment for anything
  outside the synthetic corpus.
- **Before sending content to an LLM / external service.** "This will send file content to a model. Not
  allowed for real or private data without approval. Continue?" Default to the safe choice.
- **Before share/export of a record.** "Review the evidence sidecar before sharing — it may contain source
  file paths, URIs, and hashes." Link to the sidecar review view.

## Evidence sidecar review before sharing

The evidence sidecar (`records/<ULID>.evidence.json`) maps official JSON-paths to their **source**: file
names, sheet/cell or page locators, URIs, and `sha256` hashes. For synthetic data this is all fake and safe.
**If real data is ever used, the sidecar can contain identifying provenance.** A UI that offers sharing must
surface a sidecar review step first and treat the sidecar with the same governance as the underlying
artifacts. (Note: the sidecar is an assistant convention, not an official ISAAC standard — decision D1.)

## Graphify index sensitivity

`graphify-out/` is a **derived** graph rebuilt from the repo. It is gitignored and **never committed**; it
belongs to the memory plane and never decides validity. Two rules a UI must honor:

- **Never index real or private data** into Graphify — the graph is not a safe place for sensitive provenance.
- **Never commit or export `graphify-out/`.** It can be deleted and regenerated at any time; treat it as
  disposable local cache, not a shareable artifact.

## Enforcing governance boundaries visually (design suggestion)

A concrete way to make the synthetic/real boundary legible — offered as a design idea, not a requirement:

- **A persistent "Synthetic mode" badge/indicator** in the app chrome, present in every screen, so the
  operator can never lose track of which data regime is active.
- **An explicit mode switch** to any "approved real data" regime that is gated behind an acknowledged
  governance approval and visibly changes the app's chrome (e.g. a distinct color and a standing warning
  banner) so real-data sessions look and feel different from synthetic demos.
- **Governance-blocked actions rendered as such** — disabled with an explanatory tooltip pointing to
  [`../data-governance.md`](../data-governance.md), rather than silently absent.

If sensitive data is ever committed by accident, the recovery path is in [`../../SECURITY.md`](../../SECURITY.md):
do not just delete it in a new commit (history retains it) — notify the project owner, rotate any exposed
secrets, and coordinate a history rewrite before the branch is shared.
