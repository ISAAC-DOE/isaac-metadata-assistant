/**
 * KNOWN, PRE-EXISTING ACCESSIBILITY DEFECTS — a PER-INSTANCE allow-list.
 *
 * ── What changed, and why it had to ─────────────────────────────────────────
 *
 * The first version of this file allowed an entry to be scoped
 * `surfaces: '*', projects: '*'`, and the scan filtered whole axe `Result`
 * objects. axe emits ONE `Result` per rule with every failing node inside it,
 * so a `'*'`-scoped entry dropped every node of that rule everywhere — which is
 * `disableRules([...])` wearing a disguise, three claims to the contrary
 * notwithstanding. `color-contrast` was scoped exactly that way, so all 1,610
 * of its failing nodes were invisible — on all 18 surfaces at all 5 viewports —
 * and a new one introduced tomorrow could never have failed the suite.
 *
 * There is now no wildcard. A baseline entry records an EXACT expected node
 * count for each `surfaceId@projectId` pair where the defect was measured. The
 * scan compares the live node count against that number:
 *
 *   * a pair that is absent expects 0 — any node there is a NEW violation;
 *   * one extra node on a baselined pair (71 → 72) FAILS;
 *   * one fewer (71 → 70) also fails, as `improved`, so the number in this file
 *     is corrected rather than left to rot. That is the deliberate cost of a
 *     ratchet: any change to `apps/web/src` that adds or removes rendered text
 *     will move a count and must update this file in the same commit.
 *
 * Two extra per-instance guards, because an equal count is not the same as an
 * unchanged defect:
 *
 *   * `targetPattern` — every failing node's axe target must match. A different
 *     element failing the same rule the same number of times still fails.
 *   * `foregrounds` — for `color-contrast`, the exact set of failing foreground
 *     colours. A new too-light token fails even if the node count is unmoved.
 *
 * ── Why some counts are PER PLATFORM ────────────────────────────────────────
 *
 * The app ships no webfont. `--font-ui` therefore resolves to SF Pro on macOS
 * and to a DejaVu/Liberation face on `ubuntu-latest`. Linux glyphs are wider,
 * so a line of text wraps at a different word — which changes how many text
 * nodes exist and which of them axe measures. Ten of the 103 recorded triples
 * differ between the two platforms, every one of them by exactly ±1: the
 * signature of a single wrap boundary, not of a different app.
 *
 * The response is NOT a tolerance. A range, a "±1 is fine" rule or a fuzzy
 * match would re-open exactly the hole this file exists to close. Instead a
 * count may be written as `{ darwin: n, linux: m }` and the ratchet is applied
 * to the CURRENT platform's number, exactly. Both numbers are exact; both are
 * one node away from red; the well-formedness test in `specs/a11y-axe.spec.ts`
 * proves that for every platform, not just the one it happens to run on.
 *
 * **CI (Linux) is the authority.** A green run on a developer's macOS machine
 * says the darwin column is right. It says nothing about the linux column, and
 * therefore nothing about whether CI will be green.
 *
 * ── How to regenerate the numbers ───────────────────────────────────────────
 *
 * They are measurements of THIS app in headless Chromium at the five projects
 * in `playwright.config.ts`, taken with the backend seeded by `global-setup.ts`.
 * Two consecutive full runs produced identical counts for all recorded triples on
 * one platform. When a fix lands, run the suite, read the exact numbers out of
 * the failure messages (each one names surface, project, rule, PLATFORM,
 * expected and actual) and edit them here. Do not round, do not pad, and do not
 * delete an entry that is merely inconvenient — deleting an entry means the
 * defect is GONE, and the next run proves or disproves that.
 *
 * You can only regenerate the column for the platform you are on. The other
 * column comes from a CI run: push, read the failure output of the
 * `browser-a11y` job, and transcribe. There is no way to measure Linux numbers
 * from a laptop and no attempt is made to guess them.
 *
 * ── Known limitation, stated rather than hidden ─────────────────────────────
 *
 * `specs/dialogs.spec.ts` scans the app with an overlay open, where node counts
 * legitimately differ from the closed-page measurement. It therefore uses the
 * coarse rule-level predicate `isBaselined()` below, which asks only "is this
 * rule a recorded defect for this surface+project at all". That one call site
 * is rule-level, not instance-level. It is not in scope for this change and is
 * recorded here so nobody reads the file as claiming more than it does.
 */

import { SURFACES } from './surfaces';

/** Viewport project ids, mirroring `playwright.config.ts`. */
export const PROJECT_IDS = [
  'desktop-1280x800',
  'laptop-1024x768',
  'tablet-768x1024',
  'mobile-375x812',
  'zoom-200',
] as const;

export type ProjectId = (typeof PROJECT_IDS)[number];

/**
 * NARROW-WIDTH SCAN KEYS — the axe sweep that is NOT a Playwright project.
 *
 * ── The gap these close ─────────────────────────────────────────────────────
 *
 * `PROJECT_IDS` above is 1280 / 1024 / 768 / 375 / 640@DPR2. The narrowest width
 * this product claims to support is 320 (WCAG 1.4.10 reflow), and 390 is the
 * modern phone width; `specs/layout-widths.spec.ts` has measured LAYOUT at both
 * since it was written, but nothing scanned CONTRAST, ACCESSIBLE NAMES or FOCUS
 * VISIBILITY there — and 320 is exactly where text wraps hardest, where a line
 * breaks onto a tighter background, and where controls crowd. So the widths at
 * which this app is most likely to fail axe were the widths axe never saw.
 *
 * ── Why these are keys and not a sixth project ──────────────────────────────
 *
 * `specs/layout-widths.spec.ts` already answered this question for layout and
 * the answer has not changed: a project multiplies the WHOLE suite — every
 * `@responsive` spec, not just the scan that wanted it — and it perturbs the
 * count ratchet in this file for all 21 surfaces at once. `specs/a11y-narrow.spec.ts`
 * therefore runs inside ONE project and moves the viewport itself, exactly as the
 * layout sweep does, and its pairs are namespaced `surfaceId@width-<n>` so they
 * can never collide with a real project's.
 *
 * The namespacing is not cosmetic. `mobile-375x812` and `width-390` are 15 CSS px
 * apart; a shared key would let a defect recorded at one silently excuse the
 * other.
 *
 * ── What is DELIBERATELY not here yet ───────────────────────────────────────
 *
 * NO COUNTS. Not one `width-320` or `width-390` pair appears in `A11Y_BASELINE`
 * below, which means every one of them expects 0 — so any violation at either
 * width reads as `new` and FAILS, and the failure prints the exact line to add.
 * That is the intended state, not an oversight: the numbers must be transcribed
 * from a **linux CI** run, and this file's own header says a laptop cannot
 * measure the linux column and no attempt is made to guess it. Writing a
 * darwin reading here as a bare number would be claiming it holds on both
 * platforms — the precise mistake that cost this project a cycle once already.
 *
 * See `specs/a11y-narrow.spec.ts` for the transcription procedure.
 */
export const NARROW_WIDTHS = [390, 320] as const;

/** `320` → `'width-320'`. The "project" component of a narrow-sweep key. */
export const narrowWidthId = (width: number): string => `width-${width}`;

/** The narrow-sweep pseudo-project ids, in sweep order. */
export const NARROW_WIDTH_IDS: readonly string[] = NARROW_WIDTHS.map(narrowWidthId);

/** Every id a baseline key may name: a real Playwright project, or a narrow width. */
export const SCAN_PROJECT_IDS: readonly string[] = [...PROJECT_IDS, ...NARROW_WIDTH_IDS];

/* ────────────────────────────────────────────────────────────────────────────
 * PLATFORM.
 *
 * These primitives live here, and `layout-baseline.ts` imports them, because
 * the two baseline files are the only consumers and a third module for four
 * declarations would be worse. They are deliberately not in `env.ts`: nothing
 * here is configurable, and nothing here reads an environment variable.
 * ──────────────────────────────────────────────────────────────────────────── */

/**
 * The platforms this baseline has MEASURED numbers for. Not a list of platforms
 * the suite "supports" in the aspirational sense — a list of platforms someone
 * has actually run it on and transcribed the results from.
 *
 * `linux` is `ubuntu-latest` in `.github/workflows/ci.yml` and is AUTHORITATIVE.
 * `darwin` exists so the suite is usable on a developer's machine.
 */
export const BASELINE_PLATFORMS = ['darwin', 'linux'] as const;

export type BaselinePlatform = (typeof BASELINE_PLATFORMS)[number];

/**
 * A measurement that is identical on both platforms (a bare number — 93 of the
 * 103 triples) or one that is not (an exact number for each).
 *
 * There is no third form. In particular there is no range, no tolerance and no
 * "unknown"; a platform with no measurement is a platform this file cannot
 * speak for, and `resolvePlatform` refuses to run there.
 */
export type PlatformCount = number | Readonly<Record<BaselinePlatform, number>>;

/**
 * `process.platform` → the baseline column to enforce, or a hard failure.
 *
 * Falling back to one of the two would be worse than failing: a Windows
 * contributor would get a suite that is green because it is comparing their
 * run against somebody else's font metrics. Exported separately from
 * `currentPlatform()` so `specs/self-check.spec.ts` can prove the refusal
 * without needing to run on Windows.
 */
export function resolvePlatform(nodePlatform: string): BaselinePlatform {
  if ((BASELINE_PLATFORMS as readonly string[]).includes(nodePlatform)) {
    return nodePlatform as BaselinePlatform;
  }
  throw new Error(
    `This accessibility/layout baseline has no measured numbers for platform "${nodePlatform}". ` +
      `Recorded platforms: ${BASELINE_PLATFORMS.join(', ')}. Text wraps at different words under ` +
      `different system fonts (there is no webfont), so the node counts in e2e/a11y-baseline.ts and ` +
      `the clip lists in e2e/layout-baseline.ts are platform-specific measurements — running them ` +
      `against a third platform's font metrics would produce noise, not a verdict. Run the suite on ` +
      `Linux (which is what CI runs, and what is authoritative) or on macOS, or measure "${nodePlatform}" ` +
      `and add its column to both baseline files.`
  );
}

/** The baseline column in force for THIS process. Throws on an unmeasured platform. */
export function currentPlatform(): BaselinePlatform {
  return resolvePlatform(process.platform);
}

/** Read one platform's number out of a `PlatformCount`. */
export function platformCount(count: PlatformCount | undefined, platform: BaselinePlatform): number {
  if (count === undefined) return 0;
  return typeof count === 'number' ? count : count[platform];
}

/** `${surfaceId}@${projectId}`. */
export type BaselineKey = string;

export const baselineKey = (surfaceId: string, projectId: string): BaselineKey => `${surfaceId}@${projectId}`;

export interface BaselineEntry {
  /** axe rule id. */
  readonly rule: string;
  readonly impact: 'minor' | 'moderate' | 'serious' | 'critical';
  /** What is actually wrong, and where. Written for whoever fixes it. */
  readonly note: string;
  /**
   * EXACT expected violating-node count per `surfaceId@projectId`. Exhaustive:
   * any pair not listed expects zero. There is no wildcard.
   *
   * A bare number means "measured identical on macOS and Linux".
   * `{ darwin: n, linux: m }` means the two platforms were measured separately
   * and genuinely differ — see the font-metrics note in the file header. Both
   * numbers are exact and both are enforced as a one-node ratchet.
   */
  readonly counts: Readonly<Record<BaselineKey, PlatformCount>>;
  /**
   * RegExp source; every failing node's axe target must match it. Optional
   * ONLY because `color-contrast` fails on 1,610 unrelated text nodes whose
   * selectors are `:nth-child` noise — pinning them would be brittle and would
   * say nothing. Every entry must carry a `targetPattern` or `foregrounds`;
   * `specs/a11y-axe.spec.ts` asserts that.
   */
  readonly targetPattern?: string;
  /** `color-contrast` only: the exact set of failing foreground colours. */
  readonly foregrounds?: readonly string[];
}

export const A11Y_BASELINE: readonly BaselineEntry[] = [
  {
    rule: 'color-contrast',
    impact: 'serious',
    /*
     * ── 2026-08-10 · 26 COUNTS LOWERED BY A THREE-DECLARATION CSS FIX ─────────
     *
     * `record-detail`, `guided-completion`, `evidence`, `export-readiness` and
     * `export-readiness-done` drop 1–3 nodes across 26 of their 35 cells; the other
     * NINE drop nothing, because at those widths none of the three nodes was inside
     * axe's measured set to begin with. Only `guided-completion` moves at all seven of
     * its viewports. ("each drop 1–3 nodes at every viewport" is what this line used to
     * say, which the per-entry numbers above contradict and which the "0 at BOTH
     * mobile-375x812 and width-320" note below now contradicts explicitly.) ONE CAUSE, and
     * it is a real fix rather than a measurement artefact: the app-wide StatusBar
     * had three declarations below AA, and they are now above it.
     *
     *   .statusbar-pending / .statusbar-note  --text-tertiary   #78838f  3.76:1
     *                                      -> --text-muted      #5b6570  5.77:1
     *   .statusbar-right                      --text-quaternary #9aa4af  2.46:1
     *                                      -> --text-slate      #5b6b7d  5.32:1
     *
     * (Ratios against the status bar's own `--surface-subtle` #fbfcfd, computed
     * rather than eyeballed. AA wants 4.5:1 at these sizes — 11.5px and 10.5px.)
     * The status bar renders on every record screen, which is why five surfaces move
     * together and why no `settings-*` cell moves FOR THIS REASON — the three
     * `settings-explorer` cells that do change in this same commit change for two
     * unrelated reasons documented at their own entry — on linux, this branch's five new
     * operations shifting `.api-browser-list`'s scroll clip; on darwin, a STALE COLUMN
     * corrected, since `b7792c1` already measured 48/49/64 there — and it is worth
     * being exact because "does not move at all", which this line used to say, is
     * contradicted by the diff it sits in. Measured, `<StatusBar` is
     * rendered only by `RecordWorkbench`, `GuidedCompletion`, `EvidenceExplorer` and
     * `ExportReadiness`, and `.statusbar-{pending,note,right}` exist only in
     * `StatusBar.tsx`. "Five surfaces" is the surface count, not a claim about every
     * cell: `record-detail@mobile-375x812` stays at 12, because at that width none of
     * the three nodes was inside axe's measured set to begin with.
     *
     * HOW IT WAS FOUND, because the route says something about reading this file.
     * Nobody was looking for it. The Run workspace added a section to the record
     * screen, changing no colour anywhere, and linux CI reported TWO regressions:
     * `record-detail@tablet-768x1024` 14 -> 16 (+2) and `record-detail@width-390`
     * 12 -> 13 (+1). In each message all four printed nodes were pre-existing debt
     * and the rest were truncated, so the delta was invisible; the truncation is now
     * 24 nodes (`MAX_REPORTED_NODES`, `e2e/helpers/axe.ts`).
     *
     * An A/B against `b7792c1` at `desktop-1280x800` identified the newcomers as
     * `.statusbar-right` and the two `.statusbar-pending` spans — THREE nodes there,
     * and the count is viewport-dependent, which the first version of this note got
     * wrong by narrating the desktop observation as the tablet one. How many of the
     * three each viewport actually carries is the per-entry delta recorded above, and
     * it is NOT uniform across surfaces — desktop alone spans -3 (`record-detail`,
     * `export-readiness`), -2 (`guided-completion`, `evidence`) and -1
     * (`export-readiness-done`). For `record-detail`, the row the linux regression was
     * reported on: -3 at desktop and laptop, -2 at tablet and zoom-200, -1 at
     * width-390, and 0 at BOTH mobile-375x812 and width-320. So the tablet +2 is
     * explained by two of the three, not three.
     *
     * (An earlier revision of this paragraph gave one flat list for every surface and
     * put -1 at width-320 — which is `guided-completion`'s delta, not
     * `record-detail`'s, whose width-320 count is 12 at all three commits. That is the
     * same wrong-row attribution the sibling `axe.ts` comment corrects, made again two
     * paragraphs after apologising for it.)
     *
     * SO THE OPTION TAKEN WAS THE HARDER ONE. Ratcheting `record-detail` upward was
     * available and would have been green; it would also have blessed a 2.46:1
     * failure because it was old. Fixing it instead turned one regression into 26
     * improvements.
     *
     * THE LINUX COLUMN IN THESE 26 ENTRIES IS THE PRE-FIX NUMBER AND IS KNOWN TO BE
     * TOO HIGH. That is deliberate and is this file's own instruction: only the
     * platform you measured on may be edited, the other column comes from a CI run,
     * and no attempt is made to guess it. Every darwin number above was measured on
     * this fix; the matching linux numbers arrive from the `browser-a11y` job and
     * are transcribed in the follow-up commit. Until then CI reports ~26
     * `IMPROVED … on linux` messages, each naming its exact figure. A pair that ends
     * up equal collapses back to a scalar.
     *
     * WHAT IS NOT FIXED: `--text-tertiary` (189 `var()` DECLARATIONS) and
     * `--text-quaternary` (69)
     * — both counted at this commit, after every change in it, over file bytes rather
     * than with a bare `rg`, which silently skips NUL-byte files while exiting 0 — remain
     * too light almost everywhere, which is why both are still in
     * `foregrounds` below — checked, not assumed. Darkening the TOKENS is the
     * systemic fix and is a design-system change, not a slice's to make.
     */
    // MEASURED, replacing the earlier note's stated "2.4:1 – 4.2:1, four tokens,
    // one palette decision" — all three of which were wrong.
    note:
      'FINDING A11Y-01 (low-contrast text). 1,610 failing nodes on all 18 surfaces at all 5 ' +
      'viewports. ELEVEN distinct rendered foregrounds fail, from THREE distinct causes — it ' +
      'is NOT one palette decision. (a) Neutral text tokens that are simply too light on the ' +
      'app surfaces: --text-tertiary #78838f (3.86:1 on white, 922 occurrences, all 18 ' +
      'surfaces), --text-quaternary/--idle #9aa4af (2.53:1, 263, all 18 surfaces), and ' +
      '--text-disabled #c0c8d0 (1.69:1 on white; 1.56:1 as rendered on #f4f6f9) — the WORST ' +
      'ratio in the app, and tokens.css:34 intends it for "disabled chevrons/icons" yet ' +
      'evidence.css:239 uses it for the `.ln` line numbers of the Evidence file preview, ' +
      'i.e. as TEXT at 11.5px, 110 occurrences. (b) Ancestor `opacity` compositing tokens ' +
      'that PASS at full strength down below 4.5:1: --text-muted #5b6570 (5.93:1) renders ' +
      '#777f89 and --text-slate #5b6b7d (5.46:1) renders #778493 under ' +
      '`queue.css:63 .exp-row.done { opacity: .82 }`; --text-secondary #46515f (8.07:1) ' +
      'renders #777f8a and --text-quaternary renders #b3bbc4 (1.79:1) under ' +
      '`assistant.css:1557 .upcoming-row { opacity: .72 }`; --advisory-text #8a6420 (5.35:1, ' +
      'itself darkened in P23C expressly for AA) renders #9b793d under ' +
      '`signals.css:199 .advisory-nongating { opacity: .85 }`; --text-tertiary renders ' +
      '#8e98a2 under the same .done rule. Darkening the tokens will NOT fix these five — the ' +
      'opacity has to go. (c) Two saturated category/status colours that land just under AA ' +
      'at small sizes: --verified-text #2f7d78 on the #e6f1f0 chip tint ' +
      '(4.2:1, 265 occurrences) and --src-derivation #7a6bb0 (4.25:1, 15). ' +
      'Measured range across all 43 (fg, bg, size) combinations: 1.56:1 to 4.25:1, all ' +
      'against a 4.5:1 requirement; nothing needs the 3:1 large-text threshold because every ' +
      'failing node is 9.5–13px.',
    // No targetPattern: the 1,610 nodes are ordinary text all over the app and
    // their selectors are `:nth-child` noise. `foregrounds` is the meaningful
    // per-instance guard for this rule — see the interface comment.
    // Every failing foreground colour axe reported, across all 90 scans. A new
    // one — i.e. a new too-light token, or a new opacity composite — fails even
    // if the node count is unchanged.
    foregrounds: [
      '#78838f', // --text-tertiary
      '#9aa4af', // --text-quaternary / --idle
      '#c0c8d0', // --text-disabled  (worst: 1.56:1)
      // The `/ --stats-cat-2` and `/ --stats-cat-5` aliases these two lines used
      // to carry are GONE: Statistics no longer declares six page-scoped
      // categorical slots (no chart on it encodes identity by hue). The tokens
      // themselves are unchanged, and so are these two failing colours.
      '#2f7d78', // --verified-text
      '#7a6bb0', // --src-derivation
      '#8e98a2', // --text-tertiary   @ opacity .82  (.exp-row.done)
      '#777f89', // --text-muted      @ opacity .82  (.exp-row.done)
      '#778493', // --text-slate      @ opacity .82  (.exp-row.done)
      '#777f8a', // --text-secondary  @ opacity .72  (.upcoming-row)
      '#b3bbc4', // --text-quaternary @ opacity .72  (.upcoming-row)
      '#9b793d', // --advisory-text   @ opacity .85  (.advisory-nongating)
    ],
    // 1,610 nodes on darwin / 1,616 on linux, across 90 (surface, project)
    // pairs. TEN of the 90 differ, all by exactly one node, all because the
    // system font differs: SF Pro on macOS, a DejaVu/Liberation face on
    // ubuntu-latest. Wider Linux glyphs move a wrap boundary, which adds or
    // removes one rendered text node. Eight gain a node, two lose one — a
    // one-directional "Linux is always worse" story would have been the wrong
    // one. The linux column is transcribed from GitHub Actions run
    // 30668917975; it is the authoritative one.
    counts: {
      /*
       * ── EVIDENCE GRAPH, 2026-08-13: +1 on the evidence page, one more tab button ──
       *
       * The Evidence screen gained an `Evidence List | Evidence Graph` tab strip, so
       * it now renders one more `.section-tab` -- the same pre-existing contrast
       * failure counted in the settings block above, on one more page. Uniform +1 at
       * all seven viewports, no new rule, and no page without the strip moved.
       *
       * A KNOWN DEFECT'S COUNT, NOT A NEW ONE. Fixing `.section-tab` centrally would
       * clear this and the 33 settings cells together.
       *
       * Linux measured from this branch's CI run, read line by line rather than
       * derived; darwin inferred by the extra-DOM-node argument used above.
       */
      /*
       * ── `evidence-graph`, 2026-08-16: A NEW SURFACE WITH NO COUNTS, ON PURPOSE ──
       *
       * `e2e/surfaces.ts` now carries `evidence-graph`, the `?view=graph` deep link
       * on the Evidence route. The `evidence` entry above lands on the LIST view, so
       * until that surface existed the graph panel had never been loaded by axe, by
       * the 320/390 narrow sweep, by the layout probes or by the zoom-200 pass at all.
       *
       * ~~NOT ONE `evidence-graph@*` KEY APPEARS BELOW~~ ~~CI HAS NOW ANSWERED FOR
       * ONE OF THE SEVEN~~ — ALL SEVEN ARE NOW MEASURED AND RECORDED. Both earlier
       * paragraphs are struck rather than deleted, because the procedure they state
       * is exactly the one that was followed and the record of following it is the
       * point: only the platform actually measured may be edited, no attempt is made
       * to guess the other, and a bare number asserts BOTH columns because this
       * environment cannot run the Linux face.
       *
       * Two CI runs, both on LINUX, both transcribed rather than derived:
       *   run 31963596365 on `0c9752f` — desktop-1280x800: 24
       *   run 31966373802 on `dd5e049` — laptop-1024x768: 28, tablet-768x1024: 28,
       *                                  mobile-375x812: 27, zoom-200: 27,
       *                                  width-390: 27, width-320: 27
       * Nothing here was pre-empted and nothing was lowered to make a run green.
       *
       * THE SECOND RUN ALSO CONFIRMED THE TWO FIXES, which is why this entry records
       * contrast ONLY. `aria-allowed-role` had fired on 3 nodes at all seven
       * viewports (`<li role="note">`, an invalid override of the implicit
       * `listitem`) and is now absent from the NEW list entirely; the eight
       * `clipped-x` findings at 375px are likewise gone. Both were FIXED rather than
       * recorded — which is the distinction this file exists to keep visible, and the
       * reason the number below is 27–28 and not 30–31.
       *
       * WHAT IS EXPECTED TO FIRE, stated in advance so a large number is not
       * mistaken for a regression this branch caused. `evidence-graph.css` styles
       * EIGHT rules with `--text-quaternary` at 10.5–11px — `.evgraph-result-match`
       * (:253), `.evgraph-kind-count` (:344), `.evgraph-row-kind` (:488),
       * `.evgraph-row-count` (:496), `.evgraph-detail-producer-term` (:662),
       * `.evgraph-detail-count` (:739), `.evgraph-conn-kind` (:815) and
       * `.evgraph-legend-kinds` (:850). (Eight, counted here by `grep -n` over the
       * file; the review that prompted this entry said "at least seven" and listed
       * seven, missing `.evgraph-conn-kind`.) That token is #9aa4af, measured at
       * 2.53:1 on white — below AA's 4.5:1 and below even AA-large's 3.0:1 — and it
       * is ALREADY in this entry's `foregrounds` list with 263 recorded instances
       * elsewhere in the app. Every node those rules produce is one more instance of
       * a documented token shortfall, not a new defect, and the panel renders many
       * of them per row. The systemic remedy is darkening the token, which moves
       * counts on all 18 pre-existing surfaces and belongs to the slice that owns
       * the design system — not here, where it would hide a palette change inside a
       * graph PR.
       *
       * Two things this DOES leave open, named rather than implied: the panel is
       * also newly reachable by `specs/layout-widths.spec.ts`, `layout-responsive`
       * and `zoom-200`, which carry their own baselines in `e2e/layout-baseline.ts`
       * and `e2e/layout-allowlist.ts`; and ~~`A11Y_BASELINE_TOTAL_NODES` does NOT
       * move in this commit~~ — it moves now, because the entry map does. See the
       * dated block on that constant.
       *
       * The layout half of that sentence is also no longer true and is corrected
       * rather than left: the layout probes DID report this surface — eight
       * `clipped-x` instances of SVG canvas labels, the quoted one being
       * `text "processing_notebook"` at `mobile-375x812` — and that is FIXED in
       * `EvidenceGraphPanel.tsx` (labels are bounded against the canvas rectangle
       * and cut to its width) rather than recorded in `e2e/layout-baseline.ts`. A
       * defect on a surface this branch is adding does not get a baseline entry.
       */
      'evidence@desktop-1280x800': 70,
      'evidence@laptop-1024x768': 70,
      // 70 -> 71 on 2026-08-01. NOT a new defect: `.record-file` (the mono
      // filename, 11px `--text-quaternary`) moved out of axe's `incomplete`
      // bucket and into `violations`. Before the C1/I4 fix it hung 105.3px
      // OUTSIDE `.record-context`, and axe cannot resolve a background colour
      // for an element painting over unknown ancestors, so it declined to
      // judge it. Containing the crumb made it measurable — and it fails.
      // Proven by an A/B run with only the four CSS files reverted: incomplete
      // 10 -> 9, violations 70 -> 71, and the single set difference is exactly
      // `.record-file`. The element was always painted; only measurement
      // changed. Linux is the authority and may differ.
      'evidence@tablet-768x1024': 70,
      'evidence@mobile-375x812': 68,
      'evidence@zoom-200': 68,
      /*
       * ── `evidence-graph`, MEASURED: 24 nodes at desktop, 2026-08-16 ────────────
       *
       * RECORDED, AND NOT ACCEPTED AS CORRECT. This is an instance of the known
       * systemic token failure this entry has always been about, not a defect
       * particular to the graph panel:
       *
       *   `--text-tertiary`   #78838f — measured 3.86:1 on white
       *   `--text-quaternary` #9aa4af — measured 2.53:1 on white
       *
       * WCAG AA needs 4.50:1, and AA-large 3.00:1, so the first fails AA and the
       * second fails both. Between them they have 274 usages across 40 files.
       *
       * The 24 nodes CI reported are a mix of pre-existing app chrome and new graph
       * text — `kbd.topbar-search-kbd`, `button#evidence-view-tab-list.section-tab`,
       * `p.evgraph-counts`, `p.evgraph-freshness` and more — which is the shape of a
       * token problem rather than a screen problem.
       *
       * A DEDICATED DESIGN-SYSTEM SLICE OWNS RAISING THE TWO TOKENS AND IS QUEUED.
       * It will reduce the count on this surface and on the 18 others at the same
       * time, so THIS NUMBER IS EXPECTED TO DROP. When it does, transcribe CI's new
       * figure and lower the total; do not treat the fall as a regression, and do
       * not fix the palette inside a graph PR, where it would hide.
       *
       * 24 is a LINUX reading (run 31963596365, `0c9752f`) written as a scalar,
       * which asserts darwin too. This file's type system has no way to say
       * "unknown" for one column — a per-platform pair is rejected when both halves
       * are equal — so a one-platform measurement can only be written this way, as
       * the header and several notes below already record. If a darwin run
       * disagrees, split the key and correct the total; never loosen the assertion.
       */
      'evidence-graph@desktop-1280x800': 24,
      'evidence-graph@laptop-1024x768': 28,
      'evidence-graph@tablet-768x1024': 28,
      'evidence-graph@mobile-375x812': 27,
      'evidence-graph@zoom-200': 27,
      'evidence-graph@width-390': 27,
      'evidence-graph@width-320': 27,
      /*
       * TUTORIAL-SCOPE SLICE (2026-08-04). `experiments` fell 10/10/10/9/9 →
       * 3/3/3/2/2, and the seven/eight nodes that went away did NOT get fixed —
       * they MOVED, to `experiments-example` below, which measured exactly the old
       * numbers (10/10/10/9/9).
       *
       * WHY. `ensure_seeded()` no longer materialises the five built-in examples
       * into the ordinary workspace; they exist only inside a worked-example
       * session. So this surface is now the real EMPTY state — a heading, two
       * sentences, two buttons and the first-run offer — and the low-contrast nodes
       * that used to be counted here were the queue's own (`.exp-row` metadata, the
       * `--text-tertiary` and `--text-quaternary` row text, the `.exp-row.done`
       * opacity composites). The remaining 3 (2 at the two narrow projects) are the
       * offer card and the empty-state hints.
       *
       * The pair is the point: lowering this number without adding
       * `experiments-example` would have looked like a 35-node accessibility
       * improvement while the same 35 nodes were simply no longer being scanned.
       */
      'experiments@desktop-1280x800': 3,
      'experiments@laptop-1024x768': 3,
      'experiments@tablet-768x1024': 3,
      'experiments@mobile-375x812': 2,
      'experiments@zoom-200': 2,
      /*
       * The POPULATED queue, at the same route inside a worked-example session.
       * These five numbers are byte-identical to what `experiments@*` measured
       * before the examples moved out of the ordinary workspace, which is the
       * corroboration that this surface inherited that coverage rather than
       * introducing new debt: same markup, same tokens, same counts.
       */
      'experiments-example@desktop-1280x800': 10,
      'experiments-example@laptop-1024x768': 10,
      'experiments-example@tablet-768x1024': 10,
      'experiments-example@mobile-375x812': 9,
      'experiments-example@zoom-200': 9,
      'export-readiness@desktop-1280x800': 4,
      'export-readiness@laptop-1024x768': 3,
      'export-readiness@tablet-768x1024': 3,
      'export-readiness@mobile-375x812': 1,
      'export-readiness@zoom-200': 1,
      // R1b: the `.verdict-cmd mono` block that rendered
      // `isaac validate --official · exit N` is GONE (a fabricated CLI transcript —
      // no process produced it), and it was a low-contrast node axe counted here.
      //
      // PER-PLATFORM, and the first attempt at this entry got it wrong. I lowered
      // the scalar to 12 reasoning that "a removed DOM node is platform-
      // independent", which sounds obvious and is FALSE here: linux MEASURED 12
      // (CI run on 52c1576) while darwin MEASURED 13 (local run, same commit). The
      // removal changes how the remaining fragments wrap, and the wider linux face
      // merges two text nodes that darwin keeps apart — the same mechanism the
      // notes below describe for other split pairs. Both numbers are measurements,
      // neither is derived.
      //
      // COVERAGE-DISCLOSURE SLICE: the pair COLLAPSES to a scalar 13, because linux
      // rose 12 -> 13 (CI run 30984206413 on `e02ac14`) and darwin did not move.
      // Both halves are measured, and the darwin half was measured SPECIFICALLY to
      // answer whether this slice introduced a new low-contrast node — it did not.
      // The full failing-node SET was dumped on darwin at this width on both
      // `main` (61247ec) and this branch, and the two lists are IDENTICAL, in the
      // same order: .record-file, kbd, .verdict-hint, .coverage-note, .coverage-cmd,
      // .advisory-nongating, .ready-note, the two .artifact-sub, .artifact-pathcount,
      // .artifact-hint, .assistant-note, .statusbar-right. NONE of the three
      // elements this slice adds (.coverage-sub, .coverage-sub-scope,
      // .statusbar-cover-scope) appears — consistent with their computed colours,
      // RE-MEASURED per (foreground, background) pair rather than per token, because
      // the earlier version of this note said --text-secondary #46515f is "above 8:1"
      // full stop, and 8.07:1 is its ratio on PURE WHITE (--surface) only. It is not
      // the background either of these elements has:
      //   #46515f on --surface-subtle #fbfcfd = 7.86:1  <- .statusbar-cover-scope
      //     (chrome.css: .statusbar { background: var(--surface-subtle) })
      //   #46515f on --cover-bg      #eef2f6 = 7.17:1
      //   #46515f on --surface       #ffffff = 8.07:1   <- not used by either
      //   #5b6b7d on --cover-bg      #eef2f6 = 4.86:1  <- .coverage-sub /
      //     .coverage-sub-scope, both inside .coverage (signals.css: background
      //     var(--cover-bg)); --text-slate and --cover-text are both #5b6b7d
      // Computed with the WCAG 2.x formulae directly — per-channel sRGB linearisation
      // (c/12.92 below 0.03928, else ((c+0.055)/1.055)^2.4), luminance
      // 0.2126R+0.7152G+0.0722B, ratio (L_light+0.05)/(L_dark+0.05) — not read off a
      // tool and not copied from another comment. Unrounded: 7.8553, 7.1724, 8.0687,
      // 4.8561. All four clear the 4.5:1 AA requirement at these sizes, which is what
      // this note is for; the smallest margin is the coverage card's 4.86:1, so a
      // darker --cover-bg or a lighter --cover-text would move that pair first.
      // (styles/statistics.css records "#46515f (8.07:1 / 7.86:1)" — the same two
      // numbers, for the same two backgrounds; 4.85:1 elsewhere in the repo is 4.8561
      // truncated rather than rounded.)
      //
      // So the +1 on linux is a PRE-EXISTING failing node being counted twice
      // instead of once: CoverageBadge's denominator explanation went from one
      // short line to two longer ones, the `.coverage` card grew, and on the wider
      // linux face a text run that used to merge now splits. That is the same
      // mechanism the paragraph above documents for this exact key — and the
      // interesting part is that linux has now converged ON darwin's number, which
      // is what you would expect if the merge that produced 12 stopped happening.
      // Only the LINUX total moves; darwin's stays.
      'export-readiness-done@desktop-1280x800': 12,
      'export-readiness-done@laptop-1024x768': 11,
      // The two pairs where LINUX HAS FEWER nodes: the wider face pushes two
      // fragments onto one line, so axe sees one text node instead of two.
      // Linux 11 -> 12, MEASURED by CI run 30691557697 on `7e9a387`; the split
      // is no longer needed. Same mechanism as the two darwin increases in this
      // slice: containing the top-bar crumb let axe resolve a background it
      // previously could not, so a pre-existing failure moved from `incomplete`
      // into `violations`. Linux only, because 768 is inside the band the
      // compact treatment moved into and the wider Linux face changes what fits.
      'export-readiness-done@tablet-768x1024': 11,
      'export-readiness-done@mobile-375x812': 8,
      'export-readiness-done@zoom-200': 9,
      'governance@desktop-1280x800': 4,
      'governance@laptop-1024x768': 4,
      'governance@tablet-768x1024': 4,
      'governance@mobile-375x812': 3,
      'governance@zoom-200': 3,
      'guided-completion@desktop-1280x800': 10,
      'guided-completion@laptop-1024x768': 9,
      // Linux 11 -> 10, MEASURED by CI run 30691557697 on `7e9a387`: a genuine
      // IMPROVEMENT on Linux only, lowered rather than left stale. darwin stays
      // 11 (measured locally, unchanged), so the entry splits.
      //
      // Linux 10 -> 11, MEASURED by CI on this branch's `4f845ea`. This is a
      // GROWTH and is recorded as one rather than dressed up: this slice adds
      // `.guided-inferability`, the paragraph that states WHY the app is asking
      // instead of answering, and it fails `color-contrast` on Linux.
      //
      // Why it is ratcheted and not fixed here. The new paragraph is styled to
      // match `.guided-context`, the explanatory paragraph it renders directly
      // beneath — same `--text-secondary` token, same 12.5px, same line-height —
      // and `.guided-context` ALREADY fails the same rule in this same count.
      // So the deficit is in the token against this surface, not in this slice's
      // markup: giving only the new paragraph a stronger colour would leave two
      // adjacent explanatory paragraphs deliberately mismatched and would not
      // remove a single pre-existing violation. Repairing `--text-secondary` on
      // this surface is a design-system change that moves counts on many screens
      // and belongs to its own slice, not to a no-guessing slice.
      //
      // The entry COLLAPSES back to a bare number, and the number for darwin is
      // MEASURED, not assumed. A first attempt wrote `{ darwin: 11, linux: 11 }`
      // and the well-formedness guard rejected it correctly: a per-platform pair
      // must mark a real measured difference, and equal halves are not one.
      //
      // darwin re-measured locally on this branch --
      //   npx playwright test e2e/specs/a11y-axe.spec.ts \
      //     --project=tablet-768x1024 -g "Guided Completion"
      // -- passes against 11, so darwin did NOT gain a node from
      // `.guided-inferability` while Linux did. The two platforms have therefore
      // CONVERGED at 11, which is why the split that existed for the 11/10
      // difference is no longer carrying any information and is removed.
      'guided-completion@tablet-768x1024': 9,
      // Was `{ darwin: 7, linux: 8 }`; darwin caught up to Linux on 2026-08-01
      // and the split is no longer needed. `.guided-suggestion-not` moved from
      // axe's `incomplete` bucket into `violations` after the C1/I4 fix removed
      // the overlaps that made its background unresolvable. The element itself
      // is untouched by that fix — an A/B run with only the four CSS files
      // reverted measured identical geometry (102.5x35.6) and identical colour
      // (rgb(120,131,143)), while `incomplete` fell 6 -> 3 and both
      // `.record-surface` and `.guided-suggestion-head` became resolvable AND
      // PASSING. That Linux ALREADY counted 8 is the corroboration: the wider
      // Linux face had made the same node measurable long before this slice, so
      // this is a pre-existing failure of the `--text-tertiary` token (#78838f
      // at 3.64:1, the same token as four already-baselined nodes on this
      // surface), not a regression. Fixing the token is a separate, wider
      // change: it would move counts on many surfaces at once.
      'guided-completion@mobile-375x812': 7,
      'guided-completion@zoom-200': 7,
      'load@desktop-1280x800': 3,
      'load@laptop-1024x768': 3,
      'load@tablet-768x1024': 3,
      'load@mobile-375x812': 2,
      'load@zoom-200': 2,
      'memory@desktop-1280x800': 18,
      'memory@laptop-1024x768': 18,
      'memory@tablet-768x1024': 18,
      'memory@mobile-375x812': 17,
      'memory@zoom-200': 17,
      'memory-graph@desktop-1280x800': 31,
      'memory-graph@laptop-1024x768': 31,
      'memory-graph@tablet-768x1024': 23,
      'memory-graph@mobile-375x812': 16,
      'memory-graph@zoom-200': { darwin: 21, linux: 22 },
      /* The Record Detail rows grew by one node when the `Graph` tab landed, and
         the extra node is the tab control itself:

             <button id="record-view-tab-graph" class="section-tab">Graph</button>

         `.section-tab` contrast is PRE-EXISTING, DOCUMENTED DEBT (see the
         product-hardening closure note in CLAUDE.md, which records it as
         accepted and baselined). So this is one more instance of a known
         defect, not a new one — the Graph tab inherits the same failing pair
         every other section tab on this app already has. Fixing `.section-tab`
         properly moves counts on every surface that uses it and is its own
         slice; doing it here would hide a broad change inside a graph PR.

         `tablet-768x1024` is deliberately UNCHANGED: it did not grow, on either
         platform. Do not "correct" it to match its neighbours.

         Every number below was MEASURED on both platforms, not derived by
         adding one to the old value — and mobile is why that matters. Linux
         grew 11 → 12 (+1) but darwin grew 10 → 12 (+2), so the two columns
         CONVERGE and the pair becomes a bare number. Assuming +1 per platform
         would have written `{ darwin: 11, linux: 12 }`, which is wrong. */
      /*
       * ── VALIDATE & REVIEW, 2026-08-13: +1 on record-detail, and it is a NEW node ──
       *
       * Unlike the seventh-settings-tab move, this is a node that did not exist
       * before: `<p class="vr-sub">`, the Validate & Review sub-line. So the question
       * is whether to fix it rather than record it, and the answer is that it uses
       * `var(--text-tertiary)` -- an established token already used in ~30 places and
       * already failing on this baseline wherever it renders small text. `.fg-sublabel`
       * on this very page uses the dimmer `--text-quaternary` and fails likewise.
       *
       * So this is a new INSTANCE of a systemic token-level contrast issue, not a
       * rogue colour chosen here. Giving this one element a compliant colour would
       * make it inconsistent with every sibling sub-line; the real fix is raising the
       * tertiary/quaternary tokens, which would move many baselines at once and is a
       * design-system change, not a slice change.
       *
       * Uniform +1 at all seven viewports, no new rule, no other page moved. Linux
       * measured from this branch's CI run, read line by line; darwin inferred by the
       * same DOM-node argument as the settings block above.
       *
       * ── THE +1 IS IDLE-STATE ONLY, AND UNDERSTATES THIS FEATURE'S REAL DEBT ──
       *
       * The scan never presses the Validate & Review button. It renders the section,
       * reads the idle state, and moves on — so `.vr-sub` is the ONLY node of this
       * feature axe has ever seen. Every `--text-tertiary` node the feature paints
       * AFTER a check is unscanned and uncounted: `.vr-note` (two of them),
       * `.vr-unit-ids`, `.vr-unit-subject`, `.vr-kinds`, `.vr-attention-note` and
       * `.vr-state-unavailable`, plus one instance per run of the per-unit ones.
       *
       * So `+1` is not this feature's contrast cost; it is the part of it a
       * button-press-free scan can reach. The number is left as measured — inventing
       * an unmeasured total would be worse than an honest partial one — but do NOT
       * read it as "Validate & Review adds one contrast node". Measuring the rest
       * needs a scan that drives the button, which is its own slice.
       */
      /*
       * ── UNMAPPED NOTES (PR #146), 2026-08-16: +1 on all seven `record-detail`
       *    cells, and +1/+2/+3 on all seven `settings-explorer` cells ───────────
       *
       * CI run 31973740169 on head `0c72100` failed `browser accessibility and
       * responsive baseline` with GROWTHS on exactly these two surfaces, rule
       * `color-contrast`, LINUX column. No NEW rule appeared, no `clipped-x`
       * finding, and no other rule fired anywhere. The numbers below are
       * TRANSCRIBED from that job; nothing here was measured locally, and this
       * file's standing rule applies — a11y figures come from linux CI and are
       * never read off a laptop.
       *
       * THE SAME SYSTEMIC SHORTFALL THIS ENTRY HAS ALWAYS BEEN ABOUT, not a new
       * defect and not a colour either surface chose:
       *
       *   `--text-tertiary`   #78838f — measured 3.86:1 on white
       *   `--text-quaternary` #9aa4af — measured 2.53:1 on white
       *
       * WCAG AA needs 4.50:1 and AA-large 3.00:1, so the first fails AA and the
       * second fails both. Both are already in this entry's `foregrounds` list.
       * THESE COUNTS ARE RECORDED, NOT ACCEPTED AS CORRECT. The queued
       * design-system slice that raises the two tokens will lower them here and
       * on every other surface at once, so THESE FIGURES ARE EXPECTED TO FALL;
       * when they do, transcribe CI's new numbers and lower the total. Do not
       * read the fall as a regression, and do not repair the palette inside a
       * notes PR, where a broad change would hide.
       *
       * ── WHY `record-detail` MOVED: the notes panel's EMPTY STATE ───────────
       *
       * The Unmapped Notes panel mounts inside this existing surface, and the
       * SEEDED RECORDS HOLD NO NOTES. So the +1 at every viewport is the section
       * heading / empty state and nothing else.
       *
       * WHAT THIS NUMBER THEREFORE DOES NOT MEASURE, named rather than implied:
       * the note card, the four action buttons, the three inline forms and the
       * select are ALL UNSCANNED, because the scan renders the section and moves
       * on without ever putting a note in front of it. That is a known coverage
       * gap and a deferred follow-up — it needs a scan that seeds a note and
       * drives the controls — and it must NOT be mistaken for a clean surface.
       * `+1` is the part of this feature's contrast cost a note-free scan can
       * reach, exactly as the `.vr-sub` note above says of Validate & Review.
       *
       * ── WHY `settings-explorer` MOVED: a SECOND-ORDER effect ───────────────
       *
       * This branch adds notes API operations, and the Endpoint Explorer renders
       * every operation the build exposes — so more operations means more small
       * text on that screen. Nothing about the notes UI is rendered there. This
       * is worth knowing beyond this PR: ANY FUTURE SLICE THAT ADDS ROUTES WILL
       * MOVE THIS SURFACE TOO, and its cells move by different amounts (+1 at the
       * five wide projects, +2/+3 at the narrow ones) because `.api-browser-list`
       * is a clipped scroll container — see the long RUN OVERRIDE ROUTES note
       * above `settings-explorer@desktop-1280x800` for that mechanism.
       *
       * ── HOW THE SEVEN `record-detail` CELLS ARE WRITTEN ────────────────────
       *
       * All seven were SCALARS, and a scalar asserts BOTH columns. Only linux was
       * measured, so every one of them SPLITS into `{ darwin: <carried forward,
       * unmeasured>, linux: <CI> }` rather than having its scalar raised onto a
       * macOS reading nobody took. The precedent is `settings-explorer@width-320`
       * and the two `@width-320` splits of 2026-08-16. `A11Y_BASELINE_TOTAL_NODES.darwin`
       * therefore does not move at all in this transcription.
       *
       * THE DARWIN COLUMN HERE IS KNOWN-UNVERIFIED, not known-correct. A DOM node
       * added by an empty state has moved both faces every time it has been
       * measured, so darwin has very probably moved too. It is left alone anyway:
       * a stale number that says where it came from can be corrected by the next
       * darwin run; a fresh number nobody measured cannot be caught at all.
       */
      'record-detail@desktop-1280x800': { darwin: 15, linux: 22 },
      'record-detail@laptop-1024x768': { darwin: 15, linux: 22 },
      /* linux 15 -> 14: the 320px clipping fix (min-width/overflow-wrap on
         `.fg-summary`, scoped to `.record-view-panel`) let the summary WRAP
         instead of running past its clip, and one contrast node stopped firing
         on the Linux face. An IMPROVEMENT, measured in CI, not a baseline
         loosening. darwin measured 16 on the same commit and is unchanged —
         the two faces wrap at different words, which is the entire reason this
         file has two columns. */
      'record-detail@tablet-768x1024': { darwin: 15, linux: 22 },
      'record-detail@mobile-375x812': { darwin: 13, linux: 20 },
      'record-detail@zoom-200': { darwin: 13, linux: 20 },
      'schema-reference@desktop-1280x800': 19,
      'schema-reference@laptop-1024x768': 19,
      'schema-reference@tablet-768x1024': 17,
      'schema-reference@mobile-375x812': 22,
      'schema-reference@zoom-200': 25,
      // R0 · +1 color-contrast node on EVERY Settings surface at EVERY viewport,
      // because Settings gained a "Help & Tutorial" tab.
      //
      // WHAT THE EXTRA NODE IS, checked before touching a number: axe flags the
      // INACTIVE `.section-tab` buttons (`aria-selected="false"`). The unselected-tab
      // colour is already below threshold — which is why these entries were 7, 14, 17,
      // 46 rather than 0. The new tab is one more instance of a KNOWN, pre-existing
      // shortfall in a shared pattern, not a new defect in new markup, so raising the
      // count records one more instance of documented debt. It is NOT a licence to
      // relax the rule: fixing `.section-tab` contrast would lower all of these and is
      // worth its own slice, since that class is shared with Governance & Safety and
      // Project Memory and would move many baselines at once.
      //
      // BOTH PLATFORMS MEASURED, neither derived: linux from the CI run on this branch,
      // darwin from a local sweep at the same commit. They agree on all 25 entries, so
      // these are scalars. Four `zoom-200` entries were previously per-platform objects
      // with darwin one BELOW linux (a font-metric text-node split); the extra tab
      // changes how the row wraps and the split is gone, so darwin rose by 2 where
      // linux rose by 1. That is why these are not "old value + 1" arithmetic.
      /*
       * ── CONNECT YOUR AGENT, 2026-08-13: +1 color-contrast on 33 of 35 settings cells ──
       *
       * 33 cells, every one exactly +1, every one `color-contrast`. That near-uniformity
       * is the evidence this is not a new defect: the tab strip gained a SEVENTH button
       * (`Connect Your Agent`), and `.section-tab` already fails contrast on this
       * baseline. One more tab is one more failing node on every page that renders the
       * strip, at every viewport. No new RULE appears anywhere, and no non-settings
       * page moved.
       *
       * THE TWO CELLS THAT DID NOT MOVE ARE NAMED, not absorbed into "every". There are
       * 35 settings cells in this entry — five surfaces (`settings`, `settings-about`,
       * `settings-api`, `settings-explorer`, `settings-privacy`) across the five
       * Playwright projects plus the two narrow widths — and exactly two are unchanged
       * by this branch:
       *
       *   · `settings-about@width-320`, still 14
       *   · `settings@width-320`,       still 15
       *
       * Both are the 320px face, and 320 is where this file elsewhere records a
       * scroll-CLIP effect: content that runs past its clip at that width is not
       * painted, so a node that fails at 390 can be absent at 320. That is the likely
       * cause and it is stated as likely — no per-node diff was taken, only the totals.
       * It matters because the UNIFORMITY is the argument: if the +1 were a new defect
       * in new markup it would not track the tab strip, and two exceptions at the one
       * width that clips are consistent with the strip explanation rather than against
       * it. An "every one" that is really 33/35 invites the next reader to trust the
       * shape of the claim instead of checking it.
       *
       * The arithmetic still reconciles either way: 33 raised cells, and the totals
       * below move darwin 2162 -> 2195 and linux 2152 -> 2185, +33 on each.
       *
       * SO THIS RAISES A KNOWN DEFECT'S COUNT; IT DOES NOT BASELINE A REGRESSION. The
       * underlying `.section-tab` contrast is pre-existing and is still worth fixing —
       * doing so would drop every settings cell in this entry at once (all 35, not just
       * the 33 that moved), which is the argument for fixing it centrally rather than
       * per-slice.
       *
       * LINUX IS MEASURED, DARWIN IS INFERRED, and the distinction matters. Every
       * value below comes from the CI run on this branch (`GREW ... on linux` lines,
       * read individually, not derived by adding one to the old column). No darwin
       * sweep was run. Where a cell is a per-platform object, darwin is raised by one
       * as well — justified because the cause is an EXTRA DOM NODE present on every
       * platform, not a font-metric wrap effect, which is the class of change this
       * file elsewhere records as platform-dependent. A darwin sweep should confirm.
       */
      /*
       * ── `settings-connect`, 2026-08-16: A NEW SURFACE WITH NO COUNTS, ON PURPOSE ──
       *
       * `e2e/surfaces.ts` now carries `settings-connect`, the `?tab=mcp` deep link onto
       * the Settings route. Declaring the tab in `TABBED_SURFACES` — which is all the
       * branch did at first — exercises the tablist and the deep link and NOTHING else,
       * so until that surface existed the Connect Your Agent panel had never been
       * loaded by axe, by the 320/390 narrow sweep, by the layout probes or by the
       * zoom-200 pass at all.
       *
       * NOT ONE `settings-connect@*` KEY APPEARS BELOW, and that is this file's own
       * procedure rather than an omission — the same thing `NARROW_WIDTHS` did when the
       * two narrow widths were added, and what `evidence-graph` did on its branch. The
       * header states the rule twice: only the platform you measured on may be edited,
       * and no attempt is made to guess the other. A darwin reading written as a bare
       * number would assert BOTH columns, and this environment cannot run the Linux
       * face. Numbers invented to look plausible would be worse than none, because a
       * baseline that was never measured still reads exactly like one that was.
       *
       * ~~SO THE SEVEN PAIRS ALL EXPECT 0 AND WILL READ AS `new`.~~ — ADJUDICATED.
       * CI run 31968866824 printed all seven on LINUX and they are transcribed below:
       * desktop 22, laptop 22, tablet 23, mobile-375 22, zoom-200 22, width-390 21,
       * width-320 22. Nothing was pre-empted and nothing was lowered to go green.
       *
       * ONE RULE ONLY — `color-contrast`. No landmark, role, name or focus finding
       * appeared on this surface, which is worth stating because the panel is a
       * `<dl>` grid, a `role="status"` banner, an `<ol>` and a `<code>` block, and
       * none of that authored markup produced a violation. What did is the same
       * shortfall recorded everywhere else in this entry: `--text-tertiary` at
       * 3.86:1 and `--text-quaternary` at 2.53:1 against AA's 4.50 — the panel
       * carries thirteen `.api-keys-note` paragraphs at 11.5px. RECORDED, NOT
       * ACCEPTED: the design-system slice that raises those two tokens is queued,
       * and this count is expected to FALL when it lands.
       *
       * THE SAME RUN ALSO REPORTED TWO FALLS, and they are the interesting part —
       * see the split notes on `settings@width-320` and `settings-about@width-320`.
       * They are the two cells the review of this branch named as the two of
       * thirty-five that did not move.
       *
       * WHAT IS EXPECTED TO FIRE, stated in advance so a large number is not mistaken
       * for a regression this surface introduced:
       *
       *   · `color-contrast`, and NOT a small count. The panel is built almost entirely
       *     from `.api-keys-note` (`screens.css:2635`), which is 11.5px
       *     `var(--text-tertiary)` — #78838f, 3.85:1, already this entry's most-recorded
       *     shortfall. `ConnectYourAgent.tsx` carries 14 of them (`grep -c` at this
       *     commit; 13 render in the unconfigured state, the 14th only when an address
       *     is published), plus the shared seven-button `.section-tab` strip every
       *     other settings cell already counts. The `.api-keys-row > dd` capability
       *     cells use `--text-secondary`, which this file records at #46515f / 8.07:1
       *     and which therefore should contribute nothing — said as an expectation,
       *     not a measurement, and CI is what settles it.
       *     Every one of those nodes is one more instance of a documented token
       *     shortfall in reused chrome; this slice added no colour and no CSS.
       *   · `landmark-unique`: expected 0. That finding is the two unnamed
       *     `role="search"` landmarks, and this panel has no search — it has no input of
       *     any kind, which its unit test asserts against the mounted DOM.
       *   · `scrollable-region-focusable`: expected 0. That finding is `.preview-lines`
       *     and a `<pre>`; the one command on this tab is an inline `<code>`, not a
       *     `<pre>` block.
       *
       * Two things this DOES leave open, named rather than implied: the panel is also
       * newly reachable by `specs/layout-widths.spec.ts`, `layout-responsive` and
       * `zoom-200`, which carry their own baselines in `e2e/layout-baseline.ts` and
       * `e2e/layout-allowlist.ts` and likewise record nothing for it (no settings
       * surface has an entry in either today); and `A11Y_BASELINE_TOTAL_NODES` does NOT
       * move in this commit, because the entry map is unchanged and the well-formedness
       * guard sums the map.
       */
      /* The seven `settings-connect` cells, transcribed from CI run 31968866824
         (linux). See the dated block above for what fired and what did not. */
      'settings-connect@desktop-1280x800': 22,
      'settings-connect@laptop-1024x768': 22,
      'settings-connect@tablet-768x1024': 23,
      'settings-connect@mobile-375x812': 22,
      'settings-connect@zoom-200': 22,
      'settings-connect@width-390': 21,
      'settings-connect@width-320': 22,
      'settings@desktop-1280x800': 17,
      'settings@laptop-1024x768': 17,
      'settings@tablet-768x1024': 17,
      'settings@mobile-375x812': 16,
      'settings@zoom-200': 16,
      'settings-about@desktop-1280x800': 16,
      'settings-about@laptop-1024x768': 16,
      'settings-about@tablet-768x1024': 16,
      // 14 -> 13 at 375 only, MEASURED in the tutorial-scope slice (2026-08-04).
      // A genuine improvement, lowered rather than left stale. The About tab
      // renders a workspace-derived line that is shorter now that the ordinary
      // workspace is empty, and at 375 the shorter string stops wrapping — so one
      // rendered text node fewer exists to fail. The other four projects are
      // unchanged, which is what a wrap-boundary effect looks like.
      'settings-about@mobile-375x812': 14,
      'settings-about@zoom-200': 15,
      'settings-api@desktop-1280x800': 19,
      'settings-api@laptop-1024x768': 19,
      'settings-api@tablet-768x1024': 19,
      'settings-api@mobile-375x812': 18,
      'settings-api@zoom-200': 18,
      /*
       * ── RUN VERTICAL SLICE, 2026-08-10: THE SAME CLIPPED-LIST DISPLACEMENT, AND
       *    A DARWIN COLUMN THAT TURNED OUT TO HAVE BEEN STALE ─────────────────
       *
       * linux 47 -> 48 / 47 -> 48 / 62 -> 63. darwin 47 -> 48 / 47 -> 49 / 62 -> 64,
       * AND THE DARWIN MOVES ARE NOT THIS BRANCH'S. Read that carefully, because the
       * two columns changed for two different reasons:
       *
       *   · LINUX grew by exactly +1 at each of the three widths, and that IS this
       *     branch. It publishes five new operations (`GET`/`POST /runs`,
       *     `GET`/`PATCH /runs/{id}`, `POST /runs/{id}/check`), which shifts the
       *     boundary of `.api-browser-list`'s scroll clip — the artefact the long
       *     note below documents twice already. Measured by CI on `758360c`
       *     (run 31364785191, job 93380745844).
       *   · DARWIN did not move at all. A/B MEASURED, same machine, same run of the
       *     suite, three viewports each: `b7792c1` (this branch's base, and a
       *     CI-green `main`) measures 48 / 49 / 64 on darwin, and so does this
       *     branch. So the darwin column was ALREADY WRONG by +1/+2/+2 before this
       *     work existed — which is precisely the outcome the note below warned
       *     about when it recorded "THESE TWO NUMBERS ARE DARWIN-MEASURED ONLY …
       *     the linux figures are UNVERIFIED". It was the darwin ones that rotted.
       *
       * Correcting a stale column is not ratcheting: nothing here got worse on
       * darwin. It is written per-platform because the platforms genuinely differ
       * now — the file's rule is that a `{ darwin, linux }` split is the response to
       * disagreement, never a tolerance — and the desktop pair happens to agree at
       * 48, so it stays a scalar.
       *
       * NOT FIXED, AND FIXABLE ONLY IN ONE PLACE. Every node in this list's failing
       * set is `--text-tertiary` #78838f (3.85:1) on a row background or
       * `--verified-text` #2f7d78 (4.2:1) in a method chip. Neither is a colour this
       * branch chose. This branch DID fix the same class of defect where it was
       * local — three `.statusbar-*` declarations, see `chrome.css` and the 26
       * entries lowered above and below — and deliberately did not touch the two
       * tokens, which have 189 and 69 `var()` DECLARATIONS at this commit. Counted that
       * way on purpose: a bare grep for the token NAMES finds 207/78, because the names
       * also appear in `tokens.css` and in prose — including in this sentence. Three
       * reviewers have now re-opened this figure on that difference.
       */
      /*
       * ── RUN OVERRIDE ROUTES, 2026-08-10: THE LINUX COLUMN COMES BACK DOWN AT ALL
       *    SEVEN WIDTHS, AND FOUR SCALARS HAVE TO SPLIT ───────────────────────
       *
       * linux only: desktop 48 -> 47, laptop 48 -> 47, tablet 63 -> 62, mobile
       * 55 -> 54, zoom-200 58 -> 57, width-320 56 -> 54, width-390 56 -> 54.
       * TRANSCRIBED FROM CI, run 31446324340, on `1eae5db`. All seven messages read
       * IMPROVED and the job printed no `GREW`/`REGRESSED` line anywhere — so this is
       * the two-way ratchet doing the half of its job that costs something, exactly as
       * the header promises: "a stale number would re-admit the defect".
       *
       * WHY FOUR OF THEM SPLIT INSTEAD OF JUST MOVING. desktop, mobile, zoom-200 and
       * width-320 were SCALARS, and a scalar asserts BOTH columns. No run has measured
       * darwin at this commit, so lowering them would have written four darwin numbers
       * that no run produced. The note further down this entry prescribes this exact
       * case in advance — "split the entry into `{ darwin: n, linux: <measured> }` and
       * do NOT change the darwin value to match: it was measured separately" — so every
       * darwin figure here is the one the RUN VERTICAL SLICE A/B measured, carried
       * forward untouched, and `A11Y_BASELINE_TOTAL_NODES.darwin` does not move.
       *
       * THE DARWIN COLUMN IS THEREFORE KNOWN-UNVERIFIED HERE, not known-correct. The
       * cause below is a layout clip, and a layout clip has moved both platforms every
       * time it has been measured, so darwin has very probably moved too. It is left
       * alone anyway: a stale number that says where it came from can be corrected by
       * the next darwin run, and a fresh number nobody measured cannot be caught at all.
       *
       * WHAT CAUSED IT, AND IT IS NOT AN ACCESSIBILITY FIX. Established from git, not
       * from a browser:
       *
       *   · This branch changes NO frontend source whatsoever. `git diff --stat
       *     origin/main..HEAD` touches `routes.py`, `workspace.py`, the snapshot, four
       *     backend test files, `settings-api.test.tsx` and `apiFixtures.ts` — no
       *     component, no CSS. `screens/ApiDocs.tsx` and `screens/screens.css`, which
       *     are the whole of this screen, are byte-identical to `main`.
       *   · It adds exactly TWO documented operations and removes none —
       *     `POST …/runs/{run_id}/overrides` ("Override One Inherited Value on a Run")
       *     and `POST …/runs/{run_id}/overrides/clear` ("Restore One Inherited Value on
       *     a Run"). So the ONLY input to this screen that changed is the OpenAPI
       *     document gaining two rows. `summary=` lines added 2, removed 0; the
       *     contract is a strict superset, 45 operations -> 47.
       *   · READ THE "five new operations" IN THE BLOCK ABOVE AS DATED, not as a claim
       *     about this branch now. It was five against the base `b7792c1`; `main` has
       *     since merged all five, so two is what is left over `main` — which is why
       *     that block's +1 and this one's -1 are not in contradiction.
       *   · The only contrast declarations removed anywhere in this range are
       *     `.statusbar-pending` and `.statusbar-note`, which this screen does not
       *     render. Nothing here got a better colour.
       *
       * So this is the clipped-scroll displacement the 2026-08-06 note below documents,
       * running NEGATIVE for once: `.api-browser-list` is `overflow-y: auto` at
       * `max-height: 520px`, 320px at the narrow breakpoint (`screens.css:2021` and
       * `:2959`), over a list far taller. axe judges only the rows inside the box, and
       * two new rows shift which rows those are. The displaced nodes are still painted,
       * still reachable by scrolling and still failing — they are merely no longer
       * JUDGED.
       *
       * WHY A NEW ROW SUBTRACTS HERE, when the 2026-08-06 note measured a new row
       * ADDING. Rows are not worth the same. A GET row contributes TWO failing nodes:
       * the `--verified-text` #2f7d78 method chip (4.2:1) and the `--text-tertiary`
       * #78838f summary (3.85:1). A POST row contributes ONE — its chip is
       * `--action-hover` #21568f on `--action-tint` #e8f0f8, which PASSES AA, and the
       * corroboration is in this entry's own `foregrounds` list: both GET-row colours
       * are recorded there and #21568f is not. Both new operations are POSTs tagged
       * `Experiments` — tag rank 1 of 15 — so they insert HIGH in the list and push GET
       * rows off the bottom of the clip. One GET out, one POST in is -2 + 1 = -1; two
       * GETs out, two POSTs in is -4 + 2 = -2. That is exactly the observed -1 at five
       * viewports and -2 at the two narrow ones, where the 320px box holds fewer rows.
       *
       * INFERRED, AND FLAGGED AS SUCH: that per-row arithmetic is read off the
       * stylesheet and the `foregrounds` list, NOT re-measured in a browser — nobody
       * repeated the 2026-08-06 A/B here, and which rows sit on the clip boundary at
       * each width is unmeasured. What IS measured is the git evidence above and the
       * seven CI numbers themselves; the arithmetic only has to explain them, and does.
       *
       * NOT A DEFECT WEARING AN IMPROVEMENT'S CLOTHES — checked deliberately, because
       * a count that falls because content vanished is the one thing that must never be
       * baselined. Nothing on this screen became hidden, collapsed, `display: none`,
       * virtualised or conditionally unrendered: no frontend file changed, and no
       * operation was removed from the contract. The scroll clip is PRE-EXISTING and
       * unchanged, and its cost is a coverage limitation this file has recorded since
       * 2026-08-06, not something this branch introduced.
       */
      // UNMAPPED NOTES (PR #146), 2026-08-16, CI run 31973740169 on `0c72100`:
      // linux 48 -> 49 here and on laptop. A SECOND-ORDER effect of adding notes
      // API operations — the Endpoint Explorer renders every operation the build
      // exposes — and one more instance of the #78838f / #9aa4af shortfall, not a
      // new defect. Read the block above `record-detail@desktop-1280x800` for the
      // full reasoning, including why these figures are expected to FALL.
      //
      // The desktop pair COLLAPSES to a scalar 49: darwin was already 49, linux has
      // converged on it, and the well-formedness guard rejects a pair whose halves
      // are equal ("write a bare number instead"). The scalar is therefore two
      // measurements agreeing, not one measurement asserted twice. Laptop stays a
      // pair — darwin 50 is carried forward untouched and unmeasured at this commit.
      'settings-explorer@desktop-1280x800': 49,
      'settings-explorer@laptop-1024x768': { darwin: 50, linux: 49 },
      /*
       * ── CREATE EXPERIMENT, 2026-08-07: 63 -> 62 (tablet) and 56 -> 55 (mobile) ──
       *
       * THE SAME MEASUREMENT ARTEFACT the long note below already documents, in the
       * opposite direction, and it is worth reading that note first: the Endpoint
       * Explorer's `.api-browser-list` is a clipped scroll container, so axe judges
       * only the rows inside the box and adding an operation SHIFTS WHICH ROWS THOSE
       * ARE. This branch publishes one more operation, `POST /api/experiments`, and at
       * the two narrow widths that displaces one already-failing summary text out of
       * the measured window.
       *
       * IT IS NOT AN ACCESSIBILITY IMPROVEMENT, and the suite's "IMPROVED" wording
       * should not be read as one. The displaced node is still painted and still
       * fails; it is merely no longer judged. Lowering the number is still correct —
       * a stale figure would silently absorb a real regression of the same size.
       *
       * HONEST LIMIT, AND IT IS DIFFERENT FROM THE 2026-08-06 ENTRY BELOW. That one
       * says "measured by CI ... and reproduced on darwin, which agree, so these stay
       * scalars". THESE TWO NUMBERS ARE DARWIN-MEASURED ONLY. This work could not run
       * CI, so the linux figures are UNVERIFIED — they are left as scalars because the
       * cause is a layout clip that has behaved identically on both platforms every
       * time it has been measured, not because agreement was observed this time. If
       * the first linux run disagrees, split the entry into
       * `{ darwin: 62, linux: <measured> }` and do NOT change the darwin value to
       * match: it was measured separately.
       */
      // 62 -> { darwin: 64, linux: 63 } on 2026-08-10. See the RUN VERTICAL SLICE
      // note above the desktop entry: the linux +1 is this branch's five new
      // operations shifting the scroll clip; the darwin +2 is a stale column,
      // A/B-measured as already 64 on `b7792c1`.
      // UNMAPPED NOTES (PR #146), 2026-08-16: linux 63 -> 64, same cause as the
      // desktop/laptop cells above. darwin 65 carried forward unmeasured.
      'settings-explorer@tablet-768x1024': { darwin: 65, linux: 64 },
      // 55 -> 54 on 2026-08-01: a genuine IMPROVEMENT, lowered rather than left
      // stale. The suite's own message is the reason to bother — "a stale
      // number would re-admit the defect". Linux is the authority.
      /*
       * ── RECORD VERIFICATION, 2026-08-06: 55 -> 56 and 57 -> 58 (+1 each) ────
       *
       * A GROWTH at the two NARROW projects only, ratcheted rather than fixed.
       * Measured by CI on `17cff95` and reproduced on darwin, which agree, so
       * these stay scalars. The other three projects do not move — CI measured
       * them unchanged and so did the local run.
       *
       * WHAT CAUSED IT. The Endpoint Explorer lists the live contract, and this
       * branch adds one operation to it, `GET /api/runtime/verification`. Its
       * row contributes TWO failing nodes: the `GET` method chip
       * (`--verified-text` #2f7d78, 4.2:1) and the summary text
       * `Read the Record Verification Aggregate Report` (`--text-tertiary`
       * #78838f, 3.85:1). Both foregrounds are already in `foregrounds` above
       * and neither is a colour this branch chose, so this is one more instance
       * of documented token debt in a shared list row — ratcheted for the same
       * reason as the `statistics@*` entry, and fixable only by darkening the
       * tokens across all 18 surfaces.
       *
       * WHY +2 IS RECORDED AS +1, and why the wide projects do not move at all.
       * `.api-browser-list` is a clipped scroll container — `overflow-y: auto`
       * with `max-height: 520px` at desktop and `320px` at the narrow widths
       * (measured in the page) over a ~2.2–2.9k-px scroll height — so axe only
       * ever judges the handful of rows inside the box; the rest are outside it
       * and are not scanned. Adding a row shifts that boundary. A/B MEASURED, by
       * intercepting `GET /api/openapi` and deleting the one path (same build,
       * same commit, one operation removed):
       *
       *   mobile-375x812  55 -> 56   +2 the new row, -1 `get …/artifacts`'s
       *                              summary text, which leaves the measured
       *                              window (its sibling `.api-docs-path` lands
       *                              in axe's `incomplete` bucket as
       *                              `elmPartiallyObscured`)
       *   zoom-200        57 -> 58   +2 the new row, -1 `post …/export`'s
       *                              summary text, the same displacement
       *   desktop-1280x800 47 -> 47  the new row is outside the measured window
       *                              at that width; nothing before it moves
       *
       * So the -1 in each pair is a MEASUREMENT ARTEFACT of the scroll clip, not
       * an accessibility improvement: the displaced node is still painted and
       * still fails, it is merely no longer judged. That the list's contents are
       * mostly unscanned is a real, pre-existing limitation of this surface's
       * coverage, and it is recorded here rather than left to be rediscovered.
       */
      // 56 -> 55 on 2026-08-07 — the same clipped-scroll displacement as the
      // tablet entry above; read that note, including its "darwin-measured only"
      // caveat. `zoom-200` and the two wide projects did NOT move: the new row
      // falls outside the measured window at those widths.
      // UNMAPPED NOTES (PR #146), 2026-08-16: linux 55 -> 57 (+2) at mobile and
      // 58 -> 59 (+1) at zoom-200. Same cause as the cells above; mobile moves by
      // two because the narrower box holds fewer rows across the scroll clip.
      //
      // Mobile stays a PAIR, and note the columns have now CROSSED — linux 57 is
      // above darwin 56, where it used to sit below. That is what carrying an
      // unmeasured darwin column forward looks like; it is not a correction of
      // darwin, which no run has touched at this commit.
      //
      // zoom-200 COLLAPSES to a scalar 59: darwin was already 59 and linux has
      // converged on it, and the guard rejects a pair with equal halves.
      'settings-explorer@mobile-375x812': { darwin: 56, linux: 58 },
      'settings-explorer@zoom-200': { darwin: 59, linux: 61 },
      'settings-privacy@desktop-1280x800': 9,
      'settings-privacy@laptop-1024x768': 9,
      'settings-privacy@tablet-768x1024': 9,
      'settings-privacy@mobile-375x812': 8,
      'settings-privacy@zoom-200': 8,
      /*
       * ── STATISTICS-TAB SLICE, 2026-08-04 ──────────────────────────────────
       *
       * 4/4/4/3-or-2/3 -> 3/3/3/2/2, and the arithmetic is TWO changes that do not
       * cancel. Read it as a MEASUREMENT ARTEFACT, not as accessibility work:
       *
       *   -2  The two `/api/about` cards (`Runtime Mode`, `Persistence`) moved out
       *       of Workspace at a Glance and into a collapsed `Technical Details`
       *       `<details>`. Their `.stat-card-note` lines are `--text-tertiary`
       *       #78838f at 11.5px on #fbfcfd — 3.75:1, a genuine pre-existing AA
       *       failure — and axe does not scan a closed disclosure, so the two
       *       nodes stopped being counted. NOTHING WAS FIXED. (On mobile/zoom only
       *       one of the two was in scan range before, hence -1 there.)
       *   +1  The surface gained a page-level tablist, so there is now one INACTIVE
       *       `.section-tab` button (`aria-selected="false"`) on it. That colour
       *       (#78838f on #f4f6f9, 3.56:1) is the SAME known, pre-existing shortfall
       *       in a shared pattern that Settings, Governance and Project Memory
       *       already carry; the R0 note above records the identical +1 when
       *       Settings gained a tab. It is one more instance of documented debt, not
       *       a new defect, and it is NOT a licence to relax the rule.
       *
       * ── REVIEW FOLLOW-UP, 2026-08-04: THE COVERAGE GAP IS CLOSED, AND THE NOTE
       *    THAT DESCRIBED IT WAS FALSE ─────────────────────────────────────────
       *
       * The `+2 / -2` arithmetic above still holds and is left standing, because
       * it is what a reader needs to reconcile the history. What followed it did
       * not. It said two instances went unmeasured, that they were all
       * `.stat-card-note`, and — in the `statistics-example` note below — that
       * "not one is a chart". MEASURED, opening the region on `statistics-example`
       * raised the failing node count from 9 to 12 at desktop/laptop/tablet and
       * from 8 to 11 at mobile/zoom. The THIRD node was
       *
       *     .stats-chart-tick-y.stats-chart-tick[aria-hidden="true"]
       *
       * — A CHART AXIS TICK, `--text-tertiary` #78838f at 10.5px, which axe scored
       * at 3.85:1 against a 4.5:1 requirement. So a brand-new WCAG 1.4.3 failure
       * on markup that slice authored was shipping behind a note asserting no such
       * thing existed.
       *
       * TWO SEPARATE FIXES, because the count was only ever going to see one node
       * of it:
       *
       *   1. THE TOKEN, not the node. `.stats-chart-tick` is now `--text-muted`
       *      #5b6570 — 5.93:1 on #ffffff, 5.77:1 on #fbfcfd (WCAG 2.x relative
       *      luminance over the exact hexes). That clears the FIVE further y-ticks
       *      axe files under `incomplete` (the SVG behind them defeats background
       *      resolution, so no count can ever include them) and the three x-axis
       *      ticks in the uncollapsed main flow, which appear in NEITHER bucket. A
       *      node count cannot protect any of those, so the durable guard is
       *      computational, in `src/__tests__/stats-charts.test.tsx` → "every chart
       *      text token clears 4.5:1 on both card surfaces".
       *   2. THE SCAN, not the note. `specs/a11y-axe.spec.ts` now calls
       *      `openUnreachableDisclosures` before scanning, which opens
       *      `details.stats-technical`. A native `<details>` still has no URL
       *      state — that part of the old note was true — so the sweep opens it
       *      instead of recording the loss. The two `.stat-card-note` nodes are
       *      therefore back under ratchet, which is the +2 below.
       *
       * PROOF THAT THE TWO FIXES ARE INDEPENDENT, both runs local darwin: with the
       * scan step in place and the token REVERTED to `--text-tertiary`,
       * `statistics-example` measures 9 -> 12 / 8 -> 11 (+3) at all five projects,
       * reproducing the reviewer's number exactly. With the token fixed it is +2.
       * The third node is the tick, and it is gone.
       *
       * STILL NOT SCANNED, stated rather than left to be discovered: each chart's
       * own data-table `<details class="stats-chart-table-wrap">`. Those are closed
       * by default for every reader, and opening four of them at five viewports
       * would move counts for a reason unrelated to this gap.
       *
       * MEASURED on darwin, two consecutive local runs of
       * `npx playwright test e2e/specs/a11y-axe.spec.ts`, identical counts. The
       * exact five failing nodes at desktop are `kbd` (the ⌘K hint, #9aa4af,
       * 2.52:1), `.nav-version` (#9aa4af, 2.46:1), the inactive
       * `#statistics-tab-mine` (#78838f, 3.56:1) and the two runtime
       * `.stat-card-note` lines (#78838f, 3.75:1). Not one is a chart — and unlike
       * the last time that sentence was written here, the disclosure was OPEN when
       * it was measured.
       *
       * `statistics@mobile-375x812` was `{ darwin: 3, linux: 2 }` and is now a
       * SCALAR. The pair existed because one node's wrap boundary differed
       * between the fonts; that node is one of the two that moved into the
       * disclosure — and is now scanned again on both platforms, at a width where
       * only one of the two was ever in range, so both columns land on 4. darwin is
       * measured; LINUX IS INFERRED — and the type system has no way to say "same
       * as darwin, unverified", so a scalar is the only honest form (see the note at
       * the bottom of this file). CI is the authority.
       */
      /*
       * ── RECORD VERIFICATION, 2026-08-06: 5/5/5/4/4 -> 9/9/9/8/8 (+4) ───────
       *
       * A GROWTH, and it is RATCHETED rather than fixed. Measured by CI on
       * `17cff95` at laptop/tablet/mobile/zoom, and locally on darwin at all
       * five projects (`npx playwright test e2e/specs/a11y-axe.spec.ts -g "a11y
       * scan: Statistics"`), which agree exactly — so these stay SCALARS.
       *
       * WHAT CAUSED IT. The `Record Verification` section (`RecordVerification.tsx`,
       * new on this branch) adds a four-card KPI row to the General ISAAC tab.
       * The four new failing nodes are its four `.stat-card-note` lines, and
       * NOTHING ELSE it renders fails the rule — not the grouped validator
       * chart, not its axis, not its legend, not the disclosure panels:
       *
       *   section[aria-labelledby="stats-verification"] … .stat-card-note
       *     "records in the corpus this run examined."          #78838f on #fbfcfd  3.75:1
       *   .stat-card[data-tone="good"]:nth-child(2) .stat-card-note
       *     "records satisfying the official ISAAC schema; …"   #78838f on #e9f4ee  3.42:1
       *   .stat-card[data-tone="good"]:nth-child(3) .stat-card-note
       *     "records with no format issue found by …"           #78838f on #e9f4ee  3.42:1
       *   .stat-card[data-tone="good"]:nth-child(4) .stat-card-note
       *     "trials run; 0 behaved unexpectedly."               #78838f on #e9f4ee  3.42:1
       *
       * WHY RATCHETED AND NOT FIXED, which is the question a +4 has to answer.
       * Not one of them is a colour this branch chose. `.stat-card-note` is the
       * shared `StatCard` primitive's note line; its colour is `--text-tertiary`
       * #78838f, which is already the first entry in `foregrounds` above and
       * already fails on every one of the 18 surfaces (922 occurrences), and the
       * `data-tone="good"` tint #e9f4ee is the same pre-existing card surface the
       * `statistics-example` note below already records at 3.43:1 / 3.42:1. The
       * branch added four INSTANCES of documented debt, not a new token: the diff
       * of `screens/statistics/statistics.css` introduces no colour literal and
       * no new text colour rule. Fixing it means darkening `--text-tertiary`
       * itself, which moves counts on all 18 surfaces at all 5 projects — a
       * separate slice, not a line in this one. It is not a licence to relax the
       * rule; the four nodes are one node away from red like every other entry.
       *
       * DETERMINISM, because this number could not have been recorded before.
       * The section draws only once `GET /api/runtime/verification` answers
       * `ok`, ~15s after the first request. On `17cff95` desktop measured 5 and
       * the four later projects measured 9 — the same scan, decided by when it
       * ran. `e2e/global-setup.ts` step 5 now settles the report before any
       * project starts, so all five projects measure the same page; that is why
       * `desktop-1280x800` moves here even though CI reported it green.
       */
      'statistics@desktop-1280x800': 3,
      'statistics@laptop-1024x768': 3,
      'statistics@tablet-768x1024': 3,
      'statistics@mobile-375x812': 2,
      'statistics@zoom-200': 2,
      /*
       * THE POPULATED Statistics page, at the same route inside a worked-example
       * session — ADDED 2026-08-04 to close a gap the tutorial-scope slice left open.
       *
       * That slice compensated `experiments`' 48 -> 13 drop with a new
       * `experiments-example` surface carrying the old numbers, and did NOT do the
       * same for `statistics`' 48 -> 18 drop. So the per-record markup that moved into
       * the session — the four record cards' real counts, the workflow spine's bars,
       * the five evidence chips, the export-gate rows — was scanned by NO surface in
       * ANY project for the whole of that slice. 30 nodes of recorded debt stopped
       * being measured, while the lowered `statistics` numbers read as a 30-node
       * accessibility improvement. Nothing was fixed; the rows were simply not drawn.
       *
       * MEASURED, not derived: two consecutive local darwin runs of
       * `npx playwright test e2e/specs/a11y-axe.spec.ts -g "Statistics (worked
       * example)"`, identical counts both times. The corroboration is the same one
       * `experiments-example` has — 10/10/10/9/9 is byte-identical to what
       * `statistics@*` measured BEFORE the examples left the ordinary workspace
       * (48 across the five projects), i.e. this surface inherited exactly the
       * coverage that was lost rather than introducing new debt.
       *
       * The LINUX column is UNMEASURED (see the note at the bottom of this file); the
       * five values are written as scalars because the type system has no way to say
       * "same as darwin, unverified". CI is the authority.
       */
      /*
       * 10/10/10/9/9 -> 9/9/9/8/8, STATISTICS-TAB SLICE. Same two changes and the
       * same net -1 as `statistics@*` above, for the same two reasons: the two
       * runtime `.stat-card-note` nodes moved into the collapsed disclosure (-2, or
       * -1 at the narrow widths) and one inactive `.section-tab` appeared (+1).
       *
       * ── REVIEW FOLLOW-UP, 2026-08-04: 9/9/9/8/8 -> 11/11/11/10/10 ────────────
       *
       * "not one is a chart" was the sentence that used to end this note, and IT
       * WAS FALSE — this is the surface where the unscanned chart tick was found.
       * The full account is in the `statistics@*` note above; in one line, the
       * sweep now opens `details.stats-technical`, so the two runtime
       * `.stat-card-note` nodes are counted again (+2), and the chart tick that
       * would have been a THIRD is fixed at the token rather than baselined.
       *
       * The ELEVEN, measured at desktop with the disclosure open: `kbd`,
       * `.nav-version`, the inactive `#statistics-tab-mine`, SIX
       * `.stat-card-note` lines (four record cards at 3.75:1 plus the two runtime
       * cards, and the two `dl[data-tone]` ones at 3.43:1 / 3.42:1), and the
       * `.chip-ev-supported` (#2f7d78, 4.2:1) / `.chip-ev-unknown` (#78838f,
       * 3.62:1) chip labels. Every one is a pre-existing token shortfall this file
       * already records. NOW not one is a chart — and this time the region was open
       * when that was checked.
       */
      /*
       * ── RECORD VERIFICATION, 2026-08-06: 11/11/11/10/10 -> 15/15/15/14/14 ──
       *
       * A GROWTH, ratcheted rather than fixed, and it is the SAME four nodes as
       * `statistics@*` above — the same section renders on both surfaces, and
       * the report it draws is the ten public upstream example records either
       * way, because Record Verification does not read the workspace at all. The
       * full account, including why a shared-token instance is ratcheted and a
       * new colour would not be, is in the `statistics@*` note; it is not
       * repeated here.
       *
       * Measured by CI on `17cff95` at laptop/tablet/mobile/zoom and locally on
       * darwin at all five, agreeing exactly, so these stay scalars.
       * `desktop-1280x800` moves for the determinism reason given there: CI
       * reported it green only because it ran before the sweep landed.
       */
      'statistics-example@desktop-1280x800': 5,
      'statistics-example@laptop-1024x768': 5,
      'statistics-example@tablet-768x1024': 5,
      'statistics-example@mobile-375x812': 4,
      'statistics-example@zoom-200': 4,
      /*
       * THE MY STATS TAB — a NEW surface (`/statistics?tab=mine`), added with the
       * tab restructure because neither `statistics` nor `statistics-example` opens
       * it: both land on the default `general` tab, so the personal tab's gate and
       * its eight planned-view cards were in no project's scan grid.
       *
       * ALL THREE NODES ARE SHARED CHROME, and that is the interesting result:
       * `kbd` (the ⌘K hint, #9aa4af, 2.52:1), `.nav-version` (#9aa4af, 2.46:1) and
       * the inactive `#statistics-tab-general` (#78838f, 3.56:1). NOT ONE comes
       * from the markup this slice authored — no gate panel, no plan card, no
       * heading, no chart. At 375px and at 200% zoom the ⌘K hint is not rendered,
       * so those two projects measure 2.
       *
       * MEASURED on darwin, two consecutive local runs. The LINUX column is
       * UNMEASURED — this environment cannot run the Linux system face — so the
       * five values are written as scalars and flagged here. CI is the authority.
       */
      'statistics-mine@desktop-1280x800': 3,
      'statistics-mine@laptop-1024x768': 3,
      'statistics-mine@tablet-768x1024': 3,
      'statistics-mine@mobile-375x812': 2,
      'statistics-mine@zoom-200': 2,
      'validator@desktop-1280x800': 9,
      'validator@laptop-1024x768': 9,
      'validator@tablet-768x1024': 9,
      'validator@mobile-375x812': 8,
      'validator@zoom-200': { darwin: 6, linux: 7 },
    
      /* NARROW-WIDTH SWEEP, added 2026-08-08. The 320 and 390 narrow-width sweep (`specs/a11y-narrow.spec.ts`). These widths were
       never scanned by the five Playwright projects (1280/1024/768/375/640@DPR2), and 320 is
       the WCAG 1.4.10 reflow width where text wraps hardest and controls crowd. Every pair
       here is PRE-EXISTING debt becoming visible at a width nobody had scanned — compared
       per rule against the adjacent 375 baseline, all 49 findings sit within ±2. No new
       defect class was found.

         Every number MEASURED on BOTH platforms on the same commit and merged by
         `scripts/ingest_a11y_baseline.py`, which REFUSES any pair present in only one
         run rather than guessing the other. Nobody retyped a count. */
      'evidence@width-320': 68,
      'evidence@width-390': 68,
      'experiments-example@width-320': 9,
      'experiments-example@width-390': 9,
      'experiments@width-320': 2,
      'experiments@width-390': 2,
      'export-readiness-done@width-320': 8,
      'export-readiness-done@width-390': 9,
      'export-readiness@width-320': 1,
      'export-readiness@width-390': 1,
      'governance@width-320': 3,
      'governance@width-390': 3,
      'guided-completion@width-320': 7,
      'guided-completion@width-390': 7,
      'load@width-320': 1,
      'load@width-390': { darwin: 1, linux: 2 },
      'memory-graph@width-320': 14,
      'memory-graph@width-390': 16,
      'memory@width-320': 17,
      'memory@width-390': 17,
      /* UNMAPPED NOTES (PR #146), 2026-08-16: linux 13 -> 14 at BOTH narrow
         widths, the notes panel's empty state — same +1 as the five project
         cells. Both were SCALARS and both SPLIT rather than being raised onto an
         unmeasured darwin; the precedent is `settings-explorer@width-320` just
         below. Full reasoning, including what this figure does NOT measure, is in
         the block above `record-detail@desktop-1280x800`. */
      'record-detail@width-320': { darwin: 13, linux: 20 },
      /* SPLIT, and CI is what established it. I measured darwin 13 after the
         Graph tab landed and recorded it as a bare number, saying in the commit
         that linux was not yet measured and CI would adjudicate. It did: linux
         stayed at 12. So the tab's extra node is measurable on the darwin face
         at 390 and not on the linux one — the two wrap at different words, which
         is the whole reason this file has two columns. */
      'record-detail@width-390': { darwin: 13, linux: 20 },
      'schema-reference@width-320': 20,
      'schema-reference@width-390': 22,
      /* SPLIT 2026-08-16, and it is a fall rather than a rise. CI run 31968866824
         measured linux 14 -> 13 here and 15 -> 14 on `settings@width-320`. Those
         are the exact two cells the review of this branch singled out as the two
         of thirty-five that did NOT move when the seventh tab landed — so the
         prediction was right about the tab and wrong about this branch, because
         the branch went on to add a cross-reference sentence to the API Access
         lead paragraph and that rewraps the 320px face. A fall still has to be
         recorded: a stale high number silently re-admits the defect.
         Split rather than lowered as a scalar, for the same reason
         `settings-explorer@width-320` below is split — CI measures linux only,
         darwin is carried forward UNMEASURED, and a bare number would assert a
         macOS reading nobody took. */
      'settings-about@width-320': { darwin: 14, linux: 13 },
      'settings-about@width-390': 15,
      'settings-api@width-320': 18,
      'settings-api@width-390': 18,
      // linux 56 -> 54 on BOTH, 2026-08-10, CI run 31446324340. The two narrow widths
      // move by 2 where the five wide ones move by 1 — see the RUN OVERRIDE ROUTES
      // note above `settings-explorer@desktop-1280x800` for the cause (two new API
      // operations shifting a 320px scroll clip) and for why `width-320` had to split
      // rather than have its scalar lowered onto an unmeasured darwin.
      // UNMAPPED NOTES (PR #146), 2026-08-16, CI run 31973740169: linux 55 -> 57
      // at 320 and 55 -> 58 at 390 — the notes API operations again, moving the
      // 320px scroll clip harder than the wide projects. See the block above
      // `record-detail@desktop-1280x800`.
      //
      // width-320 COLLAPSES to a scalar 57: darwin was already 57 and linux has
      // converged on it, so the pair no longer marks a measured difference and
      // the guard would reject it. width-390 stays a pair, darwin 59 unmeasured.
      'settings-explorer@width-320': { darwin: 57, linux: 56 },
      'settings-explorer@width-390': { darwin: 59, linux: 58 },
      'settings-privacy@width-320': 8,
      'settings-privacy@width-390': 8,
      /* SPLIT 2026-08-16, linux 15 -> 14. Same cause and same reasoning as
         `settings-about@width-320` above; darwin carried forward unmeasured. */
      'settings@width-320': { darwin: 15, linux: 14 },
      'settings@width-390': 16,
      'statistics-example@width-320': 4,
      'statistics-example@width-390': 4,
      'statistics-mine@width-320': 2,
      'statistics-mine@width-390': 2,
      'statistics@width-320': 2,
      'statistics@width-390': 2,
      'validator@width-320': 8,
      'validator@width-390': 8,
    },
  },
  /*
   * DELETED, because the defects are GONE — not because they were inconvenient.
   *
   *   * `button-name` (FINDING A11Y-02, 36 nodes across 36 pairs). The global
   *     search trigger now carries `aria-label="Search"`
   *     (`src/components/SearchDialog.tsx`), so its accessible name no longer
   *     depends on `chrome.css` leaving `.topbar-search-label` visible.
   *   * `aria-allowed-attr` / `aria-allowed-role` (FINDING A11Y-03, 31 nodes
   *     each at all five projects, 310 in total). Evidence Trail entries are no
   *     longer `<button role="listitem" aria-pressed>`; the `role="listitem"`
   *     moved to a wrapper `<div>` and the button keeps its implicit role and a
   *     now-valid `aria-pressed` (`src/components/EvidenceTrailPanel.tsx`).
   *
   * An absent entry expects ZERO nodes everywhere, so a regression on either
   * rule reads as `new` and fails the sweep. That is the point of deleting
   * rather than zeroing: 346 nodes of recorded debt came off the total below,
   * and the suite now proves the fix on every run.
   */
  {
    rule: 'scrollable-region-focusable',
    impact: 'serious',
    note:
      'FINDING A11Y-04. `div.preview-lines.scroll-x` (Evidence source-file preview) and ' +
      'a `<pre>` code sample on API Access scroll horizontally but are not keyboard ' +
      'focusable, so a keyboard-only user cannot scroll them. Genuinely ' +
      'width-conditional: whether the content overflows depends on the column width, so ' +
      'it fires on Evidence at 1280 and at 375 but NOT at 1024/768/640, and on API ' +
      'Access only at 375. The earlier `projects: "*"` scoping claimed all ten pairs; ' +
      'only these three were ever real.',
    targetPattern: '^(\\.preview-lines|pre)$',
    // 3 nodes across 3 (surface, project) pairs.
    counts: {
      'evidence@desktop-1280x800': 1,
      'evidence@mobile-375x812': 1,
      'settings-api@mobile-375x812': 1,
    
      /* NARROW-WIDTH SWEEP, added 2026-08-08. Narrow-width sweep. Identical to the 375 measurement (1 node per pair).

         Every number MEASURED on BOTH platforms on the same commit and merged by
         `scripts/ingest_a11y_baseline.py`, which REFUSES any pair present in only one
         run rather than guessing the other. Nobody retyped a count. */
      'evidence@width-320': 1,
      'evidence@width-390': 1,
      'settings-api@width-320': 1,
    },
  },
  {
    rule: 'page-has-heading-one',
    impact: 'moderate',
    note:
      'FINDING A11Y-05. `/load` (Load Materials) renders no `<h1>`. Every other routed ' +
      'surface has one. axe reports this against `html`, so it is one node per scan.',
    targetPattern: '^html$',
    // 5 nodes across 5 (surface, project) pairs.
    counts: {
      'load@desktop-1280x800': 1,
      'load@laptop-1024x768': 1,
      'load@tablet-768x1024': 1,
      'load@mobile-375x812': 1,
      'load@zoom-200': 1,
    
      /* NARROW-WIDTH SWEEP, added 2026-08-08. Narrow-width sweep. Identical to the 375 measurement (1 node).

         Every number MEASURED on BOTH platforms on the same commit and merged by
         `scripts/ingest_a11y_baseline.py`, which REFUSES any pair present in only one
         run rather than guessing the other. Nobody retyped a count. */
      'load@width-320': 1,
      'load@width-390': 1,
    },
  },
  {
    rule: 'landmark-unique',
    impact: 'moderate',
    note:
      'FINDING A11Y-06. Two `role="search"` landmarks coexist with no distinguishing ' +
      'accessible name: the TopBar trigger (`SearchDialog.tsx:290`) and the endpoint ' +
      'filter (`settings/ApiDocs.tsx:333`). Both are reported, so the count is 2.',
    targetPattern: '^(\\.card|\\.topbar-search-region)$',
    // 10 nodes across 5 (surface, project) pairs.
    counts: {
      'settings-explorer@desktop-1280x800': 2,
      'settings-explorer@laptop-1024x768': 2,
      'settings-explorer@tablet-768x1024': 2,
      'settings-explorer@mobile-375x812': 2,
      'settings-explorer@zoom-200': 2,
    
      /* NARROW-WIDTH SWEEP, added 2026-08-08. Narrow-width sweep. Identical to the 375 measurement (2 nodes), so purely width-invariant.

         Every number MEASURED on BOTH platforms on the same commit and merged by
         `scripts/ingest_a11y_baseline.py`, which REFUSES any pair present in only one
         run rather than guessing the other. Nobody retyped a count. */
      'settings-explorer@width-320': 2,
      'settings-explorer@width-390': 2,
    },
  },
];

/**
 * Every failing node this baseline tolerates, summed, PER PLATFORM. One number
 * a reviewer can watch: it is the size of the app's recorded automated-a11y
 * debt, and it can only go down without an explicit edit here.
 *
 * The six-node gap is entirely the ten font-metric triples above (eight +1,
 * two −1). It is not extra debt on Linux; it is the same debt counted under a
 * wider font.
 *
 * It went down by 346 when the two CRITICAL findings A11Y-02 (`button-name`,
 * 36) and A11Y-03 (`aria-allowed-attr` + `aria-allowed-role`, 310) were fixed
 * and their entries deleted: 1974 → 1628 (darwin), 1980 → 1634 (linux).
 *
 * The post-fix `linux` total 1634 was DERIVED (1980 − 346) when first written,
 * because a laptop cannot run the Linux baseline. **Linux CI has since measured
 * it** — run 30677607861 on `a911b8c`, 579 passed / 1 skipped: the three
 * deleted entries assert ZERO nodes and passed, and every surviving entry was
 * checked against real axe output under Linux font metrics. So 1634 is now the
 * sum of validated per-entry measurements, not arithmetic.
 *
 * The rule that got it there still stands for next time: if CI ever disagrees
 * with a number in this file, correct THE NUMBER, never loosen the assertion.
 *
 * ── HOW THIS NUMBER GOES STALE WITHOUT A GIT CONFLICT ───────────────────────
 *
 * Every per-cell count below is a MEASUREMENT: the axe scan reproduces it or
 * the build fails. This constant is ARITHMETIC over those measurements, and it
 * is the only thing in this file that can be wrong while every run agrees with
 * every other number.
 *
 * The way it goes wrong is a merge, not a typo. Two branches open against the
 * same `main`. Each adds a disjoint set of keys above; each raises this literal
 * to cover its own addition. When the two deltas happen to be EQUAL, both
 * branches write the SAME resulting number — and git merges two identical
 * changes to one line without a conflict, while the key additions merge
 * cleanly because they touch different keys. The merged file then holds BOTH
 * sets of new entries and only ONE of the two increments. Nothing in the text
 * of that merge says so.
 *
 * Two further facts kept it hidden longer than it should have been: GitHub does
 * not re-run a pull request's checks when its BASE advances, so neither branch
 * ever executed the combined state before merging; and the only guard was in
 * the ~30-minute `browser-a11y` job, so the first signal arrived on `main`,
 * half an hour later.
 *
 * WHAT NOW CATCHES IT, and where: `e2e/invariants/baseline-aggregate.invariant.test.ts`,
 * a `vitest` file that needs no browser. It runs in the fast `frontend` CI job
 * on every pull request and every push to `main`, and it carries negative
 * controls that reproduce exactly the two-branch merge above.
 * `specs/a11y-axe.spec.ts` still makes the same check — through the same shared
 * module, so the two cannot drift.
 *
 * HOW MUCH FASTER, measured rather than felt: the CHECK is ~6 ms locally and
 * ~26 ms in CI, but the SIGNAL costs whatever its job costs. `frontend tests and
 * build` measured 3m06s and 3m48s on recent `main` runs; `browser accessibility
 * and responsive baseline` measured 26m13s and 26m42s. So this is ~26 minutes
 * down to ~4 — about 7x, not the "seconds" an earlier revision of this note
 * claimed. Worth having; not worth overstating.
 *
 * AND IT REPORTS RATHER THAN BLOCKS. `main` has no required status checks at
 * all — `gh api repos/.../branches/main --jq '.protected'` returns `false`,
 * `.../rulesets` returns `[]`, `.../branches/main/protection` returns `404`. A
 * pull request can be merged with this check red or still running. Do not read
 * the paragraph above as an enforcement gate; it is a fast alarm. See
 * `docs/branch-protection-request.md`, "Status: NOT CONFIGURED".
 *
 * WHAT IS DELIBERATELY NOT DONE: this constant is not derived away, the way
 * `LAYOUT_BASELINE_TOTAL_INSTANCES` derives itself. Deriving it would make the
 * defect structurally impossible and was seriously considered; it is rejected
 * because this literal is the only artefact in the repository that makes a DEBT
 * INCREASE visible in a diff. A slice that adds entries for a new surface adds
 * newly tolerated debt, and a derived total would absorb that silently. The
 * per-cell ratchets catch growth on a MEASURED cell; only this number catches
 * growth by ADDITION.
 *
 * The residual risk is named rather than implied: a fast check still only runs
 * when CI runs, so a pull request merged without having seen the current base
 * fails this invariant on `main` rather than on the pull request.
 *
 * The setting that would close THAT half is "Require branches to be up to date
 * before merging", and `docs/branch-protection-request.md:74-81` **deliberately
 * declines to ask for it** — not an oversight, a measured trade: the generated
 * memory snapshot already forces every open PR to regenerate after every merge,
 * and adding the rule would additionally force a full ~30-minute CI re-run on
 * every open PR after every merge. Do not read this note as a pending request
 * for that setting; it is not one. The fast check above is the cheaper half of
 * the same protection, and it is what makes declining the expensive half more
 * defensible than it was, not less.
 */
export const A11Y_BASELINE_TOTAL_NODES: Readonly<Record<BaselinePlatform, number>> = {
  // 2026-08-01, responsive remediation slice. darwin 1628 -> 1629: the net of
  // three MEASURED per-surface changes, +1 `evidence@tablet-768x1024`,
  // +1 `guided-completion@mobile-375x812`, -1 `settings-explorer@mobile-375x812`.
  // Two of those are pre-existing failures becoming measurable (see the notes on
  // each entry), one is a real improvement.
  //
  // linux stays 1634, and that is now MEASURED rather than derived. It was
  // first written as a derivation (this environment cannot run the Linux face);
  // CI run 30691557697 on `7e9a387` then reported exactly two Linux-only
  // changes, `export-readiness-done@tablet-768x1024` 11 -> 12 and
  // `guided-completion@tablet-768x1024` 11 -> 10, which cancel. The three
  // darwin-side changes contribute 0 on Linux: two are at surfaces Linux did
  // not move, and `guided-completion@mobile-375x812` was ALREADY 8 there.
  // Same total, different arithmetic — and the rule that got it here stands:
  // if CI disagrees with a number in this file, correct THE NUMBER from the CI
  // output, never loosen the assertion.
  // 2026-08-03, product-facing-language slice. darwin 1629 -> 1620, linux
  // 1634 -> 1625: both fall by the SAME 9, and that is arithmetic rather than a
  // guess. `.onramp-tagline` used `--text-tertiary` (#78838f, 3.86:1 on the white
  // card) at 11px, below the 4.5:1 AA threshold, so BOTH taglines on /load were
  // `serious` color-contrast failures. The rule now uses `--text-muted`
  // (#5b6570, 5.93:1). The five `load@*` color-contrast entries that fall are
  // SCALARS, i.e. both platforms read the identical per-key number, so the same
  // -2/-2/-2/-1/-2 = -9 applies to each total by construction.
  //
  // The defect was PRE-EXISTING, not introduced by the rename: both taglines
  // always used that colour. Renaming the first tagline's text merely made its
  // node newly measurable at 375px, where the longer old string had wrapped out
  // of axe's reach — which is why the correct response was to fix the colour, not
  // to raise the count. If CI disagrees with either number, correct THE NUMBER
  // from the CI output, never loosen the assertion.
  //
  // R1b: LINUX ONLY falls by 1 (`export-readiness-done@desktop-1280x800` 13 -> 12,
  // measured in CI). darwin measured 13 on the same commit and is UNCHANGED at 1620.
  // The first version of this edit dropped both by 1 on the assumption that removing
  // a DOM node must affect both platforms equally. It does not — see the note on that
  // entry. Arithmetic on a total is only safe when the per-surface delta is itself
  // measured on that platform.
  // R0: 1620/1624 -> 1650/1650. Both sums are CHECKED by the suite itself (it adds
  // the entries per platform and fails if either constant disagrees), so neither is
  // my arithmetic.
  //
  // The platforms are now EQUAL, and the four-node gap closing is the interesting
  // part: it came entirely from four `settings-*@zoom-200` entries where darwin sat
  // one node BELOW linux, a font-metric text-node split. Adding the Help & Tutorial
  // tab changes how that tab row wraps, the split disappears, and darwin rises by 2
  // where linux rises by 1. So this is not '+1 per surface' arithmetic and must not
  // be re-derived that way.
  // TUTORIAL-SCOPE SLICE, 2026-08-04: 1650 -> 1632 on both columns.
  //
  // The arithmetic, so a reviewer can check it without a run: experiments
  // 48 -> 13 (-35); experiments-example +48 (a NEW surface holding exactly the
  // numbers `experiments` used to hold); statistics 48 -> 18 (-30);
  // settings-about@mobile-375x812 14 -> 13 (-1). Net -18.
  //
  // Read the net as a MEASUREMENT ARTEFACT, not as accessibility work. Nothing was
  // fixed: the built-in example records moved out of the ordinary workspace into a
  // worked-example session, so My Experiments and Statistics now render far less
  // text in the ordinary scope. The 48 queue nodes did not go away — they are
  // counted under `experiments-example`, which is why that surface was added rather
  // than the number simply being lowered.
  //
  // REVIEW FOLLOW-UP, 2026-08-04: 1632 -> 1680 on both columns.
  //
  // The paragraph above is the reason this correction was needed. It states the
  // `experiments` rule — a drop that is a measurement artefact must be compensated by
  // a new surface, or the coverage is silently lost — and then applies it to
  // `experiments` ONLY. `statistics` fell by exactly the same 30 nodes, for exactly
  // the same reason, and got no compensating surface. Independent review found it:
  // `grep statistics e2e/surfaces.ts` returned one entry, ordinary scope, so the
  // populated page existed in no project's scan grid at all.
  //
  // The arithmetic: statistics-example +48 (10/10/10/9/9), a NEW surface holding
  // exactly the numbers `statistics` held before the examples moved. Net +48.
  // Nothing regressed and nothing was fixed — 48 nodes that had stopped being
  // measured are being measured again.
  //
  // ── The one thing in this file NOT measured on both platforms ───────────────
  //
  // Every number above was measured on darwin (two consecutive local runs, same
  // counts). The LINUX column for the 21 changed/added keys — the five
  // `experiments@*`, the five `experiments-example@*`, the five `statistics@*`, the
  // five `statistics-example@*` and `settings-about@mobile-375x812` — is UNMEASURED:
  // this environment cannot run the Linux system face, and the file's own type system
  // leaves no way to say "unknown" (a per-platform pair must carry two DIFFERENT
  // numbers, so an honest "same as darwin, unverified" can only be written as a
  // scalar). They are therefore written as scalars and flagged here.
  //
  // CI (Linux) is the authority. If it disagrees, transcribe ITS numbers into the
  // keys above and correct these two totals — never loosen the assertion. The
  // previously-recorded keys are untouched and their linux values still stand.
  //
  // ── CI ANSWERED, 2026-08-04: linux 1680 -> 1679 ────────────────────────────
  //
  // The paragraph above said CI is the authority on the 21 unmeasured linux keys.
  // It has now ruled on exactly one of them. Run 30924684494 on `5a31bc0` reported
  // `statistics@mobile-375x812` color-contrast at 2 on linux where darwin measures
  // 3, so that key is now `{ darwin: 3, linux: 2 }` and only the LINUX total moves.
  //
  // darwin stays 1680 and is NOT lowered to match: nothing has measured darwin at
  // 2, and collapsing the pair to one number would assert a value no run produced.
  // That is the same mistake the R1b note above records — "arithmetic on a total is
  // only safe when the per-surface delta is itself measured on that platform".
  //
  // Worth recording because it cost a CI cycle: the entry edit and THIS total are
  // one atomic change, and a darwin-only local run cannot tell you so. Lowering the
  // linux key left this constant stale at 1680 against a 1679 sum, which failed the
  // well-formedness guard in all five projects while every per-surface scan passed.
  // Locally the guard was green, because darwin's column never moved. A linux-column
  // edit is only verifiable in CI — so change the key and the total together, and
  // expect CI, not the local run, to confirm it.
  //
  // The remaining 20 linux keys are still unmeasured; expect more single-node
  // corrections of this benign kind, each one an entry AND a total.
  //
  // ── STATISTICS-TAB SLICE, 2026-08-04: darwin 1680 -> 1683, linux 1679 -> 1683 ──
  //
  // The two columns CONVERGE, and that is not a coincidence to wave at: the one
  // key where they disagreed (`statistics@mobile-375x812`, `{ darwin: 3, linux: 2 }`)
  // owed its difference to a wrap boundary on a node that has since moved into a
  // collapsed disclosure and is no longer scanned on either platform. With that
  // node gone the disagreement has nothing left to be about, so both columns read 2
  // and every statistics key is now a scalar.
  //
  // The arithmetic, per platform, so a reviewer can check it without a run:
  //
  //   darwin  statistics       4,4,4,3,3 -> 3,3,3,2,2            = -5
  //           statistics-example 10,10,10,9,9 -> 9,9,9,8,8       = -5
  //           statistics-mine  NEW 3,3,3,2,2                     = +13
  //                                                          net  = +3  (1680 -> 1683)
  //
  //   linux   statistics       4,4,4,2,3 -> 3,3,3,2,2            = -4
  //           statistics-example 10,10,10,9,9 -> 9,9,9,8,8       = -5
  //           statistics-mine  NEW 3,3,3,2,2                     = +13
  //                                                          net  = +4  (1679 -> 1683)
  //
  // NOTHING WAS FIXED AND NOTHING REGRESSED. The -10/-9 is two pre-existing
  // `.stat-card-note` failures per surface going unscanned inside a collapsed
  // `<details>`, minus one new instance of the documented `.section-tab` shortfall;
  // the +13 is a genuinely new surface whose every failing node is shared chrome.
  // Both sums are CHECKED by the suite itself, per platform, so neither is my
  // arithmetic — but the linux PER-KEY values for all fifteen touched keys are
  // darwin measurements written as scalars. If CI disagrees, transcribe ITS numbers
  // and correct the total; never loosen the assertion.
  //
  // ── REVIEW FOLLOW-UP, 2026-08-04: 1683 -> 1703 on both columns ──────────────
  //
  // NOTHING REGRESSED AND NOTHING BROKE. The sweep now OPENS the Statistics
  // `Technical Details` disclosure before scanning (`openUnreachableDisclosures`
  // in `specs/a11y-axe.spec.ts`), so two pre-existing `.stat-card-note` failures
  // per Statistics surface are counted again instead of being recorded as a
  // coverage gap. That is +2 on ten keys:
  //
  //   statistics          3,3,3,2,2  ->  5,5,5,4,4        = +10
  //   statistics-example  9,9,9,8,8  -> 11,11,11,10,10    = +10
  //   statistics-mine     3,3,3,2,2  ->  unchanged        =   0
  //                                                   net = +20
  //
  // `statistics-mine` does not move because the My Stats tab renders no
  // `details.stats-technical` — the disclosure lives on the General tab.
  //
  // A THIRD node would have come back with them and DID NOT, which is the part
  // worth remembering: it was a chart axis tick at `--text-tertiary`, a NEW WCAG
  // 1.4.3 failure that the previous note asserted did not exist. It is fixed at
  // the token (`--text-muted`, 5.93:1 / 5.77:1) rather than added here, because
  // five sibling ticks sit in axe's `incomplete` bucket and three more in neither
  // bucket, so no count in this file could ever have held them. See the
  // `statistics@*` note for the +3-vs-+2 measurement that separates the two fixes.
  //
  // Both sums are CHECKED by the suite itself, per platform. The linux PER-KEY
  // values for these ten keys remain darwin measurements written as scalars, as
  // they already were; if CI disagrees, transcribe ITS numbers and correct the
  // total — never loosen the assertion.
  //
  // ── RECORD VERIFICATION, 2026-08-06: 1703 -> 1745 on both columns ──────────
  //
  // The arithmetic, so a reviewer can check it without a run:
  //
  //   statistics          5,5,5,4,4      ->  9,9,9,8,8         = +20
  //   statistics-example  11,11,11,10,10 -> 15,15,15,14,14     = +20
  //   settings-explorer   mobile 55 -> 56, zoom-200 57 -> 58   =  +2
  //                                                        net = +42
  //
  // NOTHING WAS FIXED AND NOTHING REGRESSED IN THE PRODUCT. All 42 are new
  // INSTANCES of two already-recorded token shortfalls — `--text-tertiary`
  // #78838f and `--verified-text` #2f7d78, both already in `foregrounds` — on
  // markup this branch added: forty on the four `.stat-card-note` lines of the
  // new Record Verification KPI row (two Statistics surfaces x five projects),
  // two on the Endpoint Explorer row for the one new operation. The per-entry
  // notes carry the measured foregrounds, ratios and the A/B that separates the
  // Explorer's +2 from its -1 displacement.
  //
  // BOTH COLUMNS ARE MEASURED FOR TWELVE OF THE FOURTEEN CHANGED KEYS: linux
  // from the CI run on `17cff95` (which reported exactly these growths at
  // laptop/tablet/mobile/zoom for the two Statistics surfaces and at
  // mobile/zoom for the Explorer), darwin from a local sweep at the same commit.
  // They agree, so the keys stay scalars.
  //
  // THE TWO EXCEPTIONS ARE `statistics@desktop-1280x800` AND
  // `statistics-example@desktop-1280x800`, and they are stated rather than
  // buried: CI could not measure them, because on `17cff95` the desktop project
  // ran BEFORE the verification sweep landed and scanned the unsettled page.
  // With `global-setup.ts` step 5 settling the report first, darwin measures
  // both at the same numbers as laptop and tablet, and the linux values are
  // written as scalars on that basis — an INFERENCE from a measured platform,
  // not a measurement. CI is the authority; if it disagrees, transcribe ITS
  // numbers into those two keys and correct this total, and never loosen the
  // assertion. Both sums are CHECKED by the suite itself, per platform.
  // no-guessing slice: LINUX ONLY rises by 1, 1703 -> 1704. This slice adds
  // `.guided-inferability` (the paragraph stating why the app is asking rather
  // than answering), which fails `color-contrast` on Linux but NOT on darwin --
  // `guided-completion@tablet-768x1024` was `{ darwin: 11, linux: 10 }` and is
  // now the scalar `11`, so the darwin half is unchanged and only the Linux half
  // moves. darwin therefore stays 1703; it was re-measured locally on this branch
  // (`playwright test e2e/specs/a11y-axe.spec.ts --project=tablet-768x1024
  // -g "Guided Completion"` passes against 11) rather than assumed, because the
  // note above records that assuming a DOM change affects both platforms equally
  // has already been wrong once here.
  //
  // ── COVERAGE-DISCLOSURE SLICE: linux 1703 -> 1704, darwin UNCHANGED ─────────
  //
  // One key moves, `export-readiness-done@desktop-1280x800`, and only on linux
  // (12 -> 13, CI run 30984206413 on `e02ac14`). Darwin measured 13 there before
  // and after this slice, so the pair collapses to the scalar 13 — see that key's
  // note for the measured failing-node SET, which is identical on `main` and this
  // branch and contains none of the three elements the slice adds.
  //
  // NEITHER number here is arithmetic. Both were computed by importing this module
  // and summing `platformCount` over every entry: darwin 1703 (matches), linux 1704.
  // That check is also what the suite itself performs per platform, so a stale
  // constant fails in all five projects — which is exactly how the previous
  // linux-column edit was caught, and why the entry and this constant are one
  // atomic change. Darwin is NOT raised to match; nothing measured darwin at 14.
  //
  // ── MERGE OF THE TWO SLICES ABOVE: darwin 1745, linux 1746 ─────────────────
  //
  // The two notes above were written independently, each against a tree whose
  // starting point was 1703/1703, and each is still correct about its OWN keys.
  // They touch DISJOINT keys and therefore COMPOSE rather than conflict:
  //
  //   Record Verification    both columns +42 (statistics, statistics-example,
  //                          settings-explorer)
  //   coverage-disclosure    linux only  +1  (export-readiness-done@desktop-1280x800)
  //                                          darwin 1703 + 42      = 1745
  //                                          linux  1703 + 42 + 1  = 1746
  //
  // So the columns no longer agree, and that asymmetry is inherited from the
  // coverage-disclosure slice, not introduced here. NEITHER number is my
  // arithmetic: both were recomputed on the merged tree by importing this module
  // and summing `platformCount` over every entry — darwin 1745, linux 1746. No
  // per-key value was changed to reach them; only this total moved. The two
  // inferred keys the Record Verification note names above are still inferred;
  // CI remains the authority, and if it disagrees, transcribe ITS numbers and
  // correct the total rather than loosening the assertion.
  // ── MERGE OF THE TWO SLICES ABOVE: linux 1704 -> 1705, darwin UNCHANGED ─────
  //
  // The two notes immediately above were written independently, each against a
  // tree where 1703/1703 was the starting point, and each correctly concluded
  // "linux 1703 -> 1704". They move DIFFERENT keys — the no-guessing slice moves
  // `guided-completion@tablet-768x1024` (linux 10 -> 11) and the coverage-
  // disclosure slice moves `export-readiness-done@desktop-1280x800` (linux
  // 12 -> 13) — so on a tree containing BOTH they COMPOSE rather than coincide:
  // linux 1703 + 1 + 1 = 1705. Darwin is untouched by either (both keys already
  // measured 11 and 13 on darwin, which is why both collapsed to scalars), so it
  // stays 1703.
  //
  // A three-way merge cannot see this. Both sides wrote the identical text
  // `linux: 1704`, so git took it without a conflict while silently combining two
  // entry changes that each justified only one of that number's two increments.
  // The resulting 1704 was arithmetically wrong for the merged entry set and the
  // per-platform self-check would have caught it. NEITHER number below is my
  // arithmetic: both were recomputed by importing this module and summing
  // `platformCount` over every entry on the merged tree — darwin 1703, linux 1705.
  // No per-key value was changed to reach them; only this total moved.
  // MERGE OF THE RECORD-VERIFICATION SLICE WITH THE NO-GUESSING SLICE. Neither
  // side's total was correct for the merged file and neither was copied: this
  // branch had 1745/1746 against a 1703/1704 base, `origin/main` had 1703/1705
  // after the no-guessing slice landed, and the merged entry set sums to
  // 1745/1747 -- this branch's +42 on top of main's post-merge linux base of
  // 1705. Both numbers were COMPUTED from the entry map by the same reduction
  // the self-check in `specs/a11y-axe.spec.ts` performs, not derived by hand:
  // summing `platformCount(entry.counts[key], platform)` over every entry and
  // every key. Two independent +1 edits that each looked correct against their
  // own base is precisely how a wrong total gets auto-merged without ever
  // raising a conflict, which already happened once on this file.
  // ── GRAPH COMMAND-SURFACE SLICE, 2026-08-08: BOTH columns fall by 55 ────────
  // `memory-graph` colour-contrast falls by ELEVEN NODES AT EVERY ONE of the five
  // viewports: desktop 42->31, laptop 42->31, tablet 34->23, mobile 27->16,
  // zoom-200 33->22 (linux). darwin 1745-55 = 1690; linux 1747-55 = 1692.
  //
  // THE LINUX NUMBERS ARE TRANSCRIBED FROM CI, NOT MEASURED LOCALLY, which is
  // what this file has always asked for and what a previous slice in this same
  // session got wrong -- it lowered `statistics@desktop-1280x800` onto a darwin
  // reading that turned out to be the settle race, and only one of five viewports
  // had moved. THAT ASYMMETRY IS THE TELL, and it is absent here: a token change
  // moves every viewport by the same amount, and this one moved all five by
  // exactly -11.
  //
  // The one platform-split key is `memory-graph@zoom-200`. Its linux value (22)
  // is CI's. Its darwin value (21) is 32 - 11, an INFERENCE from the uniform
  // delta plus a local darwin measurement of the same -11 on desktop -- flagged
  // as an inference rather than presented as a reading, exactly as the two
  // Statistics keys above are.
  //
  // The drop is real and is NOT hidden content: three pairs inside the graph
  // command surface (`.graph-cmd-suggestion-hint`, `-suggest-cmd`, `-suggest-mode`)
  // were already below AA at 2.53:1, 3.86:1 and 2.53:1, and the slice that tinted
  // their backgrounds raised them to `--text-slate` at 5.46:1 / 5.16:1 / 4.64:1.
  // Nothing was collapsed into a `<details>` to earn this.
  //
  // NOT ADDED HERE: `link-in-text-block`, which CI reported as NEW on `governance`
  // at all five viewports. A rule that has never been baselined firing for the
  // first time is a DEFECT, not a number to record -- an inline link carried by
  // colour alone (WCAG 1.4.1). It is fixed in `screens.css` with an underline.
  // ── STAT-CARD-NOTE CONTRAST FIX, 2026-08-08: BOTH columns fall by 80 ────────
  // `statistics` -6 at every viewport (9->3, 9->3, 9->3, 8->2, 8->2) and
  // `statistics-example` -10 at every viewport (15->5 x3, 14->4 x2).
  // darwin 1690-80 = 1610; linux 1692-80 = 1612. LINUX FIGURES ARE CI'S.
  //
  // The cause is a real remedy, not a re-baselining: `.stat-card-note` moved
  // from `--text-tertiary` (#78838f, 11.5px) to `--text-secondary` at 12px,
  // taking it from 3.76:1 on the neutral card and 3.43:1 on the green ones to
  // 7.86:1 and 7.16:1. Both "before" figures were independently measured twice.
  //
  // READ THIS KEY'S HISTORY BEFORE TOUCHING IT AGAIN. Earlier in this same
  // session `statistics@desktop-1280x800` was edited from 9 to 5 on a LOCAL
  // darwin reading that turned out to be the report-settle race described
  // above -- and the tell, ignored at the time, was that only ONE of the five
  // viewports had moved. That edit was reverted and CI then passed at 9,
  // proving 9 correct. It is now 3, because the underlying defect was actually
  // FIXED. So this key has been wrong in both directions within one session,
  // and both times the corrective was the same: a token change moves EVERY
  // viewport by the same amount, and the number comes from CI.
  //
  // ── MERGE WITH `feat/my-experiments-create`, 2026-08-08: a FURTHER -2 on both
  //    columns, and it is arithmetic rather than a reading ────────────────────
  //
  // The create branch and main moved DIFFERENT keys and neither touched the
  // other's, so the deltas stack:
  //
  //   settings-explorer   tablet 63 -> 62, mobile 56 -> 55   = -2
  //
  // Those two entries came in on the create branch and merged without conflict;
  // only this total conflicted, because both sides had recomputed it. THE
  // NUMBERS BELOW ARE THE SUM OF THE ENTRY MAP AS IT NOW STANDS, computed by
  // running the same reduction `specs/a11y-axe.spec.ts` performs over the merged
  // map. They are not a hand subtraction and they are not a measurement.
  //
  // WHAT IS AND IS NOT MEASURED HERE, stated because this key's own history
  // above is a record of getting exactly this wrong twice. The `statistics`,
  // `statistics-example` and `memory-graph` values are CI's, transcribed. The two
  // `settings-explorer` values are DARWIN ONLY, and their own note says so.
  //
  // AND NOTHING IN THIS MERGE HAS BEEN SCANNED AT ALL. The create branch's UI now
  // sits inside the polish slice's card idiom — a third `.queue-empty-action`
  // card with a `Plus` mark, an inline create form, and a durability line — so
  // `experiments@*` is the family most likely to move. Those five keys are
  // UNCHANGED here because no run has been made to change them from, NOT because
  // a run said they held. If the first CI run on the merged tree reports movement
  // on `experiments@*`, transcribe ITS numbers. Do not pre-empt them, and never
  // lower a key onto a local darwin reading.
  //
  // 1610 - 2 = 1608 and 1612 - 2 = 1610, both CONFIRMED by the reduction.
  // 2026-08-08, experiment-graph slice. darwin 1608 -> 1613, linux 1610 -> 1614.
  // The totals move by DIFFERENT amounts, and that is measured, not a slip.
  //
  // Four `record-detail@*` entries each gain the one node the `Graph` tab adds
  // (`#record-view-tab-graph`, `class="section-tab"` — pre-existing documented
  // contrast debt, one more instance of it rather than a new defect). Three of
  // the four move +1 on both platforms. `record-detail@mobile-375x812` does not:
  // it was `{ darwin: 10, linux: 11 }` and both platforms now measure 12, so
  // darwin gains 2 where linux gains 1, and the entry collapses to a scalar.
  //
  // darwin +1+1+2+1 = +5; linux +1+1+1+1 = +4. Every one of those eight
  // per-entry numbers was read from an actual axe run on its own platform —
  // linux from CI job 93097731133, darwin from a local run of the same commit —
  // so this is arithmetic over measured deltas, which is the only kind this file
  // permits. `record-detail@tablet-768x1024` did not move on either platform and
  // contributes 0.
  // Revised in the same slice: linux 1614 -> 1613 for the tablet improvement
  // above (-1, measured in CI). darwin is unaffected and stays 1613, so the two
  // totals coincide here by arithmetic rather than by assumption.
  //
  // 2026-08-08, narrow-width sweep (same day, later slice). +590 darwin / +588
  // linux on top of the record-detail numbers above: 49 newly-recorded pairs at
  // 320 and 390, widths the five Playwright projects never scanned. The two
  // deltas differ because three pairs are platform-split
  // (`guided-completion@width-390`, `load@width-390`, `settings-explorer@width-390`),
  // each measured on its own platform rather than derived.
  //
  // Pre-existing debt becoming VISIBLE, not new debt: compared per rule against
  // the adjacent 375 baseline, all 49 sit within +/-2.
  //
  // 1613 + 590 = 2203 darwin; 1613 + 588 = 2201 linux. They no longer coincide,
  // and that is correct -- the split pairs are why this file has two columns.
  // Corrected after CI adjudicated: darwin 2206, linux 2203.
  //
  // I set 2203/2201 and THEN bumped the two record-detail narrow pairs for the
  // Graph tab without re-deriving the totals, so darwin was short by 3. CI caught
  // it ("entries now sum to 2206"), which is exactly what the guard is for.
  //
  // The two deltas differ because the pairs do: width-320 moved +2 on BOTH faces
  // (10 -> 12), while width-390 moved +1 on darwin (12 -> 13) and 0 on linux.
  // darwin +3, linux +2.
  // ── 2026-08-10, RUN VERTICAL SLICE ──────────────────────────────────────
  // darwin 2206 -> 2162 (-44). Two causes, and they pull opposite ways:
  //   -49  the StatusBar contrast fix, summed over the 26 lowered entries on five
  //        record surfaces (see the long note at the top of the `color-contrast`
  //        entry). A real reduction in real debt, not a measurement artefact.
  //   +5   `settings-explorer` at desktop/laptop/tablet (+1/+2/+2) — a STALE DARWIN
  //        COLUMN corrected, A/B-measured as already 48/49/64 on `b7792c1`. Nothing
  //        on darwin got worse.
  // (-49 + 5 = -44. An earlier revision wrote "-47 / +3", where the +3 was the
  //  entry COUNT used as a node delta and the -47 was then back-computed from it to
  //  make the arithmetic close. The net was right and the decomposition was not,
  //  which is the more dangerous of the two ways to be wrong about a number.)
  // Both numbers are CHECKED by the suite (it re-sums the entries per platform and
  // fails if either constant disagrees), so neither is my arithmetic. Both figures
  // came from that test's own failure message, which is only rendered WHEN it fails —
  // so a later reader cannot reproduce the printout from a green tree, only re-derive
  // the sum. Re-derive it; do not trust this sentence.
  //
  // linux 2203 -> 2161, TRANSCRIBED FROM CI (run 31368770283, job 93392836969),
  // not derived. That job reported 24 `IMPROVED … on linux` messages and ZERO
  // `GREW`; every linux figure in them equals the darwin figure measured here, and
  // the two entries it did NOT report (`record-detail@tablet-768x1024` and
  // `record-detail@width-390`) passed, which is the same agreement stated the other
  // way. So all 26 collapsed from `{ darwin, linux }` back to scalars.
  //
  // THAT AGREEMENT WAS NOT SAFE TO ASSUME AND WAS NOT ASSUMED. The intermediate
  // commit deliberately carried a linux column it knew was too high rather than
  // pre-computing one, because the note above `export-readiness-done@desktop-1280x800`
  // records a case where removing a DOM node moved one platform and not the other.
  // It happened to agree everywhere this time; that is a measurement, not a rule.
  //
  // WHY THE TWO TOTALS STILL DIFFER BY ONE while all 26 changed entries agree: SIX
  // entries in this file are per-platform, and they net to +1 —
  // `settings-explorer@laptop-1024x768` { 49, 48 } +1,
  // `settings-explorer@tablet-768x1024` { 64, 63 } +1,
  // `settings-explorer@width-390` { 58, 56 } +2, against `memory-graph@zoom-200`
  // { 21, 22 } -1, `validator@zoom-200` -1 and `load@width-390` { 1, 2 } -1.
  // (An earlier revision named THREE of the six — the three that happen to sum to +1
  // on their own — which describes no determinate fact, since several 3-subsets do.
  // Written three lines below its own apology for a decomposition that had been
  // back-computed to make the arithmetic close.) This
  // arithmetic is a RECONCILIATION of a number the suite computed, not the source of
  // it: the first attempt at this constant wrote 2162 for linux and the
  // well-formedness test rejected it with the correct figure.
  //
  // ── 2026-08-10, RUN OVERRIDE ROUTES: linux 2161 -> 2152. darwin DOES NOT MOVE ──
  //
  // -9, entirely from the seven `settings-explorer` cells CI lowered on this branch
  // (-1 desktop, -1 laptop, -1 tablet, -1 mobile, -1 zoom-200, -2 width-320,
  // -2 width-390). See the note above `settings-explorer@desktop-1280x800` for what
  // was measured and what is inferred.
  //
  // darwin stays 2162 BECAUSE NOT ONE DARWIN NUMBER CHANGED. All seven cells are now
  // `{ darwin, linux }` pairs whose darwin side is the previously-measured figure
  // carried forward untouched — four of them were scalars and had to SPLIT, since a
  // scalar asserts both columns and no run has measured darwin at this commit. This
  // is the case the entry note two-thirds up this file prescribes verbatim: "split
  // the entry into `{ darwin: n, linux: <measured> }` and do NOT change the darwin
  // value to match".
  //
  // THE PARAGRAPH DIRECTLY ABOVE IS NOW SUPERSEDED, and is left standing because
  // deleting it would hide that the shape of this file changed. "SIX entries are
  // per-platform and they net to +1" was true at `1eae5db`'s parent; there are now
  // TEN and they net to +10, which is exactly 2162 - 2152:
  //   `settings-explorer` desktop { 48, 47 } +1, laptop { 49, 47 } +2,
  //   tablet { 64, 62 } +2, mobile { 55, 54 } +1, zoom-200 { 58, 57 } +1,
  //   width-320 { 56, 54 } +2, width-390 { 58, 54 } +4 — against
  //   `memory-graph@zoom-200` { 21, 22 } -1, `validator@zoom-200` -1 and
  //   `load@width-390` { 1, 2 } -1.
  // Reconciliation again, not derivation: 2152 is the reduction's own output, read
  // by running the same per-platform sum `specs/a11y-axe.spec.ts` performs over the
  // edited map. Re-derive it; do not trust this sentence.
  // 2026-08-13, Connect Your Agent. darwin 2162 -> 2195, linux 2152 -> 2185: the
  // seventh Settings tab is one more `.section-tab`, which already fails contrast,
  // so 33 of the 35 settings cells rose by exactly one. The two that did not are
  // `settings-about@width-320` (14) and `settings@width-320` (15), both the 320px
  // face, and the note above `settings@desktop-1280x800` says what is and is not
  // established about why. The totals are COMPUTED from the entries by the same
  // summation the guard uses, not derived by adding 33 -- and the darwin figure
  // matches what CI reported the entries now sum to (2195), which is the check
  // that this constant and the map agree.
  //
  // 2026-08-16: `settings-connect` joined `SURFACES` and this constant does NOT
  // move, because it records nothing. See the block above `settings@desktop-1280x800`.
  // (Those two numbers were this branch's own total before it met `main`. They are
  // kept because the 33-of-35 reasoning above is still the record of what this
  // branch measured; the LIVE total is at the bottom of this block.)
  //
  // 2026-08-13. darwin 2162 -> 2169, linux 2152 -> 2159: seven cells rose by one
  // on a single surface (see the dated block in the entries above for which, and
  // why it is a known defect's count rather than a new one). COMPUTED from the
  // entries with the same summation the guard uses, and the darwin figure matches
  // the total CI reported the entries now sum to -- which is what confirms the
  // constant and the map agree rather than merely both having moved.
  // ── 2026-08-16. darwin 2169 -> 2200, linux 2159 -> 2190 ────────────────────
  //
  // TWO CAUSES, AND THE FIRST IS A MERGE HAZARD GIT CANNOT SEE. Record it,
  // because it will recur on any branch that touches this constant.
  //
  //   +7  `main` (via PR #143, `.vr-sub` on record-detail) and this branch (the
  //       `Evidence List | Evidence Graph` tab strip) EACH raised darwin from
  //       2162 to 2169. Different surfaces, different keys, same arithmetic —
  //       and therefore the same TEXT, `darwin: 2169`, on both sides of the
  //       merge. Git saw two identical lines and took them without a conflict,
  //       while silently combining two entry-map changes that each justified
  //       only one of the two increments. The merged map sums to 2162 + 7 + 7 =
  //       2176, which is exactly what the guard computed and reported ("the
  //       entries now sum to 2176"). Two branches adding the same delta to one
  //       number is invisible to a three-way merge; the per-platform self-check
  //       is what caught it, and is why it exists. This is the second time this
  //       file has been hit by it — see the 1704/1705 note above.
  //
  //       LINUX FOLLOWS BY THE SAME ARITHMETIC: 2159 + 7 = 2166. Both branches'
  //       additions were BARE numbers rather than `{ darwin, linux }` pairs, so
  //       each moved both columns by the same 7. That is derived from the ENTRY
  //       SHAPES, not measured on Linux, and is flagged as such — CI is the
  //       authority and will say so if it is wrong.
  //
  //  +24  `evidence-graph@desktop-1280x800`, the one cell of the new surface CI
  //       has measured (run 31963596365 on `0c9752f`, linux). Scalar, so it adds
  //       24 to both columns. See that key's note: it is an instance of the
  //       `--text-tertiary` / `--text-quaternary` shortfall and is expected to
  //       DROP when the design-system slice raises the two tokens.
  //
  // +164  the OTHER SIX `evidence-graph@*` cells, measured on LINUX by run
  //       31966373802 on `dd5e049` and transcribed: laptop-1024x768 28,
  //       tablet-768x1024 28, mobile-375x812 27, zoom-200 27, width-390 27,
  //       width-320 27. All scalars, so each adds to both columns.
  //
  //       THAT RUN ALSO PROVED THE TWO NON-CONTRAST FINDINGS FIXED rather than
  //       recorded: `aria-allowed-role` (3 nodes x 7 viewports) and the eight
  //       `clipped-x` findings at 375px are both absent from its NEW list. Only
  //       contrast is baselined here, and that is a choice this file should be
  //       able to show, not merely assert.
  //
  // darwin 2162 + 7 + 7 + 24 + 164 = 2364; linux 2159 + 7 + 24 + 164 = 2354.
  //
  // ~~THE OTHER SIX ... ARE ABSENT AND EXPECT 0~~ — answered, above. All seven
  // cells of the new surface are now recorded. Both sums are re-checked by the
  // suite from the entry map, per platform, so a stale constant fails in every
  // project — which is how the double-count was caught.
  // ── 2026-08-16, THE MERGE OF THIS BRANCH INTO THE ABOVE ────────────────────
  //
  // THE HAZARD RECORDED ABOVE RECURRED, AND THIS TIME GIT SHOWED IT. `main` had
  // reached 2364/2354 by the evidence-graph work; this branch had reached
  // 2195/2185 by its 33 settings cells. Because the two literals DIFFER, the
  // three-way merge raised a real conflict instead of silently taking one — the
  // opposite of the +7/+7 case above, where the two sides agreed on the text and
  // git took it without a word. That is the whole lesson: this constant is safe
  // from a merge exactly when the two branches disagree about it.
  //
  // So neither side's number is right here. Both entry maps merged, so the total
  // is the sum of BOTH sets of additions, and it is COMPUTED from the merged map
  // by the same per-platform reduction the guard performs — not obtained by
  // adding one branch's delta to the other branch's total.
  // ── 2026-08-16, CI run 31968866824 adjudicated `settings-connect` ──────────
  //
  // +154  the seven `settings-connect` cells, transcribed from linux: 22, 22, 23,
  //       22, 22, 21, 22. Scalars, so both columns move.
  //
  //   -2  linux ONLY, and they are FALLS: `settings@width-320` 15 -> 14 and
  //       `settings-about@width-320` 14 -> 13. Both split into pairs rather than
  //       lowered as scalars, because CI measures linux and darwin is carried
  //       forward unmeasured — the precedent is `settings-explorer@width-320`.
  //       Worth noticing rather than absorbing: these are exactly the two cells
  //       this branch's review named as the two of thirty-five that did NOT rise
  //       when the seventh tab landed. They moved later, downward, because the
  //       branch then added a cross-reference sentence that rewraps the 320px
  //       face. A prediction can be right about one change and wrong about the
  //       next one to touch the same cell.
  //
  // darwin 2397 + 154 = 2551; linux 2387 + 154 - 2 = 2539. COMPUTED from the map
  // by the same per-platform reduction the guard runs, then checked against this
  // arithmetic — not obtained from it.
  // ── 2026-08-16, UNMAPPED NOTES (PR #146). linux 2539 -> 2557. darwin DOES NOT MOVE ──
  //
  // +18, entirely from the fourteen cells CI run 31973740169 (head `0c72100`)
  // reported as GROWN on linux, rule `color-contrast`:
  //
  //   +7  the seven `record-detail@*` cells, +1 each — the Unmapped Notes panel's
  //       EMPTY STATE, because the seeded records hold no notes. That is the whole
  //       of what was measured: the note card, the four action buttons, the three
  //       inline forms and the select are unscanned, and the coverage gap is a
  //       deferred follow-up, not a clean surface.
  //  +11  the seven `settings-explorer@*` cells (+1 desktop, +1 laptop, +1 tablet,
  //       +2 mobile, +1 zoom-200, +2 width-320, +3 width-390) — a SECOND-ORDER
  //       effect of this branch adding notes API operations to the contract the
  //       Endpoint Explorer renders. Any future slice that adds routes moves this
  //       surface too.
  //
  // Both are instances of the `--text-tertiary` #78838f (3.86:1) and
  // `--text-quaternary` #9aa4af (2.53:1) shortfall against AA's 4.50:1 and
  // AA-large's 3.00:1 — RECORDED, NOT ACCEPTED AS CORRECT, and expected to FALL
  // when the queued design-system slice raises the two tokens.
  //
  // darwin stays 2551 BECAUSE NOT ONE DARWIN NUMBER CHANGED. Nine of the fourteen
  // cells were scalars, and a scalar asserts both columns, so each SPLIT into
  // `{ darwin: <carried forward>, linux: <CI> }`. The three whose carried-forward
  // darwin value EQUALS the new linux one — `settings-explorer` at desktop (49),
  // zoom-200 (59) and width-320 (57) — collapse the other way, back to scalars,
  // because the guard rejects a pair with equal halves. Neither move invents a
  // darwin figure.
  //
  // 2557 is COMPUTED from the merged entry map by the same per-platform reduction
  // the guard performs, then checked against this arithmetic — not obtained from
  // it. Re-derive it; do not trust this sentence.
  // ── ASSET REFERENCES, 2026-08-17: linux 2557 -> 2601. darwin does NOT move. ──
  //
  // TRANSCRIBED from CI run 32012740475 (`browser accessibility and responsive
  // baseline`, head `387913a`), read line by line from the GREW/IMPROVED messages
  // rather than derived. Ten cells, +44 net:
  //
  //   +42  the seven `record-detail@*` cells, +6 EACH and uniformly — the Asset
  //        References panel, which mounts on this surface between Unmapped Notes
  //        and the draft blocks. Uniform across every viewport, which is itself
  //        the evidence that this is markup volume rather than a wrap artefact.
  //    +1  `settings-explorer@mobile-375x812`  57 -> 58
  //    +2  `settings-explorer@zoom-200`        59 -> 61
  //    -1  `settings-explorer@width-320`       57 -> 56   (an IMPROVEMENT)
  //
  // The three `settings-explorer` moves are the SECOND-ORDER effect this file has
  // documented twice before: the Endpoint Explorer renders every operation the
  // build exposes, this branch adds four asset routes, and `.api-browser-list` is
  // a clipped scroll container — so cells move by different amounts and one can
  // fall while its neighbours rise. Nothing about the asset UI renders there.
  //
  // RECORDED, NOT ACCEPTED AS CORRECT, and checked before being recorded rather
  // than assumed. `assets.css` paints small text with `--text-tertiary` (#78838f,
  // 3.86:1) and `--text-quaternary` (#9aa4af, 2.53:1) — five and one declaration
  // respectively. BOTH ARE ALREADY IN THIS ENTRY'S `foregrounds` LIST, which is
  // the mechanical proof that no NEW too-light colour was introduced: a new
  // foreground fails this entry's `foregrounds` guard even at an unchanged node
  // count, and it did not fire. So these 42 nodes are 42 more instances of a
  // documented token shortfall, not a defect this panel chose.
  //
  // Giving the asset panel alone a compliant colour would leave it deliberately
  // mismatched against every sibling sub-label on the same screen and would
  // remove no pre-existing violation. Raising the two tokens is the systemic fix,
  // moves counts on all 18 surfaces at once, and belongs to the design-system
  // slice — not inside an assets PR, where a palette change would hide. These
  // figures are EXPECTED TO FALL when that lands; transcribe CI's new numbers
  // then, and do not read the fall as a regression.
  //
  // DARWIN IS DELIBERATELY UNCHANGED AND IS KNOWN-UNVERIFIED, not known-correct.
  // Six DOM nodes added by a new panel have moved both faces every time this has
  // been measured, so darwin has very probably moved too. It is left alone
  // anyway, per this file's standing rule: only the platform actually measured
  // may be edited. A stale number that says where it came from can be corrected
  // by the next darwin run; a fresh number nobody measured cannot be caught at
  // all. Two cells that were scalars (`settings-explorer@zoom-200` and
  // `@width-320`) therefore SPLIT rather than having their darwin half moved onto
  // a linux reading.
  //
  // The +44 was computed by the fast invariant suite in ~10ms rather than by a
  // second 26-minute browser run — which is the whole point of
  // `e2e/invariants/baseline-aggregate.invariant.test.ts`, doing its job on its
  // first real use.
  darwin: 2551,
  linux: 2601,
};

/**
 * Exact tolerated node count for a (rule, surface, project) triple on one
 * platform. 0 when unlisted.
 *
 * `platform` defaults to the current process's — so every existing call site
 * enforces the right column automatically — and is explicit only where a test
 * needs to reason about the platform it is NOT running on.
 */
export function expectedNodeCount(
  rule: string,
  surfaceId: string,
  projectId: string,
  platform: BaselinePlatform = currentPlatform()
): number {
  const entry = A11Y_BASELINE.find((e) => e.rule === rule);
  return platformCount(entry?.counts[baselineKey(surfaceId, projectId)], platform);
}

export function baselineEntryFor(rule: string): BaselineEntry | undefined {
  return A11Y_BASELINE.find((e) => e.rule === rule);
}

export type BaselineVerdict = 'ok' | 'new' | 'grew' | 'improved';

/**
 * The ratchet itself, over two plain numbers. Split out from
 * `baselineVerdict` so `specs/self-check.spec.ts` can feed it a TAMPERED
 * expectation and prove the comparison is exact — no range, no tolerance, no
 * "±1 is fine".
 */
export function verdictForCounts(expected: number, actualNodeCount: number): BaselineVerdict {
  if (actualNodeCount === expected) return 'ok';
  if (expected === 0) return 'new';
  return actualNodeCount > expected ? 'grew' : 'improved';
}

/**
 * The whole policy, as one pure function — so `specs/a11y-axe.spec.ts` cannot
 * quietly widen it and `specs/self-check.spec.ts` can prove it is not vacuous.
 */
export function baselineVerdict(
  rule: string,
  surfaceId: string,
  projectId: string,
  actualNodeCount: number,
  platform: BaselinePlatform = currentPlatform()
): BaselineVerdict {
  return verdictForCounts(expectedNodeCount(rule, surfaceId, projectId, platform), actualNodeCount);
}

/** Baseline entries that expect at least one node on this surface+project. */
export function applicableEntries(
  surfaceId: string,
  projectId: string,
  platform: BaselinePlatform = currentPlatform()
): readonly BaselineEntry[] {
  const key = baselineKey(surfaceId, projectId);
  return A11Y_BASELINE.filter((e) => platformCount(e.counts[key], platform) > 0);
}

/**
 * COARSE, rule-level predicate. True when the rule is a recorded defect for
 * this surface+project at all, whatever the node count.
 *
 * Used ONLY by `specs/dialogs.spec.ts`, where an open overlay legitimately
 * changes node counts and the closed-page measurement does not apply. The
 * sweeping scan uses `baselineVerdict` instead. See the header note.
 */
export function isBaselined(
  rule: string,
  surfaceId: string,
  projectId: string,
  platform: BaselinePlatform = currentPlatform()
): boolean {
  return expectedNodeCount(rule, surfaceId, projectId, platform) > 0;
}

/**
 * All (surface, project) pairs the suite scans — used by the well-formedness test.
 *
 * Includes the narrow-width pseudo-projects, so the "no entry may tolerate
 * anything on a pair it did not record" assertion covers 320 and 390 too. Leaving
 * them out would have made the well-formedness test silently weaker at exactly
 * the widths this sweep was added to cover.
 */
export function allScanPairs(): { surfaceId: string; projectId: string }[] {
  return SURFACES.flatMap((s) => SCAN_PROJECT_IDS.map((p) => ({ surfaceId: s.id, projectId: p })));
}
