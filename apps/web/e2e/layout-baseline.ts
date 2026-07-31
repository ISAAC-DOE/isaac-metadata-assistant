/**
 * KNOWN, PRE-EXISTING RESPONSIVE-LAYOUT DEFECTS.
 *
 * Same contract as `a11y-baseline.ts`: an enumerated list of real bugs the
 * suite found in `apps/web/src/**`, not a way of switching a check off.
 * Anything the probes report that is NOT matched here fails the build.
 *
 * ── Matching is per INSTANCE, by exact selector ─────────────────────────────
 *
 * The first version matched with `selector.includes('statusbar')` scoped to a
 * cross-product of five surfaces and three projects. Two problems, both fixed:
 *
 *   * the substring swallowed anything whose selector merely MENTIONED
 *     `statusbar` — a genuinely new clipped descendant inside the footer would
 *     have been absorbed into the known finding and never reported;
 *   * the cross-product claimed 15 (surface, project) pairs. Measurement found
 *     the defect on 8. The other 7 were pre-authorised for free.
 *
 * `instances` below therefore lists, per `surfaceId@projectId`, the EXACT
 * offender selectors the probe produced. Anything else — a new selector, or the
 * same selector on a pair that is not listed — fails.
 *
 * A selector may be reported twice for one element (once for the horizontal
 * clip, once for the vertical); `helpers/layout.ts` de-duplicates on
 * selector + clip axis, so membership rather than a count is the right test.
 *
 * Fixing the CSS makes the matching entry stop firing;
 * `layout-responsive.spec.ts` annotates entries that no longer fire so they can
 * be deleted rather than left to rot.
 */

export interface LayoutFinding {
  readonly id: string;
  /** Which probe produced it. */
  readonly kind: 'clipped' | 'obscured';
  /**
   * Human-readable tag for this finding, used ONLY by the staleness annotation
   * in `layout-responsive.spec.ts` (which is outside this file's ownership and
   * reads `f.selector`). It is NOT what matching is based on — `instances` is.
   */
  readonly selector: string;
  /**
   * `surfaceId@projectId` → the exact offender selectors measured there.
   * Exhaustive: a pair that is absent tolerates nothing.
   */
  readonly instances: Readonly<Record<string, readonly string[]>>;
  readonly note: string;
}

// The StatusBar offenders, named once so the table below stays readable.
const SB_PHASE = 'span.statusbar-phase < footer.statusbar < div.screen-card';
const SB_NOTE = 'span.statusbar-note < footer.statusbar < div.screen-card';
const SB_PENDING = 'span.statusbar-pending < span.statusbar-seg < footer.statusbar';
const SB_ADVISORY = 'span.statusbar-advisory < span.statusbar-seg < footer.statusbar';
const SB_EYEBROW = 'span.statusbar-eyebrow < span.statusbar-seg < footer.statusbar';
const SB_RIGHT = 'span.statusbar-right < span.statusbar-tail < footer.statusbar';

export const LAYOUT_BASELINE: readonly LayoutFinding[] = [
  {
    id: 'LAYOUT-01',
    kind: 'clipped',
    selector: 'statusbar',
    note:
      'The record StatusBar footer does not reflow. At 375px its content measures ' +
      '575px in a 353px box with `overflow-x: visible`, so the phase / pending / ' +
      'advisory / coverage segments spill sideways and downwards and are then cut ' +
      'by `div.screen-card { overflow: hidden }`. Visually the segments overlap and ' +
      'read as garbled ("dry-run · 1" over "not exported yet"). Severity scales with ' +
      'width: severe at 375, a single vertically-clipped segment at 640 (200% zoom) ' +
      'and at 768, nothing at 1024 or 1280. It affects every record surface because ' +
      'StatusBar is shared chrome, but WHICH segments clip depends on the record\'s ' +
      'own status text, so the lists below differ per surface. Fix belongs in ' +
      '`src/components/chrome.css` (.statusbar), not here.',
    instances: {
      'record-detail@mobile-375x812': [SB_PHASE, SB_PENDING, SB_ADVISORY, SB_EYEBROW, SB_RIGHT],
      'record-detail@tablet-768x1024': [SB_ADVISORY],
      'record-detail@zoom-200': [SB_PHASE, SB_PENDING, SB_ADVISORY],
      'guided-completion@mobile-375x812': [SB_PHASE, SB_NOTE],
      'evidence@mobile-375x812': [SB_NOTE],
      'export-readiness@mobile-375x812': [SB_PENDING, SB_ADVISORY, SB_EYEBROW, SB_RIGHT],
      'export-readiness-done@mobile-375x812': [SB_ADVISORY, SB_EYEBROW, SB_RIGHT],
      'export-readiness-done@zoom-200': [SB_ADVISORY],
    },
  },
  {
    id: 'LAYOUT-02',
    kind: 'clipped',
    selector: 'record-context',
    note:
      'At 375px the TopBar record-context status chip (`span.chip.chip-draft` inside ' +
      '`div.record-context`) runs 9px past the right edge of `div.screen-card` and is ' +
      'cut by its `overflow: hidden` — the label reads "Draf". The evidence surface is ' +
      'where it shows because that TopBar variant carries the widest context row; the ' +
      'underlying cause (record-context does not shrink at phone widths) is shared. ' +
      'Fix belongs in `src/components/chrome.css` (.record-context / .topbar).',
    instances: {
      'evidence@mobile-375x812': ['span < span.chip.chip-draft < div.record-context'],
    },
  },
];

export const layoutKey = (surfaceId: string, projectId: string): string => `${surfaceId}@${projectId}`;

/**
 * True only for an EXACT recorded offender on an EXACT recorded
 * (surface, project) pair. No substrings, no wildcards.
 */
export function isKnownLayoutFinding(
  kind: LayoutFinding['kind'],
  selector: string,
  surfaceId: string,
  projectId: string
): boolean {
  const key = layoutKey(surfaceId, projectId);
  return LAYOUT_BASELINE.some((f) => f.kind === kind && (f.instances[key] ?? []).includes(selector));
}

export function applicableLayoutFindings(surfaceId: string, projectId: string): readonly LayoutFinding[] {
  const key = layoutKey(surfaceId, projectId);
  return LAYOUT_BASELINE.filter((f) => (f.instances[key] ?? []).length > 0);
}

/** Every offender this baseline tolerates, summed — the recorded layout debt. */
export const LAYOUT_BASELINE_TOTAL_INSTANCES = LAYOUT_BASELINE.reduce(
  (n, f) => n + Object.values(f.instances).reduce((m, list) => m + list.length, 0),
  0
);
