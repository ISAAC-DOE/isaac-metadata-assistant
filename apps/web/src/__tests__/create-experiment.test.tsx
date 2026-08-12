/*
 * MY EXPERIMENTS — the redesigned empty state, and the Create Experiment path.
 *
 * THE ROUTE MAP IS A STRUCTURAL ASSERTION, exactly as it is in `tutorial-flow`:
 * `stubFetchRoutes` REJECTS any route it was not given, so a map without
 * `POST /api/experiments` proves a rendering test creates nothing, and a map
 * without `POST /api/uploads` proves nothing here imports.
 *
 * WHAT THIS FILE IS FOR, in one line each:
 *   1. the empty state's STRUCTURE and hierarchy — asserted on the classes and
 *      roles it introduces, not on a screenshot;
 *   2. the create path — happy, refused, and what it sends;
 *   3. the DURABILITY DISCLOSURE, in all three of its states, pinned so it cannot
 *      silently start implying durability it has not established.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { LABELS } from '../lib/labels';
import { setTutorialScope } from '../lib/api';
import { __bootTutorialStore, __resetTutorialStore } from '../lib/tutorialController';
import { __resetHealthCache } from '../lib/useHealth';
import { TUTORIAL_SESSION_ID } from '../test/apiFixtures';
import { TUTORIAL_SESSION_KEY } from '../lib/tutorialSession';
import {
  aboutResponse,
  bundleRoutes,
  graphStatusUnavailable,
  healthSynthetic,
  openApiFixture,
  stubFetchRoutes,
} from '../test/apiFixtures';

afterEach(() => {
  vi.unstubAllGlobals();
  __resetTutorialStore();
  /*
   * `useHealth` memoizes ONE in-flight promise at module scope, so without this the
   * first test in the file decides what every later test believes about durability
   * — and the three-state disclosure tests below would all be asserting about the
   * same stale body while appearing to vary it.
   */
  __resetHealthCache();
  sessionStorage.clear();
  localStorage.clear();
});

/** A minted id of the real shape: `RECORD_ID_RE` is `^[0-9A-Z]{26}$`. */
const NEW_ID = '01KZ0NEWEXPERIMENT00000001';

const created = {
  id: NEW_ID,
  title: 'Cu K-edge, run 3',
  status: 'needs_attention',
  created_utc: '2026-08-07T00:00:00Z',
  pending_count: 3,
  evidenced_field_count: 0,
  exported: false,
  record_id: null,
  scenario: null,
  draft_ok: true,
  version: 'abc.0',
  rev: 0,
};

/**
 * The reads My Experiments performs, with an EMPTY list — and nothing else.
 *
 * `storage` is threaded into `/api/health` so each test can put the deployment in
 * a known state. `undefined` omits the block entirely, which is what a build
 * predating it, and a health body that never arrived, both look like.
 */
function emptyRoutes(storage?: {
  configured: boolean;
  backend: string;
  durable: boolean;
  state?: string;
}) {
  return {
    'GET /api/health': {
      body: { ...healthSynthetic, ...(storage ? { experiment_storage: storage } : {}) },
    },
    'GET /api/experiments': { body: { experiments: [] } },
    'GET /api/graph/status': { body: graphStatusUnavailable },
    'GET /api/about': { body: aboutResponse },
    'GET /api/openapi': { body: openApiFixture },
  };
}

const DURABLE = { configured: true, backend: 'postgres', durable: true, state: 'durable' };
const EPHEMERAL = {
  configured: false,
  backend: 'filesystem',
  durable: false,
  state: 'ephemeral',
};
/**
 * A database IS configured, but not the one the write path requires — WITHOUT the
 * `state` field, i.e. the shape the FIRST version of this block served. Kept
 * deliberately: a deployment running an older image still sends exactly this, and
 * the boolean fallback has to keep reading it correctly.
 */
const DEGRADED_LEGACY = { configured: true, backend: 'filesystem', durable: false };
/** The same misconfiguration as served TODAY, with the state named. */
const DEGRADED = {
  configured: true,
  backend: 'filesystem',
  durable: false,
  state: 'unavailable',
};
/**
 * THE STATE THAT BROUGHT THE HOSTED APP DOWN. `PGHOST` and `PGDATABASE` are set on
 * the deployed pod, so the durable backend selects itself; the migration is applied
 * by an operator, so there is a window in which the table does not exist. `backend`
 * stays `postgres` — the app has NOT fallen back, it keeps trying — and `durable` is
 * false because it is not working.
 */
const UNAVAILABLE = {
  configured: true,
  backend: 'postgres',
  durable: false,
  state: 'unavailable',
};
/** A `state` value this build has never heard of. Must produce silence, not a guess. */
const FUTURE_STATE = {
  configured: true,
  backend: 'postgres',
  durable: false,
  state: 'something_invented_later',
};

function renderAt(path = '/experiments') {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

function panel(): HTMLElement {
  const found = document.querySelector<HTMLElement>('.queue-empty-state');
  expect(found, 'the empty state did not render').not.toBeNull();
  return found!;
}

/**
 * `state` is OPTIONAL in this signature on purpose: `DEGRADED_LEGACY` deliberately
 * omits it, because that is the shape a deployment predating the field still
 * serves and the boolean fallback has to keep reading it.
 */
async function openEmptyState(storage?: {
  configured: boolean;
  backend: string;
  durable: boolean;
  state?: string;
}) {
  stubFetchRoutes(emptyRoutes(storage) as never);
  const view = renderAt();
  await screen.findByRole('heading', { name: LABELS.emptyExperimentsTitle });
  return view;
}

// =============================================================================
// 1. the empty state is a real product surface
// =============================================================================

describe('My Experiments · the empty state', () => {
  it('is a contained panel with a heading, not prose floating in the page', async () => {
    await openEmptyState(EPHEMERAL);
    const section = panel();
    // A landmark with an accessible name, so it is reachable and announced as a
    // region rather than as three loose paragraphs.
    expect(section.tagName).toBe('SECTION');
    expect(section.getAttribute('aria-labelledby')).toBe('queue-empty-title');
    expect(
      within(section).getByRole('heading', { name: LABELS.emptyExperimentsTitle }),
    ).toBeInTheDocument();
    expect(section.textContent).toContain(LABELS.emptyExperimentsBody);
  });

  it('leads with the three actions and no architecture paragraph', async () => {
    await openEmptyState(EPHEMERAL);
    const section = panel();
    for (const name of [
      LABELS.actionCreateExperiment,
      LABELS.actionLaunchGuidedDemo,
      LABELS.actionOpenValidator,
    ]) {
      expect(within(section).getByRole('button', { name })).toBeInTheDocument();
    }
    /*
     * THE RETIRED SENTENCE, ASSERTED ABSENT. "This deployment cannot yet create or
     * import a record" was true when it was written and became false the moment
     * `POST /api/experiments` shipped. It is pinned here as well as in
     * `product-facing-language.test.tsx` because this is the surface that carried
     * it, and a revert in this file is the likeliest way it comes back.
     */
    expect(section.textContent).not.toMatch(/cannot yet create or import/i);
    expect(section.textContent).not.toMatch(/Or, without starting the walkthrough/i);
  });

  it('gives Create Experiment the strongest treatment and the other two a real one', async () => {
    await openEmptyState(EPHEMERAL);
    const section = panel();

    // Create is the SOLID primary — the one strongest action on the screen.
    const create = within(section).getByRole('button', { name: LABELS.actionCreateExperiment });
    expect(create).toHaveClass('btn-primary');

    /*
     * THE OTHER TWO, and the three treatments now read solid → tinted → grey.
     *
     * WHY OPEN VALIDATOR IS GREY AGAIN, since an earlier revision of this test
     * asserted the opposite and this would otherwise look like a regression. It was
     * promoted to `btn-action` when it was the ONLY control on this screen wearing
     * the grey treatment, sitting under a lead-in that literally read "Or, without
     * starting the walkthrough:" — a footnote by position as much as by tone.
     *
     * It is no longer a footnote for a STRUCTURAL reason, which is the better fix:
     * it has its own card, its own heading and its own description, the same shape
     * as the other two actions. Grey on a peer card is a tone; grey on a loose
     * button under a dismissive lead-in was a demotion. The defect that promotion
     * addressed is gone, so the promotion is not needed to hold it off.
     *
     * Launch Guided Demo keeps `btn-action` — the same `--action` blue, tinted
     * rather than filled. Asserted in both directions: "is blue" and "is not the
     * solid primary" are different claims.
     */
    const demo = within(section).getByRole('button', { name: LABELS.actionLaunchGuidedDemo });
    expect(demo, 'Launch Guided Demo lost the action treatment').toHaveClass('btn-action');
    expect(demo, 'Launch Guided Demo became a second primary').not.toHaveClass('btn-primary');

    const validator = within(section).getByRole('button', { name: LABELS.actionOpenValidator });
    expect(validator, 'Open Validator became a second primary').not.toHaveClass('btn-primary');
    expect(validator, 'Open Validator left the secondary treatment').toHaveClass('btn-secondary');

    /*
     * AND IT IS STILL A PEER, which is the property the promotion was really
     * protecting. Asserted on the STRUCTURE rather than on the button variant: it
     * carries the same card, the same heading level and the same description slot
     * as the guided demo, so nothing about it reads as a trailing footnote.
     */
    const cards = section.querySelectorAll('.queue-empty-action');
    expect(cards).toHaveLength(3);
    for (const card of cards) {
      expect(card.querySelector('.queue-empty-action-title')).not.toBeNull();
      expect(card.querySelector('.queue-empty-hint')).not.toBeNull();
    }

    // Exactly ONE primary in the panel: a second would make a reader stop and work
    // out which is the real one, on the screen where that matters most.
    expect(section.querySelectorAll('.btn-primary')).toHaveLength(1);
  });

  it('keeps Launch Guided Demo wired to the tutorial, with its disclosure and its guard', async () => {
    await openEmptyState(EPHEMERAL);
    const section = panel();
    const launch = within(section).getByRole('button', { name: LABELS.actionLaunchGuidedDemo });

    // The disclosure is DESCRIBED-BY, not part of the accessible name.
    expect(launch).toHaveAccessibleName(LABELS.actionLaunchGuidedDemo);
    expect(section.textContent).toContain(LABELS.launchGuidedDemoBody);
    expect(launch.getAttribute('aria-describedby')).toBe('queue-empty-launch-hint');
    // The double-submit guard is off while idle — its ON state is covered by
    // `tutorial-session-lifecycle.test.tsx` → T7e, which drives a real session.
    expect(launch).not.toBeDisabled();
  });

  it('renders nothing at all until the empty list has actually arrived', async () => {
    await openEmptyState(EPHEMERAL);
    // Sanity for the tests above: the panel is on the LOADED branch only, so none
    // of them is asserting about a loading placeholder.
    expect(document.querySelector('.exp-row')).toBeNull();
  });
});

// =============================================================================
// 2. the durability disclosure
// =============================================================================

describe('My Experiments · where a new experiment is stored', () => {
  it('says experiments are kept until the server restarts when there is no database', async () => {
    await openEmptyState(EPHEMERAL);
    const line = panel().querySelector<HTMLElement>('.queue-empty-storage');
    expect(line).not.toBeNull();
    expect(line!.dataset.durability).toBe('ephemeral');
    expect(line!.textContent).toBe(LABELS.storageEphemeral);
    /*
     * PINNED ON THE RENDERED TEXT, not on the label constant — a matcher reading
     * `LABELS.storageEphemeral` would pass no matter what that string said, which
     * is exactly how a disclosure starts quietly implying durability. The two
     * clauses that carry the meaning are asserted directly.
     */
    expect(line!.textContent).toMatch(/cleared when the server restarts/i);
    expect(line!.textContent).not.toMatch(/\bdatabase\b/i);
    expect(line!.textContent).not.toMatch(/\bpermanent(ly)?\b|\bforever\b|\bsaved\s+for\s+good\b/i);
  });

  it('promises durability only when the deployment actually has it', async () => {
    await openEmptyState(DURABLE);
    const line = panel().querySelector<HTMLElement>('.queue-empty-storage');
    expect(line!.dataset.durability).toBe('durable');
    expect(line!.textContent).toBe(LABELS.storageDurable);
    expect(line!.textContent).toMatch(/database/i);
    expect(line!.textContent).toMatch(/stay here across restarts/i);
    // The ephemeral claim is GONE, not merely reworded — keeping a "cleared on
    // restart" clause beside a durability promise would be a contradiction the
    // reader has to resolve.
    expect(line!.textContent).not.toMatch(/cleared|until the server restarts/i);
  });

  it('a configured-but-misconfigured database claims NO durability (legacy shape)', async () => {
    /*
     * The state that makes the two booleans worth keeping apart, as served by a
     * deployment predating the `state` field. A database is wired up, but the write
     * path refused its name, so the app degraded to the workspace directory.
     * Reporting `configured` as durability would promise exactly the thing that just
     * failed.
     *
     * `ephemeral` is the RIGHT reading for this shape and only for this shape: with
     * no `state`, `configured && !durable` could only be the PGDATABASE mismatch,
     * after which the app really does fall back to the workspace directory.
     */
    await openEmptyState(DEGRADED_LEGACY);
    const line = panel().querySelector<HTMLElement>('.queue-empty-storage');
    expect(line!.dataset.durability).toBe('ephemeral');
    expect(line!.textContent).not.toMatch(/database/i);
  });

  it('a configured database that is NOT ANSWERING says so, and promises nothing', async () => {
    /*
     * THE REGRESSION THIS SECTION EXISTS FOR. Before the backend named this state,
     * it reported `durable: true` while every read and write against the database
     * failed — so this line promised durability on the exact deployment where
     * creating an experiment could not work at all.
     */
    await openEmptyState(UNAVAILABLE);
    const line = panel().querySelector<HTMLElement>('.queue-empty-storage');
    expect(line).not.toBeNull();
    expect(line!.dataset.durability).toBe('unavailable');
    expect(line!.textContent).toBe(LABELS.storageUnavailable);
    /*
     * PINNED ON THE RENDERED TEXT, not on the label constant, for the reason the
     * ephemeral case states: a matcher reading the constant passes whatever the
     * constant says. Both directions are asserted — what it must say, and the two
     * false promises it must not make.
     */
    expect(line!.textContent).toMatch(/not answering/i);
    expect(line!.textContent).not.toMatch(/stay here across restarts|saved in this/i);
    expect(line!.textContent).not.toMatch(/cleared when the server restarts/i);
  });

  it('reads the NAMED state even when it disagrees with the boolean fallback', async () => {
    /*
     * `DEGRADED` and `DEGRADED_LEGACY` carry identical booleans and differ only in
     * `state`. If `state` were ignored, these two tests would be the same test and
     * one of them would be silently wrong.
     */
    await openEmptyState(DEGRADED);
    const line = panel().querySelector<HTMLElement>('.queue-empty-storage');
    expect(line!.dataset.durability).toBe('unavailable');
    expect(line!.textContent).toBe(LABELS.storageUnavailable);
  });

  it('says NOTHING for a state value this build does not recognise', async () => {
    /*
     * A future backend value must produce silence, not the nearest-looking
     * sentence. Falling back to the boolean here would read `durable: false` as
     * "ephemeral" and tell the reader their work is cleared on restart — a
     * confident claim derived from a word we could not read.
     */
    await openEmptyState(FUTURE_STATE);
    const section = panel();
    expect(section.querySelector('.queue-empty-storage')).toBeNull();
    expect(section.textContent).not.toMatch(/database|restart/i);
  });

  it('says NOTHING when durability has not been established', async () => {
    /*
     * `/api/health` without the block — an older build, or a body that never
     * arrived. The only honest thing to say about a property you have not
     * established is nothing: a hedge ("storage is being determined…") reads as a
     * claim about the reader's data rather than about our own state.
     */
    await openEmptyState(undefined);
    const section = panel();
    expect(section.querySelector('.queue-empty-storage')).toBeNull();
    expect(section.textContent).not.toMatch(/database|restart/i);
    // ...and the screen is otherwise fully functional: not knowing where a record
    // goes is not a reason to withhold the action.
    expect(
      within(section).getByRole('button', { name: LABELS.actionCreateExperiment }),
    ).toBeEnabled();
  });
});

// =============================================================================
// 3. creating
// =============================================================================

describe('My Experiments · Create Experiment', () => {
  it('opens a form that asks for a name and NOTHING scientific', async () => {
    await openEmptyState(EPHEMERAL);
    fireEvent.click(screen.getByRole('button', { name: LABELS.actionCreateExperiment }));

    expect(
      await screen.findByRole('heading', { name: LABELS.createExperimentFormTitle }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(LABELS.createExperimentTitleLabel)).toBeInTheDocument();
    expect(screen.getByLabelText(LABELS.createExperimentDescriptionLabel)).toBeInTheDocument();

    /*
     * THE NO-GUESSING ASSERTION ON THE UI SIDE. The form must not offer a place to
     * type an evidence-bearing scientific value: anything typed there would arrive
     * as an unsourced assertion, which is the exact thing the draft validator
     * exists to keep out of a record. Those are asked for by Guided Completion,
     * where an answer is recorded with its confirmation.
     */
    const form = document.querySelector<HTMLElement>('.create-experiment')!;
    expect(form.querySelectorAll('input, textarea, select')).toHaveLength(2);
    for (const forbidden of [/technique/i, /facility/i, /sample/i, /energy/i, /edge/i, /sha256/i]) {
      expect(form.textContent, `${forbidden} is offered by the create form`).not.toMatch(forbidden);
    }
    // And no id field, in either direction — the server mints it.
    expect(form.textContent).not.toMatch(/\bid\b/i);
  });

  it('creates the experiment and opens it', async () => {
    const calls = stubFetchRoutes({
      ...bundleRoutes(NEW_ID),
      ...emptyRoutes(EPHEMERAL),
      /*
       * ORDER MATTERS AND IT IS NOT COSMETIC: `bundleRoutes` re-declares
       * `GET /api/experiments` with one row, so spreading it LAST would make the
       * queue non-empty and the empty state would never render — the test would
       * then time out looking for a heading that was correct not to be there.
       */
      'POST /api/experiments': { status: 201, body: created },
    } as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.emptyExperimentsTitle });

    fireEvent.click(screen.getByRole('button', { name: LABELS.actionCreateExperiment }));
    fireEvent.change(await screen.findByLabelText(LABELS.createExperimentTitleLabel), {
      target: { value: '  Cu K-edge, run 3  ' },
    });
    fireEvent.change(screen.getByLabelText(LABELS.createExperimentDescriptionLabel), {
      target: { value: '  Beamline 4-1  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: LABELS.createExperimentSubmit }));

    await waitFor(() => expect(calls).toContain('POST /api/experiments'));
    const body = JSON.parse(
      (vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'POST')![1] as RequestInit)
        .body as string,
    );
    // Trimmed, and carrying ONLY the two fields the contract accepts. `extra="forbid"`
    // means a third would be a 422 — the client must not be the reason that happens.
    expect(body).toEqual({ title: 'Cu K-edge, run 3', description: 'Beamline 4-1' });

    // The reader lands on the record it just created.
    await waitFor(() => expect(document.querySelector('.queue-empty-state')).toBeNull());
  });

  it('omits an empty note rather than sending a blank string', async () => {
    stubFetchRoutes({
      ...bundleRoutes(NEW_ID),
      ...emptyRoutes(EPHEMERAL),
      'POST /api/experiments': { status: 201, body: created },
    } as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.emptyExperimentsTitle });

    fireEvent.click(screen.getByRole('button', { name: LABELS.actionCreateExperiment }));
    fireEvent.change(await screen.findByLabelText(LABELS.createExperimentTitleLabel), {
      target: { value: 'Untitled run' },
    });
    fireEvent.click(screen.getByRole('button', { name: LABELS.createExperimentSubmit }));

    await waitFor(() => {
      const post = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'POST');
      expect(post).toBeDefined();
      expect(JSON.parse((post![1] as RequestInit).body as string)).toEqual({
        title: 'Untitled run',
      });
    });
  });

  it('refuses an empty title WITHOUT calling the API', async () => {
    /*
     * The route map has no `POST /api/experiments`, so a request would throw and
     * fail this test — the refusal is proven structurally, not only by the
     * assertion below.
     */
    await openEmptyState(EPHEMERAL);
    fireEvent.click(screen.getByRole('button', { name: LABELS.actionCreateExperiment }));
    fireEvent.change(await screen.findByLabelText(LABELS.createExperimentTitleLabel), {
      target: { value: '   ' },
    });
    fireEvent.click(screen.getByRole('button', { name: LABELS.createExperimentSubmit }));

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toBe(LABELS.createExperimentTitleRequired);
    expect(screen.getByLabelText(LABELS.createExperimentTitleLabel)).toHaveAttribute(
      'aria-invalid',
      'true',
    );
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);
  });

  it('surfaces a failure and keeps the reader on the form', async () => {
    stubFetchRoutes({
      ...emptyRoutes(EPHEMERAL),
      'POST /api/experiments': { status: 500, body: { detail: 'boom' } },
    } as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.emptyExperimentsTitle });

    fireEvent.click(screen.getByRole('button', { name: LABELS.actionCreateExperiment }));
    fireEvent.change(await screen.findByLabelText(LABELS.createExperimentTitleLabel), {
      target: { value: 'Doomed' },
    });
    fireEvent.click(screen.getByRole('button', { name: LABELS.createExperimentSubmit }));

    await screen.findByRole('alert');
    // The typed title survives, so a retry does not start over — and the form is
    // still there rather than the reader having been navigated somewhere.
    expect(screen.getByLabelText(LABELS.createExperimentTitleLabel)).toHaveValue('Doomed');
    expect(screen.getByRole('button', { name: LABELS.createExperimentSubmit })).toBeEnabled();
  });

  /*
   * A SESSION THAT ENDED IS NAMED, because the remedy differs from every other
   * create failure: retrying the form cannot work, and only a reload can.
   *
   * The response modelled here is the one the infrastructure owner described on
   * 2026-08-12 — a 302 to Authentik that `fetch` followed, so the body arrives from
   * outside `API_BASE`. Before this, the form rendered the client's raw transport
   * sentence and the reader was left to guess.
   */
  it('names an ended session instead of showing the raw transport message', async () => {
    stubFetchRoutes({
      ...emptyRoutes(EPHEMERAL),
      'POST /api/experiments': {
        status: 200,
        contentType: 'application/xhtml+xml',
        redirected: true,
        url: 'https://auth.example.org/if/flow/default/',
        body: {},
      },
    } as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.emptyExperimentsTitle });

    fireEvent.click(screen.getByRole('button', { name: LABELS.actionCreateExperiment }));
    fireEvent.change(await screen.findByLabelText(LABELS.createExperimentTitleLabel), {
      target: { value: 'Interrupted' },
    });
    fireEvent.click(screen.getByRole('button', { name: LABELS.createExperimentSubmit }));

    const alert = await screen.findByRole('alert');
    expect(alert.textContent ?? '').toMatch(/sign in again/i);
    // The typed title still survives — the reader signs in and resubmits.
    expect(screen.getByLabelText(LABELS.createExperimentTitleLabel)).toHaveValue('Interrupted');
  });

  it('Cancel closes the form and returns focus to the control that opened it', async () => {
    await openEmptyState(EPHEMERAL);
    const open = screen.getByRole('button', { name: LABELS.actionCreateExperiment });
    fireEvent.click(open);
    fireEvent.click(await screen.findByRole('button', { name: LABELS.createExperimentCancel }));

    await waitFor(() =>
      expect(screen.queryByLabelText(LABELS.createExperimentTitleLabel)).toBeNull(),
    );
    const reopened = screen.getByRole('button', { name: LABELS.actionCreateExperiment });
    expect(document.activeElement).toBe(reopened);
  });
});

// =============================================================================
// 4. where the control is, and is not
// =============================================================================

describe('My Experiments · exactly one create control, in the right places', () => {
  it('the header carries it once the queue has rows', async () => {
    stubFetchRoutes({
      ...emptyRoutes(EPHEMERAL),
      ...bundleRoutes(NEW_ID),
    } as never);
    renderAt();
    await waitFor(() => expect(document.querySelector('.exp-row')).not.toBeNull());

    // Present, and present exactly ONCE: the empty state is not rendered, so the
    // header is the only place it can be.
    expect(screen.getAllByRole('button', { name: LABELS.actionCreateExperiment })).toHaveLength(1);
    expect(document.querySelector('.queue-empty-state')).toBeNull();
  });

  it('is never offered inside a worked-example session', async () => {
    /*
     * `POST /api/experiments` refuses a session header with 409 and writes nothing,
     * so a control here would be a button that looks like it acts and does not —
     * the exact failure mode two other controls were removed from this header for.
     *
     * Driven through the real session pointer rather than by mocking the screen, so
     * it exercises the same `useWorkspaceScope` value the list read uses.
     */
    /*
     * The two module bodies a page load evaluates, exactly as
     * `tutorial-session-lifecycle.test.tsx` documents them:
     *   setTutorialScope(id)  — what `api.ts`'s module body derives from storage;
     *   __bootTutorialStore() — what `tutorialController`'s module body does.
     *
     * `__resetTutorialStore()` cannot stand in for this: it CLEARS the scope and
     * the pointer, which is a page load with NO session — the opposite of the
     * state under test, and the test would pass for the wrong reason.
     */
    sessionStorage.setItem(
      TUTORIAL_SESSION_KEY,
      JSON.stringify({ sessionId: TUTORIAL_SESSION_ID, index: 0 }),
    );
    setTutorialScope(TUTORIAL_SESSION_ID);
    __bootTutorialStore();
    stubFetchRoutes({
      ...emptyRoutes(EPHEMERAL),
      ...bundleRoutes(NEW_ID),
    } as never);
    renderAt();
    await waitFor(() => expect(document.querySelector('.exp-row')).not.toBeNull());

    expect(screen.queryByRole('button', { name: LABELS.actionCreateExperiment })).toBeNull();
  });
});
