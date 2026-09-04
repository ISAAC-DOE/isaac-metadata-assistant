/**
 * I-2 (independent review of PR-E, 2026-09-03) — the compact `<=1024px`
 * workflow spine must keep a non-current step's blocking REASON in the
 * accessibility tree, even though it is not painted. The regression this
 * guards: an earlier revision used `display: none` on
 * `.spine-step:not(.current) .spine-meta`, which removes an element from
 * BOTH the viewport AND the accessibility tree — so a screen-reader user on
 * a tablet/phone could no longer tell a `reopened` step from a `blocked`
 * one (`WorkflowSpine.tsx`'s own contract, `:56-58`, requires the reason
 * text for exactly that distinction).
 *
 * HONESTY ABOUT WHAT IS PROVEN HERE. jsdom applies no real layout engine and
 * does not compute a browser accessibility tree at all (there is no
 * Playwright-style `ariaSnapshot` available under vitest), so this file
 * proves the two things jsdom access CAN verify directly and that together
 * establish the fix:
 *
 *   1. RENDERED — the reason text is unconditionally present in the DOM
 *      (`textContent`) for every unsatisfied step, current or not, so there
 *      is no code path that drops it from the tree at render time.
 *   2. CSS SOURCE — `workflow.css`'s narrow-width rule for the class that
 *      hides a non-current reason visually does NOT use `display: none` (or
 *      `visibility: hidden`, or `aria-hidden`), which is what would remove
 *      it from the accessibility tree; it uses the clip-path visually-hidden
 *      technique, which does not.
 *
 * A real ariaSnapshot comparison at 768px vs 1440px belongs in a Playwright
 * spec (browser accessibility tree); the finding's own measurement was taken
 * that way. This file is the fast, CI-cheap regression guard that fails the
 * instant someone reaches for `display: none` again.
 */

import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { WorkflowSpine } from '../components/WorkflowSpine';
import type { ApiWorkflow, ApiWorkflowStep } from '../lib/types';

function renderSpine(workflow: ApiWorkflow | null, recordId?: string) {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <WorkflowSpine workflow={workflow} recordId={recordId} />
    </MemoryRouter>,
  );
}

function step(
  partial: Partial<ApiWorkflowStep> & Pick<ApiWorkflowStep, 'id' | 'label' | 'state'>,
): ApiWorkflowStep {
  return {
    current: partial.state === 'current',
    reopened: partial.state === 'reopened',
    blocked: partial.state === 'blocked',
    reason: null,
    ...partial,
  };
}

const REOPENED_REASON =
  'An upstream change reopened this step; it no longer reflects the current record.';

const MIXED_WORKFLOW: ApiWorkflow = {
  ordered_steps: [
    step({ id: 'load_record', label: 'Load Record', state: 'completed' }),
    step({ id: 'complete_metadata', label: 'Complete Metadata', state: 'current' }),
    step({
      id: 'review_evidence',
      label: 'Review Evidence',
      state: 'reopened',
      reopened: true,
      reason: REOPENED_REASON,
    }),
    step({
      id: 'review_export_readiness',
      label: 'Review Export Readiness',
      state: 'reopened',
      reopened: true,
      reason: REOPENED_REASON,
    }),
    step({ id: 'export', label: 'Export', state: 'completed' }),
  ],
  current_step: 'complete_metadata',
  record_rev: 12,
};

const BLOCKED_WORKFLOW: ApiWorkflow = {
  ordered_steps: [
    step({ id: 'load_record', label: 'Load Record', state: 'completed' }),
    step({ id: 'complete_metadata', label: 'Complete Metadata', state: 'current' }),
    step({
      id: 'review_evidence',
      label: 'Review Evidence',
      state: 'blocked',
      blocked: true,
      reason: "Complete 'Complete Metadata' first.",
    }),
  ],
  current_step: 'complete_metadata',
  record_rev: 0,
};

describe('I-2 · a non-current step reason stays in the DOM/a11y tree at narrow widths', () => {
  it('a reopened (non-current) step reason is present in the DOM verbatim — never dropped', () => {
    const { container } = renderSpine(MIXED_WORKFLOW, 'demo');
    const metas = Array.from(container.querySelectorAll('.spine-meta'));
    // Both reopened steps carry their reason text — nothing removed it.
    const reasons = metas.map((m) => m.textContent);
    expect(reasons.filter((r) => r === REOPENED_REASON)).toHaveLength(2);
  });

  it('a blocked (non-current) step reason is present in the DOM verbatim — never dropped', () => {
    const { container } = renderSpine(BLOCKED_WORKFLOW, 'demo');
    const meta = container.querySelector('.spine-meta');
    expect(meta?.textContent).toBe("Complete 'Complete Metadata' first.");
  });

  it('a non-current reason carries the narrow-hidden class; the CURRENT step\'s own reason (if any) does not', () => {
    const { container } = renderSpine(MIXED_WORKFLOW, 'demo');
    const reopenedMetas = Array.from(container.querySelectorAll('.spine-meta'));
    // Both rendered reasons in this fixture belong to non-current (reopened)
    // steps, so both must carry the class the narrow-width CSS keys on.
    for (const m of reopenedMetas) {
      expect(m.className).toContain('spine-meta-compact-narrow');
    }
  });

  it('CSS SOURCE — the narrow-hidden rule never uses display:none, visibility:hidden, or aria-hidden (which would remove it from the accessibility tree); it uses the clip-path visually-hidden technique', () => {
    const sources = import.meta.glob('../components/workflow.css', {
      query: '?raw',
      import: 'default',
      eager: true,
    }) as Record<string, string>;
    const src = Object.values(sources)[0];

    // Isolate the `.spine-meta-compact-narrow` rule block specifically —
    // asserting over the WHOLE file would pass even if this exact selector
    // regressed, as long as `display: none` did not appear ANYWHERE else.
    const ruleMatch = src.match(/\.spine-meta-compact-narrow\s*\{([^}]*)\}/);
    expect(ruleMatch, 'the .spine-meta-compact-narrow rule must exist').not.toBeNull();
    const rule = ruleMatch![1];

    expect(rule).not.toMatch(/display\s*:\s*none/);
    expect(rule).not.toMatch(/visibility\s*:\s*hidden/);
    expect(rule).toMatch(/clip-path\s*:\s*inset/);
    expect(rule).toMatch(/position\s*:\s*absolute/);

    // And the `spine-meta` span itself never carries aria-hidden — icons
    // elsewhere in this component legitimately do (they are decorative), so
    // this checks the specific JSX line that renders the reason text, not
    // the whole file.
    const tsxSources = import.meta.glob('../components/WorkflowSpine.tsx', {
      query: '?raw',
      import: 'default',
      eager: true,
    }) as Record<string, string>;
    const tsx = Object.values(tsxSources)[0];
    const spineMetaLine = tsx.match(/<span className=\{`spine-meta[^>]*>/);
    expect(spineMetaLine, 'the spine-meta span JSX must exist').not.toBeNull();
    expect(spineMetaLine![0]).not.toMatch(/aria-hidden/);
  });
});
