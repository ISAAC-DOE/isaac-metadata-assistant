# Truthfulness and security sweep — 2026-08-18

**What this is.** The scientific-truthfulness sweep and the adversarial security sweep the
programme's definition of done requires. Every line below is **measured** — each claim names the
command or the `file:line` that establishes it. Nothing is asserted from reading a summary.

**What it is NOT.** It is not a proof that the categories it clears are clean *in general*. It is a
record of specific probes against a specific commit, and the limits of each probe are stated with it.

Commit swept: `7105c0a`.

---

## 1. Security — measured, not reviewed

### 1.1 A fully forged edge identity stamps nothing

Every header the Authentik edge is documented to inject was forged on a record-creating request:
`X-authentik-username: attacker`, `X-authentik-groups: admin`, plus `uid`, `email` and `X-Isaac-Edge`.

```
POST /api/experiments  → 201
forged username stored anywhere in the record document: False
attribution block:                                      {}
```

The forged username reaches **no** stored field, and `attribution` is empty rather than populated
with a name nothing vouched for. This is the fail-closed behaviour
[`docs/identity-trust-contract.md`](../identity-trust-contract.md) requires, and it is the property
that matters most, because Dean confirmed the Service is a plain ClusterIP with no NetworkPolicy —
**an in-cluster caller can forge these headers**, so presence must never imply authentication.

Corroborating: `ISAAC_EDGE_TRUST_VERIFIER` is unset by default, and
`identity.RECOGNISED_TRUST_BASES` is `{'test_fixture', 'verified_edge_assertion'}` — neither of which
a request can mint for itself. **Nothing may be stamped until a trusted boundary exists, and nothing is.**

**Limit:** this probes the in-process app. It says nothing about what an ingress does, and it is not
a penetration test.

### 1.2 MCP is fail-closed

```
POST /api/mcp        → 404
POST /mcp            → 404
POST /api/mcp/tools  → 404
MCP paths in the served OpenAPI: []
```

No transport is mounted by default and no MCP operation is advertised. This is what
*"do not expose an unauthenticated hosted MCP route"* requires, verified rather than assumed.

### 1.3 No provider is configured, and the app says so

`GET /api/providers/capabilities` reports `any_provider_configured: false`, and every seam reports
`configured: false` with a reason in plain words — e.g. transcription: *"No transcription provider is
configured. Speech is not transcribed and no audio leaves the browser."* No surface implies a
provider exists. This matches Dean's deferral of D1–D9 exactly.

---

## 2. Scientific truthfulness — the categories, and what each check found

| # | Category | Verdict | Evidence |
|---|---|---|---|
| 1 | Fake `Connected` state | **clean** | every `Connected` match in `screens/`+`components/` is DOM `isConnected` or a graph-edge flag |
| 2 | Fake configured AI / transcription provider | **clean** | §1.3 |
| 3 | Submit success before durable commit; *"nothing was written"* after side effects | **clean — and previously defective** | see §3 |
| 4 | `Submitted` derived from Export | **clean** | `workflow.py` states the separation and consults no export state |
| 5 | Graph causal overclaim | **clean** | the disclaimer exists (`evidenceGraph.ts:135`) and is test-pinned (`evidence-graph.test.tsx:931`) |
| 6 | Unreadable/unknown evidence shown as supported | **clean** | `EVIDENCE_CLASS_CHIP` maps all six classes to six distinct chips, **no fallback** to `supported` |
| 7 | Fabricated actor | **clean** | §1.1 |
| 8 | Conflicts silently gating readiness | **clean** | `conflict_summary` carries `gating: "disclosed_not_gated"`; `workflow.py` consults no conflict state |
| 9 | Deployment blocker presented as scientific un-readiness | **clean** | `workflow.py`: *"INFRASTRUCTURE NEVER DOWNGRADES SCIENTIFIC READINESS"*, with a separate deployment block and a dedicated test |

---

## 3. The one category that was defective, and how it reads now

Category 3 is worth recording in full because it is the defect the master plan singles out.

A submit refusal used to say *"nothing was written and nothing was published again"* — **one sentence
for a refusal reachable from two places**: the preflight, before any official record is materialised,
and the write, after every one of them is. The sentence was true of the first and **false of the
second**.

It is now `_publication_disclosure`, and `_already_submitted`'s docstring records the reasoning:

> ``published`` DEFAULTS TO EMPTY AND IS NOT OPTIONAL AT THE POST-RACE CALL SITES. … The old single
> sentence … was true of the first and false of the second.

That is the shape a correction should take here: the wrong claim is quoted, not deleted.

---

## 4. A stale justification this sweep found and fixed

`workflow.py` justified conflicts-never-gate on the grounds that a conflict is something **"no
surface in this build can clear"** — so labelling the record *Needs Review* would trap it.

**That reason was invalidated by this repository's own work**: the conflict-resolution operations let
a scientist record which competing answer they stand behind. The *conclusion* is unaffected — gating
is a product decision no committed sentence authorises, and a `deferred` decision deliberately does
not clear a conflict while a `stale` one counts as unresolved — so the paragraph now rests on that
footing, with the retired argument quoted rather than removed.

This is the sweep's actual yield: not a false claim on a screen, but a **true claim whose supporting
reason had expired**. Those are harder to find and are exactly what a sweep against a moving codebase
should be looking for.

---

## 5. What this sweep did NOT cover

Stated so the table above is not read as broader than it is:

- **No hosted probe.** `/krish` returns `302` from this environment (Authentik edge); nothing here
  says what the deployed app renders.
- **No browser rendering pass.** Categories 1, 5 and 6 were checked at the source and mapping level.
  A screen could still *arrange* honest components misleadingly; that is the visual sweep's job.
- **No penetration testing**, no egress monitoring, and no check of anything outside this process.
- **Not every string in the app was read.** The categories were probed at the places the code
  concentrates them; a false sentence in an unvisited corner would not have been found.
