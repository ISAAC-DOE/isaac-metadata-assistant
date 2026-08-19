# The four actor seams — what is built, what is blocked, and what is left

**Date:** 2026-08-19. **Status:** survey. Implements nothing.

**Why this exists.** The programme plan lists "actor plumbing" as one item with four seams —
`attribution.uploaded_by`, the Run-override actor, the submission actor, and the revision-history
actor — and treats it as remaining work. Measured against the code, that is **not** what is left:
one is done, two are effectively done, and one is **blocked by a deliberate refusal in the truth
core**. Writing that down is worth more than starting an implementation that would discover it.

Every claim below cites the code.

---

## 0. The precondition that governs all four

Dean **authorized** server-stamping the canonical Authentik username — **conditional on the request's
identity having been established through a trusted authentication boundary.**

**ISAAC has no such boundary**, and Dean confirmed why: the Service is a **plain ClusterIP with no
NetworkPolicy**, so any in-cluster pod can reach the app directly and **forge forwarded identity
headers**.

> **The presence of `X-authentik-username` alone is not proof of authenticated edge traversal.**

**So nothing may be stamped today, and nothing is.** Measured, not assumed
([`docs/evidence/2026-08-18-truthfulness-and-security-sweep.md`](evidence/2026-08-18-truthfulness-and-security-sweep.md)):
a create request carrying forged `X-authentik-username: attacker` and `groups: admin` returns `201`
and stores the username **nowhere**; `attribution` comes back `{}`.

`ISAAC_EDGE_TRUST_VERIFIER` is unset by default and
`identity.RECOGNISED_TRUST_BASES` is `{test_fixture, verified_edge_assertion}` — neither of which a
request can mint for itself.

---

## 1. Seam by seam

| Seam | State | Evidence |
|---|---|---|
| **Submission actor** | **DONE** | `routes.py:7729` — the submit route takes `Depends(require_human_actor("submit"))`. `0003_revisions` carries `subject`/`trust_basis` with a table-level CHECK that an attributed row names somebody and an unattributed row names nobody. |
| **Revision-history actor** | **DONE, via the same path** | revision rows are written by `submission_store.py` inside the submission, carrying the same `subject`/`trust_basis`. There is no second write path to attribute. |
| **`attribution.uploaded_by`** | **BLOCKED — and deliberately** | see §2 |
| **Run-override actor** | **NOT BUILT, and it needs a decision first** | see §3 |

---

## 2. `attribution.uploaded_by` is blocked by the truth core, not by missing plumbing

`identity.py:1109-1113` states it directly, in the docstring of the function that resolves an actor:

> **WHERE THE RETURN VALUE MAY NOT GO.** Not into `attribution.uploaded_by` via a draft. The truth
> core refuses a draft-authored value for that field by design (commit `bdff8f5`), and this function
> is not a way around that refusal — **stamping it would require a change *in the truth core*,
> reviewed on its own terms.**

`routes.py:4223` says the same from the route side: `attribution.uploaded_by` is *"a field no client
may author"*.

**So this is not a plumbing gap.** The value is refused at the layer `CLAUDE.md` §13 protects, and the
refusal is the feature: a client-authored `uploaded_by` is exactly the fabricated actor the whole seam
exists to prevent. Stamping it server-side is a **truth-path change** and therefore needs its own
slice, its own review, and the §13 disclosures — and it should not be attempted while §0's
precondition is unmet, because the first thing it would stamp is an unverifiable name.

**Recommendation:** leave it refused. Revisit only after a trusted boundary exists, and then as a
truth-core slice rather than as part of an identity slice.

---

## 3. The Run-override actor needs a storage decision before any plumbing

`workspace.Override` records `{payload, recorded_utc, displaced}` and **carries no actor field** —
verified: the string `subject` appears once in the whole of `workspace.py`, and not on `Override`.

So attributing an override is not a matter of passing a value through; it needs a decision about
**where the actor lives**, and each option has a cost:

1. **On the `Override` record in the experiment document.** Cheapest, but it puts an identity into
   the document that `to_state()` serialises everywhere the document goes, including into every
   revision snapshot — so a name would be copied into history that was never verified.
2. **In a separate append-only table**, like the submission and revision rows. Consistent with how
   this project already attributes durable acts, and **needs a migration** — which cannot be applied
   to the hosted database by an agent, and would queue behind `0003`/`0004` which are approved and
   still unapplied.
3. **Not at all until §0 is resolved**, and say so.

**Recommendation: option 3 for now, option 2 when the time comes.** Option 1 should be refused
outright: it would write an unverified name into immutable history, which is the one outcome the
attribution CHECK constraints in `0003` were written to make impossible.

---

## 4. What a future identity slice should actually do

Not "thread the actor everywhere" — most of that is done or blocked. What is genuinely left:

- **A service-principal shape** distinct from a human actor, so an authenticated service caller is
  representable without being mistaken for a person. Shape only; no auth scheme, no bearer
  validation — those are §0's job.
- **Strengthen the header guard.** `test_no_backend_module_names_an_identity_header` asserts that only
  `identity.py` may name an identity header. It is a **text scan**, so it catches the realistic drift
  and not a header read assembled by concatenation. Worth saying in the test rather than leaving the
  guarantee to be assumed.
- **A negative-control suite** proving that a forged header, forged groups, a client-supplied actor in
  a body or query parameter, and no headers at all are all **indistinguishable** in their effect —
  the absence of a difference being the property. The security sweep measured the first and the last;
  the middle two are unpinned.

None of that requires a migration, a truth-core change, or anything Dean owns.

---

## 5. What this survey does not claim

- It did not run the fixture verifier end-to-end; the `test_fixture` path is asserted by the existing
  suite, not re-measured here.
- It read `workspace.py` for an actor field on `Override` and found none. It did not audit every
  other record type for the same question.
- §0's measurement is an in-process probe. It says nothing about what an ingress does.
