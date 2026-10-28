# Local-first ISAAC: the three data flows, and what each needs before it may carry real data

*Written 2026-10-28 for the local-first workflow (`ISAAC_Skill_Plan_2026-10-28.md`, revised).
Status words used here: **implemented**, **planned**, **approved**, **awaiting approval**,
**tested**, **deployed**. Nothing in this document is deployed.*

The local-first workflow is three separate data flows. They are approved separately and must
never be described as one. **Local file access is not permission to send file contents to a
cloud model**, and **not uploading raw files is not the same as sending nothing sensitive.**

| Flow | Path | What leaves the scientist's computer | Approval it needs | Status |
|---|---|---|---|---|
| **A: local deterministic parsing** | scientist's Mac → `isaac import` (ISAAC's own code) → local bundle folder | **Nothing.** No network call. | Permission to hold and process the files on that computer (data owner; SLAC policy for laptops: open question **H5**) | implemented (this branch), tested on synthetic fixtures only |
| **B: Claude model interpretation** | scientist's Mac → Claude Code → Claude model service | **File contents or excerpts** the skill chooses to show the model, plus the conversation | Institutional approval that this Claude account/tenant may process this data class. The data owner's OK is necessary but may not be sufficient (see below) | planned; tested on **synthetic** data only; **awaiting approval** for real data |
| **C: MCP transfer to ISAAC** | local bundle → remote MCP → ISAAC backend (SLAC) | Structured metadata, short source excerpts, hashes, relative file names, contributor names, scientist decisions | MCP reachability + login decisions **D1/D2** (Dean/Hao); classification of what may be stored on the server (**EXT-13**); a reviewed bundle-import tool | **design only** (`docs/mcp-staged-bundle-import-design.md`); not implemented, not deployed |

## Flow A — local deterministic parsing

- Runs entirely on the scientist's machine with ISAAC's existing reconstruction code: the same
  `historical_import.read_archive` the hosted site uses.
- It reads files and never executes them (macros are read as text). It reuses the importer's
  ceilings, its symlink and traversal refusal, and its ZIP-slip and decompression limits.
- **Output stays local.** Bundle source references are relative paths plus hashes. An absolute path
  is recorded only if the user explicitly asks (`--record-local-root`).
- **What still needs answering for real data:** whether SLAC permits a scientist's beamline files to
  be processed on a personal or managed laptop. This is open question **H5**, and Hao owns it.
  Angel's OK as data owner covers his own data. It does not answer the institutional question.

## Flow B — Claude model interpretation

- Whenever the skill asks Claude to read a file or an excerpt, **that content goes to the model
  service.** That is true even though the file never leaves the disk in any other sense.
- **The skill minimises flow B by design:**
  - It reads the compact summary first.
  - It looks up specific runs and conflicts on demand.
  - It shows the model only the excerpts a question needs.
  - It records every excerpt shown in the bundle's `ai_interpretations[]`, with file and locator.
- **Who can approve real data here.** All of these may be required:
  - the data owner (Angel, for Beamline 15 data he owns);
  - SLAC data governance, which decides the data class and whether it may go to an external
    processor;
  - the administrator of the Claude tenant the scientist uses, who confirms the contract covers
    this data and states its retention terms.

  Angel has said in conversation that SLAC Claude accounts may read the files (relayed by Krish,
  28 Oct). That is recorded as a **data-owner statement**, not as institutional approval.
- **Until approval is written down:**
  - model testing uses **synthetic fixtures only**;
  - real files may go through flow A only where the H5 policy permits it;
  - no real source content is shown to Claude;
  - flow B is not routed through another provider either (browser speech recognition, other AI
    services).
- Synthetic fixtures safe for flow B: `tests/fixtures/bl15/semantics/multi_operator_corpus/` and
  `tests/fixtures/historical_import/`. **Not** `tests/fixtures/bl15/notes/` or
  `tests/fixtures/bl15/gold/mini_corpus/`: they carry a pending governance flag because they share a
  sentence with a real archive. The deterministic code may run over them in tests; the model should
  not be shown their text.

## Flow C — MCP transfer to ISAAC

- Even with no raw files, a bundle can still carry sensitive material:
  - sample names, operator names, timestamps and conditions;
  - short source excerpts and file names;
  - scientist decisions.
- The importer will accept **only** what the website needs to show and review candidates:
  - excerpts are bounded;
  - local-only references stay local-only, because a path on a scientist's Mac is not a server-side
    file the backend can open;
  - hashes are kept.
- Transfer creates **draft content and open suggestions only**, never accepted values, and never a
  Submit or Export. See the MCP design.
- **Needs before real data:**
  1. **D1/D2:** may the MCP endpoint be reachable from outside, and with which login model?
     Deferred since 12 Aug.
  2. **EXT-13:** SLAC's rules for what may be stored on the server (classification, retention,
     deletion).
  3. The reviewed importer itself.

## Reporting rule

Every session that touches input files reports, per CLAUDE.md §6:
- what was read;
- synthetic or real;
- **whether a model saw it (flow B)**;
- whether anything left the machine (flow C).
