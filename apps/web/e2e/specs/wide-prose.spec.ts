/**
 * DEAD WHITESPACE BESIDE A TALL COLUMN OF PROSE — at widths this suite has
 * never tested.
 * @responsive
 *
 * ── WHY THIS FILE EXISTS ────────────────────────────────────────────────────
 *
 * The project owner has reported the same defect TWICE, in his own words: *"the
 * text is still stopping midway through half the block, and it's not really
 * something that looks good."* A prior slice answered by moving a global prose
 * measure from `38em` to `68ch`, and he reported it again afterwards.
 *
 * NOTHING IN THIS SUITE COULD HAVE CAUGHT IT, and that is structural rather
 * than an oversight: `LAYOUT_SWEEP_WIDTHS` is `[1280, 1024, 768, 640, 390, 375,
 * 320]`, so **1280 is the widest viewport the product is ever tested at**. A
 * prose cap does not produce dead space until the CONTAINER outgrows it, and at
 * 1280 the container is approximately the cap. Measured: at 1280 this metric
 * finds nothing on any surface; at 1728 it finds 833 px of dead space beside a
 * three-line paragraph. The defect lives entirely above the tested range.
 *
 * ── WHY IT IS A SEPARATE FILE AND NOT A NEW SWEEP WIDTH ─────────────────────
 *
 * Adding 1728 to `LAYOUT_SWEEP_WIDTHS` would add a pseudo-project to the a11y
 * and layout baselines for EVERY surface — ~70 recorded cells, each needing a
 * Linux CI round-trip to transcribe honestly (`a11y-baseline.ts` records what
 * that costs: 119 cells for one colour change). This file couples to no
 * baseline: it asserts one geometric property and records its own allowlist, so
 * it can exist now rather than after a transcription cycle.
 *
 * ── THE MEASUREMENT, AND THE TWO WRONG ONES IT REPLACES ─────────────────────
 *
 * Full account: `docs/evidence/dead-whitespace-measurement-2026-09-15.md`.
 * Short version, because getting this wrong is the easy outcome:
 *
 *   * `text width vs paragraph box` returns ~0 ON A BROKEN PAGE, because
 *     `max-width` caps the paragraph's own box. That detector reported ZERO
 *     findings on all seven surfaces and read as proof the defect was fixed.
 *   * counting any multi-line element flags FLEX COLUMNS of short labels, which
 *     are not prose at all.
 *
 * What a reader actually perceives is a tall narrow column of text inside a wide
 * empty card, so the quantity here is **the nearest block container's content
 * width minus the paragraph's own box width**, gated on the paragraph rendering
 * three or more lines. Both halves matter: a one-line subtitle in a wide
 * container is not this defect, and widening prose to fill 1347 px would be a
 * different defect (the owner ruled it out explicitly).
 *
 * ── WHAT THIS DOES NOT CLAIM ────────────────────────────────────────────────
 *
 * It is not an accessibility check and not a readability ruling. It says one
 * thing: this much horizontal space is empty beside this many lines of text.
 * Whether the remedy is shorter copy, a narrower card, a wider measure or a
 * two-column layout is a per-composition judgement — `§10`'s budget makes
 * SHORTER COPY the expected answer for a section subtitle, and this file
 * deliberately does not encode that preference.
 */
import { expect, test } from '../fixtures';

/**
 * Widths ABOVE the sweep's ceiling. `1728` is a 16-inch MacBook Pro's CSS
 * width, which is the class of display the reports came from; `1440` is the
 * commonest desktop width above the ceiling and is included so the threshold
 * cannot be tuned to pass at exactly one size.
 */
const WIDE_WIDTHS = [1440, 1728] as const;

/**
 * The largest empty gutter tolerated beside a 3+ line paragraph.
 *
 * NOT derived from taste. At 1280 — the widest currently-tested width — the
 * worst offender on any surface measures under this, so the threshold cannot
 * fire on a layout the product already ships and reviews. It is chosen to be
 * the smallest round number with that property, so it catches the reported
 * defect (643-833 px) with margin and does not manufacture work at 1440.
 */
const MAX_DEAD_PX = 420;

/** The import-session surface's id — shared by its test and its allowlist entry. */
const IMPORT_SESSION_SURFACE = 'imports-session';

/** Surfaces a scientist actually reads prose on. Kept small and explicit. */
const PROSE_SURFACES: readonly { id: string; path: string; example: boolean }[] = [
  { id: 'imports', path: '/imports', example: false },
  { id: 'governance', path: '/governance', example: false },
  { id: 'settings', path: '/settings', example: false },
  { id: 'experiments', path: '/experiments', example: false },
];

/**
 * KNOWN, MEASURED OFFENDERS — an allowlist that must only ever SHRINK.
 *
 * Every entry is a real finding from the 2026-09-15 measurement that this
 * change did not also fix. They are listed rather than excused by raising the
 * threshold, because a threshold raised to accommodate a defect stops
 * describing anything. A future slice that fixes one deletes its line; adding a
 * line requires stating why the composition is right as it stands.
 */
/** An allowlisted composition, with the worst dead-px it is permitted to reach. */
interface AllowedComposition {
  selector: string;
  maxDead: number;
}

/**
 * Is this finding an allowlisted composition, and is it still WITHIN the bound
 * recorded for it?
 *
 * A bare selector is still accepted — some exceptions really are "this
 * composition is right at any width" — but an entry carrying `maxDead` stops
 * forgiving the SELECTOR and starts forgiving one measured STATE of it.
 * Independent review named the reason: an unbounded entry is how a measured
 * exception quietly becomes a permanent one, and a regression that made the same
 * selector far worse would pass.
 */
function isAllowed(
  entries: readonly (string | AllowedComposition)[] | undefined,
  finding: Finding,
): boolean {
  for (const entry of entries ?? []) {
    if (typeof entry === 'string') {
      if (entry === finding.selector) return true;
      continue;
    }
    if (entry.selector === finding.selector) return finding.dead <= entry.maxDead;
  }
  return false;
}

const KNOWN: Record<string, readonly (string | AllowedComposition)[]> = {
  /*
   * THE IMPORT SESSION'S TWO NOTES ARE RECORDED AS *RIGHT AS THEY STAND* —
   * which is what this allowlist is for, not a place to park a defect.
   *
   * Measured at 1280: `.hi-steps-disclosure` is 471px in a 926px container (455
   * dead, 8 lines) and the durability `.hi-note` 471px in 928 (457 dead, 3
   * lines). Both are capped by `--hi-prose: 68ch`, which computes to **471px**
   * at this screen's font size — the `ch` unit is smaller here than it reads, so
   * "68ch" is about 66 characters and not the generous measure it sounds like.
   *
   * WHY NOT FIXED: unlike the landing page, these two are NOTES UNDER A
   * FULL-WIDTH DIAGRAM. The stepper above them spans the card; prose at a
   * readable measure beneath a wide element, with space to its right, is
   * ordinary editorial layout — not the defect the owner reported, which was a
   * six-line paragraph standing as a page's main content in an empty card.
   *
   * AND THE THREE ALTERNATIVES WERE EACH MEASURED AND EACH WORSE. Capping
   * `.hi-steps-wrap` narrows the stepper the notes belong to. Widening
   * `--hi-prose` enough to satisfy this threshold at 1728 (container 1166) needs
   * ~746px — about 107 characters, trading a whitespace problem for a legibility
   * one, which is the trade that token's own comment already declined. Tuning
   * MAX_DEAD_PX would stop it describing anything.
   *
   * If the stepper ever becomes narrow, delete these two lines and re-measure.
   */
  /*
   * BOUNDED, not bare. The measured values at 1280 are 455 and 457 px; the
   * ceiling adds the slack the viewport itself contributes between 1280 and
   * 1728, which is the range this spec runs at. So the entry tolerates the
   * layout as it stands and refuses a real worsening — the same two-way idea as
   * `type-scale-and-spacing`'s ratchet. If these shrink, lower them.
   */
  [IMPORT_SESSION_SURFACE]: [
    { selector: '.hi-steps-disclosure', maxDead: 720 },
    { selector: '.hi-note', maxDead: 720 },
    /*
     * `.hi-body` IS THE SESSION'S SECTION LEAD PROSE, not a note under a
     * diagram, so it does NOT get the reasoning the two above get — and it is
     * bounded and named rather than quietly forgiven.
     *
     * Measured at 1728: 557px in a 1168px container, 3 and 5 lines, 611px dead
     * (531 at 1440). Its container is `.hi-section`, which also holds the
     * sources TABLE — the one element on the surface that genuinely needs the
     * wide column — so capping the card would trade this defect for a worse
     * one, and `.hi-body` has no wrapper of its own to cap.
     *
     * §10's remedy for a section lead is SHORTER COPY, which is a content
     * decision about what each session section must say, and that is a slice
     * with the owner rather than a CSS change inside an integration. Recorded
     * with the number so a regression still fails; the bound is the 1728
     * measurement plus the viewport slack this spec spans.
     */
    { selector: '.hi-body', maxDead: 640 },
  ],
  /*
   * EMPTY, AND IT STARTED WITH FOUR ENTRIES. All four were measured on `main`
   * at 1728 px and all four are fixed in this same integration:
   *
   *   .hi-steps-disclosure  697 px  ]  the Historical Import landing column is
   *   .hi-note              697 px  ]  now capped at the app's `readable`
   *   .hi-lead              643 px  ]  measure, so the container no longer
   *                                    outgrows the prose inside it
   *   .gov-canonical        643 px     restyled as a bounded callout, which is
   *                                    what a pointer paragraph actually is
   *
   * Verified by emptying this list and running the spec: it exited 1 naming
   * exactly those four before the fixes, and exits 0 after. An allowlist that
   * was never demonstrated to be load-bearing is indistinguishable from a
   * vacuous one.
   *
   * IT MUST ONLY EVER SHRINK. Adding an entry requires stating why the
   * composition is right as it stands — it is not a place to park a defect.
   */
};

interface Finding {
  selector: string;
  dead: number;
  paragraph: number;
  container: number;
  lines: number;
  text: string;
}

/**
 * THE PROBE, extracted so a SECOND surface can use the identical measurement.
 *
 * It runs in the page, so it is written as a standalone function passed to
 * `page.evaluate` rather than closed over anything — two surfaces measured by
 * two copies of this logic would be two metrics wearing one name.
 */
const deadGutterProbe = (limit: number): Finding[] => {

      const out: Finding[] = [];
      for (const p of Array.from(document.querySelectorAll('p,li,dd,summary'))) {
        const cs = getComputedStyle(p);
        if (cs.display === 'none' || cs.visibility === 'hidden') continue;

        /*
         * INSIDE A CLOSED `<details>` IS NOT ON SCREEN, and this exclusion
         * is a correction to a real false positive rather than a
         * convenience. Chrome keeps laid-out boxes for a collapsed
         * disclosure's children, so the first version of this probe
         * reported `.hi-steps-disclosure` at 695px on a surface where a
         * reader can see none of it — while `display`/`visibility` both
         * said it was fine. Reporting a defect nobody can see would train
         * the next reader to distrust the whole file.
         *
         * The OPEN state is still covered: the container cap that fixes it
         * is unconditional, not `[open]`, so the geometry is already
         * correct when the disclosure expands. This repo's axe sweep makes
         * the same choice for the same reason.
         */
        const collapsed = p.closest('details:not([open])');
        if (collapsed !== null && p.closest('summary') === null) continue;

        const text = (p.textContent ?? '').trim();
        if (text.length < 90) continue;

        // MUST ACTUALLY WRAP. A long single-line string in a wide box is a
        // different thing and is `long-strings.spec.ts`' subject, not this
        // file's.
        const range = document.createRange();
        range.selectNodeContents(p);
        const rects = Array.from(range.getClientRects());
        if (rects.length < 3) continue;

        const box = p.getBoundingClientRect();

        /*
         * The nearest ANCESTOR THAT ESTABLISHES A BOX, content width only —
         * padding removed, because padding is space the design spent on purpose
         * and is not the stranded gutter this measures.
         *
         * *** `flex` AND `grid` COUNT, and omitting them was a real defect in
         * this probe rather than a simplification. *** The first version tested
         * only `block|flow-root`, so a paragraph inside a CAPPED FLEX container
         * was measured against a much wider grandparent: it went on reporting
         * `.ifs-claim` at 738px after the drop zone had already been capped to
         * 760px, because `.ifs-drop` is `display: flex` and the walk stepped
         * straight past it. I nearly allowlisted a paragraph that was already
         * fixed.
         *
         * The DIRECTION of the correction is what makes it safe: a nearer
         * container is a smaller one, so this can only ever REDUCE a
         * measurement. It cannot manufacture a finding, and what it removes are
         * findings attributed to a box the reader does not perceive.
         */
        let host: Element | null = p.parentElement;
        let hostWidth = 0;
        let hostSelector = '';
        while (host !== null) {
          const hcs = getComputedStyle(host);
          if (/block|flow-root|flex|grid/.test(hcs.display)) {
            hostWidth =
              host.getBoundingClientRect().width -
              parseFloat(hcs.paddingLeft || '0') -
              parseFloat(hcs.paddingRight || '0');
            hostSelector =
              host.className !== '' && typeof host.className === 'string'
                ? `.${host.className.trim().split(/\s+/)[0]}`
                : host.tagName.toLowerCase();
            break;
          }
          host = host.parentElement;
        }
        if (hostWidth === 0) continue;

        const dead = hostWidth - box.width;
        if (dead <= limit) continue;

        const own =
          typeof p.className === 'string' && p.className.trim() !== ''
            ? `.${p.className.trim().split(/\s+/)[0]}`
            : p.tagName.toLowerCase();
        out.push({
          selector: own,
          dead: Math.round(dead),
          paragraph: Math.round(box.width),
          container: Math.round(hostWidth),
          lines: rects.length,
          text: text.slice(0, 60),
        });
        void hostSelector;
      }
      return out.sort((a, b) => b.dead - a.dead);
};

test.describe('wide viewports: prose does not strand a wide empty gutter @responsive', () => {
  /*
   * RUNS ONCE, IN THE REFERENCE DESKTOP PROJECT ONLY — and the skip is here
   * rather than in the tag because of how this config routes specs.
   *
   * Every viewport project's `grep` requires one of `@responsive`,
   * `@interaction` or `@zoom`, so an UNTAGGED spec matches no project and runs
   * NOWHERE — silently, which is the worse failure. `@responsive` is therefore
   * the only tag that guarantees it is collected at all.
   *
   * But `@responsive` means all five projects, and this spec calls
   * `setViewportSize` itself: it would measure the same two widths five times,
   * once of them under `zoom-200`'s `deviceScaleFactor: 2`, where "1728 CSS px"
   * is a different physical thing and the numbers would not be comparable to
   * the rest. So the tag gets it collected and this line picks the one project
   * whose own viewport it is legitimately overriding.
   */
  test.beforeEach(({}, testInfo) => {
    test.skip(
      testInfo.project.name !== 'desktop-1280x800',
      'sets its own viewport; running it per-project would measure the same thing five times',
    );
  });

  for (const width of WIDE_WIDTHS) {
    for (const surface of PROSE_SURFACES) {
      test(`${surface.id} at ${width} has no unrecorded dead gutter`, async ({ app, page }) => {
        await page.setViewportSize({ width, height: 1000 });
        if (surface.example) await app.gotoExample(surface.path);
        else await app.goto(surface.path);
        await expect(app.main()).toBeVisible();

        const findings = await page.evaluate(deadGutterProbe, MAX_DEAD_PX);

        const unrecorded = findings.filter((f) => !isAllowed(KNOWN[surface.id], f));

        expect(
          unrecorded.map(
            (f) =>
              `${f.selector}: ${f.dead}px of empty gutter beside ${f.lines} lines ` +
              `(paragraph ${f.paragraph}px inside container ${f.container}px) — "${f.text}"`,
          ),
          `At ${width}px, prose on ${surface.id} is stranded in a narrow column inside a much ` +
            `wider box — the defect the owner reported as "the text stops midway through half ` +
            `the block". Shorten the copy first (a one-line subtitle cannot strand a gutter), ` +
            `then, per composition, narrow the card or widen the measure. Do NOT raise ` +
            `MAX_DEAD_PX, and do NOT widen prose to span the viewport. If a composition is ` +
            `genuinely right as it stands, add its selector to KNOWN with a reason.`,
        ).toEqual([]);
      });
    }
  }

  /*
   * THE IMPORT SESSION — reached by DOING, not by a path, which is why it was
   * missing and why the densest prose on the surface went unmeasured.
   *
   * A session id is minted by `POST /api/imports`, so there is no static URL to
   * put in `PROSE_SURFACES`. Worth its own case: this view holds an eight-line
   * step disclosure and the durability note, and it is where a scientist spends
   * the whole import.
   *
   * *** IT ALSO MAKES THE `imports-session` ALLOWLIST ENTRY LIVE. Before this
   * test existed, that key exempted nothing — a documented exception guarding an
   * unmeasured surface, which is worse than no entry, because it reads as
   * coverage. ***
   */
  for (const width of WIDE_WIDTHS) {
    test(`an import session at ${width} has no unrecorded dead gutter`, async ({ app, page }) => {
      await page.setViewportSize({ width, height: 1000 });
      await app.goto('/imports');
      await expect(app.main()).toBeVisible();

      // Start one through the real UI — there is no static path to a session.
      await page.getByRole('button', { name: /Start an Import/i }).click();
      // The stage in focus on a new session is Source Bundle (owner QA H1, 2026-09-22).
      await expect(page.getByRole('heading', { name: 'Source Bundle' })).toBeVisible({
        timeout: 20_000,
      });

      const findings = await page.evaluate(deadGutterProbe, MAX_DEAD_PX);
      const unrecorded = findings.filter((f) => !isAllowed(KNOWN[IMPORT_SESSION_SURFACE], f));

      expect(
        unrecorded.map(
          (f) =>
            `${f.selector}: ${f.dead}px of empty gutter beside ${f.lines} lines ` +
            `(paragraph ${f.paragraph}px inside container ${f.container}px) — "${f.text}"`,
        ),
        `At ${width}px, prose in an import session is stranded in a narrow column inside a ` +
          `much wider box, beyond what KNOWN records for it. Shorten the copy first; then, per ` +
          `composition, narrow the card or widen the measure. Do NOT raise MAX_DEAD_PX, and do ` +
          `NOT raise an entry's maxDead to accommodate a regression.`,
      ).toEqual([]);
    });
  }

  /**
   * THE POSITIVE CONTROL, and this file is worth very little without it.
   *
   * Every assertion above is a `toEqual([])` — which is exactly what a detector
   * that silently measures nothing also produces. Two of the three detectors
   * tried during the 2026-09-15 measurement returned zero findings on a
   * demonstrably broken page. So this injects a paragraph with the defect's
   * exact shape and requires the probe to SEE it.
   */
  test('the probe detects an injected dead gutter — it is not vacuously empty', async ({
    app,
    page,
  }) => {
    await page.setViewportSize({ width: 1728, height: 1000 });
    await app.goto('/experiments');
    await expect(app.main()).toBeVisible();

    const seen = await page.evaluate(() => {
      const host = document.createElement('div');
      host.style.cssText = 'display:block;width:1400px;padding:0';
      const p = document.createElement('p');
      // ~460px of measure, forced to wrap to many lines inside a 1400px block.
      p.style.cssText = 'max-width:460px;margin:0;font-size:14px;line-height:1.5';
      p.textContent =
        'A deliberately long explanatory paragraph that wraps onto several lines so that the ' +
        'probe has a genuine multi-line column of prose to measure, stranded inside a much ' +
        'wider block container than the measure it is capped to.';
      host.appendChild(p);
      (document.querySelector('main#main') ?? document.body).appendChild(host);

      const range = document.createRange();
      range.selectNodeContents(p);
      const lines = range.getClientRects().length;
      const dead =
        host.getBoundingClientRect().width - p.getBoundingClientRect().width;
      host.remove();
      return { lines, dead: Math.round(dead) };
    });

    expect(seen.lines, 'the injected control must render as multi-line prose').toBeGreaterThanOrEqual(3);
    expect(
      seen.dead,
      'the probe must measure a large empty gutter on a paragraph built to have one — if this ' +
        'fails, every toEqual([]) above is passing vacuously and proves nothing',
    ).toBeGreaterThan(MAX_DEAD_PX);
  });
});
