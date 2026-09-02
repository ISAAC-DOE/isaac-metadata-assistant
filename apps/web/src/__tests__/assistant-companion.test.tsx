/**
 * Settings → Connect Your Agent → "Open ISAAC Assistant in Claude".
 *
 * The section's defining requirement is that it must never overstate what it
 * knows, so most of this file is negative: it asserts the absence of the things
 * a surface like this reaches for when it has a link and nothing else — a
 * connected state, a reachability claim, an invented URL, an echo of a value the
 * server refused, and error chrome around a state that is simply the default.
 *
 * FOUR RULES THIS FILE FOLLOWS, EACH BECAUSE A WEAKER VERSION HAS ALREADY
 * SHIPPED GREEN IN THIS REPOSITORY:
 *
 *  1. **Assert BEHAVIOUR, not string presence.** `CLAUDE.md` §11 records a
 *     fabricating seam that returned `{ok: true, record: {status: "complete"}}`
 *     and passed all 25 of its tests, because the slice's central claim was
 *     pinned by a string being present rather than by what the code did. So the
 *     assertions here drive the component with server bodies it must refuse to
 *     act on — a `url` in a state that may not render one, a `checked_reachable`
 *     the server can never send — and read what the DOM actually became.
 *
 *  2. **Every absence is asserted against the rendered DOM, never the source.**
 *     A grep over `AssistantCompanion.tsx` for `<iframe` goes quiet the moment
 *     one arrives through a shared component, which is exactly the route by
 *     which one would arrive.
 *
 *  3. **The ratchets are FLAT substrings, not negation-aware.** The same rule
 *     `connect-your-agent.test.tsx` states: a guard a future author can satisfy
 *     by inserting the word "not" is not a guard. `CLAUDE.md` §11 also records a
 *     **visible lowercase** "Status: connected to your ISAAC workspace" passing
 *     a **case-sensitive** guard, so every ratchet here carries `i`.
 *
 *  4. **Every guard carries an anti-vacuity assertion.** A sweep that found
 *     nothing to check would pass and prove nothing. Each ratchet below is
 *     fired at a control string that MUST match, and each file sweep asserts it
 *     really read files.
 *
 * TEXT IS READ THROUGH `visibleText`, NOT `textContent`, for the reason
 * `connect-your-agent.test.tsx` records at length: `textContent` concatenates
 * adjacent elements with no separator, so `<h4>Connected</h4><p>No…</p>` becomes
 * `ConnectedNo…` and `/\bconnected\b/i` does not match it. A mutation setting
 * the status heading to the single word `Connected` defeated that file's whole
 * ratchet by adjacency alone. Joining the text NODES restores the boundary.
 */
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, within, cleanup, waitFor, fireEvent } from '@testing-library/react';

import { MemoryRouter } from 'react-router-dom';

import { SettingsPage } from '../screens/SettingsPage';
import { ROUTES } from '../lib/routes';
import { AssistantCompanionSection } from '../screens/settings/AssistantCompanion';
import { ASSISTANT_COMPANION_COPY as COPY } from '../lib/assistantCompanionContent';
import {
  stubFetchRoutes,
  SYNTHETIC_COMPANION_MARKER,
  SYNTHETIC_COMPANION_URL,
  assistantCompanionUnconfigured,
  assistantCompanionConfigured,
  assistantCompanionRefused,
  aboutResponse,
  graphStatusAvailable,
  openApiFixture,
} from '../test/apiFixtures';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const ROUTE = 'GET /api/runtime/assistant-companion';

/** Mount the section with one server body, and wait for the read to settle. */
async function renderWith(body: unknown, status = 200) {
  stubFetchRoutes({ [ROUTE]: { body, status } });
  const view = render(<AssistantCompanionSection onOpenExplorer={() => {}} />);
  await waitFor(() =>
    expect(screen.queryByText(COPY.loadingLabel)).not.toBeInTheDocument(),
  );
  return view;
}

/** Mount with a route that fails, so the read never produces a body. */
async function renderUnreadable() {
  stubFetchRoutes({ [ROUTE]: { status: 503, body: { detail: 'no' } } });
  const view = render(<AssistantCompanionSection onOpenExplorer={() => {}} />);
  await waitFor(() => expect(screen.getByText(COPY.unknownLabel)).toBeInTheDocument());
  return view;
}

/** Element boundaries preserved as whitespace. See the header note. */
function visibleText(container: HTMLElement): string {
  const walker = container.ownerDocument.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const parts: string[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    parts.push(node.nodeValue ?? '');
  }
  return parts.join('\n');
}

/** Text AND every attribute value, so a claim parked in a `title`, an
 *  `aria-label` or a `data-` attribute is swept too. */
function everyString(container: HTMLElement): string {
  const parts = [visibleText(container)];
  for (const el of Array.from(container.querySelectorAll('*'))) {
    for (const attr of Array.from(el.attributes)) parts.push(attr.value);
  }
  return parts.join('\n');
}

/**
 * THE CONNECTION-CLAIM RATCHET.
 *
 * Every inflection that can only be a claim about a link having been reached.
 * `connector` is deliberately NOT matched, and the exclusion is by grammatical
 * form rather than by exemption: the server's own `prerequisite` sentence names
 * the vendor's ISAAC **connector**, a thing a scientist enables in their own
 * settings, which is an instruction about a third place and not a statement
 * about this deployment's state. `\b(connect(ed|ing|ion|ions|s))\b` cannot match
 * `connector`, so the ratchet stays flat and needs no carve-out a future author
 * could widen.
 */
const CONNECTION_CLAIM =
  /\b(connected|connecting|connection|connections|connects|disconnect|disconnected|reachable|unreachable|online|offline)\b/i;

/**
 * THE REACHABILITY-CLAIM RATCHET, separate from the one above because the
 * defect is separate: a surface can avoid the word "connected" and still assert
 * that it checked the link. `checked_reachable` is a constant `false`, so no
 * sentence anywhere here may claim the link was opened, resolved or confirmed.
 */
const REACHABILITY_CLAIM =
  /\b(verified|validated the link|we opened|we checked the link|confirmed to work|known to work|responds|resolves)\b/i;

/**
 * THE STATE-CLAIM RATCHET — the third, and it exists because the first two left
 * a four-word hole that an independent review measured.
 *
 * The component's own docstring promised no state renders a claim that something
 * is "connected, reachable, working, live, active, enabled or online", each
 * pinned behaviourally. It was not true: `CONNECTION_CLAIM` covered none of
 * `live`/`active`/`enabled`, and `REACHABILITY_CLAIM` covered `is working` but
 * not the bare adjective. Measured on the branch: setting the configured label to
 * "The companion is live, active and enabled for this deployment" produced ZERO
 * new failures across all 37 tests. That sentence is
 * `ai-integration-decision-packet.md` §6's forbidden fake `Connected` state in
 * different words, and every control in this file waved it through.
 *
 * `available` and `ready` join it for the same reason, and `working` moves here
 * from `REACHABILITY_CLAIM` so the bare adjective is covered rather than only
 * the phrase.
 *
 * `enables` IS DELIBERATELY NOT MATCHED, and the exclusion is by grammatical form
 * rather than by exemption — the same device that lets `CONNECTION_CLAIM` coexist
 * with the word `connector`. The server's own `prerequisite` reads "Each
 * scientist enables the ISAAC connector in their own Claude settings": a
 * third-person verb whose subject is a scientist, describing an action in another
 * product. That is an instruction, not a state claim about this deployment, and
 * it arrives from the server so this repository cannot reword it. The adjectival
 * `enabled`/`enabling` is what a state claim wears, and both are matched.
 */
const STATE_CLAIM = /\b(live|active|enabled|enabling|working|available|ready)\b/i;

/**
 * THE ERROR-FRAMING RATCHET, applied ONLY to the `unconfigured` render.
 *
 * `unconfigured` is the default and a working state. It is not applied to the
 * failed-read state, which genuinely is a problem and must say so — the two are
 * different claims and this file keeps them apart on purpose.
 */
const ERROR_FRAMING =
  /\b(error|errors|failed|failure|broken|unavailable|invalid|missing|malfunction|misconfigur\w*|problem|coming soon|not yet|unsupported|disabled)\b/i;

/** Any absolute URL, whatever attribute it is parked in. */
const ABSOLUTE_URL = /\bhttps?:\/\/[^\s"'<>)]+/gi;

/** External `href`/`src` values actually rendered, in document order. */
function renderedUrls(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('[href], [src]'))
    .map((el) => el.getAttribute('href') ?? el.getAttribute('src') ?? '')
    .filter((url) => /^(https?:)?\/\//.test(url));
}

// --- it actually reaches a screen a scientist opens -------------------------

describe('the section is mounted on a real tab, not merely written', () => {
  it('renders inside Settings → Connect Your Agent, from a ?tab= deep link', async () => {
    /*
     * The claim `artifact_link.py` existed for four commits without: a validated
     * link with NO consumer is not a feature. This asserts the whole path — the
     * router resolves the tab, the tab renders the card, the card renders this
     * section, and the section issues its own read — rather than asserting the
     * component in isolation, which is what a mounting mistake survives.
     */
    stubFetchRoutes({
      'GET /api/about': { body: aboutResponse },
      'GET /api/openapi': { body: openApiFixture },
      'GET /api/graph/status': { body: graphStatusAvailable },
      [ROUTE]: { body: assistantCompanionUnconfigured },
    });
    render(
      <MemoryRouter
        initialEntries={[ROUTES.settingsTab('mcp')]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <SettingsPage />
      </MemoryRouter>,
    );
    const panel = await screen.findByRole('tabpanel', { name: 'Connect Your Agent' });
    expect(
      within(panel).getByRole('heading', { name: COPY.heading }),
    ).toBeInTheDocument();
    // And the live read really happened on the page, not just in isolation.
    expect(await within(panel).findByText(COPY.unconfiguredLabel)).toBeInTheDocument();
  });


  it('re-reads on every remount, and NOT while the tab stays open', async () => {
    /*
     * THE NARROWED CLAIM, MEASURED. The prose in `SettingsPage.tsx` and in the
     * component used to say section-level placement avoided pinning the answer
     * "for the life of a page load". `useFetch(…, [])` pins it for the life of
     * the MOUNT, so the true benefit is narrower: a reader who leaves the tab
     * and returns gets a fresh read; a reader who stays does not. Both halves
     * are asserted, because only asserting the first would let the prose keep
     * overstating the second.
     */
    const calls = stubFetchRoutes({
      'GET /api/about': { body: aboutResponse },
      'GET /api/openapi': { body: openApiFixture },
      'GET /api/graph/status': { body: graphStatusAvailable },
      [ROUTE]: { body: assistantCompanionUnconfigured },
    });
    render(
      <MemoryRouter
        initialEntries={[ROUTES.settingsTab('mcp')]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <SettingsPage />
      </MemoryRouter>,
    );
    await screen.findByText(COPY.unconfiguredLabel);
    const afterFirst = calls.filter((key) => key === ROUTE).length;
    expect(afterFirst).toBe(1);

    // Leave the tab. The section unmounts; nothing re-reads.
    fireEvent.click(screen.getByRole('tab', { name: 'Overview' }));
    await waitFor(() =>
      expect(screen.queryByText(COPY.unconfiguredLabel)).not.toBeInTheDocument(),
    );
    expect(calls.filter((key) => key === ROUTE).length).toBe(afterFirst);

    // Come back. It remounts, and reads again — the whole benefit, stated
    // exactly.
    fireEvent.click(screen.getByRole('tab', { name: 'Connect Your Agent' }));
    await screen.findByText(COPY.unconfiguredLabel);
    await waitFor(() =>
      expect(calls.filter((key) => key === ROUTE).length).toBe(afterFirst + 1),
    );
  });
});

// --- the three states are each rendered, and rendered as themselves ----------

describe('the companion section — the three server states', () => {
  it('renders the DEFAULT state as the default, naming no link', async () => {
    const { container } = await renderWith(assistantCompanionUnconfigured);
    expect(screen.getByText(COPY.unconfiguredLabel)).toBeInTheDocument();
    expect(screen.getByText(COPY.unconfiguredDetail)).toBeInTheDocument();
    expect(renderedUrls(container)).toEqual([]);
  });

  it('renders the CONFIGURED state, offering exactly the link the server sent', async () => {
    const { container } = await renderWith(assistantCompanionConfigured);
    expect(screen.getByText(COPY.configuredLabel)).toBeInTheDocument();
    // Exactly one external URL on the whole surface, and it is the server's
    // string byte for byte — not a normalisation of it, not a prefix of it.
    expect(renderedUrls(container)).toEqual([SYNTHETIC_COMPANION_URL]);
    const link = screen.getByRole('link', { name: new RegExp(COPY.openLinkText, 'i') });
    expect(link.getAttribute('href')).toBe(assistantCompanionConfigured.url);
  });

  it('renders the REFUSED state, relaying the server sentence verbatim', async () => {
    await renderWith(assistantCompanionRefused);
    expect(screen.getByText(COPY.refusedLabel)).toBeInTheDocument();
    expect(screen.getByText(assistantCompanionRefused.reason)).toBeInTheDocument();
  });

  it('reports a FAILED READ as its own outcome, never as "there is none"', async () => {
    const { container } = await renderUnreadable();
    // The distinction this exists for: "we could not ask" is not "there is no
    // link". Rendering the first as the second would assert something the
    // section never established.
    expect(screen.getByText(COPY.unknownLabel)).toBeInTheDocument();
    expect(screen.queryByText(COPY.unconfiguredLabel)).not.toBeInTheDocument();
    expect(screen.queryByText(COPY.configuredLabel)).not.toBeInTheDocument();
    expect(renderedUrls(container)).toEqual([]);
  });

  it('treats a state string it does not know as UNKNOWN, never as one it does', async () => {
    // A server that grows a fourth state must not have this component silently
    // describe it as one of the three it knows.
    const { container } = await renderWith({
      ...assistantCompanionUnconfigured,
      state: 'some_future_state',
      url: SYNTHETIC_COMPANION_URL,
    });
    expect(screen.getByText(COPY.unknownLabel)).toBeInTheDocument();
    expect(renderedUrls(container)).toEqual([]);
  });
});

// --- NEGATIVE CONTROL 1: no state claims a connection or a reachability ------

describe('no state claims a connection, in any casing', () => {
  it.each([
    ['unconfigured', assistantCompanionUnconfigured],
    ['configured', assistantCompanionConfigured],
    ['refused', assistantCompanionRefused],
  ])('renders no connection claim in the %s state', async (_name, body) => {
    const { container } = await renderWith(body);
    const swept = everyString(container);
    expect(swept, 'a connection claim reached the DOM').not.toMatch(CONNECTION_CLAIM);
    expect(swept, 'a reachability claim reached the DOM').not.toMatch(REACHABILITY_CLAIM);
    expect(swept, 'a live/active/enabled state claim reached the DOM').not.toMatch(
      STATE_CLAIM,
    );
  });

  it('renders no connection claim on a failed read either', async () => {
    const { container } = await renderUnreadable();
    expect(everyString(container)).not.toMatch(CONNECTION_CLAIM);
    expect(everyString(container)).not.toMatch(REACHABILITY_CLAIM);
    expect(everyString(container)).not.toMatch(STATE_CLAIM);
  });

  it('THE RATCHETS ARE NOT VACUOUS — each fires on the string it exists to catch', () => {
    // Without this, a typo in either regex would make every assertion above
    // pass over any page at all. Lowercase deliberately: `CLAUDE.md` §11 records
    // a visible lowercase "connected" passing a case-sensitive guard.
    expect('status: connected to your ISAAC workspace').toMatch(CONNECTION_CLAIM);
    expect('Status: CONNECTED').toMatch(CONNECTION_CLAIM);
    expect('the companion is reachable').toMatch(CONNECTION_CLAIM);
    expect('this link was verified').toMatch(REACHABILITY_CLAIM);
    expect('we checked the link and it responds').toMatch(REACHABILITY_CLAIM);
    // THE EXACT SENTENCE THAT SLIPPED THROUGH ALL 37 TESTS, and each of its
    // three words on its own — a control that only fired on the whole phrase
    // would go quiet the moment someone used one of them.
    expect('The companion is live, active and enabled for this deployment').toMatch(
      STATE_CLAIM,
    );
    for (const claim of [
      'the companion is live',
      'the link is active',
      'the connector is enabled',
      'the companion is working',
      'the companion is available',
      'the companion is ready',
    ]) {
      expect(claim, claim).toMatch(STATE_CLAIM);
    }
    // And the two forms that must NOT fire, because the server sends them and
    // this repository cannot reword what the server sends.
    expect('enables the ISAAC connector').not.toMatch(CONNECTION_CLAIM);
    expect('Each scientist enables the ISAAC connector').not.toMatch(STATE_CLAIM);
  });

  it('honours checked_reachable by having NO branch that could read it as true', async () => {
    /*
     * THE STRONGEST FORM OF THIS CLAIM AVAILABLE: feed a body the server can
     * never send — `checked_reachable: true` — and assert the rendered output is
     * IDENTICAL to the honest one. A component with a hidden "if it was checked,
     * say so" branch fails here; a string check for "not reachable" would not.
     */
    const honest = await renderWith(assistantCompanionConfigured);
    const honestHtml = honest.container.innerHTML;
    cleanup();
    vi.unstubAllGlobals();
    const tampered = await renderWith({
      ...assistantCompanionConfigured,
      checked_reachable: true,
    });
    expect(tampered.container.innerHTML).toBe(honestHtml);
  });
});

// --- NEGATIVE CONTROL 2: `unconfigured` does not read as an error ------------

describe('the default state does not read as a fault', () => {
  it('uses none of the vocabulary a reader reads as broken', async () => {
    const { container } = await renderWith(assistantCompanionUnconfigured);
    expect(visibleText(container), 'error framing on the default state').not.toMatch(
      ERROR_FRAMING,
    );
  });

  it('THE ERROR RATCHET IS NOT VACUOUS', () => {
    expect('Companion unavailable — setup failed').toMatch(ERROR_FRAMING);
    expect('Coming soon').toMatch(ERROR_FRAMING);
    expect('No companion link is set for this deployment').not.toMatch(ERROR_FRAMING);
  });

  it('raises no alert and uses no assertive live region, in any state', async () => {
    for (const body of [
      assistantCompanionUnconfigured,
      assistantCompanionConfigured,
      assistantCompanionRefused,
    ]) {
      const { container } = await renderWith(body);
      expect(container.querySelectorAll('[role="alert"]')).toHaveLength(0);
      expect(container.querySelectorAll('[aria-live="assertive"]')).toHaveLength(0);
      cleanup();
      vi.unstubAllGlobals();
    }
  });

  it('gives every state the SAME banner chrome, so none can borrow another’s', async () => {
    /*
     * The behavioural form of "unconfigured is not an error": the state cannot
     * be conveyed by the container at all, because the container is the same
     * element with the same class and the same role in every state. A future
     * author adding `className={state === 'unconfigured' ? 'warn' : ''}` fails
     * here even if every sentence stays honest.
     */
    const chrome: string[] = [];
    for (const body of [
      assistantCompanionUnconfigured,
      assistantCompanionConfigured,
      assistantCompanionRefused,
    ]) {
      const { container } = await renderWith(body);
      const banner = within(container).getByRole('status');
      chrome.push(`${banner.tagName}|${banner.className}`);
      cleanup();
      vi.unstubAllGlobals();
    }
    expect(chrome).toHaveLength(3);
    expect(new Set(chrome).size, `banner chrome differed by state: ${chrome}`).toBe(1);
  });
});

// --- NEGATIVE CONTROL 3: no URL is ever invented -----------------------------

describe('no URL is invented, defaulted, or leaked from a state that may not have one', () => {
  it('renders no link when the state is not configured, EVEN IF the body carries a url', async () => {
    /*
     * THE BRANCH IS ON `state`, NOT ON `url` PRESENCE, and this is what proves
     * it. A server defect — or a partially-parsed body — that left a `url`
     * beside `unconfigured` or `refused` must not produce a link, because the
     * route's contract is that a url outside `configured` means nothing was
     * approved for offering.
     */
    for (const state of ['unconfigured', 'refused']) {
      const { container } = await renderWith({
        ...assistantCompanionUnconfigured,
        state,
        url: SYNTHETIC_COMPANION_URL,
      });
      expect(renderedUrls(container), `a link leaked in the ${state} state`).toEqual([]);
      cleanup();
      vi.unstubAllGlobals();
    }
  });

  it('renders no link when the configured state carries an empty or absent url', async () => {
    for (const url of ['', null, undefined]) {
      const { container } = await renderWith({
        ...assistantCompanionConfigured,
        url,
      });
      expect(renderedUrls(container)).toEqual([]);
      cleanup();
      vi.unstubAllGlobals();
    }
  });

  it('holds no URL literal of its own — the component and its copy are URL-free', () => {
    /*
     * Source-level and deliberately so: this is the one claim that is ABOUT the
     * source. "No default, no fallback, no placeholder that looks like a link"
     * is a statement about what is committed, and a DOM assertion cannot see a
     * constant that only renders under a branch no fixture reaches.
     */
    const files = [
      'screens/settings/AssistantCompanion.tsx',
      'lib/assistantCompanionContent.ts',
    ];
    let sweptBytes = 0;
    for (const rel of files) {
      const text = readFileSync(join(SRC, rel), 'utf8');
      sweptBytes += text.length;
      expect(text.match(ABSOLUTE_URL) ?? [], `${rel} holds a URL literal`).toEqual([]);
    }
    // Anti-vacuity: the files were really read.
    expect(sweptBytes).toBeGreaterThan(4000);
  });
});

// --- NEGATIVE CONTROL 4: a refusal echoes nothing ----------------------------

describe('a refusal names a category and echoes nothing', () => {
  it('renders no field of the body except the reason', async () => {
    /*
     * The canary sits in a field the refused branch must NOT render. If a future
     * author reaches for `data.url` — the most natural mistake, since a refusal
     * IS about a url — it appears in the DOM and this fires. Asserting on the
     * absence of a value the server never sends would prove nothing, because the
     * server not sending it is exactly what is being relied on.
     */
    const CANARY = 'CANARY-VALUE-THAT-MUST-NEVER-RENDER';
    const { container } = await renderWith({
      ...assistantCompanionRefused,
      url: CANARY,
    });
    expect(screen.getByText(assistantCompanionRefused.reason)).toBeInTheDocument();
    expect(everyString(container), 'the refused branch echoed a body field').not.toContain(
      CANARY,
    );
  });

  it('the canary check is not vacuous — it fires when the value IS rendered', async () => {
    // The same canary, in the field the configured branch DOES render, proves
    // the sweep can see a value that reaches the DOM.
    /*
     * ASSEMBLED SO THAT NO `claude.ai/` PREFIX EXISTS IN THE COMMITTED BYTES,
     * and the earlier version of this comment is the lesson.
     *
     * It said splitting the trailing id made the control safe "because the
     * committed bytes contain no URL carrying a long opaque segment". That was
     * true of the ID rule and FALSE of the MARKER rule, which is applied to the
     * same bytes by the sweeps below: the scheme-plus-host-plus-path prefix is
     * ITSELF a complete match for the URL regex, and it carries no marker. Both
     * controls therefore became offenders the moment this file was committed —
     * invisible while it was untracked, red in CI the instant it was not.
     *
     * (That prefix is deliberately DESCRIBED rather than quoted on this line.
     * Written out, this comment would reproduce the defect it explains — the
     * same recursion `source-is-greppable.test.ts` records happening twice to
     * its own doc comment about NUL bytes.)
     *
     * Splitting the SCHEME and HOST apart means the regex has nothing to anchor
     * on at all, so the control is invisible to every sweep in this file rather
     * than merely passing one of two.
     */
    const CANARY =
      'https://' + 'claude.ai' + '/public/artifacts/' + 'CANARY-VALUE-THAT-' + 'MUST-NEVER-RENDER';
    const { container } = await renderWith({
      ...assistantCompanionConfigured,
      url: CANARY,
    });
    expect(everyString(container)).toContain(CANARY);
  });
});

// --- NEGATIVE CONTROL 5: deep link only, and the prerequisite travels with it -

describe('deep link only, with the prerequisite beside it', () => {
  it('renders no embed, inline frame, or allowed-domain affordance, in any state', async () => {
    for (const body of [
      assistantCompanionUnconfigured,
      assistantCompanionConfigured,
      assistantCompanionRefused,
    ]) {
      const { container } = await renderWith(body);
      expect(container.querySelectorAll('iframe, embed, object, frame')).toHaveLength(0);
      // An allowed-domain control would be a field. So would a credential
      // prompt. Nothing here accepts typing at all.
      expect(
        container.querySelectorAll('input, textarea, select, [contenteditable="true"]'),
      ).toHaveLength(0);
      cleanup();
      vi.unstubAllGlobals();
    }
  });

  it('shows the prerequisite BEFORE the link, and only where a link exists', async () => {
    const { container } = await renderWith(assistantCompanionConfigured);
    const prerequisite = screen.getByText(assistantCompanionConfigured.prerequisite);
    const link = screen.getByRole('link', { name: new RegExp(COPY.openLinkText, 'i') });
    // Document order: the qualifier must be met before the affordance, not
    // after it and not in a footnote.
    const relation = prerequisite.compareDocumentPosition(link);
    expect(relation & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // `expect(container).toBeTruthy()` stood here and asserted nothing: a
    // render always returns a container. Replaced with the claim it was
    // presumably reaching for — that both nodes are inside this section, so the
    // ordering above is an ordering WITHIN the surface and not an accident of
    // two unrelated trees.
    expect(container.contains(prerequisite)).toBe(true);
    expect(container.contains(link)).toBe(true);
  });

  it('does NOT show the prerequisite where there is no link to qualify', async () => {
    for (const body of [assistantCompanionUnconfigured, assistantCompanionRefused]) {
      await renderWith(body);
      // It qualifies a link. Shown with none, it would describe how to reach a
      // companion this deployment does not have.
      expect(
        screen.queryByText(assistantCompanionUnconfigured.prerequisite),
      ).not.toBeInTheDocument();
      cleanup();
      vi.unstubAllGlobals();
    }
  });

  it('states the limits in EVERY state, including the failed read', async () => {
    // The limits are properties of what this section can establish, not of what
    // it happened to find, so they may not live inside a branch.
    for (const render_ of [
      () => renderWith(assistantCompanionUnconfigured),
      () => renderWith(assistantCompanionConfigured),
      () => renderWith(assistantCompanionRefused),
      () => renderUnreadable(),
    ]) {
      await render_();
      for (const limit of COPY.limits) {
        expect(screen.getByText(limit.claim)).toBeInTheDocument();
      }
      cleanup();
      vi.unstubAllGlobals();
    }
  });

  it('publishes the SETTING NAME and never a value, from the server not a literal', async () => {
    const { container } = await renderWith({
      ...assistantCompanionUnconfigured,
      configured_by: 'A_RENAMED_VARIABLE',
    });
    // Read from the body, so a rename on the server cannot leave a wrong name
    // published here.
    expect(screen.getByText('A_RENAMED_VARIABLE')).toBeInTheDocument();
    expect(visibleText(container)).not.toContain('ISAAC_ASSISTANT_ARTIFACT_URL');
  });
});

// --- a malformed body degrades one line, and never blanks the page -----------

describe('a server value this client cannot show costs one line, not the page', () => {
  /*
   * THE FAILURE MODE, MEASURED BEFORE THE FIX: this application has no
   * `ErrorBoundary` anywhere, so a non-string reaching JSX throws "Objects are
   * not valid as a React child" during render and React unmounts the whole tree.
   * That is not this section going blank — it is the entire Settings page.
   *
   * These are behavioural: each feeds a wrong-typed value and asserts the
   * section still rendered, which a string check on the fallback sentence could
   * not establish.
   */
  it.each([['reason'], ['prerequisite'], ['configured_by'], ['reference']])(
    'renders the section when %s is not a string',
    async (field) => {
      const { container } = await renderWith({
        ...assistantCompanionConfigured,
        [field]: { nested: 'object' },
      });
      // The section is still on screen — the claim that matters.
      expect(screen.getByRole('heading', { name: COPY.heading })).toBeInTheDocument();
      expect(container.querySelectorAll('h3, h4').length).toBeGreaterThan(3);
      // And no `[object Object]` was coerced onto the page in its place.
      expect(everyString(container)).not.toContain('[object Object]');
    },
  );

  it('a malformed field costs ONLY its own line — a configured link still works', async () => {
    // The §11 precedent, asserted rather than assumed: one unreadable value must
    // not take the working parts of the surface with it.
    const { container } = await renderWith({
      ...assistantCompanionConfigured,
      reference: 12345,
    });
    expect(renderedUrls(container)).toEqual([SYNTHETIC_COMPANION_URL]);
    expect(
      screen.getByRole('link', { name: new RegExp(COPY.openLinkText, 'i') }),
    ).toBeInTheDocument();
  });

  it('the fallback never invents a value, and never claims a state', async () => {
    const { container } = await renderWith({
      ...assistantCompanionRefused,
      reason: ['an', 'array'],
    });
    const swept = everyString(container);
    expect(swept).not.toMatch(CONNECTION_CLAIM);
    expect(swept).not.toMatch(REACHABILITY_CLAIM);
    expect(swept).not.toMatch(STATE_CLAIM);
    // Nothing from the malformed value is reconstructed onto the page.
    expect(swept).not.toContain('array');
  });
});

// --- accessibility ------------------------------------------------------------

describe('accessibility', () => {
  it('conveys the state as text in a POLITE live region, never as colour', async () => {
    const { container } = await renderWith(assistantCompanionUnconfigured);
    const status = within(container).getByRole('status');
    expect(within(status).getByText(COPY.unconfiguredLabel)).toBeInTheDocument();
    // `role="status"` is implicitly polite; assertive would interrupt a reader
    // for a configuration readout, which is never urgent.
    expect(status.getAttribute('aria-live')).not.toBe('assertive');
    expect(visibleText(container)).not.toMatch(/\b(green|amber|red|yellow)\b/i);
  });

  it('offers the link as a real anchor with an accessible name and safe rel', async () => {
    await renderWith(assistantCompanionConfigured);
    const link = screen.getByRole('link', { name: new RegExp(COPY.openLinkText, 'i') });
    expect(link.tagName).toBe('A');
    expect(link).toHaveAttribute('href', SYNTHETIC_COMPANION_URL);
    expect((link.textContent ?? '').trim().length).toBeGreaterThan(0);
    // Keyboard-reachable: an anchor with an href is in the tab order, and
    // nothing removes it.
    expect(link).not.toHaveAttribute('tabindex', '-1');
    const rel = link.getAttribute('rel') ?? '';
    expect(rel).toContain('noopener');
    expect(rel).toContain('noreferrer');
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('offers the verify control as a real, keyboard-operable button', async () => {
    const { container } = await renderWith(assistantCompanionUnconfigured);
    const button = within(container).getByRole('button', {
      name: new RegExp(COPY.verifyAction, 'i'),
    });
    expect(button.tagName).toBe('BUTTON');
    expect(button).toHaveAttribute('type', 'button');
    expect(button).not.toBeDisabled();
    expect(button).not.toHaveAttribute('tabindex', '-1');
  });

  it('keeps a gapless heading outline, in every state', async () => {
    for (const body of [
      assistantCompanionUnconfigured,
      assistantCompanionConfigured,
      assistantCompanionRefused,
    ]) {
      const { container } = await renderWith(body);
      const headings = Array.from(container.querySelectorAll('h1,h2,h3,h4,h5,h6'));
      expect(headings.length).toBeGreaterThan(0);
      for (const h of headings) {
        expect((h.textContent ?? '').trim().length, 'an empty heading').toBeGreaterThan(0);
      }
      const levels = headings.map((h) => Number(h.tagName[1]));
      // The section opens at h3 (the card supplies the h2) and never skips.
      expect(levels[0]).toBe(3);
      for (let i = 1; i < levels.length; i += 1) {
        expect(levels[i] - levels[i - 1], `outline: ${levels.join(',')}`).toBeLessThanOrEqual(1);
      }
      cleanup();
      vi.unstubAllGlobals();
    }
  });

  it('every icon is decorative, so none of them carries the state', async () => {
    const { container } = await renderWith(assistantCompanionConfigured);
    for (const svg of Array.from(container.querySelectorAll('svg'))) {
      expect(svg.getAttribute('aria-hidden')).toBe('true');
    }
  });
});

// --- the styling contract: no new CSS, no undeclared custom property ---------

function locateSrcDir(): string {
  const candidates = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
  const found = candidates.find((dir) => existsSync(join(dir, 'main.tsx')));
  if (found === undefined) throw new Error(`cannot locate apps/web/src from ${process.cwd()}`);
  return found;
}
const SRC = locateSrcDir();
const REPO_ROOT = join(SRC, '..', '..', '..');

describe('the styling contract', () => {
  it('adds no stylesheet and references only classes the design system already defines', () => {
    const source = readFileSync(join(SRC, 'screens/settings/AssistantCompanion.tsx'), 'utf8');
    // No new CSS file is imported, so this slice cannot introduce a custom
    // property at all — which is the strongest available form of "no undeclared
    // custom property" for a component that ships none.
    expect(source).not.toMatch(/import\s+['"][^'"]+\.css['"]/);
    expect(source).not.toMatch(/var\(--/);

    // EVERY stylesheet the app loads, not the two this section happens to draw
    // from: a class defined elsewhere is still a class the design system defines,
    // and a guard that named only two files would report a false "undeclared".
    // `.mono` lives in `styles/base.css`, which the first version of this list
    // omitted and was told about.
    const css = [
      'screens/screens.css',
      'styles/tokens.css',
      'styles/base.css',
    ]
      .map((rel) => readFileSync(join(SRC, rel), 'utf8'))
      .join('\n');
    const used = new Set(
      Array.from(source.matchAll(/className="([^"{}]+)"/g)).flatMap((m) =>
        m[1].split(/\s+/).filter(Boolean),
      ),
    );
    // Anti-vacuity: the extraction really found the classes.
    expect(used.size).toBeGreaterThan(5);
    for (const name of used) {
      expect(css.includes(`.${name}`), `undeclared class: .${name}`).toBe(true);
    }
  });
});

// --- the governance guard: no real artifact URL may enter this repository ----

describe('no committed URL can be mistaken for a real artifact', () => {
  const CLAUDE_URL = /https?:\/\/(?:www\.)?claude\.ai\/[^\s"'`<>)\]]*/gi;
  const TEXTUAL = /\.(ts|tsx|js|jsx|css|json|py|md|ya?ml|html)$/;

  /** Every path `git ls-files` reports. */
  function everyTrackedPath(): string[] {
    return execFileSync('git', ['ls-files', '-z'], {
      cwd: REPO_ROOT,
      maxBuffer: 64 * 1024 * 1024,
    })
      .toString('utf8')
      // NUL-delimited, so a path containing a newline survives — and the
      // delimiter is written as an ESCAPE. A raw NUL in this file would make the
      // file invisible to `grep`/`rg` without `-a`, which is the trap
      // `source-is-greppable.test.ts` exists for. THIS FILE SHIPPED ONE ON ITS
      // FIRST WRITE, on this exact line, and again on the first attempt to fix
      // it. That is the third and fourth recorded occurrence in this repository,
      // and it is why that guard is a test rather than a note.
      .split('\u0000')
      .filter((rel) => rel !== '');
  }

  /**
   * A path segment that cannot be a real artifact id: at least 16 characters
   * from the opaque-id alphabet, unless it SAYS it is synthetic.
   *
   * THE EXEMPTION IS BY CONTENT, NOT BY AN EQUALITY ALLOWLIST, and that is the
   * whole reason it works across files this slice does not own.
   * `test_assistant_artifact_companion_route.py` already states this rule for
   * itself at `_NON_IDENTIFYING_PATHS`: every `claude.ai` path in that file
   * "either says `synthetic` outright" or is one of three enumerated stubs. So
   * `includes('synthetic')` is not a carve-out invented here to make a red test
   * green — it is the neighbouring file's own published rule, applied by this
   * one. An equality list of that file's literals would have gone stale the
   * first time it added a fixture, which is the failure mode of pinning strings
   * instead of properties.
   */
  function looksLikeARealId(segment: string): boolean {
    if (segment.toLowerCase().includes('synthetic')) return false;
    return segment.length >= 16 && /^[A-Za-z0-9_-]+$/.test(segment);
  }

  /** Every segment of a URL's path, query and fragment. */
  function segmentsOf(url: string): string[] {
    return url.replace(/^https?:\/\/(?:www\.)?claude\.ai/i, '').split(/[/?#&=]/);
  }

  /**
   * BOTH RULES, over one list of files. Factored out because the by-path sweep
   * below applied only the ID rule and was therefore structurally unable to see
   * the two MARKER offenders it was added to catch — a fix-for-the-fix that left
   * half the hole open.
   */
  function offendersIn(paths: readonly string[]): {
    unmarked: string[];
    suspicious: string[];
    found: number;
  } {
    const unmarked: string[] = [];
    const suspicious: string[] = [];
    const urls = urlsUnder(paths);
    for (const { rel, url } of urls) {
      if (!url.includes(SYNTHETIC_COMPANION_MARKER)) unmarked.push(rel + ': ' + url);
      for (const segment of segmentsOf(url)) {
        if (looksLikeARealId(segment)) {
          suspicious.push(rel + ': ' + url + ' (segment "' + segment + '")');
        }
      }
    }
    return { unmarked, suspicious, found: urls.length };
  }

  function urlsUnder(paths: readonly string[]): { rel: string; url: string }[] {
    const found: { rel: string; url: string }[] = [];
    for (const rel of paths) {
      if (!TEXTUAL.test(rel)) continue;
      let text: string;
      try {
        text = readFileSync(join(REPO_ROOT, rel), 'utf8');
      } catch {
        continue;
      }
      for (const url of text.match(CLAUDE_URL) ?? []) found.push({ rel, url });
    }
    return found;
  }

  /*
   * TWO GUARDS, AT TWO SCOPES, AND THE SCOPES DIFFER ON PURPOSE.
   *
   * The strong rule — "carries the marker" — can only be imposed where this
   * slice owns the files. Tracked source outside `apps/web` already holds
   * obviously-synthetic companion URLs written by the backend slice and by two
   * vendor-audit documents, and rewriting somebody else's fixtures to satisfy a
   * guard written here would be scope creep dressed as safety.
   *
   * So the repository-wide guard asserts the weaker property that actually
   * matters, stated mechanically rather than by taste: a REAL artifact URL
   * carries a long opaque identifier, and none of the committed ones does. That
   * is checkable, needs no allowlist of other people's strings, and fires on a
   * real URL pasted anywhere in the repository.
   */

  it('every claude.ai URL under apps/web carries the synthetic marker', () => {
    const web = everyTrackedPath().filter((rel) => rel.startsWith('apps/web/'));

    // ANTI-VACUITY, PART ONE: the sweep really enumerated the tree. A broken
    // `git` call returning nothing would pass every assertion below.
    expect(web.length).toBeGreaterThan(100);
    expect(web).toContain('apps/web/src/test/apiFixtures.ts');

    const { unmarked, found } = offendersIn(web);

    // ANTI-VACUITY, PART TWO: at least one URL was actually matched, so a regex
    // that matched nothing cannot read as a clean sweep. This assertion HAS
    // fired for real: the fixture originally built its URL by template
    // interpolation, so the committed bytes held the placeholder rather than the
    // marker, and the "clean" result was entirely vacuous.
    expect(found, 'the URL sweep matched no URL — it proves nothing').toBeGreaterThan(0);

    expect(unmarked, 'an unmarked artifact URL is committed under apps/web').toEqual([]);
  });

  it('no claude.ai URL anywhere in the repository carries a plausible artifact id', () => {
    /*
     * A published artifact URL is ACCESS-BEARING in an organization: the path is
     * what decides who can reach it. Committing one would put an access-bearing
     * identifier into a history that outlives the artifact.
     *
     * "Plausible artifact id" is defined mechanically as a path segment of at
     * least 16 characters drawn only from the opaque-id alphabet. Every
     * committed URL's segments are short placeholders (`x`, `some-id`,
     * `synthetic-id`, `auth_callback`), so the rule costs nothing today and
     * fires the moment a real one is pasted. The marker is longer than the
     * threshold and is exempted BY VALUE rather than by length, because it says
     * in words what it is.
     */
    const { suspicious, found } = offendersIn(everyTrackedPath());
    expect(found, 'the repository-wide sweep matched no URL').toBeGreaterThan(0);
    expect(suspicious, 'a committed URL carries what looks like a real artifact id').toEqual(
      [],
    );
  });

  it('THE ID RULE IS NOT VACUOUS — it fires on a URL shaped like a real one', () => {
    // Without this the threshold could be wrong by an order of magnitude and
    // every assertion above would still pass over every file.
    // Scheme and host split apart, for the reason set out at the canary above:
    // splitting only the id left the `claude.ai/` prefix as a committed literal,
    // which the MARKER rule counts as an unmarked URL even though the ID rule is
    // satisfied. A control that trips one of the two guards it exists to
    // validate is not a control.
    const REAL_SHAPED =
      'https://' + 'claude.ai' + '/public/artifacts/' + 'a1b2c3d4-e5f6' + '-7890abcdef1234';
    const segments = REAL_SHAPED.replace(/^https?:\/\/(?:www\.)?claude\.ai/i, '').split(
      /[/?#&=]/,
    );
    expect(
      segments.some((seg) => seg.length >= 16 && /^[A-Za-z0-9_-]+$/.test(seg)),
      'the id heuristic would not catch a real-shaped URL',
    ).toBe(true);
    // And the marker IS long enough to be caught, which is why the exemption
    // above has to exist and is not decoration.
    expect(SYNTHETIC_COMPANION_MARKER.length).toBeGreaterThanOrEqual(16);
  });

  it('sweeps THIS SLICE’S OWN FILES by path, applying BOTH rules, tracked or not', () => {
    /*
     * THE GAP THIS CLOSES, AND IT HAS NOW BEEN A REAL ONE TWICE.
     *
     * Both sweeps above enumerate `git ls-files`, so a file written but not yet
     * committed is INVISIBLE to them — including this one. The two anti-vacuity
     * controls in this file originally wrote a real-shaped URL as a single
     * literal, and both sweeps reported clean solely because the file was
     * untracked. The moment it was committed, both went red in CI.
     *
     * THE FIRST VERSION OF THIS TEST — added specifically to close that — DID
     * NOT CLOSE IT, in two independent ways, and the shape of the miss is worth
     * more than the fix:
     *
     *   · it applied only the ID rule, never the MARKER rule, so it was
     *     structurally unable to see the very offenders it was written for; and
     *   · its `own` list named four `apps/web` files and omitted
     *     `apps/api/tests/.../route.py`, where three further offenders lived.
     *
     * A guard written to catch a specific miss, that reproduces the miss, is the
     * recurring defect this whole file is about. It now runs the SAME predicate
     * pair as the two sweeps above — not a second implementation that can drift
     * from them — over an explicit path list, so the result does not depend on
     * whether a commit has happened yet.
     */
    const own = [
      'apps/web/src/__tests__/assistant-companion.test.tsx',
      'apps/web/src/lib/assistantCompanionContent.ts',
      'apps/web/src/screens/settings/AssistantCompanion.tsx',
      'apps/web/src/test/apiFixtures.ts',
      // The backend half of the same slice. Omitting it is how three offenders
      // reached `main`: this file's author owned it, and the sweep did not.
      'apps/api/tests/test_assistant_artifact_companion_route.py',
    ];

    // Anti-vacuity, part one: every named file exists. A typo'd path would
    // otherwise be silently skipped by `urlsUnder`'s read guard and shrink the
    // sweep to nothing while still reading clean.
    for (const rel of own) {
      expect(existsSync(join(REPO_ROOT, rel)), 'named but missing: ' + rel).toBe(true);
    }

    const { unmarked, suspicious, found } = offendersIn(own);

    // Anti-vacuity, part two: at least one URL was actually matched.
    expect(found, 'this slice’s own files matched no URL').toBeGreaterThan(0);

    // The ID rule binds everywhere, including files this slice does not own the
    // conventions of.
    expect(suspicious, 'this slice committed a URL shaped like a real artifact').toEqual([]);

    // The MARKER rule binds only under `apps/web`, where this slice sets the
    // convention. The backend file states and enforces its own equivalent rule
    // (`_NON_IDENTIFYING_PATHS`), and imposing this one on it would mean
    // rewriting another slice's fixtures to satisfy a guard written here.
    const webOnly = unmarked.filter((entry) => entry.startsWith('apps/web/'));
    expect(webOnly, 'an unmarked artifact URL is committed under apps/web').toEqual([]);
  });

  it('the marker itself says what it is, in words, not just by convention', () => {
    // A marker a reader has to look up is not a marker. This one is a sentence.
    expect(SYNTHETIC_COMPANION_MARKER).toMatch(/synthetic/i);
    expect(SYNTHETIC_COMPANION_MARKER).toMatch(/not-a-real/i);
    expect(SYNTHETIC_COMPANION_URL).toContain(SYNTHETIC_COMPANION_MARKER);
  });
});
