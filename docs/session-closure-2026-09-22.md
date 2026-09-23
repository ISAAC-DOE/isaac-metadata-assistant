# Session closure — 2026-09-22/23: the owner's hosted QA, turned into the product

**Starting point, re-derived rather than trusted:** `main = origin/main = 0a12f7ae` (`v0.0.259`),
tree clean, no open PRs, CI green. Hosted `/krish/api/health` read `commit 0a12f7ae…` —
the owner's QA was against exactly that build.

**The owner's screenshots did not arrive with the direction** — only its text did. Every
finding was therefore REPRODUCED locally from `main` in a real headless Chromium, and then,
once the owner signed Chrome in for the agent, **confirmed read-only on hosted** (no write,
no credential entered). The inventory is `docs/evidence/owner-qa-issue-inventory-2026-09-22.md`.
One hosted fact changed the work: **the owner runs with the Assistant rail expanded**
(`isaac.assistant-rail-collapsed=0`), leaving a 955 px main column at a 1510 px window, which
local collapsed-rail screenshots had understated.

## What merged

| PR | What | Merge | Release (resolved from the TAG) |
|---|---|---|---|
| #278 | Historical semantics: conventions independent of operators, reviewed rule reuse, Angel's 2026-09-22 answers, the named app-side residue | `f2838ba9` | `v0.0.260` → `f2838ba9`; **observed live on hosted** |
| #277 | Record redesign: focused Capture area, state-vs-location spine, readable Record Map, decision-first proposals and validation, acceptance preflight | `50d3cdd6` | `v0.0.261` → `50d3cdd6`; **observed live on hosted** — Capture Home, the compact acceptance notice and the Record Map rendered on the owner's own record, rail expanded |
| #279 | Historical Import: six focused stages, conflicts source by source, per-scan variation ≠ conflict | `ea3f08d1` | `v0.0.262` → `ea3f08d1` |
| (this PR) | This record, decision register §B7, the ledger header + entry, a `CLAUDE.md` §11 pointer, the reproduced issue inventory | — | — |

## Owner complaint → outcome

| Owner complaint | Old behaviour (measured on 0a12f7ae) | New behaviour | Verified by |
|---|---|---|---|
| Workflow shows the wrong page as current | `Complete Metadata` drew blue/current on Runs, Capture, Activity and `/export` | Each row carries STATE (icon + word) and LOCATION (selected fill + `aria-current="page"`) independently | unit + e2e; browser at 6 widths, rail open/closed |
| Record Fields duplicated in nav | `WORKSPACES → Record Fields` beside the workflow step reaching it | Removed; reached via `Record Created`; deep links unchanged | route tests |
| Capture is one giant page | 1,795 px empty / 4,297 px after `Start Writing`; Write and Recorder opened the same panel | Capture Home = four methods; each opens a focused view beside a live Record Map (container-query split, stacks when narrow) | browser sweep; owner layout 1510 rail-open |
| Recorder-first voice path | "Open Recorder" presented as the voice path; speech never becomes text | Claude/MCP first from real `mcp.posture` (hosted: "Not Enabled Here" + Connect Your Agent); **no Connected state exists**; local recorder under "Record Locally Instead" with every mic-release guarantee | unit (all postures incl. ready); mutation mic specs 125/125 |
| Record Map unreadable | raw paths, lowercase `sample`/`system`, clipped "Show full official schema" | human labels, SemanticStatus per row, value where honestly held, path behind `?`, no clipping | sweep: 0 clipped |
| `Sample  sample` labels; prose tails | technical keys beside every heading; `13 fields · none recorded yet` | human heading only; `N fields` + one status computed from rows (never invented) | unit |
| Weak disclosure triangles | tiny chevron as the only affordance | whole-row targets with hover / focus-visible / expanded states | real-Tab sweep |
| Proposal cards are essays | ~290 px of prose per card | status · field · value · quote + source; provenance behind "Why This Was Proposed"; one visible "not the field's value" line | unit + e2e toBeVisible |
| Accept only fails after a click | full-width refusal paragraph after a guaranteed-failing click | `proposal_acceptance` preflight → one compact lock notice + Accept disabled with a described reason; `409 human_actor_required` unchanged and rendered compactly if reached | unit (true/false/absent), mutation + trusted e2e |
| Validation is a wall | schema messages under paragraphs; advisories twice | blockers first, field in human words, message verbatim (DEC-30/35), Go to Field where real; advisories once | unit |
| Historical Import is a dump | 44,185 px session; internal tokens; prose everywhere | six stages, one at a time: 1,612 px; counts first; conflicts source by source | browser at 36 contexts, axe 0 (negative-controlled) |
| "Sources Conflict" noise | per-scan readings of one measurement shown as conflicts (36 of 43 on the synthetic multi-operator corpus) | `bl15.mapping.cardinality.v2`: a per-scan-item value differing across ≥ 2 established scans = neutral variation; a planned (measurement-level) reading is always compared with recorded (scan-level) ones; synthetic 43 → 7, real corpus 29 varies / 46 conflicts, every genuine disagreement kept | test_bl15_cardinality (23, mutation-checked) + the reviewer's own probe |
| Missing record page | title `Record Fields`, 5 perpetual skeleton rows (confirmed on hosted) | `Record Not Found`, settled spine, no live rail | document-title tests |

## Angel's 2026-09-22 answers, integrated conservatively

Missing stays missing (Q9, Q14 intentionally left missing); **`DEC-43`'s 298 K superseded**
(no automatic insert or proposal; "room temperature" kept verbatim; a nominal only via a
reviewed rule naming its convention — none enabled); per-Run HERFD selection (90 suggested /
4 unresolved on the real corpus; never writes a field); Run 32 preserved as two Runs; no
source hierarchy — suggested resolutions are non-authoritative and a confirmed one goes
forward only as a proposal; Data Quality Notes never become `qc.status`. **Q6, Q7, Q8 remain
Angel's**, plus one new question (below).

## Real BL15-2 regression

`docs/evidence/bl15-real-regression-2026-09-22.md` — aggregate counts only, local, nothing
left the machine.

## Verification

Measured on merged `main` at `ea3f08d1`, in the MAIN CHECKOUT (skip counts are +2 in a worktree,
because `graphify-out/graph.json` is gitignored), by the orchestrator:

| Check | Start (`0a12f7ae`) | End (`ea3f08d1`) | Command |
|---|---|---|---|
| Backend | 10,144 passed / 49 skipped *(worktree)* | **10,253 passed / 47 skipped** | `.venv/bin/python -m pytest -q -p no:cacheprovider` |
| Frontend | 239 files / 6,229 tests | **248 files / 6,450 tests** | `npx vitest run` (default parallelism) |
| Typecheck | exit 0 | **exit 0** | `npx tsc -b` |
| OpenAPI | 81 paths / 91 operations | **83 paths / 93 operations** | `create_app().openapi()` |

Every PR was merged at its exact CI-green head with `main` already merged into the branch
(so the tested tree was the merge result): #278 5/5 at `21f76819`, #277 5/5 at `c5fba214`, #279
5/5 at `db20c6fc`. Browser QA: Chromium, 1440/1280/1024/820/390/320 (plus 1510), Assistant rail
expanded AND collapsed, a console hook proven by a negative control (4/4) on every sweep, real-Tab
focus-visible checks, in-browser axe with its own negative control; 0 horizontal overflow on every
redesigned view. **Impeccable:** critique + polish playbooks were run by the implementers on every
redesigned surface (single-context, disclosed as degraded — no sub-agents may spawn); its
mechanical `detect.mjs` was negative-controlled and returned `[]` on deliberately broken `.tsx`, so
**no "0 findings" from it is cited anywhere**. The accessibility baseline job passed on every final
head with no cell movement from the redesign; #278's two new operations moved three linux
`settings-explorer` cells (23 → 24), transcribed from CI job 106931691561.

## Independent review — every one found defects the implementers' own suites passed

- #278: MERGE-after-fixes, 6 Important (cross-experiment rule leak, registry bypass on
  resolution, regex coercion of chosen readings, health 500 on an unreadable staging root,
  duplicated Data Quality Notes on re-import, two corpus phrases committed) — all fixed with
  failing-first tests.
- #277: MERGE-after-fixes, 9 Important (Accept offered beside a locked Accept, HelpTip below
  the fold, two run pickers, Claude dictation advertised, raw ISO/ids, toolbar wrap, advisories
  above blockers, a hidden honesty claim, no Go to Field) + pre-existing Finalize-twice
  duplicates — all fixed.
- #279 + integrated pass: MERGE-after-fixes with **one Critical** — the v1 cardinality rule hid a genuine one-scan
  planned-vs-recorded disagreement (9,175 vs 9,180 eV; 1 s vs 0.5 s) and trusted an unverified
  `#S N` ↔ `_00N` scan correspondence. Fixed as v2; the reviewer's own probe now reports all four
  cases as conflicts. Plus 6 Important (a false universal temperature sentence, a rule labelled
  "sample group ·", Add predicting ≠ delivering, three conflict counts under one name, a table
  cell contradicting the server's agreement verdict, an epoch and a zone-less local time sent as
  competing proposals — the latter into a UTC field) and 4 integrated-product findings
  (Extended Context raw keys/ids/reasoning, clipped run labels on phones, a dead-end Voice map,
  `/complete` at 320) — all fixed. The orchestrator's own browser pass then found two more (the
  Extended Context panel's collapse never hid anything — 7,630 px → 1,283 px; Review listing sent
  candidates as "Ready to Send") — both fixed.

## Operational findings worth carrying

- **A usage limit cut both agents off twice**; each was resumed from its own worktree state
  with no work lost (uncommitted edits verified before continuing).
- **CI caught two integration-only failures no local run could:** a zoom-200 loop at 58.8 s
  under a fixed 60 s budget (tipped over by three new surfaces), and a trusted-suite focus
  read taken ~15 ms before focus landed. And after #278 merged, the preflight disabled Accept
  in the mutation suite's own backend — a spec that had passed against a pre-merge backend.
- **A full-parallel-only focus failure** (passes in isolation, under CPU burners, in subsets,
  and with file parallelism off) was fixed by design — focus on the commit that renders the
  heading — not by a longer budget.
- **Another project's pytest processes (Homebrew Python 3.14) drove host load to 15–70**;
  they were not ISAAC's and were left alone.

## Named residue and external gates

**Only external/human gates remain — and a short list of named, deliberately-deferred items.**

*Hao / SLAC:* `EXT-01` trusted identity (acceptance stays `409 human_actor_required`; the UI now says so up front) · `EXT-02` production remote MCP/auth (hosted `mcp.posture: unmounted`; the Voice view shows "Not Enabled Here") · `EXT-13` real file-byte governance (`historical_file_ingestion` is now an explicit capability, **disabled by default**; enabling it is configuration) · `G2`/`G3` visibility decisions.

*Operator:* all migration artifacts re-verified unchanged (six `0003`–`0005` SHA-256 digests match their packets; `git diff origin/main` over migrations and packets empty). Nothing applied; production execution remains the operator's act.

*Angel:* `Q6` environment member, `Q7` reaction member, `Q8` JK cell type — unanswered by the 2026-09-22 reply. **New:** which acquisition quantities are legitimately per-scan (emission energy, energy grid, counting time, scan command kept per-measurement meanwhile), and whether the real corpus's 9 `acquisition_timestamp` / 9 `sample_position` conflicts are genuine.

*Krish:* authenticated hosted final eyes on `v0.0.261`+ (hosted was observed serving `v0.0.260` read-only; the redesign images roll via Flux) · **true 200% browser zoom** (no CDP method drives it; the suite's zoom-200 project is a layout-equivalent emulation and says so) · a real macOS microphone indicator check for "Record Locally Instead" · subjective final sign-off · a data-governance call on `tests/fixtures/bl15/notes/beamtime-notes.txt` (committed 2026-09-16, before this session): a count-only check found a few low-sensitivity lab phrases in it that also occur verbatim in the private corpus — already in public history, which no agent can rewrite; reword-going-forward is yours to authorize.

*Named app-side residue, deliberately not built:* `RecordWorkbench`'s cross-view focus hand-off still polls (now bounded by 60 frames AND 3 s) because its destinations are rendered by child components; the 412 branch of the transcript finalize handler does a bare `loadRuns()` (a robustness gap, not a false claim); import sessions saved before the cardinality change keep old candidates until re-read (sessions are non-durable working areas); proposal action names kept ("Accept as Proposed / Reject… / More Actions") to avoid reopening the PR-D decision and its trusted e2e pins.


## Found on hosted after the redesign shipped — and fixed in this PR

Observed read-only on `v0.0.261`: a nonexistent record id rendered **"ISAAC Returned an Error"
(HTTP 503)** instead of "Record Not Found". The page's own network log showed every bundle request
answering `404 experiment_not_found` **except one `GET /evidence` → 503** in the concurrent burst —
while the same GET issued alone answered 404. Cause: each request runs its own ordinary-scope
restore pass (`workspace._hydrate_ordinary_scope` → `store.hydrate()`), a failed pass is
deliberately a `503` ("this server does not know whether the record exists"), and concurrent passes
were not serialized.

**The first hypothesis — an in-process race between two restores — was REFUTED** by the
implementing agent: the working-copy write was already a unique temp file + `os.replace`, and 8
concurrent reads against a healthy, uncapped fake store all answered 404 on the old code. **What
does reproduce the exact hosted shape is a connection limit** (PostgreSQL SQLSTATE 53300, "too
many clients"): against a limit of 2, the old code's 8 simultaneous passes gave 6×503 + 2×404.
The hosted body then discriminated it, read-only: 8 concurrent GETs of a nonexistent id returned
7×404 and **1×503 carrying `STORAGE_READ_FAILED_MESSAGE`** ("that database could not be read just
now") — a connection/`SELECT` failure, not an incomplete restore — with `/api/health` back at
`durable` immediately afterwards. The connection limit is the best-supported explanation; it was
not observed directly on the cluster.

**Fix (backend):** one restore pass at a time per process (a module-level lock); a request reuses
a pass only if that pass STARTED after the request arrived (so a row committed by another replica
is never missed); a failed pass is shared rather than retried by every waiter (a real outage no
longer stacks connect timeouts); genuine outages stay `503`, nothing became a `404`. A burst now
holds one connection at a time. On the way it closed a real gap: a restore could overwrite a
NEWER local working copy with an older stored document (the DB row is written before the file);
a restore now creates a working copy and never replaces one. 6 tests, each failing or measurably
different on the old code (`test_hydration_is_serialized.py`).

**Fix (frontend):** the primary record read decides the settled state (`primaryReadWins`): a
primary `404` is "Record Not Found" whatever else failed, and — the reverse race, which was worse —
a primary `503` is never mislabelled "Record Not Found" because a secondary read answered `404`
first. 9 tests; five failed on the old code.
