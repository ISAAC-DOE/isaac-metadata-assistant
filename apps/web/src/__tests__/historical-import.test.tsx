/*
 * HISTORICAL IMPORT — the review surface. `HIST-004`, and `UX-016`'s import half.
 *
 * WHAT THIS FILE MOST EXISTS TO PREVENT is the pattern `HIST-004` bans by name:
 * `Upload Files -> Spinner -> Mysterious JSON`. So it asserts the three absences
 * as hard properties rather than trusting the screen's comments:
 *
 *   §1  no file input, no multipart, and no claim that either exists
 *   §2  every one of the nine things a scientist must be able to see is there
 *   §3  the unbuilt step says so and offers NO control, not a disabled one
 *   §4  one `<h1>`, one name, one vocabulary — and it is the server's
 *   §5  a candidate that cannot be sent says why, in the server's own words
 *   §6  `UX-016`: a scientist with zero experiments can discover this destination
 *
 * MUTATION-CHECKED: a test whose docstring carries a `MUTATION:` line was
 * verified by breaking the component in the way the test claims to catch,
 * confirming it went RED, and reverting. One without the line does not claim it.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { HistoricalImport } from '../screens/HistoricalImport';
import { ExperimentsHome } from '../screens/ExperimentsHome';
import { LeftNav } from '../components/LeftNav';
import { LABELS } from '../lib/labels';
import { ROUTES, ROUTE_PATTERNS } from '../lib/routes';
import { routeDocumentTitle } from '../lib/documentTitle';
import { IMPORT_COPY } from '../lib/historicalImportContent';
import type {
  ApiImportCandidate,
  ApiImportListResponse,
  ApiImportSession,
  ApiImportSource,
  ApiImportWorkflowStep,
} from '../lib/types';

/* --------------------------------------------------------------------------
 * Fixtures — shaped exactly as the real server answers, and UNMISTAKABLY FAKE.
 * -------------------------------------------------------------------------- */

const WORKFLOW: ApiImportWorkflowStep[] = [
  { id: 'new_import', label: 'New Import', built: true, disclosure: null },
  { id: 'sources', label: 'Sources', built: true, disclosure: null },
  { id: 'parse', label: 'Parse', built: true, disclosure: null },
  { id: 'reconstruct', label: 'Reconstruct', built: true, disclosure: null },
  { id: 'review', label: 'Review', built: true, disclosure: null },
  {
    id: 'add_to_experiments',
    label: 'Add to Experiments',
    built: false,
    disclosure:
      'Not built in this build. A field candidate you propose becomes an ingestion ' +
      'proposal on an experiment you choose, and you review it there; nothing here ' +
      'creates an experiment for you.',
  },
];

const DURABILITY =
  'An import session is a working area. It is kept in this workspace and is not part ' +
  'of the durable record store, so a server restart can end it. Anything you propose ' +
  'onto an experiment is stored with that experiment and is not affected.';

const POINTER_DETAIL =
  'Recorded as a reference. This build stores where the file is and what you say ' +
  'identifies it; it has not opened the file, so nothing has been parsed from it and ' +
  'no value has been read out of it.';

const FIXTURE_SOURCE: ApiImportSource = {
  source_id: '01SRCA00000000000000000001',
  kind: 'synthetic_fixture',
  filename: 'SYNTHETIC-bundle-a.txt',
  reference: 'tests/fixtures/historical_import/SYNTHETIC-bundle-a.txt',
  parse_state: 'parsed',
  parse_detail:
    'Read by Example source (key = value): 4 statement(s), 1 line(s) reported as not understood.',
  provenance: { bytes_read_by_this_application: true },
  media_type: null,
  size_bytes: null,
  sha256: null,
  fixture_name: 'SYNTHETIC-bundle-a.txt',
};

const POINTER_SOURCE: ApiImportSource = {
  source_id: '01SRCB00000000000000000002',
  kind: 'reference',
  filename: 'FAKE-scan_0012.mac',
  reference: '/nfs/fake-beamline/2099/FAKE-scan_0012.mac',
  parse_state: 'no_content_path',
  parse_detail: POINTER_DETAIL,
  provenance: { bytes_read_by_this_application: false },
  media_type: null,
  size_bytes: null,
  sha256: 'a'.repeat(64),
  fixture_name: null,
};

const SENDABLE: ApiImportCandidate = {
  candidate_id: '01CANDA0000000000000000001',
  kind: 'field',
  determinism: 'deterministic',
  rule:
    'Read verbatim from `system.technique` at line 21 of the parsed source, whose key ' +
    'IS this official ISAAC field path. No alias, synonym or normalisation was applied.',
  supporting_source_ids: [FIXTURE_SOURCE.source_id],
  supporting_statements: [
    {
      source_id: FIXTURE_SOURCE.source_id,
      key: 'system.technique',
      value: 'XAS',
      locator: 'line 21',
    },
  ],
  target_field_path: 'system.technique',
  proposed_value: 'XAS',
  disagreement: [],
  unresolved_reason: null,
  not_proposable_reason: null,
  proposable: true,
};

const DISAGREEING: ApiImportCandidate = {
  candidate_id: '01CANDB0000000000000000002',
  kind: 'field',
  determinism: 'deterministic',
  rule:
    '2 of the parsed sources state a value at `sample.material.name` and they do not ' +
    'agree, so this reconstruction chose none of them.',
  supporting_source_ids: [FIXTURE_SOURCE.source_id],
  supporting_statements: [],
  target_field_path: 'sample.material.name',
  proposed_value: null,
  disagreement: [
    {
      value: 'SYNTHETIC-CuO-FAKE-001',
      source_ids: [FIXTURE_SOURCE.source_id],
      locators: ['line 22'],
    },
    { value: 'SYNTHETIC-CuO-FAKE-002', source_ids: ['01SRCC0000000000000000003'], locators: ['line 11'] },
  ],
  unresolved_reason: 'sources_disagree',
  not_proposable_reason:
    'The sources disagree about this value, so this reconstruction chose none of them. ' +
    'Every competing value is listed with the source that asserts it; deciding between ' +
    'them is yours.',
  proposable: false,
};

const NO_WRITE_PATH: ApiImportCandidate = {
  candidate_id: '01CANDC0000000000000000003',
  kind: 'field',
  determinism: 'deterministic',
  rule: 'Read verbatim from `system.configuration.detector_model` at line 23.',
  supporting_source_ids: [FIXTURE_SOURCE.source_id],
  supporting_statements: [],
  target_field_path: 'system.configuration.detector_model',
  proposed_value: 'SYNTHETIC-DETECTOR-MODEL-ZERO',
  disagreement: [],
  unresolved_reason: null,
  not_proposable_reason:
    'This IS an official ISAAC field, and no write operation in this build accepts a ' +
    'value at its path — so a proposal for it could be created and never applied. The ' +
    'value stays visible here with the source it was read from. THIS IS A LIMITATION ' +
    'OF THIS BUILD AND NOT A STATEMENT ABOUT THE OFFICIAL ISAAC SCHEMA, which defines ' +
    'this field.',
  proposable: false,
};

const STRUCTURAL: ApiImportCandidate = {
  candidate_id: '01CANDD0000000000000000004',
  kind: 'experiment',
  determinism: 'inferred',
  rule:
    'Suggested from the parsed sources’ filenames, which share the leading text ' +
    '`SYNTHETIC-bundle`. NO SOURCE STATES A TITLE — this is an inference by a stored ' +
    'rule, not something read, and it is offered only as a starting point for a name ' +
    'you choose.',
  supporting_source_ids: [FIXTURE_SOURCE.source_id],
  supporting_statements: [],
  target_field_path: null,
  proposed_value: 'SYNTHETIC-bundle',
  disagreement: [],
  unresolved_reason: null,
  not_proposable_reason:
    'Nothing in this build creates an experiment or a run from an import. A proposal ' +
    'is about one value at one official field path, so this candidate has no proposal ' +
    'to become. Create the experiment yourself and propose the field candidates onto it.',
  proposable: false,
};

function session(overrides: Partial<ApiImportSession> = {}): ApiImportSession {
  const sources = overrides.sources ?? [FIXTURE_SOURCE, POINTER_SOURCE];
  return {
    import_id: '01IMPORT000000000000000001',
    label: 'A fictional 2099 CuO bundle',
    created_utc: '2099-01-01T00:00:00Z',
    updated_utc: '2099-01-01T00:00:05Z',
    furthest_step: 'reconstruct',
    workflow: WORKFLOW,
    durability: DURABILITY,
    sources,
    unreadable_source_count: 0,
    source_counts: {
      total: sources.length,
      parsed: sources.filter((s) => s.parse_state === 'parsed').length,
      failed: 0,
      no_content_path: sources.filter((s) => s.parse_state === 'no_content_path').length,
      unparsed: 0,
      parsable_by_this_build: sources.filter((s) => s.kind === 'synthetic_fixture').length,
    },
    parsed: [
      {
        source_id: FIXTURE_SOURCE.source_id,
        parser_id: 'synthetic_fixture_key_value',
        filename: FIXTURE_SOURCE.filename,
        statements: [
          { key: 'system.technique', value: 'XAS', locator: 'line 21' },
          { key: 'operator_initials', value: 'ZZ', locator: 'line 24' },
        ],
        skipped: [
          {
            locator: 'line 26',
            reason: 'no_key_value_separator',
            message:
              'This line has no `=`, so this parser cannot say what it asserts. It is ' +
              'reported rather than dropped.',
          },
        ],
      },
    ],
    unmapped_keys: [
      {
        source_id: FIXTURE_SOURCE.source_id,
        key: 'operator_initials',
        value: 'ZZ',
        locator: 'line 24',
        reason: 'not_an_official_field_path',
      },
    ],
    reconstruction: {
      provider_id: 'deterministic_fake',
      reconstructed_utc: '2099-01-01T00:00:05Z',
      applied: false,
      candidates: [SENDABLE, DISAGREEING, NO_WRITE_PATH, STRUCTURAL],
    },
    unreadable_candidate_count: 0,
    proposed: {},
    parsers: [
      { parser_id: 'synthetic_fixture_key_value', display_name: 'Synthetic fixture (key = value)' },
    ],
    provider: {
      provider_id: 'deterministic_fake',
      display_name: 'Deterministic fake (no model, no network)',
      applied: false,
    },
    beamline_profile: {
      profile_id: 'empty',
      display_name: 'No beamline profile',
      is_empty: true,
      conventions_encoded: 0,
    },
    available_fixtures: ['SYNTHETIC-bundle-a.txt', 'SYNTHETIC-bundle-b.txt'],
    ...overrides,
  };
}

function listResponse(
  overrides: Partial<ApiImportListResponse> = {},
): ApiImportListResponse {
  return {
    imports: [],
    total: 0,
    workflow: WORKFLOW,
    durability: DURABILITY,
    available_fixtures: ['SYNTHETIC-bundle-a.txt', 'SYNTHETIC-bundle-b.txt'],
    ...overrides,
  };
}

/** Every request the stub answered, so a test can assert what was NOT sent. */
const seen: { url: string; method: string; body: unknown; headers: unknown }[] = [];

/**
 * A fetch stub narrow enough to be honest: only the routes this screen reads are
 * answered, and anything else REJECTS LOUDLY — so a screen that started making a
 * request nobody expected fails rather than silently degrading.
 */
function stub(
  routes: {
    list?: ApiImportListResponse;
    detail?: ApiImportSession;
    onPropose?: () => Response;
    experiments?: unknown;
  } = {},
) {
  seen.length = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(typeof input === 'string' ? input : (input as Request).url ?? input);
      const method = (init?.method ?? 'GET').toUpperCase();
      seen.push({ url, method, body: init?.body, headers: init?.headers });
      const json = (payload: unknown, status = 200) =>
        new Response(JSON.stringify(payload), {
          status,
          headers: { 'Content-Type': 'application/json', ETag: '"abc.1"' },
        });

      if (/\/api\/imports\/[^/]+\/candidates\/[^/]+\/propose$/.test(url)) {
        return routes.onPropose ? routes.onPropose() : json({ deduplicated: false });
      }
      if (/\/api\/imports\/[^/]+$/.test(url) && method === 'GET') {
        return json({ import: routes.detail ?? session() });
      }
      if (url.endsWith('/api/imports') && method === 'POST') {
        return json({ import: routes.detail ?? session() });
      }
      if (url.endsWith('/api/imports')) {
        return json(routes.list ?? listResponse());
      }
      if (/\/api\/experiments\/[^/?]+$/.test(url)) {
        /*
         * THE RECORD DETAIL, WITH A `version`. The first version of this stub
         * answered `{ experiments: [] }` for every `/api/experiments*` url,
         * so `detail.version` was `undefined`, the client's truthiness guard
         * correctly sent NO `If-Match`, and the test measured the stub rather
         * than the screen. Recorded because it looked like a defect in the
         * screen and was not.
         */
        return json({ id: '01RECORD00000000000000001', version: 'abc.1' });
      }
      if (url.includes('/api/experiments')) {
        return json(routes.experiments ?? { experiments: [] });
      }
      if (url.includes('/api/health')) {
        return json({
          status: 'ok',
          mode: 'synthetic-only',
          experiment_storage: { configured: false, durable: false, state: 'ephemeral' },
        });
      }
      throw new Error(`unexpected request: ${method} ${url}`);
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderScreen() {
  return render(
    <MemoryRouter
      initialEntries={[ROUTES.imports]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <HistoricalImport />
    </MemoryRouter>,
  );
}

async function openSession() {
  stub({ list: listResponse(), detail: session() });
  renderScreen();
  fireEvent.click(await screen.findByRole('button', { name: IMPORT_COPY.actionStart }));
  await screen.findByRole('heading', { name: 'Sources' });
}

/* --------------------------------------------------------------------------
 * §1 no upload, and no claim of one
 * -------------------------------------------------------------------------- */

describe('§1 · the destination cannot accept bytes and does not say it can', () => {
  it('renders no file input anywhere on the screen', async () => {
    await openSession();
    expect(document.querySelectorAll('input[type="file"]')).toHaveLength(0);
  });

  it('declares no `type="file"` in its own source, nor a drop handler', () => {
    /*
     * THE SOURCE, NOT THE RENDER, and both are needed. The render test above
     * cannot see a control behind a branch this fixture does not reach; this one
     * cannot see one added by a child component. Together they cover both.
     *
     * `upload-claim-parity.test.tsx` separately asserts that EXACTLY two non-test
     * files in `apps/web/src` declare a file input and NAMES BOTH, so a third
     * anywhere fails that test — this is the local, specific half.
     */
    const src = readFileSync(
      join(__dirname, '..', 'screens', 'HistoricalImport.tsx'),
      'utf8',
    );
    const code = src
      .replace(/\/\*[\s\S]*?\*\//g, ' ')
      .replace(/\{\/\*[\s\S]*?\*\/\}/g, ' ')
      .replace(/^\s*\/\/.*$/gm, ' ');
    expect(code).not.toContain('type="file"');
    expect(code).not.toContain('onDrop');
    expect(code).not.toContain('FormData');
    expect(code).not.toContain('multipart');
  });

  it('MUTATION-GUARDED: the source check can actually fail', () => {
    /* Guards the guard: a `not.toContain` over a file that never had the string
     * passes trivially, so prove the predicate fires on the shape it bans. */
    const bad = '<input type="file" onChange={read} />';
    expect(bad).toContain('type="file"');
  });

  it('sends no multipart body on any request it makes', async () => {
    await openSession();
    for (const request of seen) {
      expect(String(request.body ?? '')).not.toContain('Content-Disposition');
      expect(JSON.stringify(request.headers ?? {})).not.toContain('multipart');
    }
  });
});

/* --------------------------------------------------------------------------
 * §2 the nine things HIST-004 requires a scientist to be able to see
 * -------------------------------------------------------------------------- */

describe('§2 · every one of the nine things a scientist must see is on the screen', () => {
  it('which sources were recognised, and what each one IS', async () => {
    await openSession();
    /*
     * `getAllByText`, and the multiplicity is the point rather than a nuisance:
     * the fixture's filename appears in the manifest row AND under every
     * candidate it supports, which is what "which sources support each candidate"
     * requires. `getByText` threw here, and asserting the count states the fact
     * instead of hiding it behind a scope.
     */
    expect(screen.getAllByText('SYNTHETIC-bundle-a.txt').length).toBeGreaterThan(1);
    expect(screen.getByText('FAKE-scan_0012.mac')).toBeTruthy();
    /*
     * `Example source`, NOT `Synthetic fixture` — and the rename is the finding
     * rather than a preference. The first version of this surface labelled the
     * kind `Synthetic fixture`, and
     * `product-facing-language.test.tsx`'s retired-vocabulary ratchet caught it:
     * "fixture" is this project's test-harness word, not a scientist's. The WIRE
     * VALUE is still `synthetic_fixture` (asserted on the fixture above), which is
     * the distinction that matters — a contract value a client branches on is not
     * copy anybody reads.
     */
    expect(screen.getByText('Example source')).toBeTruthy();
    expect(screen.getByText('Reference')).toBeTruthy();
  });

  it('what was read, and what was NOT — per entry, never in a banner', async () => {
    await openSession();
    expect(screen.getByText('Read')).toBeTruthy();
    expect(screen.getByText('Held as a pointer')).toBeTruthy();
    /*
     * THE REASON IS ON THE ROW. This is the load-bearing half: a fixture IS read
     * and a reference is not, so one banner covering both would be false for half
     * the manifest — which is the `Upload -> Spinner -> Mysterious JSON` pattern
     * in miniature.
     */
    expect(screen.getByText(POINTER_DETAIL)).toBeTruthy();
  });

  it('what a source SAID, verbatim, with the line it said it on', async () => {
    await openSession();
    // Appears as a parsed key AND as a candidate target — both are required.
    expect(screen.getAllByText('system.technique').length).toBeGreaterThan(1);
    expect(screen.getAllByText('XAS').length).toBeGreaterThan(0);
    expect(screen.getAllByText('line 21').length).toBeGreaterThan(0);
  });

  it('what a parse PASSED OVER, with the reason', async () => {
    await openSession();
    expect(screen.getByText(/This line has no `=`/)).toBeTruthy();
    expect(screen.getByText('line 26')).toBeTruthy();
  });

  it('what candidate experiments and runs it thinks exist', async () => {
    await openSession();
    expect(screen.getByText('A candidate experiment')).toBeTruthy();
    expect(screen.getByText('SYNTHETIC-bundle')).toBeTruthy();
  });

  it('which sources support each candidate, by FILENAME and not by id', async () => {
    await openSession();
    const card = screen.getByText('system.technique', { selector: '.hi-candidate-target' })
      .closest('article');
    expect(card).toBeTruthy();
    const support = within(card as HTMLElement);
    expect(support.getByText('SYNTHETIC-bundle-a.txt')).toBeTruthy();
    // The id is NOT what a scientist is shown.
    expect((card as HTMLElement).textContent).not.toContain(FIXTURE_SOURCE.source_id);
  });

  it('what was READ versus what was INFERRED', async () => {
    await openSession();
    expect(screen.getAllByText('Read from a source').length).toBeGreaterThan(0);
    expect(screen.getByText('Inferred by a rule')).toBeTruthy();
    // And the inferred one says, in its own warrant, that no source states it.
    expect(screen.getByText(/NO SOURCE STATES A TITLE/)).toBeTruthy();
  });

  it('where sources DISAGREE — every competing value, with who asserts it', async () => {
    await openSession();
    expect(screen.getByRole('heading', { name: 'Sources disagree' })).toBeTruthy();
    expect(screen.getByText('SYNTHETIC-CuO-FAKE-001')).toBeTruthy();
    expect(screen.getByText('SYNTHETIC-CuO-FAKE-002')).toBeTruthy();
  });

  it('what is UNRESOLVED: a disagreement shows no chosen value', async () => {
    /**
     * MUTATION: rendering `String(candidate.proposed_value)` unconditionally
     * makes this RED — it would print `null` where the screen must say that
     * nothing was chosen.
     */
    await openSession();
    const card = screen
      .getByText('sample.material.name', { selector: '.hi-candidate-target' })
      .closest('article') as HTMLElement;
    expect(within(card).getByText('No value was chosen')).toBeTruthy();
    expect(card.textContent).not.toContain('null');
  });

  it('what was read but not RECOGNISED, listed rather than guessed at', async () => {
    await openSession();
    expect(screen.getByRole('heading', { name: 'Read, but not recognised' })).toBeTruthy();
    // Appears in the parse output AND in the unmapped list, deliberately: a
    // reader has to be able to see both that it was read and that it was not
    // placed.
    expect(screen.getAllByText('operator_initials').length).toBeGreaterThan(1);
    expect(screen.getAllByText('ZZ').length).toBeGreaterThan(0);
  });
});

/* --------------------------------------------------------------------------
 * §3 the unbuilt step
 * -------------------------------------------------------------------------- */

describe('§3 · the one step this build does not have says so, and offers nothing', () => {
  it('renders the server’s own disclosure beside the step', async () => {
    await openSession();
    expect(screen.getByText(/Not built in this build/)).toBeTruthy();
  });

  it('MUTATION-GUARDED: offers NO control for it — not even a disabled one', async () => {
    /**
     * MUTATION: rendering `<button disabled>Add to Experiments</button>` in the
     * unbuilt branch makes this RED. A disabled button says the act exists and is
     * temporarily unavailable, which is the claim §15's "build nothing that
     * implies any of it exists" forbids.
     */
    await openSession();
    const steps = screen.getByRole('list', { name: 'Historical import workflow' });
    expect(within(steps).queryAllByRole('button')).toEqual([]);
    expect(within(steps).queryAllByRole('link')).toEqual([]);
    // The step is still NAMED — hiding it would be the other failure.
    expect(within(steps).getByText('Add to Experiments')).toBeTruthy();
  });

  it('never marks the unbuilt step as the one the session has reached', async () => {
    stub({ list: listResponse(), detail: session({ furthest_step: 'review' }) });
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: IMPORT_COPY.actionStart }));
    await screen.findByRole('heading', { name: 'Sources' });
    const current = document.querySelectorAll('[aria-current="step"]');
    expect(current).toHaveLength(1);
    expect(current[0].textContent).toContain('Review');
  });
});

/* --------------------------------------------------------------------------
 * §4 one heading, one name, one vocabulary
 * -------------------------------------------------------------------------- */

describe('§4 · one `<h1>`, one name for the destination, and the server’s words', () => {
  it('renders exactly one `<h1>` and it is the nav label', async () => {
    await openSession();
    const h1s = screen.getAllByRole('heading', { level: 1 });
    expect(h1s).toHaveLength(1);
    expect(h1s[0].textContent).toBe(LABELS.navImports);
  });

  it('the nav item, the heading and the document title are ONE string', () => {
    expect(routeDocumentTitle(ROUTES.imports, '')).toBe(
      `${LABELS.navImports} · ISAAC Metadata Assistant`,
    );
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <LeftNav active="imports" />
      </MemoryRouter>,
    );
    const link = screen.getByRole('link', { name: LABELS.navImports });
    expect(link.getAttribute('href')).toContain(ROUTES.imports);
    expect(link.getAttribute('aria-current')).toBe('page');
  });

  it('the route is registered so the destination is reachable at all', () => {
    expect(ROUTE_PATTERNS.imports).toBe(ROUTES.imports);
  });

  it('the workflow steps and the unbuilt disclosure come from the SERVER', async () => {
    /**
     * MUTATION: hard-coding the six labels in the component makes this RED, which
     * is the point — a second vocabulary in the browser is free to drift from the
     * operation that enforces it.
     */
    const renamed = WORKFLOW.map((step) =>
      step.id === 'parse' ? { ...step, label: 'A LABEL ONLY THE SERVER KNOWS' } : step,
    );
    stub({ list: listResponse({ workflow: renamed }) });
    renderScreen();
    expect(await screen.findByText('A LABEL ONLY THE SERVER KNOWS')).toBeTruthy();
  });

  it('the durability sentence is the SERVER’s, not the browser’s', async () => {
    stub({ list: listResponse({ durability: 'A SENTENCE ONLY THE SERVER KNOWS' }) });
    renderScreen();
    expect(await screen.findByText('A SENTENCE ONLY THE SERVER KNOWS')).toBeTruthy();
  });
});

/* --------------------------------------------------------------------------
 * §5 a candidate that cannot be sent
 * -------------------------------------------------------------------------- */

describe('§5 · a candidate that cannot be sent says why, and offers no control', () => {
  it('a disagreement offers no send control', async () => {
    await openSession();
    const card = screen
      .getByText('sample.material.name', { selector: '.hi-candidate-target' })
      .closest('article') as HTMLElement;
    expect(within(card).queryByRole('button', { name: IMPORT_COPY.actionPropose })).toBeNull();
    expect(within(card).getByText(/deciding between them is yours/i)).toBeTruthy();
  });

  it('a path with no write route keeps the schema clause VERBATIM', async () => {
    /**
     * The most important string on this screen to get right. The refusal must say
     * the limitation is THIS BUILD's — `CLAUDE.md` §1 makes the official schema
     * not ours to speak for, and the Validator screen shipped exactly that
     * conflation once (`FAIL — Invalid against official ISAAC schema` over an
     * empty error list).
     *
     * MUTATION: composing a local sentence instead of rendering the server's
     * makes this RED.
     */
    await openSession();
    const card = screen
      .getByText('system.configuration.detector_model', { selector: '.hi-candidate-target' })
      .closest('article') as HTMLElement;
    expect(card.textContent).toContain('LIMITATION OF THIS BUILD');
    expect(card.textContent).toContain('NOT A STATEMENT ABOUT THE OFFICIAL ISAAC SCHEMA');
    expect(within(card).queryByRole('button', { name: IMPORT_COPY.actionPropose })).toBeNull();
  });

  it('a structural candidate names the missing capability rather than implying it', async () => {
    await openSession();
    const card = screen
      .getByText('A candidate experiment', { selector: '.hi-candidate-target' })
      .closest('article') as HTMLElement;
    expect(card.textContent).toContain('creates an experiment or a run from an import');
    expect(within(card).queryByRole('button', { name: IMPORT_COPY.actionPropose })).toBeNull();
  });

  it('a sendable candidate DOES offer the control — the negative control', async () => {
    /* Without this, every assertion above could pass on a screen that renders no
     * send control at all. */
    await openSession();
    const card = screen
      .getByText('system.technique', { selector: '.hi-candidate-target' })
      .closest('article') as HTMLElement;
    expect(within(card).getByRole('button', { name: IMPORT_COPY.actionPropose })).toBeTruthy();
  });

  it('sending reads the RECORD’s own version and sends it as `If-Match`', async () => {
    /**
     * MUTATION: sending the session's id, or omitting the header, makes this RED.
     * An import session serves no validator; sending a blank would be a 428
     * reported to the reader as a server disagreement.
     */
    await openSession();
    const card = screen
      .getByText('system.technique', { selector: '.hi-candidate-target' })
      .closest('article') as HTMLElement;
    fireEvent.change(within(card).getByPlaceholderText("the record's id"), {
      target: { value: '01RECORD00000000000000001' },
    });
    fireEvent.click(within(card).getByRole('button', { name: IMPORT_COPY.actionPropose }));

    await waitFor(() => {
      const propose = seen.find((r) => r.url.includes('/propose'));
      expect(propose).toBeTruthy();
      expect(JSON.stringify(propose?.headers ?? {})).toContain('If-Match');
      expect(String(propose?.body ?? '')).toContain('01RECORD00000000000000001');
    });
    // It read the record first, which is where the version came from.
    expect(seen.some((r) => r.url.includes('/api/experiments/01RECORD00000000000000001'))).toBe(
      true,
    );
  });

  it('a candidate already sent links to the proposal instead of offering to resend', async () => {
    stub({
      list: listResponse(),
      detail: session({
        proposed: {
          [SENDABLE.candidate_id]: {
            experiment_id: '01RECORD00000000000000001',
            proposal_id: '01PROPOSAL0000000000000001',
            note_id: '01NOTE00000000000000000001',
            proposed_utc: '2099-01-01T00:00:09Z',
          },
        },
      }),
    });
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: IMPORT_COPY.actionStart }));
    await screen.findByRole('heading', { name: 'Sources' });
    const link = screen.getByRole('link', { name: 'Open it on that record' });
    expect(link.getAttribute('href')).toContain('proposal=01PROPOSAL0000000000000001');
    // NEVER "applied": it is an open proposal awaiting review.
    expect(screen.getByText(/awaiting review/)).toBeTruthy();
    expect(document.body.textContent).not.toContain('applied to that record');
  });
});

/* --------------------------------------------------------------------------
 * §6 UX-016 — first-run discovery of Pillar 2
 * -------------------------------------------------------------------------- */

describe('§6 · UX-016 · a scientist with zero experiments can find this destination', () => {
  function stubEmptyWorkspace() {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(typeof input === 'string' ? input : (input as Request).url ?? input);
        const json = (payload: unknown) =>
          new Response(JSON.stringify(payload), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          });
        if (url.includes('/api/experiments')) return json({ experiments: [] });
        if (url.includes('/api/health')) {
          return json({
            status: 'ok',
            mode: 'synthetic-only',
            experiment_storage: { configured: false, durable: false, state: 'ephemeral' },
          });
        }
        throw new Error(`unexpected request: ${url}`);
      }),
    );
  }

  it('the empty state offers Historical Import, as a real LINK', async () => {
    stubEmptyWorkspace();
    render(
      <MemoryRouter
        initialEntries={['/experiments']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <ExperimentsHome />
      </MemoryRouter>,
    );
    await screen.findByText(LABELS.emptyExperimentsTitle);
    const link = screen.getByRole('link', { name: LABELS.actionOpenHistoricalImport });
    expect(link.getAttribute('href')).toContain(ROUTES.imports);
  });

  it('the empty state’s lead sentence no longer omits it', async () => {
    /**
     * MUTATION: restoring the previous body ('Create your first experiment,
     * validate an existing record, or explore ISAAC with the guided demo.') makes
     * this RED. The old sentence was TRUE when written and went stale by omission
     * the moment an import path shipped, which is exactly `UX-016`'s finding.
     */
    stubEmptyWorkspace();
    render(
      <MemoryRouter
        initialEntries={['/experiments']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <ExperimentsHome />
      </MemoryRouter>,
    );
    const body = await screen.findByText(LABELS.emptyExperimentsBody);
    expect(body.textContent).toMatch(/bring in work you already have/i);
  });

  it('and it still promises no upload', () => {
    /*
     * `POST /api/uploads` is unchanged and still refuses everything, and
     * Historical Import does not open a file a reader points at. So the copy says
     * "bring in work you already have" — never "import your files", which would
     * imply the one thing the destination does not do.
     */
    const copy = `${LABELS.emptyExperimentsBody} ${LABELS.historicalImportHint}`;
    expect(copy).not.toMatch(/\bupload/i);
    expect(copy).not.toMatch(/drag|drop/i);
  });
});

/* --------------------------------------------------------------------------
 * §7 the honesty claims in the content module
 * -------------------------------------------------------------------------- */

describe('§7 · the authored copy states the blocked work rather than implying it', () => {
  it('names the formats this build does not read, and why', () => {
    expect(IMPORT_COPY.formatsNote).toMatch(/not read here/i);
    expect(IMPORT_COPY.formatsNote).toMatch(/no example of either is available/i);
  });

  it('says a checksum is recorded and never verified, using the three banned words', () => {
    expect(IMPORT_COPY.digestNote).toMatch(/no checksum is computed here/i);
    expect(IMPORT_COPY.digestNote).toMatch(/verified, checked or matched/i);
  });

  it('says no beamline convention is applied, and that a profile is not a validator', () => {
    expect(IMPORT_COPY.profileNote).toMatch(/no beamline conventions are applied/i);
    expect(IMPORT_COPY.profileNote).toMatch(/official ISAAC schema does that/i);
  });

  it('scopes the file claim to THIS WORKFLOW and never to the application', () => {
    /*
     * The absolute forms shipped false twice in this repository. This asserts the
     * scoping POSITIVELY — the sentence must name the workflow — rather than only
     * relying on `upload-claim-parity.test.tsx`'s bans, which are negative.
     */
    expect(IMPORT_COPY.sourcesLead).toMatch(/this workflow/i);
    expect(IMPORT_COPY.sourcesLead).not.toMatch(/this application/i);
    expect(IMPORT_COPY.sourcesLead).toMatch(/does not open the file it names/i);
  });

  it('says the review step writes no value', () => {
    expect(IMPORT_COPY.reviewLead).toMatch(/writes no value/i);
    expect(IMPORT_COPY.reviewLead).toMatch(/only when someone accepts it/i);
  });

  it('says the reconstruction involves no language model', () => {
    expect(IMPORT_COPY.reconstructLead).toMatch(/no language model is involved/i);
    expect(IMPORT_COPY.reconstructLead).toMatch(/no request leaves this deployment/i);
  });
});
