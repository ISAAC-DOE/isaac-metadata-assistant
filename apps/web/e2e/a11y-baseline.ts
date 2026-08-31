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
 * nodes exist and which of them axe measures. ~~Ten of the 103 recorded triples
 * differ between the two platforms, every one of them by exactly ±1: the
 * signature of a single wrap boundary, not of a different app.~~
 *
 * **RE-MEASURED 2026-08-27, and both halves of that sentence are now wrong — kept
 * struck because the SECOND half is the one that mattered and it is the one that
 * failed.** ~~The file holds **168 cells**, of which **6** differ between the
 * platforms, not ten of 103.~~ — **BOTH FIGURES RE-COUNTED 2026-08-29 AND BOTH WERE
 * WRONG, in a sentence whose entire purpose was to replace two stale numbers with
 * measured ones.** On the day it was written the file held **168** cells of which
 * **8** differed, not 6; ~~at HEAD it holds **161** … of which **8** differ~~ —
 * **CORRECTED 2026-08-30, AND THE CORRECTION IS THE POINT OF THE INSTRUCTION IN THE
 * NEXT SENTENCE.** The cell count was right; the split count was the branch's, and the
 * MERGE moved it. `c7b9db6` adopted the linux halves CI measured at `6958459` and
 * five of the eight splits COLLAPSED to scalars. At HEAD the file holds **161** cells
 * of which **5** differ, and **156** are scalars. Re-derive rather
 * than quoting — strip comments, match `'<surface>@<project>': <count-or-pair>`, and
 * count the pairs whose halves are unequal. That instruction was in this paragraph
 * already, and following it is what found this. And they do NOT all differ by ±1:
 * `settings-about@width-320` is `{ darwin: 9, linux: 7 }`, a gap of 2, and
 * `settings-explorer@tablet-768x1024` is `{ darwin: 72, linux: 74 }`, a gap of 2.
 * ~~`settings-explorer@width-320` is now `{ darwin: 76, linux: 73 }`, a gap of 3~~ —
 * **that cell is a SCALAR `76` at HEAD and no cell in this file has a gap of 3.**
 * More to the point, the day this file recorded
 * TWENTY splits, **15 of them were not platform differences at all** — they were a
 * darwin column nothing had measured since a CI transcription moved their linux twin.
 * "Every one by exactly ±1" was doing real work in the argument above (it is what made
 * a single wrap boundary the plausible cause), so its failure is worth seeing rather
 * than tidying away. Details, and the register that now makes a carried-forward darwin
 * half visible, at `A11Y_BASELINE_TOTAL_NODES` and `DARWIN_CARRIED_FORWARD`.
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
 * A measurement that is identical on both platforms (a bare number — ~~93 of the
 * 103 triples~~ **162 of the 168 cells, re-measured 2026-08-27**) or one that is not
 * (an exact number for each).
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
      /*
       * ── EVIDENCE TRAIL NO LONGER EMPTY, 2026-08-25: +3 on `evidence`, +1/+2 on
       * ── `evidence-graph`, at every viewport. A KNOWN DEFECT'S COUNT, NOT A NEW ONE.
       *
       * WHY THE COUNTS MOVED, and it is a product FIX rather than a regression. An
       * independent verification measured that a record completed through
       * `POST /api/experiments` had an EMPTY evidence trail — 0 entries beside
       * `official.ok: true` and `ready_to_export` — because
       * `evidence_trail_from_draft` walked `fields`, `implicit` and `assets` and never
       * `block_evidence` or `descriptors_outputs`, which is exactly where the four
       * blocking answers are written. `GET /evidence` now composes a second reader.
       * Measured on the seeded scenarios: ~~**+3/+3/+5/+5/+5 entries**~~ — corrected
       * 2026-08-25, **ON THE WIRE IT IS +3/+3/+5/+5/+0**. The fifth seed is EXPORTED,
       * so `GET /evidence` serves it from the sidecar branch and the new draft reader
       * never runs for it: its served total is unchanged at 36. `+5` is that seed's
       * DRAFT-SIDE figure — what `confirmed_block_trail_from_draft(exp.draft)` returns
       * — and quoting it here read as a served delta, which is the figure this file is
       * about. Measured per seed (old walker / new draft-side / SERVED): 28/3/31,
       * 31/3/34, 31/5/36, 31/5/36, and 31/5/**36 unchanged**. This suite scans seed
       * `…SEED0000000002`, which gained **+3** — that half was right and is why the
       * node counts below still hold.
       *
       * SO THE SCREEN RENDERS THREE MORE EVIDENCE ROWS, AND EACH ONE INSTANTIATES THE
       * SAME PRE-EXISTING TOKEN DEFECT the block above already documents:
       * `--text-tertiary` #8a94a0 at 3.03:1 and `--text-quaternary` #9aa4af at 2.53:1
       * against WCAG AA's 4.50:1. 99 nodes were already failing on this surface; three
       * more rows make 102. No new rule fires, no new selector class appears, and no
       * page whose trail did not grow moved — which is what distinguishes "the same
       * defect, more instances" from a defect this change introduced.
       *
       * `evidence-graph` moves by +1 at desktop and +2 elsewhere rather than uniformly,
       * because the graph renders the new entries as nodes whose label wrapping differs
       * by width. The asymmetry is TRANSCRIBED, not smoothed: a uniform delta would
       * have been the tell that these were derived rather than read.
       *
       * THE QUEUED DESIGN-SYSTEM SLICE STILL OWNS THE FIX, and this raises what it will
       * recover. The note above already says the two tokens have 274 usages across 40
       * files and that THIS NUMBER IS EXPECTED TO DROP when they are raised; it will now
       * drop by more. Do not fix the palette inside a slice about evidence honesty,
       * where it would hide.
       *
       * LINUX ONLY. Transcribed line by line from the `browser accessibility and
       * responsive baseline` job of the CI run on this branch's head `60b5ebb`, which
       * failed with exactly these fourteen GREW messages and no others. ~~**The darwin
       * halves are carried forward UNMEASURED**~~ — **CORRECTED 2026-08-27: A DARWIN RUN
       * DISAGREED, exactly as the next sentence said it might.** The seven `evidence@*`
       * darwin halves moved by the SAME +3, so all seven collapse to scalars; the
       * failing node is `.trail-section-note`, added DOM rather than a wrap. The
       * struck claim is kept because the instruction that followed it is what was
       * carried out. This file's own R1b note says not to
       * assume the two platforms move together, and the extra-DOM-node argument that an
       * earlier note used to infer darwin would predict a move here, so a darwin run may
       * well disagree. If one does, transcribe its figure; do not derive it. The
       * `evidence-graph` keys are SCALARS, which assert darwin too — that is how this
       * file is forced to write a one-platform reading, because its guard rejects a pair
       * whose halves are equal, and the header already records the compromise.
       */
      /*
       * ── `--text-disabled` MISUSE FIXED, 2026-08-29: -22 on all seven `evidence`
       *    cells, BOTH columns ──────────────────────────────────────────────────
       *
       * `src/components/evidence.css`'s `.preview-line .ln` — the line-number gutter
       * of the read-only source preview — painted TEXT at 11.5px with
       * `--text-disabled` #c0c8d0, a token `styles/tokens.css:34` declares for
       * "disabled chevrons/icons". Measured 1.69:1 on white, 1.56:1 on `--screen-base`
       * and 1.49:1 on the `--cited-line-bg` highlight (the line a reader has been
       * pointed AT — worse than the figure this entry's note records, and nothing had
       * measured it). It is now `--text-slate` #5b6b7d: 5.46 / 5.05 / 4.81:1. The
       * TOKEN'S VALUE IS UNCHANGED — `tokens.css:3-5` forbids editing values there, so
       * only the token this one rule ASKS FOR moved, exactly as the `.section-tab` and
       * `.onramp-tagline` fixes did. A11Y-01 IS NOT CLOSED BY THIS.
       *
       * DARWIN MEASURED: local macOS run at this branch's HEAD reported
       * `IMPROVED evidence @ <pair> … color-contrast fell … (-22)` on all seven cells
       * and moved nothing else on that surface — 101 -> 79 at desktop/laptop/tablet,
       * 99 -> 77 at mobile/zoom-200/width-390/width-320.
       *
       * LINUX IS ARITHMETIC, AND THE ARGUMENT IS STATED SO A REVIEWER CAN REJECT IT
       * RATHER THAN TAKE IT ON TRUST. This file's R1b note forbids assuming both
       * platforms move together when a DOM NODE is removed, because that moves a wrap
       * boundary. Nothing is removed here: the same 22 `.ln` elements render, and only
       * their `color` changes. Their count is `preview.lines.length` — data, not
       * layout — so it is 22 under any font, and every one of the 22 went from 1.49-1.69:1
       * (failing by a factor of three) to >= 4.81:1, so there is no borderline case whose
       * verdict a font could flip. Hence -22 on linux as well: 101 -> 79 and 99 -> 77.
       * If CI disagrees, transcribe ITS numbers and correct the total; never loosen the
       * assertion.
       */
      'evidence@desktop-1280x800': 79,
      'evidence@laptop-1024x768': 79,
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
      'evidence@tablet-768x1024': 79,
      'evidence@mobile-375x812': 77,
      'evidence@zoom-200': 77,
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
      /*
       * ── `evidence-graph`, 2026-08-27: 24/29/29/28/28/28/28 -> 11/11/11/10/10/10/10 ──
       *
       * THIS IS A CONTRAST FIX, NOT A RE-MEASUREMENT, AND IT REPLACES THE NOTE
       * ABOVE RATHER THAN CONTRADICTING IT. That note said the 24 was systemic
       * `--text-tertiary`/`--text-quaternary` debt and that a design-system slice
       * would one day lower it. Three of the classes carrying that debt have now
       * been moved to `--text-muted` in `src/screens/graph/evidence-graph.css`, and
       * the numbers below are what an axe scan measures with that change in place.
       *
       * WHY THOSE THREE AND NOT THE PALETTE. This branch's evidence-graph work made
       * the surface read four more routes, so it draws more of the things those three
       * classes style — three more tree rows, one more detail term, up to three more
       * connection rows. CI (job 98470544956) reported the surface GREW by +5 at
       * desktop and +7 at every other viewport. An A/B on darwin, taken by passing
       * the four new sub-fetches as `undefined` and re-scanning, reproduced the
       * pre-branch figures EXACTLY (24/29/29/28/28) and then the CI figures EXACTLY
       * (29/36/36/35/35) — so the growth was located rather than guessed, and the
       * new styling that commit added contributed NONE of it: every declaration it
       * introduced is a stroke, a fill or a swatch, and not one failed. The carriers
       * were three long-standing classes, each already below the AA floor:
       *
       *   .evgraph-row-kind       #9aa4af on #ffffff   2.53:1  (2.39:1 selected row)
       *   .evgraph-detail-row dt  #78838f on #ffffff   3.86:1
       *   .evgraph-conn-kind      #9aa4af on #fbfcfd   2.46:1
       *
       * all now `--text-muted` #5b6570 — 5.93:1, 5.61:1 and 5.77:1 against those
       * same grounds. Raising the baseline instead would have recorded a real
       * accessibility regression as expected debt.
       *
       * THE DROP IS LARGER THAN THE GROWTH, deliberately: a class fix reaches every
       * instance, not only the new ones, so the pre-existing instances of those three
       * classes went away too (-18 at most viewports against a +7 regression). The
       * 10-11 that remain are the SAME systemic token debt the note above describes
       * and are still owned by that queued slice — `.evgraph-counts`,
       * `.evgraph-freshness`, `.evgraph-search-label`, `.evgraph-focus-label`, the
       * legend, `.evgraph-kind-count`, `#evgraph-tree-label`, `.evgraph-detail-kind`,
       * `.evgraph-detail-producer-term`, the panel `h4`, and `kbd.topbar-search-kbd`
       * (which is app chrome and not this screen's at all; it is the one node absent
       * at `mobile-375x812`, `zoom-200` and the two narrow widths, which is the whole
       * of the 11-vs-10 difference).
       *
       * HONEST LIMIT ON THE PLATFORM, and it is the same limit `settings-explorer`
       * records above. THESE SEVEN NUMBERS ARE DARWIN-MEASURED ONLY; this environment
       * cannot run the linux face. They stay SCALARS — which assert both columns —
       * because darwin and linux have agreed on this surface at every measurement so
       * far, in BOTH states: pre-branch 24/29/29/28/28/28/28 on both, and post-branch
       * 29/36/36/35/35/35/35 on both (the second pair is CI's own GREW report against
       * the darwin A/B above). That is agreement observed twice, not assumed — but it
       * is not a linux reading of THIS code. If the first linux run disagrees, split
       * the cell into `{ darwin: <this number>, linux: <measured> }` and do NOT change
       * the darwin half to match: it was measured separately, on 2026-08-27, by
       * `npx playwright test e2e/specs/a11y-axe.spec.ts e2e/specs/a11y-narrow.spec.ts`.
       */
      'evidence-graph@desktop-1280x800': 11,
      'evidence-graph@laptop-1024x768': 11,
      'evidence-graph@tablet-768x1024': 11,
      'evidence-graph@mobile-375x812': 10,
      'evidence-graph@zoom-200': 10,
      'evidence-graph@width-390': 10,
      'evidence-graph@width-320': 10,
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
      'governance@desktop-1280x800': 2,
      'governance@laptop-1024x768': 2,
      'governance@tablet-768x1024': 2,
      'governance@mobile-375x812': 1,
      'governance@zoom-200': 1,
      /* DISCARD SLICE, 2026-08-27: 10 -> 9. Linux measured by CI job 98470544956
         (IMPROVED, -1); darwin re-measured here the same day and agrees, so this
         stays a scalar — two measurements agreeing, not one assumed. Nothing on this
         screen was restyled by that branch; the surface is `record-complete` for a
         seeded record and the one node that stopped failing is not identified,
         because this suite records counts and CI's IMPROVED message names none.
         Lowered rather than left stale: a high number re-admits the defect. */
      'guided-completion@desktop-1280x800': 9,
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
      /*
       * ── THE REFLOW FIX MADE A PRE-EXISTING AA FAILURE MEASURABLE, 2026-08-25 ──
       *
       * `load` goes 3 -> 2 at the three wide viewports and 2 -> 1 at the two narrow
       * ones, and `load@width-390` below goes linux 2 -> 1. **Six cells, all DOWNWARD,
       * all transcribed from CI — none derived.**
       *
       * WHY A FIX LOWERED A COUNT BY REMOVING A DEFECT AND RAISING ONE FIRST. The
       * `.onramps` grid was `1fr 1fr` unconditionally (`runner.css` had no `@media` rule
       * at all), so at 320px the second on-ramp was a 15px sliver — and axe could not
       * resolve `.drop-target`'s background against a sliver, so it filed the node
       * `incomplete` rather than a violation. Reflowing to one column made it
       * MEASURABLE, which took `load@width-320/390` from 1 to 2: a real WCAG 1.4.3
       * failure that had been hiding behind a layout defect.
       *
       * THE COLOUR WAS FIXED RATHER THAN THE BASELINE RAISED, following the verbatim
       * precedent for `.onramp-tagline` in `runner.css` — *"Fixing the colour is the
       * right response; raising the baseline was not"*. `--text-tertiary` #78838f
       * (3.85:1 on `--surface` #ffffff) -> `--text-muted` #5b6570 (5.93:1, computed;
       * axe independently reported 3.85 for the old one). That restored width-320/390
       * to 1 AND removed the node from the five project counts, which had been carrying
       * it all along.
       *
       * So the sequence is: a layout defect concealed a contrast defect; fixing the
       * layout exposed it; fixing the contrast cleared it everywhere it had been
       * counted. **No baseline was raised at any point.**
       *
       * `load@width-390` COLLAPSES to a scalar: it was `{darwin: 1, linux: 2}`, linux
       * has come down to 1, and the well-formedness guard rejects a pair whose halves
       * are equal. `load@width-320` was already 1 and does not move — which is the
       * check that the two narrow cells behaved identically, as one cause predicts.
       *
       * TRANSCRIBED from the six IMPROVED messages of the `browser accessibility and
       * responsive baseline` job on this branch's head `d4ac207`, which failed with
       * exactly those six and one unrelated timeout. **An IMPROVED message is a FAILURE
       * in this suite on purpose**: a stale high number re-admits the defect it was
       * meant to catch.
       */
      'load@desktop-1280x800': 2,
      'load@laptop-1024x768': 2,
      'load@tablet-768x1024': 2,
      'load@mobile-375x812': 1,
      'load@zoom-200': 1,
      'memory@desktop-1280x800': 15,
      'memory@laptop-1024x768': 15,
      'memory@tablet-768x1024': 15,
      'memory@mobile-375x812': 14,
      'memory@zoom-200': 14,
      'memory-graph@desktop-1280x800': 28,
      'memory-graph@laptop-1024x768': 28,
      'memory-graph@tablet-768x1024': 20,
      'memory-graph@mobile-375x812': 13,
      'memory-graph@zoom-200': { darwin: 18, linux: 19 },
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
       * ~~THE DARWIN COLUMN HERE IS KNOWN-UNVERIFIED, not known-correct.~~
       * **CORRECTED 2026-08-27 — THE DARWIN RUN HAPPENED AND THIS PARAGRAPH'S
       * PREDICTION WAS RIGHT.** A DOM node added by an empty state has moved both
       * faces every time it has been
       * measured, so darwin has very probably moved too. It is left alone anyway:
       * a stale number that says where it came from can be corrected by the next
       * darwin run; a fresh number nobody measured cannot be caught at all.
       *
       * That next darwin run is `A11Y_BASELINE_TOTAL_NODES`' 2026-08-27 note. It
       * measured all seven `record-detail` cells at the LINUX figure — +7 each, the
       * Unmapped Notes empty state (+1) plus Asset References (+6) — so the seven
       * SPLITS this block created collapse back to SCALARS, and every darwin number
       * below is now a reading. The mechanism this paragraph reasoned from was
       * correct; the cells were stale for eleven days because nothing could see it.
       */
      'record-detail@desktop-1280x800': 46,
      'record-detail@laptop-1024x768': 46,
      /* linux 15 -> 14: the 320px clipping fix (min-width/overflow-wrap on
         `.fg-summary`, scoped to `.record-view-panel`) let the summary WRAP
         instead of running past its clip, and one contrast node stopped firing
         on the Linux face. An IMPROVEMENT, measured in CI, not a baseline
         loosening. darwin measured 16 on the same commit and is unchanged —
         the two faces wrap at different words, which is the entire reason this
         file has two columns. */
      'record-detail@tablet-768x1024': 46,
      'record-detail@mobile-375x812': 44,
      'record-detail@zoom-200': 44,
      'schema-reference@desktop-1280x800': 17,
      'schema-reference@laptop-1024x768': 17,
      'schema-reference@tablet-768x1024': 15,
      'schema-reference@mobile-375x812': 20,
      'schema-reference@zoom-200': 23,
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
      'settings-connect@desktop-1280x800': 16,
      'settings-connect@laptop-1024x768': 16,
      'settings-connect@tablet-768x1024': 17,
      'settings-connect@mobile-375x812': 16,
      'settings-connect@zoom-200': 16,
      'settings-connect@width-390': 15,
      'settings-connect@width-320': 16,
      'settings@desktop-1280x800': 11,
      'settings@laptop-1024x768': 11,
      'settings@tablet-768x1024': 11,
      'settings@mobile-375x812': 10,
      'settings@zoom-200': 10,
      'settings-about@desktop-1280x800': 10,
      'settings-about@laptop-1024x768': 10,
      'settings-about@tablet-768x1024': 10,
      // 14 -> 13 at 375 only, MEASURED in the tutorial-scope slice (2026-08-04).
      // A genuine improvement, lowered rather than left stale. The About tab
      // renders a workspace-derived line that is shorter now that the ordinary
      // workspace is empty, and at 375 the shorter string stops wrapping — so one
      // rendered text node fewer exists to fail. The other four projects are
      // unchanged, which is what a wrap-boundary effect looks like.
      'settings-about@mobile-375x812': 8,
      'settings-about@zoom-200': 9,
      'settings-api@desktop-1280x800': 13,
      'settings-api@laptop-1024x768': 13,
      'settings-api@tablet-768x1024': 13,
      'settings-api@mobile-375x812': 12,
      'settings-api@zoom-200': 12,
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
       * ~~THE DARWIN COLUMN IS THEREFORE KNOWN-UNVERIFIED HERE, not known-correct.~~
       * **CORRECTED 2026-08-27 — the darwin run happened; see
       * `A11Y_BASELINE_TOTAL_NODES`.** Two of these cells moved and the rest did not:
       * `@desktop-1280x800` measured 44 (it had been a scalar 43, so it is now a true
       * split) and `@laptop-1024x768` measured 45. Both darwin halves are readings now.
       * The CAUSE clause below is NOT endorsed by that run and must not be quoted as
       * explanation — the clipping story is refuted at
       * `'settings-explorer@tablet-768x1024'`, and this note is left standing only as
       * the record of what was reasoned. The
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
      /* ── DISCARD OPERATION, 2026-08-27. BOTH CELLS COLLAPSE TO SCALARS. ───────
         `PATCH`-then-`POST /api/experiments/{id}/discard` takes the served contract
         from 70 operations to 71, and the Endpoint Explorer lists every one of them.
         Linux 43 -> 44 at both, measured by CI job 98470544956 (run 33058311910).
         darwin was ALREADY 44 at desktop and 45 at laptop; re-measured here on
         2026-08-27 it reads 44 at both — so laptop is a genuine darwin -1 and desktop
         did not move at all. Both halves are now equal and the well-formedness guard
         rejects a pair whose halves are equal, so both become scalars. A scalar here
         is two independent measurements agreeing, not a linux figure asserted about
         darwin. The mechanism is the unexplained one recorded at
         `settings-explorer@tablet-768x1024` below — do not quote the clipping story
         as the cause. */
      /* ══ PERSISTENCE-TRUTHFULNESS BRANCH, 2026-08-28. ALL SEVEN `settings-explorer`
         CELLS MOVE, FOR ONE CAUSE, ESTABLISHED BY CONTROLLED EXPERIMENT. ═══════════

         desktop 44 -> { darwin 53, linux 54 }; laptop 44 -> { darwin 53, linux 54 };
         tablet 58 -> { darwin 68, linux 69 }; mobile-375x812 { 51, 50 } -> 66;
         width-320 51 -> { darwin 68, linux 67 }; width-390 52 -> 67; zoom-200 53 -> 64.
         Each cell repeats its own figures beside itself; this block is written once so
         the seven cannot drift apart.

         THE CAUSE, MEASURED RATHER THAN INFERRED: the `GET /api/about` OpenAPI
         `description=` string in `apps/api/isaac_api/routes.py` grew from 2 paragraphs
         to ~~6~~ **5** (corrected 2026-08-28: the figure was asserted, not counted;
         measured with `len([p for p in description.split('\n\n') if p.strip()])`, which
         reads 2 on `origin/main` and 5 here. The node counts either side were measured and
         are unaffected — it is only this sentence's arithmetic that was wrong, which is
         exactly the kind of unmeasured number this file exists to refuse).
         The Endpoint Explorer renders operation descriptions as
         `<p class="api-docs-description">` paragraphs
         (`apps/web/src/screens/settings/ApiDocs.tsx:769-802`, `splitPurpose`), so four
         extra paragraphs of prose become four extra low-contrast text nodes wherever
         that operation is rendered.

         PROOF — a controlled experiment, not a reading of the diff: with `routes.py`
         ALONE reverted to `origin/main` and every frontend change on this branch still
         applied, `settings-explorer@desktop-1280x800` PASSED at 44. So no frontend copy
         change on this branch contributed to any of the seven explorer cells.

         THE CONSEQUENCE WORTH CARRYING FORWARD: **a backend docstring is rendered
         product text and moves the a11y ratchet.** Nothing about `routes.py` looks like
         a frontend file, nothing in its diff mentions contrast, and a reviewer reading
         only `apps/web/` had no way to predict a baseline move of this size.

         PROVENANCE, both halves. linux: GitHub Actions CI run 33134705411, job
         98731972499, head `dad8715`, workflow job "browser accessibility and responsive
         baseline". darwin: measured locally on this macOS host on 2026-08-28 at the
         SAME commit `dad8715`, Playwright 1.62.1 + bundled Chromium, backend started
         exactly as CI does (uvicorn, no `PG*` env,
         `ISAAC_UI_WORKSPACE=/tmp/isaac-e2e-workspace`), command
         `npx playwright test e2e/specs/a11y-axe.spec.ts e2e/specs/a11y-narrow.spec.ts
         -g "Settings" --reporter=list` — 8 failed / 34 passed / 48 skipped, and the
         eight failures are the SAME eight cells that failed on linux. Every darwin half
         written in this edit is therefore MEASURED at this commit, not carried forward:
         none of these keys is in `DARWIN_CARRIED_FORWARD`, none was added to it, and
         `A11Y_BASELINE_DARWIN_UNVERIFIED_NODES` stays 0.

         THE TWO FACES DISAGREE IN BOTH DIRECTIONS, WHICH IS WHY EACH HALF IS WRITTEN
         FROM ITS OWN RUN AND NEVER COPIED ACROSS. linux is one node HIGHER at desktop,
         laptop and tablet; darwin is one node HIGHER at width-320; the two agree exactly
         at mobile-375x812, width-390 and zoom-200. So a pre-existing split
         (mobile-375x812) COLLAPSES while a pre-existing scalar (width-320) BECOMES a
         split, in the same edit and from the same cause. Do not "tidy" either: the
         well-formedness guard rejects a pair whose halves are equal, and a scalar here
         is two independent measurements agreeing rather than one asserted twice. */
      /*
       * ── INHERITED DRIFT, DARWIN TRANSCRIBED 2026-08-29 — NOT CAUSED BY THIS SLICE ──
       *
       * All seven `settings-explorer` cells were ALREADY failing on darwin when this
       * branch was cut, and that is measurable rather than asserted: the FIRST local
       * run on this branch — taken before a single line of CSS was touched, with only
       * `ApiDocs.tsx`'s landmark change applied — reported the identical `GREW … 55 to
       * 57` on this cell. The cause is the one commit `f4523c2` already warned about
       * in this file: the base commit `542d757` edited `apps/api/isaac_api/routes.py`
       * (the `GET /api/about` OpenAPI `description=`) and
       * `apps/web/src/lib/settingsContent.ts`, and the Endpoint Explorer renders
       * operation descriptions verbatim. A BACKEND DOCSTRING IS RENDERED PRODUCT TEXT
       * AND MOVES THE A11Y RATCHET — for the second time, and the second time it was
       * committed without the baseline.
       *
       * DARWIN MEASURED, local macOS run at this branch's HEAD, twice with identical
       * figures (the full four-spec sweep and an isolated
       * `-g "Endpoint Explorer"` re-run):
       *
       *   desktop-1280x800   55 -> 57   laptop-1024x768   55 -> 57
       *   tablet-768x1024    71 -> 72   mobile-375x812    71 -> 73
       *   zoom-200           67 -> 70   width-320         73 -> 76
       *   width-390          73 -> 74
       *
       * ~~THE LINUX COLUMN IS NOT TOUCHED, and it is now KNOWN TO BE STALE ... CI
       * will report five GREW messages naming its own figures — transcribe those.~~
       *
       * ~~TWO OF THE SEVEN COULD NOT BE WRITTEN THAT WAY ... those two cells now
       * ASSERT a linux value that no run has produced since `542d757`.~~
       *
       * ── BOTH PARAGRAPHS RESOLVED BY THE MERGE, 2026-08-29. They were TRUE of this
       * slice's own branch and are struck rather than deleted, because "a cell asserts
       * an unmeasured linux value" is exactly the kind of claim a future session acts
       * on, and it is no longer true here. ────────────────────────────────────────
       *
       * CI DID report those GREW messages — run 33275970428, on the sibling branch at
       * `6958459`, which took a deliberate red check for this purpose. The linux
       * column is transcribed from it, so every one of the seven now carries a
       * measured half on BOTH platforms, and no cell in this group asserts an
       * unmeasured value. The two cells this note flagged as unwritable-as-splits
       * (laptop, tablet) turned out to be genuine splits after all — linux measured 58
       * and 74, not the 57 and 72 the stale column held — so the type system's
       * limitation never had to be worked around.
       *
       * FOUR OTHERS COLLAPSED TO SCALARS for the strongest available reason: the two
       * faces were measured independently and agree. The darwin figures below are this
       * slice's own run and are UNCHANGED by the merge; two independent darwin runs on
       * two different bases produced them, which is why the +14 and the A11Y-06 -7 can
       * be summed without double-counting.
       */
      'settings-explorer@desktop-1280x800': 60,
      'settings-explorer@laptop-1024x768': { darwin: 59, linux: 60 },
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
      /* ASSISTANT SEAM OPERATION, 2026-08-20. linux 66 -> 65, COLLAPSING to a
         scalar: darwin was already 65 and linux has converged on it, so the pair no
         longer marks a measured difference and the well-formedness guard rejects one
         whose halves are equal. The scalar is two measurements agreeing.

         SAME TRIGGER as `@width-320`/`@width-390` in the block below: the Endpoint
         Explorer lists every operation the live contract exposes, and this branch adds
         `POST /api/assistant/ask`.

         THE MECHANISM IS INFERRED AND IS PROBABLY WRONG — recorded as a question
         rather than deleted, because the NUMBERS are measured and the EXPLANATION is
         not. An earlier revision of this note asserted: "`.api-browser-list` is a
         CLIPPED SCROLL CONTAINER — axe scans only what is visible, so a taller list
         pushes failing nodes OUT as often as it adds them." The container really is
         clipped (`max-height: 520px; overflow-y: auto`, 320px narrow — `screens.css`).
         But every rule here is `color-contrast`, and axe-core does not viewport-cull
         it: children of an `overflow-y: auto` box all have layout boxes, so a row
         scrolled out of view is still scanned. Under that model adding one operation
         row should ADD contrast violations, not remove one or two.

         So the direction is unexplained. What is asserted is only what was observed:
         these counts went DOWN on linux after this branch added one operation. Do NOT
         quote the clipping story as the cause, and do not treat the decrease as an
         accessibility improvement — no violation was fixed by this branch, and if the
         cause is that nodes stopped being scanned, the lower number is MASKING and the
         aggregate now under-counts real defects. Resolving it needs an axe run on the
         linux face with per-node output, which this environment cannot produce.
         Transcribed from CI job 96347581055's IMPROVED messages, never from a macOS
         run. An IMPROVED message is a FAILURE in this suite on purpose: a stale high
         number re-admits the defect it was meant to catch. */
      /* DISCARD OPERATION, 2026-08-27: 59 -> 58, and the direction is the same
         unexplained one this block already documents — one more operation, one FEWER
         failing node. Linux from CI job 98470544956 (IMPROVED, -1); darwin
         re-measured the same day and agrees, so it stays a scalar. Not an
         accessibility improvement: no violation was fixed. */
      /* /api/about DESCRIPTION, 2026-08-28: 58 -> { darwin 68, linux 69 }, a scalar
         BECOMING a split because the two faces measured one node apart. Cause,
         provenance and the controlled experiment that established it are in the block
         above `settings-explorer@desktop-1280x800`. Both halves measured at `dad8715`. */
      'settings-explorer@tablet-768x1024': { darwin: 73, linux: 74 },
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
      // ASSISTANT SEAM OPERATION, 2026-08-20: linux 58 -> 56, collapsing to a
      // scalar for the reason given at `settings-explorer@tablet-768x1024` above.
      /* DISCARD OPERATION, 2026-08-27: SPLITS to { darwin: 51, linux: 50 }, and this
         is the one cell in this family where the two faces went OPPOSITE ways. CI job
         98470544956 reported no change here, so linux stays 50; a darwin run the same
         day reads 51 (GREW +1). Same trigger as the four cells around it — the 71st
         operation — and the same unexplained direction problem, in both directions at
         once. The darwin half is measured, not carried forward. */
      /* /api/about DESCRIPTION, 2026-08-28: { darwin 51, linux 50 } -> 66, and the
         SPLIT COLLAPSES. The one-node difference recorded on 2026-08-27 has stopped
         existing: both faces now measure 66 at `dad8715`, so the pair no longer marks a
         measured difference and the well-formedness guard rejects equal halves. This is
         two measurements agreeing, not a linux figure asserted about darwin. Cause and
         provenance: the block above `settings-explorer@desktop-1280x800`. */
      'settings-explorer@mobile-375x812': { darwin: 74, linux: 75 },
      /* LINUX 61 -> 60, AN IMPROVEMENT, AND MEASURED ON BOTH PLATFORMS BECAUSE THIS
         FILE'S OWN R1b NOTE SAYS NOT TO ASSUME THEY MOVE TOGETHER. They did not: the
         same change moved linux DOWN one and darwin not at all.

         Cause, traced rather than guessed: the run-removal slice reworded the served
         409 response description for `POST .../runs/{run_id}/remove`, and the Endpoint
         Explorer renders every response description VERBATIM. One fewer low-contrast
         text node results. CI (linux, the authority) reported the fall from 61 to 60.

         DARWIN IS LEFT AT 59 DELIBERATELY, AND IT IS KNOWN TO BE STALE. A local macOS
         run measures 61 (+2) — and it measures 61 ON `main` TOO, with this slice's
         changes absent, so the darwin drift is PRE-EXISTING and is NOT caused by this
         slice. It went unnoticed because CI runs only linux, and darwin's authority is
         a local macOS run that evidently has not been taken for this cell since it
         drifted. Correcting it here would mean carrying an unrelated pre-existing
         regression inside a run-removal diff, where the next reader would attribute it
         to this slice; correcting it also needs the darwin TOTAL moved, which is the
         one artefact in this file that makes a debt increase visible. So it is recorded
         here as a measured finding for its own slice, not silently absorbed into this
         one. Do not "fix" this line by copying the linux number across — the two
         columns were measured separately and disagree in both value and direction. */
      // ASSISTANT SEAM OPERATION, 2026-08-20: linux 60 -> 59, collapsing to a
      // scalar for the reason given at `settings-explorer@tablet-768x1024` above.
      // The 200%-zoom projection reflows to a narrow width, so it moves with the
      // narrow cells rather than with the desktop ones.
      /* /api/about DESCRIPTION, 2026-08-28: 53 -> 64, still a scalar — both faces
         measured 64 at `dad8715`. Cause and provenance: the block above
         `settings-explorer@desktop-1280x800`. */
      'settings-explorer@zoom-200': 71,
      'settings-privacy@desktop-1280x800': 3,
      'settings-privacy@laptop-1024x768': 3,
      'settings-privacy@tablet-768x1024': 3,
      'settings-privacy@mobile-375x812': 2,
      'settings-privacy@zoom-200': 2,
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
      'statistics@desktop-1280x800': 2,
      'statistics@laptop-1024x768': 2,
      'statistics@tablet-768x1024': 2,
      'statistics@mobile-375x812': 1,
      'statistics@zoom-200': 1,
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
      'statistics-example@desktop-1280x800': 4,
      'statistics-example@laptop-1024x768': 4,
      'statistics-example@tablet-768x1024': 4,
      'statistics-example@mobile-375x812': 3,
      'statistics-example@zoom-200': 3,
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
      'statistics-mine@desktop-1280x800': 2,
      'statistics-mine@laptop-1024x768': 2,
      'statistics-mine@tablet-768x1024': 2,
      'statistics-mine@mobile-375x812': 1,
      'statistics-mine@zoom-200': 1,
      'validator@desktop-1280x800': 7,
      'validator@laptop-1024x768': 7,
      'validator@tablet-768x1024': 7,
      'validator@mobile-375x812': 6,
      'validator@zoom-200': { darwin: 4, linux: 5 },
    
      /* NARROW-WIDTH SWEEP, added 2026-08-08. The 320 and 390 narrow-width sweep (`specs/a11y-narrow.spec.ts`). These widths were
       never scanned by the five Playwright projects (1280/1024/768/375/640@DPR2), and 320 is
       the WCAG 1.4.10 reflow width where text wraps hardest and controls crowd. Every pair
       here is PRE-EXISTING debt becoming visible at a width nobody had scanned — compared
       per rule against the adjacent 375 baseline, all 49 findings sit within ±2. No new
       defect class was found.

         Every number MEASURED on BOTH platforms on the same commit and merged by
         `scripts/ingest_a11y_baseline.py`, which REFUSES any pair present in only one
         run rather than guessing the other. Nobody retyped a count. */
      'evidence@width-320': 77,
      'evidence@width-390': 77,
      'experiments-example@width-320': 9,
      'experiments-example@width-390': 9,
      'experiments@width-320': 2,
      'experiments@width-390': 2,
      'export-readiness-done@width-320': 8,
      'export-readiness-done@width-390': 9,
      'export-readiness@width-320': 1,
      'export-readiness@width-390': 1,
      'governance@width-320': 1,
      'governance@width-390': 1,
      'guided-completion@width-320': 7,
      'guided-completion@width-390': 7,
      'load@width-320': 1,
      // COLLAPSED to a scalar 2026-08-25: linux 2 -> 1 joined darwin's 1, and the
      // guard rejects a pair whose halves are equal. See the `load@desktop-1280x800`
      // note for the layout-concealing-a-contrast-defect sequence.
      'load@width-390': 1,
      'memory-graph@width-320': 11,
      'memory-graph@width-390': 13,
      'memory@width-320': 14,
      'memory@width-390': 14,
      /* UNMAPPED NOTES (PR #146), 2026-08-16: linux 13 -> 14 at BOTH narrow
         widths, the notes panel's empty state — same +1 as the five project
         cells. Both were SCALARS and both SPLIT rather than being raised onto an
         unmeasured darwin; the precedent is `settings-explorer@width-320` just
         below. Full reasoning, including what this figure does NOT measure, is in
         the block above `record-detail@desktop-1280x800`. */
      'record-detail@width-320': 44,
      /* SPLIT, and CI is what established it. I measured darwin 13 after the
         Graph tab landed and recorded it as a bare number, saying in the commit
         that linux was not yet measured and CI would adjudicate. It did: linux
         stayed at 12. So the tab's extra node is measurable on the darwin face
         at 390 and not on the linux one — the two wrap at different words, which
         is the whole reason this file has two columns. */
      'record-detail@width-390': 44,
      'schema-reference@width-320': 18,
      'schema-reference@width-390': 20,
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
         ~~darwin is carried forward UNMEASURED~~, and a bare number would assert a
         macOS reading nobody took.

         **CORRECTED 2026-08-27: darwin is now MEASURED at 9, not the 8 carried
         forward here** (see `A11Y_BASELINE_TOTAL_NODES`). The split survives and its
         gap WIDENS to 2. This is the one of the five residual darwin/linux
         differences with a mechanism the file header already explains: a long
         paragraph rewrapping at 320px is exactly the wrap-boundary case, and the two
         faces disagree by whole text nodes rather than by one. */
      'settings-about@width-320': { darwin: 9, linux: 7 },
      'settings-about@width-390': 9,
      'settings-api@width-320': 12,
      'settings-api@width-390': 12,
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
      //
      // ── ASSISTANT SEAM OPERATION, 2026-08-19. linux 320: 56 -> 57 (+1).
      // ── linux 390: 59 -> 57 (-2), so the scalar SPLITS.
      //
      // TRANSCRIBED FROM CI job 96326516774, read off its own GREW/IMPROVED
      // messages, and never from a macOS run — the file header's rule.
      //
      // ONE TRIGGER, TWO DIRECTIONS. The trigger is not in doubt: the Endpoint
      // Explorer renders every operation the live contract exposes, and this branch
      // adds one, `POST /api/assistant/ask`. The block above
      // `settings-explorer@desktop-1280x800` predicted the surface would move —
      // "ANY FUTURE SLICE THAT ADDS ROUTES WILL MOVE THIS SURFACE TOO".
      //
      // ~~"`.api-browser-list` is a CLIPPED SCROLL CONTAINER, and axe scans only
      // what is visible — so a taller list pushes rows OUT of the scanned rectangle
      // as often as it adds them. At 320px the new row's own failing node lands
      // inside the rectangle (+1); at 390px, where each row is shorter, adding it
      // displaces two failing nodes past the clip (-2)."~~ — STRUCK, and struck IN
      // PLACE because the numbers beside it are measured and only the explanation
      // is not. The mechanism was refuted on the very next run, one day later: see
      // the `settings-explorer@tablet-768x1024` block above, 2026-08-20. The
      // container really is clipped (`max-height: 520px; overflow-y: auto` at 320px
      // narrow, `screens.css`), but every rule counted here is `color-contrast`,
      // and axe-core does NOT viewport-cull it — children of an `overflow-y: auto`
      // box all have layout boxes, so a row scrolled out of view is still scanned.
      // Under that model adding one operation row cannot remove a violation at all,
      // in either direction.
      //
      // WHAT IS ASSERTED IS ONLY WHAT WAS OBSERVED: after this branch added one
      // operation, this cell went UP by one at 320px and DOWN by two at 390px. The
      // opposite signs are why it is neither a regression nor a fix, and that much
      // stands without the story. Do NOT quote the clipping story as the cause here
      // either, and do not read the -2 as an accessibility improvement — no
      // violation was fixed by this branch, and if the cause is that nodes stopped
      // being scanned then the lower number is MASKING and this aggregate
      // under-counts real defects. Resolving it needs an axe run on the linux face
      // with per-node output, which this environment cannot produce.
      //
      // The -2 is recorded rather than left, and the suite is why: an IMPROVED
      // message is a FAILURE here, deliberately, because a stale high number
      // re-admits the defect it was meant to catch. No colour changed, no token
      // was darkened, and #78838f / #9aa4af remain the documented shortfall.
      //
      // width-390 SPLITS because darwin's 59 is carried forward UNMEASURED. It has
      // very probably moved too — whatever the mechanism is, nothing about it is
      // platform-specific: the added row is in the contract, not in the renderer,
      // and the same operation moved four other linux cells. (~~"the clipping
      // mechanism is platform-independent"~~ — struck with the rest of the clipping
      // story above; the expectation survives it, the named cause does not.) A
      // fresh number nobody measured cannot be caught, while a stale one that says
      // where it came from can be corrected by the next darwin run.
      //
      // **THAT DARWIN RUN HAPPENED, 2026-08-27, AND IT MEASURED 52 — one node BELOW
      // the 53 carried forward, and one node ABOVE linux.** The split therefore
      // stands with a one-node gap. Two consequences worth stating rather than
      // leaving to be re-derived: the expectation above ("it has very probably moved
      // too") was RIGHT, and `@width-320` did NOT move — the local run confirmed the
      // scalar 51 on darwin, so the two narrow widths did not behave alike. That
      // asymmetry is unexplained for the same reason the -2 above is: no per-node
      // output exists on both faces.
      /* /api/about DESCRIPTION, 2026-08-28: 51 -> { darwin 68, linux 67 }, a scalar
         BECOMING a split — and **darwin is the HIGHER half here, the OPPOSITE direction
         from desktop, laptop and tablet, where linux is higher.** That is stated rather
         than smoothed over: the same one cause moved the two faces apart in one
         direction at three cells and in the other direction at this one, and no per-node
         output exists on both faces to explain why. Both halves are measured at
         `dad8715` — do not reconcile them by copying either across. Cause and
         provenance: the block above `settings-explorer@desktop-1280x800`.

         The asymmetry the note above records — that `@width-320` and `@width-390` "did
         not behave alike" — is unchanged: they move by different amounts (+17 vs +15 on
         darwin) and only this one splits. */
      'settings-explorer@width-320': 76,
      /* DISCARD OPERATION, 2026-08-27: linux 51 -> 52, COLLAPSING to a scalar.
         darwin was already 52 and a darwin run the same day still reads 52, so the
         pair no longer marks a measured difference and the guard rejects equal
         halves. `settings-explorer@width-320` did NOT move on either face, so the two
         narrow widths again did not behave alike — the asymmetry noted above is
         unchanged and still unexplained. */
      /* /api/about DESCRIPTION, 2026-08-28: 52 -> 67, still a scalar — both faces
         measured 67 at `dad8715`. Cause and provenance: the block above
         `settings-explorer@desktop-1280x800`. */
      // ── MERGE RESOLUTION CORRECTED BY CI, 2026-08-30 ─────────────────────────
      // The merge kept `main`'s `{76, 74}` and discarded this branch's `{76, 75}`,
      // which asserted that main's darwin +1 (a description crossing
      // `PURPOSE_DISCLOSURE_MIN_CHARS` in the strike sweep) and this branch's +1 (the
      // change feed's ADDED operation) were the same node. An independent review
      // flagged that the dedup was never stated and never re-measured. CI settled it:
      // run 33355811385 on the merged head reported `GREW settings-explorer @
      // width-390 on linux: color-contrast 74 -> 75`, and that ONE cell was its only
      // mismatch. So on linux the two effects are not additive — main's sweep moved
      // linux by zero, as its own CI run 33344481475 reported — and the correct linux
      // figure is 75. TRANSCRIBED from that run, not derived.
      //
      // AND THE DARWIN HALF IS MEASURED ON THE MERGED TREE TOO, so this pair is a
      // real split rather than one measured face beside one carried forward: a local
      // macOS run of `a11y-narrow.spec.ts -g "390px: Settings & API — Endpoint
      // Explorer"` at this head PASSES against 76. That is why the key is absent from
      // `DARWIN_CARRIED_FORWARD`.
      'settings-explorer@width-390': { darwin: 76, linux: 75 },
      'settings-privacy@width-320': 2,
      'settings-privacy@width-390': 2,
      /* SPLIT 2026-08-16, linux 15 -> 14. Same cause and same reasoning as
         `settings-about@width-320` above; ~~darwin carried forward unmeasured~~.

         **COLLAPSED BACK TO A SCALAR 2026-08-27: darwin MEASURED 8, i.e. linux's
         number.** The split was recording a difference that had stopped existing —
         darwin had been carried at 9 since the day it was split. A pair whose halves
         agree must be written as one; the well-formedness guard rejects it otherwise.
         Note this went the OPPOSITE way from `settings-about@width-320` two blocks up,
         which the same note pairs it with: same branch, same cause, and the two cells
         did not behave alike. */
      /* ── 2026-08-28: 8 -> 10, AND THIS CELL MOVED FOR A DIFFERENT AND UNRELATED
         REASON FROM THE SEVEN `settings-explorer` CELLS. ─────────────────────────

         It is NOT the `/api/about` description. It is the longer `sub=` sentence on the
         Settings Overview card in `apps/web/src/screens/SettingsPage.tsx`. PROOF, by the
         same revert-one-thing-at-a-time method: with ONLY that string reverted, this
         cell PASSED at 8; with `routes.py` reverted but that string present, it still
         FAILED at 10. The two causes are independent and neither explains the other.

         Stays a SCALAR: both faces measured 10 at `dad8715` (linux CI run 33134705411 /
         job 98731972499; darwin locally the same day — see the provenance paragraph in
         the block above `settings-explorer@desktop-1280x800`).

         WHICH TWO NODES, named rather than left as a delta: `.settings-figure:
         nth-child(2) > dt` ("Build Commit") and `.settings-commit-note`. Both are
         `--text-tertiary` `rgb(120,131,143)` — PRE-EXISTING A11Y-01 palette debt, NOT a
         new token, and the `foregrounds` guard did not fire on any of the eight cells
         this branch moves.

         AND THEY ARE NOT NEW NODES. A DOM probe at 320px found the two elements
         byte-identical between `main` and this branch in size, x-position, colour,
         `visibility` and `display`; **only their `y` moved, 881.8px -> 935.8px.** That
         is what changed whether axe reported them, which means this +2 is a coverage
         change and not a regression.

         OPEN ITEM, recorded honestly and deliberately NOT fixed here: `SWEEP_HEIGHT =
         900` (`e2e/specs/a11y-narrow.spec.ts:91`, its comment on :90) is commented
         "Tall enough that no surface is scanned mid-fold", and this surface extends to ~973px at 320px — so
         **that comment is not true for this surface.** Raising `SWEEP_HEIGHT` would move
         many unrelated cells and belongs in its own slice with its own CI round-trip; it
         is named here so the next reader does not re-derive it from a two-node delta. */
      'settings@width-320': 10,
      'settings@width-390': 10,
      'statistics-example@width-320': 3,
      'statistics-example@width-390': 3,
      'statistics-mine@width-320': 1,
      'statistics-mine@width-390': 1,
      'statistics@width-320': 1,
      'statistics@width-390': 1,
      'validator@width-320': 6,
      'validator@width-390': 6,
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
  /*
   * ── A11Y-04 and A11Y-05 DELETED, 2026-08-26 — those two defects are GONE ──
   *
   * ~~"A11Y-04, A11Y-05 and A11Y-06 DELETED — the defects are GONE"~~ —
   * **CORRECTED 2026-08-27 from CI run 33025558592, and kept struck rather than
   * rewritten because it is the exact failure this file's ratchet exists to
   * catch.** A11Y-06 was deleted on the strength of a `note` that turned out to
   * misdescribe its own two nodes. Only ONE of the two was a `role="search"`
   * landmark; the other was, and still is, a duplicate `region`. CI measured
   * **1** node still firing on all seven `settings-explorer` pairs, so the
   * deletion asserted a zero that was false. The residue is re-recorded as an
   * entry below — see `landmark-unique` — rather than left as a false zero that
   * would keep the sweep permanently red.
   *
   * Same rule as the deletions above: an absent entry expects ZERO nodes on
   * every pair, so if either of the two regresses it reads as `new` and fails
   * the sweep. Zeroing an entry would have tolerated it silently.
   *
   * Both remaining fixes are STRUCTURAL — an attribute added to an element — so
   * the post-fix count is 0 on BOTH platforms by construction, not by
   * measurement. That is why these two could be deleted from a machine that
   * cannot run the Linux face: font metrics can move a wrap boundary and
   * therefore a text-node count, but they cannot make a focusable element
   * unfocusable or an `<h1>` absent. Contrast the `color-contrast` entry
   * above, where every number is a per-platform measurement.
   *
   * The correction does NOT weaken the "structural fixes are platform-free"
   * argument, and it is worth saying which half of it failed: the reasoning
   * about PLATFORM was right (nothing here differs between darwin and linux).
   * What was wrong was the claim about WHICH NODES the entry had been counting
   * — a `note` was trusted where the `targetPattern` already contradicted it. It
   * read `^(\\.card|\\.topbar-search-region)$`: two different elements, while the
   * `note` described two instances of one kind.
   *
   *   * `scrollable-region-focusable` (FINDING A11Y-04, 6 nodes across 6 pairs:
   *     `evidence@desktop-1280x800`, `evidence@mobile-375x812`,
   *     `evidence@width-320`, `evidence@width-390`,
   *     `settings-api@mobile-375x812`, `settings-api@width-320`). The two
   *     offending elements — `div.preview-lines.scroll-x`
   *     (`src/components/SourcePreview.tsx`) and `pre.api-samples-code`
   *     (`src/screens/settings/ApiDocs.tsx`) — now carry `tabIndex={0}` with
   *     `role="group"` and an `aria-label`, following `.rc-tablewrap` in
   *     `src/components/RunCompare.tsx`. `role="group"` and not `region`: a
   *     region is a landmark, and an extra landmark here would re-create
   *     A11Y-06 while closing A11Y-04.
   *   * `page-has-heading-one` (FINDING A11Y-05, 5 nodes across 5 pairs plus
   *     `load@width-320` and `load@width-390`, 7 in total). `/load` renders
   *     `<h1 class="sr-only">Load Materials</h1>`
   *     (`src/screens/LoadMaterials.tsx`), the same pattern four other screens
   *     already use. `sr-only` text is not `isVisibleOnScreen`, so axe's
   *     `color-contrast` rule does not evaluate it and no `load@*` contrast
   *     count moves. `surfaces.ts` drops `expectH1: false` in the same change,
   *     which is what `specs/structure.spec.ts` instructs.
   *   * ~~`landmark-unique` (FINDING A11Y-06) — **HALF closed, and the entry is
   *     RESTORED at 1 below rather than deleted.**~~ **FULLY closed 2026-08-29;
   *     the entry is now DELETED and this half-closed text is struck rather than
   *     rewritten, because "7 nodes remain" is the kind of claim a future session
   *     acts on.** The first half of the A11Y-06 fix is unchanged and still
   *     stands: the name sits ON each `role="search"` landmark rather than on the
   *     button inside one of them (`aria-label="Site search"` on the TopBar region
   *     in `src/components/SearchDialog.tsx`, `aria-label="Endpoint search"` on
   *     the endpoint filter in `src/screens/settings/ApiDocs.tsx`). That closed
   *     the `.topbar-search-region` node. The OTHER node per pair was never a
   *     `role="search"` landmark at all: it was the `.card` blamed for TWO
   *     `region` landmarks sharing the accessible name "Endpoint Explorer". The
   *     inner one, `<section class="api-explorer">`, has had its
   *     `aria-labelledby` removed (`src/screens/settings/ApiDocs.tsx`), so it is
   *     no longer a landmark and its `<h3>` is untouched — see the deletion note
   *     below for the measurement.
   *
   * 20 nodes of recorded debt come off both totals below (27 deleted, 7
   * restored): darwin 2559 -> 2539, linux 2829 -> 2809 — before the
   * `color-contrast` transcription in the same change takes another 378 off
   * each. Final figures and their full arithmetic are at
   * `A11Y_BASELINE_TOTAL_NODES`. The 27-node subtraction is exact rather than
   * estimated because every one of the 20 deleted keys was a SCALAR, i.e.
   * asserted the identical number on both platforms.
   */
  /*
   * ── `landmark-unique` (FINDING A11Y-06, RESIDUE) — ENTRY DELETED 2026-08-29 ──
   *
   * DELETING AN ENTRY IS THIS FILE'S WAY OF SAYING THE DEFECT IS GONE, so the
   * evidence is recorded here rather than in a commit message.
   *
   * WHAT IT RECORDED. Seven cells, 1 node each, all `settings-explorer`,
   * `targetPattern: '^\.card$'`. The blamed element was the shared `SettingsCard`
   * wrapper, but the DEFECT was a pair: `/settings?tab=explorer` rendered TWO
   * `region` landmarks with the identical accessible name "Endpoint Explorer" —
   * that `.card` (named by its `<h2>`) and, inside it, `<section
   * class="api-explorer" aria-labelledby="settings-api-explorer-heading">` (named
   * by its `<h3>`). The entry's own note said the fix was one line and named it.
   *
   * THE FIX. `src/screens/settings/ApiDocs.tsx` drops the inner `<section>`'s
   * `aria-labelledby`. A `<section>` with no accessible name is not a landmark, so
   * one of the two disappears from the landmark list; the `<h3>` is untouched, so
   * the heading outline and the visible title are unchanged. The `.card` side was
   * deliberately NOT touched — it is shared chrome for all seven Settings tabs.
   *
   * MEASURED, darwin, local macOS run on 2026-08-29 at this branch's HEAD
   * (`npx playwright test e2e/specs/a11y-axe.spec.ts e2e/specs/a11y-narrow.spec.ts
   * e2e/specs/layout-responsive.spec.ts e2e/specs/layout-widths.spec.ts`): 7 failed
   * / 339 passed / 424 skipped, and every one of the seven failures was
   * `improved:landmark-unique` on a `settings-explorer` cell —
   * "rule \"landmark-unique\" is baselined at 1 node(s) here on darwin but did not
   * fire at all". No other rule moved anywhere in that run.
   *
   * THE LINUX COLUMN IS ASSERTED, NOT MEASURED, AND THE ARGUMENT IS THE ENTRY'S
   * OWN. Two landmarks sharing an accessible NAME is a DOM/ARIA fact with no text
   * measurement in it, so no font metric can change the count between platforms;
   * the deleted entry made exactly that argument for its scalars, and a darwin run
   * on 2026-08-27 checked it and found it right. Removing one of the two landmarks
   * removes it on every platform. If CI disagrees it will report `landmark-unique`
   * as NEW with its exact count — restore the entry from that output rather than
   * loosening anything.
   *
   * −7 nodes on both columns: darwin 2426 -> 2419, linux 2430 -> 2423. See
   * `A11Y_BASELINE_TOTAL_NODES`.
   */
];

/**
 * Every failing node this baseline tolerates, summed, PER PLATFORM. One number
 * a reviewer can watch: it is the size of the app's recorded automated-a11y
 * debt, and it can only go down without an explicit edit here.
 *
 * ~~The six-node gap is entirely the ten font-metric triples above (eight +1,
 * two −1). It is not extra debt on Linux; it is the same debt counted under a
 * wider font.~~
 *
 * **STRUCK 2026-08-29, and the reason matters more than the number.** The gap is now
 * **10, in DARWIN's favour** (2279 vs 2269), and it is no longer "the same debt counted
 * under a wider font". Five `settings-explorer` cells carry a darwin reading taken on
 * 2026-08-29 beside a linux reading taken on 2026-08-28, from a source state that has
 * since changed. **A gap in this constant no longer means only "font metrics"; it can
 * also mean "one column is stale."** Which of the two it is, for each of the eight
 * differing cells, is stated at the cell. Do not reconcile the columns by arithmetic.
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
  // ~~DARWIN IS DELIBERATELY UNCHANGED AND IS KNOWN-UNVERIFIED, not known-correct.~~
  // **CORRECTED 2026-08-27 — the next darwin run came and confirmed the suspicion
  // in the very next sentence.**
  // Six DOM nodes added by a new panel have moved both faces every time this has
  // been measured, so darwin has very probably moved too. It is left alone
  // anyway, per this file's standing rule: only the platform actually measured
  // may be edited. A stale number that says where it came from can be corrected
  // by the next darwin run; a fresh number nobody measured cannot be caught at
  // all. Two cells that were scalars (`settings-explorer@zoom-200` and
  // `@width-320`) therefore SPLIT rather than having their darwin half moved onto
  // a linux reading.
  //
  // The correction, precisely: the SEVEN `record-detail` cells here moved on darwin
  // by the same +6 (the Asset References panel), so their darwin halves are now
  // readings and the cells are scalars again. The two `settings-explorer` splits this
  // block created are a different story and did NOT all collapse — see
  // `A11Y_BASELINE_TOTAL_NODES`, where four `settings*` cells are the residual real
  // platform differences and the rest reproduced. Read this note as: the RULE was
  // right, the OUTCOME was a stale column, and nothing but a darwin run could tell
  // the two apart. That is what `DARWIN_CARRIED_FORWARD` now makes visible.
  //
  // The +44 was computed by the fast invariant suite in ~10ms rather than by a
  // second 26-minute browser run — which is the whole point of
  // `e2e/invariants/baseline-aggregate.invariant.test.ts`, doing its job on its
  // first real use.
  //
  // ── EVIDENCE TRAIL NO LONGER EMPTY, 2026-08-25: darwin 2551 -> 2564 (+13). ──
  //
  // **NOT A DARWIN MEASUREMENT. NOT ONE OF THE FOURTEEN CELLS WAS MEASURED ON DARWIN.**
  // The seven `evidence-graph@*` keys are SCALARS, and a scalar asserts BOTH columns —
  // so raising them from a linux reading necessarily moves the darwin total, whether or
  // not darwin agrees. That is the compromise this file's header already records: the
  // guard rejects a pair whose halves are equal, so a one-platform reading has no other
  // way to be written.
  //
  //   evidence-graph @ desktop      +1
  //   evidence-graph @ 6 viewports  +2 each  = +12
  //                                   net      = +13   (2551 -> 2564)
  //
  // The seven `evidence@*` keys are PAIRS, so their +21 lands on linux ALONE and darwin
  // is genuinely untouched there. **A FIRST DRAFT OF THIS CHANGE MOVED ONLY THE LINUX
  // TOTAL AND ASSERTED "darwin does not move"** — false, and for the scalar half of its
  // own change. `baseline-aggregate.invariant.test.ts` caught it (`darwin = 2551, entries
  // sum to 2564`), which is what that invariant is for: it sums the cells independently
  // and does not care what the note beside them claims.
  //
  // So if a darwin run disagrees with any of the seven, split that key and correct this
  // total; do not derive it.
  //
  // ── THE REFLOW/CONTRAST SEQUENCE, 2026-08-25: darwin 2564 -> 2559 (-5). ──
  //
  // Five of the six moved cells are SCALARS (`load@desktop`, `@laptop`, `@tablet`,
  // `@mobile-375`, `@zoom-200`), and a scalar asserts BOTH columns — so darwin comes
  // down by five as a matter of arithmetic, not because darwin was re-measured. The
  // sixth, `load@width-390`, was `{darwin: 1, linux: 2}`; only its linux half moved, so
  // it contributes nothing here.
  //
  // A darwin browser run DID independently measure five failures on `load` before the
  // colour fix and two after on the narrow sweep, which agrees in direction — but the
  // authoritative figures are CI's, and these five are transcribed from CI.
  //
  // ── A11Y-04 / A11Y-05 / A11Y-06 CLOSURE, 2026-08-26: darwin 2559 -> 2532 (-27). ──
  //
  // Three whole entries deleted, 20 keys, all SCALARS — so the identical -27
  // applies to both columns as arithmetic over the deleted cells, not as a guess
  // about a platform this environment cannot run. Per-entry breakdown at the
  // deletion comment inside `A11Y_BASELINE`:
  //
  //   scrollable-region-focusable   6 cells x 1 node   = -6
  //   page-has-heading-one          7 cells x 1 node   = -7
  //   landmark-unique               7 cells x 2 nodes  = -14
  //                                                net = -27
  //
  // These three are the only kind of a11y delta a laptop may write into the linux
  // column: each fix adds an ATTRIBUTE, and no font metric can make a focusable
  // element unfocusable, an `<h1>` absent, or a named landmark unnamed. The
  // `.section-tab` contrast fix that ships alongside them is the opposite case —
  // it moves `color-contrast` TEXT-NODE counts on roughly forty cells, none of
  // which is transcribed here because none of them has been measured. The
  // `browser-a11y` job will report those as `improved` with exact figures; that
  // is the transcription source, and this constant must be corrected again from
  // it in the same change as the cells.
  //
  // ── THE ROUND-TRIP THE NOTE ABOVE ASKED FOR, 2026-08-27: 2532 -> 2161. ──
  //
  // SOURCE: CI run 33025558592, job "browser accessibility and responsive
  // baseline", head 2da0c71 — the run that failed BY DESIGN so its output could
  // be transcribed. 119 failed / 864 passed. Extracted mechanically, not by eye:
  //
  //   gh run view 33025558592 --log-failed > run.log
  //   grep -oE 'IMPROVED [a-z0-9-]+ @ [a-z0-9-]+ on [a-z]+: rule "[a-z-]+" \
  //     fell from [0-9]+ to [0-9]+ node\(s\) \(-[0-9]+\)' run.log | sort -u
  //
  // 119 unique cells, and 119 is also the failed-test count, so no cell was
  // missed. 17 surfaces x exactly 7 scan projects each. Per-surface delta,
  // constant across all 7 projects of each surface — which is the signature of a
  // fixed number of `.section-tab` elements per surface rather than of anything
  // width- or font-dependent:
  //
  //   settings, settings-about, settings-api, settings-connect,
  //   settings-explorer, settings-privacy   6 surfaces x 7 x -6 = -252
  //   memory, memory-graph                  2 surfaces x 7 x -3 =  -42
  //   governance, schema-reference,
  //   validator                             3 surfaces x 7 x -2 =  -42
  //   evidence, evidence-graph, record-detail,
  //   statistics, statistics-example,
  //   statistics-mine                       6 surfaces x 7 x -1 =  -42
  //                                                          net = -378
  //
  //   -378 (color-contrast, above) +7 (landmark-unique residue, restored) = -371
  //   2532 - 371 = 2161.
  //
  // ── WHICH COLUMN IS MEASURED AND WHICH IS REASONED ──
  //
  // The 119 linux cell counts and the 7 landmark-unique cells are MEASURED: every
  // one is the "to" number CI printed, and the transcription asserted CI's "fell
  // from" against the number already in this file for all 119 before writing
  // anything — all 119 agreed, which is why the mapping from message to cell is
  // not a guess.
  //
  // ~~THE DARWIN COLUMN IS REASONED, NOT MEASURED, AND THIS IS THE FIRST TIME THIS
  // FILE HAS DONE THAT FOR `color-contrast`. Stated plainly so nobody later reads
  // 2161 as a reading.~~ **SUPERSEDED 2026-08-27 BY A DARWIN RUN — see
  // "THE DARWIN RUN THE NOTE ABOVE SAID WOULD HAVE TO HAPPEN" below.** The block is
  // kept rather than deleted because it is the record of what was reasoned, and
  // because the run proved most of the reasoning right and part of it wrong; a reader
  // has to be able to see which. Each of the 119 darwin cells was its previous darwin
  // value minus the SAME per-surface delta CI measured on linux. Why that was defensible
  // here and was NOT the "never fix one platform by copying the other's number"
  // that `docs/browser-accessibility-testing.md` forbids:
  //
  //   * what is copied is the DELTA, not the number. 20 of the 119 cells keep a
  //     genuine `{darwin, linux}` split with an unchanged gap between the columns;
  //     none collapses to equal, so no fake platform-specificity is created and
  //     none is erased.
  //   * the change is a TOKEN SWAP on one CSS class — `.section-tab` from
  //     `--text-tertiary` #78838f (3.86:1) to `--text-muted` #5b6570 (5.93:1).
  //     Font metrics move a WRAP BOUNDARY, which is why linux and darwin
  //     text-node counts differ at all. `.section-tab` is a single-line 12.5px
  //     tab label that does not wrap, its computed foreground and background are
  //     the same hexes on both platforms, and 12.5px/500 is below the 18.66px-bold
  //     large-text threshold on both — so the same nodes stop failing on both.
  //   * the number of `.section-tab` elements on a surface is set by that screen's
  //     tab structure, not by type rendering. That is what the "constant delta
  //     across all 7 projects of each surface" table above demonstrates
  //     empirically: a font- or width-sensitive count would not be constant across
  //     320px, 375px, 768px, 1024px, 1280px and 200% zoom.
  //
  // THE ALTERNATIVE — leaving darwin stale and letting a later CI run correct it —
  // IS NOT AVAILABLE, and was checked rather than assumed: `.github/workflows/`
  // contains no macOS runner at all (`grep -rn 'macos\|darwin' .github/workflows/`
  // returns nothing; every `runs-on:` in `ci.yml` is `ubuntu-latest`). No CI run
  // will ever judge the darwin column. It is corrected only when a developer runs
  // the suite on a Mac, and until someone does, these 119 darwin numbers are
  // reasoned. If such a run disagrees, IT wins for darwin and this note is the
  // record of why the reasoning was wrong.
  //
  // ── THE DARWIN RUN THE NOTE ABOVE SAID WOULD HAVE TO HAPPEN, 2026-08-27: ───
  // ── 2161 -> 2435 (+274). MEASURED. ─────────────────────────────────────────
  //
  // A developer ran the suite on a Mac. That is the event the paragraph above
  // named as the only thing that could ever judge this column, and it is now the
  // authority for it. Every number in the `darwin` half of this file is a reading
  // taken on this host; none is carried forward or reasoned. The statement that no
  // CI job produces this column is UNCHANGED and was re-checked in the same session
  // (`grep -rn 'macos\|darwin' .github/workflows/` still returns nothing).
  //
  // PROVENANCE, so the claim is checkable rather than asserted:
  //
  //   host      macOS (`process.platform === 'darwin'`), local
  //   commit    7668bf8 (`main`, clean tree at the time of both runs)
  //   command   npx playwright test e2e/specs/a11y-axe.spec.ts \
  //               e2e/specs/a11y-narrow.spec.ts --reporter=list
  //   runs      TWO consecutive, byte-identical: 19 failed / 184 skipped /
  //             152 passed, and the 19 GREW/IMPROVED lines diffed clean between
  //             them. That is the same two-identical-runs bar the file header
  //             sets for a regeneration.
  //
  // 149 OF THE 168 CELLS WERE CONFIRMED CORRECT AND ARE UNTOUCHED. So the reasoning
  // recorded above was right about most of what it reasoned, and this is not a
  // repudiation of it — 119 `.section-tab` darwin cells were derived by subtracting
  // a linux delta and every one of them reproduced. What did NOT hold is stated
  // below, because that is the part a future session needs.
  //
  // WHAT WENT WRONG, AND IT WAS NOT THE `.section-tab` REASONING: **15 OF THE 20
  // RECORDED "PLATFORM SPLITS" WERE NOT PLATFORM DIFFERENCES AT ALL.** They were a
  // STALE DARWIN COLUMN — a linux-only transcription that wrote a linux delta into
  // one half of a pair and left the other half at a number nothing had measured
  // since. All 15 COLLAPSE to scalars. The two big clusters, whose creating notes are
  // still in this file above each key:
  //
  //   record-detail  7 cells, +7 each = +1 (Unmapped Notes empty state, 2026-08-16)
  //                                     + 6 (Asset References, 2026-08-17)
  //   evidence       7 cells, +32 each = +29 (provenance chips, 2026-08-17)
  //                                     + 3 (evidence trail, 2026-08-25)
  //
  // plus a fifteenth on its own, `settings@width-320` (darwin carried at 9, measured
  // 8, i.e. linux's number) — worth naming separately because it is the one that a
  // count of the two clusters alone would miss, and because the number 14 is
  // therefore WRONG for this and is corrected here before it can be quoted.
  //
  // Each of those notes says some form of "darwin does NOT move" or
  // "KNOWN-UNVERIFIED rather than known-correct". DARWIN MOVED IDENTICALLY in the two
  // clusters, every time, by exactly the linux delta. The failing nodes name
  // themselves in the axe output —
  // `.prov-chip[data-review-state="supported"] > .chip-rev-supported.chip > span`
  // and `.trail-section-note` — i.e. added DOM, which is the one kind of change a
  // font metric cannot arbitrate.
  //
  // TWO OF THE 20 REPRODUCED EXACTLY AND ARE UNTOUCHED, which is the control that
  // stops this reading as "splits are always wrong": `memory-graph@zoom-200`
  // `{ darwin: 18, linux: 19 }` and `validator@zoom-200` `{ darwin: 4, linux: 5 }`
  // are now CONFIRMED genuine platform differences rather than assumed ones.
  //
  // THE REMAINING 3, PLUS ONE SCALAR THAT BECAME A SPLIT, STILL DIFFER BETWEEN THE
  // PLATFORMS — but every darwin half was wrong, so what was recorded was a real
  // difference of the WRONG SIZE, which is its own kind of stale:
  //
  //   settings-explorer@desktop-1280x800   43 (scalar) -> { darwin 44, linux 43 }
  //   settings-explorer@laptop-1024x768  { darwin 44, linux 43 } -> { 45, 43 }
  //   settings-explorer@width-390        { darwin 53, linux 51 } -> { 52, 51 }
  //   settings-about@width-320           { darwin  8, linux  7 } -> {  9,  7 }
  //
  // (`settings@width-320` `{ darwin 9, linux 8 } -> 8` is NOT in this list. It is the
  // fifteenth COLLAPSE, counted above. It is stated here too because the natural
  // reading of "19 corrections, 15 of them collapses" is that the four remaining ones
  // are these four — and they are.)
  //
  // THREE of those four are `settings-explorer`, and THE MECHANISM IS
  // NOT ESTABLISHED. The obvious story — `screens.css:2047` clips
  // `.api-browser-list` to `max-height: 520px` (320px under the narrow media query)
  // with `overflow-y: auto`, so a fixed-pixel clip over font-metric-dependent row
  // heights decides how many `.api-docs-summary-text` rows axe sees — IS ALREADY
  // REFUTED IN THIS FILE and must not be quoted. See the note above
  // `'settings-explorer@tablet-768x1024'` (2026-08-20) and the one above
  // `'settings-explorer@width-320'`: `color-contrast` is not viewport-culled by
  // axe-core, because children of an `overflow-y: auto` box all have layout boxes,
  // so a row scrolled out of the clip is still scanned. That earlier note ends "Do
  // NOT quote the clipping story as the cause", and this note obeys it rather than
  // re-introducing it one screen further down.
  //
  // So what is asserted here is only what was observed: on this host these
  // `settings-explorer` cells read one node away from the linux figures CI produced,
  // in both directions. `settings-explorer@desktop-1280x800` moves the way a genuine platform
  // difference moves — it was a SCALAR and is now a true split — which is a fact
  // about the reading, not an explanation of it. Resolving the direction needs an axe
  // run with per-node output on BOTH faces, which no single machine can produce.
  //
  // `settings-about@width-320` is the one of the four that IS explained: it is the
  // ordinary long-paragraph wrap case at the hardest width, the mechanism the file
  // header describes, and a +1 there is the signature of a single wrap boundary.
  //
  // ARITHMETIC, so this total can be checked against the cells rather than trusted:
  //
  //   evidence        3 cells 69 -> 101, 4 cells 67 -> 99          = +224
  //   record-detail   3 cells 14 ->  21, 4 cells 12 -> 19          =  +49
  //   settings@width-320                              9 ->  8      =   -1
  //   settings-explorer@desktop-1280x800             43 -> 44      =   +1
  //   settings-explorer@laptop-1024x768              44 -> 45      =   +1
  //   settings-explorer@width-390                    53 -> 52      =   -1
  //   settings-about@width-320                        8 ->  9      =   +1
  //                                                          net    = +274
  //
  //   2161 + 274 = 2435
  //
  // 2435 was DERIVED from the corrected map, not typed: it is the number
  // `sumA11yNodes(A11Y_BASELINE).darwin` reports, read out of the failure message
  // of `e2e/invariants/baseline-aggregate.invariant.test.ts` before this literal was
  // changed, and the run above is what makes each of its summands a reading.
  //
  // THE LINUX COLUMN IS UNTOUCHED BY THIS CHANGE. Not one linux value moved, and
  // `linux: 2431` below is the same number it was. A darwin run cannot speak for
  // linux any more than the reverse — which is exactly the rule that produced the
  // stale column this run just found.
  //
  // WHAT NOW STOPS THIS RECURRING: `DARWIN_CARRIED_FORWARD` below, and the
  // `A11Y_BASELINE_DARWIN_UNVERIFIED_NODES` literal beside it. A carried-forward
  // darwin half used to be indistinguishable from a measured one — which is the
  // whole reason 15 cells sat wrong for eleven days with every run agreeing (~~14~~;
  // re-counted by independent review 2026-08-27 — see `DARWIN_CARRIED_FORWARD` below).
  //
  // ── 2026-08-27, DISCARD + EVIDENCE-GRAPH BRANCH: darwin 2435 -> 2312 (-123). ──
  //
  // DERIVED, not typed: 2312 is the number `sumA11yNodes(A11Y_BASELINE).darwin`
  // reports, read out of the failure message of
  // `e2e/invariants/baseline-aggregate.invariant.test.ts` before this literal was
  // changed — the same method the note above describes. Every summand is a darwin
  // reading taken on this host on 2026-08-27 with
  // `npx playwright test e2e/specs/a11y-axe.spec.ts e2e/specs/a11y-narrow.spec.ts`.
  //
  //   evidence-graph        desktop/laptop/tablet  24,29,29 -> 11,11,11   = -49
  //   evidence-graph        mobile/zoom/390/320    28,28,28,28 -> 10 each = -72
  //   settings-explorer     laptop-1024x768        45 -> 44               =  -1
  //   settings-explorer     tablet-768x1024        59 -> 58               =  -1
  //   settings-explorer     mobile-375x812         50 -> 51               =  +1
  //   guided-completion     desktop-1280x800       10 ->  9               =  -1
  //                                                                  net   -123
  //
  //   2435 - 123 = 2312
  //
  // The 121 that come from `evidence-graph` are a CONTRAST FIX in
  // `src/screens/graph/evidence-graph.css`, not a re-measurement — see the long note
  // at those seven cells. The other four are the 71st operation and the client
  // Discard slot; none of them is this branch restyling those screens.
  // ── /api/about DESCRIPTION + SETTINGS `sub=`, 2026-08-28: darwin 2312 -> 2400. ──
  //
  // MEASURED, not derived. Local macOS run at `dad8715` (Playwright 1.62.1 + bundled
  // Chromium, backend started exactly as CI does): 8 failed / 34 passed / 48 skipped
  // under `-g "Settings"`, and the eight failures are the same eight cells linux
  // reported. Every figure below is that run's "to" number.
  //
  //   settings@width-320                    8 -> 10   =  +2   (SettingsPage `sub=`)
  //   settings-explorer@desktop-1280x800   44 -> 53   =  +9
  //   settings-explorer@laptop-1024x768    44 -> 53   =  +9
  //   settings-explorer@tablet-768x1024    58 -> 68   = +10
  //   settings-explorer@mobile-375x812     51 -> 66   = +15   (was the darwin half of
  //                                                            a split that COLLAPSES)
  //   settings-explorer@width-320          51 -> 68   = +17
  //   settings-explorer@width-390          52 -> 67   = +15
  //   settings-explorer@zoom-200           53 -> 64   = +11
  //                                                net  +88
  //
  //   2312 + 88 = 2400
  //
  // TWO causes, not one, and they are independent — see the block above
  // `settings-explorer@desktop-1280x800` (the `GET /api/about` OpenAPI description
  // growing 2 -> 6 paragraphs, which the Endpoint Explorer renders verbatim) and the
  // block at `settings@width-320` (a longer Overview-card `sub=` sentence). Each was
  // isolated by reverting it ALONE and re-running the cell.
  //
  // NOT a new colour and NOT a new token: every added node is `--text-tertiary`
  // #78838f, the documented A11Y-01 palette debt, and the `foregrounds` guard did not
  // fire on any of the eight. This is more of an existing shortfall becoming visible,
  // which is exactly why the number is corrected upward rather than the assertion
  // loosened. If CI disagrees with this literal, correct THE NUMBER from CI output.
  // ── PERSISTENCE-TRUTHFULNESS ROUNDS 3-4, 2026-08-29. ALL SEVEN `settings-explorer`
  //    `color-contrast` CELLS MOVED. darwin 2426 -> 2440 (+14). ───────────────────
  //
  // CAUSE, and it is the branch's own: `GET /api/about`'s served description gained
  // 207 characters (the sentence refusing the read-back remedy), and the Endpoint
  // Explorer RENDERS every served description. More text at the same
  // `--text-tertiary` #78838f is more nodes axe counts. No token changed, no new
  // foreground appeared, and the `foregrounds` guard did not fire on any of the
  // seven — this is the documented A11Y-01 debt becoming more visible, not a new
  // defect. Round 4 changed `settingsContent.ts` and `labels.ts`, which the
  // `settings-privacy` surface renders, not this one; the movement is round 3's.
  //
  //   cell                   darwin (local macOS, this host)   linux (CI 33275970428)
  //   desktop-1280x800              55 -> 57                        55 -> 57   SCALAR 57
  //   laptop-1024x768               55 -> 57                        57 -> 58   { 57, 58 }
  //   tablet-768x1024               71 -> 72                        72 -> 74   { 72, 74 }
  //   mobile-375x812                71 -> 73                        72 -> 73   SCALAR 73
  //   zoom-200                      67 -> 70                        68 -> 70   SCALAR 70
  //   width-320                     73 -> 76                        73 -> 76   SCALAR 76
  //   width-390                     73 -> 74                        72 -> 74   SCALAR 74
  //
  // BOTH FACES WERE MEASURED AT THE SAME COMMIT (`6958459`), neither reasoned and
  // neither copied across. darwin is this host's `npx playwright test
  // e2e/specs/a11y-axe.spec.ts e2e/specs/a11y-narrow.spec.ts`; linux is transcribed
  // from the GREW lines of CI run 33275970428, which took a deliberate red check for
  // exactly this purpose — the practice `b86ca83` records.
  //
  // THE SPLIT SET CHURNS AGAIN, IN BOTH DIRECTIONS, which is now the third commit to
  // observe it: FOUR cells collapse to scalars (mobile, zoom-200, width-320,
  // width-390 — the last two had been a scalar and a split respectively) and TWO stay
  // split (laptop, tablet). Do not read a split as a stable property of a cell.
  //
  // INDEPENDENT CROSS-CHECK, worth recording because it was free: the `A11Y-06`
  // branch measured darwin on its own base and reported the identical seven darwin
  // numbers. Its landmark change moves `landmark-unique` only, so the two runs
  // agreeing on `color-contrast` is a real confirmation rather than a coincidence.
  //
  // ── AND THEN THE SAME COMMIT'S OTHER TWO SLICES, MERGED HERE 2026-08-29 ────────
  //
  // The block below is the A11Y-06 + `--text-disabled` work, integrated on top of
  // the drift above. THE ARITHMETIC COMPOSES; the two slices touch DISJOINT cells:
  //
  //   2426  baseline before either slice
  //   +14   the seven `settings-explorer` color-contrast cells (drift, block above)
  //    -7   `landmark-unique` deleted: A11Y-06 closed, 7 cells x 1 -> 0
  //  -154   `evidence` color-contrast, 7 cells x -22 (`--text-disabled` misuse)
  //  ────
  //   2279
  //
  // THE DISJOINTNESS IS MEASURED, NOT ASSUMED, and it is what makes the sum legal:
  // this branch's darwin run at `6958459` (no A11Y-06 change present) and the
  // A11Y-06 branch's darwin run at `491d567` (change present) produced the SAME
  // seven `settings-explorer` color-contrast numbers. So removing the landmark
  // moves `landmark-unique` and nothing else, and the +14 and the -7 cannot be
  // double-counting the same nodes.
  // ── A11Y-06 RESIDUE + `--text-disabled` MISUSE + INHERITED DRIFT, 2026-08-29: ──
  // ── darwin 2426 -> 2279. ──────────────────────────────────────────────────
  //
  // FIRST, THE ARITHMETIC THE PREVIOUS ENTRY DID NOT LEAVE. The trail above ends at
  // "2312 + 88 = 2400", and the literal read 2426. The missing +26 is commit
  // `b86ca83`, which re-measured the seven `settings-explorer` cells on BOTH faces
  // (CI job 99018666402 for linux, this host for darwin) and moved the literal without
  // appending a note: 53->55, 53->55, 68->71, 66->71, 64->67, 68->73, 67->73 = +26,
  // and 2400 + 26 = 2426. Recorded here so the trail reconciles with the literal
  // rather than reading as a typo. (linux's half of the same commit was +28; see the
  // linux column.)
  //
  // NOW THIS CHANGE. Three independent movements, and only two of them are work done
  // here:
  //
  //   -7    `landmark-unique` ENTRY DELETED. A11Y-06's residue is closed —
  //         `<section class="api-explorer">` is no longer a second `region` named
  //         "Endpoint Explorer". Seven scalar cells of 1 node each. See the deletion
  //         note where the entry used to be, immediately above this constant.
  //
  //  -154   `evidence@*` color-contrast, -22 on each of seven cells. The
  //         `--text-disabled` #c0c8d0 line numbers of the source preview became
  //         `--text-slate` #5b6b7d (1.49-1.69:1 -> 4.81-5.46:1). MEASURED on darwin,
  //         and derived on linux from a DOM-count argument stated in full at those
  //         cells. ONE USAGE OF A11Y-01; A11Y-01 IS NOT CLOSED.
  //
  //   +14   `settings-explorer@*`, +2/+2/+1/+2/+3/+3/+1. NOT WORK DONE HERE, and the
  //         evidence that it is not is a run: the FIRST sweep on this branch, before
  //         any CSS was touched, already reported these. The base commit `542d757`
  //         edited `routes.py`'s `GET /api/about` description and
  //         `settingsContent.ts`, and the Endpoint Explorer renders operation
  //         descriptions verbatim — the same mechanism `f4523c2` recorded four days
  //         earlier. Transcribed rather than left red.
  //
  //   2426 - 7 - 154 + 14 = 2279
  //
  // 2279 is DERIVED, not typed: it is what `sumA11yNodes(A11Y_BASELINE).darwin`
  // reports, read out of the failure message of
  // `e2e/invariants/baseline-aggregate.invariant.test.ts` before this literal was
  // changed.
  //
  // THE COLUMNS NOW DIVERGE BY 10 IN DARWIN'S FAVOUR, and that is a KNOWN STALENESS
  // rather than a measured platform difference: the `settings-explorer` +14 is a
  // text-length change, so its linux half cannot be derived and was not written. CI
  // will report five GREW messages there; transcribe ITS numbers.
  // ── ENDPOINT EXPLORER, FOUR NEW OPERATIONS, 2026-08-30: darwin 2279 -> 2282. ──
  //
  // BOTH FACES MEASURED AT THE SAME COMMIT, which is the case this file wants and
  // rarely gets. The proposals slice takes the served contract 71 -> 75 operations,
  // and the Endpoint Explorer renders every description, so `settings-explorer@*`
  // moves. LINUX came from CI (run on this branch's head, 3 failed / 980 passed,
  // naming its own figures); DARWIN was measured locally on macOS at the same tree,
  // per project, immediately after.
  //
  //   desktop-1280x800   57 -> 59   darwin AND linux agree; stays a SCALAR
  //   laptop-1024x768    {57,58} -> {58,59}
  //   mobile-375x812     73 -> {73, 75}   darwin did NOT move; linux grew by 2
  //   zoom-200           70 -> {69, 70}   darwin IMPROVED by 1; linux did not move
  //   width-390          74 -> {75, 74}   darwin grew; linux did not
  //   tablet-768x1024    {72,74} unchanged — passed on both faces
  //   width-320          76 unchanged — passed on both faces
  //
  //   darwin: +2 +1 -1 +1 = +3   ->  2279 + 3 = 2282
  //
  // THREE OF THE FIVE MOVE IN ONLY ONE COLUMN, and one of them moves DOWNWARD on
  // darwin while linux holds — so no half of this edit could have been derived from
  // the other. Two cells that were scalars are now splits for that reason, and
  // `width-390` is the rare shape where DARWIN is the higher number.
  // 2282 -> 2283, 2026-08-30: the single MEASURED +1 at
  // `settings-explorer@width-390` (75 -> 76) from the strike sweep — see that
  // entry's note. The linux total below is deliberately unmoved: CI run
  // 33344481475 at the same head reported zero baseline mismatches.
  // ── RECORD-DETAIL DISCLOSURES OPENED, 2026-08-30: +175 on BOTH faces (+25 x 7). ──
  //
  // `disclosures.ts` now opens `section[data-draft-block]` before every scan, and
  // `FieldGroup` renders no body while collapsed — so axe had NEVER scanned a
  // `.field-row` at any viewport. Three tokens that became visible were this slice's
  // own and were FIXED rather than baselined (`.field-path`, `.ev-row`, `.ev-locator`,
  // all moved to `--text-muted` at 5.93:1), which took `record-detail @ desktop` from
  // 71 to 46. The residue recorded here is the app-wide `--text-tertiary` /
  // `--text-quaternary` palette debt CLAUDE.md §11 calls **A3** — `asset-reach`,
  // `asset-digest-note`, `needsyou-about`, `notes-capture-hint`, `vr-sub` and friends.
  // Pre-existing failures becoming MEASURABLE, not new defects, and settling A3 is a
  // palette decision this slice may not take alone.
  //
  // BOTH FACES ARE MEASURED AND THEY AGREE EXACTLY, so these stay SCALARS rather than
  // becoming splits. darwin: a full local macOS sweep of `a11y-axe` + `a11y-narrow`.
  // linux: CI run 33355971504 on this branch, which named the same seven cells and the
  // same seven numbers. Contrast is colour arithmetic, so agreement is what one would
  // expect — but it is recorded because it was measured on both faces, not assumed
  // from one.
  //
  //   desktop / laptop / tablet   21 -> 46   (+25 each)
  //   mobile / zoom-200 / 320 / 390   19 -> 44   (+25 each)
  //   7 x 25 = +175 on each platform: darwin 2283 -> 2458, linux 2287 -> 2462.
  // ── FINAL MERGE, 2026-08-31: ONE KEY EACH, RE-DERIVED. ──────────────────────
  // The conflict resolution kept both prose lineages, which is right, and that put a
  // SECOND `darwin:` and a SECOND `linux:` into this literal — the same duplicate-key
  // trap this file already records once, where JavaScript silently takes the later and
  // `tsc` says nothing. Only `baseline-aggregate.invariant.test.ts` sees it, as a stale
  // total. Both lineages above are kept as comments; exactly one key of each survives,
  // and its value is the measured sum of the merged entries — 2289 + 175 (the seven
  // record-detail cells at +25) on darwin, 2291 + 175 on linux.
  darwin: 2464,
  // ── MERGED: PROPOSALS + CHANGE FEED, 2026-08-30: darwin 2282 -> 2289. ──
  //
  // TWO SLICES MOVED THE SAME SEVEN CELLS FROM THE SAME BASE, and this file now
  // carries the compound. Proposals took the served contract 71 -> 75 operations and
  // the change feed took 71 -> 72; merged, it is 76, and the Endpoint Explorer renders
  // every description. Neither branch's numbers survive the merge unchanged, which is
  // why both faces are re-measured here rather than composed.
  //
  // DARWIN, measured locally on macOS at THIS merged tree, per project:
  //   desktop-1280x800   59 -> 60      laptop-1024x768   58 -> 59
  //   mobile-375x812     73 -> 74      tablet-768x1024   72 -> 73
  //   zoom-200           69 -> 71      width-390         75 -> 76
  //   width-320          76 unchanged (passed)
  //                                    net +7  ->  2282 + 7 = 2289
  //
  // THE LINUX COLUMN IN THESE SIX CELLS IS THIS COMMIT'S KNOWN-STALE HALF, and it is
  // named rather than left to be discovered: each linux value is the one that branch
  // measured BEFORE the merge, so it is a reading of a source state that has since
  // changed. CI is the authority and will name its own figures; they are transcribed
  // in the follow-up commit. `laptop-1024x768` reads `{59, 59}` for one commit, which
  // `auditEntryShapes` would normally refuse as an equal-halves pair — it is written
  // that way deliberately so the stale linux half stays VISIBLE rather than collapsing
  // into a scalar that would falsely claim the two faces agree.
  //
  // ── MERGE, 2026-08-30: A DUPLICATE `darwin:` KEY, AND THE SECOND ONE SILENTLY WON.
  // Both branches edited this object and the merge kept BOTH lines, so the literal
  // declared `darwin` twice and JavaScript took the later — 2283, `main`'s figure —
  // while the merged ENTRIES sum to 2289. The invariant suite caught it as a stale
  // total; the duplicate key itself would have been invisible to `tsc`. The two
  // lineages are kept as prose, which is the point of this block, but only ONE key
  // remains and it is the measured sum of the merged entries.
  //
  // `main`'s half of that arithmetic, retained: 2282 -> 2283, the single MEASURED +1
  // at `settings-explorer@width-390` (75 -> 76) from the strike sweep. This branch's
  // half is the six cells above. 2283 + 6 = 2289.

  // ── PROVENANCE CHIPS, 2026-08-17: linux 2601 -> 2804. darwin does NOT move. ──
  //
  // TRANSCRIBED from CI run 32064183439, read line by line from the GREW
  // messages. Seven cells, all on `evidence`, +29 EACH and uniformly:
  //
  //   desktop / laptop / tablet   70 -> 99
  //   mobile / zoom-200 / 390 / 320   68 -> 97
  //
  // +203 net. The uniformity across every viewport is the evidence that this is
  // markup VOLUME rather than a wrap artefact: the Evidence trail renders one
  // origin chip and one review chip per entry, and that surface carries many
  // entries.
  //
  // CHECKED BEFORE RECORDING, not assumed. The chips paint with
  // `--text-muted` (#5b6570, 5.93:1 — passes AA) and `--verified-text`
  // (#2f7d78, 4.2:1 — FAILS, and is already in this entry's `foregrounds` list
  // with 265 recorded instances elsewhere). No new foreground appeared: this
  // entry's `foregrounds` guard fails even at an unchanged node count, and CI
  // reported only GREW, never a foreground finding. So these 203 nodes are more
  // instances of a documented token shortfall, not a colour this feature chose.
  //
  // WORTH SAYING PLAINLY BECAUSE THE NUMBER IS LARGE: a two-chip pair per
  // evidence row is a real increase in small text on that screen, and 4.2:1 is
  // below AA. The design-system slice that raises `--verified-text` will lower
  // this and every other surface at once; these figures are EXPECTED TO FALL.
  // Recording them is not accepting them.
  //
  // ~~darwin is deliberately unchanged and KNOWN-UNVERIFIED rather than
  // known-correct~~ — **CORRECTED 2026-08-27: it was UNVERIFIED and it was WRONG.**
  // 29 added DOM nodes per viewport have almost certainly moved
  // it too. Left alone per this file's standing rule: only the platform actually
  // measured may be edited. All seven cells therefore SPLIT from scalars rather
  // than having their darwin half moved onto a linux reading.
  //
  // The darwin run of 2026-08-27 measured all seven `evidence` cells at the linux
  // figure — the same +29 — so every split this block created COLLAPSES back to a
  // scalar. The failing node names itself:
  // `.prov-chip[data-review-state="supported"] > .chip-rev-supported.chip > span`.
  // "almost certainly moved it too" was right, and the file had no way to act on it;
  // that is the gap `DARWIN_CARRIED_FORWARD` closes.

  // ── TRANSCRIPT CAPTURE, 2026-08-17: linux 2601 -> 2604. darwin unchanged. ──
  //
  // TRANSCRIBED from CI run 32062179811. TWO cells, both `settings-explorer`,
  // and NEITHER of them is the transcript UI:
  //
  //   settings-explorer@tablet-768x1024   64 -> 66  (+2)
  //   settings-explorer@width-390         58 -> 59  (+1, and the pair COLLAPSES
  //                                                  to the scalar 59)
  //
  // This is the SECOND-ORDER effect this file has now documented four times: the
  // Endpoint Explorer renders every operation the build exposes, this branch adds
  // three (`POST .../transcript`, `POST /api/transcription`,
  // `GET /api/providers/capabilities`), and `.api-browser-list` is a clipped
  // scroll container — so its cells move by different amounts and some do not
  // move at all. Nothing about the transcript panel renders on that screen.
  //
  // THE TRANSCRIPT SURFACES THEMSELVES CONTRIBUTE NOTHING HERE, and that is a
  // coverage statement rather than a clean bill of health. The panel is a CLOSED
  // disclosure until a reader presses "Start a capture", and the scan does not
  // press it — so the textarea, the run select, the candidate list, the four
  // decision controls and every voice control are UNSCANNED. Reading `+0` on
  // `record-detail` as "this feature adds no contrast debt" would be exactly
  // wrong; it adds none that a scan which never opens it can see. Measuring the
  // rest needs a scan that drives the disclosure, which is its own slice — the
  // same gap the `.vr-sub` and Unmapped Notes notes above record.
  //
  // `@width-390` collapses to a scalar because linux rose onto darwin's existing
  // 59. Both halves are measured; a pair whose numbers agree must be written as
  // one, and the well-formedness guard rejects an equal pair.

  // ── THE MERGE OF THE TWO ABOVE ─────────────────────────────────────────────
  //
  // BOTH notes are kept, because they describe DIFFERENT cells that both
  // survive the merge: the provenance chips moved seven `evidence` cells, the
  // transcript routes moved two `settings-explorer` cells. Keeping one and
  // discarding the other would leave half the current numbers unexplained.
  //
  // The TOTAL below is neither branch's figure and is not their arithmetic. It
  // is what the fast invariant suite computes from the merged entry map — the
  // one number in this file that is arithmetic rather than measurement, which
  // is exactly why it must be recomputed at a merge rather than chosen.
  //
  // 2807. Neither 2804 (provenance) nor 2604 (transcript), and the arithmetic
  // confirms both cell sets survived: 2601 + 203 + 3. Had either branch's figure
  // been carried across, the file would have been self-inconsistent and the fast
  // invariant would have said so in milliseconds — which is what it did.
  // 2807 -> 2806: the single MEASURED linux fall above,
  // `settings-explorer@zoom-200` color-contrast 61 -> 60, caused by the reworded 409
  // response description that the Endpoint Explorer renders verbatim. darwin is
  // UNCHANGED at 2551 and that is not arithmetic: the darwin cell did not move on this
  // change (a local run measures the same 61 on `main`), so there is nothing to add or
  // subtract on that side. Per this file's standing rule, the number is corrected from
  // the CI output and the assertion is not loosened.
  // ── ASSISTANT SEAM OPERATION, 2026-08-19: linux 2806 -> 2805. darwin does NOT
  // ── move, because both cells that changed are linux-only readings.
  //
  // ARITHMETIC, so a reviewer can check it without a run. Two cells, opposite
  // signs, one TRIGGER — the Endpoint Explorer gaining a row for
  // `POST /api/assistant/ask`. ~~"the Endpoint Explorer's clipped scroll container
  // gaining a row"~~ — the CAUSE clause is struck, in place: the clipping story was
  // refuted the next day (see `settings-explorer@tablet-768x1024` above, 2026-08-20
  // — axe-core does not viewport-cull `color-contrast`, so a row scrolled out of an
  // `overflow-y: auto` box is still scanned and a taller list cannot remove a
  // violation). The arithmetic below is transcribed measurement and is unaffected;
  // only the explanation of the -2 was ever inferred, and it is now recorded as
  // unexplained rather than as understood:
  //
  //   settings-explorer@width-320   56 -> 57   (+1)
  //   settings-explorer@width-390   59 -> 57   (-2)
  //                                       net  = -1   (2806 -> 2805)
  //
  // TRANSCRIBED from CI job 96326516774's GREW/IMPROVED messages. The darwin
  // column is untouched: `width-320` was already 57 there and ~~`width-390`'s 59 is
  // carried forward unmeasured~~, which the per-key note beside it states.
  // **CORRECTED 2026-08-27: `settings-explorer@width-390` is now MEASURED on darwin
  // at 52** (see `A11Y_BASELINE_TOTAL_NODES`). Both narrow cells have since moved
  // again on linux, so neither number above is current; this note is kept for its
  // transcription provenance, not as a reading of the file's present state.
  //
  // ── ASSISTANT SEAM OPERATION, SECOND PASS, 2026-08-20: linux 2805 -> 2801. ──
  //
  // The FIRST pass moved only the two narrow cells, because those were the two the
  // suite happened to report before it stopped. Three more `settings-explorer` cells
  // moved on the next run — one cause, four cells in total, and the lesson is that
  // an Endpoint Explorer change touches every projection that clips the list, not
  // only the ones a partial run named.
  //
  //   settings-explorer@mobile-375x812   58 -> 56   (-2)
  //   settings-explorer@tablet-768x1024  66 -> 65   (-1)
  //   settings-explorer@zoom-200         60 -> 59   (-1)
  //                                             net  = -4   (2805 -> 2801)
  //
  // TRANSCRIBED from CI job 96347581055's IMPROVED messages. All three COLLAPSE to
  // scalars — darwin already held the lower number in each — so darwin does not move.
  //
  // ── EVIDENCE TRAIL NO LONGER EMPTY, 2026-08-25: linux 2801 -> 2835 (+34). ──
  //
  // Fourteen cells, one cause: `GET /evidence` stopped returning an empty trail for a
  // record built through the product, so the Evidence screen renders three more rows and
  // the graph two more nodes, each instantiating the SAME pre-existing token contrast
  // defect. Per-cell reasoning at the `evidence@desktop-1280x800` note above.
  //
  //   evidence         @ 7 viewports   +3 each   = +21
  //   evidence-graph   @ desktop       +1
  //   evidence-graph   @ 6 viewports   +2 each   = +12
  //                                      net       = +34   (2801 -> 2835)
  //
  // TRANSCRIBED from the fourteen GREW messages of the CI run on head `60b5ebb`, and
  // the arithmetic is stated so the total can be checked against the cells rather than
  // trusted. ~~darwin does not move: not one of the fourteen was measured there.~~
  // **CORRECTED before merge:** the first half is true and the CONCLUSION was false. None
  // of the fourteen was measured on darwin — but the seven `evidence-graph` keys are
  // scalars, which assert darwin too, so the darwin total moves by +13 as a matter of
  // arithmetic rather than of evidence. See the darwin note for why that is unavoidable
  // in this file. The `evidence@*` pairs are the half that genuinely leaves darwin alone.
  //
  // ── THE REFLOW/CONTRAST SEQUENCE, 2026-08-25: linux 2835 -> 2829 (-6). ──
  //
  //   load @ desktop-1280x800   3 -> 2
  //   load @ laptop-1024x768    3 -> 2
  //   load @ tablet-768x1024    3 -> 2
  //   load @ mobile-375x812     2 -> 1
  //   load @ zoom-200           2 -> 1
  //   load @ width-390          2 -> 1   (the pair, collapsed to a scalar)
  //                               net     = -6   (2835 -> 2829)
  //
  // One cause: a `1fr 1fr` grid with no media query concealed an unresolvable
  // `.drop-target` background; reflowing exposed it and raising the token cleared it
  // everywhere it had been counted. Per-cell reasoning at `load@desktop-1280x800`.
  //
  // TRANSCRIBED from the six IMPROVED messages of the job on head `d4ac207`, and the
  // arithmetic is written out so the total can be checked against the cells rather
  // than trusted. `load@width-320` does NOT appear: it was already 1 and did not move,
  // which is the check that both narrow cells behaved as one cause predicts.
  //
  // ── A11Y-04 / A11Y-05 / A11Y-06 CLOSURE, 2026-08-26: linux 2829 -> 2802 (-27). ──
  //
  // Same 20 deleted scalar keys as the darwin note above; see it for the per-entry
  // arithmetic and for why a structural fix is the one case where this environment
  // may move the linux column without a CI run.
  //
  // ── STRIKE-SWEEP MEASUREMENT, 2026-08-30: settings-explorer@width-390 darwin
  // 75 -> 76 (+1). LINUX UNTOUCHED AT 74, DELIBERATELY. ──
  //
  // The campaign-sheet slice removed editorial `~~ ~~` retractions from six SERVED
  // OpenAPI descriptions (they render as literal tildes — `apps/web` has no markdown
  // renderer). Three of the six are operation descriptions, so the Endpoint Explorer's
  // rendered text changed: total 117,944 -> 118,276 characters. `splitPurpose`
  // collapses an operation's post-lead paragraphs only when their joined length
  // exceeds `PURPOSE_DISCLOSURE_MIN_CHARS`, so a length change can move a paragraph
  // between COLLAPSED (inside a closed `<details>`, not scanned) and INLINE (rendered,
  // scanned) — which is how a prose edit moves a `color-contrast` node count at all.
  //
  // MEASURED ON THIS MACHINE, not reasoned: a local darwin Playwright run at head
  // 202a319 reported `GREW settings-explorer @ width-390 on darwin: rule
  // "color-contrast" grew from 75 to 76 node(s) (+1)`. That is the same way the
  // 2026-08-27 darwin column was produced, and it is why this cell is NOT added to
  // `DARWIN_CARRIED_FORWARD`.
  //
  // THE LINUX HALF IS NOT TOUCHED, and the reason is measured rather than assumed:
  // CI run 33344481475 at this same head reported **zero** accessibility baseline
  // mismatches — its only failure was the 320px layout overflow fixed in the same
  // commit. So linux genuinely did not move, and writing 76 there to "match" would
  // have replaced a measured number with a guessed one, against this file's own
  // header rule. The pair is now a real platform split, not a stale column.

  // ── `.section-tab` TRANSCRIPTION, 2026-08-27: linux 2802 -> 2431 (-371). ──
  //
  // MEASURED, unlike its darwin counterpart. Every one of the 119 `color-contrast`
  // cells is the exact "to" figure printed by CI run 33025558592 (job "browser
  // accessibility and responsive baseline", head 2da0c71, 119 failed / 864
  // passed), and the +7 is the `landmark-unique` residue that same run reported as
  // `new ... fired on 1 node(s)` on seven pairs. The per-surface arithmetic, the
  // extraction command, and the reason the DARWIN column beside this one is
  // reasoned rather than measured are all at the `darwin` note above; they are
  // written there once rather than twice so the two cannot drift apart.
  //
  //   2802 - 378 (color-contrast) + 7 (landmark-unique restored) = 2431
  //
  // Nothing here is a guess: this is the column CI judges, and CI produced it.
  //
  // ── 2026-08-27, DISCARD + EVIDENCE-GRAPH BRANCH: linux 2431 -> 2311 (-120). ──
  //
  // MIXED PROVENANCE, and the split is stated rather than blurred:
  //
  //   * the five `settings-explorer`/`guided-completion` movements are TRANSCRIBED
  //     from CI job 98470544956 (run 33058311910) — desktop 43 -> 44, laptop
  //     43 -> 44, width-390 51 -> 52, tablet 59 -> 58, guided-completion desktop
  //     10 -> 9. Net +1. `settings-explorer@mobile-375x812` did NOT move on linux.
  //   * the seven `evidence-graph` cells are DARWIN-MEASURED and asserted about linux
  //     by the scalar form, for the reasons set out in full at those cells. Net -121.
  //
  //   2431 + 1 - 121 = 2311
  //
  // So this column is not wholly a linux reading this time, which is a departure from
  // the rule the note above states and is flagged rather than hidden. The departure is
  // confined to one surface, it is the only way this file can express a one-platform
  // measurement, and it is the same choice `settings-explorer@width-390` made in
  // 2026-08-10. If CI disagrees, split those cells and correct this literal from its
  // output — do not adjust the darwin halves to match.
  // ── /api/about DESCRIPTION + SETTINGS `sub=`, 2026-08-28: linux 2311 -> 2402. ──
  //
  // TRANSCRIBED from CI run 33134705411, job 98731972499, head `dad8715`, workflow job
  // "browser accessibility and responsive baseline" — this is the column CI judges and
  // CI produced it. The same eight cells failed here as on darwin.
  //
  //   settings@width-320                    8 -> 10   =  +2
  //   settings-explorer@desktop-1280x800   44 -> 54   = +10
  //   settings-explorer@laptop-1024x768    44 -> 54   = +10
  //   settings-explorer@tablet-768x1024    58 -> 69   = +11
  //   settings-explorer@mobile-375x812     50 -> 66   = +16   (was the linux half of a
  //                                                            split that COLLAPSES)
  //   settings-explorer@width-320          51 -> 67   = +16
  //   settings-explorer@width-390          52 -> 67   = +15
  //   settings-explorer@zoom-200           53 -> 64   = +11
  //                                                net  +91
  //
  //   2311 + 91 = 2402
  //
  // The two columns move by DIFFERENT amounts (+88 darwin, +91 linux) from the same two
  // causes, and the per-cell disagreement runs in BOTH directions — linux is one higher
  // at desktop, laptop and tablet, darwin is one higher at width-320, and they agree
  // exactly at the other four. Unlike the 2026-08-27 entry above, no cell in this edit
  // is a one-platform measurement asserted about the other: both faces were run at the
  // same commit. Do not reconcile the columns by copying a half across.
  // 2026-08-29 (see the darwin block above): linux 2430 -> 2443 (+13). The columns
  // move by DIFFERENT amounts (+14 darwin, +13 linux) because the two faces started
  // from different places on four of the seven cells; both totals are the sum of
  // their own column's measured cells, neither derived from the other.
  //
  // ── MERGED 2026-08-29, and the linux column composes DIFFERENTLY — read this ──
  //
  //   2430  baseline before either slice
  //   +13   the seven `settings-explorer` cells (linux moved by 13, darwin by 14)
  //    -7   `landmark-unique` deleted
  //  -154   `evidence` color-contrast, 7 x -22
  //  ────
  //   2282
  //
  // NOT 2269. The A11Y-06 branch's own linux figure was 2269 because it had left
  // the seven `settings-explorer` LINUX halves stale at their pre-drift values — it
  // said so, at the cell and at the total. This merge takes the linux halves that
  // CI measured at `6958459` (run 33275970428) instead, so the +13 is present here
  // and absent there. Do not reconcile the two numbers by preferring the smaller.
  //
  // ONE HALF OF THIS TOTAL IS STILL ARITHMETIC RATHER THAN A LINUX RUN, and it is
  // named rather than buried: the `evidence` -154 was DERIVED on the argument that
  // nothing leaves the DOM (`.ln` count is `preview.lines.length`, which is data,
  // not layout) and every node moved from ~1.5:1 to >=4.81:1, so no borderline case
  // exists that a font stack could flip. The argument is stated so it can be
  // rejected; CI is the arbiter and this commit expects to be corrected by it.
  // ── A11Y-06 RESIDUE + `--text-disabled` MISUSE, 2026-08-29: linux 2430 -> 2269. ──
  //
  // FIRST, THE MISSING ARITHMETIC, matching the darwin column's: the trail above ends
  // at "2311 + 91 = 2402" and the literal read 2430. The +28 is commit `b86ca83`,
  // which transcribed the seven `settings-explorer` cells from CI job 99018666402
  // without appending a note: 54->55, 54->57, 69->72, 66->72, 64->68, 67->73, 67->72
  // = +28, and 2402 + 28 = 2430.
  //
  // NOW THIS CHANGE. TWO movements, not three — the third one darwin took is
  // deliberately absent:
  //
  //   -7    `landmark-unique` entry deleted. ASSERTED for linux, not measured, and
  //         the argument is the deleted entry's own: two landmarks sharing an
  //         accessible NAME is a DOM/ARIA fact with no text measurement in it, so no
  //         font metric can move it. Removing one of the two removes it everywhere.
  //
  //  -154   `evidence@*`, -22 on each of seven cells. ARITHMETIC, and the reasoning is
  //         written out at those cells rather than assumed: nothing is removed from
  //         the DOM, the 22 `.ln` elements are `preview.lines.length` (data, not
  //         layout) and every one of them moved from failing by a factor of three to
  //         passing with headroom, so there is no borderline case a font could flip.
  //         This file's R1b rule forbids arithmetic when a DOM NODE moves; no node
  //         moves here.
  //
  //   +14   `settings-explorer@*` — DARWIN ONLY. Not applied here, deliberately. It is
  //         a TEXT-LENGTH change (a backend OpenAPI description and a Settings `sub=`
  //         sentence, both from the base commit `542d757`), which is exactly the
  //         wrap-dependent case where this file forbids deriving the other platform.
  //         ~~Five of those seven cells now carry a stale linux half beside a fresh
  //         darwin one and CI will name its own figures; two could not be written that
  //         way at all and had to collapse to scalars~~ — **SUPERSEDED BY THE MERGE,
  //         2026-08-30, and struck rather than edited because "five cells carry a stale
  //         linux half" is a claim a future session acts on.** The merge `c7b9db6` took
  //         the linux halves CI measured at `6958459` (run 33275970428), so NO
  //         `settings-explorer` cell carries a stale linux half at HEAD: five are
  //         SCALARS (desktop 57, mobile 73, zoom-200 70, width-320 76, width-390 74)
  //         and the two that this note called collapses are the only SPLITS —
  //         laptop `{57,58}`, tablet `{72,74}`, both CI-measured. The note below on
  //         the total was corrected at the time; this per-cell sentence was not, and
  //         that asymmetry is the defect worth remembering.
  //
  //   2430 - 7 - 154 = 2269
  //
  // ~~Both totals were recomputed by summing `platformCount` over every entry~~ —
  // TRUE ON THIS BRANCH, and superseded by the merge: 2269 summed a file whose seven
  // `settings-explorer` LINUX halves were still pre-drift. The merged file carries
  // the halves CI measured at `6958459` (run 33275970428), so the linux total is
  // 2430 + 13 - 7 - 154 = 2282. The recomputation instruction stands and is how the
  // number below was re-derived after the merge. If CI disagrees, correct THE NUMBER
  // from the CI output; never loosen the assertion.
  // 2026-08-30, the same measurement as the darwin block above: linux 2282 -> 2287.
  //
  //   desktop-1280x800   57 -> 59   (+2)
  //   laptop-1024x768    58 -> 59   (+1)
  //   mobile-375x812     73 -> 75   (+2)
  //                             net  +5   ->  2282 + 5 = 2287
  //
  // Every one of these three is a CI figure transcribed from the run's own GREW
  // lines, not a derivation. The columns move by DIFFERENT amounts (+3 darwin,
  // +5 linux) from one cause, which is why both were run.
  linux: 2466,
  // 2026-08-30, ROUND TWO — CI's linux figures for the merged tree: 2287 -> 2291.
  //
  //   desktop-1280x800   59 -> 60   (+1)      laptop-1024x768   59 -> 60   (+1)
  //   width-390          74 -> 75   (+1)      zoom-200          70 -> 71   (+1)
  //   mobile-375x812 and tablet-768x1024 did NOT appear in the run's GREW lines,
  //   so their linux halves are unmoved and their splits stand as written.
  //                                    net  +4   ->  2287 + 4 = 2291
  //
  // TWO CELLS COLLAPSED TO SCALARS IN THIS TRANSCRIPTION AND ONE BECAME A SPLIT, in
  // the same edit and in opposite directions — which is the churn this file's header
  // describes rather than a mistake. `desktop-1280x800` and `zoom-200` collapsed
  // because linux caught up to darwin exactly (60 and 71), and a scalar is the only
  // legal way to say the faces agree. `laptop-1024x768`, which had to be written as a
  // scalar 59 one commit ago because both halves then read 59, SPLITS again now that
  // linux measured 60. Every number here is a CI figure or a local macOS reading at
  // the merged tree; none is derived from the other column.
  // 2291 -> 2290 on the MERGE, re-derived as the sum of the merged entries rather
  // than adjusted: `main`'s strike sweep left its linux column deliberately unmoved
  // (CI reported zero mismatches at that head) while this branch had already moved
  // `settings-explorer@width-390`'s linux half, and the two edits overlap by one.
  // Every linux figure here remains CI's; none was measured on this machine.

};

/**
 * WHEN, AND ON WHAT, THE `darwin` COLUMN WAS LAST MEASURED.
 *
 * A provenance stamp rather than an assertion — nothing enforces it, and it is here
 * so a reader can tell how old the darwin column is without reading every note in
 * this file. See `A11Y_BASELINE_TOTAL_NODES`' 2026-08-27 block for the run itself.
 */
/*
 * AMENDED 2026-08-27, and the amendment is here rather than in the fields because the
 * fields describe ONE run and the column now carries readings from two.
 *
 * 155 of the 168 cells still carry the sweep below. THIRTEEN were re-measured later the
 * same day, on the discard/evidence-graph branch, by two consecutive runs of the same
 * command that agreed (0 failed / 184 skipped / 171 passed each time): the seven
 * `evidence-graph@*` cells, `settings-explorer@` desktop, laptop, tablet and
 * mobile-375x812, `settings-explorer@width-390`, and
 * `guided-completion@desktop-1280x800`. Each of the thirteen states its own provenance
 * at the cell. `commit` below is deliberately NOT moved to the branch head: it would
 * then be wrong for the 155, which is the larger and older claim, and this file's own
 * warning is that a freshness field speaks "only loosely".
 *
 * AMENDED AGAIN 2026-08-28, and the arithmetic above is restated rather than left to be
 * re-derived: the column now carries readings from THREE runs, not two. EIGHT cells were
 * re-measured on 2026-08-28 at commit `dad8715` — `settings@width-320` and all seven
 * `settings-explorer@*` — by the `-g "Settings"` run whose provenance is written out in
 * full in the block above `settings-explorer@desktop-1280x800`. Six of those eight were
 * among the thirteen re-measured on 2026-08-27, so the split is now: 147 cells carry the
 * sweep below, 13 carry the 2026-08-27 discard/evidence-graph runs of which 7 are
 * untouched since, and 8 carry the 2026-08-28 run. `commit` below is again deliberately
 * NOT moved, for the same reason: it would then be wrong for the 147, which is the
 * larger and older claim. Each cell states its own provenance beside itself.
 *
 * Note what the 2026-08-28 run did NOT do: it was scoped to `-g "Settings"` (8 failed /
 * 34 passed / 48 SKIPPED), so it is not a whole-file sweep and must not be read as
 * re-verifying any cell outside those eight.
 *
 * AMENDED AGAIN 2026-08-29, and the CELL TOTAL in the arithmetic above has changed as
 * well as the split, so re-derive rather than quoting: the file now holds 161 cells, not
 * 168 — the seven `landmark-unique` cells were DELETED when A11Y-06's residue closed
 * (see the deletion note above `A11Y_BASELINE_TOTAL_NODES`), and all seven were
 * `settings-explorer` scalars. FOURTEEN cells carry a 2026-08-29 reading: the seven
 * `evidence@*` (the `--text-disabled` misuse fix, -22 each) and the seven
 * `settings-explorer@*` (INHERITED drift from the base commit `542d757`, not caused by
 * that day's work — see the block above `settings-explorer@desktop-1280x800`). Both sets
 * come from the same whole-file sweep, `npx playwright test e2e/specs/a11y-axe.spec.ts
 * e2e/specs/a11y-narrow.spec.ts e2e/specs/layout-responsive.spec.ts
 * e2e/specs/layout-widths.spec.ts --reporter=list`, and the `settings-explorer` figures
 * additionally reproduced in an isolated `-g "Endpoint Explorer"` re-run.
 *
 * THE SPLIT, DERIVED RATHER THAN QUOTED, because the 2026-08-28 version of this
 * paragraph did not add up (it wrote "147 + 13 + 8 = 168" while also saying 6 of the 13
 * had been superseded by the 8, which cannot both be true):
 *
 *   161  cells in the file
 *   -14  re-measured 2026-08-29 (evidence x7, settings-explorer x7)
 *    -1  still carrying the 2026-08-28 `-g "Settings"` run (`settings@width-320`;
 *        its other 7 cells were settings-explorer and are superseded above)
 *    -8  still carrying the 2026-08-27 discard/evidence-graph runs (evidence-graph x7
 *        + `guided-completion@desktop-1280x800`; the 5 settings-explorer cells among
 *        that day's 13 are superseded above)
 *   ---
 *   138  carry the sweep recorded in the fields below
 *
 * `commit` below is AGAIN deliberately not moved, for the reason it was not moved twice
 * before: it would then be wrong for the 138, which is the larger and older claim.
 */
export const DARWIN_MEASUREMENT = {
  /** Local date of the run whose readings the `darwin` column carries. */
  date: '2026-08-27',
  /** `main` at the time of the run; the tree was clean. */
  commit: '7668bf8',
  /** Two consecutive runs, byte-identical: 19 failed / 184 skipped / 152 passed. */
  runs: 2,
  command:
    'npx playwright test e2e/specs/a11y-axe.spec.ts e2e/specs/a11y-narrow.spec.ts --reporter=list',
} as const;

/**
 * THE CELLS WHOSE `darwin` HALF IS CARRIED FORWARD OR REASONED RATHER THAN MEASURED.
 *
 * ── Why this list exists, stated as the defect it closes ────────────────────
 *
 * Until 2026-08-27 a carried-forward darwin half was INDISTINGUISHABLE from a
 * measured one. Both are just a number in a `{ darwin, linux }` pair. The reason it
 * mattered is not hypothetical: 15 of the 20 recorded "platform splits" in this file
 * (~~14~~ — corrected by independent review 2026-08-27, which found `settings@width-320`
 * had collapsed too; 19 of the 168 cells moved in all, the other four being residual
 * real differences. The same correction is carried in `baseline-aggregate.ts` and in
 * `invariants/baseline-aggregate.invariant.test.ts`, and it is kept struck rather than
 * overwritten because an undercount of stale cells reads as reassurance)
 * were not platform differences at all — they were a stale darwin column, created by
 * four separate linux-only transcriptions that each wrote a linux delta into one half
 * of a pair and left the other half at a number nothing had measured since. Every one
 * of those four notes SAID it was leaving darwin unverified, and every one of them was
 * right to; the file simply had nowhere to put that fact where a later reader, or a
 * test, could act on it. It sat in prose for eleven days, and only a local run found it.
 *
 * ── The contract ───────────────────────────────────────────────────────────
 *
 * List a `surfaceId@projectId` key here whenever you write or keep a `darwin` value
 * that no darwin run produced — which is EVERY linux-only CI transcription that
 * touches a cell, including one that merely leaves a scalar standing while raising its
 * linux twin into a split. Remove the key when a darwin run measures the cell.
 * `A11Y_BASELINE_DARWIN_UNVERIFIED_NODES` below must move in the same edit, and
 * `e2e/invariants/baseline-aggregate.invariant.test.ts` fails if it does not — the same
 * literal-plus-check shape `A11Y_BASELINE_TOTAL_NODES` already uses, and for the same
 * reason: a derived number would absorb an increase silently, and an increase here is
 * exactly the thing a reviewer needs to see in a diff.
 *
 * ── It is EMPTY, and that is a measurement, not an aspiration ──────────────
 *
 * The 2026-08-27 run scanned all 168 cells on darwin: 149 reproduced and 19 were
 * corrected from its output. Nothing in this file's `darwin` column is now carried
 * forward. It will stop being empty the first time CI transcribes a linux figure, and
 * that is the point — the list is a debt register, not a badge.
 *
 * STILL EMPTY AFTER 2026-08-28, and that is a measurement too rather than an oversight.
 * The eight cells that moved on the persistence-truthfulness branch had their linux
 * halves transcribed from CI run 33134705411 — exactly the situation the contract above
 * says to list — but a local darwin run was taken at the SAME commit `dad8715` on the
 * same day, so every darwin half written in that edit was produced by a darwin run. No
 * key was added here and none was removed (none of the eight was listed);
 * `A11Y_BASELINE_DARWIN_UNVERIFIED_NODES` stays 0.
 *
 * ── What it deliberately does NOT do ───────────────────────────────────────
 *
 * It does not mark the LINUX column, which has its own and opposite problem (this
 * environment cannot measure it at all, and CI is its authority). It does not make an
 * unverified cell fail — an unverified number is still the best number available and
 * removing it would lose the ratchet. And it is not a freshness check: a cell measured
 * on darwin in March and edited by a product change in April is stale without being
 * listed here. Only `DARWIN_MEASUREMENT.commit` speaks to that, and only loosely.
 */
export const DARWIN_CARRIED_FORWARD: readonly BaselineKey[] = [];

/**
 * How many `darwin` nodes of `A11Y_BASELINE_TOTAL_NODES.darwin` sit in cells listed in
 * `DARWIN_CARRIED_FORWARD` — i.e. how much of the declared darwin debt no darwin run
 * has ever seen.
 *
 * Hand-written and checked, exactly like `A11Y_BASELINE_TOTAL_NODES`, so that growth
 * is visible in a diff rather than absorbed by a derivation.
 */
export const A11Y_BASELINE_DARWIN_UNVERIFIED_NODES = 0;

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
