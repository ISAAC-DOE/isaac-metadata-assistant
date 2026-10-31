# MCP staged bundle import: design for a later, separately authorized implementation

*Status: **DESIGN ONLY, written 2026-10-28.** Nothing here is implemented, registered as an MCP
tool, or deployed. Implementing it needs Krish's approval of this design and a security review.
Mounting it in production needs Dean/Hao (D1/D2). Code facts were measured at `69982fb9`.*

## 1. Why a new capability, and why not a "whole-record write" tool

Today's MCP server (`apps/api/isaac_api/mcp/`) exposes 18 closed-list tools:
- 12 read tools;
- `isaac_create_run` (one run, no idempotency key);
- `isaac_update_draft` (7 run fields plus blocking-question keys);
- `isaac_answer_questions`;
- `isaac_capture_note`, `isaac_capture_transcript`, `isaac_propose_field_value`.

It cannot create an experiment, add many runs at once, attach evidence, or load a bundle.
`policy.FORBIDDEN_TOOL_TOKENS` (`policy.py:207`) bans `accept`, `approve`, `submit`, `export`,
`finaliz`, `publish`, `delete` and similar tokens. Every tool must also be listed in
`PERMITTED_TOOL_NAMES` (`policy.py:~1370`): *"adding a tool is a reviewed change to that set, not a
registration."*

**Rejected: one tool that writes a finished record.** It would turn a scientist's local draft into
accepted values with no human review on the site. That breaks the two-actor rule (`DEC-37`: an
import *applies nothing*). It also breaks the trusted-actor gate on Accept (`routes.py:16022`).
Choosing a name that avoids the forbidden tokens does not make a tool authorized; the closed list is
the safety boundary.

**Chosen: a staged protocol** that reuses the server's existing review model. A bundle becomes:
- an experiment;
- runs;
- **open proposals**, each carrying its evidence;
- **inert notes** for statements nobody mapped;
- read-only evidence for conflicts and gaps.

That is exactly the model `POST /api/imports/{id}/add-to-experiment` already uses for website
imports.

## 2. Protocol

```
check  →  preview  →  commit  →  result
```

| Step | Tool (proposed names, in no forbidden token) | Scope | Writes? |
|---|---|---|---|
| **check** | `isaac_check_import_bundle` | `isaac:read` | **No.** Validates the bundle against `bundle-v1.schema.json`, its bounds and its states. Returns typed findings. |
| **preview** | `isaac_preview_import_bundle` | `isaac:read` | **No.** Returns exactly what commit would create: experiment, runs, N proposals by target path, notes, refused items with reasons, possible duplicates of existing records, plus a `plan_digest` over (bundle hash + target state). |
| **commit** | `isaac_stage_import_bundle` | `isaac:draft.write` + `isaac:proposals.write` | **Yes**, atomically. Requires `plan_digest` (428 if absent, 412 if stale, the precedent from the reset gate) and a `client_request_key`. |
| **result** | the existing `isaac_get_experiment`, `isaac_list_proposals`, `isaac_list_activity` | read | No |

**Atomicity.**
- A new experiment: commit runs inside one `record_lock` and one versioned save, the same way the
  `add-to-experiment` batch does. The record holds the whole bundle or none of it.
- An existing experiment: only with an explicit `experiment_id` plus `If-Match`. A wildcard `*` is
  refused (the discard-route precedent).
- If a multi-run apply cannot be guaranteed atomic for some target, commit **refuses** rather than
  applying part of the bundle. That partial-failure rule follows `DEC-37`: whatever the caller can
  fix refuses the whole batch.

**Idempotency.**
- `client_request_key` plus the bundle hash is stored on the created experiment.
- A replay with the same key and same hash returns the original result (200, `replayed: true`).
- The same key with a different hash returns 409 `request_key_reused`.

**Duplicate detection.** Preview flags an existing experiment whose stored import fingerprint (the
bundle's source-manifest hash set) overlaps. Commit refuses to create a second copy unless the
caller passes `duplicate_acknowledged: <experiment_id>`.

## 3. What a bundle may become on the server

| Bundle content | Becomes | Never becomes |
|---|---|---|
| `candidate_extracted` / `needs_review` with a write route | **open proposal**, with method `deterministic_parser` or `stored_rule`, plus evidence | an accepted field value |
| AI suggestion (`method: ai_interpretation`) | **open proposal** labelled "suggested by AI", with its excerpt and model id | an accepted value, or a source "witness" equal to a file |
| `conflicting` | proposal **withheld**, conflict shown read-only with every witness | a picked value |
| `scientist_decisions[]` made locally | **a claim attached to the proposal** ("confirmed locally by `<name>`, unverified") | an acceptance. Acceptance needs a verified human on the site (§5) |
| `unmapped` statements | inert notes (existing `notes` model) | field values |
| `missing` | an open question | a default |
| source references | relative name + sha256 + `local_only: true` | a URI the server pretends it can open |

Exported official records are never touched; `record_exists` (409) stays.

## 4. Bounds (enforced before any parse beyond the size check)

The bundle schema caps (`apps/api/isaac_api/local_import/bundle.py`) apply first. The server then
enforces its **own**, stricter caps:
- total request bytes;
- runs per bundle;
- proposals per bundle (≤ the existing `add-to-experiment` batch size);
- evidence entries per candidate;
- characters per excerpt;
- characters per string.

Path, type and ID validation follows `bundle-v1.schema.json`. All target paths must be in
`PROPOSAL_TARGET_PATHS` (now in the neutral `field_paths` module). Unknown keys are refused, not
ignored.

## 5. Identity, attribution and Activity

- The MCP OAuth binding verifies a bearer JWT: signature against JWKS, `iss`, exact `aud`, `exp`,
  `nbf`, non-empty `sub` (`mcp/jwt.py:600-647`). It maps the result to a `ServicePrincipal` with
  **no subject**, which "can never be an author" (`oauth.py:1115-1140`). **This design keeps that.**
- New Activity event types, kept apart on purpose:
  - `bundle_staged`: "Claude Code staged import bundle `<id>` on behalf of authenticated account
    `<sub>`; N proposals, M notes, K conflicts". The connector's account is recorded as **transfer
    provenance**. It is **not** an author or approver of any value.
  - `proposal_accepted` (existing): only from a verified human on the browser path. That needs the
    browser identity boundary (signed edge assertion or NetworkPolicy, then
    `TRUST_BASIS_VERIFIED_EDGE_ASSERTION`).
  - **A verified OAuth subject is never turned into "scientist accepted value".** Recording the
    `sub` as transfer provenance needs Dean's sign-off. It is a change to what Activity stores,
    though not to who may approve.
- Final Submit and Export stay outside MCP (forbidden tokens, unchanged).

## 6. Tokens

- Short-lived access tokens; exact audience; issuer check; scope enforcement; RS256+ only.
- JWKS supplied as a projected file (`jwks-url` is refused by design).
- **No revocation or introspection exists.** A token stays valid until `exp`. That limitation is
  documented and stays; the mitigation is short lifetimes, not an invented revocation check.

## 7. Tests the implementation must ship with

- check and preview never write (store byte-identical);
- commit without or with a stale `plan_digest` → 428 / 412;
- replay → same result; key reused with a different hash → 409;
- over-bound bundles refused before parse;
- unknown keys refused;
- target paths outside `PROPOSAL_TARGET_PATHS` refused;
- no proposal is created in `accepted`;
- `scientist_decisions` arrive as claims, not acceptances;
- conflicts create no proposal;
- missing values create questions, not values;
- exported records are untouched;
- a `ServicePrincipal` cannot accept or submit (`service_principal_not_attributable`);
- tool names pass `forbidden_tool_reason` and appear in `PERMITTED_TOOL_NAMES`;
- a partial-apply fault leaves the store unchanged;
- `bundle_staged` Activity carries no value-approval semantics.

## 8. Operator actions (Dean/Hao), in order, after implementation and review

1. Decide **D1** (reachability) and **D2** (login model).
2. Configure an Authentik OAuth provider: PKCE S256, DCR or a static client, redirect URIs for
   Claude, short token lifetime.
3. Set `ISAAC_MCP_DEPLOYMENT=oauth-resource-server` and the `ISAAC_MCP_OAUTH_*` values, with JWKS
   as a projected file.
4. Let `/krish/api/mcp` through the login redirect, and allowlist the connector's address range per
   `docs/mcp-oauth-operator-requirements-2026-08-27.md`.
5. Run `docs/mcp-operator-preflight.md`.
6. Answer **EXT-13** for which bundle content may be stored.
