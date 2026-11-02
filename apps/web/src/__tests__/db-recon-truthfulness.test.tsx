/**
 * Slice 2A (I5) — hosted truthfulness for the read-only database diagnostic.
 *
 * WHY THIS EXISTS. Slice 2A gave the deployed pod a protected, read-only
 * diagnostic (`GET /api/runtime/database/recon`) over an isolated SLAC test
 * database seeded with production-derived ISAAC records. The backend reports
 * that honestly under `GET /api/health` → `database`, but NO hosted surface read
 * it, so a viewer saw an unqualified "Synthetic" chip and governance copy that
 * implied no real data is ever read anywhere. This file pins the correction.
 *
 * WHAT IT MUST NOT BECOME. The correction is copy + status ONLY. These tests
 * therefore assert as hard as they assert the presence of the new wording that
 * NOTHING record-shaped, and no connection detail, ever reaches the chip — and
 * that the copy does not over-claim in the other direction either (no
 * production access, no "currently connected", no database-backed display).
 *
 * The chip reads the SHARED, module-cached `useHealth` — no new fetch, no
 * polling, and never a call to the reconnaissance endpoint itself. The
 * `GET /api/health` route is the only one stubbed here, which is itself part of
 * the proof: an extra request would throw in the stub.
 *
 * TWO GUARDS EXIST, AND NEITHER IMPLIES THE OTHER. Sections 13–14 below scan
 * FRONTEND copy only: the structured units of `lib/settingsContent.ts` and every
 * non-test `.ts`/`.tsx` under `apps/web/src`. They do not read a single backend
 * string. The sibling guard
 *
 *     apps/api/tests/test_backend_copy_truthfulness.py
 *
 * applies the SAME rules to BACKEND copy: the generated OpenAPI document
 * (`info.summary`, `info.description`, every tag description, and every
 * operation `summary`/`description`) and every string literal in
 * every `.py` file under `apps/api/isaac_api`, which is where the response-body
 * message constants live. It exists because a whole-API over-claim shipped in
 * `app.py`'s `info.summary` while this file was green.
 *
 * `FLAT_WHOLE_APP_CLAIM`, `DIAGNOSTIC_CLAIMS`, `QUALIFICATION` and
 * `CAPABILITY_STATEMENT` are duplicated there, in Python, because a Vitest file
 * and a pytest file cannot share a module. The duplication is NOT silent: that
 * file parses THIS file and asserts both label lists and both pattern sources
 * are character-for-character identical, so adding a pattern to one and not the
 * other fails CI rather than opening a gap.
 *
 * WHAT THE SWEEP GUARD (§13-14) DOES **NOT** CATCH. It is a RATCHET, not a
 * detector for the claim class. What it reliably catches is the set of shapes
 * that have actually shipped — each pinned in §14 as a retired string that must
 * keep failing — plus their near neighbours. Novel phrasings of the same false
 * claim pass it. These five were written by a reviewer and pass both this guard
 * and the backend one, today:
 *
 *     "This prototype only ever handles synthetic data."
 *     "No real records are read anywhere in this build."
 *     "This application never touches production records."
 *     "Nothing real is ever read by this deployment."
 *     "All data in this prototype is fabricated."
 *
 * They are recorded as known gaps, NOT as targets. Patterns chasing them would
 * widen the net over honest mode-and-workspace copy — the whole reason the
 * shipped patterns are narrow on head noun, distance and sentence position — and
 * would leave the next reader believing the class is covered. An incomplete
 * detector that says so is worth more than one that looks complete.
 *
 * 2026-11-02 — STANDING DISCLAIMERS RETIRED (owner's direction). The chip's
 * accessible-name disclosure, the Help "Synthetic workspace" section and its
 * "About this deployment" paragraph were removed, so the PRESENCE assertions that
 * required each surface to carry the workspace claims, the QUALIFICATION and the
 * capability paragraph (old §1–§5 chip clauses, §7–§12 "states …") are deleted.
 * What stays is every "no false claim" half: the sweep guard (§13–§14), the bans on
 * each surface that still renders, and "the chip exposes no record content and no
 * connection detail" over every health state. The four things the backend mirror
 * parses (`FLAT_WHOLE_APP_CLAIM`, `DIAGNOSTIC_CLAIMS`, `QUALIFICATION`,
 * `CAPABILITY_STATEMENT`) are unchanged.
 *
 * A HUMAN REVIEWER REMAINS THE BACKSTOP for any newly written data claim. What
 * CI guarantees is only this: no retired string comes back, and no near-variant
 * of a shipped shape lands unqualified.
 *
 * NOTE ON THE ALLOWLIST. The backend guard carries one (four exempted
 * sentences); this file carries none, so there is no fragment-exemption
 * mechanism here to get wrong. Sections 13(b)'s file-level scan does have a
 * coarser, long-disclosed exoneration — a file carrying the QUALIFICATION
 * anywhere is cleared wholesale — which is why §7-12 run the bans on those surfaces
 * one at a time. See "THE BLIND SPOT, stated plainly" in §13.
 */

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { fireEvent, render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { TopBar } from '../components/TopBar';
import { HelpPanel } from '../components/HelpPanel';
import { SettingsPage } from '../screens/SettingsPage';
import { API_ACCESS_COPY, SETTINGS_WIDGET_COPY, dataRows } from '../lib/settingsContent';
import { __resetHealthCache } from '../lib/useHealth';
import { __resetTutorialStore, startTutorial } from '../lib/tutorialController';
import { stubFetchDown, stubFetchRoutes, tutorialSessionRoutes } from '../test/apiFixtures';
import type { ApiDbReconStatus, ApiHealth } from '../lib/types';

// --- health bodies (built here, shape-faithful to routes.py `health()`) ------
// Deliberately local rather than added to apiFixtures: these are Slice-2A
// shapes, and the fixture module is owned by another concurrent change.

const HEALTH_BASE = {
  status: 'ok',
  mode: 'synthetic-only',
  core: 'isaac_records',
  version: '0.1.0',
  commit: null,
};

/** A pre-Slice-2A build (or a body we could not parse): no `database` block. */
const healthNoBlock: ApiHealth = { ...HEALTH_BASE };

/** `PGHOST` absent — the block exists and says so. */
const healthUnconfigured: ApiHealth = {
  ...HEALTH_BASE,
  database: {
    configured: false,
    classification: null,
    contains_production_derived_records: null,
    record_display: 'closed',
    last_recon: null,
  },
};

/** `PGHOST` present. `last` is the in-process memo of the last scan, or null. */
function healthConfigured(last: { status: ApiDbReconStatus; at: string | null } | null): ApiHealth {
  return {
    ...HEALTH_BASE,
    database: {
      configured: true,
      // The real value the backend sends. It is a code constant, not a server
      // identifier — and the chip must still never render it verbatim.
      classification: 'isolated-app-postgres',
      contains_production_derived_records: true,
      record_display: 'closed',
      last_recon: last,
    },
  };
}

const AT = '2026-07-31T00:00:00Z';

beforeEach(() => {
  __resetHealthCache(); // fresh module cache so each case proves a real fetch
});

afterEach(() => {
  vi.unstubAllGlobals();
  __resetTutorialStore();
  sessionStorage.clear();
});

/* UX-021 — `MemoryRouter` IS REQUIRED here. `HelpPanel` renders a real `<Link>`, and
 * `Link` reads router context, so a bare render throws. In production this panel is
 * mounted inside `TopBar`, inside the router, so the HARNESS was what did not match. */
function renderTopBar() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <TopBar variant="home" />
    </MemoryRouter>,
  );
}

/**
 * The chip, in a scope where one renders. Since 2026-11-02 the ordinary scope has NO
 * chip (it renders only inside a worked-example session, or for an anomalous mode), so
 * the leak scan below opens a session first: that is the scope where the chip exists
 * for every health state, including a failed one.
 */
async function renderChip(health: ApiHealth | 'down'): Promise<HTMLElement> {
  const healthRoute =
    health === 'down'
      ? { 'GET /api/health': { status: 503, body: {} } }
      : { 'GET /api/health': { body: health } };
  stubFetchRoutes({
    ...tutorialSessionRoutes(),
    ...healthRoute,
    'GET /api/experiments': { body: { experiments: [] } },
  } as never);
  await startTutorial(null);
  const { container } = renderTopBar();
  return waitFor(() => {
    const found = container.querySelector<HTMLElement>('.mode-chip');
    expect(found).not.toBeNull();
    return found!;
  });
}

// --- 1–5: the chip makes no database claim in any state ------------------------

/*
 * ~~The chip's accessible name disclosed the diagnostic per `health.database` state~~
 * (D3, Slice 2A) — RETIRED 2026-11-02 with the rest of its disclosure. What survives is
 * the direction this file exists to watch: in EVERY health state, on the ordinary
 * scope, the top bar renders no chip and claims nothing about a database, a
 * connection, or reachability; and an anomalous mode is still surfaced, never masked.
 */
const DATABASE_TALK = /test DB|diagnostic|database|connected|reachable|unavailable|unreachable/i;

describe('mode chip — no database claim in any health state, on the ordinary scope', () => {
  const states: [string, ApiHealth | 'down'][] = [
    ['no block', healthNoBlock],
    ['unconfigured', healthUnconfigured],
    ['configured, no scan', healthConfigured(null)],
    ['configured, ok', healthConfigured({ status: 'ok', at: AT })],
    ['configured, busy', healthConfigured({ status: 'busy', at: AT })],
    ['configured, refused', healthConfigured({ status: 'refused', at: AT })],
    ['configured, error', healthConfigured({ status: 'error', at: AT })],
    ['health down', 'down'],
  ];

  it.each(states)('state %s: no chip, and no database talk in the top bar', async (_label, health) => {
    if (health === 'down') stubFetchDown();
    else stubFetchRoutes({ 'GET /api/health': { body: health } });
    const { container } = renderTopBar();
    await new Promise((r) => setTimeout(r, 20));
    expect(container.querySelector('.mode-chip')).toBeNull();
    const bar = container.querySelector('header.topbar')!;
    const attrs = Array.from(bar.querySelectorAll('*')).flatMap((el) =>
      Array.from(el.attributes).map((a) => a.value),
    );
    expect(`${bar.textContent} ${attrs.join(' ')}`).not.toMatch(DATABASE_TALK);
  });

  it('surfaces an anomalous mode rather than masking it, with or without a database block', async () => {
    for (const health of [{ ...HEALTH_BASE, mode: 'production' }, { ...healthConfigured(null), mode: 'production' }]) {
      __resetHealthCache();
      stubFetchRoutes({ 'GET /api/health': { body: health } });
      const { container, unmount } = renderTopBar();
      await waitFor(() => expect(container.querySelector('.mode-chip')?.textContent).toBe('Production'));
      expect(container.querySelector('.mode-chip')!.textContent).not.toMatch(/synthetic|workspace/i);
      unmount();
      vi.unstubAllGlobals();
    }
  });
});

// --- 6: nothing record-shaped or connection-shaped ever reaches the chip ------

/** Each entry is one class of thing the chip must never expose. */
const FORBIDDEN_IN_CHIP: [string, RegExp][] = [
  ['the raw classification constant', /isolated-app-postgres/i],
  ['a database engine/name token', /postgres|postgis|pgdata|\bpg[a-z]*\b/i],
  ['a hostname or URL', /https?:\/\/|\.svc|\.cluster\.local|\.slac\.stanford|localhost|\bhost\b/i],
  ['a connection detail', /port|sslmode|dsn|connection string|:\/\/|@/i],
  ['a username or secret name', /username|\buser\b|pguser|password|secret|credential|token/i],
  // Any digit at all: a record count (30), a port (5432), a row total, a
  // timestamp. The chip legitimately needs none of them.
  ['a count, port, or timestamp', /\d/],
  ['a record id', /\b01[0-9A-HJKMNP-TV-Z]{6,}\b/],
  ['record content', /CuO|XANES|K-edge|formula|beamline|sample/i],
  ['a claim that the workspace is database-backed', /database-backed|from the database|stored in/i],
];

describe('mode chip — exposes no record content and no connection detail', () => {
  const states: [string, ApiHealth | 'down'][] = [
    ['no block', healthNoBlock],
    ['unconfigured', healthUnconfigured],
    ['configured, no scan', healthConfigured(null)],
    ['configured, ok', healthConfigured({ status: 'ok', at: AT })],
    ['configured, busy', healthConfigured({ status: 'busy', at: AT })],
    ['configured, refused', healthConfigured({ status: 'refused', at: AT })],
    ['configured, error', healthConfigured({ status: 'error', at: AT })],
    ['health down', 'down'],
  ];

  it.each(states)('state %s leaks nothing into the visible text or the accessible name', async (
    _label,
    health,
  ) => {
    const chip = await renderChip(health);
    // Let the async health settle before scanning, so a leak in the RESOLVED
    // state cannot hide behind the loading state.
    await waitFor(() => expect(chip.textContent).toBeTruthy());
    const surface = `${chip.textContent} ${chip.getAttribute('aria-label') ?? ''}`;
    for (const [what, pattern] of FORBIDDEN_IN_CHIP) {
      // The label goes in the FAILURE MESSAGE, never into the scanned string —
      // interpolating it made the scan match its own description.
      expect(surface, `the chip must not expose ${what}`).not.toMatch(pattern);
    }
  });

  // WCAG 2.5.3, kept as a CONDITIONAL guard: the chip carries no `aria-label` now, so
  // its visible text is its name; if one is ever re-added it must open with that text.
  it('if the chip carries an accessible name, it opens with its exact visible text', async () => {
    for (const health of [healthNoBlock, healthConfigured(null), healthConfigured({ status: 'error', at: AT })]) {
      __resetHealthCache();
      __resetTutorialStore();
      sessionStorage.clear();
      const chip = await renderChip(health);
      await waitFor(() => {
        const visible = chip.textContent ?? '';
        expect(visible.length).toBeGreaterThan(0);
        const accessible = chip.getAttribute('aria-label');
        if (accessible !== null) expect(accessible.startsWith(visible)).toBe(true);
      });
      vi.unstubAllGlobals();
    }
  });
});

// --- 7/8: governance copy -----------------------------------------------------

/** The diagnostic half, and its bounds. EVERY surface that mentions the
 *  read-only database diagnostic at all must state all of these — naming the
 *  capability without its bounds is the over-claim this file exists to stop. */
const DIAGNOSTIC_CLAIMS: [string, RegExp][] = [
  ['the diagnostic MAY run — not that it is running', /may run a protected, read-only diagnostic/i],
  [
    'the database is an isolated test database of production-derived records',
    /isolated SLAC test database containing production-derived records/i,
  ],
  ['records are processed transiently in pod memory', /transiently in pod memory/i],
  ['only sanitized aggregate results are returned', /sanitized aggregate results are returned/i],
  ['no record is modified', /no record is modified/i],
  ['nothing is sent to any model', /nothing is sent to any model/i],
  [
    'database-backed record display is closed pending a decision',
    /(record display|display) remains disabled pending an explicit visibility decision/i,
  ],
];

/**
 * Each entry is one way the copy could OVER-claim — the ways that hold on EVERY
 * surface, whatever else that surface is for.
 *
 * `synthetic-only` is deliberately NOT in this list: it is the runtime mode's
 * actual name (`GET /api/health` → `mode`), and Help states it on purpose while
 * explaining that the app gates on that mode rather than on contents. Krish's
 * constraint is not "never say synthetic-only", it is "never say it as an
 * unqualified description of the whole application" — which is a claim about
 * what accompanies the token, so it is asserted per surface below rather than
 * by banning the string everywhere. Where a surface never needs the token at
 * all, `FORBIDDEN_CLAIMS` still bans it outright.
 */
const FORBIDDEN_CLAIMS_SHARED: [string, RegExp][] = [
  ['access to the production database', /the production database|production access|connects? to production/i],
  ['a live connection or a running scan', /is (currently )?(running|connected|reading)|currently reachable|is connected to/i],
  ['that the app verified the isolation', /(verif\w+|confirm\w+|prove[nds]?|check\w+) (that )?(it|the app|this app)?\s*(is )?isolat/i],
  ['that database records are displayed', /records? (are|is) displayed|displays? (the )?records? from/i],
  ['that database records are stored by the app', /records? (are|is) stored (by|in) (this|the) app/i],
  ['that database-backed display is open', /(database-backed )?record display is (open|enabled|available)/i],
  ['full database-backed operation', /(runs?|operates?|backed) (on|by) (the )?(production|real) database/i],
];

/** The shared bans plus the outright ban on the mode token, for the two surfaces
 *  that never had a reason to print it. Unchanged in force from before the split. */
const FORBIDDEN_CLAIMS: [string, RegExp][] = [
  ['unqualified synthetic-only', /synthetic-only/i],
  ...FORBIDDEN_CLAIMS_SHARED,
];

/*
 * ~~GovernanceBanner~~ (retired 2026-11-02 with the Load Materials caveats) and
 * ~~Settings → Privacy & Governance → the governance policy~~ (the tab was retired the
 * same day; `?tab=privacy` now lands on Overview's Data card). What stays pinned is
 * that the page a reader now meets at that address makes no over-claim of any kind.
 */
describe('Settings at ?tab=privacy (now Overview) — no over-claim anywhere on the page', () => {
  async function settingsText(): Promise<string> {
    stubFetchRoutes({
      'GET /api/about': {
        body: {
          app_version: '0.1.0',
          build_commit: null,
          record_schema_version: '1.05',
          runtime_mode: 'synthetic-only',
          data_regime: 'synthetic-only',
          persistence: 'durable',
          core: 'isaac_records',
        },
      },
      'GET /api/openapi': { body: { openapi: '3.1.0', info: { title: 'x', version: '0' }, paths: {} } },
      'GET /api/graph/status': { status: 503, body: {} },
    } as never);
    const view = render(
      <MemoryRouter
        initialEntries={['/settings?tab=privacy']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <SettingsPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(view.container.querySelector('.settings-rows')).not.toBeNull());
    return view.container.querySelector('.settings-panel')!.textContent ?? '';
  }

  /* `FORBIDDEN_CLAIMS_SHARED`: This Build's Runtime rows print the reported mode
     value (`synthetic-only`) as data, which is the mode's real name, not a claim. */
  it.each(FORBIDDEN_CLAIMS_SHARED)('never claims %s', async (_what, pattern) => {
    expect(await settingsText()).not.toMatch(pattern);
  });

  it('makes no unqualified whole-application claim, and bounds the capability if it states it', async () => {
    const text = await settingsText();
    expect(unqualifiedClaims(text)).toEqual([]);
    expect(missingBounds(text)).toEqual([]);
  });
});

// --- 9: the Help popover ------------------------------------------------------

/*
 * The Help popover's synthetic section was the third whole-application claim, then a
 * correctly qualified one; on 2026-11-02 it was removed (owner's direction). What is
 * pinned now is that NO part of the popover makes the claim this file exists to stop,
 * and that the retired section does not come back.
 */

/** The whole rendered popover body, so a forbidden claim cannot hide in any section. */
function helpBodyText(): string {
  const view = render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <HelpPanel />
    </MemoryRouter>,
  );
  fireEvent.click(view.getByRole('button', { name: 'Help' }));
  return view.container.querySelector('.help-panel-body')!.textContent ?? '';
}

describe('Help popover copy — no whole-application data claim anywhere in it', () => {
  it.each(FORBIDDEN_CLAIMS_SHARED)('never claims %s, anywhere in the popover', (_what, pattern) => {
    expect(helpBodyText()).not.toMatch(pattern);
  });

  it('makes no unqualified whole-application claim, and bounds the capability if it states it', () => {
    const text = helpBodyText();
    expect(unqualifiedClaims(text)).toEqual([]);
    expect(missingBounds(text)).toEqual([]);
  });

  it('never states the mode token as a description of the deployment', () => {
    // With the qualifying paragraph gone, the token may not stand alone either.
    expect(helpBodyText()).not.toMatch(/synthetic-only/i);
  });

  it('neither the retired "Synthetic mode" nor "Synthetic workspace" section comes back', () => {
    const view = render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <HelpPanel />
      </MemoryRouter>,
    );
    fireEvent.click(view.getByRole('button', { name: 'Help' }));
    const headings = [...view.container.querySelectorAll('.help-section h3')].map((h) => h.textContent);
    expect(headings).not.toContain('Synthetic mode');
    expect(headings).not.toContain('Synthetic workspace');
  });
});

// --- 10–12: Settings → Overview → the Data card ------------------------------

/*
 * The twelve Privacy & Governance concept cards were retired 2026-11-02. Their
 * replacement is four plain rows (`dataRows`), written from the reported
 * persistence. Every "no false claim" half that held over the cards is run over the
 * rows, on every persistence arm — including an unrecognised value, which must be
 * NAMED rather than narrowed into a branch that asserts something unreported.
 */

const SETTINGS_FACTS = {
  dataRegime: 'synthetic-only',
  persistence: 'ephemeral',
  recordSchemaVersion: '1.05',
};

const PERSISTENCE_ARMS = ['ephemeral', 'durable', 'unavailable', 'not-a-known-state'];

function dataText(persistence: string): string {
  return dataRows({ ...SETTINGS_FACTS, persistence })
    .map((r) => `${r.label} ${r.text}`)
    .join('\n');
}

describe('Settings → Data — no row over-claims, on any persistence arm', () => {
  it.each(PERSISTENCE_ARMS)('persistence %s: none of the forbidden claims', (persistence) => {
    const text = dataText(persistence);
    for (const [what, pattern] of FORBIDDEN_CLAIMS) {
      expect(text, `the Data card claims ${what}`).not.toMatch(pattern);
    }
    expect(unqualifiedClaims(text)).toEqual([]);
    expect(missingBounds(text)).toEqual([]);
  });

  it.each([
    ['denies that any database exists', /there is no database/i],
    ['promises the build takes synthetic data only', /\bsynthetic\s+(demo\s+)?data\s+only\b/i],
    ['puts real data out of scope for the whole build', /out of scope for (this|the) (prototype|build|deployment|app|application)/i],
    ['claims a live database connection', /is (currently )?(connected|reachable|online)/i],
  ])('no arm %s', (_what, pattern) => {
    for (const persistence of PERSISTENCE_ARMS) expect(dataText(persistence)).not.toMatch(pattern);
  });

  it('an unrecognised persistence value is named, never narrowed into a claim', () => {
    const text = dataText('not-a-known-state');
    expect(text).toContain('not-a-known-state');
    expect(text).not.toMatch(/survive a restart|stored as files/i);
  });

  it('the unavailable arm does not claim liveness it did not measure', () => {
    // `/api/health` does zero I/O: the arm reports what the server RECORDED.
    expect(dataText('unavailable')).not.toMatch(/right now|currently|is down|is offline/i);
  });

  // PRECONDITION: the reads the copy has described are the reads `db_recon` makes. If
  // this moves, any future description of the diagnostic has to move with it.
  it('the reads db_recon makes are known, and no app table is among them', () => {
    const candidates = [
      join(process.cwd(), '..', 'api', 'isaac_api', 'db_recon.py'),
      join(process.cwd(), 'apps', 'api', 'isaac_api', 'db_recon.py'),
    ];
    const path = candidates.find((c) => existsSync(c));
    expect(path, 'db_recon.py located').toBeTruthy();
    const src = readFileSync(path as string, 'utf8');
    expect(src).toMatch(/FROM records\b/);
    expect(src).toMatch(/FROM vocabulary_cache\b/);
    expect(src).toMatch(/information_schema\.tables/);
    expect(src).not.toMatch(/FROM isaac_[a-z_]+/);
  });
});

// --- 13: THE SWEEP GUARD ------------------------------------------------------

/*
 * WHY THIS EXISTS. This defect was corrected four times, one surface at a time:
 * the top-bar chip, the governance banner, Governance → Policy, the Help
 * popover, the `no-real-experiment-data` concept — and each pass discovered
 * another surface the previous pass had not thought to look at. Every one of
 * those passes had green tests, because every test named the surfaces it already
 * knew about. A fifth instance OF ONE OF THESE SHAPES — a retired string
 * returning, or a near-variant of one — is now caught by CI rather than by a
 * reader. A newly PHRASED instance is not: see "WHAT THE SWEEP GUARD DOES NOT
 * CATCH" in this file's header for five that pass today, and why chasing them
 * with more patterns would make the guard worse rather than complete.
 *
 * WHAT IT SCANS. Two granularities, deliberately:
 *
 *  (a) EVERY user-visible copy unit inside `settingsContent.ts` — each concept,
 *      each `API_ACCESS_COPY` string — because that module is structured data
 *      and a file-level scan of it is useless: it now contains the qualification
 *      somewhere, which would exonerate every card in it. Per-concept is the
 *      granularity that would have caught `synthetic-data-only`, and section 14
 *      proves that on the retired string itself.
 *  (b) EVERY `.ts`/`.tsx` file under `apps/web/src` except tests and fixtures —
 *      so a NEW screen is covered the day it is written. Comments are stripped
 *      first, so a note recording a past defect (there are several) is not read
 *      as the defect.
 *
 * THE RULE. A unit may not make a flat whole-application data claim UNLESS the
 * same unit also carries the qualification. That is the actual requirement — a
 * claim is wrong when it is unqualified, not when the words appear — so the
 * guard encodes the pairing rather than banning vocabulary.
 *
 * THE BLIND SPOT, stated plainly: at file granularity, a file that carries the
 * qualification is exonerated wholesale (since 2026-11-02 TopBar and HelpPanel no
 * longer do; settingsContent and GovernancePage still may). That is why sections 7–12
 * above run the bans surface by surface, and why (a) exists for the one of them that
 * holds many independent cards.
 */

/** Each entry is one way of claiming the whole application/build/deployment
 *  takes only synthetic data, or that real data is out of scope for it. */
const FLAT_WHOLE_APP_CLAIM: [string, RegExp][] = [
  [
    'the build/deployment itself is synthetic-only',
    /\b(this|the)\s+(build|prototype|deployment|app|application)\b[^.!?]{0,80}\bsynthetic[- ]only\b/i,
  ],
  [
    'synthetic-only used as a name for the build/deployment',
    /\bsynthetic[- ]only\b[^.!?]{0,40}\b(build|prototype|deployment|app|application)\b/i,
  ],
  // The ADJECTIVAL shape, added after the backend sweep. `app.py`'s OpenAPI
  // `info.summary` read "Synthetic-only FastAPI wrapper over the deterministic
  // isaac_records core." — a label for the whole API — and matched NONE of the
  // patterns around it, because the one above needs `build|prototype|
  // deployment|app|application` within 40 characters and "FastAPI wrapper over
  // the deterministic…" supplies none of them.
  //
  // Deliberately narrow on three axes, so the mode token stays usable where it
  // is honest: the token must OPEN the unit or a sentence (a label position, not
  // "configured for synthetic-only operation" mid-clause); at most three words
  // may intervene (an adjective phrase, not a clause); and the head noun must
  // denote the SOFTWARE ITSELF. `workspace`, `mode` and `operation` are
  // deliberately absent from that noun list — "a synthetic-only workspace" and
  // "synthetic-only mode" are the correctly scoped forms this whole sweep
  // arrived at, and must keep passing.
  [
    'synthetic-only as an adjectival label for the whole API/app',
    /(?:^|[.!?]\s+)synthetic[- ]only\s+(?:[a-z0-9_]+\s+){0,3}(api|service|server|backend|wrapper|application|app|prototype|build|deployment|tool|assistant|platform|system)\b/i,
  ],
  [
    'calling the whole thing "this synthetic <build>"',
    /\bthis\s+synthetic\s+(build|prototype|deployment|app|application|preview)\b/i,
  ],
  ['"synthetic (demo) data only"', /\bsynthetic\s+(demo\s+)?data\s+only\b/i],
  [
    'real data out of scope for the build/deployment',
    /out of scope for (this|the)\s+(prototype|build|deployment|app|application)/i,
  ],
  [
    'a claim about which data is in scope at all',
    /\b(data|records?|artifacts?)\b[^.!?]{0,40}\b(is|are)\s+in\s+scope\b/i,
  ],
  ['a flat denial that any database exists', /\bthere\s+is\s+no\s+database\b/i],
  // The negative lookahead keeps the truthful "no database records are
  // displayed" (the chip's accessible name) out of the net: that is a claim
  // about DISPLAY, not about a database's existence.
  ['"no database" as a bare fact about the deployment', /\bno\s+database\b(?!\s+records)/i],
  ['no real experiment data, with no scope on it', /\bno\s+real\s+(experiment|facility|scientific)?\s*data\b/i],
];

/** The marker that a unit states the diagnostic rather than promising it away.
 *  Matches every corrected surface's wording, including the chip's "configured
 *  to run a protected, read-only diagnostic" and "protected, read-only
 *  test-database diagnostic". */
const QUALIFICATION = /protected,\s*read-only[^.!?]{0,40}diagnostic/i;

/** The capability statement. A unit that makes it must state every bound. */
const CAPABILITY_STATEMENT = /may run a protected, read-only diagnostic/i;

function unqualifiedClaims(text: string): string[] {
  if (QUALIFICATION.test(text)) return [];
  return FLAT_WHOLE_APP_CLAIM.filter(([, pattern]) => pattern.test(text)).map(([label]) => label);
}

function missingBounds(text: string): string[] {
  if (!CAPABILITY_STATEMENT.test(text)) return [];
  return DIAGNOSTIC_CLAIMS.filter(([, pattern]) => !pattern.test(text)).map(([label]) => label);
}

// (a) --- the structured copy units of settingsContent.ts ----------------------

interface CopyUnit {
  where: string;
  text: string;
}

/*
 * EVERY REACHABLE PERSISTENCE STATE, not just the one the fixture happens to
 * carry. `SETTINGS_FACTS.persistence` is `'ephemeral'`, and until 2026-08-27
 * that was the ONLY value `GET /api/about` could return — it was a hardcoded
 * literal — so scanning one state scanned the whole copy surface.
 *
 * It is derived now, from `experiment_storage.state`, and the hosted deployment
 * reports `durable`. So the cards that branch on it have arms this sweep had
 * never seen, and an arm nobody sweeps is exactly where the next unqualified
 * whole-application claim would land. `unavailable` and an unrecognised value are
 * included for the same reason: every arm that can render is scanned.
 */
const PERSISTENCE_STATES = PERSISTENCE_ARMS;

function settingsCopyUnits(): CopyUnit[] {
  const units: CopyUnit[] = [];
  for (const persistence of PERSISTENCE_STATES) {
    for (const row of dataRows({ ...SETTINGS_FACTS, persistence })) {
      units.push({ where: `data row "${row.label}" [persistence=${persistence}]`, text: `${row.label} ${row.text}` });
    }
  }
  for (const [key, value] of Object.entries(API_ACCESS_COPY)) {
    if (typeof value === 'string') units.push({ where: `API_ACCESS_COPY.${key}`, text: value });
  }
  for (const [key, value] of Object.entries(SETTINGS_WIDGET_COPY)) {
    if (typeof value === 'string') units.push({ where: `SETTINGS_WIDGET_COPY.${key}`, text: value });
  }
  return units;
}

describe('sweep guard — every settingsContent copy unit, one at a time', () => {
  const units = settingsCopyUnits();

  it('scans every Data row on every arm, and every API-access and widget string', () => {
    expect(units.length).toBeGreaterThanOrEqual(4 * PERSISTENCE_STATES.length + 10);
    for (const persistence of PERSISTENCE_STATES) {
      expect(units.map((u) => u.where)).toContain(`data row "Experiment Records" [persistence=${persistence}]`);
    }
    expect(units.map((u) => u.where)).toContain('API_ACCESS_COPY.stateLine');
    expect(units.map((u) => u.where)).toContain('SETTINGS_WIDGET_COPY.dataTitle');
  });

  it.each(units.map((u) => [u.where, u.text]))(
    '%s makes no unqualified whole-application claim',
    (where, text) => {
      expect(unqualifiedClaims(text as string), `${where} over-claims`).toEqual([]);
    },
  );

  it.each(units.map((u) => [u.where, u.text]))(
    '%s states every bound if it states the capability',
    (where, text) => {
      expect(missingBounds(text as string), `${where} names the diagnostic unbounded`).toEqual([]);
    },
  );
});

// (b) --- every frontend source file ------------------------------------------

/**
 * Locate `apps/web/src` on disk. Deliberately NOT `import.meta.url`: under the
 * jsdom environment that is an http URL, not a file one. Mirrors the same helper
 * in `hosted-truthfulness.test.tsx`, which this guard is modelled on — it is
 * duplicated rather than exported so neither file can silently change the
 * other's scan.
 */
function locateSrcDir(): string {
  const candidates = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
  const found = candidates.find((dir) => existsSync(join(dir, 'main.tsx')));
  if (found === undefined) throw new Error(`cannot locate apps/web/src from ${process.cwd()}`);
  return found;
}

const SRC_DIR = locateSrcDir();
/** Tests and fixtures are copy ABOUT the app, not copy the app renders. */
const NOT_USER_FACING = new Set(['__tests__', 'test']);

function frontendSourceFiles(dir: string = SRC_DIR): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!NOT_USER_FACING.has(entry.name)) found.push(...frontendSourceFiles(full));
    } else if (/\.tsx?$/.test(entry.name) && !entry.name.endsWith('.d.ts')) {
      found.push(relative(SRC_DIR, full).split(sep).join('/'));
    }
  }
  return found.sort();
}

/**
 * Strip comments; keep string literals and JSX text, which is what a user reads.
 * The `[^:'"\`]` guard keeps `https://…` inside a literal from being eaten.
 *
 * Then COLLAPSE WHITESPACE, which the sibling helper in
 * `hosted-truthfulness.test.tsx` does not need and this one does. Its patterns
 * are short; these span a clause. JSX wraps prose across lines and TypeScript
 * concatenates long strings, so the browser renders "nothing is sent to any
 * model" from a source that reads `any\n                model` — and a sentence
 * matched in the DOM goes unmatched in the file. Both `HelpPanel.tsx` and
 * `GovernancePage.tsx` were reported as unbounded for exactly that reason while
 * rendering the full paragraph correctly.
 */
function renderedCopy(path: string): string {
  return readFileSync(join(SRC_DIR, path), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(^|[^:'"`\\])\/\/[^\n]*/g, '$1')
    .replace(/\s+/g, ' ');
}

describe('sweep guard — no unqualified whole-application claim in any frontend source', () => {
  const files = frontendSourceFiles();

  it('scans the real string sources, not a duplicate of them', () => {
    expect(files.length).toBeGreaterThan(40);
    for (const covered of [
      'components/HelpPanel.tsx',
      'components/TopBar.tsx',
      'lib/labels.ts',
      'lib/settingsContent.ts',
      'screens/GovernancePage.tsx',
      'screens/LoadMaterials.tsx',
      'screens/SettingsPage.tsx',
      'screens/settings/ApiKeys.tsx',
    ]) {
      expect(files).toContain(covered);
    }
    expect(files.some((f) => f.startsWith('__tests__/'))).toBe(false);
  });

  /* The scan reads prose the way a browser renders it, not the way the file
     wraps it. Without this the two paragraph surfaces silently look unbounded
     and the bounds test below becomes a false alarm rather than a guard. */
  it('reads wrapped JSX prose as one sentence', () => {
    // Re-pointed 2026-11-02: the capability paragraph this used to read left Help. The
    // property is the same — a sentence the source wraps over three lines is matched as
    // the one sentence the browser renders.
    const help = renderedCopy('components/HelpPanel.tsx');
    expect(help).toContain(
      'a record can be valid against that schema and still be refused here, and no screen reports such a refusal as a schema error.',
    );
    // ...and the comments explaining the retired copy are gone, so a note about the
    // defect is never counted as the defect.
    expect(help).not.toContain('"Synthetic workspace" section');
  });

  it.each(FLAT_WHOLE_APP_CLAIM)('no file claims %s without the qualification', (_label, pattern) => {
    const offenders = files.filter((path) => {
      const copy = renderedCopy(path);
      return pattern.test(copy) && !QUALIFICATION.test(copy);
    });
    expect(offenders).toEqual([]);
  });

  it('every file that states the capability states all of its bounds', () => {
    const offenders = files
      .map((path) => [path, missingBounds(renderedCopy(path))] as const)
      .filter(([, missing]) => missing.length > 0)
      .map(([path, missing]) => `${path}: missing ${missing.join(', ')}`);
    expect(offenders).toEqual([]);
  });
});

// --- 14: the guard is proven on the defects it was written for ----------------

/*
 * A guard nobody has watched fail is not a guard. These run the guard's own
 * predicates over the EXACT strings that shipped, so the pairing rule is shown
 * to reject them — and shown to reject them for the right reason.
 */

/** `lib/settingsContent.ts` before this sweep — the fourth instance. */
const RETIRED_SYNTHETIC_DATA_ONLY =
  'Synthetic Data Only ' +
  'Synthetic-only mode — file upload is refused outright, and the app cannot tell real data from synthetic. ' +
  'Only unmistakably synthetic data is in scope, and this build runs in synthetic-only mode: file upload is refused outright. Real mode intentionally refuses to start, because the ingestion and governance guardrails it would need do not exist yet. What the app enforces is that mode, not the contents of what it is handed — it cannot tell real data from synthetic, so keeping real artifacts out is a responsibility of whoever operates it, not a check the software performs.';

/** `lib/settingsContent.ts` before this sweep — the storage card. */
const RETIRED_WHAT_RESETS =
  'What Resets ' +
  "No database — the workspace is files on the server, discarded with the deployment's temporary storage. " +
  'There is no database. Workspace state is written as files in a working directory on the server, so restarting the backend process does not by itself clear it.';

/** `screens/GovernancePage.tsx` before the third pass. */
const RETIRED_GOVERNANCE_POLICY =
  'This prototype is synthetic-only by default. Real SLAC/SSRL or private artifacts require written data-governance approval before they can be read, indexed, or sent to any model.';

/** `components/HelpPanel.tsx` before the second pass. */
const RETIRED_HELP =
  'Synthetic mode. This prototype runs on synthetic demo data only — no real experiment data.';

/** `lib/settingsContent.ts` before the pass that preceded this one. */
const RETIRED_NO_REAL_EXPERIMENT_DATA =
  'No Real Experiment Data ' +
  'Real or private facility artifacts are out of scope for this prototype and require written data-governance approval before they could be read, indexed, or sent anywhere.';

/**
 * `apps/api/isaac_api/app.py`'s OpenAPI `info.summary` before the backend sweep.
 * RETIRED — this is a fixture, not copy to "fix". It is pinned here as well as
 * in `apps/api/tests/test_backend_copy_truthfulness.py` because the pattern that
 * catches it lives in THIS file's list, and a pattern nobody has watched fire is
 * not a pattern. Every other entry in `FLAT_WHOLE_APP_CLAIM` misses it.
 */
const RETIRED_APP_SUMMARY = 'Synthetic-only FastAPI wrapper over the deterministic isaac_records core.';

describe('sweep guard — rejects every string this defect has ever shipped as', () => {
  it.each([
    ['the synthetic-data-only card (the fourth instance)', RETIRED_SYNTHETIC_DATA_ONLY],
    ['the what-resets card', RETIRED_WHAT_RESETS],
    ['the Governance → Policy lead', RETIRED_GOVERNANCE_POLICY],
    ['the Help popover section', RETIRED_HELP],
    ['the no-real-experiment-data card', RETIRED_NO_REAL_EXPERIMENT_DATA],
    ['the API Access status heading', 'API Key Management Is Not Available in This Synthetic Preview'],
    ['the upload-refusal fallback', 'Uploads are approval-gated and not enabled in this synthetic prototype.'],
    ["the backend's OpenAPI info.summary", RETIRED_APP_SUMMARY],
  ])('flags %s', (_what, retired) => {
    expect(unqualifiedClaims(retired as string).length).toBeGreaterThan(0);
  });

  it('flags the OpenAPI summary by the adjectival pattern, which is the only one that sees it', () => {
    // The point of the addition: before it, this string passed the whole list.
    expect(unqualifiedClaims(RETIRED_APP_SUMMARY)).toEqual([
      'synthetic-only as an adjectival label for the whole API/app',
    ]);
  });

  it('leaves the correctly scoped uses of the same token alone', () => {
    for (const scoped of [
      // The replacement that shipped in `app.py`.
      'FastAPI wrapper over the deterministic isaac_records core: a synthetic-only workspace plus one read-only, aggregate-only database diagnostic.',
      // The Settings mode card's summary AS IT STOOD ON 2026-09-12, kept as a
      // frozen fixture of the token-scoping rule: the token opens the unit, but
      // its head noun is `mode`, not the software.
      //
      // IT NO LONGER QUOTES THE SHIPPED COPY, and that is recorded rather than
      // silently refreshed. The card's refusal clause was UNSCOPED — "file
      // upload is refused outright" on a build with two controls that read a
      // user-picked file — and is now "the upload route refuses every request
      // outright" (`upload-claim-parity.test.tsx` §7 pins it and holds the
      // polarity). That defect is orthogonal to what THIS fixture tests, which
      // is why the string is left as it was: narrowing it to the new wording
      // would drop the older phrasing from the scoping proof for no gain.
      'Synthetic-only mode — file upload is refused outright.',
      // ...and the wording that replaced it, so the rule is proven on both.
      'Synthetic-only mode — the upload route refuses every request outright.',
      // `screens/LoadMaterials.tsx`, reviewed and found truthful: it makes no
      // data-regime claim at all, and "build" is a neutral label for the thing
      // the affordance is disabled in.
      'not enabled in this build',
    ]) {
      expect(unqualifiedClaims(scoped), scoped).toEqual([]);
    }
  });

  it('flags the fourth instance for its scope claim specifically, not by accident', () => {
    const flagged = unqualifiedClaims(RETIRED_SYNTHETIC_DATA_ONLY);
    expect(flagged).toContain('a claim about which data is in scope at all');
    expect(flagged).toContain('the build/deployment itself is synthetic-only');
    expect(flagged).toContain('"synthetic (demo) data only"');
  });

  it('would have passed the same string once the qualification is added', () => {
    const repaired = `${RETIRED_SYNTHETIC_DATA_ONLY} Separately, this deployment may run a protected, read-only diagnostic against an isolated SLAC test database containing production-derived records.`;
    expect(unqualifiedClaims(repaired)).toEqual([]);
    // ...but the pairing rule then demands the rest of the bounds, so a
    // half-qualification cannot be used to silence the guard.
    expect(missingBounds(repaired).length).toBeGreaterThan(0);
  });

  it('does not flag copy that is correctly scoped to the workspace', () => {
    for (const scoped of [
      'The records shown here are synthetic, uploads are disabled.',
      'This is a shared, hosted synthetic workspace. Real data is unaffected — this workspace is synthetic-only.',
      'Synthetic or public data only — do not upload real or private data.',
      'Synthetic-mode validator: the record is checked in memory and discarded.',
      'demo data only. This deployment is also configured to run a protected, read-only diagnostic against an isolated test database; it returns sanitized aggregate results only, and no database records are displayed.',
    ]) {
      expect(unqualifiedClaims(scoped), scoped).toEqual([]);
    }
  });
});
