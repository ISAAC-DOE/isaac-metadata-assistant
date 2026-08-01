/**
 * NARROW, DOCUMENTED EXEMPTIONS for the layout probes in `helpers/layout.ts`.
 *
 * This file is NOT `layout-baseline.ts`. The two answer different questions and
 * must not be confused:
 *
 *   * `layout-baseline.ts` enumerates KNOWN APPLICATION DEFECTS that are
 *     tolerated until they are fixed. Every entry there is a bug with a fix
 *     address. Entries are expected to be deleted.
 *   * THIS file enumerates regions whose behaviour is CORRECT BY DESIGN — a
 *     deliberate horizontal scroller, or an accessible-name carrier that is
 *     supposed to paint nothing. Entries here are expected to persist, and each
 *     one cites the stylesheet line that declares the intent.
 *
 * ── Rules for adding an entry (deliberately strict) ─────────────────────────
 *
 *   1. `match` is matched with `Element.matches()` against the OFFENDING
 *      ELEMENT ITSELF. It must name a specific class. A tag-name selector
 *      (`pre`, `span`), a universal selector, or a descendant selector that
 *      exempts a whole SUBTREE (`.card *`) is forbidden: those are the wildcard
 *      exemptions that let `main.screen-main.pad` overflow by 123px at 375px
 *      wide without a single test noticing.
 *   2. `surfaces` is EXHAUSTIVE. An entry is inert on any surface not listed,
 *      so the same class overflowing somewhere unexpected still fails.
 *   3. `evidence` cites the `apps/web/src/**` line that makes the behaviour
 *      deliberate. "It looked intentional" is not evidence; a stylesheet
 *      declaration written for the purpose is.
 *   4. `reason` says what the user can still do. A horizontal scroller is only
 *      acceptable if the content is genuinely scrollable and the surrounding
 *      page is not.
 *
 * Every entry here was MEASURED before it was written down: at widths
 * 1280 / 1024 / 768 / 640 / 390 / 375 / 320, against the `ceea656` production
 * bundle and again against a later rebuild of it. Candidates that were proposed
 * but did NOT actually fire were left OUT rather than pre-authorised — see
 * `NOT_ALLOWLISTED_NOTE` at the bottom, which records those judgement calls and
 * the reasoning, so nobody has to re-derive them.
 *
 * The measurements come from a build whose CSS was being edited concurrently,
 * so treat the exact px figures in the comments as "the geometry that produced
 * this entry", not as a current-state claim. What the entries assert is
 * INTENT — each cites the stylesheet declaration — and intent does not move
 * with a rebuild.
 */

/** A region permitted to overflow its own box horizontally. */
export interface OverflowAllowance {
  readonly id: string;
  /** CSS selector matched against the offending element itself. Must name a class. */
  readonly match: string;
  /** Surface ids (see `surfaces.ts`) where this is legitimate. Exhaustive. */
  readonly surfaces: readonly string[];
  /** What the user can still do, and why the overflow is correct. */
  readonly reason: string;
  /** The `apps/web/src/**` declaration that makes it deliberate. */
  readonly evidence: string;
}

/**
 * `true` for surfaces where the allowance applies everywhere. Used only by the
 * visually-hidden utilities, which are shared chrome and are not surface-bound.
 */
export const ANY_SURFACE = '*' as const;

export const OVERFLOW_ALLOWANCES: readonly OverflowAllowance[] = [
  {
    id: 'ALLOW-SCROLL-X',
    match: '.scroll-x',
    // Measured: `div.preview-lines.scroll-x` on the evidence route, scrollWidth
    // 493 vs clientWidth 323 at 375px. `pre.preview-json.scroll-x` is the same
    // utility on the same surface.
    surfaces: ['evidence'],
    reason:
      'A DELIBERATE horizontal scroller for source-file lines, record JSON and sidecar JSON. ' +
      'The content is monospaced data (hashes, URIs, `values[]`) that must not be re-wrapped, ' +
      'because re-wrapping a hash changes what the user reads. It scrolls INSIDE its own box; ' +
      'the page does not scroll with it, which is exactly the distinction the document-level ' +
      'probe enforces. Only three call sites exist (SourcePreview.tsx:69, :91, :100), so the ' +
      'class is narrow in practice as well as in principle.',
    evidence: 'apps/web/src/styles/base.css:287 — `.scroll-x { overflow-x: auto; overflow-y: hidden; }`',
  },
  {
    id: 'ALLOW-ARTIFACT-PATH',
    match: '.artifact-path',
    // Measured: export-readiness-done @ 1280, scrollWidth 299 vs clientWidth 288.
    surfaces: ['export-readiness-done'],
    reason:
      'The exported-artifact file path. `white-space: nowrap` plus `overflow-x: auto` is chosen ' +
      'so a path is shown as ONE unbroken string — a wrapped path is ambiguous about whether the ' +
      'break is a real character. Scrolls inside its own bordered box.',
    evidence: 'apps/web/src/components/artifact.css:45-56 — `.artifact-path { overflow-x: auto; white-space: nowrap; }`',
  },
  {
    id: 'ALLOW-API-CODE-SAMPLES',
    match: '.api-samples-code',
    // Measured firing at settings-api @ 390 (280/232), @ 375 (280/227) and
    // @ 320 (280/172). NOT extended to `settings-explorer`, where the same
    // class exists but sits inside a CLOSED `<details>` and is therefore never
    // reported (the probe skips `content-visibility: hidden` subtrees) — see
    // the note on `.api-browser-json` below.
    surfaces: ['settings-api'],
    reason:
      'A `<pre>` code sample (`white-space: pre`). Copy-pasteable curl/HTTP examples must not be ' +
      'reflowed: a wrapped shell command is a different command. Scrolls in both axes inside a ' +
      '280px-tall box.',
    evidence: 'apps/web/src/screens/screens.css:2637-2648 — `.api-samples-code { overflow: auto; white-space: pre; }`',
  },
];

/**
 * VISUALLY-HIDDEN accessible-name carriers: elements that are SUPPOSED to paint
 * nothing while remaining in the accessibility tree.
 *
 * These are listed BY EXPLICIT CLASS NAME and never by geometry, and that choice
 * is the whole point. The obvious shortcut — "exempt anything whose clientWidth
 * is 0 or 1" — is precisely the rule that would swallow the defect this suite
 * was hardened to catch: the top-bar `span.record-title` measures clientWidth 0
 * with scrollWidth 250 at 375px, i.e. 100% content loss, and a geometric
 * exemption cannot tell it apart from an `.sr-only` span.
 *
 * Each class below implements the standard clip-rect pattern (1x1 box, clipped,
 * `white-space: nowrap`) and exists so a control or figure has an accessible
 * name. Their text is never intended to be seen.
 */
export const HIDDEN_TEXT_ALLOWANCES: readonly OverflowAllowance[] = [
  {
    id: 'ALLOW-SR-ONLY',
    match: '.sr-only',
    surfaces: [ANY_SURFACE],
    reason: 'The app-wide visually-hidden utility. Supplies accessible names/units to screen readers only.',
    evidence: 'apps/web/src/styles/base.css:293-302 — `.sr-only { width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); }`',
  },
  {
    id: 'ALLOW-GRAPH-VISUALLY-HIDDEN',
    match: '.memory-graph-visually-hidden',
    surfaces: ['memory-graph'],
    reason: 'Surface-local visually-hidden utility naming the graph search box and the graph command field.',
    evidence: 'apps/web/src/screens/graph/graph.css:73-74 — "visually-hidden utility (this surface only)"',
  },
  {
    id: 'ALLOW-VALIDATOR-VISUALLY-HIDDEN',
    match: '.rec-val-visually-hidden',
    surfaces: ['validator'],
    reason: 'Visually-hidden label for the standalone validator file input.',
    evidence: 'apps/web/src/components/record-validator.css:135',
  },
  {
    id: 'ALLOW-CSV-RECON-VISUALLY-HIDDEN',
    match: '.csv-recon-visually-hidden',
    surfaces: ['evidence'],
    reason: 'Visually-hidden label for the CSV reconciliation file input.',
    evidence: 'apps/web/src/components/csv-reconcile.css:74',
  },
];

/**
 * DELIBERATELY NOT ALLOWLISTED — the judgement calls, recorded so that a future
 * session does not have to re-derive them and cannot quietly reverse them.
 *
 * `div.screen-card` (`overflow: hidden`, scrollWidth 575 vs clientWidth 353 on
 *   the record-detail route at 375px)
 *   → NOT allowlisted. `overflow: hidden` on the app shell is a containment
 *     rule, not a scroller: whatever crosses that edge is GONE, with no scroll
 *     affordance and no ellipsis. The 222px of content beyond the edge is the
 *     StatusBar, and `layout-baseline.ts` LAYOUT-01 already records the same
 *     defect from the clipped-text side. It belongs in the defect baseline, not
 *     in an "intentional" list.
 *
 * `footer.statusbar` (scrollWidth 575 vs clientWidth 353)
 *   → NOT allowlisted, and it is not even reported by the overflow probe: its
 *     computed `overflow-x` is `visible`, so it SPILLS rather than clipping or
 *     scrolling, and the probe attributes the finding to the first ancestor that
 *     actually clips it (`div.screen-card`, above). Two probes already cover it
 *     from the other side (LAYOUT-01's clipped segments, and the hardened
 *     occlusion probe, which now includes `.statusbar-*` as status labels). The
 *     fix address is `src/components/chrome.css` (.statusbar does not reflow).
 *
 * `span.trail-key` (`overflow: hidden` + `text-overflow: ellipsis`, scrollWidth
 *   291 vs clientWidth 253 on the evidence route)
 *   → NOT allowlisted, and deliberately routed to the ELLIPSIS STORY instead.
 *     Every single-line ellipsis container has scrollWidth > clientWidth by
 *     construction; allowlisting them one by one would grow without bound and
 *     would exempt the magnitude question along with the geometry. The overflow
 *     probe therefore classifies them as `ellipsisDeferred` (reported, never
 *     silently dropped) and `findClippedText` judges whether enough text is
 *     still visible. At 253px of 291px, `span.trail-key` keeps ~87% of its
 *     content and reads fine; at 0px of 250px, `span.record-title` does not —
 *     which is a distinction only the magnitude test can make.
 *
 * `.api-browser-json` (the Endpoint Explorer response sample, `overflow: auto`)
 *   → NOT allowlisted, because it never fires: it lives inside a `<details>`
 *     that is CLOSED by default, and the probes skip closed disclosures (that
 *     handling exists because ignoring it produced three confident, wrong
 *     reports). Writing the entry anyway would pre-authorise an overflow no
 *     measurement has ever seen. If a future spec opens that disclosure and the
 *     probe fires, add the entry THEN, with the measurement.
 *
 * `.graph-canvas` (the graph surface on `/memory?tab=graph`)
 *   → NOT allowlisted, because it did not fire. It was measured at 1280 / 768 /
 *     375 / 320 and its scrollWidth never exceeded its clientWidth (the canvas
 *     sizes to its container: `graph.css:1817` clamps its height, and the SVG
 *     scales). Writing a pre-emptive entry would have granted an exemption
 *     nobody needs and would hide a future regression there.
 */
export const NOT_ALLOWLISTED_NOTE =
  'See the block comment above this constant for the five judgement calls ' +
  '(div.screen-card, footer.statusbar, span.trail-key, .api-browser-json, .graph-canvas).';

/**
 * The selectors that apply on a given surface, for `findOverflowingRegions`.
 *
 * The visually-hidden carriers are included as well, and must be: the clip-rect
 * pattern is a 1px box holding a full sentence, so `scrollWidth 285 vs
 * clientWidth 1` is not a defect there but the mechanism working as designed.
 * Measured before this was added: they produced 84 of the 98 overflow findings
 * across seven widths, drowning the six real ones.
 */
export function overflowMatchersFor(surfaceId: string): { id: string; match: string }[] {
  return [...OVERFLOW_ALLOWANCES, ...HIDDEN_TEXT_ALLOWANCES]
    .filter((a) => a.surfaces.includes(ANY_SURFACE) || a.surfaces.includes(surfaceId))
    .map((a) => ({ id: a.id, match: a.match }));
}

/** The selectors permitted to render no visible text, for `findClippedText`. */
export function hiddenTextMatchersFor(surfaceId: string): { id: string; match: string }[] {
  return HIDDEN_TEXT_ALLOWANCES.filter(
    (a) => a.surfaces.includes(ANY_SURFACE) || a.surfaces.includes(surfaceId)
  ).map((a) => ({ id: a.id, match: a.match }));
}
