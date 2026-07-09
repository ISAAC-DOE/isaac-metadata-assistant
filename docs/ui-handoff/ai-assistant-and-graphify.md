# UI handoff — AI assistant and Graphify in the UI

> Design handoff, **not** implementation. How the assistant (Claude) and Graphify appear and behave
> in a future ISAAC UI. The governing rule: **AI and Graphify explain and navigate; they never
> create scientific truth and never validate.** Companions: [`screens.md`](screens.md),
> [`design-system.md`](design-system.md), [`user-workflows.md`](user-workflows.md). Ground truth:
> [`../claude-workflow.md`](../claude-workflow.md), [`../graphify-workflow.md`](../graphify-workflow.md),
> [`../query-cookbook.md`](../query-cookbook.md), [`../query-safety-checklist.md`](../query-safety-checklist.md).

## Roles, stated plainly

- **The assistant is an optional helper, not a truth source.** It explains what happened, narrates
  artifacts, and routes the user to the deterministic checks. It is visually subordinate everywhere
  (see [`design-system.md`](design-system.md)).
- **Graphify is memory / navigation, not a validator.** It answers "how is this wired?", "which
  files implement X?", "what's related?" — never "is this valid?" or "what's the missing value?".
- **The deterministic CLI is truth.** `isaac validate | export | audit` decide validity,
  exportability, and completeness. If the assistant/graph and the CLI ever disagree, the CLI wins
  and the UI says so.

## What the assistant may and may not do

**May:**

- Explain docs, code, schema, and evidence in plain language.
- Route the user: "run validation", "answer these blockers", "see the sidecar".
- **Propose** a value **with cited evidence** for the user to confirm.
- Locate things via Graphify, then open and quote the real file.

**May not (UI enforces):**

- Fill a scientific value the user did not confirm and no source supports.
- Fabricate a sha256, URI, number, descriptor, edge, or timestamp.
- Mark a record valid/invalid, or override validation, audit, or the export gate.
- Mutate a record or the sidecar.
- See, index, or send **real / private** data to any model without explicit written approval.

## Propose → confirm → evidence (the one place AI touches values)

The assistant may **propose**, never **decide**. The UI must make this a two-step, human-owned
gate:

1. Assistant proposes a value **with a cited source** (e.g. "the archive listing shows
   `xanes_reduction_v2.ipynb`; is this the processing notebook?"). A proposal is visually distinct
   from a confirmed value — it is a suggestion, not data.
2. The **user explicitly confirms**. Only then is the value written.
3. The confirmation is stored as **`user_confirmation` evidence**
   (`{source_type: "user_confirmation", question, answer, timestamp}`) **alongside** the
   deterministic evidence, never replacing it — exactly as `complete.apply_answers` does today.

The assistant never supplies a sha256 / number / URI to satisfy the schema. "I don't know" leaves
the field honestly missing.

## Where the assistant appears

- A **persistent side/below panel** on the artifact screens (draft, sidecar, validation & audit,
  export) — visually subordinate to the deterministic surfaces, per [`screens.md`](screens.md).
- **Contextual explain affordances** on individual elements ("explain this field", "explain this
  warning") that open the panel pre-scoped to that element and its evidence.
- It is **never** the primary surface of any screen and never occupies the canvas the artifact owns.

## Assistant panel behaviors

- **Source citation required on every answer.** Show an **"answered from: …"** label —
  `schema` / `audit` / `git` / `graph` / `files`. An answer with no source is not shown.
- **Route truth questions off the graph.** "Is this valid?" → `isaac validate --official`.
  "Is it complete / do sidecar paths resolve?" → `isaac audit`. The panel should visibly hand these
  to the deterministic surfaces rather than answering itself.
- **Open the cited file.** For navigation/memory answers, the graph result is a **lead**; the final
  answer quotes the real file, which the user can open.
- **No verdicts.** The panel never renders PASS/FAIL styling or a validity claim.

## Suggested prompt chips (grounded in supported queries)

Draw chips from real, supported questions in [`../query-cookbook.md`](../query-cookbook.md) —
never invent capabilities. Group by the source that answers them:

- **Truth (routes to CLI/schema):** "Is this record valid?" · "What's required for this record
  type?" · "Which records fail validation or lack a sidecar?"
- **Evidence / provenance (reads the sidecar):** "Where did the beamline come from?" · "Trace this
  field to its source."
- **Advisory:** "What does `NO_LINKS` mean?" (advisory / non-gating — never an invalidity verdict).
- **Memory / navigation (Graphify, then open the file):** "Which files implement export?" · "Where
  is the sidecar explained?" · "Which records are related to CuO?"
- **History:** "What changed since we vendored v1.05?" (routes to `git log`).
- **Policy:** "Can we use real data?" (routes to data governance — never guessed, never asked of the
  graph).

Chips must degrade honestly: a memory chip when the graph is stale/missing still answers from files
and says so.

## Graphify freshness indicator

Surface `scripts/check_graphify_freshness.py` output as a small, always-visible indicator on the
memory panel. Exact meanings:

- **`fresh`** (exit `0`) — no tracked source is newer than the graph build. Graph leads are current;
  still open the cited file before asserting.
- **`stale`** (exit `1`) — a tracked source changed after the last build. Show a caveat; verify any
  specific claim against the actual file; offer (don't force) a refresh (`graphify update .`).
- **`missing`** (exit `2`) — no `graphify-out/graph.json`. The memory layer isn't built; answer from
  files directly and offer to build it.

The indicator compares mtimes only, never contents, and never refreshes the graph itself.

## Fallback when Graphify is unavailable

Graceful degradation is the rule (see [`../graphify-workflow.md`](../graphify-workflow.md) §7):

- **Never fail the task** for lack of the graph.
- **Answer from the repo files / a deterministic CLI check** instead.
- **Disclose** which situation applied (unavailable / missing / stale / noisy).
- **Never fabricate graph output** — no invented nodes, edges, or "the graph says…".

The UI should make the fallback visible ("memory layer unavailable — answered from files"), not
silent.

## What the assistant refuses — and how refusal looks

Refusal is a **feature**, the no-guessing policy made visible. Style it as **protective, not as
failure** (see governance/blocker styling in [`design-system.md`](design-system.md)).

The assistant refuses to:

- invent a scientific value, unit, hash, URI, path, descriptor, edge, or timestamp;
- validate, invalidate, or override a deterministic result;
- process real / private data without written approval;
- present a graph guess as fact.

Refusal copy should be calm, specific, and forward-pointing — for example:

> "I can't fill `descriptor` — no source supports a value and you haven't confirmed one. I can show
> the evidence I do have, or you can confirm a value and I'll store it as `user_confirmation`
> evidence. If you don't have it, leaving it missing is honest."

Never phrase a refusal as an error or an apology-for-failing. It is the product doing its job.
