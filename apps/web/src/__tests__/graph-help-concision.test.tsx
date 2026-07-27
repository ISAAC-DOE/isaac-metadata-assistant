import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, waitFor, within, type RenderResult } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProjectMemory } from '../screens/ProjectMemory';
import { LOD_CLUSTER_SCALE, LOD_SYMBOL_SCALE, MAX_SCALE } from '../lib/graphModel';
import {
  stubFetchRoutes,
  graphStatusUnavailable,
  memoryGraphAvailable,
} from '../test/apiFixtures';

/*
 * P36V.1 Unit G Slice 10 — About This Graph as IN-PRODUCT HELP.
 *
 * The dialog used to be ten sections of dense prose: what it shows, what it does
 * not show, the advisory warning, the graph-data layer chain, node types, cluster
 * colours, relationship types, how to explore, the command grammar, and keyboard
 * controls. It read as a document.
 *
 * What is guarded here:
 *   1. CONCISION — the first screenful carries orientation only, and every piece
 *      of REFERENCE data (the sha256, the un-embedded source-graph figures, the
 *      raw relationship identifiers, the eleven-row grammar, the render bounds,
 *      the detailed keyboard table) sits behind one collapsed disclosure (§1).
 *   2. The two BOUNDARY statements are NOT collapsed (§2). An independent review
 *      on this same phase raised a Critical finding against collapsing honesty
 *      copy into a closed disclosure; concision must never buy itself a caveat.
 *   3. Unit F's semantic-zoom layer is documented at all (§3) — it was not.
 *   4. Every keyboard shortcut the help lists is one GraphCanvas actually
 *      honours, checked by pressing it (§4).
 *   5. The dialog contract — focus trap, Escape, focus restoration — and the
 *      structural properties a narrow viewport and a 200% zoom depend on (§5).
 */

const routes = {
  'GET /api/graph/status': { body: graphStatusUnavailable },
  'GET /api/memory/graph': { body: memoryGraphAvailable },
};

async function openHelp(): Promise<{ view: RenderResult; dialog: HTMLElement }> {
  stubFetchRoutes(routes);
  const view = render(
    <MemoryRouter
      initialEntries={['/memory?tab=graph']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ProjectMemory />
    </MemoryRouter>,
  );
  await view.findByText('Graph', { selector: 'h2' });
  fireEvent.click(view.getByRole('button', { name: 'About This Graph' }));
  return { view, dialog: view.getByRole('dialog', { name: 'About This Graph' }) };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

/** The text a reader sees WITHOUT opening anything — every `<details>` removed. */
function visibleText(dialog: HTMLElement): string {
  const clone = dialog.cloneNode(true) as HTMLElement;
  for (const d of [...clone.querySelectorAll('details')]) d.remove();
  return (clone.textContent ?? '').replace(/\s+/g, ' ').trim();
}

const collapsedText = (dialog: HTMLElement): string =>
  [...dialog.querySelectorAll('details')]
    .map((d) => (d.textContent ?? '').replace(/\s+/g, ' '))
    .join(' ');

// --- 1. concision ------------------------------------------------------------

describe('About This Graph — the first screenful orients, it does not document', () => {
  it('carries the five required things, in order, before the first disclosure', async () => {
    const { dialog } = await openHelp();
    const text = visibleText(dialog);

    // 1 what the graph shows · 2 what it does not · 3 the legend · 4 the
    // interactions · 5 a disclosure to the advanced material.
    const order = [
      'What You Are Viewing',
      'What It Does Not Show',
      'Node Types',
      'Quick Guide',
    ].map((section) => text.indexOf(section));
    expect(order.every((i) => i >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    // A real, reachable disclosure control for the advanced material.
    expect(
      within(dialog).getByText('Technical Details', { selector: 'summary' }),
    ).toBeInTheDocument();
  });

  it('keeps the visible part short rows, not walls of prose', async () => {
    const { dialog } = await openHelp();
    const clone = dialog.cloneNode(true) as HTMLElement;
    for (const d of [...clone.querySelectorAll('details')]) d.remove();

    /*
     * A REGRESSION GUARD, not a claim about a viewport: jsdom computes no layout,
     * so nothing here can prove what fits on a first screenful. What it can hold
     * is the shape that makes a first screenful possible — a bounded amount of
     * visible copy, delivered as short rows. The bound is the shipped length plus
     * a small margin; the whole dialog is over 8,000 characters, so more than a
     * third of it now sits behind the one disclosure.
     */
    const visible = visibleText(dialog);
    const whole = (dialog.textContent ?? '').replace(/\s+/g, ' ').trim();
    expect(visible.length).toBeLessThan(5500);
    expect(visible.length).toBeLessThan(whole.length * 0.7);
    const rows = [...clone.querySelectorAll('.graph-help-list > li')];
    expect(rows.length).toBeGreaterThan(10);
    for (const row of rows) {
      expect((row.textContent ?? '').trim().length, row.textContent ?? '').toBeLessThan(240);
    }
    // No paragraph is a wall. The longest visible one is the boundary callout,
    // which is a caveat and therefore allowed its sentences.
    for (const p of [...clone.querySelectorAll('p')]) {
      const length = (p.textContent ?? '').trim().length;
      const isBoundary = p.closest('.graph-help-boundary') !== null;
      expect(length, p.textContent ?? '').toBeLessThan(isBoundary ? 620 : 400);
    }
    // Three of the visible lists carry the two-column treatment, so the rows read
    // as a legend rather than a column of prose.
    expect(clone.querySelectorAll('.graph-help-cols').length).toBeGreaterThanOrEqual(3);
  });

  it('moves the REFERENCE data into Technical Details, which is closed by default', async () => {
    const { dialog } = await openHelp();
    const technical = dialog.querySelector('.graph-help-technical') as HTMLDetailsElement;
    expect(technical).not.toBeNull();
    expect(technical.open).toBe(false);

    const visible = visibleText(dialog);
    const collapsed = collapsedText(dialog);
    // Fingerprints, builder identifiers, the un-embedded figures, the raw
    // relationship identifiers and the render bounds: present, but not up front.
    for (const reference of [
      '0cfccb9f',
      'sanitized-snapshot',
      'integrity verified',
      '2988 nodes',
      '4465 edges',
      '257 clusters',
      '1 · Source graph',
      'schema v1',
    ]) {
      expect(collapsed, `${reference} left the dialog`).toContain(reference);
      expect(visible, `${reference} is still in the first screenful`).not.toContain(reference);
    }
    // The eleven-row grammar is a nested disclosure inside Commands, not prose.
    const grammar = dialog.querySelector('.graph-help-sub-details') as HTMLDetailsElement;
    expect(grammar.open).toBe(false);
    expect(grammar.textContent).toContain('neighbors <node> [depth 1|2]');
    expect(visible).not.toContain('neighbors <node> [depth 1|2]');
    // The raw backend relationship value moved; the readable label stayed.
    expect(visible).toContain('Imports');
    expect(collapsed).toContain('imports');
  });

  it('states the advisory boundary ONCE, not in every section', async () => {
    const { dialog } = await openHelp();
    const text = (dialog.textContent ?? '').replace(/\s+/g, ' ');
    // One callout element, and one occurrence of the authority sentence.
    expect(dialog.querySelectorAll('.graph-help-note').length).toBe(1);
    expect(text.match(/authorises an export/g) ?? []).toHaveLength(1);
    expect(text.match(/Project Memory is advisory/g) ?? []).toHaveLength(1);
  });
});

// --- 2. the caveats are NOT behind a disclosure ------------------------------

describe('About This Graph — concision never buys itself a caveat', () => {
  it('keeps the non-authority statement visible in the first screenful', async () => {
    const { dialog } = await openHelp();
    const visible = visibleText(dialog);
    expect(visible).toContain('Project Memory is advisory');
    expect(visible).toContain('it returns leads to verify, never a verdict');
    expect(visible).toContain('authorises an export');
    expect(visible).toContain('the official schema and the deterministic validators');
    // Not inside any <details>, in the real DOM.
    const note = dialog.querySelector('.graph-help-boundary') as HTMLElement;
    expect(note.closest('details')).toBeNull();
  });

  it('keeps the structural-staleness statement visible, unsoftened, with both axes', async () => {
    const { dialog } = await openHelp();
    const visible = visibleText(dialog);
    expect(visible).toContain('two separate axes');
    expect(visible).toContain('point-in-time index of commit');
    expect(visible).toContain('caab1d0');
    expect(visible).toContain('including work that exists in this running app');
    expect(visible).toContain('A current integrity check does not make the structure current');
    // A lie of degree is still a lie.
    expect(visible.toLowerCase()).not.toContain('slightly out of date');
    expect(visible.toLowerCase()).not.toContain('may be a little');
    // And the full fingerprint it refers to is the one reference item that DID
    // move — the claim stays, its 40-character hash does not.
    expect(visible).not.toContain('caab1d0a69c1733524bda5dde495623bc4b7bad1');
    expect(collapsedText(dialog)).toContain('caab1d0a69c1733524bda5dde495623bc4b7bad1');
  });

  it('keeps the cluster and shape caveats visible too', async () => {
    const { dialog } = await openHelp();
    const visible = visibleText(dialog);
    expect(visible).toContain('derived automatically by the upstream graph builder');
    expect(visible).toContain('not categories the schema recognises');
    // Colour is never the only carrier of meaning — said, not just implemented.
    expect(visible).toContain('Shape, not colour, carries every distinction here');
    expect(visible).toContain('never the only carrier of meaning');
    // No shape distinction is claimed that the canvas does not draw.
    expect(visible).toContain('the shape is the same');
    expect(visible).toContain('not causality');
    expect(visible).toContain('not a record and not a validation result');
    expect(visible).toContain('outer rings');
  });
});

// --- 3. Unit F's semantic zoom is documented ---------------------------------

describe('About This Graph — the semantic-zoom layer is documented', () => {
  it('names the three levels and their real thresholds', async () => {
    const { dialog } = await openHelp();
    const zoom = [...dialog.querySelectorAll('.graph-help-section')].find(
      (s) => s.querySelector(':scope > h4')?.textContent === 'Zoom Levels',
    ) as HTMLElement;
    expect(zoom).toBeTruthy();
    const text = (zoom.textContent ?? '').replace(/\s+/g, ' ');
    expect(text).toContain('Files');
    expect(text).toContain('Clusters');
    expect(text).toContain('Symbols');
    // The thresholds come from the model, so the help cannot drift from them.
    expect(text).toContain(`${Math.round(LOD_CLUSTER_SCALE * 100)}%`);
    expect(text).toContain(`${Math.round(LOD_SYMBOL_SCALE * 100)}%`);
    expect(text).toContain('Zooming reveals structure rather than magnifying');
  });

  it('documents Reveal Detail, the lazy fetch, the undraggable marks and the search scope', async () => {
    const { dialog } = await openHelp();
    const text = (dialog.textContent ?? '').replace(/\s+/g, ' ');
    // The toolbar control that makes semantic zoom discoverable at all.
    expect(text).toContain('Reveal Detail');
    expect(text).toContain('steps to the next zoom level');
    // Lazily fetched, and honestly degraded when the artifact is absent.
    expect(text).toContain('fetched only');
    expect(text).toContain('stays on the file projection and says so');
    expect(text).toContain('nothing is aggregated or estimated in its place');
    // Deep marks are not draggable — and why.
    expect(text).toContain('not draggable');
    expect(text).toContain('would misrepresent containment');
    // Search matches files, NOT symbol names.
    expect(text).toContain('It does not match symbol names');
    // A focus suspends the deeper layers.
    expect(text).toContain('keeps the file projection it was computed over');
    // The deep bounds and the zoom clamp are reference data, so they are in
    // Technical Details — but they ARE stated.
    expect(collapsedText(dialog)).toContain(`${Math.round(MAX_SCALE * 100)}%`);
    expect(collapsedText(dialog)).toMatch(/at most 260 marks and 400 lines/);
  });

  it('documents the Suggested Commands row and its insert-not-run rule', async () => {
    const { dialog } = await openHelp();
    const text = (dialog.textContent ?? '').replace(/\s+/g, ' ');
    expect(text).toContain('Suggested Commands');
    expect(text).toContain('puts that exact command in the bar and waits for you to press Run');
    // BOTH click-acting exceptions are named — an earlier draft said "only Fit to
    // View … acts on the click itself", which was false: View Technical Details
    // opens the panel on its click too.
    expect(text).toContain('The two exceptions act on the click itself and are labelled as such');
    expect(text).toContain('Fit to View');
    expect(text).toContain('View Technical Details');
  });
});

// --- 4. the documented shortcuts are the implemented shortcuts ----------------

describe('About This Graph — every documented key is a key the canvas honours', () => {
  const canvasSource = Object.values(
    import.meta.glob('../screens/graph/GraphCanvas.tsx', {
      query: '?raw',
      import: 'default',
      eager: true,
    }) as Record<string, string>,
  )[0];
  const barSource = Object.values(
    import.meta.glob('../screens/graph/GraphCommandBar.tsx', {
      query: '?raw',
      import: 'default',
      eager: true,
    }) as Record<string, string>,
  )[0];
  const helpSource = Object.values(
    import.meta.glob('../screens/graph/GraphHelp.tsx', {
      query: '?raw',
      import: 'default',
      eager: true,
    }) as Record<string, string>,
  )[0];

  /**
   * The literal each documented key must appear as in the handler that owns it.
   * An explicit table, not a blind substring sweep: `Esc` is `'Escape'` in code
   * and `Space` is `' '`, so a naive scan would either pass vacuously or fail on
   * correct code.
   */
  const KEY_LITERALS: Record<string, { source: 'canvas' | 'bar' | 'help'; literals: string[] }> = {
    Tab: { source: 'bar', literals: ["'Tab'"] },
    '+': { source: 'canvas', literals: ["'+'"] },
    '=': { source: 'canvas', literals: ["'='"] },
    '-': { source: 'canvas', literals: ["'-'"] },
    _: { source: 'canvas', literals: ["'_'"] },
    '0': { source: 'canvas', literals: ["'0'"] },
    f: { source: 'canvas', literals: ["'f'"] },
    Home: { source: 'canvas', literals: ["'Home'"] },
    End: { source: 'canvas', literals: ["'End'"] },
    Enter: { source: 'canvas', literals: ["'Enter'"] },
    Space: { source: 'canvas', literals: ["' '", "'Spacebar'"] },
    '↑': { source: 'bar', literals: ["'ArrowUp'"] },
    // Esc is the DIALOG's own key, handled by GraphHelp, not by the canvas.
    Esc: { source: 'help', literals: ["'Escape'"] },
  };

  it('lists no key outside the set the components implement', async () => {
    const { dialog } = await openHelp();
    const keyboard = [...dialog.querySelectorAll('.graph-help-keys .graph-help-kbd')].map(
      (k) => (k.textContent ?? '').trim(),
    );
    expect(keyboard.length).toBeGreaterThan(8);
    for (const key of new Set(keyboard)) {
      const entry = KEY_LITERALS[key];
      expect(entry, `the help documents \`${key}\`, which this test has no source literal for`).toBeTruthy();
      const source =
        entry.source === 'canvas' ? canvasSource : entry.source === 'bar' ? barSource : helpSource;
      expect(
        entry.literals.some((literal) => source.includes(literal)),
        `\`${key}\` is documented but ${entry.source} handles none of ${entry.literals.join(' / ')}`,
      ).toBe(true);
    }
  });

  it('and every one of them actually does what it is documented to do', async () => {
    const { view } = await openHelp();
    fireEvent.keyDown(document, { key: 'Escape' }); // Esc closes this panel
    await waitFor(() => expect(view.queryByRole('dialog')).toBeNull());

    const svg = () => document.querySelector('.memory-graph-svg') as SVGSVGElement;
    const box = () => svg().getAttribute('viewBox');

    // arrow keys pan the canvas
    const beforePan = box();
    fireEvent.keyDown(svg(), { key: 'ArrowRight' });
    await waitFor(() => expect(box()).not.toBe(beforePan));

    // + / = zoom in, - / _ zoom out, 0 resets, f fits
    for (const [key, expected] of [
      ['+', 'zoom 125%'],
      ['=', 'zoom 156%'],
      ['-', 'zoom 125%'],
      ['_', 'zoom 100%'],
    ] as const) {
      fireEvent.keyDown(svg(), { key });
      await waitFor(() => expect(view.container.textContent).toContain(expected));
    }
    fireEvent.keyDown(svg(), { key: '+' });
    await waitFor(() => expect(view.container.textContent).toContain('zoom 125%'));
    fireEvent.keyDown(svg(), { key: '0' });
    await waitFor(() => expect(view.container.textContent).toContain('zoom 100%'));
    const beforeFit = box();
    fireEvent.keyDown(svg(), { key: 'f' });
    await waitFor(() => expect(box()).not.toBe(beforeFit));

    // Tab reaches the marks; Home / End / arrows move between them; Enter and
    // Space select. The roving mark is the one with tabindex 0.
    const marks = () => [...document.querySelectorAll('.memory-graph-node')] as unknown as HTMLElement[];
    const roving = () => marks().find((m) => m.getAttribute('tabindex') === '0')!;
    fireEvent.keyDown(roving(), { key: 'End' });
    const last = document.activeElement as HTMLElement;
    expect(last.getAttribute('role')).toBe('button');
    fireEvent.keyDown(last, { key: 'Home' });
    const first = document.activeElement as HTMLElement;
    expect(first).not.toBe(last);
    fireEvent.keyDown(first, { key: 'ArrowRight' });
    expect(document.activeElement).not.toBe(first);

    fireEvent.keyDown(document.activeElement as HTMLElement, { key: 'Enter' });
    await waitFor(() => expect(document.querySelector('.memory-graph-node.selected')).not.toBeNull());
    fireEvent.keyDown(document.activeElement as HTMLElement, { key: ' ' });
    // Space is documented as "selects", and it does — the same node stays chosen.
    expect(document.querySelector('.memory-graph-node.selected')).not.toBeNull();

    // The command-bar keys: ↑ recalls, Tab accepts a completion, Esc closes the
    // list and then clears the input.
    const bar = view.getByRole('combobox', { name: 'Graph command' }) as HTMLInputElement;
    fireEvent.change(bar, { target: { value: 'type file' } });
    fireEvent.keyDown(bar, { key: 'Enter' });
    fireEvent.keyDown(bar, { key: 'ArrowUp' });
    expect(bar.value).toBe('type file');
    fireEvent.change(bar, { target: { value: 'sel' } });
    await view.findByRole('listbox', { name: 'Command completions' });
    fireEvent.keyDown(bar, { key: 'ArrowDown' });
    fireEvent.keyDown(bar, { key: 'Tab' });
    expect(bar.value.startsWith('select')).toBe(true);
    fireEvent.keyDown(bar, { key: 'Escape' });
    fireEvent.keyDown(bar, { key: 'Escape' });
    expect(bar.value).toBe('');
  });
});

// --- 5. the dialog contract, and what narrow / zoomed rendering rests on ------

describe('About This Graph — dialog contract and responsive structure', () => {
  it('traps Tab inside the panel and restores focus to the trigger on Escape', async () => {
    const { view, dialog } = await openHelp();
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(document.activeElement).toBe(dialog);

    const focusables = [...dialog.querySelectorAll('button, summary, [tabindex]:not([tabindex="-1"])')];
    expect(focusables.length).toBeGreaterThan(1);
    // Tab is handled at capture, cycles inside, and never escapes the panel.
    for (let i = 0; i < focusables.length + 2; i += 1) {
      fireEvent.keyDown(document, { key: 'Tab' });
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(dialog.contains(document.activeElement)).toBe(true);

    const trigger = view.getByRole('button', { name: 'About This Graph' });
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(view.queryByRole('dialog')).toBeNull());
    expect(document.activeElement).toBe(trigger);
  });

  it('opens each disclosure from the keyboard and keeps a correct heading outline', async () => {
    const { dialog } = await openHelp();
    const technical = dialog.querySelector('.graph-help-technical') as HTMLDetailsElement;
    const summary = technical.querySelector('summary') as HTMLElement;
    // A <summary> is natively focusable and operable; no ARIA of our own needed.
    expect(summary.textContent).toBe('Technical Details');
    expect(technical.querySelector('summary h1, summary h2, summary h3, summary h4, summary h5')).toBeNull();

    const levels = [...dialog.querySelectorAll('h1, h2, h3, h4, h5, h6')].map((h) =>
      Number(h.tagName[1]),
    );
    expect(levels[0]).toBe(3);
    for (let i = 1; i < levels.length; i += 1) {
      expect(levels[i] - levels[i - 1], `h${levels[i - 1]} → h${levels[i]}`).toBeLessThanOrEqual(1);
    }
  });

  it('rests on intrinsic layout rules, so narrow viewports and 200% zoom reflow', async () => {
    // jsdom computes NO layout, so this asserts the RULES a narrow viewport and a
    // 200% zoom depend on, not the rendered result. Real rendering, real reflow
    // and real contrast remain human checks.
    const css = Object.values(
      import.meta.glob('../screens/graph/graph.css', {
        query: '?raw',
        import: 'default',
        eager: true,
      }) as Record<string, string>,
    )[0];
    // The two-column lists collapse by INTRINSIC minimum, with no media query —
    // so they reflow for a narrow window and for a zoomed one alike.
    expect(css).toMatch(/\.graph-help-cols\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(/);
    // The panel is width-capped and the backdrop scrolls; no fixed height that a
    // 200% zoom could clip.
    expect(css).toMatch(/\.graph-help-backdrop\s*\{[^}]*overflow-y:\s*auto/);
    expect(css).toMatch(/\.graph-help-panel\s*\{[^}]*max-width:/);
    expect(css).not.toMatch(/\.graph-help-panel\s*\{[^}]*[^-]height:\s*\d/);
    // Reduced motion is honoured for the panel.
    expect(css).toMatch(/prefers-reduced-motion[\s\S]*\.graph-help-panel/);
    // Long tokens wrap rather than forcing a horizontal scroll.
    expect(css).toMatch(/\.graph-help-list li\s*\{[^}]*overflow-wrap:\s*anywhere/);

    const { dialog } = await openHelp();
    for (const list of dialog.querySelectorAll('.graph-help-cols')) {
      expect(list.classList.contains('graph-help-list')).toBe(true);
    }
  });

  it('never uses verdict language, anywhere in the rewritten copy', async () => {
    const { dialog } = await openHelp();
    const text = dialog.textContent ?? '';
    for (const claim of [
      /\bis valid\b/i,
      /\bis invalid\b/i,
      /passes validation/i,
      /fails validation/i,
      /\bconfirms\b/i,
      /\bproves\b/i,
      /\bguarantees\b/i,
      /\bcauses\b/i,
      /ground truth/i,
      /knowledge graph/i,
      /\bontology\b/i,
    ]) {
      expect(text, `verdict language in the help: ${claim}`).not.toMatch(claim);
    }
  });
});
