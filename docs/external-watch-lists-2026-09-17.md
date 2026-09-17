# External watch lists — Angel and Hao

**Created 2026-09-17.** Two lists, deliberately separate, because they are answered by two different
people about two different kinds of thing and a combined list invites the wrong person to guess.

**What this document is FOR:** so that a session can tell, mechanically, whether it is blocked. The
answer is almost always **no**. Every row below names what the answer *unlocks* — and if a row's
"unlocks" column does not name the work you are about to do, that row is **not** your blocker and
you should proceed.

**What this document is NOT.** It is not a claim that either person has been contacted, or has
replied. **This repository cannot witness a delivery** — `CLAUDE.md` §11 records exactly this trap,
where two documents sat described as "ready and UNSENT" while one had in fact been sent and the
other had been superseded. So no row here asserts a send state. **Only Krish can say what has been
sent.** What the repository can witness is *preparation*, and that is all that is recorded.

**A third category exists and is named rather than folded in:** several open items are **Krish's
own**, and a few have an **unknown** owner. Forcing them into one of these two lists would make them
look answered-by-someone-else. They are in §3.

---

## 1. ANGEL — unresolved **scientific** questions only

Angel is the domain owner. **Nothing on this list is a mapping, placement, or engineering question**
— `DEC-41` settled placement, and `DEC-47` settled the filename vocabulary. Each row below is a
judgement the corpus does not state and that no amount of parsing can recover.

**Nothing in the programme is blocked on any of these**, and that is a property of the design rather
than good luck: the import preserves literals, conflicts and unknowns, so it is safe to ship before
they are answered. An unanswered row leaves a value **absent** and a record **blocked** — never
guessed (`CLAUDE.md` §5).

| # | Question | What the answer unlocks | What happens meanwhile |
|---|---|---|---|
| **Q6** | Which `environment` member does the BL15-2 condition set belong to? | a **native v1.05 placement** (hierarchy level 1) instead of Extended Context (level 4) | preserved as structured Extended Context with its literal, source and locator |
| **Q7** | Which `reaction` member applies? | same — a level-1 placement | same |
| **Q8** | What cell type is `JK`? | a typed cell identity rather than a preserved token | the token `JK` is kept verbatim as the scientist's own vocabulary |
| **Q9** | The `JK` **reference electrode / potential scale** | **potential values become comparable across runs.** Until it is answered, two potentials from different scales must not be compared or converted | potentials kept as literals on their own runs; **no conversion is performed** |
| **Q11** | The **primary HERFD channel** | a canonical `reduced_spectrum` choice per run | no channel is promoted to primary; all are preserved |
| **Q14** | Does a given free-text note imply a **QC state**? | automatic `qc.status` from notes | `qc` stays a human answer; notes are preserved and never classified |
| **Q15** | **Source precedence** when three *different* sources disagree | a deterministic precedence rule | **all sources preserved, conflict surfaced, nothing auto-picks a winner.** Note `DEC-42` answers the *narrower* case of one document disagreeing with **itself**; it is **not** the answer to this |
| **Q16** | Was `runNo` **32** deliberately reused? Is `runNo` unique at all? | whether the two File-32 acquisitions can be ordered or one marked superseded | **both preserved, disagreement pinned in tests and provenance (`DEC-46`). Preferring either one is FORBIDDEN — including "because the beamtime document says so."** The document narrows it (`1400` occurs zero times in it) and narrowing is not answering |

**Also Angel's, and separate from the eight above:**

| ID | Item | Unlocks | Meanwhile |
|---|---|---|---|
| **EXT-09** | Classify the six `system.configuration.*` paths (Experiment-level vs Run-level) | exact write routing for those six | they remain `unclassified`, **verified**; those six plus `timestamps.created_utc` are the **7 paths no write route accepts**. **Blocks nothing else** |
| **EXT-10** | A representative BL15-2 corpus **plus expert ground truth** | the **parsers** and the evaluation harness — and *only* those | the import shell, source model, provenance, review integration, parser interfaces and synthetic harness all proceed **now**. `DEC-13` closed the pilot decision itself |

---

## 2. HAO — infrastructure, governance and operator requirements only

Hao is the addressee for what Dean previously owned. **Committed history keeps Dean's name** on rows
he answered or deferred — those records are of who acted, and rewriting them would destroy that.

**Nothing on this list is application code.** Every row is an act only someone with institutional
authority or cluster access can perform. **No row is a request for a secret value**, and none may
become one.

| ID | Item | What the answer/action unlocks | What is true meanwhile |
|---|---|---|---|
| **EXT-01** | **Trusted authentication boundary.** The Service is a plain ClusterIP with **no NetworkPolicy**, so any in-cluster pod can reach the app and forge forwarded identity headers (Dean, reconfirmed 2026-08-12) | `ACT-005` (a real actor on activity events), `attribution.uploaded_by` actually being stamped, submission acceptance, run-override attribution, and **every future sharing/ACL feature** | the actor reads **`unattributed`**, honestly. `record_attribution.py`'s `trust_basis == verified_edge_assertion` gate exists and **no verifier in this build mints that basis**, so the seam is unset **by construction**. Acceptance answers `409 human_actor_required` — a **configuration** fact, not a build defect. **No authorization is derived from any forwarded header, ever** (`DEC-45`) |
| **EXT-02** | **Remote MCP reachability + the OAuth model** (Dean's `D1`/`D2`, deferred 2026-08-12) | `Connect Your Agent` showing a **real** connection; an external agent reaching ISAAC | `GET /api/mcp` **404s** when unmounted, with `mcp.posture: "unmounted"` — an absent route, not a broken one. All 16 tools, the policy, the OAuth resource server (disabled by default), bounds, idempotency and the change-feed sync are **built and tested** against deterministic fakes. **No screen implies a connection** (`ai-integration-decision-packet.md` §6) |
| **EXT-04** | **`D1`–`D9`**: model provider, credential, network path, billing, egress, retention, data policy, transcription provider | a **production** LLM and real voice→text | **DEFERRED by Dean 2026-08-12** — *"leave AI integration as future work"*. Every provider seam answers **`501 no_provider_configured`**. The owner separately authorized building against fakes, and that is done. **The Web Speech API is NOT a workaround** — in Chrome it routes scientist speech to a third party, which the egress boundary forbids |
| **EXT-05** | Is scientific speech/data approved to flow through the organization's Claude environment? | Claude-mediated capture **without** an ISAAC-owned ASR | distinct from `EXT-04` and **not** answered by it |
| **EXT-06** | **G2** — hosted per-record display | showing real record content in the hosted app | **CLOSED BY DEFAULT.** Hosted `record_display: "closed"`. Dean's guide requires the boundary be built into the read path from the start, not bolted on |
| **EXT-07** | **G3** — the five withheld aggregates | restoring `by_instance_path`, `distinct_structural_signatures`, the `total_link_count`/`dangling_link_count` pair, and `vocabulary_term_count` | all five are **withheld** and named in `dataset.withheld_pending_visibility_decision` — **confirmed by an inspected response body**, 2026-09-13. **Do not restore any of them without his answer** |
| **EXT-13** | **Governance decision on real historical file bytes** — retention period, storage location, data classification, deletion path | real BL15-2 file bytes reaching a server | `POST /api/uploads` is an **unconditional 403**, pinned with its polarity by `upload-claim-parity.test.tsx`. **The blocker is server transmission/storage/retention — NOT local file selection**, which is why the local-only staging path is buildable today |
| **operator** | Apply the **three owner-approved migrations** and run the backfill | Stage-2b run reads; durable revision/submission history | **all three are owner-approved and NONE is applied anywhere** (`0003`/`0004` 2026-08-17; `0005` **2026-09-17**). The ordered eleven-step sequence is [`migration-approval-packet-0005.md`](migration-approval-packet-0005.md) §12A. **The backfill has never been run anywhere. No agent may perform any of the eleven steps** |

---

## 3. NEITHER LIST — Krish's own, or owner unknown

Named here so they are not mistaken for something an external reply will clear.

| ID | Item | Owner |
|---|---|---|
| **EXT-03** | Registering an **organization-wide** remote MCP connector | **Claude organization Owner / Primary Owner — identity UNKNOWN. Do not assume this is Hao or Dean.** `DEC-23`: a self-service *personal* connector is **not** an acceptable substitute for real SLAC data |
| **EXT-11** | Authenticated hosted QA; **true 200% zoom**; a real-microphone check; hosted narrow widths | **Krish.** None is automatable — **no CDP method can drive true zoom**, and `resize_window` reports success without moving the rendered viewport |
| **EXT-12** | Personal deployment retirement (Vercel + Railway) | **Krish.** Both still live and public; Railway has a **persistent volume**, so deleting destroys what pausing preserves |
| **DEC-48** | A dedicated Authentik logout affordance | **Krish — DECIDED 2026-09-17: not now.** Dean's answer that `/outpost.goauthentik.io/sign_out` is valid stays recorded. Honest consequence: a scientist on a shared workstation has **no in-app way to end a session** |

---

## 4. The operating rule

**Do not wait on either list while any independent application-side work remains**, and do not retry
or speculate about an answer. If a task's dependency is not named in an "unlocks" column above, it is
not blocked — build it, and say honestly what the absent answer leaves absent.

When only these rows remain, the correct report is **exactly what each answer will unlock** — which
is what the "unlocks" columns exist to make quotable.
