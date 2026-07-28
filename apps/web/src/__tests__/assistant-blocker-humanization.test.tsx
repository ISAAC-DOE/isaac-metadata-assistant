/*
 * P36V.1 Unit B — the two hosted-QA defects, end to end through the FREE-FORM
 * Assistant path.
 *
 * Hosted, the Assistant answered:
 *
 *   "1 path is listed as blocking export: $. Open Validate to run the
 *    deterministic schema check."
 *
 * Defect 1 — the raw JSONPath `$`. It comes from the TRUTH CORE:
 * `src/isaac_records/official.py:71` joins `err.absolute_path` and falls back to
 * the literal `"$"` when it is empty, which is every ROOT-level violation (a
 * missing required top-level property, a root type error, a root
 * `additionalProperties` error). `official.py` is NOT edited — the humanization is
 * display-only, and the exact locator is preserved in a `Technical Details`
 * disclosure.
 *
 * Defect 2 — "Open Validate" appeared inert. The brief's premise ("rename Open
 * Validate to Open Validator") was only half right: `OPEN_VALIDATOR_ACTION` was
 * ALREADY labelled "Open Validator", already targeted `/governance?tab=validator`,
 * and already resolved the `/krish` basename through the router — covered by
 * `open-validator-action.test.tsx`. The control the reader actually clicked was a
 * different one: the BACKEND emitted a cited-source chip
 * `{"label": "Open Validate", "navigate_to": base}` where `base` is `/record/<id>`
 * — the record already on screen. And `AssistantQueryResponse` had no `action`
 * field at all, so a free-form answer structurally could not render the working
 * button. The frontend retired the dead prose; the backend half never was.
 *
 * These tests therefore exercise the FREE-FORM path (the composer + the resolver
 * response), which the existing suite never covered for either defect.
 */

import { describe, it, expect, afterEach, vi, type Mock } from 'vitest';
import { render, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, useHref, useLocation, useNavigate } from 'react-router-dom';

import { AppRoutes } from '../App';
import { OPEN_VALIDATOR_ACTION, resolveAssistantAction } from '../lib/assistantComposer';
import type { AssistantQueryResponse } from '../lib/types';
import { bundleRoutes, stubFetchRoutes } from '../test/apiFixtures';

const REC = 'demo';
const RECORD_ROUTE = `/record/${REC}`;
const QUERY_ROUTE = `POST /api/experiments/${REC}/assistant/query`;

/** The retired control name, in either casing. It must never render again. */
const RETIRED_PROSE = /open Validate\b/i;

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/**
 * The resolver response for "why can't I export?" against a record whose ONLY
 * blocker is root-level — exactly what `apps/api/isaac_api/assistant_query.py`
 * now returns (pinned there by `test_root_level_blocker_is_never_reported_as_the_
 * raw_dollar_locator`).
 */
function rootBlockerAnswer(over: Partial<AssistantQueryResponse> = {}): AssistantQueryResponse {
  return {
    answer:
      '1 record-level validation issue may be blocking export. Open Validator to reach ' +
      'the deterministic schema check.',
    result: 'answered',
    grounding: ['schema'],
    // the self-navigating "Open Validate" chip is gone: an action is not a citation
    sources: [],
    record_rev: 3,
    version: '1.0',
    stale: false,
    followups: [],
    action: { kind: 'open-validator', label: 'Open Validator', to: '/governance?tab=validator' },
    technical_paths: ['$'],
    ...over,
  };
}

function routesWith(resp: AssistantQueryResponse) {
  return { ...bundleRoutes(REC), [QUERY_ROUTE]: { body: resp } };
}

/** Surfaces the live router location, steps Back, and resolves the action href. */
function RouterProbe() {
  const loc = useLocation();
  const navigate = useNavigate();
  const href = useHref(OPEN_VALIDATOR_ACTION.to);
  return (
    <div>
      <div data-testid="loc">{`${loc.pathname}${loc.search}`}</div>
      <div data-testid="href">{href}</div>
      <button type="button" onClick={() => navigate(-1)}>
        probe back
      </button>
      <button type="button" onClick={() => navigate(OPEN_VALIDATOR_ACTION.to)}>
        probe open validator
      </button>
    </div>
  );
}

function renderApp(entries: string[], opts: { basename?: string } = {}) {
  return render(
    <MemoryRouter
      initialEntries={entries}
      basename={opts.basename}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
      <RouterProbe />
    </MemoryRouter>,
  );
}

/** Every non-GET request the stubbed fetch saw. */
function writeRequests(): string[] {
  const fetchMock = globalThis.fetch as Mock | undefined;
  if (!fetchMock?.mock) return [];
  return (fetchMock.mock.calls as [string, RequestInit?][])
    .filter(([, init]) => (init?.method ?? 'GET').toUpperCase() !== 'GET')
    .map(([url, init]) => `${(init?.method ?? 'GET').toUpperCase()} ${String(url)}`);
}

/** Mount the Record Workbench and ask a free-form question through the composer. */
async function askFreeForm(
  resp: AssistantQueryResponse,
  opts: { basename?: string; question?: string } = {},
) {
  stubFetchRoutes(routesWith(resp));
  const prefix = opts.basename ?? '';
  const rendered = renderApp([`${prefix}${RECORD_ROUTE}`], opts);
  const assistant = (await waitFor(() => {
    const el = rendered.container.querySelector('.assistant');
    expect(el).not.toBeNull();
    return el as HTMLElement;
  })) as HTMLElement;
  const panel = within(assistant);
  const box = panel.getByRole('textbox', { name: /ask the assistant a question/i });
  fireEvent.change(box, { target: { value: opts.question ?? "why can't I export?" } });
  fireEvent.submit(box.closest('form')!);
  await waitFor(() => expect(panel.getByText(resp.answer)).toBeInTheDocument());
  return { ...rendered, assistant, panel };
}

// ---------------------------------------------------------------------------
// Defect 1 — the raw `$` never reaches the primary label
// ---------------------------------------------------------------------------

describe('P36V.1 Unit B · a root-level blocker reads as record-level, not as "$"', () => {
  it('the primary answer names the record; the raw "$" appears NOWHERE outside Technical Details', async () => {
    const { assistant, panel } = await askFreeForm(rootBlockerAnswer());

    const reply = assistant.querySelector('.assistant-reply') as HTMLElement;
    expect(reply.textContent).toContain('1 record-level validation issue may be blocking export.');
    // the PRIMARY visible label carries no raw locator …
    expect(reply.textContent).not.toContain('$');
    expect(reply.textContent).not.toMatch(/blocking export: \$/);
    expect(reply.textContent).not.toMatch(RETIRED_PROSE);

    // … the ONLY place it survives is the Technical Details disclosure
    const details = assistant.querySelector('details[data-details="technical"]') as HTMLDetailsElement;
    expect(details).not.toBeNull();
    expect(details.textContent).toContain('$');
    // and it is the only `$` in the whole panel
    const outside = assistant.textContent!.replace(details.textContent!, '');
    expect(outside).not.toContain('$');

    // it is a real, named, COLLAPSED disclosure — not pushed at the reader
    expect(details.open).toBe(false);
    expect(panel.getByText('Technical Details')).toBeInTheDocument();
  });

  it('the disclosure lists every exact locator, in order, and mixes root with nested', async () => {
    const { assistant } = await askFreeForm(
      rootBlockerAnswer({
        answer:
          '2 validation issues may be blocking export: the record itself, assets → 0 → sha256. ' +
          'Open Validator to reach the deterministic schema check.',
        technical_paths: ['$', 'assets.0.sha256'],
      }),
    );

    const reply = assistant.querySelector('.assistant-reply') as HTMLElement;
    expect(reply.textContent).toContain('the record itself, assets → 0 → sha256');
    expect(reply.textContent).not.toContain('$');

    const details = assistant.querySelector('details[data-details="technical"]') as HTMLElement;
    const items = [...details.querySelectorAll('li')].map((li) => li.textContent);
    expect(items).toEqual(['$', 'assets.0.sha256']);
  });

  it('an answer with no locators renders NO disclosure (never an empty one)', async () => {
    const { assistant } = await askFreeForm(
      rootBlockerAnswer({
        answer:
          'No blocking validation issues are listed in the current validation response. ' +
          'Open Validator to reach the deterministic schema check.',
        technical_paths: [],
      }),
    );
    expect(assistant.querySelector('details[data-details="technical"]')).toBeNull();
  });

  it('a malformed locator list can never render a blank row', async () => {
    const { assistant } = await askFreeForm(
      rootBlockerAnswer({
        technical_paths: ['', '   ', '$'] as unknown as string[],
      }),
    );
    const details = assistant.querySelector('details[data-details="technical"]') as HTMLElement;
    expect([...details.querySelectorAll('li')].map((li) => li.textContent)).toEqual(['$']);
  });

  it('a missing technical_paths field (an older backend) renders no disclosure and does not throw', async () => {
    const resp = rootBlockerAnswer();
    delete (resp as Partial<AssistantQueryResponse>).technical_paths;
    const { assistant } = await askFreeForm(resp);
    expect(assistant.querySelector('details[data-details="technical"]')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// P36V.1 review IMPORTANT-1 — a validation CRASH is not a validation issue
//
// `routes.py` returns `[{path:'$', message:'Validation could not be completed.'}]`
// when the dry-run itself raised. The backend now describes that honestly
// (pinned in `test_assistant_query.py::test_a_validation_crash_is_never_described_
// as_a_validation_issue`); this is the RENDERED consequence: no locator disclosure
// is offered for a crash, because no locator was reported.
// ---------------------------------------------------------------------------

const CRASH_ANSWER =
  'The deterministic schema check could not be completed for this record, so no ' +
  'blocking locations can be listed. Open Validator to reach the deterministic ' +
  'schema check.';

describe('P36V.1 review IMPORTANT-1 · a crash renders no locators and claims no issue', () => {
  it('shows the honest sentence, NO Technical Details, and still offers Open Validator', async () => {
    const { assistant, panel } = await askFreeForm(
      rootBlockerAnswer({
        answer: CRASH_ANSWER,
        result: 'insufficient_context',
        technical_paths: [],
      }),
    );

    const reply = assistant.querySelector('.assistant-reply') as HTMLElement;
    expect(reply.textContent).toContain('could not be completed for this record');
    expect(reply.textContent).not.toMatch(/validation issue/);
    expect(reply.textContent).not.toMatch(/record-level/);
    expect(reply.textContent).not.toContain('$');
    // the disclosure is the ONLY place a locator may appear — and there is none
    expect(assistant.querySelector('details[data-details="technical"]')).toBeNull();
    expect(panel.queryByText('Technical Details')).toBeNull();
    expect(panel.getByRole('button', { name: /Open Validator/ })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// P36V.1 review IMPORTANT-3 — a cited source opens the surface it NAMES
//
// "Complete Metadata" and "Evidence & Sources" carried `navigate_to = /record/<id>`
// — the record page the question was asked from — so on the Record Workbench mount
// clicking them did nothing visible: the same inert-click defect this slice exists
// to fix. The backend now targets the record SUB-surfaces; these tests prove the
// targets are real client routes that render, and that the click transitions.
// ---------------------------------------------------------------------------

function citedAnswer(label: string, to: string): AssistantQueryResponse {
  return rootBlockerAnswer({
    answer: '5 fields still need you: Formula, Edge, Beamline, …and 2 more.',
    result: 'answered',
    grounding: ['workflow'],
    sources: [{ label, navigate_to: to }],
    action: null,
    technical_paths: [],
  });
}

describe('P36V.1 review IMPORTANT-3 · cited sources reach the surface they name', () => {
  it('"Complete Metadata" navigates to Guided Completion, not to the record already on screen', async () => {
    const { panel } = await askFreeForm(
      citedAnswer('Complete Metadata', `${RECORD_ROUTE}/complete`),
      { question: 'what still needs me?' },
    );

    const chip = panel.getByRole('button', { name: /Complete Metadata/ });
    fireEvent.click(chip);

    await waitFor(() =>
      expect(screen.getByTestId('loc').textContent).toBe(`${RECORD_ROUTE}/complete`),
    );
    // the target is a REAL route that renders (not a redirect back to the record)
    expect(await screen.findByText('Complete Missing Fields')).toBeInTheDocument();
    expect(screen.getByTestId('loc').textContent).not.toBe(RECORD_ROUTE);
  });

  it('"Evidence & Sources" navigates to the Evidence Explorer', async () => {
    const { panel } = await askFreeForm(
      citedAnswer('Evidence & Sources', `${RECORD_ROUTE}/evidence`),
      { question: 'where did the formula come from' },
    );

    fireEvent.click(panel.getByRole('button', { name: /Evidence & Sources/ }));

    await waitFor(() =>
      expect(screen.getByTestId('loc').textContent).toBe(`${RECORD_ROUTE}/evidence`),
    );
    // the target is a REAL route that renders (the screen names itself in both its
    // top bar and its screen-level heading, hence findAll)
    expect((await screen.findAllByText('Evidence & File Preview')).length).toBeGreaterThan(0);
  });

  it('both new targets pass the panel\'s client-route allowlist and keep the /krish base path', async () => {
    const { panel } = await askFreeForm(
      citedAnswer('Complete Metadata', `${RECORD_ROUTE}/complete`),
      { basename: '/krish', question: 'what still needs me?' },
    );
    // rendered as a NAVIGATING chip (the allowlist admitted it) …
    const chip = panel.getByRole('button', { name: /Complete Metadata/ });
    expect(chip.className).toContain('assistant-source-chip-nav');

    fireEvent.click(chip);

    // … and the router resolves it under the basename, with no page reload
    await waitFor(() =>
      expect(screen.getByTestId('loc').textContent).toBe(`${RECORD_ROUTE}/complete`),
    );
    expect(window.location.pathname).not.toContain('/record');
  });
});

// ---------------------------------------------------------------------------
// Defect 2 — the free-form answer's validate affordance actually works
// ---------------------------------------------------------------------------

const openValidator = () => screen.getByRole('button', { name: /Open Validator/ });

describe('P36V.1 Unit B · a FREE-FORM answer renders the working Open Validator control', () => {
  it('renders it as a Proposed Action button — the response contract now carries the action', async () => {
    const { assistant, panel } = await askFreeForm(rootBlockerAnswer());

    const go = panel.getByRole('button', { name: /Open Validator/ });
    expect(go.tagName).toBe('BUTTON');
    const region = go.closest('.assistant-proposed') as HTMLElement;
    expect(region).not.toBeNull();
    expect(region.textContent).toMatch(/not applied/i);
    // it is not a chat message and not a citation chip
    expect(go.closest('.assistant-log')).toBeNull();
    expect(go.closest('.assistant-provenance')).toBeNull();
    // the retired control name is gone from the whole panel
    expect(assistant.textContent).not.toMatch(RETIRED_PROSE);
  });

  it('an answer that carries NO action offers no control (nothing new was surfaced)', async () => {
    const resp = rootBlockerAnswer({ action: null, technical_paths: [] });
    const { panel } = await askFreeForm(resp, { question: 'what still needs me?' });
    expect(panel.queryByRole('button', { name: /Open Validator/ })).toBeNull();
  });

  it('an UNKNOWN action kind from the wire is dropped, never rendered', async () => {
    const { panel } = await askFreeForm(
      rootBlockerAnswer({
        action: { kind: 'delete-everything', label: 'Delete Everything', to: '/record/demo' },
      }),
    );
    expect(panel.queryByRole('button', { name: /Delete Everything/ })).toBeNull();
    expect(panel.queryByRole('button', { name: /Open Validator/ })).toBeNull();
  });

  it('the wire label and target are NOT trusted — the frontend catalog owns both', () => {
    // a hostile wire descriptor resolves to this build's own frozen descriptor
    expect(
      resolveAssistantAction({
        kind: 'open-validator',
        label: 'Delete The Record',
        to: 'https://evil.example',
      }),
    ).toBe(OPEN_VALIDATOR_ACTION);
    // and every malformed shape resolves to nothing
    for (const raw of [null, undefined, 0, 'open-validator', [], {}, { kind: 7 }, { kind: 'x' }]) {
      expect(resolveAssistantAction(raw)).toBeUndefined();
    }
  });

  it('the backend action mirrors the frontend descriptor exactly (cross-language parity)', () => {
    // The value asserted here is the literal the backend emits, pinned on the
    // Python side by `test_export_blockers_carries_the_open_validator_action_...`.
    expect(
      resolveAssistantAction({
        kind: 'open-validator',
        label: 'Open Validator',
        to: '/governance?tab=validator',
      }),
    ).toEqual(OPEN_VALIDATOR_ACTION);
  });
});

// ---------------------------------------------------------------------------
// The required integration path: activate → route → tab → focus → Back → no mutation
// ---------------------------------------------------------------------------

describe('P36V.1 Unit B · activating the free-form Open Validator reaches the Validator', () => {
  it('lands on Governance & Safety → Validator with the tab genuinely selected', async () => {
    await askFreeForm(rootBlockerAnswer());

    fireEvent.click(openValidator());

    await waitFor(() =>
      expect(screen.getByTestId('loc').textContent).toBe('/governance?tab=validator'),
    );
    expect(screen.getByRole('tab', { name: 'Validator' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByRole('tab', { name: 'Policy' })).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByRole('heading', { name: 'Standalone Validator' })).toBeInTheDocument();
    expect(screen.getByLabelText(/candidate record \(json\)/i)).toBeInTheDocument();
  });

  it('moves focus to the Validator heading on arrival', async () => {
    await askFreeForm(rootBlockerAnswer());

    fireEvent.click(openValidator());

    const heading = await screen.findByRole('heading', { name: 'Standalone Validator' });
    await waitFor(() => expect(heading).toHaveFocus());
    // a programmatic target only — never added to the Tab order
    expect(heading).toHaveAttribute('tabindex', '-1');
  });

  it('is a history PUSH: Back returns to the record the reader came from', async () => {
    await askFreeForm(rootBlockerAnswer());

    fireEvent.click(openValidator());
    await waitFor(() =>
      expect(screen.getByTestId('loc').textContent).toBe('/governance?tab=validator'),
    );

    fireEvent.click(screen.getByRole('button', { name: 'probe back' }));
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe(RECORD_ROUTE));
  });

  it('preserves the deployed /krish base path and never reloads the page', async () => {
    const before = `${window.location.pathname}${window.location.search}`;
    await askFreeForm(rootBlockerAnswer(), { basename: '/krish' });

    // the router resolves the action target UNDER the basename …
    expect(screen.getByTestId('href').textContent).toBe('/krish/governance?tab=validator');

    const go = openValidator();
    // … and it is a BUTTON, so no document-level navigation can occur
    expect(go.tagName).toBe('BUTTON');
    expect(go.getAttribute('type')).toBe('button');
    expect(go.hasAttribute('href')).toBe(false);
    expect(go.closest('form')).toBeNull();

    fireEvent.click(go);

    await waitFor(() =>
      expect(screen.getByTestId('loc').textContent).toBe('/governance?tab=validator'),
    );
    expect(screen.getByRole('tab', { name: 'Validator' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(`${window.location.pathname}${window.location.search}`).toBe(before);
  });

  it('mutates NO record: the only writes are the record screen dry-runs and the read-only query', async () => {
    await askFreeForm(rootBlockerAnswer());
    const titleBefore = (await screen.findByText(/Synthetic XANES/)).textContent;

    fireEvent.click(openValidator());
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Standalone Validator' })).toBeInTheDocument(),
    );

    // every non-GET request is either a pre-existing screen dry-run or the
    // read-only assistant query — never /answers, /edit, /export, /reset
    for (const req of writeRequests()) {
      expect(req).toMatch(/\/(validate|audit|assistant\/query)$/);
    }
    // the Validator's own POST /api/validate/record was NOT triggered by arriving
    expect(writeRequests().some((r) => r.includes('/api/validate/record'))).toBe(false);

    // Back to the record: it renders exactly the same data it did before. (The
    // record screen unmounts on navigation, so the ORIGINAL node is necessarily
    // detached — the meaningful assertion is that the re-mounted screen shows the
    // same record, with still no mutating request having been issued.)
    fireEvent.click(screen.getByRole('button', { name: 'probe back' }));
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe(RECORD_ROUTE));
    expect((await screen.findByText(/Synthetic XANES/)).textContent).toBe(titleBefore);
    for (const req of writeRequests()) {
      expect(req).toMatch(/\/(validate|audit|assistant\/query)$/);
    }
  });

  it('arriving again at the Validator still moves focus (never perceptibly dead)', async () => {
    await askFreeForm(rootBlockerAnswer());

    fireEvent.click(openValidator());
    const heading = await screen.findByRole('heading', { name: 'Standalone Validator' });
    await waitFor(() => expect(heading).toHaveFocus());

    // move focus away, then navigate AGAIN to the identical Validator URL — the
    // same target the action carries. `location.key` changes on every navigation,
    // so the arrival effect re-runs and the surface is never perceptibly dead.
    (screen.getByRole('button', { name: 'probe back' }) as HTMLButtonElement).focus();
    expect(heading).not.toHaveFocus();

    fireEvent.click(screen.getByRole('button', { name: 'probe open validator' }));

    await waitFor(() => expect(heading).toHaveFocus());
    expect(screen.getByTestId('loc').textContent).toBe('/governance?tab=validator');
    expect(screen.getByRole('tab', { name: 'Validator' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });
});
