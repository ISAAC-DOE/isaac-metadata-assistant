# ISAAC Metadata Assistant — mentor brief

**For:** Angel, Dean, and ISAAC mentors · **From:** Krish Verma (intern)
**Repo:** `main`, clean, full test suite passing · see git history for the exact commit

A five-minute read. It says what exists, what the demo proves, what is deterministic vs.
assistant-driven, what is still synthetic, and which decisions I need from you. Nothing here
changes code — it is a review-and-direction checkpoint. Deeper docs are linked inline.

---

## 1. One-paragraph summary

The ISAAC Metadata Assistant turns scattered experiment metadata (spreadsheets, file listings,
notes) into a **validated, official ISAAC v1.05 record** plus a separate **evidence trail**, and it
**refuses to guess**. Anything a source doesn't support becomes a question for a human, not an
invented value. The deterministic core (extract → draft → validate → export → audit) runs with no
LLM and no knowledge graph; Claude and Graphify sit *around* it as an operator/assistant layer, never
as the authority on what is valid.

## 2. The problem (plain English)

A synchrotron catalysis experiment leaves metadata spread across a campaign spreadsheet, beamline
web forms, lab notes, and a file archive. Assembling that into a clean, machine-readable record that
matches the DOE-BES **ISAAC** "AI-ready record" standard is slow and error-prone. The obvious
shortcut — let an AI just *fill in* the record — is the wrong move for science: a plausible but
**invented** hash, unit, or peak energy is worse than a blank, because it looks trustworthy and
isn't. We want an assistant that drafts fast, **cites evidence for every value, and leaves the rest
blank as explicit questions**.

## 3. Current prototype status

A working, **synthetic**, end-to-end proof-of-concept for one path: **characterization / XANES-family**
(`record_type = evidence`). "Synthetic XANES" = *fake, sample XANES-style metadata* — a fictional
year-2099 SSRL session with fictional people — used so we get a realistic structured-metadata workflow
**with zero data-governance risk**. No real SLAC/SSRL data has been read, committed, or shown to any
model. XANES is just the example technique; the pipeline is the point.

- Maturity: **prototype / proof-of-concept**, ready to *demo and review* — not a production service,
  and not yet ingesting real beamline data.
- Source of truth: the **official ISAAC schema** (`schema/isaac_record_v1.json`, v1.05, vendored with
  pinned provenance). We do **not** author our own record schema.
- Delivery shape: a **local Python CLI + tooling pipeline** with Claude slash-skills wrapped around
  it. It is *not* just a Claude prompt, *not* a web app, and *not* an MCP server.

## 4. What the demo does

One command runs the real pipeline on committed synthetic fixtures:

```
synthetic sheet + file listing
   → evidenced draft            (26 fields, each with a source locator)
   → 5 pending blockers          (3 file sha256 hashes, the reduced spectrum, ≥1 descriptor — refused, not guessed)
   → human-confirmed answers     (the demo supplies these from a fixture; normally typed into /isaac-complete)
   → official ISAAC v1.05 record + evidence sidecar
   → schema validation + audit   (valid, evidence 33/33, 0 dangling)
```

The **5 refused blockers are the whole demo**: the extractor *knows* it needs three hashes, a reduced
spectrum, and a descriptor, and it will not invent any of them. Full walkthrough with expected
output: [`docs/demo.md`](demo.md). Live-meeting version: [`docs/demo-script.md`](demo-script.md).

## 5. What has been verified

- **The full test suite passes**, including: all 10 official golden records validate; export is
  doubly gated (no-guessing **and** official schema); every sidecar evidence path resolves; and the
  truth core **never imports Graphify** or the advisory warning seam (enforced by test).
- The demo regenerates the committed sample record `01JQZ0SYNTHXANESDEMO000000` **byte-for-byte**
  (`scripts/run_synthetic_demo.py`, step [5] asserts it).
- Result: 26 evidenced fields, 5 blockers refused-then-answered, valid against v1.05, clean audit
  (`evidence 33/33` — 25 scalar fields + 8 block targets: spectrum, QC verdict, 3 assets, 1
  descriptor, 2 contributors — 0 failures).
- **GitHub Actions CI** runs the test suite, the synthetic demo, official validation, advisory
  warnings, and the evidence audit on every push and PR to `main`.

## 6. Deterministic vs. assistant — who decides what

| Layer | Role | Decides validity? |
|---|---|---|
| **Official ISAAC schema + validators + export + audit** (`src/isaac_records/*.py`) | The **truth plane**. LLM-free, Graphify-free, reproducible. | **Yes — the only authority.** |
| **Claude slash-skills** (`/isaac-draft`, `-complete`, `-validate`, `-export`, `-query`) | The **operator layer** — drives the CLI, asks the blocker questions, explains results. | No. The CLI is the judge. |
| **Graphify** (memory/query plane) | Finds related docs/records, explains architecture, project memory, "what changed?". | No — cannot validate, export, or fill a scientific value. |
| **Portal-style soft-warnings** (`portal_warnings.py`, `--warnings`) | Advisory "you may want to look at this" notes, run *after* the hard gate. | No — **non-gating**, never blocks export. |

- **Claude/Graphify, concretely.** Today a technical user runs the CLI/demo and can use the Claude
  skills as an assistant. Graphify answers *memory/navigation* questions
  ([`docs/query-demo.md`](query-demo.md)); if a graph answer ever conflicts with the schema, a
  validated record, or the audit, **the deterministic source wins**.
- **Portal warnings, concretely.** A local seam (Phase 8) emits two schema-grounded advisory codes
  (`NO_LINKS`, `QC_NONVALID_WITHOUT_EVIDENCE`). It is **not** upstream portal parity — the real
  `portal/validation.py` is not vendored. See [`docs/portal-warnings.md`](portal-warnings.md).

## 7. What is intentionally NOT built yet (honest scope)

These are deliberate scope choices, not missed gaps:

- **Real/sanitized data** — not touched; requires explicit data-governance approval (D3/D4 below).
- **LLM-assisted extraction** of screenshots/PDFs/notes/web-form dumps — *designed*
  ([`docs/extraction.md`](extraction.md)) but **not implemented**; extraction is structured-only today.
- **True portal parity** — only a local non-gating seam exists.
- **Second domain** (e.g. electrochemistry/performance) — not built; one XANES path only.
- **Web app / MCP server / portal integration** — not built.
- **Advisory AI scientific review** — placeholder interface only, wired into nothing.
- **Graphify deeper query-layer** — the memory/query demo, routing, and graceful-degradation +
  freshness test tier exist; a deeper behavioral routing simulation is not built yet.

## 8. Decisions I need from you

Full detail, with recommended defaults and "if yes / if no" for each, is in
**[`docs/mentor-decisions.md`](mentor-decisions.md)** (D1–D8). The three that most shape next steps:

| # | Decision | My recommended default |
|---|---|---|
| **D1** | Is the evidence **sidecar** an acceptable ISAAC assistant convention? | Keep it; propose upstream as an *optional companion* file. It is **not** claimed to be an official ISAAC artifact today. |
| **D2** | Vendor the real **portal validator** for true parity, or keep the local non-gating seam? | Fine to keep the seam; vendor later, still non-gating. |
| **D3/D4** | May we process **real/sanitized** data, and may an **LLM** read it? | Stay synthetic-first; real data only with written, bounded approval; LLM-on-real only if separately approved. |
| **D6** | Which **domain** after XANES? | Performance/electrochemistry — it exercises the schema's conditional-required rules. |
| **D7/D8** | Final deliverable scope + paper emphasis? | Proof-of-concept + paper/poster; lead with *no-guessing* + *evidence sidecar* + *truth-vs-memory*. |

## 9. Recommended next step

**Do this review first.** The prototype is demo-complete; the next real fork is a mentor decision,
not more polish. If you want more technical work after review, the options are:

- **A — Presentation/final-deliverable polish.** Best if the deadline is close. Lowest risk; focus on
  paper/poster/figures. Outline ready: [`docs/final-deliverable-outline.md`](final-deliverable-outline.md).
- **B — Deeper Graphify query/memory layer.** Best if you want the AI-assistant story emphasized.
  Stays separate from validation/export truth.
- **C — Portal validator parity (D2).** Best if ISAAC portal alignment matters. Vendor/review the
  upstream `portal/validation.py`; keep non-gating unless you approve gating.
- **D — Second synthetic domain, likely electrochemistry/performance (D6).** Best if you want a link
  back to the original electrochem project. Safe — no real data needed.
- **E — Real/sanitized data pilot (D3/D4).** Best if realism is the priority. **Requires explicit
  written scope + governance approval first.**
- **F — Claude UX / command polish.** Best if the live demo feels clunky. No core changes.

**My default recommendation:** review now, then if mentors want more technical work, choose **B** (if
they care about assistant usefulness), **C** (if they care about ISAAC compliance), or **D** (if they
want the electrochem connection). **E** only after explicit data-governance approval.
