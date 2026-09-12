# ISAAC External Blockers, Vendor Capability Matrix, and Risk Register

**Status:** **APPROVED — IMPLEMENTATION AUTHORIZED 2026-09-12.** **Created:** 2026-09-12 · **Base:** `main` @ `2f9a1133`
**Parent:** [`2026-09-12-isaac-master-implementation-plan.md`](2026-09-12-isaac-master-implementation-plan.md)

---

> ## STATUS CHANGED 2026-09-12 — IMPLEMENTATION AUTHORIZED
> Krish approved moving from planning into implementation. The planning gate is **CLEARED**.
> Every external-owner, security, migration and data-governance boundary in this document is
> **UNCHANGED**. Decision statuses are reconciled in
> [`ISAAC_PRODUCT_DECISIONS.md`](ISAAC_PRODUCT_DECISIONS.md) — read that first where it disagrees
> with prose written before the gate cleared. Source: `2026-09-12-plan-review-and-revisions.md`.


## 1. External blocker matrix

Re-verified against the repository and the live hosted deployment this session, not carried
forward from prior notes. Where a status differs from `CLAUDE.md`, the difference is stated.

| Blocker | Owner | What it blocks | Evidence | App work continues? | Exact next action |
|---|---|---|---|---|---|
| **EXT-01 — no trusted authentication boundary.** The Service is a plain ClusterIP with no NetworkPolicy; any in-cluster pod can reach the app and forge forwarded identity headers. | **Dean / SLAC infra** | authoritative actor stamping; proposal **acceptance** (answers `409 human_actor_required` in every default deployment) | Dean reconfirmed 2026-08-12. **Hosted `submission.blockers` reads exactly `["no_attributable_actor"]`** (observed 2026-09-12) | **YES — all of it.** Fail closed; never trust a raw header | Dean's decision on the trusted-edge / Bearer-validation pattern he named as the portal precedent |
| **EXT-02 — the remote MCP endpoint is not mounted.** | **Dean / SLAC infra** (one environment variable) | **the entire Claude companion path** | `GET /krish/api/mcp` → **404**, and the body `{"detail":"Not Found"}` is **ISAAC's own string** at `spa.py:46-47` — so the request reached the app and ISAAC declined it. Gate: `app.py:313` → `ISAAC_MCP_DEPLOYMENT`, **unset by default**; `Dockerfile:64-67` does not set it | **YES** — every item in Phase E | set `ISAAC_MCP_DEPLOYMENT`, then confirm with the status-code table (§2). **Excluded already:** the Authentik-routing hypothesis, and an incomplete OAuth config (which would stop the container booting; health answered 200) |
| **EXT-03 — registering an organization-wide remote connector.** | **Claude organization Owner / Primary Owner — IDENTITY UNKNOWN. Do not assume this is Dean.** | an org-wide connector | vendor: **Owner-only on Team/Enterprise**; "Admin" is **not** documented as sufficient | YES | **identify the role-holder first.** Note: **Free/Pro/Max is self-service**, so a two-scientist pilot needs **no organization action at all** |
| **EXT-04 — D1–D9: model provider, credential, billing, egress, retention, data policy, transcription provider.** | **Dean — DEFERRED 2026-08-12**: *"leave AI integration as future work rather than increasing scope at this point"* | a **production** provider | his deferral | **YES** — implementation against deterministic fakes is separately owner-authorized | nothing to ask now. **Do not record any D-row as approved, narrowed, or closed** |
| **EXT-05 — may scientific speech/detail flow through the organization's Claude environment?** **NEW — created by this architecture.** | **institution + Dean** | Claude-mediated voice capture | the Claude-Voice architecture makes ISAAC's own ASR unnecessary but raises this instead | YES (typed capture is the honest fallback) | ask it explicitly and separately from EXT-04. **If the answer is no, BOTH voice architectures die** and typed capture is the product |
| **EXT-06 — G2, hosted per-record display** | Dean | showing real record content | **hosted `record_display: "closed"`**, observed 2026-09-12 | YES | unchanged: closed by default is correct |
| **EXT-07 — G3, the five withheld aggregates** | Dean | restoring them | withheld pending his answer | YES | do not restore any of the five without his answer |
| **EXT-08 — migration `0005`: approval, application, backfill, Stage-2b cutover** | Krish (approval) + operator (application) | authoritative run-projection cutover | **hosted `run_projection.last_pass.unavailable: 3`** — all three hosted experiments have an unreadable projection (observed 2026-09-12). `0003`/`0004` are **owner-approved 2026-08-17 and applied nowhere**; `0005` is **not approved** and its backfill has **never run anywhere** | YES | **zero migrations are required by this plan** — this blocker gates no proposed slice |
| **EXT-09 — six `system.configuration.*` classifications** | **Angel / domain owner** | exact Experiment-vs-Run mapping for those six paths | two question packets prepared (2026-08-25, -08-27), unanswered | YES | blocks nothing else. Those six plus `timestamps.created_utc` are the **7 paths no write route accepts** |
| **EXT-10 — a representative BL15-2 corpus + expert ground truth** | **Krish + Angel** | **Pillar 2's PARSERS and evaluation ONLY.** The BL15-2 pilot decision itself is **CLOSED** (DEC-13); the shell, source model, provenance, Review integration, parser interfaces, synthetic harness and the provider-neutral semantic contract (`HIST-003a`) all proceed **now** | **measured: zero `.mac`, zero `.xlsx`/`.xls` in the entire tree**; `examples/` is generated by `scripts/make_synthetic_examples.py` with fictional people and a fictional year-2099 session; `openpyxl` is not a dependency | **PARTIALLY** — the Import Session shell and review surface proceed; **no parser does** | **issue `HIST-000`, the data request, immediately.** It costs nothing and is the gate |
| **EXT-11 — authenticated hosted QA, true 200% zoom, real microphone, hosted narrow widths** | **Krish** | post-release human verification | **rollout is now verified** (hosted `commit` = `2f9a1133`) — that is the **rollout, not the QA**. No CDP method can drive true zoom; `resize_window` reports success while the rendered viewport does not follow | YES | run `docs/krish-manual-verification-checklist.md`. **An agent must never claim these as automated** |
| **EXT-12 — personal deployment retirement (Vercel + Railway)** | Krish | removing stale unauthenticated demos | both still live and public; **Railway has a persistent volume, so deleting destroys what pausing preserves** | YES | disable, do not delete |

> **The scheduling conclusion: every Phase A–E task proceeds while every one of EXT-01 … EXT-12
> stays shut.** Only Phase F (the demonstration) and Phase G's parsers wait on other people.

---

## 2. The operator preflight for EXT-02

Hand this to whoever sets the variable. Mounted-vs-unmounted is decidable by status code alone:

| `GET <base>/api/mcp` | Meaning |
|---|---|
| **404** | **unmounted** ← observed 2026-09-12 |
| 405 | mounted; wrong method (expected healthy answer) |
| 403 | mounted; `local-loopback` mode with a remote peer |
| 401 | mounted; OAuth on, no token presented |

**What cannot be distinguished from outside:** *unset* vs *set to a fail-closed value* — both give
404. That ambiguity is itself an app-side gap (`MCP-003`): **MCP is the only seam that says nothing
about itself on the wire**, which is why the cause is unresolvable from outside *by construction*.

**The trap that would produce a 100%-failing deployment that looks correct from both ends:**
RFC 8707 permits an authorization server to *map* the audience; **ISAAC's `aud` check is exact**. So
the preflight must prove the token's `aud` matches **character-for-character**, not merely that a
token was issued.

---

## 3. Vendor capability matrix

Verified against official Anthropic documentation on **2026-09-12**. Nothing here comes from memory,
a blog, or a secondary source. **Every account-specific fact is UNKNOWN and is Krish's, not an
agent's** — no account, session, or admin surface was inspected.

| Capability | GA / conditions | Limitation | ISAAC implication | SLAC-specific |
|---|---|---|---|---|
| Custom **remote** MCP connector | **Yes** | — | the architecture is supported in principle | — |
| Which plans can add one | **Owner-only on Team/Enterprise; self-service on Free/Pro/Max** | "Admin" is **not** documented as sufficient | **a two-scientist pilot needs no organization action** — this is the cheapest first demo | **UNKNOWN** which plan SLAC holds |
| Who may register org-wide | **Owner / Primary Owner** | — | **identify the role-holder before asking anyone** | **UNKNOWN — do not assume Dean** |
| Authentication | OAuth **and** auth type **`none`**, documented **"Supported"** | — | The vendor fact is true and stays on the record. ~~So OAuth is ISAAC's choice, not a vendor gate — a stronger, cheaper argument to Dean.~~ **REJECTED BY THE OWNER 2026-09-12 (DEC-23).** Vendor permission is **not** a reason to drop authentication: **trusted attribution is load-bearing**, so production ISAAC rejects authless MCP for real SLAC scientific data. Authless is permitted **only** for explicitly approved local/synthetic/non-sensitive smoke testing (`MCP-019`). **And the identity point holds either way:** an OAuth bearer yields a `ServicePrincipal`, so **EXT-01 survives EXT-02** | — |
| Machine-to-machine | **No** — *"Every connection requires user consent"* | no unattended agent access | **matches ISAAC's invariants rather than fighting them** | — |
| Public reachability | **Required** — Claude connects *"from Anthropic's cloud infrastructure, rather than from your local device"*; the server must be reachable from **`160.79.104.0/21`** | **the authorization server must be allowlisted too** — the vendor names this as a common failure | two allowlist asks for Dean, not one | — |
| Custom connector + **Voice mode** | **UNKNOWN — NOT VERIFIABLE FROM OFFICIAL DOCS** | the voice article's tool sentence names only **pre-built** connectors; **"custom" never appears** in it, and **"voice" appears in none** of twelve connector/admin/skills documents | **do not architect on it.** Build the **text-chat** path first — it exercises the identical MCP contract | **UNKNOWN.** One observation by Krish settles it |
| Platform availability for custom connectors | *"Claude, Cowork, and Claude Desktop"* | **mobile is absent from that sentence** | the phone story stacks **two** unverified capabilities; a prior internal audit's "central scenario" conclusion is **contradicted** | **UNKNOWN** |
| Per-tool admin enforcement | **Enterprise** | — | an administrator could ship ISAAC **read-only** — worth knowing before proposing write scopes | **UNKNOWN** |
| Tool-result size ceiling | ≈ **150,000 characters** | — | ISAAC's unbounded reads exceed it by **≈50×** at 1,000 runs → `MCP-002` is a **compatibility** fix, not an optimization | — |
| Retry behaviour on tool-call failure | **UNKNOWN — no vendor guidance exists at all** | — | **`MCP-001`'s idempotency key is therefore not optional** | — |
| Google Drive / Docs / Sheets connectors alongside a custom connector | **Not established here** | — | Pillar 2's Google path stays **Option A/C** (reference-first / ephemeral parse) until verified | **UNKNOWN** |
| Data handling / retention for scientific content | **not an ISAAC decision** | — | **EXT-05.** Distinct from EXT-04 and must be asked separately | **UNKNOWN** |

---

## 4. Risk register

Likelihood × impact on a 1–5 scale. "Required verification" is what must be **proved**, not
promised.

### Scientific-integrity risks — the ones that would make the product harmful

| Risk | L | I | Mitigation | Required verification |
|---|:-:|:-:|---|---|
| **Silent ambiguity collapse** — a model or a regex picks one of two candidates | **5 (currently occurring)** | **5** | `CAP-001` (`search`→`finditer`), then persist the grouping and the `unresolved` state | **Reproduced and now fixed**: one-sentence "425 … maybe 430" must yield **two** candidates, neither preferred. A **negative control proving the old behaviour red** is mandatory — an inert fix passes any test written after it |
| **LLM hallucination / fabricated scientific value** | 4 | **5** | model output is **proposed**, never accepted; no model output in the truth path; `_refuse_a_confidence` rejects scores at any depth | **fabricated-value rate** is the headline import metric, not fields-filled. Mutation tests that reintroduce the exact defect and prove red |
| **False confident historical mapping** | 4 | **5** | every candidate source-linked and reviewable; the scientist decides | precision **and recall** against expert ground truth, per source type. **Requires EXT-10** |
| **Invented range semantics** — encoding "425 maybe 430" as `bounds:[425,430]` | 3 | **5** | the schema's only uncertainty path is descriptor-only (`$.descriptors.outputs[].descriptors[].uncertainty`); ambiguity stays assistant-side and resolves to one value before export | a test asserting no candidate set ever reaches an official record |
| **Missing provenance** | 3 | 4 | `CAP-006`; `EVG-001` **before** `EVG-002` | a test that every accepted value resolves to a source; the provenance read-out exists **before** the graph is cut |
| **Removing provenance to simplify the UI** | **4** | **5** | `EVG-001` is a hard prerequisite of `EVG-002` — `/provenance` ~~loses its only frontend caller~~ — **CORRECTED 2026-09-12 by first-hand measurement:** the caller is `screens/EvidenceExplorer.tsx:709`, not the graph (which receives provenance as a *prop*, `EvidenceGraphPanel.tsx:398`), and provenance is **already rendered outside the graph** as an origin+review chip pair at `EvidenceTrailPanel.tsx:163-175`, computed client-side by `lib/provenance.ts`. The residual prerequisite is narrower: only the multi-hop **`derived_from` chain** may be unrendered. See `ISAAC_EXECUTION_LEDGER.md` EVG-001 otherwise | PR ordering enforced; `derived_from` chains visibly reachable without the graph |
| **Incorrect run reconstruction / wrong experiment grouping** | 4 | 4 | candidates only; merge/split/reject under review; nothing authoritative automatically | run-segmentation accuracy vs ground truth. **Requires EXT-10** |
| **AI / validator conflation** | 3 | **5** | advisory can never flip PASS→FAIL; `schema_ok` stays visible; exactness findings never reported as schema errors | `validator-exactness` guard family extended to the new presentation |

### Security, privacy and governance

| Risk | L | I | Mitigation | Required verification |
|---|:-:|:-:|---|---|
| **Incorrect user identity** | **5 (structural today)** | **5** | fail closed; acceptance answers `409 human_actor_required`; client identity never authoritative; **note an OAuth bearer yields a `ServicePrincipal`, so EXT-02 does not close EXT-01** | no stamp is ever minted without `trust_basis == verified_edge_assertion` |
| **Scientific data egress to an unapproved provider** | 3 | **5** | every provider answers `501`; `any_provider_configured: false` hosted; no outbound model call exists | the five capture-surface disclosure claims stay pinned, and **polarity-tested** |
| **Raw-source retention beyond approval** | 3 | 4 | `DEC-12`: Option A reference-first, Option C ephemeral; **Option D ruled out for real data** | no durable bytes; `assets[]` stays pointer-only (`"NO BYTES, EVER"`) |
| **Duplicate MCP operations** | **4** | 4 | `MCP-001`'s `client_request_key` | vendor retry behaviour is **UNKNOWN**, so this must be proved by test, not assumed |
| **Permission drift** | 2 | 4 | no ACL is built; folders are a **label, never a permission boundary** | a test asserts folders grant and deny nothing |
| **"Immutable" history that is not immutable at the database level** | 3 | 4 | the five append-only tables are enforced by **one source-parsing test and nothing else** (a trigger needs dollar-quoting, refused by `split_statements`; `REVOKE` is a forbidden verb) | **never describe those rows as database-immutable.** Documentation fix in the first docs PR |

### Data-model and concurrency

| Risk | L | I | Mitigation | Required verification |
|---|:-:|:-:|---|---|
| **A new state key silently not persisted** | **4** | 4 | `save_versioned()` returns `False` **writing nothing** when `_authoritative_signature` is unchanged, and `from_state` drops unknown keys | `folder` must be a real dataclass field **and** join the signature; a test proves a move survives a round-trip |
| **A folder move changing scientific meaning** | 2 | **5** | folder is organizational only | a test proves no metadata, identity, run value or validation result changes, and `content_signature` does **not** move |
| **Stale CAS / ETag invalidation surprise** | 3 | 3 | a move bumps `rev` as `title` already does | state it in the PR; assert the ETag transition |
| **Revision corruption / the rename trap** | 3 | 4 | reinterpret "edit submitted work" as "keep editing, then submit again" (migration-free) | surface the trap rather than hide it: **a rename does not move `content_signature`, so submit → rename → resubmit yields `409 already_submitted`** |
| **Migration uncertainty** | 2 | 4 | **zero migrations in the proposed sequence — by design** | any slice discovering it needs one **stops and reports**: new §15 sentence + owner-approved packet + operator action |
| **Change-feed loss** | 3 | 3 | `(changed_at_rev, kind, entity_id)` key; `CURSOR_VERSION` 2; a v1 cursor is **refused (422)**, never misread | at-least-once delivery incl. duplicate-page redelivery |
| **Large imports / giant spreadsheets / malformed `.mac` / unusual encodings** | 3 | 3 | bounded reads; fail-closed parsers; a malformed **persisted** value is **read, not refused** (the reader did nothing wrong) | a malformed source refuses at the request boundary with a typed error; a malformed persisted value never blanks a screen |

### Process and product risks

| Risk | L | I | Mitigation | Required verification |
|---|:-:|:-:|---|---|
| **The UI re-complexifies** | **4** | 3 | tokens before components; one primary action per surface; a destination census as an acceptance criterion | a ratchet on the destination count and on raw type/spacing literals |
| **Hidden dependencies behind "gimmick" UI** | **4** | 4 | dependency analysis **before** any removal; this already found one (`/provenance`'s only caller) and one non-delete (`assistant.css` shared with `GuidedPrompt`; six lib modules with non-Assistant consumers) | every removal PR names what loses a consumer |
| **Over-parallelized implementation** | 3 | 3 | **five sub-agents total, not concurrent; nested spawning forbidden** | excessive parallelism once drove load average ≈326 and produced hundreds of false timeouts. Concurrency is a ceiling, not a target |
| **Stale ledger** | **4** | 4 | update the SESSION HEADER at every milestone and before any interruption | the continuation protocol requires correcting the header **before** doing anything else |
| **A green suite that proves nothing** | **5** | 4 | mutation-test every honesty fix; assert **polarity** | this repository has shipped an **inverted** disclosure guard, a docstring claiming an assertion the body did not make, and a guard comparing against zero instead of the value its message named |
| **Merging a stale-base PR** | **4** | 3 | re-run `tsc -b` **and** the suite on the **merge result** | exact-head-green protects the HEAD, not the MERGE — this produced two `main`-red counterexamples nine minutes apart |
| **Claiming a human gate was automated** | 3 | **5** | true 200% zoom, narrow widths and a real microphone are **not automatable by this tooling** | the honest status is always `PENDING (Krish)` with an exact checklist |

---

## 5. Verification strategy, per risk class

Every number here was measured in the **main checkout** this session, with exit codes captured to a
file rather than read through a pipe.

### 5.1 The baseline any future slice is measured against

| Suite | Command | Result |
|---|---|---|
| Backend | `.venv/bin/pytest -q -rs` | **7203 passed, 45 skipped, exit 0** (563.52 s) |
| Frontend | `npx vitest run` | **206 files / 5465 tests, exit 0** |
| Types | `npx tsc -b` | **exit 0** |
| Playwright read-only | `--list` (**listed, not run**) | 1600 tests / 20 files |
| Playwright mutation | `--list` | 121 / 15 |
| Playwright **trusted** | `--list` | 8 / 3 |
| Playwright bench | `--list` | 7 / 7 |
| Snapshot + deep graph | `build_memory_snapshot.py … --check` with **both** `--out` and `--detail-out` | **exit 0, no drift on either artifact** |

**The 45 skips are fully classified and sum exactly to 45**, which matters because an unclassified
skip total is a coverage claim nobody has checked:

| Count | Reason | Is it a coverage hole? |
|---:|---|---|
| 34 | gated on `ISAAC_RUN_REAL_ENGINE_PARITY` | **No** — CI's `postgres-migration` job also sets `ISAAC_REQUIRE_REAL_ENGINE_PARITY`, so an absent engine **fails** rather than skips |
| 1 | the `REQUIRE` variant | No, same mechanism |
| 4 | "strict reader tolerates a malformed persisted value" | No — deliberate, covered by unconditional siblings |
| 2 | `psycopg2` genuinely absent | No |
| 3 | opt-in perf benchmarks (`ISAAC_PERF_BENCH=1`) | No |

**Quote the checkout with every skip count.** A count taken in a git *worktree* is `+2` against
this one, because `graphify-out/graph.json` is gitignored and exactly two tests gate on its
presence.

### 5.2 Which suite proves what — and what none of them proves

| Risk class | Required proof | Suite |
|---|---|---|
| UI redesign | tokens declared+referenced; type-scale asserted; per-workspace `h1`; destination-count ratchet | `vitest`, `tsc -b`, `browser-a11y` |
| **Honesty claims** | **polarity-tested** guards — the guard must fail on the false version | the 11-file honesty harness (§5.3) |
| Folders / data model | a move changes no metadata, identity, run value or validation result, and does not move `content_signature`; a state round-trip survives `save_versioned` | `pytest`, plus a real-PostgreSQL case in CI |
| MCP contract | idempotency under retry; bounded reads under the ~150 k ceiling; `aud` matched character-for-character | `pytest`, `test_mcp_transport.py`, the operator preflight |
| Historical parsers | precision/recall **and fabricated-value rate** against expert ground truth | new harness — **requires EXT-10** |
| Ambiguity model | one sentence, two candidates, neither preferred, explicitly unresolved — **with a negative control proving the old behaviour red** | `pytest` + `vitest` |
| Validator presentation | `schema_ok` visible; exactness in its own list; advisory cannot flip PASS→FAIL | `validator-exactness` family |
| Proposal acceptance end-to-end | the **two-actor** walk | **`playwright.trusted.config.ts` ONLY** — it runs under `ISAAC_EDGE_TRUST_VERIFIER=test_fixture`, and **no shipped deployment sets that variable**. A green read-only or mutation run has **not** exercised acceptance at all |

**What no suite in this repository proves:** behaviour against the hosted database with its real
data, roles and grants; true 200% browser zoom; hosted narrow widths; a real microphone and its OS
indicator. The first is the operator's; the other three are human gates this tooling **provably
cannot drive**.

### 5.3 The honesty-guard harness a redesign must not break

Eleven files. This is the regression harness that exists because each defect shipped once.

`upload-claim-parity` · `reset-claim-parity` · `discard-claim-parity` ·
`assistant-model-claim-parity` · `unanswerable-pending-entry-honesty` · `memory-honesty` ·
`help-and-honesty` · `validator-exactness` · `source-is-greppable` · `interaction-states` (P22C) ·
`palette-contrast` (the phantom-property ratchet, **now unconditional** as of `b3ab5c80`) — plus
`test_no_developer_paths_are_tracked` (tracked-symlink mode `120000`; its home-absolute-path half
was deliberately **withdrawn** as too noisy, and the withdrawal is recorded in the file).

**Any redesign PR that touches a claim site must extend the matching guard, not edit around it —
and must test polarity.** This project has shipped an *inverted* disclosure guard that passed, a
docstring claiming an assertion its body never made, and a guard comparing against zero instead of
the value its own message named.

### 5.4 Fail-closed boundaries confirmed in source

`POST /api/uploads` → unconditional **403** · acceptance without a trusted actor → **409
`human_actor_required`** · every provider → **501** · `db_write.WriteStatementPolicy` +
`OWNED_TABLES` + `_APPEND_ONLY_TABLES` · `runtime_mode` refuses `real` at boot · recon's frozen
allowlists project every block and **raise** on an unlisted key on the success path.

Gitignored and treated as sensitive: `graphify-out/`, `examples/*`, `.venv/` **and** bare `.venv`,
`node_modules/`, `design-handoff/`.

### 5.5 CI and release mechanics — what they prove and what they do not

`ci.yml` has exactly **four** jobs: `test`, `postgres-migration`, `frontend`, `browser-a11y`.

- **Zero macOS/darwin jobs exist anywhere.** So the darwin half of any accessibility baseline can
  never be judged by CI and must be **measured locally**, never carried forward. (A carried-forward
  darwin column has been wrong before, in 19 of 168 cells, and 15 of 20 recorded "platform splits"
  turned out to be a stale column rather than a platform difference.)
- **Zero `fetch-depth` overrides anywhere except `build-and-push`'s explicit `fetch-depth: 0`**, so
  every other checkout is shallow. That is why history-spanning assertions **degrade to
  `pytest.skip` in CI** while being enforced in a full clone. Their skip messages must say so
  rather than reading as a pass.
- The **release gate** is `workflow_run`-triggered, fork-safe
  (`head_repository.full_name == github.repository`), and checks out the gate script from the
  **trusted default branch, never the tree being judged**. `build-and-push` needs the gate, and the
  gate requires CI `success` for the **exact SHA**. It still pushes `:latest` — **H1 remains
  unfixed**.
- **The durable lesson, verified against real history:** *exact-head-green protects the HEAD, not
  the MERGE.* All four cited counterexample SHAs exist (`2b8a017`, `1ef0c0d`, `7e29e81`,
  `da88c63`): two merges turned `main` red because each PR was green against a base that had moved,
  and only the release gate stopped a broken image from shipping. **Before merging a PR whose base
  has moved, re-run `tsc -b` and the suite on the MERGE RESULT.**

### 5.6 Documentation staleness found while measuring

Each is a claim a future session would act on. All are docs-only; none is a blocker.

| Artifact | Stale claim | Measured truth |
|---|---|---|
| `CLAUDE.md` §11 | "the ~69 → **71** operations `test_about_and_openapi.py` pins" | the test asserts **77** (`:684`), and the live `/api/openapi` is **69 paths / 77 method-operations** |
| `CLAUDE.md` §11 | `A11Y_BASELINE_TOTAL_NODES` **871/871** | **877/877**, 70 cells, 2 platform splits, `DARWIN_CARRIED_FORWARD = []` |
| ~~`CLAUDE.md` §16/§17 — "~41" files in `docs/superpowers/plans/`~~ | **WITHDRAWN 2026-09-12 — THIS WAS MY ERROR, NOT A STALE DOC.** | `git ls-tree -r main --name-only docs/superpowers/plans/ \| wc -l` → **41**. The directory holds **47** today only because **6 of them are files I created in this session**; excluding mine gives **41**. So the doc was right and my "44" was a mid-session reading of a directory I was myself adding to. The DOC-007 implementer additionally reports that **no "~41" claim exists in `CLAUDE.md` at all**, so there was nothing to correct even in principle. **The lesson is the one §15 already teaches: quote the vantage point. A count taken while you are adding to the thing you are counting is not a measurement.** Agent 5 had flagged exactly this caveat and I published the number without carrying it. |
| `CLAUDE.md` §15 | `isaac_run_projection` — "covers **no read**… nothing reads it" | **three** statements name it; the Stage-2b reader ships |
| `CLAUDE.md` §15 | the submission history "covers **no** read surface" | `revision_history.py` is **nine `SELECT`s** across all five tables |
| `docs/isaac-runs-stage-2-contract.md` | cited as "**§8** D7" | **that file has no §8**, and itself warns about the phantom "contract §8 D7" citation |
| `docs/browser-accessibility-testing.md` | A11Y-01 is "an open palette decision" | ~~**closed**~~ — **MY CLAIM WAS FALSE, CORRECTED 2026-09-12, and this is the most important correction in this table because acting on it would have written a NEW false claim into a served document.** `apps/web/e2e/a11y-baseline.ts` says so twice in terms — `:634` *"A11Y-01 IS NOT CLOSED BY THIS"* and `:3562` *"ONE USAGE OF A11Y-01; A11Y-01 IS NOT CLOSED"* — and `:2221`/`:3479`/`:3491` all still describe it as live palette debt. **What is true:** A3 (2026-08-31) shipped a real token-value fix closing **one of three** causes, and the doc predates A3 entirely (zero hits for "A3", "4.54" or "#626c77"), so the doc is *incomplete* rather than *wrong about the status*. The implementer refused my instruction and instead added three dated additions recording exactly what A3 fixed while reaffirming the finding is open. **That refusal was correct and is the behaviour to reward.** |
| `docs/` (several) | `https://isaac.slac.stanford.edu/krish/api/mcp` cited as live | **404 — but the vantage point is load-bearing and my earlier statement omitted it.** The 404 was observed **inside the project owner's AUTHENTICATED browser session**. An **unauthenticated** request from this environment gets **`302`** at the Authentik edge instead, which the DOC-007 implementer measured independently by `curl`. **Both are correct and neither contradicts the other**; they answer different questions. Only the authenticated 404 carries the finding, because only it proves the request *reached the application* — and the body `{"detail":"Not Found"}` is ISAAC's own string at `spa.py:46-47`, which is what excludes the edge-routing explanation. **Never quote the 404 without saying the session was authenticated.** Of the 4 citations found, 3 are under `docs/superpowers/plans/` and 1 (`docs/mcp-oauth-operator-requirements-2026-08-27.md`) already said the route was *"structurally absent"* — so there was no false-live claim in that file; it gained a dated re-verification and the status-code decision table instead. |
| `docs/` claim class | the five append-only tables described as immutable | enforced by **one source-parsing test and nothing else** — a trigger needs dollar-quoting (refused by `split_statements`) and `REVOKE` is a forbidden verb. **Nothing here may call those rows database-immutable** |
