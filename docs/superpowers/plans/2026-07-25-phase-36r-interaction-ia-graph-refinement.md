# Phase 36R — Interaction, Information Architecture & Graph Exploration Refinement

**Status:** authorized 2026-07-25 · repository-local · synthetic-only · no Phase 37
**Starting canonical state (verified, not assumed):**

| Axis | Verified value | How verified |
|---|---|---|
| Repository | `ISAAC-DOE/isaac-metadata-assistant` (`origin`) | `git remote -v` |
| Branch | `main`, clean, 0 ahead / 0 behind | `git status -sb`, `git rev-list --left-right --count HEAD...origin/main` |
| HEAD | `424d021756b391413a2fa130436f1b1e74b4e134` | `git rev-parse HEAD` == `git ls-remote origin main` |
| Latest image tag | `v0.0.12` → `424d021` | `git ls-remote --tags origin` |
| Backend tests | **1029 passed** | `.venv/bin/pytest -q` |
| Frontend tests | **751 passed / 62 files** | `npx vitest run` |
| Bundle baseline | JS **391 095 B**, CSS **110 424 B** (unminified-gzip: measured per slice) | `apps/web/dist/assets/` |
| Hosted `/krish/api/health` | **HTTP 302 (Authentik redirect)** — body not readable from this environment | `curl https://isaac.slac.stanford.edu/krish/api/health` |

Phase 36 (P36.1–P36.8) is closed. This phase is a **refinement** of the surfaces
Phase 36 shipped. It adds no truth-core change, no LLM, no portal, no real data.

---

## 0. Reconciliations against the authorizing prompt

Each item below differs from the prompt's literal instruction. Each is grounded
in a verified repository fact, not a preference.

### R1 — The Graphify HTML artifact cannot be reused. Build native. *(affects Slice 3)*

The prompt offers three implementation options and asks for the safest. Option 1
(adapt the Graphify rendering code) and option 3 (sandboxed static viewer) are
both **disqualified by verified facts**:

1. **`graphify-out/` is gitignored** (`.gitignore:2`) — it is not in the repository,
   not in the Docker `COPY` allowlist (`Dockerfile:32-37`, whose header explicitly
   forbids adding it), and therefore cannot exist in the deployed image at all.
2. **`graphify-out/graph.html` loads `https://unpkg.com/vis-network@9.1.6/…`** — a
   hard CDN runtime dependency, which this phase's own boundary list forbids.
3. **`graphify-out/graph.json` contains paths the served-content governance
   manifest deliberately excludes** — verified: `ux-review/inventory-report.md`,
   `ux-review/planning-archaeology-report.md`, `ux-review/ux-review-report.md`,
   `examples/README.md`. Serving the raw artifact would publish material the
   snapshot manifest withholds.
4. **Size**: `graph.html` is 2 549 755 B against a current *total* JS bundle of
   391 095 B.

**Decision: option 2 — a native visualization built from the already-committed,
already-sanitized snapshot projection**, with **zero new dependencies**. The
Graphify HTML is used as a *visual reference only* (immersive dark canvas,
community color, search sidebar, node info panel) — none of its code, data, or
assets are copied, iframed, or served.

### R2 — The conversation region is white-on-lavender, not lavender-on-lavender. *(Slice 2)*

The prompt asks for "a subtle lavender-tinted background" for the conversation
region. The Assistant **rail column is already lavender** (`--assist-tint`
`#ecebfb`, `assistant.css:16-18` + `screens.css` `.record-right` / `.memory-right`).
A lavender region on a lavender rail would not bound anything.

**Decision:** the conversation region is an **elevated white/near-white surface
with one restrained full `--assist-border` outline**, lifting off the existing
lavender rail. This satisfies the prompt's actual requirement ("a clearly bounded
conversation region", "one restrained purple accent") on the real background.

### R3 — No colored left/right accent edge is permitted anywhere. *(Slices 2, 3, 10)*

`apps/web/src/__tests__/no-vertical-rail.test.ts` fails CI on any
`border-left`/`border-right` declaration paired with an accent token **or any hex
literal**, across every `.css` and every inline `.tsx` style. The prompt's
"restrained purple border/accent" must therefore be a **full four-sided `border:`
shorthand**, never an accent edge. The dark graph canvas is bound by the same rule.

### R4 — Hosted verification is not performable from this environment.

`GET https://isaac.slac.stanford.edu/krish/api/health` returns **HTTP 302** — the
Authentik edge redirects an unauthenticated caller, so the `commit` field cannot
be read. Per `CLAUDE.md` §12 this is reported as **`HOSTED QA PENDING (Krish)`**
with an exact checklist. No rollout will be claimed as verified. This is a
reconciliation of the prompt's "verify hosted health where authenticated access is
available" clause — access is *not* available here.

### R5 — 112 communities is a real usability defect, not a rendering detail. *(Slices 3, 7)*

Verified from the live projection: 201 files / 19 concepts / 508 edges /
**112 communities**. Most are singletons. A flat 112-entry `<select>` (today's
`MemoryGraphCard.tsx:430-437`) is noise. Community controls will be **sorted by
file_count descending**, searchable, and will label singleton communities
honestly rather than presenting 112 equal-weight options.

### R6 — Assistant graph intents resolve **client-side**, against the same projection. *(Slice 5)*

The prompt requires the Assistant and the command bar to "share the same typed
graph action model" and forbids "separate incompatible graph logic". The command
bar necessarily operates on the client-side graph index. Resolving Assistant graph
intents on the backend (`assistant_query.py`) would create a **second node-resolution
implementation** that can drift from the first.

**Decision:** one shared frontend module (`lib/graphActions.ts`) owns the typed
`GraphAction` union, the command grammar parser, the bounded NL intent classifier,
and node resolution. The Assistant's graph capability is opt-in per mount
(Project Memory only in this phase); every other Assistant behavior and every
record-surface mount is unchanged, and no backend route is added or modified.
This is documented in the closure as an explicit architectural boundary.

### R7 — `Schema & Vocabulary` → `Schema Reference`, and Vocabulary is **not** empty.

The prompt says to rename "unless actual vocabulary files justify the broader
name", and to show an honest empty state "if no vocabulary files exist".
Verified: `vocabulary/descriptor_class.json` is **real, non-stub content** — 33
class tokens across 4 groups, 11 products, 1 deprecated alias, with an honest
provenance note and an upstream wiki source URL. The schema itself carries 37
`enum` occurrences.

**Decision:** rename the tab to **Schema Reference** (as asked) and keep a real,
populated **Vocabulary** subview. The "compact honest empty state" is implemented
as the *fallback branch* (it renders when `vocabularies` is empty) but will not be
the observed state — claiming otherwise would be false.

---

## 1. Permanent boundaries re-affirmed for this phase

Unchanged and enforced by existing tests: deterministic truth core; official
schema validation authority; evidence/export authority; no guessing; read-only
advisory non-LLM Assistant; ephemeral conversation; Project Memory separate from
record truth; graph results are navigational leads; synthetic-only; no real data,
Postgres, portal/personal API key, external model provider, embeddings, vector DB,
runtime Graphify dependency, telemetry, CDN, or `isaac-k8` change; no direct push
to org `main`; no squash/rebase merge; no force-push; no manual release tag;
**no Phase 37**.

Files that must NOT be modified by any slice in this phase:
`schema/isaac_record_v1.json`, `src/isaac_records/*`, `apps/api/isaac_api/export*`,
and the truth tests. `apps/api/isaac_api/memory_graph.py` may be extended ONLY if
a slice provably needs it; the default is no backend change at all.

---

## 2. Slice → PR map

| PR | Slices | Branch | Scope |
|---|---|---|---|
| 1 | 1 + 2 | `feat/p36r-1-layout-assistant` | Shared width modes; Assistant conversation redesign |
| 2 | 3 + 6 | `feat/p36r-2-graph-explore` | Graph Explore/Browse; graph help |
| 3 | 4 + 5 | `feat/p36r-3-graph-commands` | Command bar; Assistant graph intents |
| 4 | 7 | `feat/p36r-4-concepts` | Concepts master-detail redesign |
| 5 | 8 | `feat/p36r-5-schema-reference` | Governance IA; Schema Reference; Validator copy |
| 6 | 9 | `feat/p36r-6-settings-api` | Settings tabs; API browser |
| 7 | 10 | `feat/p36r-7-polish-closure` | Cross-surface polish; docs closure |

Slices 1+2 are combined because the Assistant rail width and the main-content
width are the same layout computation — splitting them would land a width change
that provably overlaps the rail, then fix it in a second PR. Slices 3+6 are
combined because the help drawer documents controls that do not exist until
Explore lands. Slices 4+5 are combined because the command bar and the Assistant
intents are two front-ends over one shared `GraphAction` module written once.

---

## 3. Slice specifications

### Slice 1 — Shared content-width system

**Root cause (verified):** `apps/web/src/screens/screens.css:171` —
`.placeholder { max-width: 640px }` constrains the *entire* Project Memory page,
Governance page, and Settings page, including the Graph tab's canvas.
`chrome.css:40-47` offers only `.centered-col` (1040px) / `.centered-col.narrow`
(720px), used by a different set of screens.

**Deliverable:** one truthful width system on `AppShell`, exposed as a
`width?: 'readable' | 'wide' | 'full'` prop (default preserves today's behavior
for unlisted screens), implemented with CSS custom properties in `chrome.css` so
prose keeps a readable measure inside a wide container.

| Mode | Container | Prose measure | Applied to |
|---|---|---|---|
| `readable` | ≤ 760px | inherits | Guided Completion, focused forms, confirmation flows |
| `wide` | ≤ 1200px | ≤ 68ch on `p`, `li` | Project Memory Overview/Sources/Concepts, Governance, Schema Reference, Settings |
| `full` | 100% − gutters | ≤ 68ch on prose only | Graph Explore, Export Readiness workbench |

Gutter between `<main>` and the Assistant rail: **28px** (within the prompt's
24–32px band), applied as `padding-inline-end` on `.screen-main`, so it survives
the rail collapsing to a drawer.

**Acceptance:** no overlap with the rail at any width; no horizontal page scroll
at 1440/1280/1024/768/375 and at 200% zoom; consistent gutters and title
alignment; record workflows not indiscriminately stretched; existing 62 frontend
test files still pass.

### Slice 2 — Assistant conversation redesign

Shared-component work in `AssistantPanel.tsx` + `assistant.css` only. All five
mounts inherit it (`RecordWorkbench:166`, `GuidedCompletion:271`,
`EvidenceExplorer:164`, `ExportReadiness:340`, `ProjectMemory:102`).

**Region order (replaces today's header → composer → prompts → Agent Actions →
Clear → log → live reply):**

1. **Header** — title, memory status (where the mount passes `availability`),
   `Clear Conversation` **only when a conversation exists**.
2. **Empty state** — concise guidance, Suggested Questions, Agent Actions.
   No filler card; no oversized blank container.
3. **Conversation region** — mounted only once a turn exists. Elevated white
   surface, one full `--assist-border` outline (R2/R3), internal `overflow-y`,
   `overflow-x: hidden`, user messages right-aligned on a muted surface,
   assistant messages left-aligned on white with a restrained indigo accent
   (not a left edge), provenance attached beneath its own response, follow-ups
   attached to their response.
4. **Proposed action region** — `Stage Answer` / navigation / proposals rendered
   as a distinct **Proposed action** block beneath the relevant response, never
   as chat messages, never implying the action already happened.
5. **Composer** — sticky at the bottom of the panel; conversation scrolls above
   it; Suggested Questions collapse to a compact disclosure once a conversation
   exists.
6. **Authority footer** — the existing `SUBORDINATE_CAPTION`, beneath the composer.

**Overflow contract (audit every flex/grid child):** `min-width: 0` on flex
children; `max-width: 100%`; `overflow-wrap: anywhere` on all text carriers
including chips, buttons, provenance rows, and action previews; **remove the
fixed `max-height: 340px` on `.assistant-log`** (`assistant.css:73`) in favour of
a flex-driven height so 200% zoom does not clip; no truncation without the full
value remaining reachable.

**Preserved verbatim:** one coherent transcript, deterministic replies, honest
refusals, unavailable states, Ask Again, provenance, suggested prompts, Agent
Actions, ephemeral state, no logging of question/answer text, the verdict-language
guard, the `answered from:` line, the memory caveat, and every existing a11y
live-region rule (log stays `aria-live="off"`; exactly one polite live region).

**Added:** auto-scroll to newest only when already near the bottom (already
present — preserve), focus handling after submit and after Clear, screen-reader
announcement of new answers, reduced-motion handling.

### Slice 3 — Graph Explore / Browse

**Data source:** `GET /api/memory/graph` →
`apps/api/isaac_api/memory_graph.py::build_graph_projection`, over the committed
`apps/api/isaac_api/data/memory-snapshot.json`. Verified live payload: 220 nodes
(201 files / 19 concepts), 508 edges, 112 communities, 5 relation types
(`calls`, `imports`, `imports_from`, `references`, `shares_data_with`), 119 770 B,
`truncated: false`. **One fetch; every interaction is client-side state.**

**No backend change.** No new dependency.

**Explore mode** — a bounded dark canvas inside the light shell:
deterministic force-free layout (seeded, no `Math.random`, no physics loop);
pan / zoom / fit / reset / node drag; community coloring with a categorical,
contrast-checked palette; node **shape** distinction (circle = file, diamond =
concept) so meaning is never color-only; search; node-type / community /
relationship-type filters; 1-hop and bounded 2-hop neighborhoods; connected-node
highlighting; deterministic BFS shortest path (tie-broken by sorted node id);
selected-node detail panel; source navigation; node/edge counts; snapshot
fingerprint; explicit loading / empty / unavailable / invalid states.

**Render bound:** never mount the full 220-node graph unfiltered as the default —
the default view is search-first plus a bounded overview; expansion is explicit.
Hard cap on simultaneously rendered nodes, reported honestly when it bites.

**Browse mode** — the existing textual experience, preserved and refined:
searchable node list, keyboard selection, connected-node list, relationship list,
source navigation, metadata, read-only JSON disclosure, community grouping, no
pointer-only interaction. **Browse is permanent**, not a fallback to be removed.

**Truth copy:** the existing "served-file reference projection, not the full
source graph" disclosure is retained and extended to explain the four layers
(full un-embedded Graphify source graph → served-file projection → concepts →
communities/relationships visible in ISAAC).

### Slice 4 — Graph command bar

Deterministic bounded grammar, no LLM, no expression evaluator, no shell/FS
access, no mutation. Parsed into the shared `GraphAction` union:

`help` · `find <query>` · `select <node>` · `neighbors <node> [depth 1|2]` ·
`community <name|id>` · `type file|concept|all` · `relation <relation-type>` ·
`path <node-a> -> <node-b>` · `fit` · `reset` · `clear filters`

Examples/autocomplete; clear validation errors; honest not-found; **never a
guessed node identity** — an ambiguous token lists bounded candidates and stops;
ephemeral local history; keyboard-first; accessible result announcements;
commands mutate the *same* canonical graph state as filters and clicks; bounded
shareable URL state with correct `/krish` basename and working back/forward.

### Slice 5 — Assistant → graph integration

`lib/graphActions.ts` additionally exposes a bounded NL classifier producing the
**same** `GraphAction`. On recognition the Assistant: resolves deterministically,
explains what it found or could not find, shows provenance, and offers an explicit
**`Apply to Graph`** action. It never manipulates the graph before the user
applies it. Ambiguity → bounded choice list. No path → said honestly. Out of
scope → refused or redirected to supported graph capabilities. Applying navigates
to Project Memory → Graph → Explore with the state encoded in the URL.

Capability is opt-in per mount; only Project Memory receives it in this phase.

### Slice 6 — Graph help

An `i` control beside the Graph title / in the Explore toolbar opening a concise
drawer: what the graph represents and does not; node shapes; community colors;
relationship types; search; filters; pan/zoom; fit/reset; selection; neighborhood;
path search; command syntax with directly-applicable examples; keyboard shortcuts;
snapshot fingerprint; why Project Memory is advisory and not record truth;
Explore vs Browse. Concise — not a documentation wall.

### Slice 7 — Concepts redesign

Master-detail replacing today's flat single-open accordion
(`ProjectMemory.tsx:769-979`): search, community filter, compact list, selected-
concept detail, plain-language description, anchor source, community, related
leads, source navigation, honest missing-source state, **Show in Graph Explore**,
browse-connected action. Copy fix: `not present locally on this backend`
(`ProjectMemory.tsx:916`) → **"The cited source is not included in this deployed
snapshot."** No implication that a concept is a verified scientific conclusion.

### Slice 8 — Governance & Schema Reference

Tabs → **Policy · Validator · Schema Reference**. Schema Reference subviews:
**Fields** (default; searchable list + selected-field detail; path, plain-language
description, type, required/optional, allowed values, examples, nested structure,
related conditional requirements, source/version — not everything expanded at
once) · **Conditional Rules** (the `allOf`/`if`/`then` dump restructured into
trigger / required consequence / affected paths / source rule, with raw form
expandable, never leading with raw JSON Schema) · **Vocabulary** (real
`descriptor_class` content per R7; honest compact empty state as the fallback
branch).

Validator retained, clarified with **"Validate a record without adding it to My
Experiments."**, kept as a secondary utility. **One** validator implementation —
`validate_official` via `POST /api/validate/record`; the 512 KB bound, the
no-persistence and no-content-logging guarantees, and the structured errors are
preserved and re-asserted by tests.

### Slice 9 — Settings IA

Tabs → **Overview · Data & Privacy · About · API**. No invented settings.
API becomes a master-detail OpenAPI browser (search + grouped endpoint list +
selected-endpoint detail + collapsible schemas/examples), still generated from
`GET /api/openapi`, still no CDN, still `/krish`-correct, no sensitive data.

### Slice 10 — Cross-surface polish + closure

Title/tab spacing, card padding, gutters, empty states, search fields, detail
panels, long values, sticky regions, scroll boundaries, button heights, radii,
focus rings, icon alignment, badges, typography, narrow stacking. The light
neutral design system is preserved; the **only** intentionally dark surface is the
bounded graph canvas.

---

## 4. Verification contract

**After every slice:** focused tests → full frontend (`npx vitest run`) → full
backend (`.venv/bin/pytest -q`) → `tsc -b` → production build → snapshot drift
check (when a manifest-listed file changed) → secret/absolute-path/external-request
scans → independent Opus review → fix all Critical + Important → commit → push
branch → PR → green CI (`ci.yml` both jobs + `pr-docker-smoke.yml`) → **merge
commit** (never squash/rebase) → monitor `build-push.yaml` semver publication.

**Before closure:** full backend + frontend suites, TypeScript, production build,
Docker build + smoke, `/krish` base-path tests, nested-route refresh, synthetic
demo, official validation, evidence audit, snapshot + committed-snapshot gate,
secret / absolute-path / external-request / hardcoded-route / hardcoded-API scans,
`.only`/skipped-test audit, bundle-size comparison, graph performance checks,
final independent release review.

**Visual QA:** local run (`uvicorn` + `vite`) driven through Chrome at 1440 /
1280 / 1024 / 768 / 375 and 200% zoom, screenshot-inspected per the prompt's
scenario matrix. **Krish's human sign-off gate stays OPEN** — automated/browser QA
is reported as exactly that.

## 5. Orchestration

Orchestrator (this session) plans, inspects, reviews, verifies, and controls all
git/PR/merge/deploy actions. One focused implementation subagent per slice,
sequential. A separate independent reviewer that implemented none of the work
under review runs after every state-changing slice. Implementation and review
subagents never commit, push, merge, tag, deploy, change remotes/infrastructure/
credentials, connect real data, or begin Phase 37.

High-risk slices (shared Assistant component, shared layout system, graph action
model) use the strongest available implementation model; all reviews use it.

## 6. Open human gates carried into this phase

- Responsive / 200%-zoom human visual sign-off (open since Phase 33).
- Hosted QA of every published image (Authentik edge; not self-verifiable here).
- Personal-deploy retirement (Vercel `isaac-demo-web` + Railway) — Krish's
  dashboard action.
- Phase 37 authorization — **not** requested by this phase.
