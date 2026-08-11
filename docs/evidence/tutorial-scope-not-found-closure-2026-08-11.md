# The stale tutorial-scope pointer was not a second `Record Not Found` defect

**Verdict: NOT REAL.** Closed with evidence on 2026-08-11, at `main` HEAD `77820bf`. No code was
written to fix it, because there was nothing to fix — and this document exists so the next session
does not re-open it, or worse, "fix" it by teaching the server to cross scopes.

**One genuine residual was found and is tracked separately.** It is a frontend *copy* defect, not a
truthfulness defect in the API. See §5.

---

## 0. Why this was investigated

PR [#113](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/113) fixed a real defect: a
durable-store hydration failure was being reported to the user as `experiment_not_found`, so a
*temporary infrastructure problem* was rendered as *this record does not exist*. That is a lie about
science, and it is the class of defect this project treats most seriously.

A second candidate of the same family was hypothesised: a **stale tutorial-scope pointer** — a
client retaining a reference to a worked-example record after its temporary scope ended, and being
told the record does not exist.

The hypothesis was worth testing and is **wrong**. What follows is the mechanism, not an absence of
evidence.

---

## 1. Scope is a directory namespace, not a filter

`apps/api/isaac_api/workspace.py:190-200` — `scope_root()` resolves a tutorial scope to
`<workspace>/_tutorial/<session_id>`. Exclusion from the ordinary workspace is therefore
**structural**: an ordinary read does not filter tutorial records out, it never looks where they are.

**Measured:** an ordinary `GET /api/experiments` returns `{"experiments": []}` while a live tutorial
session holds five canonical records.

## 2. Three independent mechanisms make the hypothesised defect impossible

### 2.1 The scope dependency never degrades to the ordinary workspace

`apps/api/isaac_api/routes.py:467-508` — `tutorial_scope`:

| Client state | Response |
|---|---|
| malformed session header | **422 `invalid_tutorial_session`** |
| unknown / expired session | **404 `tutorial_session_not_found`** |

The 404 body says verbatim *"This request was not answered from the ordinary workspace."* A stale
pointer therefore yields a **typed, different, honest** 404 — never `experiment_not_found`.

### 2.2 The client discriminates on the reason, deliberately

- `apps/web/src/lib/api.ts:303-315` — `httpErrorWithReason` lifts the 404 body's `error` into
  `ApiError.reason`.
- `apps/web/src/components/FetchStates.tsx:324-341` — the `Record Not Found` panel renders **only**
  for `reason === 'experiment_not_found'`, or for a bare record path with no reason.
- `FetchStates.tsx:316-321` documents the exclusion in the source: `tutorial_session_not_found` *"is
  raised by the scope dependency BEFORE any record work happens … so it is evidence about a dead
  worked-example session and none at all about whether the record exists."*
- `apps/web/src/lib/tutorialController.ts:345-366` re-validates the pointer on **every** boot and
  **deletes** it on the typed 404, surfacing `sessionError: 'expired'`. So it cannot reproduce
  indefinitely from storage.

### 2.3 No user-created record can ever be in a tutorial scope

`apps/api/isaac_api/routes.py:1837-1854` — `create_experiment_route` refuses creation inside a
tutorial scope with **409 `ordinary_scope_required`**.

**This is what bounds the blast radius.** Only the five committed synthetic canonical ids can ever be
involved. **A scientist's own experiment cannot be misreported by this path at all.**

## 3. Measured state transitions

Run against `create_app()` via `TestClient` over `tempfile.mkdtemp()` workspaces. Synthetic
fixtures only.

```
B. POST /api/tutorial/sessions              201  5 canonical ids, ttl_hours=24
C. GET  /experiments/{id}  + header         200  (in scope)
D. GET  /experiments/{id}  NO header        404  {"error":"experiment_not_found", …}
                                                 session dir still on disk? True
E. GET  /experiments/{id}  DEAD header      404  {"error":"tutorial_session_not_found", …
                                                 "This request was not answered from the
                                                  ordinary workspace."}
G. GET  /experiments/{id}  malformed hdr    422  {"error":"invalid_tutorial_session", …}
```

**Case E is the hypothesised defect, and it is closed by its own status body.**

## 4. The reachable case is the *inverse*, and its 404 is truthful

Case **D** is real and reachable. The durable carrier of a tutorial-scoped id is **not** storage — it
is **the URL**. `apps/web/src/App.tsx:22` and `apps/web/src/lib/routes.ts:125-128` route
`/record/:id`, and `tutorialSteps.ts:187-307` navigates the walkthrough to `/record/<canonical id>`
via a history **push** (`GuidedTutorial.tsx:176`). Client storage holds no record id at all — only
`isaac.tutorial.session.v1` = `{sessionId, index}` (`tutorialSession.ts:25-32`). So a bookmark, a
pasted link, or a back-navigation can carry a worked-example id into an unscoped tab.

**That 404 is correct, and it is not the #113 family:**

- The session id is `secrets.token_urlsafe(16)` (`workspace.py:3796`) and lived only in the dead tab's
  `sessionStorage`. **There is no scope that client could address in which the record is visible.**
  The 404 is terminal *for that client*, not premature.
- Refusing to cross scopes is the guard, not the bug — `workspace.py:3589-3592`: a canonical id in the
  normal scope resolves to `None`, *"which is what makes a normal-scope request for one a 404 rather
  than a silent cross-scope read."*
- **#113 was different in kind.** There the record **was** reachable — a durable row existed and
  hydration would have found it — so the 404 was premature. Nothing here is premature.
- The project had already considered and pinned this case:
  `apps/web/src/__tests__/tutorial-session-lifecycle.test.tsx:995-1042`, *"a deep link to an example
  record with no session fails safely."*

Two further guards found: `apps/web/src/lib/workspaceScope.ts:74-78` (`useWorkspaceScopeChanged`)
bounces all four record screens to My Experiments on a scope change, and
`ExperimentsHome.tsx:130-131` keys the list fetch on scope.

**`POST /api/demo/reset` cannot participate.** Measured: without the header **409
`tutorial_scope_required`**; with it, `preview` then `execute` both 200, `final_count: 5`, the same
five canonical ids re-materialised, and the session directory still present with all records reading
200. Reset addresses only `scope_root(scope)` and never disposes the session, so it cannot orphan a
pointer.

## 5. The one genuine residual — a copy defect, tracked separately

`FetchStates.tsx` explains the panel as *"This experiment id is not in the workspace — **it may not
have been created yet**."*

**There are TWO variants of that string, not one**, and a fix must handle both — this was refined
from the investigation's report after re-reading the file, because a fix that changed only one would
leave the defect live in the other environment:

```
hosted ? 'This experiment id is not in the workspace — it may not have been created yet.'
       : 'This experiment id is not in the local workspace — it may not have been created yet.'
```

For a worked-example id after a completed walkthrough, the record **was** created. The hedged "may"
is not literally false, but it is the wrong explanation and reads to a scientist as a malfunction
rather than as *that temporary workspace has ended*.

**Most reachable trigger:** `finishTutorial` (`tutorialController.ts:552-563`) disposes the session
and navigates to `/experiments`; pressing **Back** remounts `/record/<canonical id>` with scope
`null`. `useWorkspaceScopeChanged` is a **delta** detector and structurally cannot fire on a cold
mount (`null → null`), so no bounce occurs. All ten per-record reads return `experiment_not_found`
unscoped (measured), so the panel is deterministic rather than a `Promise.all` race.

**If this is fixed, the fix is frontend-only copy and routing.** Do **not** make the server cross
scopes, and do not teach it to disclose that a canonical id exists elsewhere — that would undo
`workspace.py:3589-3592`, which is the guard this whole investigation vindicated.

## 6. Commands run

| Command | Result |
|---|---|
| `PYTHONPATH=apps/api .venv/bin/pytest apps/api/tests/test_tutorial_scope.py -q` | **88 passed** |
| `npx vitest run tutorial-session-lifecycle backend-down-state workspace-scope-invalidation` | **83 passed, 3 files** |
| three scratchpad repro scripts (scope mismatch / stale pointer / reset) | outputs in §3, §4 |
| `git status --porcelain` | **0 changes** — the investigation wrote no code |

## 7. Measured vs inferred

**MEASURED** — every status code and body in §3 and §4; the session directory surviving a scope
mismatch; all ten per-record reads returning `experiment_not_found`; the 409 create refusal;
`TUTORIAL_TTL_HOURS = 24` (`workspace.py:148`); every `file:line` cited; both suite results.

**INFERRED, and labelled as such** — that `sessionStorage` is per-tab and absent in a pasted-URL tab
(HTML specification, not measured here); that a back-button remount does not trip
`useWorkspaceScopeChanged` (follows from the `useRef(scope)` at mount, `workspaceScope.ts:76`; no
test was written for it).

**NOT OBSERVED.** No hosted behaviour is claimed. `/krish` sits behind an Authentik edge this
environment cannot authenticate to, and no rendered pixels were inspected in any browser.

**Data governance.** Synthetic only — five committed synthetic fixtures through `TestClient` against
temporary directories. **No database connection was opened during this session.** No network access,
nothing under `examples/` read, and the truth path (`src/isaac_records/**`, `schema/`) neither
touched nor modified.
