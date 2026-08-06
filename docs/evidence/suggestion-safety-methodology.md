# No-guessing suggestion safety — methodology and findings

**Date:** 2026-08-06 · **Branch:** `feat/suggestion-no-guessing` · **Reviewed SHA:** `4f845ea` (PR #64)

The record-verification programme proves the system **detects** schema deviations. It says nothing about
whether the system **invents values**. That is a separate property, and auditing it found two real
defects.

**There is no LLM in this codebase.** Confirmed, not assumed: a grep for `openai|anthropic|langchain|
litellm|transformers|torch|huggingface|cohere|mistral|ollama` across `apps/`, `src/` and `pyproject.toml`
returns zero import or dependency hits. `assistant_query.py` matches lowercase substrings against a finite
trigger catalog — no scoring, no model.

**No production-derived record was read, held, or transmitted by this work.** Testing used public upstream
examples, generated fixtures, and synthetic adversarial cases only.

---

## 1. The governing invariant

ISAAC may offer a concrete value **only** when it is uniquely inferable from existing record data, schema
semantics, validated evidence, or another explicitly approved deterministic source. When information is
missing, ambiguous, contradictory or not inferable, it must not guess.

## 2. The two defects found

### D1 — the walkthrough's fabricated science was served for every record

`apps/api/isaac_api/serialize.py::_demo_answer_for` read `tests/fixtures/synthetic/
xanes_completion_answers.json` **unconditionally** on the `series` and `descriptor` branches, and offered
its contents as the suggested answer to a scientific question about **any** record — a 7-point spectrum
and `descriptor.value = 9001.2 eV, uncertainty.sigma = 0.01`.

`routes.py` documented the behaviour as *"for the built-in examples only"*. **That boundary did not exist
in the code.** Only the `asset` branch was incidentally scoped, because it happens to key on URI.

This is the exact failure `CLAUDE.md` §5 exists to prevent: invented scientific values presented as an
answer, beneath a comment asserting a guard that was not there. No test caught it, because the tests
asserted that a suggestion **appeared** — not that it was **earned**.

**Fixed:** `example_scope` is now a required-in-practice keyword defaulting to `False` (fail closed), gated
on the same `CANONICAL_IDS` that reset already enforces, and the example carries
`provenance.is_evidence_for_this_record: false`. The documented sentence is now true by construction.
Independent review confirmed closure by checking all four call sites and establishing that a user record
**cannot** acquire a canonical id: `create_experiment` has no caller in the API package, uploads are
refused, `csv_ingest` is preview-only, and `POST /api/demo/run` derives its target server-side.

### D2 — the client invented a schema-governed value

`apps/web/src/lib/adapt.ts` stamped `technique = 'Cu K-edge XANES'` onto every row client-side.
`technique` is `system.technique`, **an enum in the official schema**, and no endpoint sends it. It was
never rendered — which is luck, not design.

**Fixed:** constant deleted, field made optional. Absence is the honest representation.

## 3. Inferability states

```
supported_suggestion | needs_user_input | ambiguous | contradictory_evidence | not_inferable
```

A concrete value may exist **only** for `supported_suggestion`, and only with provenance naming the
supporting fields, the applied rule, uniqueness, and why alternatives were excluded. Enforced in
`__post_init__`, so a violating object cannot be constructed.

**Refused as evidence** — each with a test: model confidence, heuristic confidence, statistical priors,
"commonly used", population defaults, **a value found in another record**, **tutorial or example content**,
and schema defaults/enums/examples. A bare `confidence`/`probability`/`score` key is refused separately,
and the scan is **depth-bounded recursive** — the top-level-only version passed
`{"uncertainty": {"confidence": 0.86}}`, which is the exact nesting this repository's own corpus uses at
`tests/fixtures/official/operando_xanes_co2rr_record.json:242-244`.

`detail` is a **per-state allowlist with declared types**, deep-frozen (lists → tuples, dicts →
`MappingProxyType`). An earlier version was a four-key denylist behind a docstring claiming *structural
impossibility*; `frozen=True` blocks rebinding but not writing **through** a dict, and
`{"candidates": ["Cu","Fe"], "most_likely": "Cu"}` was accepted on an `ambiguous` result. The mechanism was
fixed and **the impossibility claim was deliberately not restored** — the docstring now states what holds
and names the residual.

## 4. Negative-control methodology

A test that cannot fail is worse than no test, because it reads as coverage. Every guard here was proven
by **injecting the defect it claims to catch and confirming the test fails**, then reverting.

Eight controls, all confirmed: guess the most common value; select one of several ambiguous candidates;
infer from an absent field; copy a value from another record; treat tutorial data as evidence; return a
concrete value with no provenance; persist a suggestion without acceptance; remove the example-scope gate.

Independent review re-ran six of them **against the fixed code** — a control that only bit the old code
proves nothing about the replacement.

**One control initially passed, which is how a real gap was found.** Promoting a QC blocker to
`supported_suggestion` did not fail, because the dispatch silently ignored the table's state column. The
guard was tightened to raise on a value-bearing state, and it now fails.

## 5. Two defects in the test suite itself

**A test that could not fail.** `test_the_pending_endpoint_survives_unknown_evidence` claimed to exercise a
defect *"over HTTP against a real record"*. A reviewer replaced `infer_all`'s entire body with an
unconditional `raise` and the test **still passed** — the same commit had removed the only caller. Deleted
and replaced with two tests that call `infer_all` directly on the real canonical seed. Both fail under
that probe.

**The positive assertion nobody had written.** `infer_all` swallows `UnsupportedSuggestion` per rule and
degrades to `not_inferable`. Every existing test asserted a **refusal** — which is exactly what a totally
broken rule engine also produces. The whole suite could have stayed green while the rules silently died.
A test now asserts the canonical seed still yields `supported_suggestion`; emptying `supporting_fields` in
`absorbing_element` fails it. Under the old suite that edit was invisible.

## 6. What is live, and what is not — stated because it is easy to overstate

**Measured: 344 of `inferability.py`'s 866 lines have no production caller.** Exactly one function is
live — `blocker_inferability`, one call site at `serialize.py:267`, rendered at `GuidedPrompt.tsx:99-104` —
and it can only return `needs_user_input` or `not_inferable`.

So **no `supported_suggestion` can currently reach a client**. The module's original opening line — *"the
single place that decides whether the app may put a concrete value in front of a user"* — was wrong, and
now says so. The app's only concrete unsupplied value is `demo_answer`, decided in `serialize.py`.

What actually enforces no-guessing in the running application today is: the `example_scope` gate, the
deterministic truth plane, and the `If-Match` / `confirmed_by_user` acceptance contract. The inferability
vocabulary is a **tested contract awaiting a consumer**.

The unconsumed `inferences` response block was **removed rather than wired up** — it shipped concrete
values to no consumer and bypassed the client-side re-check. It was deliberately **not** re-wired to
manufacture a caller for the comment. A library with no caller is debt; a fake caller added to justify a
comment is a lie.

## 7. Private-data boundary

External-model suggestion generation was **not** run over any private record — there is no external model
in this codebase at all. The authorized 30-record phase is limited to official validation, format-aware
shadow validation, deterministic mutation verification, and privacy-protected aggregates. **That phase has
not executed.**

## 8. Verification

| Check | Result |
|---|---|
| `pytest apps/api/tests tests -q` | **2,268 passed, 2 skipped, 0 failed** |
| `npx vitest run` | **2,837 passed / 2,837, 119 files** |
| `npx tsc -b` | exit 0 |
| `tests/test_truthpath_characterization.py` | **77 passed** |
| Negative controls | 8 original + 2 vacuity probes + 1 frontend denylist probe, all bite |

`src/isaac_records/extract/draft_builder.py` was modified — `non_oxygen_elements()` extracted so "two
candidates" can be distinguished from "none". Proven **behaviour-identical over 20,023 differential
inputs, 0 mismatches**, by a reviewer that reimplemented `main`'s version and diffed rather than trusting
the "pure refactor" claim. Exported-record behaviour and official schema compliance unchanged. No file in
`CLAUDE.md` §13's frozen truth-path list was touched.

## 9. Residual

- `sanitizeInferability` mirrors the server's positive allowlist but deliberately **duplicates** rather
  than derives it: a guard whose job is to hold when the server's copy doesn't cannot take its rules from
  the server.
- `detail`'s allowlist type-checks each permitted key, but a field path in `missing` is a string and so is
  an element symbol. What is guaranteed is that every string a consumer receives arrived under a key whose
  meaning is declared. This limit is disclosed in the module rather than papered over.
- The value path being uncalled (§6) means its guards are unexercised in production. They are exercised by
  tests; that is a weaker claim and is stated as one.
