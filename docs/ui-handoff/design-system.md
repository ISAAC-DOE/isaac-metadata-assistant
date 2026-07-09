# UI handoff — design system direction

> Visual and interaction direction for a future Claude Design session. This is **direction, not a
> component library**, and **not** an implementation. It sets the feel, the visual grammar for the
> product's non-negotiable distinctions, and the guardrails a designer must not cross. Companions:
> [`screens.md`](screens.md), [`user-workflows.md`](user-workflows.md),
> [`ai-assistant-and-graphify.md`](ai-assistant-and-graphify.md).

## The feel

Premium **scientific infrastructure** software. Calm, trustworthy, technical but not intimidating.
Evidence-first. The product's whole value is that it **refuses to guess** — the UI must feel like a
precise instrument, not a magic box.

Deliberately **not**:

- a chatbot toy (the assistant is a helper, not the product);
- a generic admin dashboard (no vanity KPIs, no gauge clusters, no invented health scores);
- an over-automated black box (no "AI did it for you" theater; every value is traceable);
- a flashy AI product (no shimmer, no fake automation, no hallucination-vibe gradients).

Premium but **restrained**. The strongest visual signal in the whole product is the deterministic
verdict. Everything else defers to it.

## Layout principles

- **Workbench metaphor.** One record is the workpiece on the bench; the operator assembles it from
  evidence and runs a deterministic inspector. See the layout verdict in
  [`screens.md`](screens.md): left rail = gated workflow spine, main canvas = current artifact,
  right = evidence (truth) stacked above assistant/memory (advisory), status bar = the trust readout.
- **Artifact dominance.** The draft / record / sidecar is always the largest, calmest surface.
  Chrome recedes.
- **Truth and advisory never share space unlabeled.** Deterministic surfaces (fields, evidence,
  verdict) and advisory surfaces (assistant, memory, warnings) are visually separated at all times.
- **Generous whitespace, quiet density.** Scientific data is dense; the layout should breathe so the
  data doesn't feel like a spreadsheet dump.

## Typography

- **UI text:** a high-quality, neutral **sans-serif** with strong legibility at small sizes and a
  wide weight range (for status vs. body vs. label hierarchy). Direction, not a mandate — pick
  something that reads as serious instrumentation, not consumer-app playful.
- **Monospace for identifiers and data.** ULIDs (`01JQZ0SYNTHXANESDEMO000000`), sha256 hashes,
  URIs (`ssrl-archive://…`), JSON paths (`system.facility.beamline`), enum tokens, and any raw JSON
  must render in a mono face. This is a core trust signal: technical values look like technical
  values and are never "prettified".
- **Numbers:** tabular / lining figures for scientific values and uncertainties (e.g. `9001.2 eV`,
  `σ 0.01`) so columns align and values read precisely.
- **Restraint:** two families (sans + mono) is enough. No display/decorative fonts.

## Color semantics

Color carries **meaning**, not decoration. Three verdict families each get a distinct color
identity, and the assistant/memory accent is a fourth, kept clearly apart.

- **Deterministic verdict (hard gate):** PASS = a serious, grounded green; FAIL = a serious red.
  These two colors are **reserved** for the official validation verdict / export gate. They must
  **never** be reused for assistant content, warnings, or coverage.
- **Advisory warning:** a distinct amber/ochre, visually weaker than the verdict reds/greens.
  Non-gating by appearance.
- **Coverage (audit):** a neutral / informational tone (e.g. a calm blue-gray), clearly **not**
  green-PASS. `evidence 26/26` is information, not a verdict.
- **Evidence states:** verified / user-confirmed / inferred / missing / pending get their own muted
  chip palette (see below), kept off the verdict greens/reds.
- **Assistant / memory accent:** a single distinct accent (e.g. a cool violet or teal) used **only**
  for assistant/memory surfaces — never any verdict color. If the assistant is on a green surface,
  it looks like a verdict; that is forbidden.

**Accessibility, non-negotiable:**

- Never encode a distinction by hue alone. Pair every color with an **icon and/or text label** and,
  where possible, shape. PASS/FAIL, warning, and coverage must be distinguishable in grayscale and
  for color-blind users (avoid relying on red/green separation as the only cue).
- Meet WCAG AA contrast for text and essential UI against both light and dark backgrounds. The UI
  should be built theme-aware (light + dark) from the start.

## Card / chip / status system

- **Field status chips** (draft review, sidecar): `verified`, `user-confirmed`, `inferred`,
  `missing`, `pending`. Each = color + icon + short label. `missing` and `pending` read as **honest
  and expected**, never as errors — muted, not alarming.
- **Validation verdict card:** the single most prominent status element. Large, unambiguous
  `PASS` / `FAIL` with the schema version (`ISAAC v1.05`). One per record.
- **Warning chips:** `⚠ [CODE]` (e.g. `[NO_LINKS]`, `[QC_NONVALID_WITHOUT_EVIDENCE]`) as amber
  chips carrying the code in mono. Grouped, counted, clearly advisory.
- **Coverage badge:** `evidence 26/26` in the neutral coverage tone, adjacent to but visually
  distinct from the verdict card.

## Validation / audit / warning visual grammar

Three families, three visually distinct treatments — this is the most important visual rule:

1. **Hard gate (validation / export):** boldest, most saturated, largest. PASS/FAIL. This is truth.
2. **Coverage (audit):** neutral, informational, secondary weight. `evidence N/N`. Not a verdict.
3. **Advisory (warnings):** amber, tertiary weight, explicitly labeled non-gating.

A viewer glancing at the status bar must instantly tell these apart without reading. Never render a
warning that could be mistaken for a FAIL, or a coverage figure that could be mistaken for a PASS.

## Evidence highlighting

- Evidence is a **first-class, deterministic surface** — treat it with the same seriousness as the
  verdict, not as a tooltip afterthought.
- For each value, show its citation compactly: `source_type` badge (`spreadsheet`, `file_listing`,
  `derivation`, `user_confirmation`), `source_file`, `locator`, and the `quote` in mono.
- `user_confirmation` evidence should be visually marked as **human-supplied** (a person/verified
  motif) so it's distinct from extracted `spreadsheet`/`file_listing` evidence and from
  `derivation` (rule-based). The sidecar mixes all four — the design must make the mix legible.
- Namespaced sidecar entries (`assets:`, `descriptors:`, `implicit:`) get a distinct grouping from
  the dotted JSON-path entries.

## Missing-field / blocker styling

- Blockers are **the product working as intended** — the no-guessing policy made visible. Style them
  as **prominent but honest**, never as red errors.
- Use a calm, attention-drawing treatment (e.g. a distinct "needs you" band or accent) that says
  *action required from a human*, not *the system failed*.
- Each blocker shows the exact question and, for enum fields, the allowed schema values. "I don't
  know" is a legitimate, non-penalized answer and should look like one.
- Never pre-populate a blocker with a "suggested" scientific value styled as an answer.

## Assistant panel styling

- **Visually subordinate** to every deterministic surface. Smaller, quieter, off to the side or
  below evidence — never dominating the canvas.
- Uses the assistant accent color **only**; never a verdict green/red.
- Always **labeled as explanation / navigation**, with an "answered from: …" source label on every
  answer (schema / audit / git / graph / files).
- Reads as a **helper**, not an oracle. No typing-dots theater implying deep thought; no green
  "verified by AI" badges (the AI verifies nothing).

## Data-governance warning styling

- A distinct **protective** treatment — serious, not alarming — for the synthetic-only / no-real-data
  policy and for intercepts. Feels like a safety rail, not a crash.
- Persistent, low-key banner in intake/upload contexts; a firmer, blocking panel on an intercept.
- Copy is calm and explanatory ("real data needs written approval"), never scolding.

## Export artifact cards

- The **record** and the **sidecar** are **two separate artifacts** and get two separate cards.
- Record card: schema-clean, official `ISAAC v1.05`, ULID in mono, PASS verdict attached.
- Sidecar card: labeled **assistant convention (not an official ISAAC standard)**, evidence-count
  shown. Visually related to the record but clearly secondary and clearly non-official.

## Empty states

- Empty repo → invite the **synthetic demo**, not a blank void.
- No draft / no record / no sidecar → explain the honest reason and the next action; never render
  a fake artifact to fill space.
- No warnings → say "no local advisory warnings fired" — **not** "portal approved".

## Icon direction

- Precise, technical, line-based icons. A restrained set: verified (check), user-confirmed (person +
  check), inferred (rule/function), missing (dashed/outline), pending (open circle), warning
  (triangle), governance (shield), evidence (document/quote), record (structured doc), sidecar
  (linked doc). Icons **reinforce** color, never replace the text label.
- Avoid sparkle / wand / "magic AI" iconography anywhere. The assistant is a helper, not magic.

## Spacing, rhythm, and density

- Establish a consistent spacing scale and stick to it; scientific data invites clutter, so the
  layout must impose calm rhythm. Group related fields and their evidence; separate unrelated blocks
  (`system`, `sample`, `measurement`, `assets`, `descriptors`) with clear structural breaks.
- Long data (measurement `values[]` arrays, full sha256 hashes, `ssrl-archive://…` URIs, raw JSON)
  must live in **horizontally-scrollable containers** — the page body never scrolls sideways.
- Truncate mono identifiers gracefully (head+tail ellipsis for hashes/ULIDs) with a reveal/copy
  affordance; never silently drop characters of a hash or URI a user might need to verify.

## Theme and responsiveness

- Build **light and dark** from the start. Verdict, warning, coverage, evidence, and assistant
  colors must each keep their distinct identity **and** AA contrast in both themes.
- Design responsively: the rail / canvas / panel split should collapse sensibly on narrow widths
  (rail → top progress, right panel → tabs or drawer) without ever hiding the verdict.

## Consolidated hard don'ts (visual)

- Never reuse the deterministic PASS/FAIL colors for assistant, memory, warning, or coverage content.
- Never style a warning so it can be mistaken for a FAIL, or coverage so it reads as a PASS.
- Never style a missing/pending field or a blocker as a red error — they are expected, honest states.
- Never brand the sidecar as an official ISAAC artifact.
- Never show a value without a path to its evidence, or a verdict without the command behind it.
- Never use sparkle / wand / "magic AI" motifs, or fake progress/typing theater.

## Interaction principles

- **No fake progress.** Progress reflects the real command that ran (`isaac …`) and its real stages.
  No decorative spinners implying work that isn't happening.
- **No unexplained magic.** Every state change is attributable to a command, a schema rule, or a
  user action. If the UI shows a verdict, the command behind it is inspectable.
- **Every claim traceable.** Any value, verdict, or answer links back to its source (evidence, CLI
  output, schema, doc, or graph node the user can open).
- **Light on animation.** Subtle, functional transitions only. This is an instrument; motion should
  never editorialize or celebrate.
- **Honest failure.** FAIL, blockers, dangling evidence, stale graph, and governance intercepts are
  all designed as calm, legible, expected states — not as crashes or scolding.
- **Clear truth/advisory separation, always.** The line between "the deterministic core says this"
  and "the assistant explains this" is visible on every screen.
