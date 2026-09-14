/**
 * QA-023 · AN `aria-label` ON AN ELEMENT THAT CANNOT CARRY ONE IS ANNOUNCED TO
 * NOBODY, AND NOTHING IN THIS REPOSITORY WAS WATCHING FOR IT.
 *
 * ── WHAT WAS MEASURED ──────────────────────────────────────────────────────
 *
 * A bare `<span>` or `<div>` has the implicit ARIA role `generic`, and the ARIA
 * spec PROHIBITS naming a `generic`. Browsers therefore compute the name and
 * discard it: the author's sentence is written, shipped, and reaches no one.
 *
 * Measured with an instrumented axe run over all 28 surfaces at
 * `desktop-1280x800` (temporary probe, run and removed, not committed):
 *
 *     before   QA023_TOTAL=86   {evidence:66, record-detail:3, record-runs:3,
 *                                record-capture:3, record-graph:3,
 *                                export-readiness:3, export-readiness-done:3,
 *                                guided-completion:1, memory:1}
 *     after    QA023_AFTER_TOTAL=0   {}
 *
 * Five components, all labelled CONTAINERS, all fixed with `role="group"` —
 * ARIA's role for a set of UI objects not included in the page summary. It
 * permits a name and adds no behaviour, no required children and no keyboard
 * semantics.
 *
 * ── WHY NO EXISTING GUARD CAUGHT 86 NODES ─────────────────────────────────
 *
 * `e2e/specs/a11y-axe.spec.ts` reads `results.violations` ONLY. axe reports
 * this rule as **`incomplete`** — a third bucket, neither pass nor fail, that
 * the sweep does not look at. So the full seven-viewport sweep was green
 * throughout, and running it again after this fix reports **zero movements**,
 * because nothing it counts ever changed. A guard that reads one bucket is
 * evidence about that bucket and about nothing else.
 *
 * ── WHY THIS TEST IS A SOURCE SCAN AND NOT AN AXE RUN ─────────────────────
 *
 * The honest alternative was to widen the a11y sweep to read `incomplete`. That
 * was declined for a stated reason rather than for convenience: `incomplete`
 * also holds 60 `color-contrast` nodes that are genuinely UNDECIDABLE (axe
 * cannot resolve a background over an SVG chart or a canvas), so adopting the
 * whole bucket would import 60 entries that can never reach zero and would
 * teach a reader to ignore it. This scan takes the one rule whose `incomplete`
 * verdict is deterministic from the source, and leaves the rest measured and
 * named in the ledger.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

/* `__dirname`, as `storage-mock-is-effective.test.ts` already does here — a
   `new URL('..', import.meta.url).pathname` resolves to a path this vitest
   config cannot read. */
const SRC = resolve(__dirname, '..');

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules' || entry === '__tests__' || entry === 'test') continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...sourceFiles(full));
    else if (/\.tsx$/.test(entry)) out.push(full);
  }
  return out;
}

/**
 * Every `<span …>` or `<div …>` opening tag, with its attribute text.
 *
 * Deliberately NOT a parser. The question is narrow — does this tag carry a
 * name without a role? — and a regex over the opening tag answers it for the
 * shapes this codebase writes. A tag spanning lines is matched because `[^>]*`
 * crosses newlines here; the negative controls below prove that.
 */
const OPENING_TAG = /<(span|div)(\s[^>]*?)?>/g;

const NAMING_ATTR = /\b(aria-label|aria-labelledby)\s*=/;
const HAS_ROLE = /\brole\s*=/;

describe('QA-023 · a name on a `generic` is announced to nobody', () => {
  it('no `<span>` or `<div>` under src/ carries a name without a role', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles(SRC)) {
      const src = readFileSync(file, 'utf8');
      for (const m of src.matchAll(OPENING_TAG)) {
        const attrs = m[2] ?? '';
        if (!NAMING_ATTR.test(attrs)) continue;
        if (HAS_ROLE.test(attrs)) continue;
        const line = src.slice(0, m.index).split('\n').length;
        offenders.push(`${file.replace(SRC + '/', 'src/')}:${line}  <${m[1]} …${attrs.trim().slice(0, 80)}>`);
      }
    }
    expect(
      offenders,
      'A bare <span>/<div> has the implicit role `generic`, and ARIA PROHIBITS naming a\n' +
        '`generic` — the browser computes this label and throws it away. Give the element a\n' +
        'role that permits a name (`group` for a labelled container; see ProvenanceChips.tsx),\n' +
        'or move the text into a visually-hidden child. QA-023 found 86 of these:\n\n' +
        offenders.join('\n'),
    ).toEqual([]);
  });

  it('POLARITY CONTROL — the scan MATCHES the shapes it forbids, and spares the shapes it allows', () => {
    /*
     * Without this the test above is indistinguishable from one whose regex
     * never matches anything. Every `forbidden` string is a real shape this
     * codebase shipped; every `allowed` one is a real shape it still ships.
     */
    const forbidden = [
      '<span className="prov-pair" aria-label="Where this came from">',
      '<div className="evclass-sources" aria-label="Safe source references">',
      '<span aria-labelledby="some-heading">',
      // multi-line, which is how four of the five real offenders were written
      '<span\n  className="statusbar-seg"\n  key="validation"\n  aria-label="Validation signal"\n>',
    ];
    for (const shape of forbidden) {
      const hit = [...shape.matchAll(OPENING_TAG)].some(
        (m) => NAMING_ATTR.test(m[2] ?? '') && !HAS_ROLE.test(m[2] ?? ''),
      );
      expect(hit, `the scan does NOT catch: ${shape}`).toBe(true);
    }

    const allowed = [
      // the fix
      '<span className="prov-pair" role="group" aria-label="Where this came from">',
      // an element whose role permits a name for other reasons
      '<div role="region" aria-label="About this">',
      '<div className="memory-graph-chips" role="group" aria-label="Active filters">',
      // no name at all — not this rule's business
      '<span className="exp-title">',
      // a name on an element that is NOT a span/div, e.g. a button, which can
      // always carry one. The scan must not widen to those and start shouting.
      '<button aria-label="Close">',
    ];
    for (const shape of allowed) {
      const hit = [...shape.matchAll(OPENING_TAG)].some(
        (m) => NAMING_ATTR.test(m[2] ?? '') && !HAS_ROLE.test(m[2] ?? ''),
      );
      expect(hit, `the scan WRONGLY catches: ${shape}`).toBe(false);
    }
  });

  it('VACUITY GUARD — the sweep reads a meaningful number of files and tags', () => {
    // A scan that silently read nothing would pass the first test forever.
    const files = sourceFiles(SRC);
    expect(files.length, 'the .tsx sweep found almost no files').toBeGreaterThan(100);
    const tags = files.reduce(
      (n, f) => n + [...readFileSync(f, 'utf8').matchAll(OPENING_TAG)].length,
      0,
    );
    expect(tags, 'the tag regex matched almost nothing').toBeGreaterThan(1000);
  });
});
