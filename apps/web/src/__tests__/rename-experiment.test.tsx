/*
 * RENAME — the affordance a scientist did not have.
 *
 * `title` was written exactly once, by `POST /api/experiments`, and no operation
 * could change it. With `0001_experiments` applied to the hosted database that made
 * every mistakenly created experiment permanent, with its typo.
 *
 * WHAT WOULD FAIL BEFORE THE BEHAVIOUR EACH TEST DEFENDS. Every one of these is a
 * way this panel could be built that renders fine, looks finished, and still loses a
 * reader's work or tells them something false:
 *
 *   1. The panel exists but nothing mounts it. A component test that renders it
 *      standalone passes either way, so the affordance is asserted on the REAL
 *      screen, through the router. (`the record screen mounts it`)
 *   2. A save that refreshes the record the LOADING way. `RecordWorkbench` unmounts
 *      its whole loaded body while its fetch is not in `data`, so the loud reload
 *      destroys this panel mid-announcement, blanks the screen, and drops focus to
 *      `<body>`. (`saving refreshes the record silently`)
 *   3. A 412 whose message clears on the next keystroke, while the client still
 *      holds exactly the validator that was rejected — so the next Save re-sends it,
 *      is refused again, and the message flickers. (`a stale-write refusal stands…`)
 *   4. A refusal that also destroys what the reader typed. This repository has fixed
 *      that class four times. (`a refusal keeps the typed title`)
 *   5. The over-limit case silently truncated by `maxLength`, so a pasted title is
 *      cut and the reader is told nothing. (`too long is refused in words…`)
 *   6. A note field. `PATCH /api/experiments/{id}` refuses `description` with a 422,
 *      because the server stores it at `source.description` and also reads it as the
 *      provenance marker deciding whether a record belongs to the managed example
 *      dataset. A form offering one would promise an edit the server refuses.
 *      (`it offers no note field, and sends none`)
 *   7. Focus left behind on a control that no longer exists.
 *      (`focus moves into the box…`, `…and back to the button`)
 *
 * Every fixture is synthetic and no test here reaches a backend.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import axe from 'axe-core';
import { cleanup, render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { RenameExperimentPanel } from '../components/RenameExperimentPanel';
import { AppRoutes } from '../App';
import { LABELS } from '../lib/labels';
import { bundleRoutes, experimentDetail, stubFetchRoutes } from '../test/apiFixtures';
import type { ApiExperimentDetail } from '../lib/types';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const TYPO = 'Cu K-edge, first attemt';
const FIXED = 'Cu K-edge, first attempt';

function detail(over: Partial<ApiExperimentDetail> = {}): ApiExperimentDetail {
  return { ...experimentDetail, id: 'demo', title: TYPO, ...over } as ApiExperimentDetail;
}

/** Render the panel and open its section, which is collapsed on arrival. */
function renderPanel(props: Partial<Parameters<typeof RenameExperimentPanel>[0]> = {}) {
  const onSaved = props.onSaved ?? vi.fn();
  const utils = render(
    <RenameExperimentPanel detail={props.detail ?? detail()} onSaved={onSaved} />,
  );
  fireEvent.click(screen.getByRole('button', { name: /Experiment Name/ }));
  return { ...utils, onSaved };
}

function openForm() {
  fireEvent.click(screen.getByRole('button', { name: LABELS.actionRenameExperiment }));
  return screen.getByLabelText(LABELS.renameTitleLabel) as HTMLInputElement;
}

// =============================================================================
// 1. it is REACHABLE on the real screen — not merely renderable in isolation
// =============================================================================

describe('the affordance is reachable', () => {
  it('the record screen mounts it', async () => {
    stubFetchRoutes({
      ...bundleRoutes('demo'),
      'GET /api/experiments/demo': { body: { ...experimentDetail, id: 'demo', title: TYPO } },
    });
    render(
      <MemoryRouter
        initialEntries={['/record/demo']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );
    const header = await screen.findByRole('button', { name: /Experiment Name/ });
    fireEvent.click(header);
    expect(
      await screen.findByRole('button', { name: LABELS.actionRenameExperiment }),
    ).toBeInTheDocument();
  }, 20000);

  it('renaming on the real screen does not blank the record', async () => {
    /*
     * THE DEFECT THIS PINS, AND IT IS NOT HYPOTHETICAL — it is what the unverified
     * snapshot branch shipped. `RecordWorkbench` unmounts its ENTIRE loaded body
     * whenever its fetch is not in the `data` state, and `onManualRefresh` is
     * `bundle.reload`, the variant that flips back to loading. Wiring the save to
     * it destroys this panel mid-announcement, replaces the whole screen with a
     * loading panel, and drops focus to `<body>`.
     *
     * Asserted at the SCREEN, through the router, because a panel test with a
     * `vi.fn()` for `onSaved` cannot see which refresh the screen chose.
     */
    /*
     * THE REFETCH IS HELD OPEN, and that is what makes this test able to see the
     * difference at all. A first version asserted the absence of the loading panel
     * AFTER awaiting the announcement, and the loud reload SURVIVED it — measured —
     * because the stubbed refetch resolved before the assertion ran, so the flip
     * happened and was over. Holding the second detail read open means the loud
     * reload leaves this screen in its loading state for as long as the test looks,
     * with this panel unmounted and the announcement unreachable.
     */
    let reads = 0;
    stubFetchRoutes({
      ...bundleRoutes('demo'),
      'GET /api/experiments/demo': () => {
        reads += 1;
        if (reads === 1) return { body: { ...experimentDetail, id: 'demo', title: TYPO } };
        return new Promise<never>(() => {}); // never settles
      },
      'PATCH /api/experiments/demo': { body: { ...experimentDetail, id: 'demo', title: FIXED } },
    });
    render(
      <MemoryRouter
        initialEntries={['/record/demo']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByRole('button', { name: /Experiment Name/ }));
    fireEvent.change(openForm(), { target: { value: FIXED } });
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameSubmit }));

    const announced = await screen.findByText(LABELS.renameSaved);
    // and it landed in a region that was already live, not one inserted with it
    expect(announced).toHaveAttribute('role', 'status');
    // The screen is still the record while the refresh is in flight, not a loading panel.
    expect(screen.queryByText(/Loading the record from the ISAAC API/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Experiment Name/ })).toBeInTheDocument();
    expect(reads).toBeGreaterThan(1); // the refresh really was issued
  }, 20000);

  it('is collapsed on arrival, so a reader who never renames pays one line for it', () => {
    render(<RenameExperimentPanel detail={detail()} onSaved={vi.fn()} />);
    expect(screen.getByRole('button', { name: /Experiment Name/ })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    expect(
      screen.queryByRole('button', { name: LABELS.actionRenameExperiment }),
    ).not.toBeInTheDocument();
  });

  it('shows the name it is offering to change', () => {
    renderPanel();
    expect(screen.getByText(TYPO)).toBeInTheDocument();
  });

  it('the live region is in the DOM BEFORE there is anything to announce', () => {
    /*
     * Measured, not assumed: asserting `role="status"` on the element found AFTER a
     * save passes whether the region was already there or was inserted with its own
     * content — the mutation that inserts it survived exactly that assertion. A live
     * region created together with its text is announced unreliably, so what has to
     * be pinned is its presence while it is still empty.
     */
    const { container } = renderPanel();
    const region = container.querySelector('[role="status"]');
    expect(region).not.toBeNull();
    expect(region?.textContent).toBe('');
  });
});

// =============================================================================
// 2. the happy path, and what it sends
// =============================================================================

describe('renaming', () => {
  it('sends exactly the trimmed title and the record’s own validator', async () => {
    const calls = stubFetchRoutes({
      'PATCH /api/experiments/demo': { body: { ...experimentDetail, id: 'demo', title: FIXED } },
    });
    const onSaved = vi.fn();
    renderPanel({ onSaved });
    const input = openForm();
    fireEvent.change(input, { target: { value: `  ${FIXED}  ` } });
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameSubmit }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(calls).toEqual(['PATCH /api/experiments/demo']);
    const init = (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({ title: FIXED });
    expect((init.headers as Record<string, string>)['If-Match']).toBe(
      `"${experimentDetail.version}"`,
    );
  });

  it('offers no note field, and sends none', async () => {
    const calls = stubFetchRoutes({
      'PATCH /api/experiments/demo': { body: { ...experimentDetail, id: 'demo', title: FIXED } },
    });
    renderPanel();
    openForm();
    // The create form's note label must not appear here: the server refuses the key.
    expect(
      screen.queryByLabelText(LABELS.createExperimentDescriptionLabel),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: /note/i })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(LABELS.renameTitleLabel), {
      target: { value: FIXED },
    });
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameSubmit }));
    await waitFor(() => expect(calls.length).toBe(1));
    const init = (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls[0][1] as RequestInit;
    expect(Object.keys(JSON.parse(String(init.body)))).toEqual(['title']);
  });

  it('saving refreshes the record silently and confirms the act in a live region', async () => {
    stubFetchRoutes({
      'PATCH /api/experiments/demo': { body: { ...experimentDetail, id: 'demo', title: FIXED } },
    });
    const onSaved = vi.fn();
    renderPanel({ onSaved });
    fireEvent.change(openForm(), { target: { value: FIXED } });
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameSubmit }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    // The confirmation lands in a region that was ALREADY in the DOM — a live region
    // inserted together with its content is announced unreliably.
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(LABELS.renameSaved),
    );
    // and the form has closed, so the panel is back to its read state
    expect(screen.getByRole('button', { name: LABELS.actionRenameExperiment })).toBeInTheDocument();
  });

  it('a blank version sends NO If-Match rather than a malformed empty one', async () => {
    /*
     * The truthiness guard every other mutation in `api.ts` carries, for its reason:
     * `If-Match: ""` is malformed and the server answers 400, which reports a client
     * bug as a server disagreement. Sending no header at all is a 428 that names the
     * missing precondition — the honest failure.
     */
    stubFetchRoutes({
      'PATCH /api/experiments/demo': { body: { ...experimentDetail, id: 'demo', title: FIXED } },
    });
    renderPanel({ detail: detail({ version: '' }) });
    fireEvent.change(openForm(), { target: { value: FIXED } });
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameSubmit }));

    await waitFor(() =>
      expect((globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls.length).toBe(1),
    );
    const init = (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>)['If-Match']).toBeUndefined();
  });

  it('a re-sent identical title is still sent — the server decides it is a no-op', async () => {
    const calls = stubFetchRoutes({
      'PATCH /api/experiments/demo': { body: { ...experimentDetail, id: 'demo', title: TYPO } },
    });
    renderPanel();
    openForm();
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameSubmit }));
    await waitFor(() => expect(calls).toEqual(['PATCH /api/experiments/demo']));
  });
});

// =============================================================================
// 3. refusals — each one keeps what the reader typed
// =============================================================================

describe('refusals', () => {
  it('a blank title is refused before anything is sent', async () => {
    const calls = stubFetchRoutes({});
    renderPanel();
    fireEvent.change(openForm(), { target: { value: '   ' } });
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameSubmit }));

    expect(await screen.findByRole('alert')).toHaveTextContent(LABELS.renameTitleRequired);
    expect(calls).toEqual([]);
    // and the box still holds what they typed
    expect(screen.getByLabelText(LABELS.renameTitleLabel)).toHaveValue('   ');
  });

  it('too long is refused in words, and nothing the reader typed is cut', async () => {
    const calls = stubFetchRoutes({});
    renderPanel();
    const input = openForm();
    const long = 'x'.repeat(203);
    fireEvent.change(input, { target: { value: long } });
    // The control carries no `maxLength`, so the browser cannot silently truncate.
    expect(input).not.toHaveAttribute('maxLength');
    expect(input).toHaveValue(long);
    // The counter says how far over, in words rather than in colour alone.
    expect(screen.getByText(/3 over the 200-character limit/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: LABELS.renameSubmit }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/3 characters over/);
    expect(calls).toEqual([]);
    expect(screen.getByLabelText(LABELS.renameTitleLabel)).toHaveValue(long);
  });

  it('a refusal keeps the typed title', async () => {
    stubFetchRoutes({
      'PATCH /api/experiments/demo': { status: 422, body: { error: 'invalid_title' } },
    });
    renderPanel();
    fireEvent.change(openForm(), { target: { value: FIXED } });
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameSubmit }));

    await screen.findByRole('alert');
    expect(screen.getByLabelText(LABELS.renameTitleLabel)).toHaveValue(FIXED);
  });

  it('a stale-write refusal stands until a newer record arrives, and blocks a retry that would repeat it', async () => {
    stubFetchRoutes({
      'PATCH /api/experiments/demo': { status: 412, body: { error: 'stale_write' } },
    });
    const onSaved = vi.fn();
    const { rerender } = render(
      <RenameExperimentPanel detail={detail()} onSaved={onSaved} />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Experiment Name/ }));
    fireEvent.change(openForm(), { target: { value: FIXED } });
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameSubmit }));

    expect(await screen.findByRole('alert')).toHaveTextContent(LABELS.renameStale);
    // the record was refreshed, so a retry has something newer to hold
    expect(onSaved).toHaveBeenCalled();
    // Typing does NOT clear it: the validator is still the rejected one.
    fireEvent.change(screen.getByLabelText(LABELS.renameTitleLabel), {
      target: { value: `${FIXED}!` },
    });
    expect(screen.getByRole('alert')).toHaveTextContent(LABELS.renameStale);
    expect(screen.getByRole('button', { name: LABELS.renameSubmit })).toBeDisabled();

    // A refreshed record carrying a DIFFERENT version retires it, and only that.
    rerender(
      <RenameExperimentPanel
        detail={detail({ version: `${experimentDetail.version}-next` })}
        onSaved={onSaved}
      />,
    );
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: LABELS.renameSubmit })).toBeEnabled();
    // and what they typed survived all of it
    expect(screen.getByLabelText(LABELS.renameTitleLabel)).toHaveValue(`${FIXED}!`);
  });
});

// =============================================================================
// 4. keyboard and screen reader
// =============================================================================

describe('accessibility', () => {
  it('has no axe violation in either state', async () => {
    const rules = [
      'label',
      'aria-valid-attr-value',
      'aria-required-attr',
      'button-name',
      'aria-allowed-attr',
      'form-field-multiple-labels',
    ];
    const { container } = renderPanel();
    const read = await axe.run(container, {
      runOnly: { type: 'rule', values: rules },
      resultTypes: ['violations'],
    });
    expect(read.violations.map((v) => `${v.id} × ${v.nodes.length}`)).toEqual([]);

    openForm();
    const editing = await axe.run(container, {
      runOnly: { type: 'rule', values: rules },
      resultTypes: ['violations'],
    });
    expect(editing.violations.map((v) => `${v.id} × ${v.nodes.length}`)).toEqual([]);
  });

  it('the box is named by a real label and described by the limit', () => {
    renderPanel();
    const input = openForm();
    const described = (input.getAttribute('aria-describedby') ?? '').split(/\s+/).filter(Boolean);
    expect(described.length).toBeGreaterThan(0);
    const text = described
      .map((id) => document.getElementById(id)?.textContent ?? '')
      .join(' ');
    expect(text).toMatch(/200 characters/);
  });

  it('focus moves into the box when the form opens, and back to the button when it closes', () => {
    renderPanel();
    const input = openForm();
    expect(document.activeElement).toBe(input);
    fireEvent.click(screen.getByRole('button', { name: LABELS.renameCancel }));
    expect(document.activeElement).toBe(
      screen.getByRole('button', { name: LABELS.actionRenameExperiment }),
    );
  });

  it('the section header states what it is, so it can be found without opening it', () => {
    render(<RenameExperimentPanel detail={detail()} onSaved={vi.fn()} />);
    const section = screen.getByRole('region', { name: /Experiment Name/ });
    expect(within(section).getByRole('button', { name: /Experiment Name/ })).toBeInTheDocument();
  });
});
