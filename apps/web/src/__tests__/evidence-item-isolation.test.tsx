/**
 * ONE unreadable evidence item must degrade to ITSELF — not to the whole screen.
 *
 * THE DEFECT, AS MEASURED ON `77820bf`. This app has NO ErrorBoundary anywhere
 * (`main.tsx` renders `<App/>` bare), so anything that throws during render
 * unmounts the entire tree. Four different one-item malformations were driven
 * through this exact route and the observed result recorded:
 *
 *   | one appended bad entry            | measured result                          |
 *   |-----------------------------------|------------------------------------------|
 *   | `source_type: 'instrument_log'`   | React "Element type is invalid" at        |
 *   |                                   | `EvidenceTrailPanel.tsx:128` → EMPTY DOM  |
 *   | `evidence: 7`                     | threw inside `getEvidenceBundle`, bundle  |
 *   |                                   | rejected → "Backend Not Running" alert    |
 *   | `evidence: { … }`                 | same as above                             |
 *   | `path: null`                      | `TypeError: … reading 'includes'` in      |
 *   |                                   | `evidenceEntriesToTrail` → EMPTY DOM      |
 *
 * Three of the four are silent, total blanking; the fourth accuses the SERVER of
 * being down because of one field in one record. Each case below asserts the
 * three valid fixture entries still render, the bad one renders AS unavailable,
 * and no placeholder value or citation is invented for it.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { evidenceEntriesToTrail, provenanceFor } from '../lib/adapt';
import { evidenceBundleRoutes, evidenceExported, stubFetchRoutes } from '../test/apiFixtures';
import type { ApiEvidenceEntry } from '../lib/types';

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

/** The three good fixture entries plus ONE bad one, served from /evidence. */
function routesWithBadEntry(bad: unknown) {
  const routes = evidenceBundleRoutes('demo');
  routes['GET /api/experiments/demo/evidence'] = {
    body: { evidence: [...evidenceExported.evidence, bad] },
  };
  return routes;
}

/** The keys of the three valid fixture entries, in the order they are served. */
const VALID_KEYS = evidenceExported.evidence.map((e) => e.path);

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('Evidence trail · one bad item degrades to itself', () => {
  const cases: Array<{
    name: string;
    bad: Record<string, unknown>;
    key: string;
    /**
     * Whether the entry is UNREADABLE (an error state) as opposed to merely
     * unfamiliar. An unknown source type is well-formed data — it crashed the
     * screen, but it is not a malformation, and badging it "unavailable" would
     * be this fix inventing a defect in the reader's record.
     */
    unavailable: boolean;
  }> = [
    {
      name: 'a source type this build does not enumerate',
      bad: {
        path: 'system.instrument_log_ref',
        value: 'LOG-9',
        status: 'verified',
        evidence: [{ source_type: 'instrument_log', locator: 'line 4' }],
      },
      key: 'system.instrument_log_ref',
      unavailable: false,
    },
    {
      name: 'evidence that is not a list at all',
      bad: { path: 'system.broken_number', value: 'x', status: 'verified', evidence: 7 },
      key: 'system.broken_number',
      unavailable: true,
    },
    {
      name: 'evidence that is an object, not a list',
      bad: {
        path: 'system.broken_object',
        value: 'x',
        status: 'verified',
        evidence: { source_type: 'spreadsheet' },
      },
      key: 'system.broken_object',
      unavailable: true,
    },
    {
      name: 'a list member that is not an evidence object',
      bad: {
        path: 'system.broken_member',
        value: 'x',
        status: 'verified',
        evidence: ['spreadsheet'],
      },
      key: 'system.broken_member',
      unavailable: true,
    },
    {
      name: 'the backend already marked it unavailable',
      bad: {
        path: 'system.facility.beamline',
        value: null,
        status: 'unavailable',
        evidence: [],
        unavailable: true,
        unavailable_reason: 'the stored evidence for this entry is a number, not a list of evidence entries',
      },
      key: 'system.facility.beamline',
      unavailable: true,
    },
  ];

  for (const { name, bad, key, unavailable } of cases) {
    it(`renders every valid entry and an error state for the bad one: ${name}`, async () => {
      stubFetchRoutes(routesWithBadEntry(bad));
      const { container, findByText, getByText } = renderAt('/record/demo/evidence');

      // 1. The screen LOADED. (Three of these cases used to reach zero DOM, and
      //    one reached the "Backend Not Running" alert — assert against both.)
      expect(await findByText('Direct Fields')).toBeInTheDocument();
      expect(container.querySelector('[role="alert"]')).toBeNull();
      expect(container.textContent).not.toMatch(/Backend Not Running/i);

      // 2. Every VALID entry is still listed, unharmed.
      for (const validKey of VALID_KEYS) {
        expect(getByText(validKey, { selector: '.trail-key' })).toBeInTheDocument();
      }

      // 3. The bad entry is STILL VISIBLE, under its own key — not dropped, not
      //    hidden, not silently skipped.
      const row = getByText(key, { selector: '.trail-key' }).closest('button')!;
      expect(row).not.toBeNull();
      // An UNREADABLE entry says so in text on the row itself; an unfamiliar but
      // well-formed one is a normal entry and must NOT be badged as broken.
      if (unavailable) {
        expect(row.textContent).toContain('unavailable');
      } else {
        expect(row.textContent).not.toContain('unavailable');
      }
    });
  }

  it('an unknown source type is shown verbatim, never renamed to a known one', () => {
    // The fallback GLYPH must not become a fallback MEANING. The stored string is
    // the only honest thing to print next to it.
    const [entry] = evidenceEntriesToTrail([
      {
        path: 'a.b',
        value: 'x',
        status: 'verified',
        evidence: [{ source_type: 'instrument_log' }],
      } as unknown as ApiEvidenceEntry,
    ]);
    expect(entry.sourceTypes).toEqual(['instrument_log']);
    expect(provenanceFor(entry)).toContain('instrument_log');
    // Not silently coerced into one of the seven types the icon map knows.
    expect(provenanceFor(entry)).not.toMatch(/spreadsheet|file_listing/);
  });

  it('states the real cause and never a generic failure, and invents nothing', async () => {
    const reason =
      'the stored evidence for this entry is a number, not a list of evidence entries';
    stubFetchRoutes(
      routesWithBadEntry({
        path: 'system.facility.beamline',
        value: null,
        status: 'unavailable',
        evidence: [],
        unavailable: true,
        unavailable_reason: reason,
      }),
    );
    const { container, findByText, getByText } = renderAt('/record/demo/evidence');
    await findByText('Direct Fields');

    fireEvent.click(getByText('system.facility.beamline', { selector: '.trail-key' }));

    const detail = container.querySelector('.sidecar-entry')!;
    const note = within(detail as HTMLElement).getByText(/Evidence unavailable for this entry/i);
    // It is a note, not decoration — the state is exposed, not just drawn.
    expect(note).toHaveAttribute('role', 'note');
    // Truthful about WHAT failed and WHY — the backend's own reason, verbatim.
    expect(note.textContent).toContain(reason);
    expect(note.textContent).toMatch(/unavailable/i);
    // Not a generic shrug that hides a distinguishable cause.
    expect(note.textContent).not.toMatch(/something went wrong|unknown error/i);
    // And NOT the pre-existing "No citations recorded", which is a claim about
    // the record and is false when the citations merely could not be read.
    expect(detail.textContent).not.toContain('No citations recorded.');
    // Nothing is drawn in place of what failed.
    expect(container.querySelector('.sidecar-ev')).toBeNull();
  });

  it('does not badge an entry that honestly carries no citation', () => {
    // Crying wolf on every uncited field would be its own honesty defect.
    const [entry] = evidenceEntriesToTrail([
      { path: 'a.b', value: 'x', status: 'verified', evidence: [] },
    ]);
    expect(entry.unavailable).toBeUndefined();
    expect(provenanceFor(entry)).toBe('This entry carries no citation.');
  });

  it('keeps the readable half of a partially readable entry AND says what it lost', () => {
    const [entry] = evidenceEntriesToTrail([
      {
        path: 'a.b',
        value: 'x',
        status: 'verified',
        evidence: [{ source_type: 'spreadsheet', source_file: 'c.csv' }, 'junk'],
      } as unknown as ApiEvidenceEntry,
    ]);
    expect(entry.evidence).toEqual([{ source_type: 'spreadsheet', source_file: 'c.csv' }]);
    expect(entry.unavailable).toBe(true);
    // The provenance sentence describes what IS shown, then discloses the rest —
    // it must not read as a complete provenance.
    expect(provenanceFor(entry)).toMatch(/campaign spreadsheet/);
    expect(provenanceFor(entry)).toMatch(/unavailable/i);
  });

  it('names an entry whose path is not even a string by its position', () => {
    // Identity is what makes a failure actionable: a scientist has to be able to
    // find the offending item. Position is the only identity such an entry has.
    const [entry] = evidenceEntriesToTrail([
      { path: null, value: 'x', status: 'verified', evidence: [] } as unknown as ApiEvidenceEntry,
    ]);
    expect(entry.key).toContain('entry 1');
    expect(entry.unavailable).toBe(true);
    expect(entry.unavailableReason).toMatch(/path is not a string/);
  });

  it('survives a whole /evidence payload that is not an array', () => {
    // The bundle-level analogue on the client. It must not throw; the SCREEN's
    // own honest empty state then takes over.
    expect(evidenceEntriesToTrail(undefined as unknown as ApiEvidenceEntry[])).toEqual([]);
  });
});
