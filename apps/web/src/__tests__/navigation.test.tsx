import { describe, it, expect, afterEach, vi } from 'vitest';
import type { ReactNode } from 'react';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { WorkflowSpine, buildSpine } from '../components/WorkflowSpine';
import { bundleRoutes, evidenceBundleRoutes, stubFetchRoutes } from '../test/apiFixtures';

function renderAt(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

function renderSpine(ui: ReactNode) {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      {ui}
    </MemoryRouter>,
  );
}

/** The <li> for a spine step, found by its rendered label. */
function stepLi(container: HTMLElement, label: string): HTMLElement {
  const items = Array.from(container.querySelectorAll('li.spine-step')) as HTMLElement[];
  const li = items.find((el) => el.querySelector('.spine-label')?.textContent === label);
  if (!li) throw new Error(`spine step "${label}" not found`);
  return li;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('P22B · navigation / no dead ends', () => {
  it('the brand mark is a real link to My Experiments (/experiments)', () => {
    // /load renders synchronously (no fetch) and mounts the brand + breadcrumb chrome.
    const { container } = renderAt('/load');
    const brand = container.querySelector('a.brand');
    expect(brand).not.toBeNull();
    expect(brand!.getAttribute('href')).toBe('/experiments');
  });

  it('the breadcrumb leaf crumb is non-link text marked aria-current="page"', () => {
    const { container } = renderAt('/load');
    const crumb = container.querySelector('.breadcrumb');
    expect(crumb).not.toBeNull();
    expect(crumb!.tagName).toBe('SPAN'); // leaf, not a link
    expect(crumb!.getAttribute('aria-current')).toBe('page');
  });

  it('Evidence Trail deep-link renders an explicit return link to /record/:id + a current leaf crumb', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { container, findByText } = renderAt('/record/demo/evidence');
    await findByText('Direct Fields');

    // Ancestor crumb: a real react-router link back to Review Record, so it works
    // even on a direct deep-link into /record/demo/evidence.
    const back = container.querySelector('a.record-title-link');
    expect(back).not.toBeNull();
    expect(back!.getAttribute('href')).toBe('/record/demo');

    // Leaf crumb: the current sub-surface, non-link, marked as the current page.
    const leaf = container.querySelector('.record-surface');
    expect(leaf).not.toBeNull();
    expect(leaf!.tagName).toBe('SPAN');
    expect(leaf!.getAttribute('aria-current')).toBe('page');
  });

  it('WorkflowSpine: done and active steps are links to their routes; locked steps are not', () => {
    // Exported record: draft/complete/export = done, validate = active (no route),
    // audit = locked.
    const { container } = renderSpine(<WorkflowSpine steps={buildSpine('validate')} recordId="demo" />);

    expect(stepLi(container, 'Draft').querySelector('a.spine-step-link')?.getAttribute('href')).toBe(
      '/record/demo',
    );
    expect(
      stepLi(container, 'Complete').querySelector('a.spine-step-link')?.getAttribute('href'),
    ).toBe('/record/demo/complete');
    expect(
      stepLi(container, 'Export').querySelector('a.spine-step-link')?.getAttribute('href'),
    ).toBe('/record/demo/export');

    // Validate is active but has no standalone route — never a link.
    const validate = stepLi(container, 'Validate');
    expect(validate.querySelector('a')).toBeNull();
    expect(validate.getAttribute('aria-current')).toBe('step');

    // Audit is locked — not a link, semantically disabled, not focusable as an action.
    const audit = stepLi(container, 'Audit');
    expect(audit.querySelector('a')).toBeNull();
    expect(audit.getAttribute('aria-disabled')).toBe('true');
  });

  it('WorkflowSpine: an active step with a route links to it; locked future steps do not', () => {
    // draft = done, complete = active, export/validate/audit = locked.
    const { container } = renderSpine(<WorkflowSpine steps={buildSpine('complete')} recordId="demo" />);

    expect(
      stepLi(container, 'Complete').querySelector('a.spine-step-link')?.getAttribute('href'),
    ).toBe('/record/demo/complete');

    // Export has a route but is a locked future gate — must NOT be a link (gating).
    const exportStep = stepLi(container, 'Export');
    expect(exportStep.querySelector('a')).toBeNull();
    expect(exportStep.getAttribute('aria-disabled')).toBe('true');
  });

  it('WorkflowSpine: with no record id, no step is navigable', () => {
    const { container } = renderSpine(<WorkflowSpine steps={buildSpine('validate')} />);
    expect(container.querySelector('a.spine-step-link')).toBeNull();
  });

  it('Review Record spine (record home): the done/active draft step links back to /record/:id', async () => {
    // Exported demo: draft is done and links home from the record workbench itself.
    stubFetchRoutes(bundleRoutes('demo'));
    const { container, findByText } = renderAt('/record/demo');
    await findByText('5 Fields Need Your Confirmation');
    // The draft step links to /record/demo (self / hub), never a dead disc.
    const draft = stepLi(container, 'Draft');
    // draft is active (not exported fixture) -> active step with a route is a link.
    expect(draft.querySelector('a.spine-step-link')?.getAttribute('href')).toBe('/record/demo');
  });
});
