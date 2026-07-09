# Live demo script — ISAAC Metadata Assistant

A practical script to run in a mentor meeting. Target: **~5 minutes** of terminal, plus Q&A.
Everything below uses **committed synthetic fixtures** (a fake year-2099 SSRL session — no real
SLAC/SSRL data). Nothing here needs the network, an LLM, or Graphify.

Companion docs: [`docs/demo.md`](demo.md) (full expected output), [`docs/mentor-brief.md`](mentor-brief.md)
(the one-page context), [`docs/portal-warnings.md`](portal-warnings.md), [`docs/query-demo.md`](query-demo.md).

> **The one-sentence pitch to open with:** "This turns scattered experiment metadata into an
> official ISAAC record *without guessing* — anything it can't support from a source becomes a
> question for a human instead of an invented value."

---

## 0. Pre-flight (do this before the meeting)

```bash
git status -sb            # expect: clean, on main
.venv/bin/pytest -q       # expect: all tests pass
```

If `.venv` doesn't exist yet:

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
```

Have two files open in an editor as backup, in case you'd rather *show* than *run*:
`docs/samples/01JQZ0SYNTHXANESDEMO000000.json` and `…​.evidence.json`.

## 1. The money shot — one command, the whole pipeline (~60s)

```bash
.venv/bin/python scripts/run_synthetic_demo.py
```

**What to say while it runs:** "This runs the *real* pipeline — extract, no-guessing validation,
apply human answers, schema-gated export. The script only drives it; it defines no validation of its
own."

**Point at these lines in the output:**

- `[1] … -> 26 evidenced fields, 0 assets, 5 pending blocker(s)` — then the five `pending[...]`
  lines. **This is the heart of the demo.** Say: *"It knows it needs three file hashes, the reduced
  spectrum, and a descriptor — and it refuses to invent any of them. These become the exact
  questions the completion step asks."*
- `[3] … -> 0 pending remaining, 3 assets now resolved (sha256 supplied)` — *"A human supplied the
  hashes; here they come from a committed answers fixture standing in for that person."*
- `[4] official schema valid: True (ISAAC v1.05)` — *"The transform is gated — it won't export
  unless both the no-guessing checks and the official schema pass. There is no `--force`."*
- `[5] record byte-identical to committed sample: True` — *"Fully reproducible."*

## 2. Show the official record (~30s)

```bash
.venv/bin/isaac validate /tmp/isaac-demo/01JQZ0SYNTHXANESDEMO000000.json --official
```
→ `PASS — valid against official ISAAC schema v1.05`

Open `/tmp/isaac-demo/01JQZ0SYNTHXANESDEMO000000.json` (or the committed
`docs/samples/…json`). Say: *"This is a 100% standard ISAAC record — no assistant-only fields. It
would validate anywhere the official schema is used."*

## 3. Show the evidence sidecar + audit (~45s)

```bash
.venv/bin/isaac audit --records-dir /tmp/isaac-demo
```
→ `PASS  01JQZ0SYNTHXANESDEMO000000.json  (0 schema errors, evidence 26/26)`
→ `1 records audited, 0 failing official validation`

Open `…​.evidence.json`. Say: *"The official record has no slot for per-field provenance — its schema
is `additionalProperties: false`. So evidence lives in a **sidecar** keyed by the record's own
JSON-paths. `evidence 26/26` means every evidence entry points at a real field — zero dangling. The
audit is the deterministic check that the record is schema-valid **and** its evidence trail is
intact."* (Flag: the sidecar is an **assistant convention**, pending mentor approval — decision D1.)

## 4. Show the advisory portal warnings (~30s)

```bash
.venv/bin/isaac validate docs/samples/01JQZ0SYNTHXANESDEMO000000.json --official --warnings
```

Say: *"After the hard schema gate, there's an **advisory** tier — soft warnings that never block
export. Here it flags `NO_LINKS`: the record declares no relationship to other records. The exit
code is still 0 — valid record, informational warning. This is a **local seam**, not the real ISAAC
portal validator; vendoring that for true parity is decision D2."*

## 5. Explain the Graphify memory layer (talk, optional to run) (~30s)

Say: *"Separate from truth, there's a **memory/query plane** — a Graphify knowledge graph over the
docs and code. It answers 'where is the sidecar explained?' or 'what's related to this record?'. It
**cannot** validate a record, authorize an export, or fill a missing value — and the truth core is
tested to never even import it. If the graph ever disagrees with the schema or the audit, the
deterministic source wins."* Details/examples: [`docs/query-demo.md`](query-demo.md).

## 6. Close (~15s)

*"So: fast drafting, evidence for every value, an explicit refusal to guess, a record that validates
against the real ISAAC schema, and a separate audit-able evidence trail — all deterministic and
reproducible. Everything you saw is synthetic and single-domain by design; the open questions are in
the mentor brief."*

---

## What NOT to overclaim (say these honestly if asked)

- ❌ "It handles real beamline data." → **No.** All inputs are synthetic; real data needs governance
  approval (D3/D4). No real data has been read or shown to any model.
- ❌ "It reads screenshots/PDFs/notes." → **Not yet.** Extraction is structured-only today; the
  unstructured/LLM path is *designed* (`docs/extraction.md`), not built.
- ❌ "It's the official ISAAC portal validator." → **No.** We cover the hard schema rules; the
  soft-warning tier is a local non-gating stand-in, not upstream parity.
- ❌ "The sidecar is an official ISAAC artifact." → **No.** It's our assistant convention, pending
  your call (D1).
- ❌ "Graphify checks the records." → **No.** Graphify is memory/query only; it never decides validity.
- ❌ "It's a web app / MCP server." → **No.** It's a local Python CLI + Claude skills today.

## Likely mentor questions — short answers

- **"How do I know it isn't guessing?"** The extractor emits `pending[]` blockers for anything a
  source doesn't support, and a test asserts no finalized field lacks evidence. In the demo you *see*
  the 5 refused blockers before any human answer.
- **"What if the AI hallucinates a value?"** The AI never writes the record. The deterministic export
  does, and it's schema-gated. A human answer is stored as `user_confirmation` evidence, not as an
  AI guess.
- **"Is this locked to XANES?"** No — XANES is the one *implemented* path. The next domain (likely
  electrochemistry/performance) is decision D6; it exercises schema rules XANES doesn't.
- **"Why a sidecar instead of putting evidence in the record?"** The official schema is
  `additionalProperties: false` — no room for provenance. Sidecar keeps the record 100% standard and
  auditability intact. Whether ISAAC should adopt it is D1.
- **"Can it validate against the real ISAAC portal?"** Against the official **schema**, yes (the hard
  gate). The portal's **soft-warning** tier is a local stand-in until we vendor the real one (D2).
- **"Is any of this reproducible for a paper?"** Yes — one command regenerates the sample
  byte-for-byte; the full test suite passes; outline in [`docs/final-deliverable-outline.md`](final-deliverable-outline.md).
