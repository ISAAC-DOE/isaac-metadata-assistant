/*
 * THE RECORD-LEVEL WRITE INVENTORY FOLLOWS THE SERVED CONTRACT.
 *
 * ── WHAT THIS FILE ASSERTS, AND WHAT IT DELIBERATELY DOES NOT ────────────────
 *
 * `record-description.test.tsx` opens by saying the path set *"is NOT asserted here,
 * deliberately … this file could only compare the panel against a literal it also owns,
 * which passes against any set at all"*, and points at
 * `apps/api/tests/test_record_campaign_fields.py` — which regex-parses
 * `lib/recordFields.ts` and compares the declared literal to
 * `routes._record_writable_fields()`. **That reasoning is right and that guard is not
 * replaced by anything here.** It answers "is the declared set the CORRECT set?", which
 * is a cross-language question and cannot be settled from inside `vitest`.
 *
 * THIS FILE ANSWERS A DIFFERENT QUESTION THE PYTHON GUARD CANNOT SEE: *does the screen
 * FOLLOW what the server serves, or does it render a list of its own?* That is
 * answerable here without owning any literal, because the server's answer arrives in the
 * fixture and the assertion is that the rendering EQUALS it — for three different served
 * sets, two of which disagree with the declared list. A hardcoded inventory satisfies at
 * most one of the three, so it cannot pass by coincidence, and it fails the moment the
 * contract widens or narrows.
 *
 * ── THE CONTRACT ────────────────────────────────────────────────────────────
 *
 * `GET /api/experiments/{id}/draft` returns `capture.record_writable` on every field
 * row. It is `routes.capture_facts` reading `_record_writable_fields()` — the identical
 * expression the two record-level write operations gate on.
 *
 * NOT `record_writable_field_paths` (served on `GET .../notes`), and the difference is
 * measured rather than stylistic: that key is the INTERSECTION with the note-mappable
 * paths and holds 13 where the routes accept 14. The one it drops is `system.domain` —
 * absent from `EXTRACTOR_FIELD_MAP`, so not a note's target, but record-writable and one
 * of the two closed enums this panel offers a picker for. `THE_SERVED_FACTS` below
 * encodes that 14-vs-13 difference, and one test pins it, so a future slice that
 * "simplifies" the derivation onto the notes key removes a working control loudly.
 *
 * ── PROVENANCE OF THE FIXTURE ───────────────────────────────────────────────
 *
 * `THE_SERVED_FACTS` is TRANSCRIBED from `routes.capture_facts` over the 26 paths
 * `GET /draft` skeletons, run against this tree's vendored schema — not invented here.
 * `choices` is deliberately NOT transcribed: the two enum lists are read from the
 * official schema JSON this test imports, for the same reason the panel reads them from
 * `GET /api/schema` rather than holding a copy.
 *
 * Everything is synthetic: stubbed routes, a fixture record, no network.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { RecordDescriptionPanel } from '../components/RecordDescriptionPanel';
import {
  RECORD_FIELDS,
  derivedRecordFieldSpec,
  offeredRecordFields,
  servedRecordWritablePaths,
} from '../lib/recordFields';
import type { ApiDraftResponse, DraftFieldCapture } from '../lib/types';
import {
  EXP_ID,
  VERSION_FIELDS,
  experimentDetail,
  runsPage,
  stubFetchRoutes,
  type RouteEntry,
} from '../test/apiFixtures';
import officialSchema from '../../../../schema/isaac_record_v1.json';

const BASE = `/api/experiments/${EXP_ID}`;

/**
 * One row of the transcription: the three writability booleans and the classification,
 * per path, exactly as `routes.capture_facts` reported them over this tree's schema.
 *
 * `R` is `record_writable`, `F` is `run_field_writable`, `O` is `run_overridable`.
 */
type Row = { R: boolean; F: boolean; O: boolean; level: DraftFieldCapture['level']; open?: string };

const THE_SERVED_FACTS: Record<string, Row> = {
  'context.environment': { R: false, F: true, O: false, level: 'run' },
  'context.temperature_K': { R: false, F: true, O: false, level: 'run' },
  'context.thermodynamics.atmosphere': { R: false, F: true, O: false, level: 'run' },
  'sample.composition.CuO2_mass_fraction': {
    R: true, F: false, O: true, level: 'experiment', open: 'sample.composition',
  },
  'sample.composition.sucrose_mass_fraction': {
    R: true, F: false, O: true, level: 'experiment', open: 'sample.composition',
  },
  'sample.geometry.pellet_diameter_mm': { R: true, F: false, O: true, level: 'experiment' },
  'sample.material.formula': { R: true, F: false, O: true, level: 'experiment' },
  'sample.material.name': { R: true, F: false, O: true, level: 'experiment' },
  'sample.material.provenance': { R: true, F: false, O: true, level: 'experiment' },
  'sample.sample_form': { R: true, F: false, O: true, level: 'experiment' },
  'system.configuration.detector_model': {
    R: false, F: false, O: false, level: 'unclassified', open: 'system.configuration',
  },
  'system.configuration.monochromator_crystal': {
    R: false, F: false, O: false, level: 'unclassified', open: 'system.configuration',
  },
  'system.configuration.n_scans': {
    R: false, F: false, O: false, level: 'unclassified', open: 'system.configuration',
  },
  'system.configuration.proposal_id': {
    R: false, F: false, O: false, level: 'unclassified', open: 'system.configuration',
  },
  'system.configuration.session_id': {
    R: false, F: false, O: false, level: 'unclassified', open: 'system.configuration',
  },
  'system.configuration.spectrometer_geometry': {
    R: false, F: false, O: false, level: 'unclassified', open: 'system.configuration',
  },
  'system.domain': { R: true, F: false, O: false, level: 'experiment' },
  'system.facility.beamline': { R: true, F: false, O: true, level: 'experiment' },
  'system.facility.endstation': { R: true, F: false, O: true, level: 'experiment' },
  'system.facility.facility_name': { R: true, F: false, O: true, level: 'experiment' },
  'system.facility.organization': { R: true, F: false, O: true, level: 'experiment' },
  'system.facility.site': { R: true, F: false, O: true, level: 'experiment' },
  'system.technique': { R: true, F: false, O: true, level: 'experiment' },
  'timestamps.acquired_end_utc': { R: false, F: true, O: false, level: 'run' },
  'timestamps.acquired_start_utc': { R: false, F: true, O: false, level: 'run' },
  'timestamps.created_utc': { R: false, F: false, O: false, level: 'unclassified' },
};

/** The paths the transcription says a RECORD-level operation accepts. Derived, not listed. */
const RECORD_WRITABLE = Object.keys(THE_SERVED_FACTS)
  .filter((path) => THE_SERVED_FACTS[path].R)
  .sort();

/**
 * The six paths whose scope is an OPEN SCIENTIFIC QUESTION for Angel, plus the one the
 * exporter stamps. `CLAUDE.md` §15 records the six as `unclassified, verified`; no
 * surface may offer a box for any of the seven, because every write route refuses them.
 */
const NO_ROUTE_ACCEPTS = Object.keys(THE_SERVED_FACTS)
  .filter((path) => THE_SERVED_FACTS[path].level === 'unclassified')
  .sort();

/** The schema's own closed set for a path, READ rather than transcribed. */
function schemaChoices(path: string): string[] | null {
  let node: unknown = officialSchema;
  for (const segment of path.split('.')) {
    const properties = (node as { properties?: Record<string, unknown> } | null)?.properties;
    if (!properties || !(segment in properties)) return null;
    node = properties[segment];
  }
  const values = (node as { enum?: unknown }).enum;
  return Array.isArray(values) ? (values as string[]) : null;
}

/**
 * A draft response carrying the served capture facts.
 *
 * `overrides` lets one test widen or narrow the served set without touching the rest,
 * which is what makes the negative controls negative.
 */
function draftWithCapture(
  overrides: Record<string, boolean | undefined> = {},
  options: { stored?: Record<string, unknown>; omitCapture?: boolean } = {},
): ApiDraftResponse {
  const paths = [...new Set([...Object.keys(THE_SERVED_FACTS), ...Object.keys(overrides)])].sort();
  const fields = paths
    .filter((path) => overrides[path] !== undefined || path in THE_SERVED_FACTS)
    .map((path) => {
      const row = THE_SERVED_FACTS[path] ?? { R: false, F: false, O: false, level: null };
      const writable = overrides[path] ?? row.R;
      const capture: DraftFieldCapture = {
        level: row.level,
        record_writable: writable,
        run_field_writable: row.F,
        run_overridable: row.O,
        choices: writable ? schemaChoices(path) : null,
        open_namespace: row.open ?? null,
      };
      const value = options.stored?.[path];
      return {
        path,
        label: path.split('.').slice(-1)[0],
        value: value === undefined ? null : value,
        status: (value === undefined ? 'missing' : 'verified') as 'missing' | 'verified',
        evidence_count: value === undefined ? 0 : 1,
        source_types: [] as never[],
        present: value !== undefined,
        ...(options.omitCapture ? {} : { capture }),
      };
    });
  return {
    // ONE GROUP. The panel's own sections come from `RECORD_FIELD_GROUPS`, not from the
    // draft's grouping, so the draft's shape here is deliberately not load-bearing.
    groups: [{ title: 'All', fields }],
    record_blocks: { 'block:attribution': { contributors: [] }, 'block:tags': null },
  } as unknown as ApiDraftResponse;
}

const SCHEMA_ROUTE: Record<string, RouteEntry> = {
  'GET /api/schema': {
    body: {
      schema_title: 'ISAAC record',
      schema_version: '1.05',
      schema: officialSchema,
      vocabularies: {},
    },
  },
};

function routes(
  draft: ApiDraftResponse,
  extra: Record<string, RouteEntry> = {},
): Record<string, RouteEntry> {
  return {
    [`GET ${BASE}`]: { body: { ...experimentDetail, id: EXP_ID } },
    [`GET ${BASE}/draft`]: { body: draft },
    [`GET ${BASE}/runs`]: { body: runsPage([]) },
    ...SCHEMA_ROUTE,
    ...extra,
  };
}

async function open(draft: ApiDraftResponse, extra: Record<string, RouteEntry> = {}) {
  stubFetchRoutes(routes(draft, extra));
  render(<RecordDescriptionPanel experimentId={EXP_ID} />);
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /Record Description/ }));
  });
  await screen.findByRole('button', { name: /Save record description/ });
}

/**
 * The form control this screen offers for one official path, found BY ROLE.
 *
 * NOT by CSS class and NOT by a label this test computed — either would make the
 * assertion agree with the implementation by construction. The control is located
 * through its own `aria-describedby`, i.e. through the description a screen reader would
 * actually be given, which is the element that names the path. So a control that is not
 * described, or is described by something that does not name its path, is not found —
 * which is the correct outcome for an unlabelled box.
 */
function controlForPath(path: string): HTMLElement | undefined {
  const controls = [
    ...screen.queryAllByRole('textbox'),
    ...screen.queryAllByRole('combobox'),
  ];
  return controls.find((control) => {
    const described = (control.getAttribute('aria-describedby') ?? '').split(/\s+/);
    return described.some((id) => {
      const node = id ? document.getElementById(id) : null;
      // EXACT segment match, not `includes`: `system.facility.site` must not be found by
      // a hint that happens to mention a longer path containing it.
      return (node?.textContent ?? '').split(/\s|·/).some((token) => token.trim() === path);
    });
  });
}

const ACCEPTED = {
  body: {
    ...VERSION_FIELDS,
    version: '1.1',
    pending: [],
    pending_page: {
      total: 0, returned: 0, offset: 0, limit: 50,
      withheld: 0, complete: true, run_id: null, record_total: 0,
    },
    status: 'in_review',
    workflow: experimentDetail.workflow,
    invalidation: {
      changed: true, rev: 4, changed_fields: [],
      reopened_steps: [], artifact: { state: 'none', reason: null }, reason: null,
    },
  },
};

function postCall(suffix: 'answers' | 'edit') {
  const stub = globalThis.fetch as unknown as { mock: { calls: [string, RequestInit][] } };
  return stub.mock.calls.find(
    ([url, init]) => init?.method === 'POST' && String(url).endsWith(`/${suffix}`),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the offered inventory is derived from the served contract', () => {
  it('offers an accessible input for every path the server reports record-writable', async () => {
    await open(draftWithCapture());

    // The transcription is not empty and is not everything — otherwise the assertions
    // below could pass over a degenerate set.
    expect(RECORD_WRITABLE.length).toBe(14);
    expect(RECORD_WRITABLE.length).toBeLessThan(Object.keys(THE_SERVED_FACTS).length);

    for (const path of RECORD_WRITABLE) {
      const control = controlForPath(path);
      expect(control, `no accessible control for ${path}`).toBeTruthy();
      // A BOX WITH NO NAME IS NOT AN INPUT A PERSON CAN USE. Asserted per path rather
      // than once, because the two enum paths render a different element from the twelve.
      expect(control).toHaveAccessibleName(expect.stringMatching(/\S/) as unknown as string);
      expect((control as HTMLElement).tagName).toMatch(/^(INPUT|SELECT)$/);
    }
  });

  it('renders a box for the twelve free-text paths, not only the two closed enums', async () => {
    await open(draftWithCapture());
    const freeText = RECORD_WRITABLE.filter((path) => schemaChoices(path) === null);
    // TWELVE, and the number is derived from the schema rather than asserted about it.
    expect(freeText).toHaveLength(12);
    for (const path of freeText) {
      const control = controlForPath(path);
      expect(control, `no text box for ${path}`).toBeTruthy();
      expect((control as HTMLElement).tagName).toBe('INPUT');
    }
    for (const path of RECORD_WRITABLE.filter((p) => schemaChoices(p) !== null)) {
      expect((controlForPath(path) as HTMLElement).tagName).toBe('SELECT');
    }
  });

  it('NEGATIVE CONTROL — a path the contract GAINS is offered, with an accessible name', async () => {
    // A path no version of this build declares. `RECORD_FIELDS` cannot contain it, so a
    // screen rendering the declared list fails here and only a derived one passes.
    const GAINED = 'sample.material.purity';
    expect(RECORD_FIELDS.some((spec) => spec.path === GAINED)).toBe(false);

    await open(draftWithCapture({ [GAINED]: true }));

    const control = controlForPath(GAINED);
    expect(control, 'the widened contract was not followed').toBeTruthy();
    expect(control).toHaveAccessibleName('Purity');
    // AND IT IS SOMEWHERE A READER CAN FIND IT, under a real legend rather than loose.
    expect(screen.getByRole('group', { name: 'Sample' })).toContainElement(control!);
  });

  it('NEGATIVE CONTROL — a path the contract LOSES is not offered at all', async () => {
    const LOST = 'system.facility.beamline';
    expect(RECORD_FIELDS.some((spec) => spec.path === LOST)).toBe(true);

    await open(draftWithCapture({ [LOST]: false }));

    // A control the routes would refuse is worse than an absent one — `CLAUDE.md` §11's
    // "a panel told the scientist to enter a value on 25 fields, and 7 accept none".
    expect(controlForPath(LOST)).toBeUndefined();
    // AND EVERY OTHER PATH SURVIVES, so this is a narrowing and not a blank screen.
    for (const path of RECORD_WRITABLE.filter((p) => p !== LOST)) {
      expect(controlForPath(path), `${path} disappeared too`).toBeTruthy();
    }
  });

  it('equals the served set exactly over three different contracts, so a stale list cannot pass', () => {
    const declared = new Set(RECORD_FIELDS.map((spec) => spec.path));
    const cases: Record<string, boolean>[] = [
      {},
      { 'sample.material.purity': true },
      { 'system.facility.beamline': false, 'system.technique': false },
    ];
    const seen: string[][] = [];
    for (const override of cases) {
      const draft = draftWithCapture(override);
      const served = new Set(servedRecordWritablePaths(draft).paths);
      const offered = offeredRecordFields(draft);
      expect(offered.served).toBe(true);
      expect(new Set(offered.fields.map((spec) => spec.path))).toEqual(served);
      seen.push([...served].sort());
    }
    // THE THREE CONTRACTS REALLY DIFFER, and two of them differ from the declared list —
    // so no single fixed list satisfies all three, which is what makes this a proof
    // rather than a restatement.
    expect(new Set(seen.map((s) => s.join('|'))).size).toBe(3);
    expect(seen.filter((s) => s.join('|') === [...declared].sort().join('|'))).toHaveLength(1);
  });

  it('names a gained path from its own last segment and nothing else', () => {
    expect(derivedRecordFieldSpec('sample.material.purity')).toEqual({
      path: 'sample.material.purity',
      label: 'Purity',
      group: 'sample',
    });
    expect(derivedRecordFieldSpec('system.facility.hutch').group).toBe('facility');
    // A path outside every known namespace still gets somewhere to live rather than
    // being dropped, which is the whole point of the fourth group.
    expect(derivedRecordFieldSpec('measurement.beam_size_um')).toEqual({
      path: 'measurement.beam_size_um',
      label: 'Beam size um',
      group: 'other',
    });
  });

  it('follows the DRAFT contract and not the notes one, which omits system.domain', async () => {
    // `record_writable_field_paths` on `GET .../notes` is the intersection with the
    // note-mappable paths: 13, dropping `system.domain`. Deriving from it would delete a
    // working picker, so this pins that `system.domain` is offered.
    await open(draftWithCapture());
    const control = controlForPath('system.domain');
    expect(control).toBeTruthy();
    expect((control as HTMLSelectElement).tagName).toBe('SELECT');
    expect(RECORD_WRITABLE).toContain('system.domain');
  });
});

describe('what must never be offered', () => {
  it('offers no box for the six system.configuration paths or timestamps.created_utc', async () => {
    await open(draftWithCapture());
    expect(NO_ROUTE_ACCEPTS).toEqual([
      'system.configuration.detector_model',
      'system.configuration.monochromator_crystal',
      'system.configuration.n_scans',
      'system.configuration.proposal_id',
      'system.configuration.session_id',
      'system.configuration.spectrometer_geometry',
      'timestamps.created_utc',
    ]);
    for (const path of NO_ROUTE_ACCEPTS) {
      expect(controlForPath(path), `${path} was offered a control`).toBeUndefined();
    }
  });

  it('offers no box for a run-level path, whose value belongs to a run', async () => {
    await open(draftWithCapture());
    for (const path of Object.keys(THE_SERVED_FACTS).filter(
      (p) => THE_SERVED_FACTS[p].level === 'run',
    )) {
      expect(controlForPath(path), `${path} was offered on the record`).toBeUndefined();
    }
  });

  it('offers nothing, and says so, when the server reports no record-writable field', async () => {
    // The server's own fail-closed answer: `_record_writable_fields()` is empty whenever
    // the vendored schema cannot be read, and every write is then `unrecognized_field`.
    const none = Object.fromEntries(Object.keys(THE_SERVED_FACTS).map((p) => [p, false]));
    await open(draftWithCapture(none));
    for (const path of RECORD_WRITABLE) expect(controlForPath(path)).toBeUndefined();
    expect(
      screen.getByText(/reports no record-level field it will accept a value at/i),
    ).toBeInTheDocument();
    // AND NO EMPTY SECTION IS LEFT STANDING OVER NOTHING.
    expect(screen.queryByRole('group', { name: 'Facility' })).toBeNull();
  });

  it('discloses the fallback when the server said nothing about capture at all', async () => {
    // "Said false" and "said nothing" are different claims — the same distinction
    // `serialize._UNKNOWN_CAPTURE` draws with `level: null`.
    await open(draftWithCapture({}, { omitCapture: true }));
    expect(screen.getByText(/did not say which fields it accepts a value at/i)).toBeInTheDocument();
    // The declared list is still offered, so a contract skew does not blank the screen.
    for (const spec of RECORD_FIELDS) expect(controlForPath(spec.path)).toBeTruthy();
  });
});

describe('writing a value through the record\'s own operations', () => {
  it('persists a valid value through /answers with the record\'s If-Match, and says it saved', async () => {
    await open(draftWithCapture(), { [`POST ${BASE}/answers`]: ACCEPTED });

    const box = controlForPath('sample.material.name') as HTMLInputElement;
    fireEvent.change(box, { target: { value: 'Synthetic pellet A' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Save record description/ }));
    });

    const call = postCall('answers');
    expect(call, 'no POST to /answers was made').toBeTruthy();
    expect(JSON.parse(String(call![1].body)).answers).toEqual({
      'sample.material.name': 'Synthetic pellet A',
    });
    // THE RECORD'S OWN VERSION, quoted as an ETag exactly as `api.ts:1021` sends it —
    // asserted in that form rather than unquoted, because `If-Match: ""` is malformed
    // (400) and the quoting is part of what "preserves CAS" means here.
    expect((call![1].headers as Record<string, string>)['If-Match']).toBe(
      `"${experimentDetail.version}"`,
    );
    // NOT /edit — the record holds nothing here, and the server refuses the wrong side.
    expect(postCall('edit')).toBeUndefined();
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(/Saved 1 value to this record/i);
    });
  });

  it('routes a value the record already holds to /edit instead', async () => {
    await open(
      draftWithCapture({}, { stored: { 'sample.material.name': 'Old name' } }),
      { [`POST ${BASE}/edit`]: ACCEPTED },
    );
    const box = controlForPath('sample.material.name') as HTMLInputElement;
    expect(box.value).toBe('Old name');
    fireEvent.change(box, { target: { value: 'New name' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Save record description/ }));
    });
    expect(JSON.parse(String(postCall('edit')![1].body)).answers).toEqual({
      'sample.material.name': 'New name',
    });
    expect(postCall('answers')).toBeUndefined();
  });

  it('reports an invalid value truthfully — at the field, in a summary, and keeps what was typed', async () => {
    await open(draftWithCapture(), {
      [`POST ${BASE}/answers`]: {
        status: 422,
        body: {
          error: 'invalid_field_value',
          experiment_id: EXP_ID,
          key: 'sample.material.name',
          keys: ['sample.material.name'],
          expected_types: { 'sample.material.name': 'string' },
          message:
            'Nothing was written: any value the record already held for these fields is unchanged.',
        },
      },
    });

    const box = controlForPath('sample.material.name') as HTMLInputElement;
    fireEvent.change(box, { target: { value: 'a value the server refuses' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Save record description/ }));
    });

    // AT THE FIELD: the control is marked invalid and describes its own error.
    await waitFor(() => expect(box).toHaveAttribute('aria-invalid', 'true'));
    const describedBy = (box.getAttribute('aria-describedby') ?? '').split(/\s+/);
    const errorText = describedBy
      .map((id) => (id ? document.getElementById(id)?.textContent ?? '' : ''))
      .join(' ');
    expect(errorText).toMatch(/string/);

    // AND IN AN ACCESSIBLE SUMMARY that links to the control by its own id.
    const summary = screen.getByRole('alert');
    const link = within(summary).getByRole('link', { name: 'Material name' });
    expect(link.getAttribute('href')).toBe(`#${box.id}`);

    // NOTHING CLAIMS A SAVE. `role="status"` must not read as success.
    expect(screen.getByRole('status')).not.toHaveTextContent(/Saved/i);
    // AND THE TYPED TEXT SURVIVES the refusal — the reader retypes nothing.
    expect(box.value).toBe('a value the server refuses');
  });

  it('does not clobber on a stale write — nothing written, the conflict named, the text kept', async () => {
    await open(draftWithCapture(), {
      [`POST ${BASE}/answers`]: {
        status: 412,
        body: { error: 'stale_write', current_version: '9.9' },
      },
    });

    const box = controlForPath('sample.material.name') as HTMLInputElement;
    fireEvent.change(box, { target: { value: 'typed while someone else edited' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Save record description/ }));
    });

    await waitFor(() => {
      expect(screen.getByText(/changed somewhere else while you were editing/i)).toBeInTheDocument();
    });
    // EXACTLY ONE ATTEMPT. A silent retry against a fresh version is the clobber.
    const stub = globalThis.fetch as unknown as { mock: { calls: [string, RequestInit][] } };
    expect(
      stub.mock.calls.filter(([url, init]) => init?.method === 'POST' && String(url).endsWith('/answers')),
    ).toHaveLength(1);
    expect(postCall('edit')).toBeUndefined();
    // NOTHING WAS WRITTEN AND NOTHING WAS LOST.
    expect(box.value).toBe('typed while someone else edited');
    expect(screen.getByRole('status')).not.toHaveTextContent(/Saved \d/i);
    expect(screen.getByRole('button', { name: /Save record description/ })).toBeDisabled();
  });
});
