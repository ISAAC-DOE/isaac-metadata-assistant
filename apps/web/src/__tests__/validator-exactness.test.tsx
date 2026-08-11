/**
 * The Validator must not assert that the upstream schema rejected a record it
 * accepted.
 *
 * WHAT SHIPPED. `POST /api/validate/record` gained ISAAC's anchored-pattern
 * exactness gate, so `ok` stopped being the official schema's own verdict. The
 * MEASURED response for a record whose only defect is `tags: ["campaign\n"]` — a
 * trailing newline, i.e. a copy-paste or text-file artefact — is:
 *
 *     ok=False   schema_ok=True   errors=[]   exactness_errors=[1]
 *
 * `toValidationResult` mapped that to `{verdict: 'fail', errors: []}`, dropping
 * `schema_ok` and `exactness_errors` entirely (they were absent from the response
 * type, so TypeScript actively prevented reading them), and `VerdictCard` rendered:
 *
 *     FAIL — Invalid against official ISAAC schema v1.05 — 0 errors. Export blocked.
 *
 * above a "Schema Errors" card holding zero rows. The only statement of the real
 * reason was inside a COLLAPSED `<details>Full validator summary</details>`.
 *
 * WHY THAT IS THE SERIOUS KIND OF WRONG. The record does not violate official
 * ISAAC v1.05 — the same response says so — and the schema is upstream-owned
 * (`CLAUDE.md` §1). `exactness.py` calls its "not a schema rule" heading
 * load-bearing for exactly this reason: a surface that blurs the two attributes an
 * ISAAC policy to upstream, on the product's most prominent status element.
 *
 * NO FIXTURE IN THE REPO EXERCISED THIS SHAPE, which is how it shipped. These
 * tests are that fixture. The assertions are polarity-sensitive on purpose: several
 * of them fail if the claim is merely reworded rather than made conditional.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, cleanup, screen, within } from '@testing-library/react';
import { RecordValidator } from '../components/RecordValidator';
import { VerdictCard } from '../components/VerdictCard';
import type { ValidationResult } from '../lib/types';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const CANDIDATE = JSON.stringify({ isaac_record_version: '1.05', tags: ['campaign\n'] });

/**
 * The exactness finding's wording, copied from a MEASURED response body, not
 * paraphrased. The doubled backslashes are in the real string: the message quotes
 * the pattern with Python's `repr`, so `\S` arrives on the wire as `\\S`.
 */
const EXACTNESS_MESSAGE =
  "value is accepted by the schema pattern '^\\\\S(.*\\\\S)?$' only because Python's '$' " +
  'also matches before a trailing newline; the pattern is anchored and the value does ' +
  'not match it exactly. Offending trailing character(s): U+000A LINE FEED. Remove them ' +
  'and resubmit — ISAAC will not strip them for you, because editing a value you ' +
  'supplied would change metadata you did not ask to change.';

/** THE SHAPE THAT SHIPPED THE DEFECT. Transcribed from the measured API response. */
const EXACTNESS_ONLY = {
  ok: false,
  schema_ok: true,
  summary:
    'PASS — valid against official ISAAC schema v1.05\n\n' +
    'Anchored-pattern exactness (ISAAC gate, not a schema rule):\n' +
    `✗ tags.0 — ${EXACTNESS_MESSAGE}\nFAIL (1 inexact pattern matches)`,
  errors: [],
  exactness_errors: [{ path: 'tags.0', message: EXACTNESS_MESSAGE }],
  schema_version: '1.05',
};

const SCHEMA_ONLY = {
  ok: false,
  schema_ok: false,
  summary: 'FAIL — invalid against official ISAAC schema v1.05',
  errors: [{ path: 'record_type', message: "'record_type' is a required property" }],
  exactness_errors: [],
  schema_version: '1.05',
};

function stubValidate(body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (String(url).includes('/validate/record')) {
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      }
      return new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } });
    })
  );
}

async function validate(body: unknown) {
  stubValidate(body);
  render(<RecordValidator />);
  fireEvent.change(screen.getByRole('textbox'), { target: { value: CANDIDATE } });
  fireEvent.click(screen.getByRole('button', { name: /^Validate$/i }));
  await screen.findByText('FAIL');
}

describe('the Validator names the gate that refused, not the one that did not', () => {
  it('never claims the official schema rejected a record it accepted', async () => {
    await validate(EXACTNESS_ONLY);

    // The exact sentence that shipped, and the family it belongs to. Both, because
    // fixing only the "0 errors" arithmetic would leave the false attribution.
    expect(
      screen.queryByText(/Invalid against official ISAAC schema v1\.05 — 0 errors/),
      'the shipped sentence: it asserted an upstream rejection that did not happen'
    ).toBeNull();
    expect(
      screen.queryByText(/Invalid against official ISAAC schema/),
      'schema_ok is true — no wording may say the official schema found this invalid'
    ).toBeNull();
  });

  it('states the schema PASSED and that an ISAAC gate refused it', async () => {
    await validate(EXACTNESS_ONLY);

    const claim = screen.getByText(/Valid against official ISAAC schema v1\.05, and refused/);
    expect(claim).toBeInTheDocument();
    expect(claim.textContent).toMatch(/1 anchored-pattern exactness finding\b/);
    expect(
      claim.textContent,
      'the disclaimer is the whole point — without it the reader still blames upstream'
    ).toMatch(/not a schema error/i);
    expect(claim.textContent).toMatch(/Export blocked/);
  });

  it('renders no Schema Errors card when there are no schema errors', async () => {
    await validate(EXACTNESS_ONLY);
    expect(
      screen.queryByRole('heading', { name: /^Schema Errors$/ }),
      'a "Schema Errors" heading over zero rows is the surface half of the same false claim'
    ).toBeNull();
  });

  it('renders the finding under its own heading, which says it is not a schema rule', async () => {
    await validate(EXACTNESS_ONLY);
    const heading = screen.getByRole('heading', { name: /Anchored-Pattern Exactness/i });
    expect(heading.textContent).toMatch(/not a schema rule/i);

    // Scoped to the exactness card. The message text ALSO appears in the collapsed
    // summary `<pre>`, which is precisely why an unscoped query would prove nothing
    // about the surface being tested.
    const card = heading.closest('.exactness-errors') as HTMLElement;
    expect(card).not.toBeNull();
    expect(within(card).getByText('tags.0')).toBeInTheDocument();
    expect(within(card).getByText(/matches before a trailing newline/)).toBeInTheDocument();
    expect(within(card).getByText(/will not strip them for you/)).toBeInTheDocument();
  });

  it('shows the reason WITHOUT the reader expanding a disclosure', async () => {
    await validate(EXACTNESS_ONLY);
    // The defect was not that the reason was ABSENT — it was in the collapsed "Full
    // validator summary". A presence assertion alone would pass with the defect
    // fully intact, so this asserts the finding is not inside ANY <details>.
    const heading = screen.getByRole('heading', { name: /Anchored-Pattern Exactness/i });
    const card = heading.closest('.exactness-errors') as HTMLElement;
    expect(card.closest('details'), 'the exactness card is inside a disclosure').toBeNull();
    for (const node of [heading, within(card).getByText('tags.0')]) {
      expect(node.closest('details'), `"${node.textContent?.slice(0, 30)}…" is inside a <details>`)
        .toBeNull();
    }
    // Exactly two renderings of the message: the visible row and the summary pane.
    // Pinned so a future change that removes the visible one and leaves the
    // disclosure — the shipped state — cannot pass.
    const all = screen.getAllByText(/matches before a trailing newline/);
    expect(all.filter((n) => n.closest('details') === null)).toHaveLength(1);

    // The disclosure still exists — it was never the problem.
    expect(screen.getByText(/Full validator summary/)).toBeInTheDocument();
  });

  it('leaves a genuine schema failure reported exactly as before', async () => {
    await validate(SCHEMA_ONLY);
    expect(
      screen.getByText(/Invalid against official ISAAC schema v1\.05 — 1 error\./)
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /^Schema Errors$/ })).toBeInTheDocument();
    expect(screen.getByText(/'record_type' is a required property/)).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: /Anchored-Pattern Exactness/i }),
      'no exactness findings means no exactness card'
    ).toBeNull();
  });

  it('reports both groups separately when both gates refuse', async () => {
    await validate({
      ...SCHEMA_ONLY,
      exactness_errors: [{ path: 'tags.0', message: EXACTNESS_MESSAGE }],
    });
    expect(screen.getByRole('heading', { name: /^Schema Errors$/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Anchored-Pattern Exactness/i })).toBeInTheDocument();
    // The headline names the SCHEMA failure, because that one really is upstream's.
    expect(
      screen.getByText(/Invalid against official ISAAC schema v1\.05 — 1 error\./)
    ).toBeInTheDocument();
    // …and the exactness note must not then claim the schema accepted the record.
    expect(screen.queryByText(/The official ISAAC schema accepts this record/)).toBeNull();
  });

  it('still presents a clean record as an unqualified PASS', async () => {
    stubValidate({
      ok: true,
      schema_ok: true,
      summary: 'PASS — valid against official ISAAC schema v1.05',
      errors: [],
      exactness_errors: [],
      schema_version: '1.05',
    });
    render(<RecordValidator />);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: CANDIDATE } });
    fireEvent.click(screen.getByRole('button', { name: /^Validate$/i }));

    expect(await screen.findByText('PASS')).toBeInTheDocument();
    expect(screen.getByText('Valid against official ISAAC schema v1.05.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /Anchored-Pattern Exactness/i })).toBeNull();
  });
});

describe('VerdictCard without the new fields behaves exactly as it did', () => {
  // The per-experiment validate route returns neither `schema_ok` nor
  // `exactness_errors`, and its `ok` IS the schema verdict. Absent must therefore
  // keep meaning what it meant before the fields existed.
  const LEGACY_FAIL: ValidationResult = {
    verdict: 'fail',
    ok: false,
    schemaVersion: '1.05',
    errors: [{ path: 'record_type', message: "'record_type' is a required property" }],
  };

  it('reads an absent schemaOk as "same as ok" and reports the schema failure', () => {
    render(<VerdictCard result={LEGACY_FAIL} />);
    expect(
      screen.getByText(/Invalid against official ISAAC schema v1\.05 — 1 error\./)
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /^Schema Errors$/ })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /Anchored-Pattern Exactness/i })).toBeNull();
  });

  it('offers the Back to Complete route exactly once when both groups render', () => {
    render(
      <VerdictCard
        result={{
          ...LEGACY_FAIL,
          schemaOk: false,
          exactnessErrors: [{ path: 'tags.0', message: EXACTNESS_MESSAGE }],
        }}
        onBackToComplete={() => {}}
      />
    );
    expect(screen.getAllByRole('button', { name: /Back to Complete/i })).toHaveLength(1);
  });

  it('refuses to blame the schema for a refusal it cannot explain', () => {
    // ok: false, schema PASS, no findings — an unreachable shape today, and the
    // point is that the default is not "blame upstream".
    render(<VerdictCard result={{ ...LEGACY_FAIL, schemaOk: true, errors: [], exactnessErrors: [] }} />);
    expect(screen.queryByText(/Invalid against official ISAAC schema/)).toBeNull();
    expect(screen.getByText(/No reason was supplied with this result/)).toBeInTheDocument();
  });
});
