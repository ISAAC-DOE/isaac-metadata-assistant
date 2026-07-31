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
 * nodes exist and which of them axe measures. Ten of the 149 recorded triples
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
 * Two consecutive full runs produced identical counts for all 149 triples on
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
 * A measurement that is identical on both platforms (a bare number — 139 of the
 * 149 triples) or one that is not (an exact number for each).
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
      'at small sizes: --verified-text/--stats-cat-2 #2f7d78 on the #e6f1f0 chip tint ' +
      '(4.2:1, 265 occurrences) and --src-derivation/--stats-cat-5 #7a6bb0 (4.25:1, 15). ' +
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
      '#2f7d78', // --verified-text / --stats-cat-2
      '#7a6bb0', // --src-derivation / --stats-cat-5
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
      'evidence@desktop-1280x800': 71,
      'evidence@laptop-1024x768': 71,
      'evidence@tablet-768x1024': 70,
      'evidence@mobile-375x812': 68,
      'evidence@zoom-200': 69,
      'experiments@desktop-1280x800': 10,
      'experiments@laptop-1024x768': 10,
      'experiments@tablet-768x1024': 10,
      'experiments@mobile-375x812': 9,
      'experiments@zoom-200': 9,
      'export-readiness@desktop-1280x800': 7,
      'export-readiness@laptop-1024x768': 6,
      'export-readiness@tablet-768x1024': 6,
      'export-readiness@mobile-375x812': 1,
      'export-readiness@zoom-200': 4,
      'export-readiness-done@desktop-1280x800': 13,
      'export-readiness-done@laptop-1024x768': 12,
      // The two pairs where LINUX HAS FEWER nodes: the wider face pushes two
      // fragments onto one line, so axe sees one text node instead of two.
      'export-readiness-done@tablet-768x1024': { darwin: 12, linux: 11 },
      'export-readiness-done@mobile-375x812': 8,
      'export-readiness-done@zoom-200': 10,
      'governance@desktop-1280x800': 4,
      'governance@laptop-1024x768': 4,
      'governance@tablet-768x1024': 4,
      'governance@mobile-375x812': 3,
      'governance@zoom-200': 3,
      'guided-completion@desktop-1280x800': 12,
      'guided-completion@laptop-1024x768': 11,
      'guided-completion@tablet-768x1024': 11,
      // Linux wraps the guided-completion prompt one word earlier.
      'guided-completion@mobile-375x812': { darwin: 7, linux: 8 },
      'guided-completion@zoom-200': 9,
      'load@desktop-1280x800': 5,
      'load@laptop-1024x768': 5,
      'load@tablet-768x1024': 5,
      'load@mobile-375x812': 3,
      'load@zoom-200': 4,
      'memory@desktop-1280x800': 18,
      'memory@laptop-1024x768': 18,
      'memory@tablet-768x1024': 18,
      'memory@mobile-375x812': 17,
      'memory@zoom-200': 17,
      'memory-graph@desktop-1280x800': 42,
      'memory-graph@laptop-1024x768': 42,
      'memory-graph@tablet-768x1024': 34,
      'memory-graph@mobile-375x812': 27,
      'memory-graph@zoom-200': { darwin: 32, linux: 33 },
      'record-detail@desktop-1280x800': 16,
      'record-detail@laptop-1024x768': 16,
      'record-detail@tablet-768x1024': { darwin: 16, linux: 15 },
      'record-detail@mobile-375x812': { darwin: 10, linux: 11 },
      'record-detail@zoom-200': 13,
      'schema-reference@desktop-1280x800': 19,
      'schema-reference@laptop-1024x768': 19,
      'schema-reference@tablet-768x1024': 17,
      'schema-reference@mobile-375x812': 22,
      'schema-reference@zoom-200': 25,
      'settings@desktop-1280x800': 15,
      'settings@laptop-1024x768': 15,
      'settings@tablet-768x1024': 15,
      'settings@mobile-375x812': 14,
      'settings@zoom-200': { darwin: 13, linux: 14 },
      'settings-about@desktop-1280x800': 14,
      'settings-about@laptop-1024x768': 14,
      'settings-about@tablet-768x1024': 14,
      'settings-about@mobile-375x812': 12,
      'settings-about@zoom-200': { darwin: 12, linux: 13 },
      'settings-api@desktop-1280x800': 17,
      'settings-api@laptop-1024x768': 17,
      'settings-api@tablet-768x1024': 17,
      'settings-api@mobile-375x812': 16,
      'settings-api@zoom-200': 16,
      'settings-explorer@desktop-1280x800': 46,
      'settings-explorer@laptop-1024x768': 46,
      'settings-explorer@tablet-768x1024': 62,
      'settings-explorer@mobile-375x812': 55,
      'settings-explorer@zoom-200': { darwin: 55, linux: 56 },
      'settings-privacy@desktop-1280x800': 7,
      'settings-privacy@laptop-1024x768': 7,
      'settings-privacy@tablet-768x1024': 7,
      'settings-privacy@mobile-375x812': 6,
      'settings-privacy@zoom-200': { darwin: 5, linux: 6 },
      'statistics@desktop-1280x800': 10,
      'statistics@laptop-1024x768': 10,
      'statistics@tablet-768x1024': 10,
      'statistics@mobile-375x812': 9,
      'statistics@zoom-200': 9,
      'validator@desktop-1280x800': 9,
      'validator@laptop-1024x768': 9,
      'validator@tablet-768x1024': 9,
      'validator@mobile-375x812': 8,
      'validator@zoom-200': { darwin: 6, linux: 7 },
    },
  },
  {
    rule: 'button-name',
    impact: 'critical',
    note:
      'FINDING A11Y-02. Below the 640px breakpoint, `chrome.css:503` sets ' +
      '`.topbar-search-label, .topbar-search-kbd { display: none }`. The only other ' +
      'content of `<button class="topbar-search">` is an `aria-hidden` SVG, and the ' +
      'button carries no `aria-label`, so the global search trigger has NO accessible ' +
      'name at phone widths and at 200% browser zoom. Exactly one node on each of the ' +
      '18 surfaces (it lives in the shared TopBar) at exactly the two narrow projects — ' +
      'never at 768px or wider, which is why the desktop pairs are absent below.',
    targetPattern: '^\\.topbar-search$',
    // 36 nodes across 36 (surface, project) pairs.
    counts: {
      'evidence@mobile-375x812': 1, 'evidence@zoom-200': 1,
      'experiments@mobile-375x812': 1, 'experiments@zoom-200': 1,
      'export-readiness@mobile-375x812': 1, 'export-readiness@zoom-200': 1,
      'export-readiness-done@mobile-375x812': 1, 'export-readiness-done@zoom-200': 1,
      'governance@mobile-375x812': 1, 'governance@zoom-200': 1,
      'guided-completion@mobile-375x812': 1, 'guided-completion@zoom-200': 1,
      'load@mobile-375x812': 1, 'load@zoom-200': 1,
      'memory@mobile-375x812': 1, 'memory@zoom-200': 1,
      'memory-graph@mobile-375x812': 1, 'memory-graph@zoom-200': 1,
      'record-detail@mobile-375x812': 1, 'record-detail@zoom-200': 1,
      'schema-reference@mobile-375x812': 1, 'schema-reference@zoom-200': 1,
      'settings@mobile-375x812': 1, 'settings@zoom-200': 1,
      'settings-about@mobile-375x812': 1, 'settings-about@zoom-200': 1,
      'settings-api@mobile-375x812': 1, 'settings-api@zoom-200': 1,
      'settings-explorer@mobile-375x812': 1, 'settings-explorer@zoom-200': 1,
      'settings-privacy@mobile-375x812': 1, 'settings-privacy@zoom-200': 1,
      'statistics@mobile-375x812': 1, 'statistics@zoom-200': 1,
      'validator@mobile-375x812': 1, 'validator@zoom-200': 1,
    },
  },
  {
    rule: 'aria-allowed-attr',
    impact: 'critical',
    note:
      'FINDING A11Y-03. The 31 Evidence Trail entries render as ' +
      '`<button role="listitem" aria-pressed="true|false">`. `role="listitem"` ' +
      'overrides the implicit button role, and `aria-pressed` is not allowed on ' +
      'listitem — so the selected/unselected state is not exposed at all. 31 nodes, ' +
      'identical at every viewport: the trail length is fixed by the synthetic seed.',
    // axe qualifies a target with its parent only when the bare selector is
    // ambiguous, so both forms occur among the same 31 buttons.
    targetPattern:
      '^(\\.selected|(div\\[role="list"\\]:nth-child\\(\\d+\\) > )?' +
      '\\.trail-entry\\[role="listitem"\\]\\[type="button"\\](:nth-child\\(\\d+\\))?)$',
    // 155 nodes across 5 (surface, project) pairs.
    counts: {
      'evidence@desktop-1280x800': 31,
      'evidence@laptop-1024x768': 31,
      'evidence@tablet-768x1024': 31,
      'evidence@mobile-375x812': 31,
      'evidence@zoom-200': 31,
    },
  },
  {
    rule: 'aria-allowed-role',
    impact: 'minor',
    note:
      'FINDING A11Y-03 (same 31 nodes as above). `role="listitem"` is not an allowed ' +
      'role for `<button>`. The intent (a list of selectable evidence entries) is ' +
      'expressible as `<ul role="list"><li><button aria-pressed=…>`.',
    // axe qualifies a target with its parent only when the bare selector is
    // ambiguous, so both forms occur among the same 31 buttons.
    targetPattern:
      '^(\\.selected|(div\\[role="list"\\]:nth-child\\(\\d+\\) > )?' +
      '\\.trail-entry\\[role="listitem"\\]\\[type="button"\\](:nth-child\\(\\d+\\))?)$',
    // 155 nodes across 5 (surface, project) pairs.
    counts: {
      'evidence@desktop-1280x800': 31,
      'evidence@laptop-1024x768': 31,
      'evidence@tablet-768x1024': 31,
      'evidence@mobile-375x812': 31,
      'evidence@zoom-200': 31,
    },
  },
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
 */
export const A11Y_BASELINE_TOTAL_NODES: Readonly<Record<BaselinePlatform, number>> = {
  darwin: 1974,
  linux: 1980,
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

/** All (surface, project) pairs the suite scans — used by the well-formedness test. */
export function allScanPairs(): { surfaceId: string; projectId: ProjectId }[] {
  return SURFACES.flatMap((s) => PROJECT_IDS.map((p) => ({ surfaceId: s.id, projectId: p })));
}
