# Hosted QA Checklist — for Krish

**Created:** 2026-07-31 · Closes gates **G1** and **G4** in the
[Baseline Completion Matrix](superpowers/plans/2026-07-31-baseline-completion-matrix.md).

**Why this is yours and not the agent's.** `/krish` sits behind an Authentik forward-auth edge.
Reaching it requires signing in, and an agent must not enter credentials or handle your session.
This has been attempted and stopped at the login flow — most recently `GET /krish/api/health`
returned **HTTP 302** to the Authentik edge, so **which image is running is UNKNOWN**. No rollout,
gate, or reconnaissance result has ever been observed from the agent's side, and none is claimed.
**The real database has never been contacted; no scan has ever run.** Everything below is unverified
until you run it.

**Three expectations to set before you start, so a correct result does not look like a failure:**

1. **A failed scan returns HTTP 200**, with a `status` of `refused`, `error`, `not_configured` or
   `busy` and, where one applies, a named `refusal_gate`. Only a concurrent scan returns 409. A
   refusal is the system working, not breaking. Note the distinction, because it changes who owns the
   result: `refused` means a **gate** stopped the scan deliberately; `error` means something went
   wrong **inside** the app (including the projection allowlist and the final leak scan failing
   closed) and the report was replaced by a sanitized envelope rather than served. Both are complete,
   honest answers and both should be sent as-is.
2. **`records_failing_full_schema > 0` is likely and is a useful result.** Dean's guide says schema
   conformance is "expected but **unverified**" and that "finding drift is a useful result, not a
   problem with the database". Do not treat drift as a bug to be worked around.
3. **The `dataset` block is deliberately narrower than it was in `v0.0.32`.** Five aggregates that
   image served — `by_instance_path`, `distinct_structural_signatures`, `total_link_count`,
   `dangling_link_count`, `vocabulary_term_count` — are **withheld** pending Dean's answer to G3,
   and the response now *names* them in `dataset.withheld_pending_visibility_decision`. If you were
   expecting them, their absence is the fix, not a bug. §1.2 below is where you check that.

---

## Part 1 — Rollout (G1)

Sign in to `https://isaac.slac.stanford.edu/krish` first, so the session cookie is present.

### 1.1 Health — `GET /krish/api/health`

> **Which SHA to compare against.**
>
> **`<CLOSURE_MERGE_SHA>` — PLACEHOLDER, to be filled in by the orchestrator when the closure PR is
> merged. It does not exist yet.** Do not substitute an earlier SHA to make this step pass. The
> point of the step is that the *final* code — the A11Y-02/A11Y-03 fixes and the G3 narrowing of the
> `dataset` block — is what is actually running. An older SHA here means you would be QA-ing the
> wrong build, and in particular you would be looking at a `dataset` block that still serves the
> five withheld aggregates.
>
> **Two things about the image chain that are honestly unknown from this repository**, so that
> "`commit` is not what I expected" does not get misdiagnosed:
>
> * Every push to `main` publishes an image — `.github/workflows/build-push.yaml` has **no path
>   filters**, so even a docs-only merge builds and tags one. Images `v0.0.33` through `v0.0.37`
>   were all built and pushed by successful CI runs. Those digests are **CI's record of what it
>   pushed**, read out of the workflow logs; **no registry-side confirmation was possible** from the
>   agent's environment (anonymous `ghcr.io` token failed, and `gh api /orgs/ISAAC-DOE/packages`
>   returned 403 for missing `read:packages`).
> * **Which image the cluster actually selects is UNDETERMINED.** No Flux `ImagePolicy` or
>   `ImageUpdateAutomation` manifest exists in this repository — that configuration lives in
>   `isaac-k8`, which is Dean's and out of reach here. So whether the pod tracks `:latest`, a semver
>   range, or a pinned tag is **not something this document knows**, and it is not guessed.
>
> The consequence: if `commit` does not match, the correct action is to **wait and re-check, then
> ask Dean** — not to assume a build failed.

| Field | Expected | Meaning if different |
|---|---|---|
| `commit` | **`<CLOSURE_MERGE_SHA>`** (placeholder — see the box above) | Flux has not rolled yet, or the cluster's image-selection policy does not pick this tag. Wait and re-check; if it persists, ask Dean. Do not chase it, and do not proceed with §1.2 against an older commit — the `dataset` shape differs |
| `mode` | `synthetic-only` | correct and expected; it describes the **workspace**, not the database |
| `database.configured` | `true` | `false` means `PGHOST` is not reaching the pod → Dean |
| `database.classification` | `isolated-app-postgres` | — |
| `database.contains_production_derived_records` | `true` | — |
| `database.record_display` | `closed` | anything else is a **stop-and-report** |

Health opens **no database connection** by design — it is the Kubernetes readiness-probe target, and
a database outage must never take the pod out of service. Its `last_recon` is a per-process memo, not
live state.

### 1.2 Reconnaissance — `GET /krish/api/runtime/database/recon`

`database.gates` is an object with exactly **seven** boolean keys. These are the names you will
actually see in the JSON — all seven should be `true`:

- [ ] `database_identity`
- [ ] `current_user`
- [ ] `session_user`
- [ ] `tls`
- [ ] `records_table_present`
- [ ] `transaction_read_only`
- [ ] `not_production_shaped`

If the scan **refuses**, `refusal_gate` names the gate that stopped it, and that name comes from a
wider internal set than the seven above — it may also be `opt_in`, `pgdatabase_env`, `no_mutation`,
or `schema_root`. A refusal is a complete, honest answer; send it as-is and I will classify whether
it is ours, Dean's, or the environment's.

#### Check the `dataset` key set against the frozen allowlist

This is the G3 narrowing, and it is the one step where reading the *shape* matters more than reading
the values. `dataset` is built key-by-key from a frozen tuple in
`apps/api/isaac_api/routes.py` (`_DB_RECON_DATASET_KEYS`), so the served key set must be **exactly**
these **16**, no more and no fewer:

- [ ] `total_records`
- [ ] `records_scanned`
- [ ] `records_parsed`
- [ ] `parse_failures`
- [ ] `record_id_digest_count`
- [ ] `expected_seed_rows`
- [ ] `seed_count_matches`
- [ ] `records_passing_full_schema`
- [ ] `records_failing_full_schema`
- [ ] `total_validation_issues`
- [ ] `by_rule_family`
- [ ] `by_schema_path`
- [ ] `by_record_type`
- [ ] `by_record_domain`
- [ ] `vocabulary_cache_present` — a **boolean** (`true`/`false`). It replaced the former
      `vocabulary_term_count`; presence, not cardinality. **If you see a number here, you are on an
      old image** — go back to §1.1
- [ ] `withheld_pending_visibility_decision` — **must be present**, and should list exactly
      `by_instance_path`, `distinct_structural_signatures`, `total_link_count`,
      `dangling_link_count`, `vocabulary_term_count`

And the negative check, which is the actual assurance:

- [ ] **none of those five withheld names appears anywhere in the response as a data key** — only
      inside the `withheld_pending_visibility_decision` list and inside the `limitations` prose
- [ ] **no key in `dataset` that is not on the list above.** An unlisted key cannot get there by
      design (the code raises and fails closed into a sanitized `projection` failure envelope), so
      if you see one, that is a stop-and-report

If instead you get `status: "error"` with `database.refusal_gate: "projection"` (the field is nested
inside the `database` block, not at the top level), that is the allowlist failing
closed — a key was built that is not on the list, so the whole report was replaced by a sanitized
envelope rather than served. Send it: it is a bug report, and a well-behaved one.

**One honest caveat about `by_schema_path`, so an empty list is not misread as a clean database.**
It is populated by the diagnostics enricher. If that enricher does not load in the pod, the report
falls back to the `official` engine, `by_schema_path` comes back **empty**, and `by_rule_family` is
then the *only* breakdown carrying signal. An empty `by_schema_path` alongside a non-zero
`total_validation_issues` therefore means "the path breakdown was unavailable", **not** "the drift
has no schema location". The report names which engine produced it — include that field when you
send the JSON back. Relatedly: **do not expect a particular set of `family` labels.** The two
engines label families differently and the deployed engine's label set is an open set of raw
jsonschema keywords. Nobody has seen it, because the scan has never run.

#### Check integrity

- [ ] `rows_modified` is **0**
- [ ] `rows_before` equals `rows_after`
- [ ] `dml_statements_issued` is **0**
- [ ] `partial_schema_validation_runs` is **0**
- [ ] `schema_fingerprint` identical before and after; `schema_stable_across_run` is `true`

### 1.3 Read the JSON yourself — do not trust the tests

Scan the whole response for anything that should never appear:

- [ ] no record ID (raw or hashed) — only `record_id_digest_count`
- [ ] no record title
- [ ] no scientific value
- [ ] no evidence content
- [ ] no full or partial record JSON
- [ ] no person's name or identity
- [ ] no host, port, username, password, secret name, or connection string

If **any** of these appears, stop and send it to me before sharing the response further.

### 1.4 UI spot-check

- [ ] Top-bar chip reads `Synthetic workspace · test DB diagnostics`
      (or `· test DB check failed` if the last scan refused — both are honest)
- [ ] My Experiments, Record Detail, Statistics, Project Memory all behave exactly as before
- [ ] No record from the database appears anywhere in the UI
- [ ] Browser console: no errors

Two accessibility fixes ship in this build. They are verified **locally on macOS** against the
accessibility *tree*, on macOS locally **and on Linux CI** (run `30677607861` on `a911b8c`: 579
passed, 1 skipped against the tightened ratchet, where the three deleted entries assert ZERO nodes),
plus 11 jsdom tests running the real axe engine. What no automated check can tell you is whether a
screen reader actually *says* the right
thing, so if you have VoiceOver to hand these are the two worth ten seconds each:

- [ ] Narrow the window below 640px (or zoom to 200%): the top-bar **search** control still
      announces as a named button — "Search, button" — even though its visible label is hidden
- [ ] On a record's **Evidence** screen, the trail entries announce as buttons with a
      selected/unselected (pressed) state, and the list still announces as a list

### 1.5 Send back

Paste the recon JSON. **It is safe by construction** — that is the whole design — but §1.3 is your
independent check on that claim, and it is worth doing precisely because nobody has ever seen the
real output.

---

## Part 2 — Responsive and 200% zoom sign-off (G4)

Still open from Phase 33/34, and still yours. Automated coverage from the browser/accessibility
slice, where it exists, runs against a **local** instance only — it can never run against `/krish`,
because of the Authentik edge. Automation does not close this gate.

**And for 200% specifically it could not close it even if it ran against `/krish`.** The automated
`zoom-200` project models zoom as a 640×400 viewport at device-pixel-ratio 2. That was probed
directly rather than assumed, and two facts came out of it: the device-pixel-ratio contributes
**nothing** to CSS layout (the same page at DPR 2 and DPR 1 measured byte-identically), and **no CDP
method, launch flag or Playwright API can drive Chrome's own zoom control at all** — pinch-zoom and
the CSS `zoom` property were both tried and neither fires the breakpoint. Viewport-halving is
therefore the correct and only available *model* of what 200% zoom does to layout, and a model is
what it stays. Your <kbd>Cmd</kbd>/<kbd>Ctrl</kbd>-<kbd>+</kbd> pass is the only thing that exercises
real zoom, including the parts the model provably does not reproduce: browser chrome and scrollbar
scaling, `outerWidth` staying at the window's real width, and glyph rounding at the zoomed scale.
Details in [`browser-accessibility-testing.md`](browser-accessibility-testing.md) §4.

Surfaces: My Experiments · Record Detail · Guided Completion · Evidence · Export Readiness ·
Project Memory (incl. Graph) · Governance (incl. Validator) · Statistics · Settings (all five tabs).

Viewports: **1280×800**, **1024×768**, **768×1024**, **375×812**.

Then **real browser zoom at 200%** (`Cmd +` / `Ctrl +`, not a narrow window — they are genuinely
different: zoom halves the CSS layout viewport *and* doubles device pixel ratio).

At each: no clipping, no overlap, no horizontal page scroll, focus visible when tabbing, dialogs
dismissable with Escape.

---

## Part 3 — Two things that need your decision, not your testing

- **Personal deployments** are still live, public and unauthenticated; Railway is 77 commits stale
  and has a **persistent volume**, so deleting destroys data that pausing preserves. Facts and an
  approval-gated order are in [`personal-deployment-retirement.md`](personal-deployment-retirement.md).
  Recommendation: do nothing until G1 closes.
- **Compression** — one observation would settle a deferred performance question. In DevTools →
  Network, load `/krish` and check whether a `.js` asset response carries
  `content-encoding: gzip` or `br`. If it does, the app should add nothing. If it does not, adding
  compression is worth a slice. The ingress config lives in `isaac-k8`, which is Dean's and not in
  this repository, so this cannot be checked any other way from here.

---

## Part 4 — Questions for Dean (not yours to answer)

- **G2** — may the hosted app display per-record fields from `metadata_assistant`, and to whom?
  Everything real-record-facing is blocked on this and is deliberately unbuilt.
- **G3** — **five** aggregates beyond Dean's enumerated list were served in image `v0.0.32`:
  `by_instance_path`, `distinct_structural_signatures`, `total_link_count`, `dangling_link_count`
  and `vocabulary_term_count`. (Earlier drafts of this checklist said three; that undercounted.)
  They are record-*derived* structural facts — none emits a value, title or id, but each is produced
  by reading the stored documents. **All five have since been withdrawn from the HTTP response** and
  are named in `dataset.withheld_pending_visibility_decision`; `vocabulary_term_count` was coarsened
  to the boolean `vocabulary_cache_present`. So the question to Dean is no longer "should we remove
  these" — it is: *were any of them within what you intended, and may they be restored?* Retained,
  with reasoning: `by_rule_family` and `by_schema_path`, because they are produced by the vendored
  **public** schema rather than by any stored value.

  Two things to say plainly when raising this: the five **were live in a published image**, and
  narrowing them now does not undo that. And withdrawal is what happened to the *response* — the
  wider report is still computed in the pod for the offline `scripts/db_recon.py`, which the
  container's `COPY` allowlist deliberately keeps **out of the image** (pinned by a test).
