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
 *   §12 the stage flow (owner QA H1, 2026-09-22): one stage in focus, real tabs
 *
 * ── THE SESSION IS NOW SIX STAGES, ONE IN FOCUS (owner QA H1, 2026-09-22) ──
 *
 * The session used to render every section at once. It is now a tablist —
 * Source Bundle, What ISAAC Read, Runs & Candidates, Conflicts, Review, Add to
 * Experiment — with every panel MOUNTED and all but one `hidden`, and a candidate
 * is a collapsed row rather than an always-open card. So a test that reads by TEXT
 * still reaches every panel (text queries ignore `hidden`), and a test that needs a
 * CONTROL first opens the stage and the row a scientist would open. Nothing below
 * was relaxed to fit: where a query moved, the assertion it guards did not.
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

/** The comment-stripping the source-scan guards use, extracted so the mutation
 *  control can exercise the REAL pipeline rather than a bare substring check.
 *  Block comments, JSX expression comments, and line comments — in that order,
 *  because a JSX comment contains a block comment. */
function stripComments(source: string): string {
  return source
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, ' ')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/^\s*\/\/.*$/gm, ' ')
    .replace(/\/\/.*$/gm, ' ');
}
import { HistoricalImport } from '../screens/HistoricalImport';
import { ExperimentsHome } from '../screens/ExperimentsHome';
import { LeftNav } from '../components/LeftNav';
import { LABELS } from '../lib/labels';
import { ROUTES, ROUTE_PATTERNS } from '../lib/routes';
import { routeDocumentTitle } from '../lib/documentTitle';
import { IMPORT_COPY, IMPORT_STAGE_COPY } from '../lib/historicalImportContent';
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

/*
 * ALL SIX STEPS ARE BUILT, as of `HIST-005` (2026-09-15).
 *
 * This fixture used to mark `add_to_experiments` `built: false` with the
 * server's "Not built in this build" disclosure, and §3 below asserted the
 * surface rendered it. That was true of the server then and is not true now:
 * `historical_import.UNBUILT_STEP` is `None`, so every row the server sends
 * reports `built: true` with a `null` disclosure.
 *
 * A FIXTURE THAT DESCRIBES A STATE THE SERVER NO LONGER PRODUCES is how a suite
 * comes to pass while testing nothing — which is why this one moved rather than
 * being left beside a new one. §3's tests are KEPT, retargeted at the MECHANISM
 * with `UNBUILT_WORKFLOW` below, because the mechanism is what has to keep
 * working: a step the server declares unbuilt must be shown as unbuilt, and the
 * next such step should not need this surface changed.
 */
const WORKFLOW: ApiImportWorkflowStep[] = [
  { id: 'new_import', label: 'New Import', built: true, disclosure: null },
  { id: 'sources', label: 'Sources', built: true, disclosure: null },
  { id: 'parse', label: 'Parse', built: true, disclosure: null },
  { id: 'reconstruct', label: 'Reconstruct', built: true, disclosure: null },
  { id: 'review', label: 'Review', built: true, disclosure: null },
  { id: 'add_to_experiments', label: 'Add to Experiments', built: true, disclosure: null },
];

/** A server that declares one step unbuilt — the shape §3's mechanism needs. */
const UNBUILT_WORKFLOW: ApiImportWorkflowStep[] = WORKFLOW.map((step) =>
  step.id === 'add_to_experiments'
    ? {
        ...step,
        built: false,
        disclosure:
          'Not built in this build. A field candidate you propose becomes an ingestion ' +
          'proposal on an experiment you choose, and you review it there; nothing here ' +
          'creates an experiment for you.',
      }
    : step,
);

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
    available_archives: ['bl15_synthetic_mini_corpus'],
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
    available_archives: ['bl15_synthetic_mini_corpus'],
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
    /** `HIST-005` — what `POST .../add-to-experiment` answers. */
    added?: unknown;
    onAdd?: () => Response;
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
      /* MATCHED BEFORE THE BARE `/api/imports/{id}` GET BELOW, which its own
         regex would otherwise not catch — but order still matters here because a
         future looser pattern would. */
      if (/\/api\/imports\/[^/]+\/add-to-experiment$/.test(url)) {
        if (routes.onAdd) return routes.onAdd();
        return json(routes.added ?? null);
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
      if (url.endsWith('/api/experiments') && method === 'POST') {
        /*
         * CREATE ANSWERS AN EXPERIMENT, NOT A LIST — and this branch exists
         * because its absence produced a crash rather than a failure. Without
         * it, `POST /api/experiments` fell through to the list branch below,
         * `created.id` was `undefined`, and the panel threw
         * `Cannot read properties of undefined (reading 'trim')` from its own
         * submit-disabled expression. That is a FIXTURE gap, not a screen
         * defect: the real route answers `201` with the experiment as the whole
         * body (`test_historical_import_routes.py::_record` records measuring
         * exactly that). Worth naming, though — the panel and the candidate card
         * both do `setExperimentId(created.id)` with no guard, so a server that
         * really answered without an `id` would take the screen down. That is
         * pre-existing and shared, and closing it is its own change.
         */
        return json({ id: '01RECORD00000000000000009', title: 'A fictional 2099 CuO bundle' }, 201);
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
  /*
   * `experiments` IS SERVED HERE because sending a candidate now CHOOSES a
   * destination from the workspace's own records rather than asking a scientist
   * to type a ULID (see `useProposalDestinations`). An empty list is a legitimate
   * state — the screen then offers "New record from this import" instead — but a
   * test about the SEND path needs something to send to.
   */
  stub({
    list: listResponse(),
    detail: session(),
    experiments: {
      experiments: [{ id: '01RECORD00000000000000001', title: 'Cu K-edge campaign, 2019' }],
    },
  });
  renderScreen();
  fireEvent.click(await screen.findByRole('button', { name: IMPORT_COPY.actionStart }));
  await screen.findByRole('tablist', { name: IMPORT_STAGE_COPY.stagesLabel });
}

/** Wait for an opened session's stage tabs — the session view is mounted. */
async function sessionOpen() {
  await screen.findByRole('tablist', { name: IMPORT_STAGE_COPY.stagesLabel });
}

/** Put one stage in focus by pressing its tab, and return its panel. */
function goTo(title: string): HTMLElement {
  const tab = screen.getByRole('tab', { name: new RegExp(title.replace(/[&?]/g, '.')) });
  fireEvent.click(tab);
  const panel = document.getElementById(tab.getAttribute('aria-controls') ?? '');
  expect(panel, `no panel for the ${title} stage`).not.toBeNull();
  expect(panel!.hidden).toBe(false);
  return panel as HTMLElement;
}

/**
 * The candidate row for one official path, in the stage in focus, OPENED — the way
 * a scientist reaches its sources and its send control. Opens the bucket holding it
 * first when that bucket is collapsed.
 */
function openCandidate(panel: HTMLElement, needle: string): HTMLElement {
  const row = [...panel.querySelectorAll<HTMLElement>('li.hi-cand')].find((li) =>
    (li.textContent ?? '').includes(needle),
  );
  expect(row, `no candidate row mentioning ${needle}`).toBeTruthy();
  const bucket = row!.closest('.hi-bucket');
  const bucketTrigger = bucket?.querySelector(':scope > .disclosure-heading > .disclosure-trigger, :scope > .disclosure-trigger');
  if (bucketTrigger && bucketTrigger.getAttribute('aria-expanded') === 'false') fireEvent.click(bucketTrigger);
  const trigger = row!.querySelector(':scope > .hi-cand-row > .disclosure-trigger')!;
  if (trigger.getAttribute('aria-expanded') === 'false') fireEvent.click(trigger);
  return row as HTMLElement;
}

/* --------------------------------------------------------------------------
 * §1 no upload, and no claim of one
 * -------------------------------------------------------------------------- */

/*
 * *** §1 IS INVERTED, 2026-09-15, AND IT NOW BANS THE HARM RATHER THAN THE
 * AFFORDANCE — which is a STRICTLY STRONGER CLAIM than the one it replaces. ***
 *
 * ~~It asserted that this screen renders NO `input[type="file"]` and declares
 * no `type="file"`, `onDrop`, `FormData` or `multipart` in its source. Its
 * stated subject was "the destination cannot accept bytes and does not say it
 * can".~~
 *
 * The project owner reversed that decline (`DEC-33`) and — this is the part
 * that makes the inversion legitimate rather than a loosening — he ANSWERED
 * the decline's own objection instead of overruling it. The objection was:
 *
 *     "a scientist who picked twelve files would reasonably believe twelve
 *      files had been uploaded."
 *
 * His instruction supplies the mitigation (a staged file must read `Local only
 * — not sent to ISAAC`) and is explicit that the guards are to be RECONCILED,
 * not deleted.
 *
 * SO THE SUBJECT CHANGES FROM "the affordance cannot exist" TO "the affordance
 * exists and cannot do harm", and the three things asserted below are the harm:
 * no byte is transmitted, the disclosure is on screen, and no upload route is
 * called. The old assertion could pass on a build that had no feature; these
 * cannot pass on a build that lies about one.
 *
 * WHAT IS NOT WEAKENED: `POST /api/uploads` is still an unconditional 403, and
 * `upload-claim-parity.test.tsx` still holds the app-wide census of which
 * components declare a file input — it goes from two named files to three named
 * files, with the third's disclosure pinned. Neither guard is deleted.
 */
describe('§1 · the file picker exists and cannot send a byte', () => {
  it('renders a file input — the affordance the owner asked for is present', async () => {
    await openSession();
    const inputs = document.querySelectorAll('input[type="file"]');
    expect(
      inputs.length,
      'the staging panel is mounted on Sources; if this is 0 the feature has been ' +
        'removed rather than the guard updated',
    ).toBe(1);
    expect(inputs[0]).toHaveAttribute('multiple');
  });

  it('the disclosure is on screen, in the open, next to it', async () => {
    await openSession();
    /*
     * THE MITIGATION THE DECLINE ASKED FOR, asserted at the point of use. A
     * privacy state is one of the things the copy rule keeps VISIBLE, so this
     * also checks it is not tucked inside a disclosure — `.ifs-claim` sitting
     * inside a `<details>` would satisfy a presence-only check and still leave
     * the reader with the false impression the decline warned about.
     */
    const claim = document.querySelector('.ifs-claim');
    expect(claim).not.toBeNull();
    expect(claim!.textContent).toMatch(/not sent to ISAAC/i);
    expect(claim!.closest('details')).toBeNull();
    // Nor behind the shared `Disclosure`: it sits in the Source Bundle stage itself,
    // beside the picker, and is on screen whenever that stage is.
    expect(claim!.closest('.disclosure-body')).toBeNull();
    const panel = goTo(IMPORT_STAGE_COPY.sources.title);
    expect(panel.contains(claim)).toBe(true);
  });

  it('declares no upload machinery in its own source, and calls no upload route', () => {
    /*
     * THE SOURCE, NOT THE RENDER, and both are still needed for the original
     * reason: the render test cannot see a control behind a branch this fixture
     * does not reach, and the source test cannot see one added by a child.
     *
     * `type="file"` is no longer banned here — the panel legitimately declares
     * one, and it is `ImportFileStaging`'s, asserted in
     * `import-file-staging.test.tsx` both structurally and behaviourally (a spy
     * on `fetch` and `XMLHttpRequest` that throws if either is touched). What is
     * banned is the machinery that would carry BYTES, which no part of this
     * pathway has any use for.
     */
    const src = readFileSync(
      join(__dirname, '..', 'screens', 'HistoricalImport.tsx'),
      'utf8',
    );
    const code = stripComments(src);
    expect(code).not.toContain('FormData');
    expect(code).not.toContain('multipart');
    expect(code).not.toContain('/uploads');
    expect(code).not.toContain('api.upload');
  });

  it('M-9 — the LANDING copy does not promise a format the build cannot read', async () => {
    /*
     * The promise and the capability must sit on the SAME screen. The lead used to
     * name four source classes ("filenames, notes, sheets, run logs") on the index,
     * while the honest correction rendered one step downstream on Sources — so a
     * scientist decided whether to start from a sentence the product corrected
     * later. Of the four, one layout is read.
     *
     * §15: "build nothing that implies any of it exists". Asserted over the RENDERED
     * index rather than over the constant, because what matters is what a reader
     * meets before they commit to the flow.
     */
    renderScreen();
    await screen.findByRole('heading', { level: 1 });
    const lead = document.querySelector('.hi-lead')!;
    const text = (lead.textContent ?? '').toLowerCase();

    // The formats this build CANNOT read must not be offered here.
    for (const unreadable of ['run log', 'spreadsheet', 'sheets', '.mac', 'macro']) {
      expect(text, `the landing copy offers ${unreadable}, which this build cannot read`).not.toContain(
        unreadable,
      );
    }
    // ...and the honest limit IS stated here, not only downstream.
    expect(text).toContain('one layout');
    expect(text).toContain('reference');
  });

  it('MUTATION-GUARDED: the source check can actually fail, THROUGH the real pipeline', () => {
    /*
     * *** THE PREVIOUS VERSION OF THIS TEST WAS A TAUTOLOGY, and an independent
     * review caught it (M-4). *** It read:
     *
     *     const bad = '<input type="file" onChange={read} />';
     *     expect(bad).toContain('type="file"');
     *
     * — `x` contains a substring of `x`. True for any two strings so related, and
     * it exercised NEITHER the comment-stripping pipeline NOR the assertion above
     * it. The guard it claimed to control was in fact sound (the reviewer injected
     * a live `type="file"` into the screen and the real test failed), so this is a
     * false LABEL rather than a false guard — which is its own defect, because the
     * label is what a future reader trusts instead of re-checking.
     *
     * It now drives `stripComments`, the SAME function the assertion above uses, in
     * BOTH directions. The second arm is the one that matters and the tautology
     * could never have reached: a banned string inside a COMMENT must survive
     * stripping as absent, or the guard would fire on its own documentation — and
     * this file's screen does discuss file inputs in prose.
     */
    const inCode = '<input type="file" onChange={read} />';
    expect(stripComments(inCode)).toContain('type="file"');

    for (const commented of [
      '/* we deliberately render no <input type="file" /> here */',
      '{/* no type="file", no onDrop, no FormData, no multipart */}',
      '// FormData and multipart are never constructed',
    ]) {
      const stripped = stripComments(commented);
      expect(stripped, `stripComments left content behind: ${commented}`).not.toContain(
        'type="file"',
      );
      expect(stripped).not.toContain('FormData');
      expect(stripped).not.toContain('multipart');
    }
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

  it('an ARCHIVE is named in words — its raw id and where it was read from sit behind the `?`', async () => {
    /*
     * The review of #279 measured `staged:multi_operator_corpus` printed beside the
     * archive's human name: a staged archive's reference IS its id, so the reference line
     * put the raw token straight back, and the Remove button was named by it too.
     */
    const archive: ApiImportSource = {
      ...FIXTURE_SOURCE,
      source_id: '01SRCARCH0000000000000001',
      kind: 'archive',
      filename: 'staged:FAKE_multi_corpus',
      reference: 'staged:FAKE_multi_corpus',
      fixture_name: null,
    };
    stub({ list: listResponse(), detail: session({ sources: [archive] }), experiments: { experiments: [] } });
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: IMPORT_COPY.actionStart }));
    await sessionOpen();
    const panel = goTo('Source Bundle');
    expect(within(panel).getByText(/Fake multi corpus/)).toBeTruthy();
    // Every text node carrying the raw id is inside the help tip's hidden panel.
    const walker = document.createTreeWalker(panel, NodeFilter.SHOW_TEXT);
    let raw = 0;
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (!(n.textContent ?? '').includes('staged:')) continue;
      raw += 1;
      expect(n.parentElement?.closest('[hidden]'), `raw id shown: ${n.textContent}`).not.toBeNull();
    }
    expect(raw).toBeGreaterThan(0);
    expect(within(panel).getByRole('button', { name: `${IMPORT_COPY.actionRemoveSource} Fake multi corpus` })).toBeTruthy();
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
    // A human name rather than the server's `kind`, and the value it suggests.
    expect(screen.getByText('Candidate experiment')).toBeTruthy();
    expect(screen.getByText('SYNTHETIC-bundle')).toBeTruthy();
  });

  it('which sources support each candidate, by FILENAME and not by id', async () => {
    await openSession();
    const card = openCandidate(goTo(IMPORT_STAGE_COPY.review.title), 'system.technique');
    const support = within(card);
    expect(support.getByText('SYNTHETIC-bundle-a.txt')).toBeTruthy();
    // The id is NOT what a scientist is shown.
    expect(card.textContent).not.toContain(FIXTURE_SOURCE.source_id);
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
    const panel = goTo(IMPORT_STAGE_COPY.conflicts.title);
    // The kind's header names it and counts it; each row carries the shared status.
    expect(
      within(panel).getByRole('heading', { name: new RegExp(IMPORT_STAGE_COPY.conflicts.fieldKindTitle) }),
    ).toBeTruthy();
    expect(within(panel).getAllByText(IMPORT_STAGE_COPY.stateLabels.conflict).length).toBeGreaterThan(0);
    // Every competing value, WITH the file that asserts it, in the Source Facts layer.
    const facts = [...panel.querySelectorAll('.hi-layer-facts > li')].map((li) => li.textContent ?? '');
    expect(facts.some((t) => t.includes('SYNTHETIC-CuO-FAKE-001') && t.includes('SYNTHETIC-bundle-a.txt'))).toBe(true);
    expect(facts.some((t) => t.includes('SYNTHETIC-CuO-FAKE-002'))).toBe(true);
  });

  it('what is UNRESOLVED: a disagreement shows no chosen value', async () => {
    /**
     * MUTATION: rendering `String(candidate.proposed_value)` unconditionally
     * makes this RED — it would print `null` where the screen must say that
     * nothing was chosen.
     */
    await openSession();
    const card = openCandidate(goTo(IMPORT_STAGE_COPY.review.title), 'sample.material.name');
    expect(within(card).getByText(IMPORT_STAGE_COPY.conflicts.noValue)).toBeTruthy();
    expect(card.textContent).not.toContain('null');
  });

  it('what was read but not RECOGNISED, listed rather than guessed at', async () => {
    await openSession();
    const panel = goTo(IMPORT_STAGE_COPY.runs.title);
    expect(within(panel).getByRole('button', { name: /Read, but not recognised/ })).toBeTruthy();
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

describe('§3 · a step the SERVER declares unbuilt says so, and offers nothing', () => {
  /*
   * RETARGETED 2026-09-15, not deleted. These tests were about
   * `add_to_experiments` specifically, because it was the one unbuilt step; it
   * shipped in `HIST-005`, so they are now about the MECHANISM, driven by a
   * server that declares SOME step unbuilt. The mutation guard below is the
   * reason they had to survive the change: it is the only thing standing between
   * a future unbuilt step and a disabled button that implies the act exists.
   */
  async function openWithAnUnbuiltStep() {
    // BOTH the list and the detail carry the workflow, and the strip renders the
    // one on screen — overriding only `listResponse` left the session view
    // showing the default (all-built) list, and the first version of this helper
    // failed looking for the `Sources` heading because it never opened a session
    // at all.
    stub({
      list: listResponse({ workflow: UNBUILT_WORKFLOW }),
      detail: session({ workflow: UNBUILT_WORKFLOW }),
    });
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: IMPORT_COPY.actionStart }));
    await sessionOpen();
  }

  it('renders the server’s own disclosure beside the step', async () => {
    await openWithAnUnbuiltStep();
    expect(screen.getByText(/Not built in this build/)).toBeTruthy();
  });

  it('MUTATION-GUARDED: offers NO control for it — not even a disabled one', async () => {
    /**
     * MUTATION: rendering `<button disabled>Add to Experiments</button>` in the
     * unbuilt branch makes this RED. A disabled button says the act exists and is
     * temporarily unavailable, which is the claim §15's "build nothing that
     * implies any of it exists" forbids.
     */
    await openWithAnUnbuiltStep();
    /*
     * RE-POINTED 2026-09-22: the session's six steps are now stage TABS, and a tab
     * is navigation rather than the act. What must stay true is unchanged — the
     * unbuilt stage offers NO control for the act, not a disabled one — so it is
     * asserted over the stage's own panel, where the act would be.
     */
    const panel = goTo(IMPORT_STAGE_COPY.add.title);
    const acts = within(panel)
      .queryAllByRole('button')
      .filter((b) => !b.classList.contains('helptip-trigger'));
    expect(acts).toEqual([]);
    expect(within(panel).queryAllByRole('link')).toEqual([]);
    expect(within(panel).queryAllByRole('combobox')).toEqual([]);
    // The step is still NAMED, and its tab says it is not built.
    const tab = screen.getByRole('tab', { name: new RegExp(IMPORT_STAGE_COPY.add.title) });
    expect(tab.textContent).toContain(IMPORT_STAGE_COPY.stateLabels.notBuilt);
  });

  it('this build declares NO unbuilt step, so no disclosure is rendered', async () => {
    /*
     * THE STATE THAT ACTUALLY SHIPS. Without this, the retargeted tests above
     * would keep passing on a hand-made server shape while the real one went
     * unexercised — a suite green on a situation that no longer occurs, which is
     * exactly what the fixture comment records happening once already.
     */
    await openSession();
    expect(screen.queryByText(/Not built in this build/)).toBeNull();
    const tab = screen.getByRole('tab', { name: new RegExp(IMPORT_STAGE_COPY.add.title) });
    expect(tab.textContent).not.toContain(IMPORT_STAGE_COPY.stateLabels.notBuilt);
    expect(document.querySelectorAll('.unbuilt')).toHaveLength(0);
  });

  it('marks only the step the session has reached, wherever that is', async () => {
    stub({ list: listResponse(), detail: session({ furthest_step: 'review' }) });
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: IMPORT_COPY.actionStart }));
    await sessionOpen();
    const current = document.querySelectorAll('[aria-current="step"]');
    expect(current).toHaveLength(1);
    expect(current[0].textContent).toContain('Review');
  });

  it('marks the LAST step when the session has reached it', async () => {
    /*
     * REACHABLE NOW, AND IT WAS NOT BEFORE. The old test asserted the last step
     * could NEVER be current, which was right while the step did not exist. The
     * server reaches it when every proposable candidate has been sent.
     */
    stub({
      list: listResponse(),
      detail: session({ furthest_step: 'add_to_experiments' }),
    });
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: IMPORT_COPY.actionStart }));
    await sessionOpen();
    const current = document.querySelectorAll('[aria-current="step"]');
    expect(current).toHaveLength(1);
    expect(current[0].textContent).toContain(IMPORT_STAGE_COPY.add.title);
    expect(current[0].getAttribute('role')).toBe('tab');
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
    const card = openCandidate(goTo(IMPORT_STAGE_COPY.review.title), 'sample.material.name');
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
    const card = openCandidate(goTo(IMPORT_STAGE_COPY.review.title), 'system.configuration.detector_model');
    expect(card.textContent).toContain('LIMITATION OF THIS BUILD');
    expect(card.textContent).toContain('NOT A STATEMENT ABOUT THE OFFICIAL ISAAC SCHEMA');
    expect(within(card).queryByRole('button', { name: IMPORT_COPY.actionPropose })).toBeNull();
  });

  it('a structural candidate names the missing capability rather than implying it', async () => {
    await openSession();
    // A structural candidate is shown in Runs & Candidates ("What this looks like");
    // Review lists only the field candidates a proposal can carry.
    const card = openCandidate(goTo(IMPORT_STAGE_COPY.runs.title), 'SYNTHETIC-bundle');
    expect(card.textContent).toContain('creates an experiment or a run from an import');
    expect(within(card).queryByRole('button', { name: IMPORT_COPY.actionPropose })).toBeNull();
  });

  it('a sendable candidate DOES offer the control — the negative control', async () => {
    /* Without this, every assertion above could pass on a screen that renders no
     * send control at all. */
    await openSession();
    const card = openCandidate(goTo(IMPORT_STAGE_COPY.review.title), 'system.technique');
    expect(within(card).getByRole('button', { name: IMPORT_COPY.actionPropose })).toBeTruthy();
  });

  it('sending reads the RECORD’s own version and sends it as `If-Match`', async () => {
    /**
     * MUTATION: sending the session's id, or omitting the header, makes this RED.
     * An import session serves no validator; sending a blank would be a 428
     * reported to the reader as a server disagreement.
     */
    await openSession();
    const card = openCandidate(goTo(IMPORT_STAGE_COPY.review.title), 'system.technique');
    /*
     * A PICKER SINCE 2026-09-14, not a typed ULID. This used to
     * `getByPlaceholderText("the record's id")` and type the id in — which is
     * exactly the interaction the project owner reported as unusable ("nobody
     * knows a ULID"), so the field is now a `<select>` of the workspace's own
     * records. The destination is incidental to THIS test, whose subject is that
     * sending reads the RECORD's version and sends it as `If-Match`; only the
     * way the destination is chosen changed. See `useProposalDestinations`.
     *
     * The option must exist to be selectable, so this waits for the list read
     * rather than assuming it has landed.
     */
    const destination = await waitFor(() => {
      const el =
        within(card).queryByRole('combobox', { name: /which record/i }) ??
        within(card).queryByPlaceholderText("the record's id");
      if (el === null) throw new Error('no destination control yet');
      return el;
    });
    fireEvent.change(destination, { target: { value: '01RECORD00000000000000001' } });
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
    await sessionOpen();
    const row = openCandidate(goTo(IMPORT_STAGE_COPY.review.title), 'system.technique');
    const link = screen.getByRole('link', { name: 'Open it on that record' });
    expect(link.getAttribute('href')).toContain('proposal=01PROPOSAL0000000000000001');
    // NEVER "applied": it is an open proposal awaiting review. Scoped to the Review row:
    // the Runs stage (mounted, hidden) now says the same of the same candidate.
    expect(within(row).getByText(/awaiting review/)).toBeTruthy();
    expect(document.body.textContent).not.toContain('applied to that record');
  });

  it('after a send, Review shows 0 Ready and the sent candidate as SENT, with the record it went to', async () => {
    /*
     * The orchestrator's browser pass of #279: after Add to Experiment the header said
     * "4 Sent" and the Add stage "0 can be sent · 4 already sent", while Review still
     * listed the same four under "Ready to Send · 4", each chipped "Ready to Send". A
     * sent candidate is SENT everywhere — one categorisation (`reviewBucketOf`, built on
     * the same plan the Add stage and the header read).
     */
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
      experiments: {
        experiments: [{ id: '01RECORD00000000000000001', title: 'Cu K-edge campaign, 2019' }],
      },
    });
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: IMPORT_COPY.actionStart }));
    await sessionOpen();
    const panel = goTo(IMPORT_STAGE_COPY.review.title);
    const ready = IMPORT_STAGE_COPY.bucketTitles.ready;

    // 0 Ready: no chip, no group, and the header agrees.
    expect(panel.querySelector('.hi-review-counts')?.textContent ?? '').not.toContain(ready);
    const groups = [...panel.querySelectorAll('.hi-bucket')].map(
      (g) => g.querySelector('.disclosure-summary')?.textContent,
    );
    expect(groups).not.toContain(ready);
    expect(groups).toContain('Sent');
    expect(document.querySelector('.hi-summary-item[data-id="ready"] dd')?.textContent).toBe('0');

    // The row reads Sent — never Ready to Send — and names the record it went to.
    const row = openCandidate(panel, 'system.technique');
    expect(within(row).getAllByText('Sent').length).toBeGreaterThan(0);
    expect(within(row).queryByText(IMPORT_STAGE_COPY.stateLabels.ready)).toBeNull();
    await waitFor(() =>
      expect(within(row).getByRole('link', { name: /Cu K-edge campaign, 2019/ }).getAttribute('href')).toContain(
        'proposal=01PROPOSAL0000000000000001',
      ),
    );
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

/* --------------------------------------------------------------------------
 * §8 the loading state is the SHARED one, so the sweeps can see it
 * -------------------------------------------------------------------------- */

describe('§8 · the loading panel is the one every sweep waits for', () => {
  it('renders `div.fetch-state[role="status"]`, not a hand-rolled status div', async () => {
    /**
     * AN INVARIANT, NOT CONSISTENCY FOR ITS OWN SAKE — and it was a real defect
     * in the first version of this screen.
     *
     * `e2e/specs/layout-widths.spec.ts` asserts
     * `locator('div.fetch-state[role="status"]')` has count 0 before it measures
     * a surface, i.e. "no screen is still loading". This screen first rendered
     * `<div className="placeholder" role="status">`, which that locator does NOT
     * match — so the sweep could not wait for it and would one day have measured
     * a skeleton and reported it as this surface.
     *
     * MUTATION: replacing `<LoadingPanel/>` with a bare `role="status"` div makes
     * this RED.
     */
    let resolve: ((value: unknown) => void) | undefined;
    const pending = new Promise((r) => {
      resolve = r;
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        await pending;
        return new Response(JSON.stringify(listResponse()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }),
    );
    const { container } = renderScreen();
    const panel = container.querySelector('div.fetch-state[role="status"]');
    expect(panel, 'the loading panel is not the shared one the sweeps wait for').not.toBeNull();
    expect(panel?.textContent).toContain('Loading imports');
    resolve?.(null);
    await screen.findByRole('heading', { name: 'Imports' });
  });
});

/* --------------------------------------------------------------------------
 * §10 HIST-005 — Add This Import to a Record
 *
 * The workflow's sixth step, built 2026-09-15. Three things have to be true for
 * this control to be honest, and each gets its own test rather than one test
 * asserting a rendering:
 *
 *   1. it is ONE request, not a loop — the defect it exists to prevent is a
 *      record holding half an import with nothing able to say which half;
 *   2. it reports what the SERVER said, including the parts that went badly;
 *   3. it never says "applied", because nothing is.
 * -------------------------------------------------------------------------- */

/** A second sendable candidate, RUN-scoped, so the run half is exercisable. */
const SENDABLE_RUN: ApiImportCandidate = {
  ...SENDABLE,
  candidate_id: '01CANDE0000000000000000005',
  target_field_path: 'sample.material.name',
  proposed_value: 'FICTIONAL-CuO',
  rule: 'Read verbatim from `sample.material.name` in a fictional source.',
};

const TWO_SENDABLE = [SENDABLE, SENDABLE_RUN, DISAGREEING, NO_WRITE_PATH, STRUCTURAL];

function addedResponse(overrides: Record<string, unknown> = {}) {
  return {
    experiment_id: '01RECORD00000000000000001',
    run_id: null,
    sent: [
      {
        candidate_id: SENDABLE.candidate_id,
        target_field_path: 'system.technique',
        rule: SENDABLE.rule,
        proposal_id: '01PROPOSAL0000000000000001',
        note_id: '01NOTE00000000000000000001',
        run_id: null,
        already_sent: false,
      },
      {
        candidate_id: SENDABLE_RUN.candidate_id,
        target_field_path: 'sample.material.name',
        rule: SENDABLE_RUN.rule,
        proposal_id: '01PROPOSAL0000000000000002',
        note_id: '01NOTE00000000000000000002',
        run_id: null,
        already_sent: false,
      },
    ],
    not_sent: [
      {
        candidate_id: DISAGREEING.candidate_id,
        target_field_path: 'sample.material.name',
        kind: 'field',
        error: 'candidate_unresolved',
        reason: 'A SENTENCE ONLY THE SERVER KNOWS about disagreeing sources.',
      },
    ],
    counts: { candidates: 5, sent: 2, already_sent: 0, not_sent: 1 },
    experiment_version: '7',
    ...overrides,
  };
}

async function openWithTwoSendable(added: unknown = addedResponse()) {
  stub({
    list: listResponse(),
    detail: session({
      reconstruction: { ...session().reconstruction!, candidates: TWO_SENDABLE },
    }),
    experiments: {
      experiments: [{ id: '01RECORD00000000000000001', title: 'Cu K-edge campaign, 2019' }],
    },
    added,
  });
  renderScreen();
  fireEvent.click(await screen.findByRole('button', { name: IMPORT_COPY.actionStart }));
  await sessionOpen();
}

/**
 * Choose the destination and submit, SCOPED TO THE PANEL.
 *
 * A loaded session renders FOUR comboboxes — this panel's and one per candidate
 * card that offers a form — so an unscoped `getAllByRole('combobox')[0]` picks
 * whichever happens to come first in the DOM. The first version of these tests
 * did exactly that, changed a candidate card's select instead, submitted a panel
 * whose own field was still empty, and failed looking for a result block that
 * had correctly never been rendered. Measured, not guessed: a probe printed
 * `COMBOS 4` with the panel present and its button found.
 */
async function chooseRecordAndAdd() {
  goTo(IMPORT_STAGE_COPY.add.title);
  const panel = document.querySelector('.hi-addwhole') as HTMLElement;
  expect(panel).not.toBeNull();
  fireEvent.change(within(panel).getByRole('combobox'), {
    target: { value: '01RECORD00000000000000001' },
  });
  fireEvent.click(
    within(panel).getByRole('button', { name: IMPORT_COPY.actionAddWhole }),
  );
}

describe('§10 · adding a whole import to one record', () => {
  it('offers the step as ONE control when more than one candidate can be sent', async () => {
    await openWithTwoSendable();
    const panel = goTo(IMPORT_STAGE_COPY.add.title);
    expect(within(panel).getAllByRole('button', { name: IMPORT_COPY.actionAddWhole })).toHaveLength(1);
    /*
     * ONE NAME FOR THE STAGE. Re-pointed 2026-09-22: the stepper this used to be
     * checked against is now the stage tab, and the tab and the stage's heading read
     * the SAME constant — so the panel and the control that opens it cannot call one
     * step two things.
     */
    expect(within(panel).getByRole('heading', { name: IMPORT_STAGE_COPY.add.title })).toBeTruthy();
    expect(screen.getByRole('tab', { name: new RegExp(IMPORT_STAGE_COPY.add.title) })).toBeTruthy();
  });

  it('does NOT offer it when exactly one candidate can be sent', async () => {
    /*
     * TWO CONTROLS FOR ONE ACT is what makes a reader wonder which is the real
     * one. With a single sendable candidate, that candidate's own form already
     * IS the whole batch. The step stays completable — sending the one candidate
     * finishes it, and the server's `furthest_step` says so.
     */
    await openSession();
    goTo(IMPORT_STAGE_COPY.add.title);
    expect(screen.queryByRole('button', { name: IMPORT_COPY.actionAddWhole })).toBeNull();
  });

  it('MUTATION-GUARDED: sends ONE request for the whole batch, not one per candidate', async () => {
    /**
     * MUTATION: reimplementing the submit handler as
     * `for (const c of sendable) await api.proposeImportCandidate(...)` makes
     * this RED — two `/propose` calls and no `/add-to-experiment` call.
     *
     * This is the assertion the whole operation exists for. N requests, each with
     * its own `If-Match`, means a closed tab or a `412` partway through leaves
     * the record holding part of an import with nothing able to say which part.
     */
    await openWithTwoSendable();
    await chooseRecordAndAdd();
    await screen.findByText(IMPORT_COPY.addWholeResultTitle);

    const batch = seen.filter((r) => r.url.includes('/add-to-experiment'));
    const single = seen.filter((r) => r.url.includes('/propose'));
    expect(batch).toHaveLength(1);
    expect(single).toHaveLength(0);
    expect(batch[0].method).toBe('POST');
    // `seen` records the RAW body the client sent, which is a JSON string.
    expect(JSON.parse(String(batch[0].body))).toEqual({
      experiment_id: '01RECORD00000000000000001',
    });
    // THE RECORD'S OWN VALIDATOR, read immediately before the write — never the
    // session's, which does not have one.
    expect(batch[0].headers).toMatchObject({ 'If-Match': '"abc.1"' });
  });

  it('sends the run only when one was named, and never invents one', async () => {
    await openWithTwoSendable();
    await chooseRecordAndAdd();
    await screen.findByText(IMPORT_COPY.addWholeResultTitle);
    // NO `run_id` KEY AT ALL when the field is blank — not `run_id: null`, and
    // not the only run that happens to exist.
    const sentBody = JSON.parse(
      String(seen.filter((r) => r.url.includes('/add-to-experiment'))[0].body),
    );
    expect(sentBody).toEqual({ experiment_id: '01RECORD00000000000000001' });
    expect('run_id' in sentBody).toBe(false);
  });

  it('reports every one of the server’s counts, including the bad news', async () => {
    await openWithTwoSendable();
    await chooseRecordAndAdd();
    await screen.findByText(IMPORT_COPY.addWholeResultTitle);

    /* ALL FOUR NUMBERS. A surface that showed "2 sent" and stopped would tell a
       reader less than the server said — and the one it left out is the one
       that needs their attention. */
    const counts = screen.getByText(/could not be sent/);
    expect(counts.textContent).toContain('2 sent');
    expect(counts.textContent).toContain('0 already there');
    expect(counts.textContent).toContain('1 could not be sent');
    expect(counts.textContent).toContain('5 candidates in this import');
  });

  it('gives the SERVER’s reason for each candidate it could not send', async () => {
    await openWithTwoSendable();
    await chooseRecordAndAdd();
    // VERBATIM, and not a paraphrase composed here: the sentence the server will
    // actually enforce is the one a scientist has to be able to act on.
    expect(
      await screen.findByText(/A SENTENCE ONLY THE SERVER KNOWS about disagreeing sources/),
    ).toBeTruthy();
  });

  it('reads `already_sent` off the server rather than inferring a second click', async () => {
    const already = addedResponse({
      sent: addedResponse().sent.map((row) => ({ ...row, already_sent: true })),
      counts: { candidates: 5, sent: 0, already_sent: 2, not_sent: 1 },
    });
    await openWithTwoSendable(already);
    await chooseRecordAndAdd();
    await screen.findByText(IMPORT_COPY.addWholeResultTitle);

    expect(screen.getByText(IMPORT_COPY.addWholeNothingNew)).toBeTruthy();
    expect(screen.getAllByText('already there').length).toBe(2);
    // AND IT DOES NOT CLAIM TO HAVE SENT ANYTHING.
    expect(screen.getByText(/could not be sent/).textContent).toContain('0 sent');
  });

  it('never says a value was applied, written or saved to the record', async () => {
    await openWithTwoSendable();
    await chooseRecordAndAdd();
    await screen.findByText(IMPORT_COPY.addWholeResultTitle);

    /* "Add This Import to a Record" is a name a reader can hear as "apply it",
       which is exactly why the lead has to say otherwise and why nothing on the
       surface may contradict it. Scoped to this panel rather than the document:
       the word "applied" legitimately appears elsewhere on the screen, in the
       reconstruction line that reports `nothing was applied`. */
    // The whole Add stage — its lead, the form and the report — since 2026-09-22.
    const panel = goTo(IMPORT_STAGE_COPY.add.title);
    const text = panel.textContent ?? '';
    expect(text).toMatch(/no value is written/i);
    for (const forbidden of [/\bapplied to\b/i, /\bwritten to the record\b/i, /\bsaved\b/i]) {
      expect(text).not.toMatch(forbidden);
    }
    // And it says what each candidate BECAME.
    expect(text).toContain('open proposal');
  });

  it('states that the run is used only for the values a run owns', async () => {
    /*
     * THE DIFFERENCE FROM THE PER-CANDIDATE FORM, SAID OUT LOUD. There, a run
     * given for a record-scoped target is REFUSED; here one run is given for a
     * whole import and used where it belongs. A reader who learned the first
     * rule would otherwise expect this form to refuse the same thing.
     */
    await openWithTwoSendable();
    expect(within(goTo(IMPORT_STAGE_COPY.add.title)).getByText(IMPORT_COPY.addWholeRunNote)).toBeTruthy();
  });

  it('links each sent candidate to its proposal on that record', async () => {
    await openWithTwoSendable();
    await chooseRecordAndAdd();
    await screen.findByText(IMPORT_COPY.addWholeResultTitle);

    fireEvent.click(screen.getByRole('button', { name: /Sent candidates/ }));
    const links = within(
      document.querySelector('.hi-addwhole-result .hi-addwhole-sent') as HTMLElement,
    ).getAllByRole('link');
    expect(links).toHaveLength(2);
    expect(links[0].getAttribute('href')).toContain('01PROPOSAL0000000000000001');
    expect(links[1].getAttribute('href')).toContain('01PROPOSAL0000000000000002');
  });
});

/* --------------------------------------------------------------------------
 * §11 the one control that CREATES the destination
 * -------------------------------------------------------------------------- */

describe('§11 · creating the destination, from either form', () => {
  /*
   * ONE COMPONENT, TWO CALL SITES. The label is exempted in
   * `product-facing-language.test.tsx` as ONE STRING, ONE OCCURRENCE — the
   * exemption's own comment calls that "what makes this an act rather than a
   * widening" — so `HIST-005`'s panel could not carry a second copy of it.
   * Extracting the control satisfies the guard for the reason it exists; these
   * tests pin the behaviour that extraction had to preserve.
   */
  it('MUTATION-GUARDED: the new record appears in the SAME picker that submits', async () => {
    /**
     * MUTATION: give `NewDestinationButton` its own `useProposalDestinations()`
     * instead of taking the caller's `reload` — this goes RED.
     *
     * A second hook instance is a second list. Creating a record would refresh
     * the one nobody renders, while the form's own `<option>` list still lacked
     * the new id, so `onCreated` would set a select value matching no option and
     * the picker would read blank with the submit disabled. This is the defect
     * the extraction introduced and the prop removes.
     */
    let listCalls = 0;
    const created = { id: '01RECORD00000000000000009', title: 'A fictional 2099 CuO bundle' };
    stub({
      list: listResponse(),
      detail: session({
        reconstruction: { ...session().reconstruction!, candidates: TWO_SENDABLE },
      }),
      experiments: { experiments: [] },
    });
    // Re-stub with a list that GROWS once the record exists, so "the picker was
    // reloaded" is observable rather than asserted.
    const base = globalThis.fetch as unknown as (...a: unknown[]) => Promise<Response>;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(typeof input === 'string' ? input : (input as Request).url ?? input);
        const method = (init?.method ?? 'GET').toUpperCase();
        if (url.endsWith('/api/experiments') && method === 'POST') {
          return new Response(JSON.stringify(created), {
            status: 201,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        if (url.endsWith('/api/experiments') && method === 'GET') {
          listCalls += 1;
          return new Response(
            JSON.stringify({ experiments: listCalls > 1 ? [created] : [] }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          );
        }
        return base(input, init);
      }),
    );

    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: IMPORT_COPY.actionStart }));
    await sessionOpen();
    goTo(IMPORT_STAGE_COPY.add.title);

    const panel = document.querySelector('.hi-addwhole') as HTMLElement;
    expect(panel).not.toBeNull();
    // An empty workspace offers no picker yet — the honest empty state.
    expect(within(panel).queryByRole('combobox')).toBeNull();

    fireEvent.click(
      within(panel).getByRole('button', { name: 'New record from this import' }),
    );

    // THE PICKER THIS FORM SUBMITS now holds the new record AND has it selected.
    const select = (await within(panel).findByRole('combobox')) as HTMLSelectElement;
    expect([...select.options].map((o) => o.textContent)).toContain(created.title);
    expect(select.value).toBe(created.id);
    expect(
      within(panel).getByRole('button', { name: IMPORT_COPY.actionAddWhole }),
    ).not.toBeDisabled();
  });

  it('titles the new record from the import and carries no field over', async () => {
    await openWithTwoSendable();
    goTo(IMPORT_STAGE_COPY.add.title);
    const panel = document.querySelector('.hi-addwhole') as HTMLElement;
    fireEvent.click(
      within(panel).getByRole('button', { name: 'New record from this import' }),
    );
    await waitFor(() => {
      expect(seen.some((r) => r.url.endsWith('/api/experiments') && r.method === 'POST')).toBe(
        true,
      );
    });
    const body = JSON.parse(
      String(seen.find((r) => r.url.endsWith('/api/experiments') && r.method === 'POST')!.body),
    );
    // A TITLE AND NOTHING ELSE. No candidate has been reviewed yet, so carrying a
    // value over would write an unreviewed one — which is the whole thing this
    // surface refuses to do.
    expect(body).toEqual({ title: 'A fictional 2099 CuO bundle' });
  });
});

/* --------------------------------------------------------------------------
 * §12 the stage flow (owner QA H1, 2026-09-22)
 * -------------------------------------------------------------------------- */

describe('§12 · one stage in focus, reached by real tabs', () => {
  it('shows six stage tabs and exactly ONE panel, the one the session has reached', async () => {
    await openSession();
    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((t) => t.querySelector('.hi-stage-name')?.textContent)).toEqual([
      IMPORT_STAGE_COPY.sources.title,
      IMPORT_STAGE_COPY.read.title,
      IMPORT_STAGE_COPY.runs.title,
      IMPORT_STAGE_COPY.conflicts.title,
      IMPORT_STAGE_COPY.review.title,
      IMPORT_STAGE_COPY.add.title,
    ]);
    const panels = document.querySelectorAll('[role="tabpanel"]');
    expect(panels).toHaveLength(6);
    expect([...panels].filter((p) => !(p as HTMLElement).hidden)).toHaveLength(1);
    // A reconstructed session opens on its candidates, not on an empty first step.
    expect(screen.getByRole('tab', { selected: true }).textContent).toContain(IMPORT_STAGE_COPY.runs.title);
  });

  it('MUTATION-GUARDED: arrow keys, Home and End move the stage AND the focus', async () => {
    /**
     * MUTATION: dropping `refs.current.get(next)?.focus()` from `move` makes this RED
     * — the selection moves and a keyboard reader is left on a tab that is no longer
     * the selected one.
     */
    await openSession();
    const selected = () => screen.getByRole('tab', { selected: true });
    selected().focus();
    fireEvent.keyDown(selected(), { key: 'ArrowRight' });
    expect(selected().textContent).toContain(IMPORT_STAGE_COPY.conflicts.title);
    expect(document.activeElement).toBe(selected());
    fireEvent.keyDown(selected(), { key: 'End' });
    expect(selected().textContent).toContain(IMPORT_STAGE_COPY.add.title);
    fireEvent.keyDown(selected(), { key: 'ArrowRight' });
    expect(selected().textContent).toContain(IMPORT_STAGE_COPY.sources.title);
    fireEvent.keyDown(selected(), { key: 'Home' });
    expect(selected().textContent).toContain(IMPORT_STAGE_COPY.sources.title);
    expect(document.activeElement).toBe(selected());
    // Roving tabindex: only the selected tab is in the tab order.
    expect(screen.getAllByRole('tab').filter((t) => t.tabIndex === 0)).toHaveLength(1);
  });

  it('puts the counts first, every one read off the payload', async () => {
    await openSession();
    const summary = document.querySelector('dl.hi-summary')!;
    expect(summary.getAttribute('aria-label')).toBe(IMPORT_STAGE_COPY.summaryTitle);
    const pairs = Object.fromEntries(
      [...summary.querySelectorAll('.hi-summary-item')].map((item) => [
        item.getAttribute('data-id'),
        item.querySelector('dd')?.textContent,
      ]),
    );
    // Two sources, one read, four candidates, one conflict (the disagreement), one ready.
    expect(pairs).toMatchObject({ sources: '2', read: '1', candidates: '4', conflicts: '1', ready: '1' });
    // "Need review" is the Review tab's own number: FIELD candidates only, so the header
    // and the tab can never disagree (the structural candidate is never sent).
    const reviewTab = screen.getByRole('tab', { name: new RegExp(IMPORT_STAGE_COPY.review.title) });
    expect(reviewTab.textContent).toContain(`${pairs['needs-review']} need review`);
  });

  it('every stage is ONE heading and ONE sentence on the surface, the rest behind a `?`', async () => {
    await openSession();
    for (const id of ['sources', 'read', 'runs', 'conflicts', 'review', 'add'] as const) {
      const panel = goTo(IMPORT_STAGE_COPY[id].title);
      const head = panel.querySelector('.hi-stage-head')!;
      expect(head.querySelectorAll('h3')).toHaveLength(1);
      expect(head.querySelectorAll('p.hi-stage-lead')).toHaveLength(1);
      // The explanation is kept, one press away.
      expect(head.querySelector('.helptip-panel')?.textContent).toBe(IMPORT_STAGE_COPY[id].help);
    }
  });

  it('MUTATION-GUARDED: an act keeps the reader on the stage they are on', async () => {
    /**
     * MUTATION: deleting the `setStage((current) => current ?? activeRef.current)`
     * pin in `act` makes this RED. Found in a real browser first: adding the first
     * source re-derived the stage and swept the reader to What ISAAC Read, table and
     * all, while they were still assembling the bundle.
     */
    const empty = session({ sources: [], parsed: [], unmapped_keys: [], reconstruction: null, furthest_step: 'new_import' });
    const withSource = session({ sources: [FIXTURE_SOURCE], parsed: [], unmapped_keys: [], reconstruction: null, furthest_step: 'sources' });
    let added = false;
    stub({ list: listResponse(), detail: empty });
    const base = globalThis.fetch as unknown as (...a: unknown[]) => Promise<Response>;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(typeof input === 'string' ? input : (input as Request).url ?? input);
        const method = (init?.method ?? 'GET').toUpperCase();
        const json = (payload: unknown) =>
          new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });
        if (/\/api\/imports\/[^/]+\/sources$/.test(url) && method === 'POST') {
          added = true;
          return json({ import: withSource });
        }
        if (/\/api\/imports\/[^/]+$/.test(url) && method === 'GET') return json({ import: added ? withSource : empty });
        return base(input, init);
      }),
    );
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: IMPORT_COPY.actionStart }));
    await sessionOpen();
    expect(screen.getByRole('tab', { selected: true }).textContent).toContain(IMPORT_STAGE_COPY.sources.title);
    fireEvent.click(screen.getByRole('button', { name: IMPORT_COPY.actionAddFixture }));
    await waitFor(() => expect(added).toBe(true));
    await waitFor(() => expect(document.querySelector('table')).not.toBeNull());
    expect(screen.getByRole('tab', { selected: true }).textContent).toContain(IMPORT_STAGE_COPY.sources.title);
  });

  it('names the next stage at the foot of each one, and lands focus on its tab', async () => {
    await openSession();
    const panel = goTo(IMPORT_STAGE_COPY.sources.title);
    const next = within(panel).getByRole('button', { name: `Next: ${IMPORT_STAGE_COPY.read.title}` });
    fireEvent.click(next);
    expect(screen.getByRole('tab', { selected: true }).textContent).toContain(IMPORT_STAGE_COPY.read.title);
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('tab', { selected: true })));
    // The last stage offers no "next".
    expect(within(goTo(IMPORT_STAGE_COPY.add.title)).queryByRole('button', { name: /^Next:/ })).toBeNull();
  });
});

describe('§13 · what the batch send reports, and where review happens', () => {
  const REPORT = {
    counts: { candidates: 5, sent: 2, already_sent: 0, not_sent: 1, runs_created: 1 },
    runs_already_present: [
      { run_id: 'R1', label: '#3 FAKE', stem: 'FAKE_03', matched_by: 'acquisition_identity' },
      { run_id: 'R2', label: '#4 FAKE', stem: 'FAKE_04', matched_by: 'label_before_origins_existed' },
    ],
  };

  it('links to the record’s proposals and names HOW each existing run was found', async () => {
    await openWithTwoSendable(addedResponse(REPORT));
    await chooseRecordAndAdd();
    await screen.findByText(IMPORT_COPY.addWholeResultTitle);
    const link = screen.getByRole('link', { name: IMPORT_STAGE_COPY.openProposals });
    expect(link.getAttribute('href')).toBe(ROUTES.recordView('01RECORD00000000000000001', 'proposals'));
    expect(screen.getByText(/1 runs created/)).toBeTruthy();
    // `matched_by` in words, never the token.
    expect(screen.getByText('found by the file’s own identity')).toBeTruthy();
    expect(screen.getByText(/found by its label/)).toBeTruthy();
    expect(document.body.textContent).not.toContain('label_before_origins_existed');
  });

  it('says acceptance needs an identified reviewer ONLY when the server’s capability says so', async () => {
    stub({
      list: listResponse(),
      detail: session({
        reconstruction: { ...session().reconstruction!, candidates: TWO_SENDABLE },
        capabilities: {
          historical_file_ingestion: { enabled: false, reason: 'FAKE' },
          proposal_acceptance: { available: false, reason: 'FAKE' },
        },
      }),
      experiments: { experiments: [{ id: '01RECORD00000000000000001', title: 'Cu K-edge campaign, 2019' }] },
      added: addedResponse(),
    });
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: IMPORT_COPY.actionStart }));
    await sessionOpen();
    // Not before a send: the note belongs beside the link to review.
    expect(within(goTo(IMPORT_STAGE_COPY.add.title)).queryByText(IMPORT_STAGE_COPY.acceptanceNote)).toBeNull();
    await chooseRecordAndAdd();
    await screen.findByText(IMPORT_COPY.addWholeResultTitle);
    expect(screen.getByText(IMPORT_STAGE_COPY.acceptanceNote)).toBeTruthy();
  });

  it('and says nothing about acceptance when the capability is available', async () => {
    await openWithTwoSendable();
    await chooseRecordAndAdd();
    await screen.findByText(IMPORT_COPY.addWholeResultTitle);
    expect(screen.queryByText(IMPORT_STAGE_COPY.acceptanceNote)).toBeNull();
  });

  it('offers "one run per measurement" only for an archive import', async () => {
    await openWithTwoSendable();
    expect(
      within(goTo(IMPORT_STAGE_COPY.add.title)).queryByRole('checkbox', { name: IMPORT_STAGE_COPY.createRuns }),
    ).toBeNull();
  });
});

describe('§14 · per-scan variation is not counted or shown as a conflict', () => {
  const VARIES: ApiImportCandidate = {
    ...NO_WRITE_PATH,
    candidate_id: '01CANDV0000000000000000009',
    target_field_path: null,
    proposed_value: null,
    not_proposable_reason: 'FAKE registry reason.',
    agreement: 'varies',
    review_status: 'unmapped',
    variation_basis: 'per_scan',
    variation_scans: 2,
    variation: [
      { scan: '1', item: null, source: null, value: 'ZZ_unit · scan 1', source_ids: ['S1'], locators: ['l1'] },
      { scan: '2', item: null, source: null, value: 'ZZ_unit · scan 2', source_ids: ['S2'], locators: ['l2'] },
    ],
  };

  it('the Conflicts stage counts only real conflicts, and says where the variation went', async () => {
    stub({
      list: listResponse(),
      detail: session({
        reconstruction: {
          ...session().reconstruction!,
          candidates: [SENDABLE, DISAGREEING, NO_WRITE_PATH, STRUCTURAL, VARIES],
        },
      }),
    });
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: IMPORT_COPY.actionStart }));
    await sessionOpen();
    // ONE conflict — the disagreement — in the tab, the summary and the stage.
    expect(screen.getByRole('tab', { name: new RegExp(IMPORT_STAGE_COPY.conflicts.title) }).textContent).toContain('1 open');
    const conflictsCount = document.querySelector('.hi-summary-item[data-id="conflicts"] dd');
    expect(conflictsCount?.textContent).toBe('1');
    const panel = goTo(IMPORT_STAGE_COPY.conflicts.title);
    expect(panel.querySelectorAll('li.hi-conflict')).toHaveLength(1);
    const note = panel.querySelector('.hi-varies-note')!;
    expect(note.textContent).toContain(IMPORT_STAGE_COPY.stateLabels.variesByScan);
    expect(note.textContent).toContain('1 value');
    expect(note.textContent).toContain('not conflicts');
  });
});

describe('§15 · an act is announced and lands focus on what it produced', () => {
  it('Add This Import: the report heading takes focus and the stage says it was sent', async () => {
    await openWithTwoSendable();
    await chooseRecordAndAdd();
    const heading = await screen.findByRole('heading', { name: IMPORT_COPY.addWholeResultTitle });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    const status = [...document.querySelectorAll('.hi-stages-card > [role="status"]')];
    expect(status).toHaveLength(1);
    expect(status[0].textContent).toBe('Sent to the record. The report is below.');
  });

  it('Reconstruct: moves to Runs & Candidates, focuses its heading and says so', async () => {
    stub({ list: listResponse(), detail: session({ reconstruction: null, furthest_step: 'parse' }) });
    const base = globalThis.fetch as unknown as (...a: unknown[]) => Promise<Response>;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(typeof input === 'string' ? input : (input as Request).url ?? input);
        if (url.endsWith('/reconstruct')) {
          return new Response(JSON.stringify({ import: session() }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        return base(input, init);
      }),
    );
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: IMPORT_COPY.actionStart }));
    await sessionOpen();
    goTo(IMPORT_STAGE_COPY.runs.title);
    fireEvent.click(screen.getByRole('button', { name: IMPORT_COPY.actionReconstruct }));
    await waitFor(() =>
      expect(document.querySelector('.hi-stages-card > [role="status"]')?.textContent).toBe(
        'Candidates reconstructed. Showing Runs & Candidates.',
      ),
    );
    const heading = screen.getByRole('heading', { name: IMPORT_STAGE_COPY.runs.title, level: 3 });
    await waitFor(() => expect(document.activeElement).toBe(heading));
  });
});
