import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { WorkflowSpine } from '../components/WorkflowSpine';
import type { ApiWorkflow, ApiWorkflowStep } from '../lib/types';

/*
 * P28.1 — the WorkflowSpine renders the BACKEND-derived workflow verbatim. It
 * never re-derives step order or completion; it reads only the `workflow` prop.
 */

function renderSpine(workflow: ApiWorkflow | null, recordId?: string) {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <WorkflowSpine workflow={workflow} recordId={recordId} />
    </MemoryRouter>,
  );
}

function step(partial: Partial<ApiWorkflowStep> & Pick<ApiWorkflowStep, 'id' | 'label' | 'state'>): ApiWorkflowStep {
  return {
    current: partial.state === 'current',
    reopened: partial.state === 'reopened',
    blocked: partial.state === 'blocked',
    reason: null,
    ...partial,
  };
}

function stepLi(container: HTMLElement, label: string): HTMLElement {
  const items = Array.from(container.querySelectorAll('li.spine-step')) as HTMLElement[];
  const li = items.find((el) => el.querySelector('.spine-label')?.textContent === label);
  if (!li) throw new Error(`spine step "${label}" not found`);
  return li;
}

// A full canonical workflow with one step in each unsatisfied variant so every
// state is exercised in one render: load completed, complete current, evidence
// reopened, readiness reopened, export completed (a LATER step satisfied is what
// makes the middle steps "reopened" rather than "blocked").
const REOPENED_REASON =
  'An upstream change reopened this step; it no longer reflects the current record.';

const MIXED_WORKFLOW: ApiWorkflow = {
  ordered_steps: [
    step({ id: 'load_record', label: 'Load Record', state: 'completed' }),
    step({ id: 'complete_metadata', label: 'Complete Metadata', state: 'current' }),
    step({ id: 'review_evidence', label: 'Review Evidence', state: 'reopened', reopened: true, reason: REOPENED_REASON }),
    step({ id: 'review_export_readiness', label: 'Review Export Readiness', state: 'reopened', reopened: true, reason: REOPENED_REASON }),
    step({ id: 'export', label: 'Export', state: 'completed' }),
  ],
  current_step: 'complete_metadata',
  record_rev: 12,
};

// A never-started record: complete_metadata current, later steps blocked.
const BLOCKED_WORKFLOW: ApiWorkflow = {
  ordered_steps: [
    step({ id: 'load_record', label: 'Load Record', state: 'completed' }),
    step({ id: 'complete_metadata', label: 'Complete Metadata', state: 'current' }),
    step({ id: 'review_evidence', label: 'Review Evidence', state: 'blocked', blocked: true, reason: "Complete 'Complete Metadata' first." }),
    step({ id: 'review_export_readiness', label: 'Review Export Readiness', state: 'blocked', blocked: true, reason: "Complete 'Complete Metadata' first." }),
    step({ id: 'export', label: 'Export', state: 'blocked', blocked: true, reason: "Complete 'Complete Metadata' first." }),
  ],
  current_step: 'complete_metadata',
  record_rev: 0,
};

describe('P28.1 · WorkflowSpine renders the backend workflow verbatim', () => {
  it('renders exactly the backend ordered_steps, in that order', () => {
    const { container } = renderSpine(BLOCKED_WORKFLOW, 'demo');
    const labels = Array.from(container.querySelectorAll('li.spine-step .spine-label')).map(
      (el) => el.textContent,
    );
    expect(labels).toEqual([
      'Load Record',
      'Complete Metadata',
      'Review Evidence',
      'Review Export Readiness',
      'Export',
    ]);
  });

  it('reads the prop verbatim: a re-ordered / trimmed workflow renders in THAT order', () => {
    // A deliberately non-canonical order + subset. If the component re-derived a
    // fixed order internally, this would not match.
    const custom: ApiWorkflow = {
      ordered_steps: [
        step({ id: 'export', label: 'Export', state: 'current' }),
        step({ id: 'load_record', label: 'Load Record', state: 'completed' }),
      ],
      current_step: 'export',
      record_rev: 1,
    };
    const { container } = renderSpine(custom, 'demo');
    const labels = Array.from(container.querySelectorAll('li.spine-step .spine-label')).map(
      (el) => el.textContent,
    );
    expect(labels).toEqual(['Export', 'Load Record']);
  });

  it('a completed step renders as a navigable link to its route', () => {
    const { container } = renderSpine(MIXED_WORKFLOW, 'demo');
    const load = stepLi(container, 'Load Record');
    const link = load.querySelector('a.spine-step-link');
    expect(link).not.toBeNull();
    expect(link!.getAttribute('href')).toBe('/record/demo');
  });

  it('the current step gets aria-current="step"', () => {
    const { container } = renderSpine(MIXED_WORKFLOW, 'demo');
    const current = stepLi(container, 'Complete Metadata');
    expect(current.getAttribute('aria-current')).toBe('step');
    // no other step claims aria-current
    const others = Array.from(container.querySelectorAll('li.spine-step')).filter(
      (el) => el !== current,
    );
    for (const el of others) expect(el.getAttribute('aria-current')).toBeNull();
  });

  it('a blocked step is non-navigable and aria-disabled', () => {
    const { container } = renderSpine(BLOCKED_WORKFLOW, 'demo');
    const blocked = stepLi(container, 'Export');
    expect(blocked.querySelector('a')).toBeNull();
    expect(blocked.getAttribute('aria-disabled')).toBe('true');
  });

  it('a reopened step is visually distinct from a blocked one (class + reason text)', () => {
    const reopened = stepLi(renderSpine(MIXED_WORKFLOW, 'demo').container, 'Review Evidence');
    const blocked = stepLi(renderSpine(BLOCKED_WORKFLOW, 'demo').container, 'Review Evidence');

    // Distinct CSS state class — never styled identically.
    expect(reopened.className).toContain('reopened');
    expect(reopened.className).not.toContain('blocked');
    expect(blocked.className).toContain('blocked');
    expect(blocked.className).not.toContain('reopened');

    // Distinct, non-color text (never color-only): the reopened reason vs the
    // blocked reason are different human strings.
    expect(reopened.querySelector('.spine-meta')?.textContent).toBe(REOPENED_REASON);
    expect(blocked.querySelector('.spine-meta')?.textContent).toContain("Complete 'Complete Metadata' first.");
    expect(reopened.querySelector('.spine-meta')?.textContent).not.toBe(
      blocked.querySelector('.spine-meta')?.textContent,
    );
  });

  it('neither imports nor re-derives a local step order / active step', () => {
    // The component source must not carry the retired frontend-only model
    // (buildSpine / a hardcoded `active` derivation of completion). It reads the
    // backend prop only. (A canonical skeleton for the loading state is allowed —
    // it carries labels only, never a derived completion/active step.)
    const sources = import.meta.glob('../components/WorkflowSpine.tsx', {
      query: '?raw',
      import: 'default',
      eager: true,
    }) as Record<string, string>;
    const src = Object.values(sources)[0];
    expect(src).not.toMatch(/buildSpine/);
    expect(src).not.toMatch(/\bactiveIndex\b/);
  });
});
