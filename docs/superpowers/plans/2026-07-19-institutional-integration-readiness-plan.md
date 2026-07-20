Status: PROPOSED — awaiting approval. No implementation authorized.
Date: 2026-07-19  ·  Baseline commit: f534a4c  ·  Author: Claude (planning)
Related: 2026-07-16-phases-23-26-arc-decisions.md; P24 specs (P24.9/P24.10 memory-plane); this doc EXTENDS the approved arc as a cross-cutting readiness assessment (it does not reorder or replace the 23→24→25→26 sequence).
Approval decisions required:
- Q1 Do we authorize an ISAAC-side "seam-introduction" phase at all (Protocols + default impls, zero behavior change), or keep this doc as pure assessment until an institution engages?
- Q2 Is durable multi-user persistence (identity + owner + real store) IN SCOPE for ISAAC, or does ISAAC only expose the seams and the institution supplies every backing store?
- Q3 Confirm the governance walls (uploads-403, 2-fixture source allowlist, synthetic-only) stay CLOSED by default even after seams exist — i.e. seams are dormant until an institution explicitly enables them.
- Q4 Confirm the ordering constraint: none of these seams may precede or entangle P25 (Grounded Assistant) / P26 (Real Search) unless the user re-prioritises.
- Q5 Sign off that the truth core (`src/isaac_records/`, `schema/`) is OFF-LIMITS to every slice here.

# Institutional Integration Readiness Plan

## Thesis

Target: **the product is functional with synthetic/demo providers, and an institutional team mainly REPLACES or CONFIGURES provider seams rather than rewriting the application.**

This is a READINESS ASSESSMENT + interface-recommendation plan. It does **not** implement institutional infrastructure and does **not** modify `apps/`, `src/`, or `schema/`. It (a) inventories every provider/repository boundary, (b) marks each as *seam already exists* vs *seam must be introduced first*, (c) sketches the recommended Protocol/abstraction, and (d) proposes small, independently-reviewable ISAAC-side "introduce-the-seam" slices that would make the boundary configurable/replaceable while keeping today's behavior byte-identical by default.

**Invariant preserved throughout:** institutional infrastructure may STORE and TRANSPORT data, but the Python truth core (`src/isaac_records/*`, `schema/isaac_record_v1.json`) remains AUTHORITATIVE for schema validation, evidence audit, completion rules, and export eligibility. No seam introduced here may compute, cache, or override a verdict. This is already test-enforced in both directions (`tests/test_export.py:169` truth→no-graphify; `apps/api/tests/test_memory.py:813` memory→stdlib-only) and those tests must keep passing.

## Legend — seam states

- **CLEAN SEAM** — Protocol/abstraction + env-override already present; institution swaps an implementation. No ISAAC refactor required.
- **PARTIAL** — an env hook or a single insertion point exists, but no abstraction; ISAAC must introduce the interface first.
- **GREENFIELD** — no concept in the codebase at all; ISAAC must introduce both a model and an interface first.
- **GOVERNANCE-GATED** — a deliberate closed wall; a seam may be introduced behind it but stays disabled until explicit approval.

## Seam-state summary (quick reference)

| # | Area | State | Introduce-the-seam slice? |
|---|---|---|---|
| 1 | Identity / authentication | PARTIAL (ASGI middleware swap point) | Slice S2 |
| 2 | Users / organizations | GREENFIELD | Slice S3 |
| 3 | Authorization / roles | GREENFIELD | Slice S4 |
| 4 | Experiment persistence | PARTIAL (baked-in file I/O) | **Slice S1 (foundational)** |
| 5 | Draft persistence | PARTIAL (rides on #4) | Folded into S1 |
| 6 | Evidence metadata | PARTIAL (sidecar files) | Folded into S1 (+ note) |
| 7 | Approved file/object storage | GOVERNANCE-GATED (uploads-403) | Slice S6 (dormant) |
| 8 | Project Memory provider | **CLEAN SEAM** | None — document only (S9) |
| 9 | Search provider | GREENFIELD (deferred to P26) | None here — cross-ref P26 |
| 10 | Background-job provider | GREENFIELD (not yet needed) | Slice S8 (deferred) |
| 11 | Notifications | GREENFIELD (not yet needed) | Slice S7 (deferred) |
| 12 | Audit / history storage | PARTIAL (per-experiment answer_log) | Slice S5 |
| 13 | Deployment secrets / config | CLEAN SEAM (env-var discipline) | Document + validate (S9) |

---

# Part A — Per-Area Provider Boundary Assessment

Each area states: current implementation (cited) · existing seam · missing seam · recommended interface · what the institution must provide · what ISAAC must continue to own · migration risks · test strategy.

## A1. Identity / Authentication — PARTIAL

- **Current impl:** single shared-secret bearer token. `apps/api/isaac_api/auth.py::ApiKeyAuthMiddleware` (auth.py:24-52) compares `Authorization: Bearer <ISAAC_UI_API_KEY>` constant-time (`secrets.compare_digest`); disabled entirely when the env var is unset (auth.py:29-31). Wired app-wide at `app.py:44`, before CORS. Open paths: `GET /api/health` + `OPTIONS` only (auth.py:21).
- **Existing seam:** the ASGI middleware slot is a clean *insertion point* — any middleware can replace it. Env-toggle is clean.
- **Missing seam:** no per-request principal, no token issuance/verification against an IdP, no session, no logout. Auth is binary (valid key = full access).
- **Recommended interface:** introduce an `AuthProvider` that resolves a request to a `RequestPrincipal`, and stash the principal on `request.state` for routes/authorizer to read.
  ```python
  @dataclass(frozen=True)
  class RequestPrincipal:
      subject: str            # stable id; "local" for the default single-principal mode
      display_name: str | None
      org_id: str | None
      roles: frozenset[str]   # empty in default mode
      is_authenticated: bool
  class AuthProvider(Protocol):
      def authenticate(self, headers: Mapping[str, str]) -> RequestPrincipal | None: ...
  ```
  Default impl = today's shared-secret provider returning a fixed `local` principal (behavior identical).
- **Institution provides:** an OIDC/SAML/institutional-SSO `AuthProvider` impl (token verification, claims→principal mapping, key rotation), plus the IdP itself.
- **ISAAC continues to own:** the middleware wiring, the open-path list, the never-leak-verdict contract, and the rule that auth never influences a validation/export verdict — it only gates transport.
- **Migration risks:** turning on a real IdP without first threading a principal breaks the "one shared key" assumption silently; CORS-before-auth ordering must be preserved so 401s keep CORS headers (app.py:42-43).
- **Test strategy:** keep `test_deploy_config.py` + `test_memory_api.py:606-614` green; add a fake `AuthProvider` in tests asserting principal propagation and that default mode still equals shared-secret behavior.

## A2. Users / Organizations — GREENFIELD

- **Current impl:** none. No user, org, or tenant anywhere. `Experiment` has no owner field (workspace.py:80-89). Hosted deployment shares ONE workspace and auto-seeds a single demo experiment (workspace.py:229-232).
- **Existing seam:** none.
- **Missing seam:** a user/org/tenant model + membership + the association of experiments to an owner/org.
- **Recommended interface:** do NOT build a user table in ISAAC. Treat identity as external (A1's `RequestPrincipal.subject`/`org_id`). Introduce only the *linkage*: an optional, defaulted `owner_subject`/`org_id` on the experiment record, populated from the principal at create time.
  ```python
  # additive, defaulted — no migration for existing single-user data
  owner_subject: str = "local"
  org_id: str | None = None
  ```
- **Institution provides:** the authoritative user/org directory (via IdP claims), membership semantics, provisioning/deprovisioning.
- **ISAAC continues to own:** storing the owner/org *tag* on its own records and scoping list/read queries by it; ISAAC does not become a user-management system.
- **Migration risks:** existing single-workspace data has no owner — default `"local"` must be back-compatible; multi-tenant listing must not leak across orgs once populated.
- **Test strategy:** fixtures with 2 principals in 2 orgs; assert list/read isolation once owner-scoping is enabled; assert default single-principal mode is unchanged.

## A3. Authorization / Roles — GREENFIELD

- **Current impl:** none. Authorization is binary (valid token → full access). No roles, no per-resource checks; no `Depends(...)` auth in routes.py.
- **Existing seam:** none (the auth middleware is authentication, not authorization).
- **Missing seam:** a policy decision point invoked per resource/action, and a role model.
- **Recommended interface:** a single `Authorizer` Protocol consulted at route entry, defaulting to allow-all (matches today).
  ```python
  class Authorizer(Protocol):
      def can(self, principal: RequestPrincipal, action: str,
              resource: ResourceRef) -> bool: ...
  # default AllowAllAuthorizer().can(...) -> True  (byte-identical to today)
  ```
  `action` examples: `experiment.read|write|export|audit`. Callsites are a thin decorator/guard, NOT logic inside the truth core.
- **Institution provides:** a role/ABAC policy impl mapping principal+org+roles → decisions; the role definitions.
- **ISAAC continues to own:** where authorization is checked (the callsite map), and the guarantee that a *denied* action returns 403 transport-level and never mutates truth. Authorization NEVER changes a schema/audit/export verdict — a denied export is a transport refusal, not an "invalid record".
- **Migration risks:** default must stay allow-all or hosted demo breaks; adding checks must be exhaustive (a missed callsite = silent bypass) — enumerate every mutating route.
- **Test strategy:** deny-matrix tests with a fake `Authorizer`; a coverage test asserting every mutating route consults the authorizer; assert default allow-all path unchanged.

## A4. Experiment Persistence — PARTIAL (the main seam to introduce)

- **Current impl:** flat JSON on local disk. `apps/api/isaac_api/workspace.py` `Experiment` dataclass (workspace.py:80-184) has `save()`/`from_state()` with file I/O baked in; `list_experiments()`/`load_experiment()` (workspace.py:235-250) read JSON off disk each call — no cache, no index, no concurrency control. Root = `ISAAC_UI_WORKSPACE` (default `/tmp/isaac-ui-workspace`, workspace.py:54-65). Status is DERIVED on read (workspace.py:167-184). CLI writes `records/<ULID>.json` via `cli.py::cmd_export` (cli.py:61-89), immutability-guarded (cli.py:78-80).
- **Existing seam:** partial — env-overridable root; a small store-op surface (`create/list/load`). But model + I/O are fused; JSON-file shape is assumed at every callsite.
- **Missing seam:** a repository interface so the backing store is swappable without touching callsites — the analogue of the memory plane's `MemoryReader`.
- **Recommended interface:** an `ExperimentStore` Protocol; the `Experiment` dataclass becomes a pure data model (no I/O); the filesystem impl becomes the default `FilesystemExperimentStore`.
  ```python
  class ExperimentStore(Protocol):
      def create(self, exp: ExperimentState, *, owner: RequestPrincipal) -> str: ...
      def load(self, exp_id: str) -> ExperimentState | None: ...
      def list(self, *, owner: RequestPrincipal | None = None) -> list[ExperimentSummary]: ...
      def save(self, exp: ExperimentState) -> None: ...
      def ensure_seeded(self) -> None: ...
  def get_default_store() -> ExperimentStore: ...  # precedence like get_default_reader()
  ```
- **Institution provides:** a durable `ExperimentStore` impl (Postgres/S3/managed), backups, concurrency control, and a non-ephemeral volume — the current `/tmp` default is wiped on Railway restart.
- **ISAAC continues to own:** the `ExperimentState` shape, status-derivation logic, the immutability guard, seeding policy, and the guarantee that persistence stores serialized truth-core output but never re-derives validity. Records exported through `cli.py`/`export.py` remain schema-gated by the truth core regardless of store.
- **Migration risks:** highest-blast-radius refactor here; every route touching the workspace must go through the store. Ephemeral→durable changes seeding semantics (a real store should NOT auto-seed a demo per tenant). Concurrency: two writers to one experiment.json today would race — a DB impl must define locking.
- **Test strategy:** an in-memory `ExperimentStore` fake for route tests; a contract test-suite run against BOTH filesystem-default and fake to prove interchangeability; assert default filesystem behavior (paths, seeding, status derivation, immutability 409) is byte-identical post-refactor.

## A5. Draft Persistence — PARTIAL (rides on A4)

- **Current impl:** the draft is an inline dict inside `experiment.json` (workspace.py:113-122); answers append to `answer_log` (workspace.py:87; routes.py:169,:284).
- **Existing seam:** same store as the experiment; no separate seam.
- **Missing seam:** none beyond A4 — drafts should ride the `ExperimentStore` rather than get their own store (avoids split-brain between an experiment and its draft).
- **Recommended interface:** keep drafts inside `ExperimentState`; no separate Protocol. If an institution needs draft autosave/versioning, add optional `draft_revisions` to the state, still stored via `ExperimentStore`.
- **Institution provides:** nothing beyond A4's store.
- **ISAAC continues to own:** the draft envelope shape (`{value, unit?, status, evidence[]}`, `src/isaac_records/models.py`) and the no-guessing rules (`draft_validator.py`) — draft validity is truth-core, never storage.
- **Migration risks:** splitting drafts into a separate store risks transactional inconsistency with the experiment; keep them together.
- **Test strategy:** covered by A4 contract suite; add a draft round-trip test through the store fake.

## A6. Evidence Metadata — PARTIAL

- **Current impl:** two paths. (a) Live draft: evidence embedded in the draft envelope. (b) Exported: `<id>.evidence.json` sidecar written next to the record (routes.py:294-301; `export.py::build_sidecar` export.py:107-135). Read back via `/artifacts` + `/evidence` (routes.py:438-514).
- **Existing seam:** partial — the sidecar *format* is stable and documented (CLAUDE.md §4), but storage is local files keyed by record id.
- **Missing seam:** a durable evidence store; today it is local FS only. The sidecar format itself is portable and does not need changing.
- **Recommended interface:** evidence artifacts ride the same `ExperimentStore`/records storage as their record (co-located, same durability guarantee). Expose read via a narrow `evidence_for(record_id)` on the store rather than a new provider.
- **Institution provides:** durable co-located storage for record + sidecar bytes; nothing format-related.
- **ISAAC continues to own:** the sidecar SCHEMA and generation (`export.py::build_sidecar`), the JSON-path→evidence mapping, and the audit coverage computation (`audit.py:88-146`). The truth core owns evidence *meaning*; the institution owns evidence *bytes at rest*.
- **Migration risks:** a store that separates record from sidecar could orphan one; they must be written/read atomically as a pair.
- **Test strategy:** assert record+sidecar are written and read as a unit through the store; keep the existing `/artifacts` byte-exactness tests green.

## A7. Approved File / Object Storage — GOVERNANCE-GATED

- **Current impl:** no real file storage. `POST /api/uploads` ALWAYS returns 403 (`routes.py:606-609`, `_UPLOAD_BLOCKED`) — no multipart declared/parsed, no byte touches disk. Source preview serves ONLY 2 committed synthetic fixtures by basename, traversal-guarded (`sources.py`; routes.py:455-481).
- **Existing seam:** the 403 endpoint IS a named governance seam ("no multipart is declared or parsed"). The 2-fixture allowlist is an intentional wall.
- **Missing seam:** a real object store + ingest pipeline (multipart, type/virus checks, sha256-on-ingest, per-file governance policy).
- **Recommended interface:** an `ObjectStore` + `IngestPolicy` Protocol living BEHIND the 403 wall, defaulting to "blocked" so the wall stays up until explicitly enabled.
  ```python
  class ObjectStore(Protocol):
      def put(self, data: bytes, *, content_type: str, sha256: str) -> ObjectRef: ...
      def open(self, ref: ObjectRef) -> BinaryIO: ...
  class IngestPolicy(Protocol):
      def admit(self, meta: UploadMeta) -> IngestDecision: ...  # default: DENY_ALL
  ```
- **Institution provides:** S3/GCS-backed `ObjectStore`, multipart handling, AV/type scanning, and an `IngestPolicy` that reflects their data-governance rules (what real data may enter).
- **ISAAC continues to own:** the default-DENY posture, the sha256/provenance requirements, the traversal guard, and the rule that ingested bytes never bypass truth-core validation — an uploaded file is evidence input, never an authorized record.
- **Migration risks:** flipping this wall is a DATA-GOVERNANCE decision (CLAUDE.md §6, §15), not plumbing; enabling upload without `IngestPolicy` + AV = a real-data leak/malware risk. Must stay dormant by default.
- **Test strategy:** assert `POST /api/uploads` still 403 by default even with the seam present; a fake `ObjectStore`+admit-all policy exercised only in isolated tests; assert sha256/provenance enforced on the admit path.

## A8. Project Memory Provider — CLEAN SEAM (no introduction needed)

- **Current impl:** `MemoryReader` Protocol (memory.py:157-166) with two concrete impls: `LocalGraphArtifactSource` (memory.py:402) over live `graphify-out/`, and `SanitizedSnapshotSource` (memory.py:807) over a packaged `memory-snapshot.json`. `get_default_reader()` selects by precedence `ISAAC_MEMORY_SNAPSHOT` → packaged snapshot → `ISAAC_MEMORY_DIR` → repo `graphify-out/` (memory.py:1145-1183).
- **Existing seam:** YES — Protocol + env-override + provider precedence + a snapshot generator (`scripts/build_memory_snapshot.py`). The docstring already anticipates "a future database source, mounted volume, hosted memory service, or login-gated institutional backend" (memory.py:50-60).
- **Missing seam:** nothing structural. Only a concrete DB/HTTP-backed `MemoryReader` impl, which is institution-provided.
- **Recommended interface:** already defined — satisfy `MemoryReader` and add one branch to `_resolve_reader_choice()`. Freshness/integrity/policy-fingerprint plumbing (P24.10) already exists (memory.py:236-300).
- **Institution provides:** a `MemoryReader` impl over their chosen backend + wiring; must honor the never-verdict / metadata-only contract.
- **ISAAC continues to own:** the Protocol, the stdlib-only + no-verdict + honest-degradation contract, and the MEMORY_NOTE ("leads, never a correctness ruling", routes.py:619).
- **Migration risks:** low — an institutional reader that violates the stdlib-only/no-verdict contract would fail `test_memory.py:813`; that test is the guardrail.
- **Test strategy:** run the existing memory Protocol/isolation suite against any new impl; no new seam tests required.

## A9. Search Provider — GREENFIELD (deferred to P26; do NOT build here)

- **Current impl:** none. No `/search` route (zero hits in routes.py). The frontend's fake search was deliberately DELETED and its absence is a tested invariant (`help-and-honesty.test.tsx`, `memory-*.test.tsx`).
- **Existing seam:** none — but the `MemoryReader` Protocol is the clean place to later add a memory `search()`, and the workspace state is per-resource queryable via existing endpoints.
- **Missing seam:** a search route + a cross-resource index over workspace + memory; a `search()` method on `MemoryReader`.
- **Recommended interface:** OUT OF SCOPE for this plan. Owned by P26 (arc decision #9/#10). Cross-reference only: P26 must add `MemoryReader.search()` and a workspace index, and rewrite the "no search" honesty tests in a dedicated reviewed slice.
- **Institution provides:** N/A here.
- **ISAAC continues to own:** N/A here — flagged so no institutional slice accidentally builds search ahead of P26.
- **Migration risks:** building search in this plan would collide with P26 and touch the guarded "no fake search" invariant. Explicitly deferred.
- **Test strategy:** none here; belongs to P26.

## A10. Background-Job Provider — GREENFIELD (deferred; introduce only when needed)

- **Current impl:** none. Everything synchronous in-request (export writes files inline, routes.py:334-335). No queue, no worker.
- **Existing seam:** none.
- **Missing seam:** a job runner — needed ONLY if long-running ingest/indexing (A7/A9) is added.
- **Recommended interface:** a `JobRunner` Protocol defaulting to synchronous inline execution (behavior identical to today).
  ```python
  class JobRunner(Protocol):
      def submit(self, task: Task) -> JobId: ...
      def status(self, job_id: JobId) -> JobStatus: ...
  # default InlineJobRunner runs task synchronously and returns a completed status
  ```
- **Institution provides:** a queue/worker (Celery/RQ/managed) impl if async work is enabled.
- **ISAAC continues to own:** the default synchronous path; the rule that a job may transport/transform inputs but the final validate/export still runs through the truth core synchronously before a record is authoritative.
- **Migration risks:** premature introduction adds operational surface for no benefit; introduce only alongside A7 real ingest or A9 indexing.
- **Test strategy:** default `InlineJobRunner` proves synchronous equivalence; fake async runner for status-polling tests when/if added.

## A11. Notifications — GREENFIELD (deferred)

- **Current impl:** none (zero hits for email/webhook/notify).
- **Existing seam:** none.
- **Missing seam:** a notifier channel.
- **Recommended interface:** a `Notifier` Protocol defaulting to no-op.
  ```python
  class Notifier(Protocol):
      def notify(self, principal: RequestPrincipal, event: DomainEvent) -> None: ...
  # default NullNotifier does nothing
  ```
- **Institution provides:** email/Slack/webhook impl + templates + delivery policy.
- **ISAAC continues to own:** the default no-op; emitting well-typed domain events (ties to A12); never putting a validation verdict in a notification without the truth-core-sourced provenance.
- **Migration risks:** low; depends on A1 (principal) + A12 (events) for meaningful content.
- **Test strategy:** default `NullNotifier` asserted silent; fake notifier asserts events emitted with correct provenance.

## A12. Audit / History Storage — PARTIAL

- **Current impl:** two forms. (a) Scientific audit = deterministic re-validation, computed fresh each call, never stored (`audit.py`; routes.py:387-399; `isaac audit`). (b) Action history = a per-experiment `answer_log` list appended in `experiment.json` (workspace.py:87; routes.py:169,:284). No global, queryable, actor-attributed event log.
- **Existing seam:** partial — `answer_log` persists per experiment but is not cross-queryable and has no actor.
- **Missing seam:** an append-only event/audit-trail sink with actor attribution (needs A1 identity first).
- **Recommended interface:** an `EventSink` Protocol defaulting to the current in-file `answer_log` behavior (or no-op for non-experiment events).
  ```python
  @dataclass(frozen=True)
  class DomainEvent:
      actor: str; action: str; resource: ResourceRef
      at: str; detail: Mapping[str, Any]
  class EventSink(Protocol):
      def record(self, event: DomainEvent) -> None: ...
      def query(self, *, resource: ResourceRef | None = None) -> list[DomainEvent]: ...
  ```
  Note: the *scientific audit* stays computed-fresh by the truth core; this sink is for ACTION history, not for caching validity verdicts.
- **Institution provides:** a durable append-only store (DB/log service) + retention/immutability guarantees.
- **ISAAC continues to own:** what events mean, the never-cache-a-verdict rule (the scientific audit is always recomputed, never read from the event store as truth), and actor sourcing from the principal.
- **Migration risks:** conflating action history with scientific audit would let stale stored verdicts masquerade as truth — must keep them separate; actor attribution is meaningless until A1 lands.
- **Test strategy:** default sink reproduces today's `answer_log`; fake sink asserts events recorded with actor; a test asserting `POST .../audit` still recomputes and never reads a stored verdict.

## A13. Deployment Secrets / Configuration — CLEAN SEAM

- **Current impl:** all config via env vars, read live where it matters. `_build_commit()`: `ISAAC_BUILD_COMMIT` → `RAILWAY_GIT_COMMIT_SHA` → null (routes.py:92-102). CORS `ISAAC_UI_CORS_ORIGINS` (app.py:27,34-37); auth `ISAAC_UI_API_KEY`; workspace `ISAAC_UI_WORKSPACE`; memory `ISAAC_MEMORY_SNAPSHOT`/`ISAAC_MEMORY_DIR`; frontend `VITE_API_BASE`/`VITE_API_KEY`. Deploy = `Dockerfile` (allowlist COPY) + `railway.json` + `apps/web/vercel.json`; CI = 2 jobs, no deploy step. No secrets in repo, all safely defaulted.
- **Existing seam:** YES — consistent env-var discipline is itself a clean config seam; a secret manager plugs in at the env layer.
- **Missing seam:** no formal config schema/validation and no documented "institutional deploy" env surface; no IaC beyond `railway.json`/`vercel.json`; no staging definition.
- **Recommended interface:** a small startup config validator (fail-fast on required vars once a non-default provider is selected) + a documented env matrix. No new abstraction — formalize what exists.
- **Institution provides:** a secret manager (Vault/cloud KMS), env injection, IaC, and staging/prod separation.
- **ISAAC continues to own:** the env-var contract, safe local defaults (zero-config dev), and the no-secrets-in-repo rule (Dockerfile COPY allowlist excludes `examples/drafts/records/graphify-out`).
- **Migration risks:** adding required-var fail-fast must not break zero-config local dev (only enforce when a provider is explicitly selected).
- **Test strategy:** extend `test_deploy_config.py` with a config-validation test; assert defaults still yield a bootable app with no env set.

---

# Part B — 25-Point Phase Envelope

Part A is the substantive per-area detail; the numbered points below frame the phase and, at point 20, turn the *seam-introduction* areas into slices. Points 8/12/14/15/16 reference Part A rather than repeat it.

**1 Purpose.** Make ISAAC institution-ready by ensuring every provider/repository boundary is a *configurable/replaceable seam*, so an institutional team replaces implementations and supplies backing infra rather than rewriting the app — without ever moving validity authority out of the truth core.

**2 User/scientist value.** A path to durable, per-user, multi-tenant workspaces (today's hosted state is ephemeral and shared) while keeping the same deterministic validation guarantees.

**3 Mentor/demo value.** A credible "how this graduates from prototype to institutional deployment" narrative: shows the boundaries are already mostly clean (memory + config), names the two real gaps (persistence + identity), and shows they are small, reviewable refactors — not a rewrite.

**4 Architectural value.** Extends the memory plane's proven Protocol pattern to persistence/identity/authz/audit, so the whole backend converges on one seam idiom (`get_default_X()` precedence + Protocol + default impl) that is already test-idiomatic in `memory.py`.

**5 Dependencies.** S1 (ExperimentStore) is foundational for S3/S4/S5/S6. A1 identity (S2) is a prerequisite for meaningful A2/A3/A12 actor attribution. Memory (A8) and config (A13) depend on nothing. Search (A9) is owned by P26 and is out of scope. No dependency on P25.

**6 Scope.** Introduce Protocols + default impls (byte-identical behavior) for: experiment/draft/evidence persistence; identity principal; authorization decision point; action-history event sink; object-store behind the upload wall; notifier; job runner; plus config validation + institutional env docs. See Part A for per-area boundaries.

**7 Non-goals.** Building any real backing store, IdP, object store, queue, notifier, or search; flipping any governance wall; touching the truth core; reordering or entangling P25/P26; adding new slash commands; indexing private data. All institutional *implementations* are out of scope — only the *seams* are in scope, and only if approved (Q1/Q2).

**8 Current baseline (cite files).** See Part A. Anchors: `auth.py`, `workspace.py`, `memory.py`, `routes.py`, `export.py`, `audit.py`, `sources.py`, `Dockerfile`, `railway.json`, `apps/web/vercel.json`, `.github/workflows/ci.yml`. Verification baseline: backend 461 tests, frontend 137/17, official validate PASS v1.05, audit 33/33, deployed `f534a4c`.

**9 Files likely touched (if slices approved).** `apps/api/isaac_api/workspace.py`, `auth.py`, `app.py`, `routes.py`, `serialize.py`, and new sibling modules (e.g. `store.py`, `identity.py`, `authz.py`, `events.py`, `objectstore.py`, `config.py`) under `apps/api/isaac_api/`; corresponding `apps/api/tests/*`; `docs/` for the env matrix. NOTE: introducing these WOULD modify `apps/` — hence gated on Q1; this planning doc itself modifies none of them.

**10 Files that must NOT be touched.** `src/isaac_records/*` (all truth-core modules), `schema/isaac_record_v1.json`, `schema/PROVENANCE.md`, the memory Protocol contract in `memory.py` (extend via new impl only, never weaken), and the frontend "no search" invariant tests (owned by P26). No slice may edit the two isolation tests (`test_export.py:169`, `test_memory.py:813`) except to keep them passing.

**11 Data flow.** Request → `AuthProvider`→`RequestPrincipal` on `request.state` → `Authorizer.can()` guard → route handler → `ExperimentStore` (load/save serialized state) → truth-core function (`validate_draft`/`export_draft`/`audit_records`) computes the verdict → `EventSink.record()` action event → response. The store/identity/sink only STORE and TRANSPORT; every verdict edge still originates in `src/isaac_records`.

**12 API / contracts.** No new public route shapes required for S1–S5 (seams are internal). New routes only if an institution enables uploads (A7, dormant) or async status (A10, deferred). Recommended Protocols are sketched per area in Part A. Response envelopes and the MEMORY_NOTE contract are unchanged.

**13 UI behavior.** None by default — all slices are behavior-preserving. A future institutional deployment MAY surface owner/org and a real login, but that is institution-side UI work, not part of these seams. The "no fake search" invariant is untouched.

**14 Security / governance constraints.** Truth core stays authoritative (schema validation, evidence audit, completion rules, export eligibility) — see Part A "what ISAAC continues to own" for each area. Governance walls (uploads-403, source allowlist, synthetic-only) stay CLOSED by default (Q3). Authorization refusals are transport-level and never alter a verdict. No secrets in repo; Dockerfile COPY allowlist preserved.

**15 Risks.** See per-area "migration risks". Top three: (a) S1 blast radius — every workspace callsite must route through the store; (b) ephemeral→durable changes seeding/multi-tenant semantics; (c) partial authorization coverage = silent bypass. Mitigation: contract test-suites + coverage tests + default impls that are provably byte-identical.

**16 Tests.** Per-area strategies in Part A. Cross-cutting: (i) a store contract-suite run against both filesystem-default and an in-memory fake; (ii) principal-propagation + deny-matrix tests; (iii) a guard-coverage test enumerating mutating routes; (iv) keep both isolation tests and all 461/137 baseline tests green; (v) assert default modes reproduce today's behavior exactly.

**17 Verification.** `.venv/bin/pytest` (backend), `npm test && npm run build` (frontend), `.venv/bin/isaac validate ... --official` (PASS v1.05), `.venv/bin/isaac audit` (33/33) after each slice. Each slice must show default-mode equivalence before merge.

**18 Deployment impact.** None by default (all seams dormant/default). When an institution supplies impls: a durable volume/DB replaces `/tmp`, an IdP replaces the shared key, a secret manager replaces raw env — all via env selection, no image rebuild logic change. `railway.json`/`vercel.json`/Dockerfile unchanged except possibly a documented volume mount.

**19 Documentation impact.** Add an "Institutional deployment" doc (env matrix + which Protocol to implement per backend) and update `docs/project-memory-map.md` back-burner registry. Do NOT fix the separately-owned stale docs (mentor-brief, final-deliverable-outline, paper-notes) here.

**20 Bite-sized slices.** Each slice: introduce ONE seam as a Protocol + default impl with zero behavior change; independently reviewable/committable; ends at a stop gate. All are gated on Q1 approval and none may modify the truth core.

- **S1 — ExperimentStore seam (foundational).** *Objective:* extract a `ExperimentStore` Protocol + `FilesystemExperimentStore` default + `get_default_store()`; make `Experiment` a pure model. *Files touched:* `workspace.py`, `routes.py` (callsites), new `store.py`, `apps/api/tests/*`. *Files forbidden:* `src/isaac_records/*`, `schema/*`. *Model:* Opus (data-model/architecture-critical). *Acceptance:* all workspace access goes through the store; filesystem behavior byte-identical (paths, seeding, status, 409 immutability). *Tests:* store contract-suite (filesystem + in-memory fake); baseline green. *Report:* diff vs invariants, equivalence evidence, truth-path-untouched confirmation. *Commit:* one commit, `P-inst-S1`. *Stop point:* review before S2.
- **S2 — Identity principal seam.** *Objective:* `AuthProvider` Protocol + `RequestPrincipal`; default shared-secret provider yields a fixed `local` principal on `request.state`. *Files touched:* `auth.py`, `app.py`, `routes.py`, new `identity.py`, tests. *Forbidden:* truth core, schema. *Model:* Opus (security-sensitive). *Acceptance:* principal available to routes; default = today's shared-secret behavior; `test_deploy_config.py`/`test_memory_api.py:606-614` green. *Tests:* fake provider principal-propagation. *Stop point:* review before S3.
- **S3 — Owner/org tagging.** *Objective:* additive defaulted `owner_subject`/`org_id` on experiment state, populated from principal. *Files touched:* `store.py`, `workspace.py` model, `routes.py`, tests. *Forbidden:* truth core, schema. *Model:* Opus. *Acceptance:* existing single-user data defaults to `local`; optional owner-scoped listing behind a flag. *Tests:* 2-principal isolation. *Depends:* S1,S2. *Stop point:* review before S4.
- **S4 — Authorizer decision point.** *Objective:* `Authorizer` Protocol + `AllowAllAuthorizer` default; guard every mutating route. *Files touched:* `routes.py`, new `authz.py`, tests. *Forbidden:* truth core, schema. *Model:* Opus (security). *Acceptance:* default allow-all = today; deny returns 403 without mutation. *Tests:* deny-matrix + guard-coverage. *Depends:* S2. *Stop point:* review before S5.
- **S5 — EventSink action history.** *Objective:* `EventSink` Protocol; default reproduces `answer_log`; actor from principal. *Files touched:* `routes.py`, `workspace.py`/`store.py`, new `events.py`, tests. *Forbidden:* truth core, schema. *Model:* Opus. *Acceptance:* action history preserved; scientific audit still recomputed (never read from sink). *Tests:* event-record + audit-recompute. *Depends:* S2. *Stop point:* review before S6.
- **S6 — ObjectStore behind the upload wall (dormant).** *Objective:* `ObjectStore`+`IngestPolicy` Protocols behind `POST /api/uploads`; default DENY_ALL (403 unchanged). *Files touched:* `routes.py`, new `objectstore.py`, tests. *Forbidden:* truth core, schema. *Model:* Opus (governance/security). *Acceptance:* uploads still 403 by default; sha256/provenance enforced on the (test-only) admit path. *Tests:* default-403 + admit-path provenance. *Governance:* Q3. *Stop point:* review before S7.
- **S7 — Notifier (deferred/optional).** *Objective:* `Notifier` Protocol + `NullNotifier` default. *Model:* Sonnet (mechanical). *Acceptance:* default silent. *Depends:* S2,S5. *Stop point:* review.
- **S8 — JobRunner (deferred/optional).** *Objective:* `JobRunner` Protocol + `InlineJobRunner` default. *Model:* Sonnet. *Acceptance:* synchronous equivalence. *Stop point:* review. (Build only alongside real A7/A9 async need.)
- **S9 — Config validation + institutional env docs.** *Objective:* fail-fast config validator (only when non-default provider selected) + env matrix doc + memory institutional-impl contract doc. *Files touched:* new `config.py`, `app.py`, `docs/`, `test_deploy_config.py`. *Forbidden:* truth core, schema. *Model:* Sonnet (docs/mechanical). *Acceptance:* zero-config local dev still boots. *Stop point:* review.

**21 Model/subagent assignment.** Fable orchestrates/reviews/verifies. S1–S6 → Opus 4.8 (architecture/data-model/security/governance). S7–S9 → Sonnet 5 (mechanical/docs). Memory (A8) and search (A9) need no slice here.

**22 Acceptance criteria.** Every approved slice: (a) Protocol + default impl with proven byte-identical default behavior; (b) truth core + schema untouched; (c) both isolation tests + full 461/137 baseline green; (d) governance walls still closed by default; (e) independently reviewable and committed alone.

**23 Stop / approval gates.** Gate 0: approve Q1–Q5 before ANY slice. Then a stop gate after each slice (S1→…→S9) — no slice starts before the previous is reviewed and merged. S1 is a hard gate (foundational). S6 is a governance gate (Q3). This plan authorizes NOTHING until Gate 0 passes.

**24 Deferred items.** Search provider (A9) → P26. Real backing implementations (DB, IdP, S3, queue, notifier) → institution. Async job runner (S8) until real ingest/index exists. Notifier (S7) until events are consumed. IaC/staging definition. Register these in `docs/project-memory-map.md` back-burner table rather than duplicating.

**25 Explicit questions for the user.** See header Q1–Q5. In short: (Q1) authorize a seam-introduction phase at all? (Q2) does ISAAC own durable persistence or only the seam? (Q3) confirm governance walls stay closed by default? (Q4) confirm no entanglement with P25/P26 ordering? (Q5) confirm truth core is off-limits?
