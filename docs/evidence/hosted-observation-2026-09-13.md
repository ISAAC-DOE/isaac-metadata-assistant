# Hosted observation, 2026-09-13 — the first INSPECTED recon response body

**Status: READ-ONLY OBSERVATION, captured artifact.** This is not operator testimony. Every figure
below was read from a response body in an authenticated browser session in this environment, and the
commands that produced them are given so they can be re-run.

**Authorization basis.** The project owner stated in-session that the SLAC session was already
authenticated and invited debugging through the browser tab. `GET /api/runtime/database/recon` is the
route authorized by **Slice 2A** (`CLAUDE.md` §15, *"the deployed pod performs read-only
reconnaissance and returns a sanitized aggregate report"*, authorized 2026-07-31).

**No credential was entered, and no agent connected to any database.** The pod opened its own
short-lived read-only connection, which is the whole point of the deployment-mediated design. The
prohibition at `2026-07-24-phase-37-readiness-plan.md:48-52` is on a connection *originating from a
laptop or from CI*; none was made. No kubeconfig, port-forward or Secret was requested.

**Data boundary.** Only sanitized aggregates were read. No record id, title, scientific value,
evidence entry or record text was read or is recorded here. Two fields the browser tooling itself
withheld as sensitive (`session_user`, `app_commit`) are reported as withheld rather than guessed.
Every figure recorded below falls inside Dean's enumerated list — record counts, counts by type and
domain, validation totals, schema version, reachability. `by_record_type` and `by_record_domain`
values were **not fetched**, because they were not needed.

---

## 1. What the hosted deployment is running

| Field | Observed |
|---|---|
| `commit` | `2f9a1133bcda7f45e1d751110641d1322586f60e` |
| `mode` | `synthetic-only` |
| `core` / `version` | `isaac_records` / `0.1.0` |

**That commit is byte-for-byte the current `main`.** `git rev-parse main` and `git rev-parse
origin/main` both return `2f9a1133…`. So for the first time in many sessions the hosted
deployment is provably running the head this repository can inspect, rather than an unobserved image.

**A cross-check that could have looked like a defect and is not.** The hosted `/api/health` payload
carries **no `mcp` block**. `MCP-003` adds one — and `MCP-003` lives on PR #248, not on `main`
(`git show main:apps/api/isaac_api/routes.py | grep -c '"mcp"'` → **0**). The absence is exactly
what running `main` predicts.

## 2. Gate G2 holds, and the workspace is not empty — both at once

`database.record_display` reads **`closed`**, and `contains_production_derived_records` reads
**`true`**. The 30-record production-derived corpus is present and is not displayed.

`GET /api/experiments` returns **3 experiments**, and none of them is from that corpus — they are
records this application created through its own durable Create Experiment path:

| Title | Status | Pending | Exported |
|---|---|---|---|
| `Durability check after 0001 (2026-08-09)` | `needs_attention` | 3 | false |
| `SYNTHETIC Run-slice hosted QA (cf2a8bc)` | `needs_attention` | 6 | false |
| `b` | `needs_attention` | 3 | false |

These are the artifacts of the `0001` hosted verification and a later run-slice QA, persisted because
`experiment_storage` is `postgres` / `durable`. **So `record_display: closed` and a populated
workspace are consistent, not contradictory** — the two live in different tables.

**A memory note is thereby stale.** The tutorial-scope entry records *"normal My Experiments is
PERMANENTLY empty (no create path exists)"*. A create path exists, the hosted screen renders a
**Create Experiment** control, and three records sit in the list. That note described a true state
that has since been superseded.

**And the run-projection counter corroborates the row count exactly.** Health reports
`run_projection.last_pass: {complete: 0, stale: 0, never_projected: 0, unavailable: 3, mismatch: 0}`.
**`unavailable: 3` is the same 3.** It reads `unavailable` rather than `never_projected` because
`0005_run_projection` is **not applied to the hosted database** — correctly, since it is not
owner-approved. Two independent surfaces agreeing on 3 is the kind of coherence that is hard to fake.

## 3. The recon response body, INSPECTED

`CLAUDE.md` §15 says of this route's masking that it is *"backed by code review rather than by an
inspected response body"*, and of its results that they are *"operator-relayed testimony, not a
captured artifact"*. **Both qualifications are now discharged for this observation.** Payload: 4,123
bytes, `report_format_version: 1`, `status: ok`, `schema_version: 1.05`.

### 3.1 The five G3 aggregates are withheld ON THE WIRE

`dataset` carries **sixteen** keys and **not one** of the five is among them:

```
by_record_domain · by_record_type · by_rule_family · by_schema_path · expected_seed_rows
parse_failures · record_id_digest_count · records_failing_full_schema · records_parsed
records_passing_full_schema · records_scanned · seed_count_matches · total_records
total_validation_issues · vocabulary_cache_present · withheld_pending_visibility_decision
```

`dataset.withheld_pending_visibility_decision` names exactly the five, and nothing else:
`by_instance_path`, `distinct_structural_signatures`, `total_link_count`, `dangling_link_count`,
`vocabulary_term_count`. `vocabulary_cache_present` is present and `true` — the boolean that
replaced the withheld cardinality, and reachability *is* on Dean's list.

**MY FIRST CHECK FOR THIS WAS A FALSE POSITIVE OF MY OWN MAKING, and it is recorded because the
next person will write the same check.** I tested `JSON.stringify(payload).includes('"' + key +
'"')` for each of the five and got **all five back**, which reads as a leak. The substring matched
**the withheld list itself**, which necessarily names them as strings. The designed behaviour and
its own violation have the same signature under a flat-text search. *Enumerate the keys of the
block; do not grep the serialized payload.*

### 3.2 The scan I triggered mutated nothing, and the wire says so

| `integrity` field | Observed |
|---|---|
| `ddl_statements_issued` | **0** |
| `dml_statements_issued` | **0** |
| `read_statements_issued` | 19 |
| `rows_before` / `rows_after` | **30 / 30** |
| `rows_modified` | **0** |
| `transaction_read_only` | `true` |
| `schema_stable_across_run` | `true` |
| `full_schema_fingerprint_match` | `true` |
| `partial_schema_validation_runs` | 0 |
| `session_statements_issued` | withheld by the browser tooling as sensitive |

All six preflight `gates` read `true`: `current_user`, `database_identity`, `not_production_shaped`,
`records_table_present`, `tls`, `transaction_read_only`. `refusal_class` is `null`.

**`rows_before` and `rows_after` are BOTH reported, which narrows a recorded limitation.** The
2026-08-08 private-30 entry lists as a limitation that *"no database row was re-read and compared
after the sweep (the connection closes first)"*. That remains true **of the private verification
mode**, which is a different path; it is not true of this route, which reports both sides of the
scan and a modified count. The two must not be conflated.

### 3.3 Official validation on the production-derived corpus

| Field | Observed |
|---|---|
| `total_records` | 30 |
| `records_scanned` / `records_parsed` | 30 / 30 |
| `records_passing_full_schema` | **30** |
| `records_failing_full_schema` | **0** |
| `total_validation_issues` | 0 |
| `parse_failures` | 0 |
| `expected_seed_rows` / `seed_count_matches` | 30 / `true` |

30 of 30 pass official ISAAC v1.05 validation with zero issues. This agrees with the 2026-08-08
operator-relayed figure, and unlike that figure it was read here from a response body.

### 3.4 The hosted engine is PostgreSQL 18

`database.server_version_major` is **18**, with `expected_major_version_match: true`. CI proves the
migrations against a `postgres:18` service container, and `CLAUDE.md` §15 is careful that this *"is
not the same as proving it against the hosted database with its real data"*. That caveat stands
untouched — **but the engine major version is no longer an assumption**, which removes one of the
several ways the CI-to-hosted inference could have been wrong.

## 4. QA-019 confirmed as a real hosted defect

On `https://isaac.slac.stanford.edu/krish/experiments`, `document.title` is the bare
**`ISAAC Metadata Assistant`** — no route segment, on a route that is not the app root. That is the
WCAG 2.4.2 defect `QA-019` fixes, observed on the deployed product rather than argued from source.
The local dev tab in the same browser, running this branch, renders
**`Review Export Readiness · ISAAC Metadata Assistant`**.

The hosted left navigation shows **five** destinations (`My Experiments`, `Project Memory`,
`Governance & Safety`, `Statistics`, `Settings & API`); this branch's `UX-002` work reduces that to
three by making Project Memory and Statistics children of Settings. Both readings are consistent with
hosted running `main`.

## 5. The honesty chip, measured hosted

Visible text: **`Workspace`**. Accessible name, opening with that visible text, as
`CLAUDE.md` §11 records:

> Workspace — nothing in this build adds a built-in example record to this workspace — they are
> created only inside a guided-walkthrough session; file upload is refused, and no official
> institutional record is shown. This deployment is also configured to run a protected, read-only
> diagnostic against an isolated test database; it returns sanitized aggregate results only, and no
> database records are d… *(truncated by the read, not by the product)*

Matches the recorded text. `mode: synthetic-only` on the wire is unchanged.

## 6. What this observation does NOT establish

- **It is not a QA pass for any image built from PR #248.** Nothing on this branch is deployed;
  hosted runs `main`. Every image from this session remains `HOSTED QA PENDING (Krish)`.
- **It says nothing about narrow widths, 200% zoom, or a real microphone.** This tooling cannot
  drive any of the three — `resize_window` reports success while the rendered viewport does not
  follow, and every driven tab reports `visibilityState: "hidden"`, so change-feed-driven updates
  never fire.
- **It is not authorization for anything.** Gate **G2** (per-record display) is still closed and
  still Dean's; gate **G3** (the five withheld aggregates) is still open and still Dean's — this
  observation confirms the withholding is *implemented*, not that the five may be restored.
- **No migration was applied and none may be.** `0003`, `0004` and `0005` remain unapplied to the
  hosted database, and applying one is the operator's act.
- **`limitations` carries 7 items** which were counted but not transcribed; a future reader should
  read them from the live route rather than from this file.

## 7. Re-derivation

```bash
git rev-parse main origin/main          # expect 2f9a1133… twice
git show main:apps/api/isaac_api/routes.py | grep -c '"mcp"'   # expect 0
```

In an already-authenticated browser tab, read-only:

```js
await fetch('/krish/api/health').then(r => r.json())
await fetch('/krish/api/runtime/database/recon').then(r => r.json())
// enumerate Object.keys(payload.dataset) — do NOT grep the serialized payload
```

---

## 8. Three honesty constraints, verified on the LIVE deployment

Each of these has a history in this repository of being asserted falsely and then corrected. All
three are now correct **on the deployed product**, not merely in source.

### 8.1 The upload claim is SCOPED, not app-wide

`Governance & Safety` (`/krish/governance`, 1,723 characters of copy) reads:

> Adding a file to this workspace is closed off entirely: every file upload is refused outright,
> whatever it contains, and **the refused request** is never read, parsed, or inspected.

The load-bearing words are *"the refused request"*. The 2026-08-03 product-hardening entry records
that this screen once asserted *"no file is read, parsed, or inspected"* while `RecordValidator` and
`CsvReconcilePanel` — one tab away — read and POST a chosen file. Measured on the live page:

| Probe | Result |
|---|---|
| unqualified `no file is read, parsed, or inspected` | **absent** |
| `refused before anything is read` | **absent** |
| any claim of real-vs-synthetic detection | **absent** |

The third matters as much as the first two: **no real-vs-synthetic detection exists anywhere in this
codebase**, and the R9 finding was that a prior revision implied it did. The live copy claims
synthetic *mode*, never synthetic *data*.

### 8.2 There is NO fake `Connected` state

`ai-integration-decision-packet.md` §6 binds the continued AI work with, above all, **no fake
`Connected` state**.

**MY FIRST MEASUREMENT OF THIS SAID "over the whole of `Settings & API`" AND HAD SEEN ONE TAB.**
That is corrected here rather than quietly widened, because the sentence described a method. The
probe read `document.body.innerText` with the **Overview** tab active — **2,575 characters** — and
Settings has **seven** tabs, one of which is literally *"Connect Your Agent"*. The conclusion
happened to be right; the stated scope was wrong by **18×**.

Re-measured by clicking through all seven and reading each rendered panel:

| Tab | `?tab=` | chars | `/\bconnected\b/i` |
|---|---|---:|---|
| Overview | `overview` | 2,575 | false |
| Data & Privacy | `privacy` | 10,378 | false |
| About | `about` | 1,341 | false |
| API Access | `api` | 3,918 | false |
| Endpoint Explorer | `explorer` | 10,622 | false |
| **Connect Your Agent** | `mcp` | **17,038** | **false** |
| Help & Tutorial | `help` | 2,004 | false |
| **total** | | **47,876** | **0 occurrences** |

**The word appears nowhere in 47,876 characters**, which is stronger than the guard requires: a
screen reading *"Not connected"* would still imply connecting is something this build attempts.

And the `Connect Your Agent` tab — the one place a fake state would actually live, and the largest
body of copy in Settings — **names the absence rather than omitting it**:

> No agent can connect to this deployment.

> There is no endpoint address to connect to and no configured way to authenticate a caller, so
> there is **no live connection for this page to report**, and nothing for it to revoke.

Its headings include `Requires organization configuration` and `No Agent Can Submit a Record`. That
is §6 honoured deliberately, not by accident of vocabulary.

**One incidental correction:** the tab parameter for that panel is `mcp`, not `agent` — my
`?tab=agent` guess loaded Settings with **Overview** still active and no error, which is its own
small lesson about deep links that silently fall back.

### 8.3 The no-model claim renders, and is true

> No language model at all — the assistant answers from a bounded in-repository catalog.

This is `ASSISTANT_NO_MODEL_CLAIM`'s substance, rendered rather than buried behind a tab — the gap
§11's 2026-08-25 note was added to close. It is true of this deployment: every provider seam answers
`501 no_provider_configured`.

## 9. QA-019 measured on FOUR hosted routes

`document.title` on the deployed product, read from the live DOM:

| Route | `document.title` | `<h1>` |
|---|---|---|
| `/krish/experiments` | `ISAAC Metadata Assistant` | My Experiments |
| `/krish/record/<ULID>` | `ISAAC Metadata Assistant` | Review Record |
| `/krish/governance` | `ISAAC Metadata Assistant` | Governance & Safety |
| `/krish/settings` | `ISAAC Metadata Assistant` | Settings & API |

**Four distinct routes, four distinct `<h1>`s, one identical title.** Each page knows what it is and
the title does not say. That is the WCAG 2.4.2 failure `QA-019` fixes, and it is now observed on the
deployed product rather than argued from source. The local dev tab in the same browser, running this
branch, reads `Review Export Readiness · ISAAC Metadata Assistant`.

**An exhaustive hosted title count was attempted and abandoned rather than estimated.** Driving the
nav links in one evaluation failed with *"Inspected target navigated or closed"* — those links are
real `<a href>`s causing full document loads, so the evaluation context dies with each one. Four
measured routes are reported; the full route set is covered by this branch's own suite locally, and
no hosted total is claimed.

## 10. UX-014's premise, confirmed verbatim on hosted

The record screen renders schema identifiers as product copy, exactly as `UX-014` describes. Read
from live `<h2>` and banner text (concatenated by `textContent`, so the identifier is a sibling
badge rather than part of the sentence):

- `System & Instrument` **`system`** `13 fields · none recorded yet`
- `Environment & Context` **`context`**  ← the *"Environment & Context context"* duplication the
  ledger row names
- `Reduced Spectrum` **`reduced_spectrum`**  ← in the confirmation banner

The banner's own copy is good and should be preserved by any `UX-014` work:

> 3 Fields Need Your Confirmation — These are values the system refuses to guess. Confirm each
> before this record can export — expected, not a failure.

The hosted record workspace nav shows `Record Fields`, `Runs`, **`Graph`** — `Graph` is still linked
on `main`; this branch's `EVG-002` removes that link while keeping the address reachable, which is
why `QA-018` had to scan it.

## 11. A NEW defect this observation found: there is no not-found state at all

Navigating to `https://isaac.slac.stanford.edu/krish/validator` — a plausible guess at the
Standalone Validator's address — landed on **My Experiments**, with `<h1>My Experiments</h1>` and
`location.pathname` rewritten to `/krish/experiments`. No message, no explanation.

The cause is one line, and `App.tsx` declares only two route patterns in total:

```tsx
<Route path="*" element={<Navigate to={ROUTES.experiments} replace />} />
```

**Every unknown path silently becomes My Experiments, and `replace` erases the attempted URL from
history**, so Back does not return the reader to wherever the bad link came from. There is no 404,
no not-found screen, and nothing that says the address was not understood.

**Why this is worth a row rather than a shrug.** A scientist following a stale link — a route
renamed between images, a URL copied from an older build, a typo in a shared address — is told
that their destination *is* My Experiments. The app makes a claim about the address it did not
honour, which is the same class as the honesty defects this programme keeps finding, arriving
through routing instead of copy.

**What it is NOT.** `/record/<unknown-ULID>` does **not** reach this branch: `/record/:id` matches,
and the record screen renders the API's own not-found handling. So the discarded-record case, which
is the one a reader is most likely to hit, is already handled correctly. This defect is confined to
genuinely unrecognised **paths**.

**Deliberately NOT fixed in PR #248, and the reason is scope rather than difficulty.** Eight test
files reference the catch-all or a not-found concept
(`navigation.test.tsx`, `proposal-deep-link.test.tsx`, `record-identity.test.ts`,
`tutorial-anchors.test.tsx`, `memory-sources.test.tsx`, `assistant-capabilities.test.tsx`,
`evidence-selection-state-affordance.test.tsx`, `palette-contrast.test.ts`), so replacing the
redirect with a not-found screen is a behaviour change with a real blast radius. Bundling it into a
93-commit PR whose CI is already green would risk the whole merge to add one screen. It is filed as
`QA-020` with this measurement attached.

**One measurement a follow-up must make first, because I did not:** whether any *shipped* link,
redirect or documented URL currently depends on the catch-all to land somewhere sensible. If one
does, a not-found screen would surface a defect rather than fix one, and that link is the real bug.

### 11.1 The blast-radius figure in §11 was FALSE, and is corrected here

§11 above said **8 test files** reference the catch-all. **Re-measured against the behaviour rather
than the vocabulary: ZERO test files assert the router redirect.**

The 8 came from `grep -lE "catch-all|unknown route|not.found|NotFound"`. Every one of the four
actual matches is about something else entirely:

| Match | What it is actually about |
|---|---|
| `tutorial-anchors.test.tsx:151` | `stubFetchRoutes` rejecting an unknown **API** route |
| `record-identity.test.ts:537` | a **record list**'s "weaker not-found" |
| `assistant-capabilities.test.tsx:573` | the **assistant intent resolver**'s catch-all |
| `assistant-capabilities.test.tsx:579` | the same intent resolver |

Three unrelated domains, one shared vocabulary. **This is the same error as `MCP-002`'s false
negative earlier in this same session** — there a grep for an invented constant name reported a
built feature as missing; here a grep for a real word reported an unrelated feature as related.
*A grep for a word measures your guess about the vocabulary, not the behaviour.*

**And the precondition §11 demanded is now discharged, in the safe direction.** Over **175** shipped
non-test `.ts`/`.tsx` files:

| Probe | Result |
|---|---|
| literal `to=`/`href=` targets outside the ten legitimate routes | **0** |
| template-literal `` to={`/…`} `` targets | **0** |

All navigation goes through `ROUTES` and its path helpers, so every shipped destination is
legitimate by construction and **nothing relies on the catch-all**. A not-found screen therefore
fixes a defect rather than surfacing one.

**Revised assessment: small and low-risk** — and still deliberately not in PR #248, but now for a
different and better reason. A not-found screen is a **new surface**, and `QA-018` is this session's
lesson that a new surface needs its own accessibility scan before it ships. It should get that in
its own reviewable PR, not appended to a 94-commit one.

The ten legitimate routes, for the record: `/experiments`, `/load`, `/memory`, `/governance`,
`/statistics`, `/settings`, `/record/:id`, and `/record/:id/{complete,evidence,export}`. **There is
no `/validator` route** — the Standalone Validator is not addressable, so the URL that exposed this
defect was my own wrong guess rather than a broken shipped link.
