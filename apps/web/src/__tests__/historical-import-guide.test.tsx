/**
 * HISTORICAL IMPORT IS THE SKILL'S GUIDE, AND THE CUT SURFACES REDIRECT (2026-11-16).
 *
 * `/imports` no longer runs an import in the browser: historical import is done by the
 * Claude Code skill on the scientist's computer, and this page says how. Pinned here:
 *   1. the guide renders, in the Historical Import nav slot, with every section;
 *   2. the install and run commands are on it, each copyable, and every `scripts/…` it
 *      names exists in this repository (a command that is not there is the worst thing
 *      a how-to can print);
 *   3. old `/imports?import=…&stage=…` links land on the guide, never a 404;
 *   4. `/load` redirects to My Experiments, and `/memory` does too unless the developer
 *      flag (`VITE_ISAAC_DEV_TOOLS=1`) is on;
 *   5. the copy states facts: none of the retired standing disclaimers comes back.
 */
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { AppRoutes } from '../App';
import { LABELS } from '../lib/labels';
import { GUIDE_COMMANDS, GUIDE_COPY } from '../lib/historicalImportGuide';
import { stubFetchDown } from '../test/apiFixtures';

/** The repository root, from `apps/web` (vitest's cwd). */
const REPO = resolve(process.cwd(), '../..');

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>;
}

function renderAt(path: string) {
  stubFetchDown();
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppRoutes />
      <LocationProbe />
    </MemoryRouter>,
  );
}

const at = () => screen.getByTestId('location').textContent;

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('the Historical Import guide', () => {
  it('renders at /imports, under its own nav item, with every section', () => {
    renderAt('/imports');
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(LABELS.navImports);
    const nav = screen.getByRole('navigation', { name: 'Primary' });
    const current = within(nav).getByRole('link', { current: 'page' });
    expect(current.textContent).toBe(LABELS.navImports);
    for (const title of [
      GUIDE_COPY.whatTitle,
      GUIDE_COPY.getTitle,
      GUIDE_COPY.installTitle,
      GUIDE_COPY.runTitle,
      GUIDE_COPY.stepsTitle,
      GUIDE_COPY.dataTitle,
      GUIDE_COPY.askedTitle,
      GUIDE_COPY.knowTitle,
      GUIDE_COPY.browserTitle,
      GUIDE_COPY.troubleTitle,
    ]) {
      expect(screen.getByRole('region', { name: title }), title).toBeTruthy();
    }
    expect(screen.getByRole('region', { name: GUIDE_COPY.stepsTitle }).querySelectorAll('li')).toHaveLength(8);
    expect(screen.getByText(GUIDE_COPY.troubleElse)).toBeTruthy();
  });

  it('shows the install, self-test, check and run commands, each with a copy button', () => {
    renderAt('/imports');
    const shown = [...document.querySelectorAll('code.hig-cmd-text')].map((el) => el.textContent);
    for (const command of Object.values(GUIDE_COMMANDS)) {
      expect(shown, command).toContain(command);
    }
    expect(screen.getByRole('button', { name: 'Copy the install command' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Copy the self-test command' })).toBeTruthy();
    // Install comes before the self-test, which comes before the run.
    const order = [GUIDE_COMMANDS.install, GUIDE_COMMANDS.selftest, GUIDE_COMMANDS.skill].map((c) =>
      shown.indexOf(c),
    );
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });

  it('names only scripts that exist in this repository', () => {
    renderAt('/imports');
    const scripts = new Set(
      [...document.querySelectorAll('code.hig-cmd-text')]
        .map((el) => el.textContent ?? '')
        .filter((text) => text.startsWith('scripts/'))
        .map((text) => text.split(' ')[0]),
    );
    expect(scripts.size).toBeGreaterThanOrEqual(3);
    for (const script of scripts) {
      expect(existsSync(resolve(REPO, script)), script).toBe(true);
    }
    // And the skill the page tells you to run is the one in the repository.
    expect(existsSync(resolve(REPO, '.claude/skills/isaac-historical-import/SKILL.md'))).toBe(true);
    expect(GUIDE_COMMANDS.skill).toBe('/isaac-historical-import');
  });

  it('lays out where data goes as a table with row headers', () => {
    renderAt('/imports');
    const table = screen.getByRole('table', { name: GUIDE_COPY.dataCaption });
    expect(within(table).getAllByRole('rowheader').map((th) => th.textContent)).toEqual(
      GUIDE_COPY.dataRows.map((row) => row.what),
    );
    expect(table.textContent).toContain('Claude service');
    expect(table.textContent).toContain('Nothing is uploaded unless you upload it.');
  });

  it('offers no import control: nothing on the page uploads, starts or reads a file', () => {
    renderAt('/imports');
    const main = screen.getByRole('main');
    expect(main.querySelector('input, form, textarea, select')).toBeNull();
    const buttons = within(main).queryAllByRole('button').map((b) => b.getAttribute('aria-label') ?? b.textContent);
    expect(buttons.every((name) => /^Copy /.test(name ?? '')), buttons.join(' | ')).toBe(true);
  });

  it('states facts: no retired standing disclaimer returns', () => {
    renderAt('/imports');
    const text = screen.getByRole('main').textContent ?? '';
    for (const retired of [/this build/i, /prototype/i, /\bdemo\b/i, /synthetic-only/i, /local[- ]first/i, /never uploads/i]) {
      expect(text, String(retired)).not.toMatch(retired);
    }
  });
});

describe('old links and cut surfaces land somewhere sensible', () => {
  it('an old /imports?import=…&stage=… link lands on the guide, with the stale parameters dropped', () => {
    renderAt('/imports?import=01OLDIMPORT0000000000000000&stage=review');
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(LABELS.navImports);
    expect(at()).toBe('/imports');
    expect(screen.queryByRole('heading', { name: LABELS.screenNotFound })).toBeNull();
  });

  it('a bare ?stage= link lands on the guide too', () => {
    renderAt('/imports?stage=sources');
    expect(at()).toBe('/imports');
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(LABELS.navImports);
  });

  it('/load redirects to My Experiments', () => {
    renderAt('/load');
    expect(at()).toBe('/experiments');
  });

  it('/memory redirects to My Experiments without the developer flag', () => {
    renderAt('/memory');
    expect(at()).toBe('/experiments');
  });

  it('/memory?concept=… redirects as well (an assistant or search link from before)', () => {
    renderAt('/memory?concept=concept-provenance');
    expect(at()).toBe('/experiments');
  });

  it('/memory stays Project Memory with VITE_ISAAC_DEV_TOOLS=1', () => {
    vi.stubEnv('VITE_ISAAC_DEV_TOOLS', '1');
    renderAt('/memory');
    expect(at()).toBe('/memory');
  });
});
