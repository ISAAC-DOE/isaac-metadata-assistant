import { describe, it, expect, afterEach, vi } from 'vitest';
import type { ReactNode } from 'react';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { WorkflowSpine } from '../components/WorkflowSpine';
import {
  bundleRoutes,
  evidenceBundleRoutes,
  exportReadyRoutes,
  fixtureWorkflow,
  stubFetchDown,
  stubFetchRoutes,
} from '../test/apiFixtures';

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
    // The Historical Import guide renders synchronously (no fetch) and mounts the brand.
    // (It was `/load`, which redirects to My Experiments since 2026-11-16.)
    const { container } = renderAt('/imports');
    const brand = container.querySelector('a.brand');
    expect(brand).not.toBeNull();
    expect(brand!.getAttribute('href')).toBe('/experiments');
  });

  /*
   * INVERTED 2026-10-12. This asserted /load's one-crumb top bar — a leaf crumb and
   * no left navigation, which left the brand mark as the page's only way out. /load
   * (and the not-found page) now carry the SAME chrome as every other screen, so the
   * no-dead-ends property this describe exists for is asserted directly: the primary
   * navigation is present, no item claims to be the current page (no nav destination
   * matches /load), and Help is in reach. The retired `.breadcrumb` crumb is absent.
   */
  /* 2026-11-16: `/load` redirects, so the not-found page — the other screen that is not a
     nav destination — carries this property now. */
  it('the not-found page carries the shared chrome: primary navigation with no item current, and Help', () => {
    const { container, getByRole } = renderAt('/no-such-place');
    const nav = getByRole('navigation', { name: 'Primary' });
    expect(nav.querySelectorAll('a').length).toBeGreaterThanOrEqual(4);
    expect(nav.querySelector('[aria-current]')).toBeNull();
    expect(getByRole('button', { name: 'Help' })).toBeInTheDocument();
    expect(container.querySelector('.breadcrumb')).toBeNull();
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

  it('WorkflowSpine: completed steps link to their routes; the current step links + is aria-current', () => {
    // Ready-to-export: everything before Export is completed; Export is current.
    const wf = fixtureWorkflow({ pending_count: 0, draft_ok: true, ready: true, exported: false, rev: 3 });
    const { container } = renderSpine(<WorkflowSpine workflow={wf} recordId="demo" />);

    expect(
      stepLi(container, 'Record Created').querySelector('a.spine-step-link')?.getAttribute('href'),
    ).toBe('/record/demo');
    expect(
      stepLi(container, 'Complete Metadata').querySelector('a.spine-step-link')?.getAttribute('href'),
    ).toBe('/record/demo/complete');
    expect(
      stepLi(container, 'Review Evidence').querySelector('a.spine-step-link')?.getAttribute('href'),
    ).toBe('/record/demo/evidence');
    expect(
      stepLi(container, 'Review Export Readiness').querySelector('a.spine-step-link')?.getAttribute('href'),
    ).toBe('/record/demo/export');

    // Export is the current step: navigable AND marked aria-current="step".
    const exportStep = stepLi(container, 'Export');
    expect(exportStep.querySelector('a.spine-step-link')?.getAttribute('href')).toBe('/record/demo/export');
    expect(exportStep.getAttribute('aria-current')).toBe('step');
  });

  it('WorkflowSpine: the current step links to its route; blocked future steps do not', () => {
    // needs_attention: Complete Metadata current, everything after it blocked.
    const wf = fixtureWorkflow({ pending_count: 5, draft_ok: false, ready: false, exported: false, rev: 3 });
    const { container } = renderSpine(<WorkflowSpine workflow={wf} recordId="demo" />);

    const complete = stepLi(container, 'Complete Metadata');
    expect(complete.querySelector('a.spine-step-link')?.getAttribute('href')).toBe('/record/demo/complete');
    expect(complete.getAttribute('aria-current')).toBe('step');

    // Export is blocked (a prerequisite is unmet) — non-navigable + aria-disabled.
    const exportStep = stepLi(container, 'Export');
    expect(exportStep.querySelector('a')).toBeNull();
    expect(exportStep.getAttribute('aria-disabled')).toBe('true');
  });

  it('WorkflowSpine: with no record id, no step is navigable', () => {
    const wf = fixtureWorkflow({ pending_count: 0, draft_ok: true, ready: true, exported: false, rev: 3 });
    const { container } = renderSpine(<WorkflowSpine workflow={wf} />);
    expect(container.querySelector('a.spine-step-link')).toBeNull();
  });

  it('Review Record spine (record home): the completed Record Created step links back to /record/:id', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { container, findByText } = renderAt('/record/demo');
    await findByText('5 Fields Need Your Confirmation');
    // load_record is always completed and links to /record/demo (self / hub).
    const load = stepLi(container, 'Record Created');
    expect(load.querySelector('a.spine-step-link')?.getAttribute('href')).toBe('/record/demo');
  });
});

describe('P23B · breadcrumb is a real link during loading/error, not just once loaded', () => {
  it('S6 Ready to Export: the breadcrumb links back to Review Record while the bundle is still loading', async () => {
    stubFetchRoutes(exportReadyRoutes('demo'));
    // assert synchronously, before the stubbed fetch promises resolve — this is
    // the loading branch's TopBar, not the loaded one.
    const { container, getByText, findByText } = renderAt('/record/demo/export');
    expect(
      getByText('Loading the export checks…'),
    ).toBeInTheDocument();
    const back = container.querySelector('a.record-title-link');
    expect(back).not.toBeNull();
    expect(back!.getAttribute('href')).toBe('/record/demo');
    // let the stubbed fetch settle so the effect update happens inside act()
    await findByText('Export Official Record + Sidecar');
  });

  it('S6 Ready to Export: the breadcrumb still links back to Review Record when the backend is down', async () => {
    stubFetchDown();
    const { container, findByText } = renderAt('/record/demo/export');
    await findByText('ISAAC Is Not Running');
    const back = container.querySelector('a.record-title-link');
    expect(back).not.toBeNull();
    expect(back!.getAttribute('href')).toBe('/record/demo');
  });

  it('S4 Complete: the breadcrumb links back to Review Record while the bundle is still loading', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { container, getByText, findByText } = renderAt('/record/demo/complete');
    expect(getByText('Loading the open questions…')).toBeInTheDocument();
    const back = container.querySelector('a.record-title-link');
    expect(back).not.toBeNull();
    expect(back!.getAttribute('href')).toBe('/record/demo');
    // let the stubbed fetch settle so the effect update happens inside act()
    await findByText('Answer 5 Questions to Finish This Record');
  });

  it('S5 Evidence: the breadcrumb links back to Review Record while the bundle is still loading', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { container, getByText, findByText } = renderAt('/record/demo/evidence');
    expect(getByText('Loading the evidence trail…')).toBeInTheDocument();
    const back = container.querySelector('a.record-title-link');
    expect(back).not.toBeNull();
    expect(back!.getAttribute('href')).toBe('/record/demo');
    // let the stubbed fetch settle so the effect update happens inside act()
    await findByText('Direct Fields');
  });

  it('S3 Review Record (hub): the loading branch has no ancestor link — it IS the record home, matching the loaded state', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { container, getByText, findByText } = renderAt('/record/demo');
    expect(getByText('Loading the record…')).toBeInTheDocument();
    expect(container.querySelector('a.record-title-link')).toBeNull();
    // let the stubbed fetch settle so the effect update happens inside act()
    await findByText('5 Fields Need Your Confirmation');
  });
});
