/**
 * The client's copy of the workflow labels does not drift from the server's.
 *
 * ── WHY THIS FILE EXISTS ────────────────────────────────────────────────────
 *
 * `lib/workflowSteps.ts::CANONICAL_STEPS` is a SECOND COPY of a vocabulary whose
 * source is `apps/api/isaac_api/workflow.py::CANONICAL_LABELS`. The mirror is
 * deliberate — that file's own note explains why, so a screen NAME can be the
 * step's name rather than a third string authored beside it — but a mirror with
 * nothing checking it is a drift waiting to happen.
 *
 * IT DRIFTED ON 2026-09-14. `load_record` was relabelled `Load Record` →
 * `Record Created` server-side (it links to the `fields` workspace, so a STEP and
 * a PLACE had near-identical names for one page — the project owner reported it as
 * *"'record fields' is the same as 'load record'"*). This mirror was not updated in
 * the same edit, and **four `statistics-page` chart assertions went red** — the only
 * thing that noticed. The assistant's spoken workflow sentence was stranded by the
 * same change; that copy could be DERIVED from the source, and now is.
 *
 * WHAT THIS FILE CAN AND CANNOT PROVE, stated rather than implied. It runs in
 * jsdom with no access to the Python module, so it cannot check server parity —
 * `apps/api/tests/test_workflow_label_mirror.py` does that by reading this
 * repository's TypeScript directly. What it CAN prove is that the two CLIENT
 * copies agree: the mirror in `lib/`, and the `WF_LABELS` map inside
 * `test/apiFixtures.ts` that every rendering test actually draws from. Those two
 * drifted independently, which is why both are named here.
 */

import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { CANONICAL_STEPS, canonicalStepLabel } from '../lib/workflowSteps';
import { fixtureWorkflow } from '../test/apiFixtures';

/** The labels the shared fixture actually serves to every rendering test. */
function fixtureLabels(): Record<string, string> {
  // A record with nothing done: every step present, none satisfied past the first.
  const wf = fixtureWorkflow({
    pending_count: 3,
    draft_ok: false,
    ready: false,
    exported: false,
    rev: 1,
  }) as unknown as { ordered_steps: { id: string; label: string }[] };
  return Object.fromEntries(wf.ordered_steps.map((s) => [s.id, s.label]));
}

describe('the client workflow-label mirror', () => {
  it('agrees with the fixture every rendering test draws from', () => {
    const fixture = fixtureLabels();
    expect(CANONICAL_STEPS.map((s) => s.id)).toEqual(Object.keys(fixture));
    for (const step of CANONICAL_STEPS) {
      expect(canonicalStepLabel(step.id), `mirror label for ${step.id}`).toBe(fixture[step.id]);
    }
  });

  it('no longer carries the retired label, in either copy', () => {
    for (const step of CANONICAL_STEPS) expect(step.label).not.toBe('Load Record');
    expect(canonicalStepLabel('load_record')).toBe('Record Created');
    expect(Object.values(fixtureLabels())).not.toContain('Load Record');
  });

  it('is not vacuous: five steps, every label non-empty', () => {
    const fixture = fixtureLabels();
    expect(Object.keys(fixture).length).toBe(5);
    expect(CANONICAL_STEPS.length).toBe(5);
    for (const label of Object.values(fixture)) expect(label.trim().length).toBeGreaterThan(0);
  });

  it('the retired label is gone from the whole of apps/web, not just these two maps', () => {
    /*
     * The rename touched 12 files and three of them were prose comments describing
     * the spine. A reader hitting a stale comment concludes the product still says
     * "Load Record". Read as bytes (`latin1`) so a NUL-bearing file cannot hide a
     * hit — `CLAUDE.md` §11 records a sweep that returned 0 for exactly that reason.
     */
    const roots = ['lib', 'components', 'screens'];
    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = resolve(dir, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (/\.(ts|tsx|css)$/.test(entry.name)) {
          if (readFileSync(full, 'latin1').includes('Load Record')) offenders.push(full);
        }
      }
    };
    for (const r of roots) walk(resolve(__dirname, '..', r));
    expect(offenders).toEqual([]);
  });
});
