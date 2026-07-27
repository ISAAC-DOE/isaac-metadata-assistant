# Phase 36V — Closure

**Status:** COMPLETE at org canonical `main` **`85057e4`**.
**Plan:** `docs/superpowers/plans/2026-07-26-phase-36v-visual-clarity-settings-api.md`
**Scope:** frontend presentation · information architecture · responsive layout ·
accessibility · navigation · **OpenAPI documentation-metadata enrichment** (the one
authorized backend edit). Synthetic-only · deterministic · **no LLM added** · no portal ·
no real data · **no new dependency** · truth core untouched · **no Phase 37 work**.

---

## 1. Starting → ending state

| Axis | Start | End |
|---|---|---|
| HEAD | `f56f1ce` | **`85057e4`** |
| Image | `v0.0.20` | **`v0.0.23`** (3 publications) |
| Frontend tests | 1120 / 69 files | **1366 / 75 files** (+246) |
| Backend tests | 1029 | **1042** (+13) |
| OpenAPI consumer descriptions | **8 of 34** | **34 of 34** |
| OpenAPI tags | **0** | **14 registered** |
| `/api/openapi` leak scan | **did not exist** | **0/16, guard added** |
| Bundle JS | 500.98 kB | 534.13 kB |
| Bundle CSS | 145.47 kB | 158.85 kB |
| Hosted `/krish` | not readable here | **not readable here** |

Every merge was a **merge commit** (three parents each verified). No squash, no rebase, no
force-push, no manual tag, no direct push to `main`.

## 2. Slices → PRs

| PR | Scope | Merge | Image |
|---|---|---|---|
| [#19](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/19) | Assistant hierarchy · Open Validator · clear-context reset | `b80bf59` | `v0.0.21` |
| [#20](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/20) | Concepts clarity · Graph decluttering · humanized labels | `d577e3f` | `v0.0.22` |
| [#21](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/21) | Settings dedup · honest API keys · API docs · OpenAPI metadata | `85057e4` | `v0.0.23` |

Three PRs rather than seven, per the authorizing decision, to limit unverified rollouts.
Each: Opus implementation → **independent Opus review that implemented none of the work under
review** → every Critical and Important fixed → green CI (3 checks including a Docker
production-image smoke test) → merge commit → semver image.

## 3. What the reviews caught that 1366 green tests did not

Every review returned **DO NOT SHIP**. None returned SHIP unchanged. As in P36R, the
findings that mattered were **honesty defects that passed the whole suite**.

1. **Chips that inverted their own affordance (PR2, Critical).** The graph's active-filter
   chips enumerated the relation types still *shown* rather than those *hidden*. On the real
   five-relation payload, unticking one relation produced a trigger reading "Filters 1
   active" beside **four** chips whose accessible names — "Remove the Imports relationship
   filter" — named relations being **kept**, and whose activation **narrowed** the graph
   while every sibling control widened it. Invisible to the suite because both fixtures carry
   only one or two relation types, where the wording happens to read correctly. The
   orchestrator's own browser QA had exercised the cluster filter and missed it too.
   Fixed and verified on the real payload: 3 hidden → 3 chips → 399 → 479 → 515 → 516
   rendered edges as each is restored.
2. **An agent guide contradicting the contract on its own screen (PR3, Important).** Connect
   an Agent stated an unnamed request-body key "is dropped rather than interpreted".
   `DemoResetRequest` sets `extra="forbid"`, so `POST /api/demo/reset` **rejects it with
   422** — and that operation's own generated description, rendered two sections above on the
   same page, says "Any other field is rejected." Proven live by the reviewer.
3. **Prescribed copy weaker than what it replaced (PR1, Important).** The authorizing spec's
   advisory-footer sentence dropped the explicit **"It never validates"** claim — in the very
   slice that added an `Open Validator` button and a `Deterministic Schema Check` card to that
   panel. Clause restored and now guarded by a positive assertion. Same class as P36R's R9.
4. **One axis, two conflicting accessible names (PR1, Important).** Enabling the availability
   status on every mount reversed Phase-33 HQA #7 and left `GraphStatusChip` announcing
   "Project memory available — memory plane, advisory only, never a validator" beside a row
   announcing "Memory Available". It also destroyed a real capability: `availability` drives
   `classifyAnswer`, so a mount could no longer use the value while letting the page own the
   label.
5. **Focus dropped to `<body>` (PR2, Important).** A keyboard user activating a
   self-unmounting clear control was dumped to the top of the document — new, because the
   control was previously always mounted.

## 4. The near-miss worth recording

The authorizing prompt instructed that error responses including **422** be documented. In
FastAPI's `get_openapi_path`, the automatic `422` + `HTTPValidationError` entry is emitted
**only if the operation has params/body AND you have not declared 422 yourself**. Following
that instruction literally would have **silently stripped the validation-error schema from 33
operations** — a real contract regression inside a change authorized as documentation-only.

The implementing subagent detected it, declared 422 only on the one operation with no
params/body (hence no auto-422), and added
`test_operations_with_parameters_keep_the_validation_error_schema`. Independent review
confirmed by mutation that this is **the only test capable of catching it**: the response-code
*set* is unchanged, so a code-set assertion passes while the `$ref` disappears.

## 5. Reconciliations (recorded, never silent)

`N1` the edge provider is never named in client copy — the guard mirrors what the backend
withholds from `GET /api/about`; the substance is stated provider-neutrally · `N2` the API
base URL is **derived**, not the literal `/api` this plan first specified — under the deployed
base path the documented paths are `/krish/api/...`, so the literal would have shown every API
consumer a wrong base (verified in a `/krish` production build) · `N3` no accent edge on the
Assistant bubble — the no-vertical-rail rule is permanent and CI-enforced · `N4` Open Validator
is additive, not a repair; no such control existed, only reply prose · `N5` the prescribed
advisory-footer copy was weaker than what shipped, and was corrected · `N6` the availability
status is not restated where the page already owns it · `N7` relation types are humanized from
a closed five-value set with verbatim fallthrough; **cluster names are not renamed** because
the spec's own `cell_type → Cell Type` rule applied to the real 100+ open-ended values yields
**"She Work Function Ev"** from `SHE_work_function_eV` and "Test Export.py" — fabricating a
scientific label is what the no-guessing rule forbids · `N8` the legend's duplicate raw token
line was removed in favour of per-entry `title`.

## 6. Instruction-architecture fix

`CLAUDE.md` §17 described the served-content manifest as "200 files… `CLAUDE.md`, `AGENTS.md`,
every `docs/*.md`, and each `.claude/skills/*/SKILL.md`". Measured reality: **201 entries**
whose largest bucket is **64 `apps/web/src` files**, plus 36 `tests/**`, 15 `apps/api/**`, 15
`src/**`, 7 `docs/superpowers/**`. Three slices this phase independently hit "unexpected"
drift because ordinary frontend and test edits *do* cause it. §17 now states the real
composition and warns that concurrent slices must regenerate **once** after both settle.

## 7. Verification at closure

Backend **1042 passed** · frontend **1366 passed / 75 files** · `tsc -b` clean · production
build clean · snapshot regenerated in every commit touching a manifest-listed file, `--check`
reporting no drift · Docker production-image smoke test green on every PR · no `.only`, no
skipped tests · no secrets, absolute paths, or external URLs introduced · the API-keys surface
writes nothing to storage or cookies (asserted, mutation-verified).

Browser QA was performed against a **true production build served at `/krish`**
(`VITE_BASE_PATH=/krish/ VITE_API_BASE=/krish/api` + `ISAAC_STATIC_DIR`), not the dev server,
so base-path behaviour is covered by the same evidence.

## 8. Open — Krish's calls, not this phase's

1. **HOSTED AUTHENTICATED QA — every image `v0.0.13`…`v0.0.23` is unverified (11 images).**
   `https://isaac.slac.stanford.edu/krish/api/health` returns **http=000** from this
   environment — not a 401, so it is network-blocked rather than auth-blocked. **No rollout is
   claimed as verified.** After Flux rolls `v0.0.23`, that endpoint should report commit
   `85057e4`.
2. **Human visual sign-off — responsive and 200% zoom.** Not verifiable here: `resize_window`
   reports success while `window.innerWidth` stays pinned at 1054, confirmed by reading it.
   Open since Phase 33.
3. **Personal-deploy retirement** (Vercel `isaac-demo-web` + Railway) — dashboard action.

## 9. Deferred, with reasons

- **Real API-key management** remains unbuilt and the UI says so. It requires hashed secret
  storage, per-key identity, revocation, expiry and scopes — Phase 37, unauthorized.
- **`POST /api/uploads` still documents a `200` that never occurs.** Declaring
  `status_code=403` would be provably behaviour-neutral, but the authorization forbade
  status-code changes; the `response_description` says the outcome never occurs and the UI
  renders that honestly. Needs a one-line decision.
- **Documented status codes are pinned, not proven producible.** ~150 codes are asserted to
  match the generated document; reachability was spot-verified, not exhaustively proven.
- **The Sources tab's own relation chips** were humanized, but its remaining raw identifiers
  and the `Community`/`Cluster` terminology split (carried over from P36R) are untouched.
- **Graphify re-index** still not run — its concept extraction calls an external model, which
  this phase forbids. Already disclosed in-product.

## 10. Phase 37 boundary

**No Phase 37 work was performed.** Untouched: portal integration, Postgres or durable
persistence, real data, portal/personal API keys, external model provider, embeddings, vector
retrieval, identity/role enforcement, `isaac-k8`, new production secrets, and Vercel/Railway
deletion. Phase 37 remains **unauthorized**; readiness plan only.
