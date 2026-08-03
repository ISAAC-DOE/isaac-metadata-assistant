/*
 * R1b · the staged runner offered a control that could not work, with a count it
 * made up.
 *
 * WHAT SHIPPED. `components/StagedRunner.tsx` rendered, whenever a stage carried
 * `isBlocker`, a `btn btn-primary` reading `Answer 5 Fields →`. Three independent
 * things were wrong with it, and each alone would be enough:
 *
 *   1. `isBlocker` was never set. `RunnerStage`'s ONLY producer is
 *      `lib/adapt.ts::demoStepsToStages`, which emits `{key,label,command,state,
 *      detail}` and nothing else. Nothing anywhere assigned the flag.
 *   2. `onAnswer` was never passed. The ONLY call site,
 *      `screens/LoadMaterials.tsx`, renders `<StagedRunner stages={…} />`, so
 *      `onClick` was `undefined` — a primary button that does nothing on click.
 *   3. The `5` was a hard-coded literal. Even had the control worked, the number
 *      of fields it promised to answer was fabricated, unrelated to the record.
 *
 * WHAT THIS ASSERTS. The component cannot render such a control even if handed a
 * stage that still carries the retired flag (assertion 1 — a live-behaviour test,
 * not a source scan, because that is the failure a user would meet), and the flag
 * and the prop are gone from the contract so they cannot be reintroduced by
 * accident (assertions 2-3).
 *
 * WHY A SOURCE SCAN IS PART OF IT. A behaviour test alone would pass if someone
 * re-added `isBlocker?: boolean` to `RunnerStage` and left the CTA out — and the
 * next slice would then wire a producer to a type field whose UI meaning had been
 * deliberately removed. Pinning the type is what makes the deletion durable.
 *
 * WHAT IT CANNOT CATCH: a NEW dead control, in this component or any other. It is
 * a regression pin on one deletion, not a sweep for undefined click handlers.
 */

import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';

import { StagedRunner } from '../components/StagedRunner';
import { demoStepsToStages } from '../lib/adapt';
import type { ApiDemoStep, RunnerStage } from '../lib/types';

function locateSrcDir(): string {
  const candidates = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
  const found = candidates.find((dir) => existsSync(join(dir, 'main.tsx')));
  if (found === undefined) throw new Error(`cannot locate apps/web/src from ${process.cwd()}`);
  return found;
}

const SRC_DIR = locateSrcDir();

/**
 * Comments stripped, so the prose recording the deletion (there is a paragraph of
 * it in `StagedRunner.tsx` and a line in `lib/types.ts`) is not read as the thing
 * deleted — the same trade the sibling honesty guards make. Cost: this says
 * nothing about comments, which is right, because comments render nothing.
 */
const source = (path: string) =>
  readFileSync(join(SRC_DIR, path), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(^|[^:'"`\\])\/\/[^\n]*/g, '$1');

/** The real shape `POST /api/demo/run` returns for its pipeline steps. */
const REAL_STEPS: ApiDemoStep[] = [
  { name: 'load_sources', ok: true, detail: 'read 2 reference files' },
  { name: 'assemble_draft', ok: true, detail: '26 fields' },
  { name: 'validate_draft', ok: false, detail: '5 fields still need your confirmation' },
];

describe('R1b · StagedRunner renders no control it cannot make work', () => {
  it('renders no button at all for the stages its only producer emits', () => {
    const { container } = render(<StagedRunner stages={demoStepsToStages(REAL_STEPS)} />);
    // Zero controls is the honest state: this component reports what the pipeline
    // returned. Anything actionable belongs to the screen around it.
    expect(container.querySelectorAll('button')).toHaveLength(0);
  });

  it('ignores a stage still carrying the retired blocker flag — no dead CTA', () => {
    // Deliberately cast: the flag is gone from the type, and the point is that a
    // stale object carrying it can no longer conjure the control back.
    const stale = [
      { key: 'validate_draft', label: 'Validate Draft', command: 'validate_draft', state: 'current', isBlocker: true },
    ] as unknown as RunnerStage[];
    const { container } = render(<StagedRunner stages={stale} />);
    expect(container.querySelectorAll('button')).toHaveLength(0);
    expect(container.textContent ?? '').not.toMatch(/Answer\s+\d+\s+Fields/i);
  });

  it('renders no fabricated field count anywhere', () => {
    const { container } = render(<StagedRunner stages={demoStepsToStages(REAL_STEPS)} />);
    // Every number on this surface must come from a step's own detail string.
    expect(container.textContent ?? '').not.toMatch(/Answer\s+\d+\s+Fields/i);
  });

  it('every control the runner does render has a real click handler', () => {
    // Vacuous today (there are none), and deliberately kept: if a control is ever
    // added back, this fails unless it is actually wired.
    const { container } = render(<StagedRunner stages={demoStepsToStages(REAL_STEPS)} />);
    for (const button of Array.from(container.querySelectorAll('button'))) {
      expect((button as HTMLButtonElement).onclick).not.toBeNull();
    }
  });
});

describe('R1b · the retired flag and prop are gone from the contract', () => {
  it('`RunnerStage` no longer declares `isBlocker`', () => {
    const types = source('lib/types.ts');
    const iface = /export interface RunnerStage \{[\s\S]*?\n\}/.exec(types);
    expect(iface, 'RunnerStage must still exist').not.toBeNull();
    expect(iface![0]).not.toMatch(/isBlocker/);
  });

  it('no source file references `isBlocker` or an `onAnswer` prop any more', () => {
    for (const path of ['components/StagedRunner.tsx', 'lib/adapt.ts', 'lib/types.ts', 'screens/LoadMaterials.tsx']) {
      expect(source(path), `${path} must not mention isBlocker`).not.toMatch(/isBlocker/);
      expect(source(path), `${path} must not mention onAnswer`).not.toMatch(/onAnswer/);
    }
  });

  it('`demoStepsToStages` — the one producer — emits no blocker flag', () => {
    for (const stage of demoStepsToStages(REAL_STEPS)) {
      expect(Object.keys(stage)).not.toContain('isBlocker');
    }
  });
});
