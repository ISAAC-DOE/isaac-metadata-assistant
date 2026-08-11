/*
 * PER-RUN OVERRIDES — the seven states this surface can be in, and the four
 * sentences it is not allowed to say.
 *
 * WHAT IS UNDER TEST HERE AND WHAT IS NOT. The DOMAIN properties — that an
 * override on one run does not touch its sibling, that it never mutates the
 * record, that a record edit still flows through to runs that inherit, that
 * export and validation read the resolved value — belong to the backend and are
 * pinned there (`apps/api/tests/test_run_api.py`,
 * `apps/api/tests/test_export_fan_out.py`). Re-asserting them over a fetch stub
 * would prove only that the stub returns what the stub was told to return.
 *
 * What this file pins is everything the UI could get wrong ON TOP of a correct
 * backend, and every one of them is a way of LYING to a scientist:
 *
 *   · reporting success for a write the server refused (422) or lost (412);
 *   · reporting a no-op as a change;
 *   · confirming on the reader's behalf;
 *   · rendering a generic failure where the server sent a specific, typed one;
 *   · showing an override that cannot be told from an inherited value without
 *     colour;
 *   · sending an envelope the no-guessing rules would refuse, or one carrying a
 *     value nobody typed.
 *
 * THE ASSERTIONS ARE MADE ON THE REQUEST THAT LEFT, not only on the screen. A
 * panel that renders beautifully and sends `confirmed_by_user: false` is a
 * broken panel, and the reverse — sending `true` from a control the reader never
 * touched — is worse.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useState } from 'react';

import { RunInheritedPanel } from '../components/RunInheritedPanel';
import { stubFetchRoutes, type RouteEntry } from '../test/apiFixtures';
import type { ApiRunView } from '../lib/types';

const EXP = 'demo';
const RUN = 'RUNAAA';
const OVERRIDES = `POST /api/experiments/${EXP}/runs/${RUN}/overrides`;
const CLEAR = `POST /api/experiments/${EXP}/runs/${RUN}/overrides/clear`;
const GET_RUN = `GET /api/experiments/${EXP}/runs/${RUN}`;

const MATERIAL = 'field:sample.material.name';
const DIAMETER = 'field:sample.geometry.pellet_diameter_mm';
const DOMAIN = 'field:system.domain';

function envelope(value: unknown) {
  return { value, status: 'verified', evidence: [] };
}

function runView(over: Partial<ApiRunView> = {}): ApiRunView {
  return {
    id: RUN,
    experiment_id: EXP,
    label: 'Run 1',
    ordinal: 1,
    created_utc: '2099-04-02T09:05:00Z',
    updated_utc: '2099-04-02T09:05:00Z',
    rev: 3,
    version: 'ra.3',
    record_id: null,
    fields: {},
    inherited: {
      [MATERIAL]: {
        state: 'inherited',
        payload: envelope('Synthetic CuO powder'),
        inherited_payload: envelope('Synthetic CuO powder'),
      },
    },
    ...over,
  } as ApiRunView;
}

/** The same run, with `sample.material.name` overridden to `value`. */
function overriddenRun(value: string, over: Partial<ApiRunView> = {}): ApiRunView {
  return runView({
    rev: 4,
    version: 'ra.4',
    inherited: {
      [MATERIAL]: {
        state: 'overridden',
        payload: envelope(value),
        inherited_payload: envelope('Synthetic CuO powder'),
        displaced_payload: envelope('Synthetic CuO powder'),
      },
    },
    ...over,
  });
}

/** Every request the stub saw, with its parsed body and `If-Match`. */
function requestLog() {
  const seen: { key: string; body: Record<string, unknown>; ifMatch?: string }[] = [];
  return {
    seen,
    wrap(routes: Record<string, RouteEntry>): Record<string, RouteEntry> {
      const wrapped: Record<string, RouteEntry> = {};
      for (const [key, entry] of Object.entries(routes)) {
        wrapped[key] = async (init?: RequestInit) => {
          seen.push({
            key,
            body: init?.body ? JSON.parse(String(init.body)) : {},
            ifMatch: (init?.headers as Record<string, string> | undefined)?.['If-Match'],
          });
          return typeof entry === 'function' ? await entry(init) : entry;
        };
      }
      return wrapped;
    },
  };
}

function mount(run: ApiRunView, routes: Record<string, RouteEntry> = {}) {
  const onRun = vi.fn();
  stubFetchRoutes(routes);
  const view = render(<RunInheritedPanel experimentId={EXP} run={run} onRun={onRun} />);
  return { onRun, view };
}

/**
 * The panel with a PARENT that adopts what the server returns.
 *
 * `mount` hands `onRun` to a spy, which is right for asserting what was sent —
 * but it freezes `run.version` at the mounted value, so it cannot show that a
 * re-read makes the NEXT attempt carry a different token. That is exactly the
 * claim the 412 recovery has to back, so it is tested against a parent that does
 * what `RunCard`'s does: replace the run with the one the server returned.
 */
function mountLive(initial: ApiRunView, routes: Record<string, RouteEntry> = {}) {
  stubFetchRoutes(routes);
  function Harness() {
    const [run, setRun] = useState(initial);
    return <RunInheritedPanel experimentId={EXP} run={run} onRun={setRun} />;
  }
  return render(<Harness />);
}

const panel = () => screen.getByRole('region', { name: 'Values inherited from the record' });
const rowFor = (address: string) =>
  panel().querySelector(`[data-address="${address}"]`) as HTMLElement;
const outcome = () => panel().querySelector('.run-inherited-outcome')!.textContent ?? '';

/** Open the override form on one row and type into it. */
async function openOverride(address: string, text: string) {
  await act(async () => {
    fireEvent.click(
      within(rowFor(address)).getByRole('button', {
        name: /Override for this run|Change this run's value/,
      }),
    );
  });
  await act(async () => {
    fireEvent.change(within(rowFor(address)).getByRole('textbox'), { target: { value: text } });
  });
}

const confirmBox = (address: string) =>
  within(rowFor(address)).getByRole('checkbox') as HTMLInputElement;
const recordButton = (address: string) =>
  within(rowFor(address)).getByRole('button', { name: /Record override/ }) as HTMLButtonElement;

beforeEach(() => vi.useRealTimers());
afterEach(() => vi.unstubAllGlobals());

// ---------------------------------------------------------------------------
// 1 — an inherited value says where it came from, and offers the act
// ---------------------------------------------------------------------------

describe('an inherited value', () => {
  it('names the record as its source, and keeps that context visible', () => {
    mount(runView());
    const row = rowFor(MATERIAL);
    expect(within(row).getByText('sample.material.name')).toBeInTheDocument();
    expect(within(row).getByText('Synthetic CuO powder')).toBeInTheDocument();
    expect(within(row).getByText(/Inherited from record/)).toBeInTheDocument();
    // The panel states inheritance BY REFERENCE, which is the property the whole
    // feature rests on — nothing is copied into a run.
    expect(panel().textContent).toMatch(/nothing is copied into a run/);
  });

  it('offers an override, and no way to edit the value in place', () => {
    mount(runView());
    const row = rowFor(MATERIAL);
    expect(
      within(row).getByRole('button', { name: /Override for this run/ }),
    ).toBeInTheDocument();
    expect(row.querySelectorAll('input, select, textarea')).toHaveLength(0);
  });

  it('names the address in the control\'s accessible name, after its visible text', () => {
    // Fifteen buttons reading "Override for this run" would have fifteen identical
    // accessible names. The address is APPENDED so the visible string stays a
    // contiguous substring of the accessible one (WCAG 2.5.3, Label in Name).
    mount(runView());
    const button = within(rowFor(MATERIAL)).getByRole('button', {
      name: 'Override for this run · sample.material.name',
    });
    expect(button.textContent).toContain('Override for this run');
  });
});

// ---------------------------------------------------------------------------
// 2 — recording one: the confirmation is the reader's
// ---------------------------------------------------------------------------

describe('recording an override', () => {
  it('will not send until the reader confirms, and then sends confirmed_by_user: true', async () => {
    const log = requestLog();
    const { onRun } = mount(
      runView(),
      log.wrap({
        [OVERRIDES]: {
          body: {
            run: overriddenRun('Copper(I) Oxide'),
            override: { address: MATERIAL, recorded_utc: '2099-04-02T10:00:00Z' },
          },
        },
      }),
    );

    await openOverride(MATERIAL, 'Copper(I) Oxide');
    // THE GATE: not pre-ticked, and the submit is inert until it is.
    expect(confirmBox(MATERIAL).checked).toBe(false);
    expect(recordButton(MATERIAL).disabled).toBe(true);
    await act(async () => {
      fireEvent.click(recordButton(MATERIAL));
    });
    expect(log.seen).toHaveLength(0);

    await act(async () => {
      fireEvent.click(confirmBox(MATERIAL));
    });
    expect(recordButton(MATERIAL).disabled).toBe(false);
    await act(async () => {
      fireEvent.click(recordButton(MATERIAL));
    });

    await waitFor(() => expect(log.seen).toHaveLength(1));
    expect(log.seen[0].body.confirmed_by_user).toBe(true);
    expect(log.seen[0].body.address).toBe(MATERIAL);
    // THE RUN'S token, not the record's — the route says so in as many words.
    expect(log.seen[0].ifMatch).toBe('"ra.3"');
    expect(onRun).toHaveBeenCalledWith(expect.objectContaining({ rev: 4 }));
    expect(outcome()).toMatch(/Override recorded for sample\.material\.name/);
    expect(outcome()).toMatch(/2099-04-02T10:00:00Z/);
    expect(outcome()).toMatch(/record's own value is unchanged/);
  });

  it('sends a draft field envelope carrying the confirmation and NO client timestamp', async () => {
    const log = requestLog();
    mount(
      runView(),
      log.wrap({
        [OVERRIDES]: {
          body: {
            run: overriddenRun('Copper(I) Oxide'),
            override: { address: MATERIAL, recorded_utc: '2099-04-02T10:00:00Z' },
          },
        },
      }),
    );
    await openOverride(MATERIAL, 'Copper(I) Oxide');
    await act(async () => {
      fireEvent.click(confirmBox(MATERIAL));
    });
    await act(async () => {
      fireEvent.click(recordButton(MATERIAL));
    });
    await waitFor(() => expect(log.seen).toHaveLength(1));

    /*
     * THE PAYLOAD IS THE ROUTE'S OWN SHAPE. A `verified` value with an EMPTY
     * evidence list is refused server-side in the draft validator's own words, so
     * the confirmation entry is required rather than decorative. The TIMESTAMP is
     * deliberately absent: a browser's clock is not an authority, and its presence
     * would also defeat the server's documented idempotence by making every
     * re-record look like a new value.
     */
    expect(log.seen[0].body.payload).toEqual({
      value: 'Copper(I) Oxide',
      status: 'verified',
      evidence: [
        {
          source_type: 'user_confirmation',
          question: 'Override sample.material.name on this run?',
          answer: 'Copper(I) Oxide',
        },
      ],
    });
    expect(JSON.stringify(log.seen[0].body)).not.toContain('timestamp');
  });

  it('starts from an EMPTY box — the record\'s value is context, never a suggestion', async () => {
    mount(runView());
    await act(async () => {
      fireEvent.click(
        within(rowFor(MATERIAL)).getByRole('button', { name: /Override for this run/ }),
      );
    });
    const box = within(rowFor(MATERIAL)).getByRole('textbox') as HTMLInputElement;
    expect(box.value).toBe('');
    // …and the record's value is shown BESIDE it, so nothing is hidden by that.
    expect(rowFor(MATERIAL).textContent).toMatch(/The record says/);
    expect(rowFor(MATERIAL).textContent).toMatch(/Synthetic CuO powder/);
  });

  it('says the confirmation records the ACT, not a check that the value is right', async () => {
    mount(runView());
    await openOverride(MATERIAL, 'x');
    expect(rowFor(MATERIAL).textContent).toMatch(/it is not a check that the value is right/);
  });

  it('refuses a blank entry on screen and sends nothing', async () => {
    const log = requestLog();
    mount(runView(), log.wrap({}));
    await openOverride(MATERIAL, '   ');
    await act(async () => {
      fireEvent.click(confirmBox(MATERIAL));
    });
    await act(async () => {
      fireEvent.click(recordButton(MATERIAL));
    });
    expect(log.seen).toHaveLength(0);
    expect(rowFor(MATERIAL).textContent).toMatch(/An override records a value; it never records a blank/);
  });
});

// ---------------------------------------------------------------------------
// 3 — the JSON type is mirrored from the record, and disclosed
// ---------------------------------------------------------------------------

describe('a record-level value the record holds as a number', () => {
  const numericRun = () =>
    runView({
      inherited: {
        [DIAMETER]: {
          state: 'inherited',
          payload: envelope(8),
          inherited_payload: envelope(8),
        },
      },
    });

  it('is sent as a number, and the panel says so', async () => {
    const log = requestLog();
    mount(
      numericRun(),
      log.wrap({
        [OVERRIDES]: {
          body: {
            run: runView({ rev: 4 }),
            override: { address: DIAMETER, recorded_utc: '2099-04-02T10:00:00Z' },
          },
        },
      }),
    );
    await openOverride(DIAMETER, '8.5');
    expect(rowFor(DIAMETER).textContent).toMatch(/The record holds a number here, so this is sent as a number/);
    await act(async () => {
      fireEvent.click(confirmBox(DIAMETER));
    });
    await act(async () => {
      fireEvent.click(recordButton(DIAMETER));
    });
    await waitFor(() => expect(log.seen).toHaveLength(1));
    expect((log.seen[0].body.payload as { value: unknown }).value).toBe(8.5);
  });

  it('refuses text that is not a number, rather than silently changing the type', async () => {
    const log = requestLog();
    mount(numericRun(), log.wrap({}));
    await openOverride(DIAMETER, 'about eight');
    await act(async () => {
      fireEvent.click(confirmBox(DIAMETER));
    });
    await act(async () => {
      fireEvent.click(recordButton(DIAMETER));
    });
    expect(log.seen).toHaveLength(0);
    expect(rowFor(DIAMETER).textContent).toMatch(/the record holds a number at this path/);
  });
});

// ---------------------------------------------------------------------------
// 4 — an overridden value is distinguishable WITHOUT colour
// ---------------------------------------------------------------------------

describe('an overridden value', () => {
  it('is marked by words and a state attribute, not by colour alone', () => {
    mount(overriddenRun('Copper(I) Oxide'));
    const row = rowFor(MATERIAL);
    expect(row.dataset.state).toBe('overridden');
    expect(within(row).getByText(/Overridden on this run/)).toBeInTheDocument();
    expect(within(row).queryByText(/Inherited from record/)).toBeNull();
    // The glyph is present too, and is never the only signal.
    expect(row.querySelector('.run-inherited-state svg')).not.toBeNull();
  });

  it('keeps the record\'s own value visible beside it', () => {
    mount(overriddenRun('Copper(I) Oxide'));
    expect(rowFor(MATERIAL).textContent).toMatch(
      /The record currently says\s*Synthetic CuO powder/,
    );
  });

  it('says the record has MOVED since, when the displaced value differs from it', () => {
    // The three payloads the route documents: what the run holds, what the record
    // says now, and what was displaced. Two values side by side with no explanation
    // read as a bug; this sentence is the explanation.
    mount(
      overriddenRun('Copper(I) Oxide', {
        inherited: {
          [MATERIAL]: {
            state: 'overridden',
            payload: envelope('Copper(I) Oxide'),
            inherited_payload: envelope('Cuprous Oxide'),
            displaced_payload: envelope('Synthetic CuO powder'),
          },
        },
      }),
    );
    const text = rowFor(MATERIAL).textContent ?? '';
    expect(text).toMatch(/The record currently says\s*Cuprous Oxide/);
    expect(text).toMatch(/it said\s*Synthetic CuO powder\s*when this override was recorded/);
  });

  it('never claims the value is verified, checked or correct', () => {
    mount(overriddenRun('Copper(I) Oxide'));
    const text = panel().textContent ?? '';
    // Provenance says where a value came from. It is not a verdict, and this panel
    // renders none — the envelope's own `status: "verified"` is a DRAFT state
    // meaning "carries evidence or a confirmation", and it is never shown as a word
    // to a scientist here.
    expect(text).not.toMatch(/verified/i);
    expect(text).not.toMatch(/validated/i);
    expect(text).not.toMatch(/\bcorrect\b/i);
  });
});

// ---------------------------------------------------------------------------
// 5 — reverting resumes LIVE inheritance
// ---------------------------------------------------------------------------

describe('reverting to the inherited value', () => {
  const revertButton = () =>
    within(rowFor(MATERIAL)).getByRole('button', { name: /Revert to inherited/ });

  it('asks for an explicit second act, and describes live inheritance rather than a copy', async () => {
    const log = requestLog();
    mount(overriddenRun('Copper(I) Oxide'), log.wrap({}));
    await act(async () => {
      fireEvent.click(revertButton());
    });
    expect(log.seen).toHaveLength(0);
    const text = rowFor(MATERIAL).textContent ?? '';
    expect(text).toMatch(/will hold nothing there/);
    expect(text).toMatch(/read the record's value live again, including every later change/);
  });

  it('sends the clear once confirmed, with the run\'s own If-Match, and reports the removal', async () => {
    const log = requestLog();
    const { onRun } = mount(
      overriddenRun('Copper(I) Oxide'),
      log.wrap({ [CLEAR]: { body: { run: runView(), cleared: true } } }),
    );
    await act(async () => {
      fireEvent.click(revertButton());
    });
    await act(async () => {
      fireEvent.click(within(rowFor(MATERIAL)).getByRole('button', { name: 'Confirm revert' }));
    });
    await waitFor(() => expect(log.seen).toHaveLength(1));
    expect(log.seen[0].key).toBe(CLEAR);
    expect(log.seen[0].body).toEqual({ confirmed_by_user: true, address: MATERIAL });
    expect(log.seen[0].ifMatch).toBe('"ra.4"');
    expect(onRun).toHaveBeenCalledWith(expect.objectContaining({ version: 'ra.3' }));
    expect(outcome()).toMatch(/Override removed for sample\.material\.name/);
    expect(outcome()).toMatch(/reads the record's value again, live/);
  });

  it('keeps the override when the reader backs out', async () => {
    const log = requestLog();
    mount(overriddenRun('Copper(I) Oxide'), log.wrap({}));
    await act(async () => {
      fireEvent.click(revertButton());
    });
    await act(async () => {
      fireEvent.click(within(rowFor(MATERIAL)).getByRole('button', { name: 'Keep the override' }));
    });
    expect(log.seen).toHaveLength(0);
    expect(rowFor(MATERIAL).dataset.state).toBe('overridden');
  });

  it('reports `cleared: false` as the no-op it is, not as a removal', async () => {
    // The contract makes this a SUCCESS — the address held no override, nothing was
    // written and the run did not advance — which is what lets a dropped response be
    // retried safely. Saying "removed" here would report a removal that never happened.
    mount(overriddenRun('Copper(I) Oxide'), {
      [CLEAR]: { body: { run: runView(), cleared: false } },
    });
    await act(async () => {
      fireEvent.click(revertButton());
    });
    await act(async () => {
      fireEvent.click(within(rowFor(MATERIAL)).getByRole('button', { name: 'Confirm revert' }));
    });
    await waitFor(() => expect(outcome()).toMatch(/There was no override at sample\.material\.name to remove/));
    expect(outcome()).toMatch(/Nothing was written/);
    expect(outcome()).not.toMatch(/Override removed/);
  });
});

// ---------------------------------------------------------------------------
// 6 — a re-recorded override is a no-op, and must not present as a change
// ---------------------------------------------------------------------------

describe('re-recording the same override', () => {
  it('shows the run\'s OWN value back, so the re-record is reachable at all', async () => {
    mount(overriddenRun('Copper(I) Oxide'));
    await act(async () => {
      fireEvent.click(
        within(rowFor(MATERIAL)).getByRole('button', { name: /Change this run's value/ }),
      );
    });
    const box = within(rowFor(MATERIAL)).getByRole('textbox') as HTMLInputElement;
    // The run's own value, not the record's — and the ONLY row where a box is
    // prefilled, because this value was already entered by a person.
    expect(box.value).toBe('Copper(I) Oxide');
    expect(box.value).not.toBe('Synthetic CuO powder');
  });

  it('reports "already held" rather than "recorded", because the run did not advance', async () => {
    /*
     * `set_run_override` returns the EXISTING override unchanged when the payload is
     * equal: it does not restamp `recorded_utc` and the run's `rev` does not move. The
     * panel reads that off the refreshed run the server returned — an unmoved `rev` IS
     * the server's answer — rather than comparing text locally. Presenting a no-op as
     * a change is how an audit trail acquires entries nothing happened at.
     */
    const unchanged = overriddenRun('Copper(I) Oxide');
    mount(unchanged, {
      [OVERRIDES]: {
        body: {
          run: unchanged, // same `rev`: the server wrote nothing
          // The route's own behaviour: the ORIGINAL recorded time, not a new one.
          override: { address: MATERIAL, recorded_utc: '2099-04-02T09:30:00Z' },
        },
      },
    });
    await openOverride(MATERIAL, 'Copper(I) Oxide');
    await act(async () => {
      fireEvent.click(confirmBox(MATERIAL));
    });
    await act(async () => {
      fireEvent.click(recordButton(MATERIAL));
    });
    await waitFor(() =>
      expect(outcome()).toMatch(/This run already held that value at sample\.material\.name/),
    );
    expect(outcome()).toMatch(/Nothing was written and nothing changed/);
    expect(outcome()).not.toMatch(/Override recorded/);
    // …and no recorded time is presented, because none was newly recorded.
    expect(outcome()).not.toMatch(/2099-04-02T09:30:00Z/);
  });

  it('reports a CHANGED value as a change, so the no-op branch cannot swallow real writes', async () => {
    mount(overriddenRun('Copper(I) Oxide'), {
      [OVERRIDES]: {
        body: {
          run: overriddenRun('Cuprous Oxide', { rev: 5, version: 'ra.5' }),
          override: { address: MATERIAL, recorded_utc: '2099-04-02T11:00:00Z' },
        },
      },
    });
    await openOverride(MATERIAL, 'Cuprous Oxide');
    await act(async () => {
      fireEvent.click(confirmBox(MATERIAL));
    });
    await act(async () => {
      fireEvent.click(recordButton(MATERIAL));
    });
    await waitFor(() => expect(outcome()).toMatch(/Override recorded for sample\.material\.name/));
    expect(outcome()).not.toMatch(/already held/);
  });
});

// ---------------------------------------------------------------------------
// 7 — every way the write can fail says something TRUE
// ---------------------------------------------------------------------------

describe('a refused write', () => {
  /** Drive an override attempt on an inherited row against a failing route. */
  async function attempt(address: string, route: RouteEntry, run: ApiRunView = runView()) {
    const log = requestLog();
    mount(run, log.wrap({ [OVERRIDES]: route }));
    await openOverride(address, 'Copper(I) Oxide');
    await act(async () => {
      fireEvent.click(confirmBox(address));
    });
    await act(async () => {
      fireEvent.click(recordButton(address));
    });
    return log;
  }

  const NOT_OVERRIDABLE_MESSAGE =
    'This address cannot hold a run override. Only a record-level value a run INHERITS ' +
    'can be overridden — `field:<official.dotted.path>`, `block:attribution` or ' +
    '`block:tags`, spelt exactly as the run\'s `inherited` map spells its keys.';

  it('names the address that cannot hold an override, in the server\'s own words', async () => {
    // `field:system.domain` IS reported under `inherited` and is NOT overridable —
    // the run view's map is where the SPELLING is read and is neither necessary nor
    // sufficient for membership. So this refusal is reachable from a row the panel
    // legitimately renders, and it must not degrade to "could not be saved".
    const domainRun = runView({
      inherited: {
        [DOMAIN]: {
          state: 'inherited',
          payload: envelope('materials'),
          inherited_payload: envelope('materials'),
        },
      },
    });
    await attempt(
      DOMAIN,
      {
        status: 422,
        body: {
          error: 'not_overridable',
          address: DOMAIN,
          message: NOT_OVERRIDABLE_MESSAGE,
        },
      },
      domainRun,
    );
    await waitFor(() =>
      expect(rowFor(DOMAIN).textContent).toMatch(/This address cannot hold this override/),
    );
    const text = rowFor(DOMAIN).textContent ?? '';
    expect(text).toContain(DOMAIN);
    expect(text).toContain('Only a record-level value a run INHERITS can be overridden');
    expect(outcome()).toBe('');
  });

  it('shows the draft validator\'s OWN findings for a refused envelope', async () => {
    await attempt(MATERIAL, {
      status: 422,
      body: {
        error: 'invalid_envelope',
        address: MATERIAL,
        findings: ['verified field has no observed evidence or user confirmation'],
        message:
          'A record-level field override must be a draft field envelope and this one is not ' +
          'one the no-guessing rules accept. Nothing was written.',
      },
    });
    await waitFor(() =>
      expect(rowFor(MATERIAL).textContent).toMatch(/Nothing was written/),
    );
    expect(rowFor(MATERIAL).textContent).toContain(
      'verified field has no observed evidence or user confirmation',
    );
    expect(outcome()).toBe('');
  });

  it('a 412 says the override was NOT recorded — never a success', async () => {
    /*
     * The route verifies the precondition INSIDE the same critical section as the
     * write, so a losing writer's override was not recorded. Reporting this as
     * anything other than "not recorded" would be the single most damaging thing this
     * panel could say.
     */
    await attempt(MATERIAL, {
      status: 412,
      body: { error: 'stale_write', current_version: 'ra.9' },
    });
    await waitFor(() =>
      expect(rowFor(MATERIAL).textContent).toMatch(
        /This run changed somewhere else — the override was not recorded/,
      ),
    );
    expect(rowFor(MATERIAL).textContent).toMatch(/Nothing was written/);
    expect(outcome()).not.toMatch(/recorded for/);
    expect(rowFor(MATERIAL).dataset.state).toBe('inherited');
  });

  it('falls back honestly when the refusal carries no readable reason', async () => {
    // Never invent a reason the server did not give — and never call it a success.
    await attempt(MATERIAL, { status: 422, body: 'not json at all' });
    await waitFor(() =>
      expect(rowFor(MATERIAL).textContent).toMatch(
        /this build could not read its reason\. Nothing was written/,
      ),
    );
    expect(outcome()).toBe('');
  });

  it('a transport failure is reported as one, not as a refusal', async () => {
    await attempt(MATERIAL, { status: 503, body: { error: 'unavailable' } });
    await waitFor(() =>
      expect(rowFor(MATERIAL).textContent).toMatch(/The override could not be sent/),
    );
    expect(rowFor(MATERIAL).textContent).not.toMatch(/cannot hold this override/);
    expect(outcome()).toBe('');
  });
});

// ---------------------------------------------------------------------------
// 8 — the 412's named remedy is ON SCREEN, and it actually recovers
// ---------------------------------------------------------------------------

describe('recovering from a compare-and-swap refusal', () => {
  /** The run as a second client left it: same values, a version this page has not seen. */
  const movedRun = () => runView({ rev: 9, version: 'ra.9' });

  /** 412 on the first override attempt, 200 on every one after it. */
  function overridesThenSucceed(): RouteEntry {
    let calls = 0;
    return () => {
      calls += 1;
      if (calls === 1) return { status: 412, body: { error: 'stale_write', current_version: 'ra.9' } };
      return {
        body: {
          run: overriddenRun('Copper(I) Oxide', { rev: 10, version: 'ra.10' }),
          override: { address: MATERIAL, recorded_utc: '2099-04-02T10:00:00Z' },
        },
      };
    };
  }

  async function driveToStale(log: ReturnType<typeof requestLog>, routes: Record<string, RouteEntry>) {
    mountLive(runView(), log.wrap(routes));
    await openOverride(MATERIAL, 'Copper(I) Oxide');
    await act(async () => {
      fireEvent.click(confirmBox(MATERIAL));
    });
    await act(async () => {
      fireEvent.click(recordButton(MATERIAL));
    });
    await waitFor(() =>
      expect(rowFor(MATERIAL).textContent).toMatch(/the override was not recorded/),
    );
  }

  const refreshButton = () =>
    within(rowFor(MATERIAL)).getByRole('button', {
      name: 'Refresh this run · sample.material.name',
    }) as HTMLButtonElement;

  it('offers the refresh it names, and a retry then carries the version the server holds', async () => {
    /*
     * THE DEFECT THIS PINS. The notice said "Refresh this run to load the version the
     * server holds", and the app's only refresh was `RunCard`'s, gated on
     * `autosave.status === 'conflict'` — a state an override 412 never reaches, because
     * this write does not go through `useRunAutosave` at all. So `run.version` could
     * never advance, every retry 412'd forever, and only a full page reload recovered.
     */
    const log = requestLog();
    await driveToStale(log, {
      [OVERRIDES]: overridesThenSucceed(),
      [GET_RUN]: { body: { run: movedRun() } },
    });
    expect(log.seen[0].ifMatch).toBe('"ra.3"');

    await act(async () => {
      fireEvent.click(refreshButton());
    });

    // The re-read is reported as a re-read — NOT as a write, and not as a retry.
    await waitFor(() => expect(outcome()).toMatch(/This run was re-read from the server/));
    expect(outcome()).toMatch(/Nothing was written/);
    expect(outcome()).toMatch(/is still not recorded/);
    expect(rowFor(MATERIAL).textContent).not.toMatch(/the override was not recorded/);

    // The form is still open, still holding the value and the ticked confirmation…
    expect((within(rowFor(MATERIAL)).getByRole('textbox') as HTMLInputElement).value).toBe(
      'Copper(I) Oxide',
    );
    expect(confirmBox(MATERIAL).checked).toBe(true);
    // …and the retry carries the SERVER's token, which is the whole point.
    await act(async () => {
      fireEvent.click(recordButton(MATERIAL));
    });
    await waitFor(() => expect(outcome()).toMatch(/Override recorded for sample\.material\.name/));
    const overridePosts = log.seen.filter((s) => s.key === OVERRIDES);
    expect(overridePosts).toHaveLength(2);
    expect(overridePosts[1].ifMatch).toBe('"ra.9"');
  });

  it('leaves focus on the retry the copy names, never on the document body', async () => {
    const log = requestLog();
    await driveToStale(log, {
      [OVERRIDES]: overridesThenSucceed(),
      [GET_RUN]: { body: { run: movedRun() } },
    });
    await act(async () => {
      fireEvent.click(refreshButton());
    });
    await waitFor(() => expect(outcome()).toMatch(/re-read from the server/));
    expect(document.activeElement).toBe(recordButton(MATERIAL));
  });

  it('says so when the re-read itself fails, and keeps the refusal on screen', async () => {
    // A control that fails silently would be the very defect this button was added to
    // remove. The 412 is still true and still unresolved, so its notice stays.
    const log = requestLog();
    await driveToStale(log, {
      [OVERRIDES]: overridesThenSucceed(),
      [GET_RUN]: { status: 503, body: { error: 'unavailable' } },
    });
    await act(async () => {
      fireEvent.click(refreshButton());
    });
    await waitFor(() =>
      expect(rowFor(MATERIAL).textContent).toMatch(/This run could not be re-read/),
    );
    expect(rowFor(MATERIAL).textContent).toMatch(/the override was not recorded/);
    expect(outcome()).not.toMatch(/re-read from the server/);
    // …and the reader is left on the control they can try again, not on `<body>`.
    expect(document.activeElement).toBe(refreshButton());
  });
});

// ---------------------------------------------------------------------------
// 9 — focus survives every control that destroys itself
// ---------------------------------------------------------------------------

describe('keyboard focus', () => {
  /*
   * MEASURED BEFORE THE FIX, in a real browser, on the trigger of row 9 of 13:
   *
   *   BEFORE ACTIVATE: BUTTON.btn.btn-secondary|Override for this run · …
   *   AFTER ACTIVATE : BODY|Skip to contentISAAC…
   *   AFTER CANCEL   : BODY|Skip to contentISAAC…
   *
   * Every control on this surface unmounts the moment it is activated, and nothing
   * moved focus after it — so a keyboard or screen-reader reader was dropped on
   * `<body>` and had to tab back through the skip link, the app shell and every
   * preceding row to reach the box they had just revealed. The axe scan says nothing
   * about this: axe does not evaluate focus movement.
   */
  const trigger = (name: RegExp) =>
    within(rowFor(MATERIAL)).getByRole('button', { name }) as HTMLButtonElement;

  it('moves to the value box when the form opens', async () => {
    mount(runView());
    await act(async () => {
      fireEvent.click(trigger(/Override for this run/));
    });
    expect(document.activeElement).toBe(within(rowFor(MATERIAL)).getByRole('textbox'));
    expect(document.activeElement).not.toBe(document.body);
  });

  it('returns to the control that opened the form when the reader cancels', async () => {
    mount(runView());
    await act(async () => {
      fireEvent.click(trigger(/Override for this run/));
    });
    await act(async () => {
      fireEvent.click(within(rowFor(MATERIAL)).getByRole('button', { name: 'Cancel' }));
    });
    expect(document.activeElement).toBe(trigger(/Override for this run/));
  });

  it('lands on the row\'s own control after a successful record — which now says something else', async () => {
    // The trigger the reader activated has been REPLACED rather than restored: an
    // inherited row is an overridden one now, so the button in its place reads
    // "Change this run's value". Focusing it announces the new state by name.
    mountLive(runView(), {
      [OVERRIDES]: {
        body: {
          run: overriddenRun('Copper(I) Oxide'),
          override: { address: MATERIAL, recorded_utc: '2099-04-02T10:00:00Z' },
        },
      },
    });
    await openOverride(MATERIAL, 'Copper(I) Oxide');
    await act(async () => {
      fireEvent.click(confirmBox(MATERIAL));
    });
    await act(async () => {
      fireEvent.click(recordButton(MATERIAL));
    });
    await waitFor(() => expect(outcome()).toMatch(/Override recorded/));
    expect(document.activeElement).toBe(trigger(/Change this run's value/));
  });

  it('moves to the revert confirmation, and back again when the reader keeps the override', async () => {
    mount(overriddenRun('Copper(I) Oxide'));
    await act(async () => {
      fireEvent.click(trigger(/Revert to inherited/));
    });
    expect(document.activeElement).toBe(
      within(rowFor(MATERIAL)).getByRole('button', { name: 'Confirm revert' }),
    );
    await act(async () => {
      fireEvent.click(within(rowFor(MATERIAL)).getByRole('button', { name: 'Keep the override' }));
    });
    expect(document.activeElement).toBe(trigger(/Revert to inherited/));
  });

  it('lands on the row\'s remaining control after a successful revert', async () => {
    // The control the reader started from is GONE — there is no override left to
    // revert — so focus goes to the one the row still has, which states the new
    // state in its own name.
    mountLive(overriddenRun('Copper(I) Oxide'), {
      [CLEAR]: { body: { run: runView(), cleared: true } },
    });
    await act(async () => {
      fireEvent.click(trigger(/Revert to inherited/));
    });
    await act(async () => {
      fireEvent.click(within(rowFor(MATERIAL)).getByRole('button', { name: 'Confirm revert' }));
    });
    await waitFor(() => expect(outcome()).toMatch(/Override removed/));
    expect(document.activeElement).toBe(trigger(/Override for this run/));
  });

  it('lands on the refusal rather than the body when a write is refused', async () => {
    // The submit disabled itself for the round trip, and a browser blurs a control it
    // disables — so without this the reader is on `<body>` with an alert they cannot
    // reach. The notice is a `tabIndex={-1}` landing place, the error-summary pattern.
    mount(runView(), {
      [OVERRIDES]: {
        status: 422,
        body: { error: 'not_overridable', address: MATERIAL, message: 'No.' },
      },
    });
    await openOverride(MATERIAL, 'Copper(I) Oxide');
    await act(async () => {
      fireEvent.click(confirmBox(MATERIAL));
    });
    await act(async () => {
      fireEvent.click(recordButton(MATERIAL));
    });
    await waitFor(() =>
      expect(rowFor(MATERIAL).textContent).toMatch(/This address cannot hold this override/),
    );
    expect(document.activeElement).toBe(rowFor(MATERIAL).querySelector('.run-inherited-failure'));
    expect(document.activeElement).not.toBe(document.body);
  });
});

// ---------------------------------------------------------------------------
// 10 — "carries no value" and "carries something unshowable" are different facts
// ---------------------------------------------------------------------------

describe('a record value this row cannot render', () => {
  const structuredRun = () =>
    runView({
      inherited: {
        [MATERIAL]: {
          state: 'overridden',
          payload: envelope('Copper(I) Oxide'),
          // An object at a `field:` address. Latent today — every overridable field
          // path is `str`/`float` server-side — but `valueText` returns `null` for it
          // exactly as it does for absence, and the two are different statements.
          inherited_payload: envelope({ a: 1 }),
        },
      },
    });

  it('says the record carries something unshowable, not that it carries nothing', () => {
    mount(structuredRun());
    const text = rowFor(MATERIAL).textContent ?? '';
    expect(text).toMatch(/carries a value at this address that this row cannot show in one line/);
    expect(text).not.toMatch(/carries no value at this address/);
  });

  it('draws the same distinction in the form\'s own context line', async () => {
    mount(structuredRun());
    await act(async () => {
      fireEvent.click(
        within(rowFor(MATERIAL)).getByRole('button', { name: /Change this run's value/ }),
      );
    });
    const text = rowFor(MATERIAL).textContent ?? '';
    expect(text).toMatch(/cannot show in one line/);
    expect(text).not.toMatch(/carries no value at this address/);
  });

  it('still says "carries no value" when the record really carries none', () => {
    // The other half of the discrimination: the original sentence must survive for
    // the case it was written for, or this is a rename rather than a fix.
    mount(
      runView({
        inherited: {
          [MATERIAL]: {
            state: 'overridden',
            payload: envelope('Copper(I) Oxide'),
            inherited_payload: null,
          },
        },
      }),
    );
    expect(rowFor(MATERIAL).textContent).toMatch(/The record carries no value at this address/);
  });
});
