import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { EXP_ID, exportedReadyRoutes, stubFetchRoutes } from '../test/apiFixtures';

/**
 * THE SIXTH CONSUMER — an exported record whose verdict came from NO validator.
 *
 * WHAT WAS MEASURED, over HTTP, before this fix. Export a record, delete its written
 * artifact out of band, then `POST /api/experiments/{id}/validate`:
 *
 *     {"ok": false, "schema": "ISAAC v1.05", "dry_run": false,
 *      "official_validator_ran": false, "unavailable": true,
 *      "errors": [{"path": "$", "message": "Validation could not be completed."}]}
 *
 * `routes.post_validate` returns that under its own log line *"reporting no verdict"* —
 * the artifact could not be READ, so `validate_official` was never called.
 *
 * `ExportReadiness` converted it with `lib/adapt.ts::toValidationResult`, which sets no
 * `schemaOk` (the per-experiment route carried none), so `VerdictCard` fell back to
 * `schemaOk = ok = false` and rendered, in the reserved red hard-gate treatment:
 *
 *     FAIL — "Invalid against official ISAAC schema v1.05 — 1 error. Export blocked."
 *
 * about a document the official ISAAC schema never opened. `CLAUDE.md` §1 makes the
 * vendored schema not ours to speak for; §12 records this exact sentence shipping once
 * before, above a `schema_ok: true`.
 *
 * WHY NO SWEEP AND NO STATIC GUARD SAW IT. Every one of them was shaped around the
 * PAYLOAD — files reading `official.errors`, `dry_run`, `official_validator_ran`. Not
 * one file in this chain reads a payload key: the screen calls an adapter, the adapter
 * returns a DIFFERENT type, and the card renders that type.
 * `official-attribution-discriminator.test.ts` now treats `ValidationResult` as a
 * consumer signal, which brings `VerdictCard` into its scope — but a static guard can
 * only police WHERE the wording lives, never whether a producer filled `schemaOk`
 * honestly. This file is the behavioural half, and it is the only thing pinning the
 * screen's decision not to render that card at all.
 *
 * BOTH DIRECTIONS ARE TESTED TOGETHER ON PURPOSE. A test asserting only the absence of
 * the claim would also pass if the screen rendered nothing, or rendered a pass. The
 * refusal has to keep its full force and the finding has to stay visible — withholding
 * an attribution must never read as softening a refusal.
 */

const NO_VERDICT = {
  ok: false,
  errors: [{ path: '$', message: 'Validation could not be completed.' }],
  schema: 'ISAAC v1.05',
  dry_run: false,
  official_validator_ran: false,
  unavailable: true,
};

/** A REAL schema refusal on a written record — the control this must not disturb. */
const SCHEMA_REFUSED = {
  ok: false,
  errors: [{ path: 'tags.0', message: "' x' does not match '^\\\\S(.*\\\\S)?$'" }],
  schema: 'ISAAC v1.05',
  dry_run: false,
  official_validator_ran: true,
};

function renderExported(validate: unknown) {
  const routes = exportedReadyRoutes();
  routes[`POST /api/experiments/${EXP_ID}/validate`] = { body: validate };
  stubFetchRoutes(routes);
  return render(
    <MemoryRouter
      initialEntries={[`/record/${EXP_ID}/export`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('an exported record the official validator never examined', () => {
  it('does not tell the scientist the official ISAAC schema rejected it', async () => {
    renderExported(NO_VERDICT);
    await waitFor(() => expect(document.body.textContent).toMatch(/No verdict could be produced/i));
    // THE CLAIM THAT USED TO SHIP, asserted absent by its own words rather than by a
    // component name — a refactor that moves the sentence elsewhere must still fail.
    expect(document.body.textContent).not.toMatch(/Invalid against official ISAAC schema/i);
    expect(document.body.textContent).not.toMatch(/Valid against official ISAAC schema/i);
  });

  it('still shows the finding, so withholding the attribution never softens the refusal', async () => {
    renderExported(NO_VERDICT);
    await waitFor(() =>
      expect(document.body.textContent).toMatch(/Validation could not be completed\./),
    );
    expect(document.body.textContent).toMatch(/not a schema failure/i);
  });

  it('NEGATIVE CONTROL — a real schema refusal still names the official schema', async () => {
    // Without this, the fix would also pass by never naming the schema anywhere, which
    // is a different honesty defect: a genuine upstream refusal reported vaguely.
    renderExported(SCHEMA_REFUSED);
    await waitFor(() =>
      expect(document.body.textContent).toMatch(/Invalid against official ISAAC schema/i),
    );
    expect(document.body.textContent).not.toMatch(/No verdict could be produced/i);
  });
});
