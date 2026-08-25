/**
 * Settings → Connect Your Agent.
 *
 * The tab's defining requirement is that it must never lie about being
 * connected, so most of this file is negative: it asserts the absence of the
 * five things a surface like this reaches for when it has nothing true to show
 * — a Connected state, an endpoint URL, a last-activity date, a Revoke button,
 * and a credential field.
 *
 * TWO RULES THIS FILE FOLLOWS, BOTH BECAUSE A WEAKER VERSION WOULD PASS ON A
 * BROKEN PAGE:
 *
 *  1. **Every absence is asserted against the rendered DOM, never against the
 *     source.** A grep over `ConnectYourAgent.tsx` for `<input` would go quiet
 *     the moment a field arrived through a shared component, which is exactly
 *     the route by which one would arrive. So the credential check queries the
 *     mounted tree for every element that accepts typing, and the URL check
 *     reads text content *and* every attribute.
 *  2. **The negative controls are flat substring ratchets, not
 *     negation-aware.** `not.toMatch(/\bconnected\b/i)` fails on "no agent is
 *     connected" too. That is deliberate: a guard a future author can satisfy
 *     by inserting the word "not" is not a guard, and the page is written to
 *     the ratchet rather than the ratchet loosened to the page.
 *
 * The one positive branch — an endpoint the deployment supplies — is exercised
 * through the panel's `endpoint` prop, and the same Connected ratchet is
 * re-run against it. An address existing is not evidence that anything reached
 * it, and the page must not start claiming otherwise the day D1 is answered.
 */
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, within, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { SettingsPage } from '../screens/SettingsPage';
import { ConnectYourAgentPanel } from '../screens/settings/ConnectYourAgent';
import {
  MCP_CAPABILITIES_ALLOWED,
  MCP_CAPABILITIES_REFUSED,
  MCP_CONNECT_COPY,
  MCP_ENDPOINT,
  MCP_PERMISSIONS,
  MCP_SETUP_STEPS,
  mcpDeploymentState,
} from '../lib/mcpConnectContent';
import { SETTINGS_TAB_IDS, ROUTES, isSettingsTab } from '../lib/routes';
import { stubFetchRoutes, aboutResponse, graphStatusAvailable, openApiFixture } from '../test/apiFixtures';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const TAB_LABEL = 'Connect Your Agent';

function fullRoutes() {
  return {
    'GET /api/about': { body: aboutResponse },
    'GET /api/openapi': { body: openApiFixture },
    'GET /api/graph/status': { body: graphStatusAvailable },
  };
}

/** The whole Settings page, deep-linked to a tab exactly as a shared link would. */
function renderSettings(entry = ROUTES.settingsTab('mcp')) {
  stubFetchRoutes(fullRoutes());
  return render(
    <MemoryRouter
      initialEntries={[entry]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <SettingsPage />
    </MemoryRouter>,
  );
}

/** The panel alone, so the endpoint branch can be driven without a deployment. */
function renderPanel(endpoint?: string | null) {
  return render(
    <ConnectYourAgentPanel endpoint={endpoint} onOpenExplorer={() => {}} />,
  );
}

const norm = (s: string) => s.replace(/\s+/g, ' ').trim();

/**
 * The tab's text with element boundaries PRESERVED as whitespace.
 *
 * `container.textContent` concatenates adjacent elements with no separator, so
 * `<h3>Connected</h3><p>No agent…</p>` yields `ConnectedNo agent…` — and
 * `/\bconnected\b/i` does NOT match that, because the `d` is followed by a word
 * character and there is no boundary for `\b` to find.
 *
 * This is not a hypothetical. Every ratchet below was first written against
 * `textContent`, and a mutation that set the status heading to the single word
 * `Connected` PASSED all 26 tests — the one mutation the whole file exists to
 * catch. The guard was defeated by adjacency, not by any weakness in the regex.
 *
 * Joining the text NODES restores the boundary that the DOM always had and that
 * the flattened string had lost. Every assertion that reads text on this tab
 * goes through here for that reason; `textContent` is not used directly.
 */
function visibleText(container: HTMLElement): string {
  const walker = container.ownerDocument.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const parts: string[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    parts.push(node.nodeValue ?? '');
  }
  return parts.join('\n');
}

// --- the tab exists, and is reachable the way every other tab is -------------

describe('Connect Your Agent — the tab', () => {
  it('is a registered Settings tab id', () => {
    expect(SETTINGS_TAB_IDS).toContain('mcp');
    expect(isSettingsTab('mcp')).toBe(true);
  });

  it('renders as a tab in the page tablist', () => {
    renderSettings(ROUTES.settingsTab('overview'));
    expect(screen.getByRole('tab', { name: TAB_LABEL })).toBeInTheDocument();
  });

  it('opens from a ?tab= deep link, with its real content and not an empty panel', () => {
    renderSettings();
    expect(screen.getByRole('tab', { name: TAB_LABEL })).toHaveAttribute('aria-selected', 'true');

    const panel = screen.getByRole('tabpanel', { name: TAB_LABEL });
    expect(panel).toHaveAttribute('id', 'settings-tabpanel-mcp');
    expect(panel).toHaveAttribute('aria-labelledby', 'settings-tab-mcp');
    expect(within(panel).getByText(MCP_CONNECT_COPY.statusLabel)).toBeInTheDocument();
  });

  it('the deep link helper builds the URL the page actually reads', () => {
    expect(ROUTES.settingsTab('mcp')).toBe('/settings?tab=mcp');
  });
});

// --- the unconfigured state renders AS unconfigured --------------------------

describe('Connect Your Agent — the unconfigured state', () => {
  it('the module ships no endpoint, so the derived state is requires-configuration', () => {
    expect(MCP_ENDPOINT).toBeNull();
    expect(mcpDeploymentState(MCP_ENDPOINT)).toBe('requires-configuration');
  });

  it('states the configuration requirement as its heading and explains who owns it', () => {
    const { container } = renderPanel();
    expect(screen.getByRole('heading', { name: MCP_CONNECT_COPY.statusLabel })).toBeInTheDocument();
    expect(norm(visibleText(container))).toContain(norm(MCP_CONNECT_COPY.statusDetail));
    expect(norm(visibleText(container))).toContain(norm(MCP_CONNECT_COPY.statusOwner));
  });

  it('conveys the state as text inside a live region, not as colour', () => {
    const { container } = renderPanel();
    // The state is announced if it ever changes, and reads identically to a
    // screen reader, a monochrome display and a sighted user.
    const status = screen.getByRole('status');
    expect(within(status).getByText(MCP_CONNECT_COPY.statusLabel)).toBeInTheDocument();
    // Nothing anywhere on the tab leans on a colour word to carry the state.
    expect(visibleText(container)).not.toMatch(/\b(green|amber|red|yellow)\b/i);
  });

  it('says there is no endpoint rather than showing a placeholder address', () => {
    const { container } = renderPanel();
    expect(screen.getByRole('heading', { name: MCP_CONNECT_COPY.endpointHeading })).toBeInTheDocument();
    expect(norm(visibleText(container))).toContain(norm(MCP_CONNECT_COPY.endpointNone));
  });
});

// --- the negative controls ---------------------------------------------------

/**
 * XML namespace identifiers, which are URIs that name a vocabulary and are not
 * addresses anything is fetched from or a reader could copy.
 *
 * Exempted BY EXACT VALUE rather than by attribute name. `xmlns`-anything would
 * have been the easier rule and the weaker one: it exempts a location as long as
 * it is parked in an attribute starting with those five letters. Pinning the
 * literal keeps every other value in the sweep, and makes a second namespace
 * arriving one day a deliberate edit here rather than a silent widening.
 */
const XML_NAMESPACES = new Set(['http://www.w3.org/2000/svg']);

/** Every attribute value on the tab, less the XML namespace declarations. */
function everyAttributeValue(container: HTMLElement): string[] {
  const values: string[] = [];
  for (const el of Array.from(container.querySelectorAll('*'))) {
    for (const attr of Array.from(el.attributes)) {
      if (XML_NAMESPACES.has(attr.value)) continue;
      values.push(attr.value);
    }
  }
  return values;
}

describe('Connect Your Agent — negative controls', () => {
  it('NOTHING on the tab reads "connected" when the deployment is unconfigured', () => {
    const { container } = renderPanel();
    expect(visibleText(container)).not.toMatch(/\bconnected\b/i);
    // And no element is *named* it either — an accessible name is text a user
    // reads, and a `Connected` chip whose label lived in `aria-label` would
    // pass a textContent-only check.
    for (const value of everyAttributeValue(container)) {
      expect(value, `attribute claims a connection: ${value}`).not.toMatch(/\bconnected\b/i);
    }
  });

  it('the same ratchet holds through the whole Settings page on this tab', () => {
    const { container } = renderSettings();
    expect(visibleText(container)).not.toMatch(/\bconnected\b/i);
  });

  it('fabricates no endpoint URL — no URL appears in text or in any attribute', () => {
    const { container } = renderPanel();
    expect(visibleText(container)).not.toMatch(/https?:\/\//i);
    expect(visibleText(container)).not.toMatch(/\bwss?:\/\//i);
    for (const value of everyAttributeValue(container)) {
      expect(value, `attribute carries a URL: ${value}`).not.toMatch(/https?:\/\//i);
    }
  });

  it('renders no last-activity value — absent is the honest value, and it says why', () => {
    const { container } = renderPanel();
    const text = visibleText(container);
    expect(norm(text)).toContain(norm(MCP_CONNECT_COPY.activityNone));

    /*
     * THE DATE ASSERTION IS AN ALLOWLIST, NOT A BAN, and the difference is the
     * point. The tab legitimately carries ONE date — 2026-08-12, when the two
     * infrastructure decisions were deferred. That is a fact about a decision,
     * not a timestamp of anything an agent did. A blanket "no dates" rule would
     * have forced that fact off the page; an allowlist keeps it while making any
     * *second* date fail here until somebody writes down what it is.
     */
    const dates = text.match(/\d{4}-\d{2}-\d{2}/g) ?? [];
    expect(dates, 'an unexplained date appeared on the tab').toEqual(['2026-08-12']);

    // No clock time, no relative time, no labelled activity value, no `<time>`.
    expect(text).not.toMatch(/\b\d{1,2}:\d{2}\b/);
    expect(text).not.toMatch(/\b\d+\s*(second|minute|hour|day|week|month)s?\s+ago\b/i);
    expect(text).not.toMatch(/\blast\s+(activity|seen|used|call|request|connection)\b/i);
    expect(container.querySelector('time')).toBeNull();
  });

  it('offers no Revoke or Disconnect control, and says why there is none', () => {
    const { container } = renderPanel();
    for (const button of screen.queryAllByRole('button')) {
      expect(
        button.textContent ?? '',
        `a control that could revoke nothing: ${button.textContent}`,
      ).not.toMatch(/\b(revoke|disconnect|sign out|remove access|deauthori[sz]e)\b/i);
    }
    // The absence is explained rather than silent.
    expect(norm(visibleText(container))).toContain(norm(MCP_CONNECT_COPY.revocationNone));
  });

  /** Every element that accepts typing, by tag, by role, and by editability. */
  function assertNothingAcceptsTyping(root: HTMLElement) {
    expect(root.querySelectorAll('input')).toHaveLength(0);
    expect(root.querySelectorAll('textarea')).toHaveLength(0);
    expect(root.querySelectorAll('select')).toHaveLength(0);
    expect(root.querySelectorAll('form')).toHaveLength(0);
    expect(root.querySelectorAll('[contenteditable]')).toHaveLength(0);
    for (const role of ['textbox', 'searchbox', 'combobox', 'spinbutton'] as const) {
      expect(within(root).queryAllByRole(role), `a ${role} on the tab`).toHaveLength(0);
    }
    // …and nothing that merely *looks* like a place to paste one.
    expect(visibleText(root)).not.toMatch(/\b(paste|enter|copy) your\b|\byour (api )?key\b/i);
  }

  it('has NOTHING that accepts typing anywhere on the tab', () => {
    // Asserted against the mounted DOM, not by reading the source: a field
    // arriving through a shared component would be invisible to a grep and
    // is the likeliest way one would arrive.
    const { container } = renderPanel();
    assertNothingAcceptsTyping(container);
  });

  it('…and none in the tab PANEL either, chrome and shared card included', () => {
    /*
     * The check above mounts the panel body alone, which is the component this
     * slice wrote. This one mounts the real Settings page, deep-linked to the
     * tab, and scopes to the actual `tabpanel` — so it covers the shared
     * `SettingsCard` chrome around the body as well. A credential field is
     * likeliest to arrive through shared furniture, and the narrower check is
     * exactly the one that would not see it.
     */
    renderSettings();
    assertNothingAcceptsTyping(screen.getByRole('tabpanel', { name: TAB_LABEL }));
  });

  it('names no credential value and no environment variable that would hold one', () => {
    const { container } = renderPanel();
    const text = visibleText(container);
    expect(text).not.toMatch(/VITE_[A-Z_]+/);
    expect(text).not.toMatch(/\bsk-[a-z0-9]/i);
    expect(text).not.toMatch(/\bBearer\s+\S/);
  });
});

// --- the claims a scientist is actually here for ------------------------------

describe('Connect Your Agent — what it tells a scientist', () => {
  it('states that no agent can submit, in its own section and in the boundary list', () => {
    const { container } = renderPanel();
    const text = norm(visibleText(container));
    expect(
      screen.getByRole('heading', { name: MCP_CONNECT_COPY.neverSubmitHeading }),
    ).toBeInTheDocument();
    expect(text).toContain(norm(MCP_CONNECT_COPY.neverSubmitDetail));
    const noSubmit = MCP_CAPABILITIES_REFUSED.find((c) => c.id === 'no-submit');
    expect(noSubmit, 'the refusal list must carry the submit row').toBeDefined();
    expect(text).toContain(norm(noSubmit!.action));
    expect(text).toContain(norm(noSubmit!.detail));
  });

  it('renders every allowed capability and every refused one', () => {
    const { container } = renderPanel();
    const text = norm(visibleText(container));
    for (const capability of [...MCP_CAPABILITIES_ALLOWED, ...MCP_CAPABILITIES_REFUSED]) {
      expect(text, `missing capability: ${capability.action}`).toContain(norm(capability.action));
      expect(text, `missing detail: ${capability.action}`).toContain(norm(capability.detail));
    }
  });

  it('renders both permissions with what each allows and refuses', () => {
    const { container } = renderPanel();
    const text = norm(visibleText(container));
    expect(MCP_PERMISSIONS).toHaveLength(2);
    for (const permission of MCP_PERMISSIONS) {
      expect(text).toContain(permission.name);
      expect(text).toContain(norm(permission.allows));
      expect(text).toContain(norm(permission.refuses));
    }
    expect(text).toContain(norm(MCP_CONNECT_COPY.permissionsDetail));
  });

  it('renders the setup steps, with the blocking precondition above them', () => {
    const { container } = renderPanel();
    const text = norm(visibleText(container));
    expect(text).toContain(norm(MCP_CONNECT_COPY.setupPrerequisite));
    for (const step of MCP_SETUP_STEPS) {
      expect(text, `missing step: ${step.title}`).toContain(norm(step.title));
    }
    // The precondition precedes the first step, so a reader cannot start the
    // procedure before being told it cannot be completed.
    const prerequisiteAt = text.indexOf(norm(MCP_CONNECT_COPY.setupPrerequisite));
    const firstStepAt = text.indexOf(norm(MCP_SETUP_STEPS[0].title));
    expect(prerequisiteAt).toBeGreaterThanOrEqual(0);
    expect(prerequisiteAt).toBeLessThan(firstStepAt);
  });

  it('qualifies the capability material as defined rather than running', () => {
    const { container } = renderPanel();
    expect(norm(visibleText(container))).toContain(norm(MCP_CONNECT_COPY.provenanceNote));
  });

  it('states the one-way direction, so nobody reads this as ISAAC gaining an AI', () => {
    const { container } = renderPanel();
    expect(norm(visibleText(container))).toContain(norm(MCP_CONNECT_COPY.oneWayDetail));
  });

  it('points at the HTTP API as a separate mechanism, so neither tab is read alone', () => {
    /*
     * Two controls one word and two tabs apart. API Access → Connect an Agent
     * says a call carries a credential in a header where a deployment enables
     * authentication; this tab says there is no configured way to authenticate
     * a caller. Both true of their own path, and a reader who meets only one of
     * them concludes either that the agent story works or that ISAAC has no
     * program access at all. The pointer is what stops that, so it is pinned —
     * and it is pinned in BOTH endpoint branches, because the distinction does
     * not lapse the day an address is published.
     */
    expect(norm(visibleText(renderPanel().container))).toContain(
      norm(MCP_CONNECT_COPY.restApiPointer),
    );
    cleanup();
    expect(norm(visibleText(renderPanel('https://agent.example.invalid/mcp').container))).toContain(
      norm(MCP_CONNECT_COPY.restApiPointer),
    );
  });
});

// --- the confirmation is the AGENT's claim, and the page has to say so ---------

/**
 * C1. The write-draft row used to read "Each write carries your confirmation as
 * its support" — which a scientist reads as a GATE, as though ISAAC had asked
 * them and recorded the answer.
 *
 * It has not, and cannot. `confirmed_by_user` is a boolean the CALLER sends and
 * the server passes through unchanged; it is then stored as `user_confirmation`
 * evidence, which under `CLAUDE.md` §5 is the support for a value that has no
 * other evidence. So an agent that asked nothing writes a field whose evidence
 * trail is indistinguishable from one the scientist really confirmed — and the
 * page that a scientist reads before granting `isaac:draft.write` was the one
 * place describing that as their own confirmation.
 *
 * The direction of the assertion is therefore pinned, in both polarities: the
 * honest wording has to be PRESENT, and the wording that reads as a gate has to
 * be ABSENT. Pinning only the first would pass on a row that said both.
 */
describe('Connect Your Agent — the draft-write confirmation, whose claim it is', () => {
  const writeRow = MCP_CAPABILITIES_ALLOWED.find((c) => c.id === 'write-draft');

  it('the row this is about still exists and still describes the write tool', () => {
    // A vacuous guard would be one where the row was renamed away and every
    // assertion below started passing over an `undefined` that never rendered.
    expect(writeRow, 'the write-draft capability row is gone').toBeDefined();
    expect(writeRow!.tools).toEqual(['isaac_update_draft']);
  });

  it('names the AGENT as the party asserting the confirmation', () => {
    const { container } = renderPanel();
    const text = norm(visibleText(container));
    expect(text).toContain(norm(writeRow!.detail));
    expect(writeRow!.detail).toMatch(/the agent’s assertion that you gave it/i);
  });

  it('says ISAAC cannot check it, and turns that into advice the reader can act on', () => {
    // Not merely "ISAAC does not verify" as a fact left hanging: the reader's
    // only available control is which agent they grant the permission to, so
    // the sentence has to say that.
    expect(writeRow!.detail).toMatch(/ISAAC cannot check/i);
    expect(writeRow!.detail).toMatch(/trust to ask you first/i);
  });

  it('never describes the confirmation as one the scientist is known to have given', () => {
    /*
     * A flat ratchet over the shapes that read as a gate, in the register the
     * rest of this file uses. It is deliberately not negation-aware: the
     * failure being guarded against is a future author restoring the shorter,
     * friendlier phrasing, not one writing a careful double negative.
     */
    const { container } = renderPanel();
    for (const text of [writeRow!.detail, visibleText(container)]) {
      expect(text).not.toMatch(/carries your confirmation/i);
      expect(text).not.toMatch(/your confirmation as its support/i);
      expect(text).not.toMatch(/\bwith your confirmation\b/i);
      // …and no claim that anything on this path verifies or records that the
      // scientist was asked.
      expect(text).not.toMatch(/\bconfirmation is (verified|checked|recorded by ISAAC)\b/i);
    }
  });

  it('keeps the half that IS structural — an unknown key writes nothing', () => {
    /* The refusal of an invented or misspelt key is enforced by the server, so it
       stays stated plainly. Weakening it while fixing the confirmation claim would
       trade one inaccuracy for another.
       "field path" BECAME "key", because the row no longer claims the two branches
       take the same key space — the record-level branch takes blocking-question keys
       and refuses an official field path. The structural property is unchanged: an
       unrecognised key is refused and nothing is written. */
    expect(writeRow!.detail).toMatch(/invented or misspelt key is refused with nothing written/i);
  });

  it('is what the backend says about itself, in the backend’s own words', () => {
    /*
     * The parity that makes this more than an opinion about wording. Both
     * sentences are read from `mcp/tools.py` with whitespace collapsed — they
     * are wrapped across source lines and across adjacent Python string
     * literals, so a raw substring search would fail on a file that says
     * exactly what it should, and the test would then be about line wrapping
     * rather than about meaning.
     *
     * If the server ever DID establish the confirmation itself, these fail and
     * send somebody back to the page. That is the right direction for the
     * failure to point: the page is downstream of the boundary, never the other
     * way round.
     */
    expect(TOOLS_SOURCE).toContain(
      "a layer that sets it on the caller's behalf manufactures a confirmation nobody gave",
    );
    expect(TOOLS_SOURCE).toContain(
      "it is the caller's assertion that the scientist confirmed it, not this server's",
    );
  });
});

// --- accessibility -------------------------------------------------------------

describe('Connect Your Agent — accessibility', () => {
  it('every heading has real text and the outline never skips a level', () => {
    const { container } = renderSettings();
    const headings = Array.from(container.querySelectorAll('h1, h2, h3, h4, h5, h6'));
    expect(headings.length).toBeGreaterThan(0);
    for (const heading of headings) {
      expect((heading.textContent ?? '').trim().length, 'an empty heading').toBeGreaterThan(0);
    }
    const levels = headings.map((h) => Number(h.tagName[1]));
    for (let i = 1; i < levels.length; i += 1) {
      expect(levels[i] - levels[i - 1], `outline: ${levels.join(',')}`).toBeLessThanOrEqual(1);
    }
  });

  it('the one control on the tab is a real, keyboard-operable button with a name', () => {
    renderPanel();
    const explorer = screen.getByRole('button', { name: /Endpoint Explorer/i });
    expect(explorer).toHaveAttribute('type', 'button');
    expect(explorer).not.toBeDisabled();
    // A native button: reachable and activatable by keyboard without a
    // hand-rolled key handler.
    expect(explorer.tagName).toBe('BUTTON');
    expect(explorer).not.toHaveAttribute('tabindex', '-1');
  });

  it('renders no link off this build and no external URL', () => {
    const { container } = renderPanel();
    for (const el of Array.from(container.querySelectorAll('[href], [src]'))) {
      const url = el.getAttribute('href') ?? el.getAttribute('src') ?? '';
      expect(/^(https?:)?\/\//.test(url), `external URL rendered: ${url}`).toBe(false);
    }
  });
});

// --- the branch that exists for the day the decisions land ---------------------

describe('Connect Your Agent — when a deployment does publish an address', () => {
  // Deliberately not a real host: the fixture must not resemble somewhere a
  // reader could be sent, and the Settings infrastructure-substring guard
  // forbids naming one anyway.
  const ADDRESS = 'https://agent.example.invalid/mcp';

  it('shows the address the deployment supplied, and still claims no connection', () => {
    const { container } = renderPanel(ADDRESS);
    expect(screen.getByText(ADDRESS)).toBeInTheDocument();
    expect(norm(visibleText(container))).toContain(
      norm(MCP_CONNECT_COPY.endpointPublishedNote),
    );
    // The ratchet holds in this branch too — an address is not a connection.
    expect(visibleText(container)).not.toMatch(/\bconnected\b/i);
    // …and it is inert text, never a link.
    expect(container.querySelector(`a[href="${ADDRESS}"]`)).toBeNull();
  });

  it('the state derivation is the only thing that decides which branch renders', () => {
    expect(mcpDeploymentState(null)).toBe('requires-configuration');
    expect(mcpDeploymentState(ADDRESS)).toBe('endpoint-published');
  });

  it('does NOT deny the endpoint it is displaying — the banner follows the branch', () => {
    /*
     * The defect this pins: the banner rendered the unconfigured sentences
     * unconditionally, so this branch showed the address and, immediately above
     * it, "There is no endpoint address to connect to". A page that contradicts
     * itself on its one subject is worse than one that says nothing, and no
     * assertion in this file caught it — the address test only looked for the
     * address.
     */
    const { container } = renderPanel(ADDRESS);
    const text = norm(visibleText(container));

    expect(text).toContain(norm(MCP_CONNECT_COPY.statusDetailPublished));
    expect(text).not.toContain(norm(MCP_CONNECT_COPY.statusDetail));
    // The `Requires organization configuration` heading is a claim about a
    // deployment with no address; it must not survive into a branch that has one.
    expect(text).not.toContain(norm(MCP_CONNECT_COPY.statusLabel));
    // Nor may it keep asserting the two decisions are outstanding — an address
    // existing is evidence that at least one of them moved.
    expect(text).not.toContain(norm(MCP_CONNECT_COPY.statusOwner));
    // And the published status still is not a connection claim.
    expect(visibleText(container)).not.toMatch(/\bconnected\b/i);
  });

  it('the unconfigured branch is unaffected — it keeps its own two sentences', () => {
    const text = norm(visibleText(renderPanel().container));
    expect(text).toContain(norm(MCP_CONNECT_COPY.statusDetail));
    expect(text).toContain(norm(MCP_CONNECT_COPY.statusOwner));
    expect(text).not.toContain(norm(MCP_CONNECT_COPY.statusDetailPublished));
  });
});

// --- parity with the backend that defines the boundary -------------------------

/*
 * The three claims on this tab that are NOT about this build's own UI — the tool
 * set, the two permissions, and the deferral date — have their source in files
 * this test reads directly. Without that, the tab is a hand-written description
 * of somebody else's module, free to drift the moment that module changes, and
 * the drift would be invisible: a page confidently describing eight tools when
 * nine exist looks exactly like a correct page.
 *
 * WHAT THIS CANNOT DO, stated so nobody reads more into a green run. It checks
 * that the page NAMES the right things, never that the prose ABOUT them is
 * accurate. "Add a run" could be reworded to something false about what adding a
 * run does and every assertion here would still pass. A human reviewer is the
 * backstop for the wording; this is the backstop for the inventory.
 */

/** The repository root, located by a file only it has. */
function locateRepoRoot(): string {
  const candidates = [join(process.cwd(), '..', '..'), process.cwd()];
  const found = candidates.find((dir) => existsSync(join(dir, 'schema', 'isaac_record_v1.json')));
  if (found === undefined) {
    throw new Error(`cannot locate the repository root from ${process.cwd()}`);
  }
  return found;
}

const REPO_ROOT = locateRepoRoot();
const POLICY_SOURCE = readFileSync(join(REPO_ROOT, 'apps/api/isaac_api/mcp/policy.py'), 'utf8');
/**
 * `mcp/tools.py` as PROSE: adjacent Python string literals joined, then all
 * whitespace collapsed.
 *
 * Same reasoning as `AUDIT_SOURCE` below, for a different mechanism. The two
 * sentences the confirmation-direction block asserts on are wrapped BOTH across
 * source lines (the module docstring) and across adjacent string literals in a
 * tool description, so a raw substring search fails on a file that says exactly
 * what it should — and the test would then be pinning line wrapping rather than
 * meaning. Reflowing the file must not fail this; changing what it says must.
 */
const TOOLS_SOURCE = readFileSync(join(REPO_ROOT, 'apps/api/isaac_api/mcp/tools.py'), 'utf8')
  .replace(/"\s*\n\s*"/g, '')
  .replace(/\s+/g, ' ');
/**
 * The audit as PROSE: blockquote markers dropped, emphasis dropped, whitespace
 * collapsed.
 *
 * Without this the assertions below are hostage to line wrapping. The sentence
 * they check sits inside a `>` blockquote and wraps mid-clause, so the raw file
 * contains `approved,\n> narrowed` and a plain substring search fails on a
 * document that says exactly what it should. Normalising means a reflow of the
 * paragraph does not fail this test, while a change of MEANING still does —
 * which is the only thing worth pinning.
 */
const AUDIT_SOURCE = readFileSync(join(REPO_ROOT, 'docs/mcp-capability-audit.md'), 'utf8')
  .replace(/^\s*>\s?/gm, '')
  .replace(/\*+/g, '')
  .replace(/\s+/g, ' ');
/**
 * The local-transport note, normalised the same way as `AUDIT_SOURCE`.
 *
 * Read purely so the two MCP documents can be checked TOGETHER. On 2026-08-24 the
 * self-falsifying "no product screen mentions MCP" sentence was struck here and the
 * identical claim in the audit was missed, so the pair diverged for a day inside a
 * document read as an audit. Pinning them in one test is what stops the next sweep
 * fixing one copy again.
 */
const TRANSPORT_SOURCE = readFileSync(join(REPO_ROOT, 'docs/mcp-local-transport.md'), 'utf8')
  .replace(/^\s*>\s?/gm, '')
  .replace(/\*+/g, '')
  .replace(/\s+/g, ' ');

/** Every tool name the backend permits, read off `PERMITTED_TOOL_NAMES`. */
function permittedToolNames(): string[] {
  const block = POLICY_SOURCE.match(/PERMITTED_TOOL_NAMES = frozenset\(\s*\{([^}]*)\}/);
  if (block === null) throw new Error('cannot find PERMITTED_TOOL_NAMES in policy.py');
  return Array.from(block[1].matchAll(/"([^"]+)"/g), (m) => m[1]).sort();
}

/** Every scope string the backend can express, read off the `Scope` enum. */
function scopeValues(): string[] {
  const block = POLICY_SOURCE.match(/class Scope\(Enum\):([\s\S]*?)\ndef parse_scope/);
  if (block === null) throw new Error('cannot find the Scope enum in policy.py');
  return Array.from(block[1].matchAll(/^ {4}[A-Z_]+ = "([^"]+)"$/gm), (m) => m[1]).sort();
}

describe('Connect Your Agent — parity with the backend it describes', () => {
  it('the parsers actually found something — a vacuous read would pass every check below', () => {
    // Set-equality between two empty sets is true, so an over-narrow regex would
    // turn every assertion in this block green while checking nothing. These two
    // lines are what stop that.
    expect(permittedToolNames().length).toBeGreaterThan(0);
    expect(scopeValues().length).toBeGreaterThan(0);
  });

  it('the capability list covers every backend tool — exactly, in both directions', () => {
    const described = MCP_CAPABILITIES_ALLOWED.flatMap((c) => c.tools ?? []).sort();
    // No duplicates: two rows claiming the same tool would let a real tool go
    // undescribed while the totals still matched.
    expect(described, 'a tool is claimed by two capability rows').toEqual([
      ...new Set(described),
    ]);
    // A tool added to policy.py fails here until this tab says what it lets an
    // agent do; a tool removed there fails until the claim is withdrawn.
    expect(described).toEqual(permittedToolNames());
  });

  it('the two permissions are exactly the scopes the backend can express', () => {
    expect(MCP_PERMISSIONS.map((p) => p.name).sort()).toEqual(scopeValues());
  });

  /*
   * THE COPY FOR A PERMISSION MUST MATCH WHAT THAT PERMISSION ACTUALLY PERMITS.
   *
   * THE DEFECT THIS CLOSES, measured on 2026-08-25. The tab said *"Two
   * permissions, and they do not nest: an agent granted only the draft-write
   * permission is refused every read tool, and one granted only read is refused
   * every write"*, and the draft-write row's `allows` described write capability
   * as something that grant confers. Both halves misled in the same direction.
   *
   * What a principal holding ONLY `isaac:draft.write` can actually do, driven
   * through `McpServer.handle`:
   *
   *     tools/list                 -> []           (not one of the ten)
   *     tools/call, every tool     -> JSON-RPC -32002
   *       "'isaac_answer_questions' requires the scope(s)
   *        ['isaac:draft.write', 'isaac:read'], and this connection was not
   *        granted ['isaac:read']."
   *
   * Because `Tool.required_scopes` returns `frozenset({Scope.READ, self.scope})`
   * — every tool costs READ, since a write tool also returns the state it
   * produced. Non-nesting is real and is the SAFE property; the tab turned it
   * into a false capability claim. `tools.py`'s own docstring already said the
   * true thing the screen omitted: *"a principal holding DRAFT_WRITE alone can
   * now call nothing at all rather than being able to write blind."*
   *
   * A scientist who granted draft-write alone would have found the agent totally
   * inert, having been told it would write.
   *
   * So the rule this block enforces: the number of tools a single-scope
   * principal can call is DERIVED from `tools.py`, and the copy for that scope
   * must agree with it. Deriving rather than hard-coding is what makes this
   * catch the next divergence instead of pinning today's sentence.
   */
  /** Every tool name in `tools.py` with the scope it declares. */
  function declaredTools(): { name: string; scope: string }[] {
    const source = readFileSync(join(REPO_ROOT, 'apps/api/isaac_api/mcp/tools.py'), 'utf8');
    const out: { name: string; scope: string }[] = [];
    const pattern = /name="(isaac_[a-z_]+)"[\s\S]*?scope=Scope\.([A-Z_]+)/g;
    for (const match of source.matchAll(pattern)) {
      out.push({ name: match[1], scope: match[2] });
    }
    return out;
  }

  /**
   * Does every tool require READ on top of its own scope? Read off the
   * `required_scopes` property rather than assumed — if a future change makes a
   * write tool cost DRAFT_WRITE alone, this flips and the assertions below
   * change with it instead of going quietly stale.
   */
  function everyToolAlsoCostsRead(): boolean {
    const source = readFileSync(join(REPO_ROOT, 'apps/api/isaac_api/mcp/tools.py'), 'utf8')
      .replace(/\s+/g, ' ');
    return source.includes('return frozenset({Scope.READ, self.scope})');
  }

  /** The tools a principal holding EXACTLY `scope` can call. */
  function callableWithOnly(scope: 'READ' | 'DRAFT_WRITE'): string[] {
    const alsoRead = everyToolAlsoCostsRead();
    return declaredTools()
      .filter(({ scope: own }) => {
        const cost = new Set(alsoRead ? ['READ', own] : [own]);
        return cost.size === 1 && cost.has(scope);
      })
      .map((t) => t.name)
      .sort();
  }

  it('the parser found the tools and the scope rule — a vacuous read would pass the rest', () => {
    const declared = declaredTools();
    expect(declared.length).toEqual(permittedToolNames().length);
    expect(declared.map((t) => t.name).sort()).toEqual(permittedToolNames());
    expect(declared.some((t) => t.scope === 'DRAFT_WRITE')).toBe(true);
    expect(everyToolAlsoCostsRead()).toBe(true);
  });

  it('draft-write alone permits NOTHING, and the copy for it says so', () => {
    // Derived, not asserted: every tool costs READ, so a draft-write-only
    // principal reaches zero of them.
    expect(callableWithOnly('DRAFT_WRITE')).toEqual([]);

    const draftWrite = MCP_PERMISSIONS.find((p) => p.id === 'draft-write');
    expect(draftWrite, 'the draft-write permission row is gone').toBeDefined();
    const copy = `${draftWrite!.allows} ${draftWrite!.refuses}`;

    // It must say the grant is additive / requires read, rather than presenting
    // write capability as something this grant confers on its own.
    expect(copy).toMatch(/added to read|on top of read|requires? read|as well as read/i);
    expect(copy).toMatch(/permits nothing|refused all|nothing at all|inert/i);

    // And it must NOT reproduce the retired inference, in either place.
    const everything = [
      MCP_CONNECT_COPY.permissionsDetail,
      copy,
      ...MCP_SETUP_STEPS.map((s) => s.detail),
    ].join(' ');
    expect(
      everything,
      'the tab again presents draft-write as usable without read',
    ).not.toMatch(/granted only the draft-write permission is refused every read tool/i);
    expect(everything).not.toMatch(/they do not nest/i);
  });

  /*
   * NEITHER MCP DOCUMENT MAY ASSERT THAT NO PRODUCT SCREEN MENTIONS MCP.
   *
   * The claim carried its own falsifier — it cited `apps/web/src` as the check — and
   * it was FALSE ON THE DAY IT WAS COMMITTED to the audit: `mcpConnectContent.ts`
   * landed in `a1b8ee0` (2026-08-13) and the audit bullet in `b4b5e9f` (2026-08-16).
   * Measured 2026-08-25 on the committed tree::
   *
   *     git grep -ic mcp 6baadc8 -- apps/web/src
   *       -> 151 matching lines across 9 files, ConnectYourAgent.tsx among them
   *
   * `docs/mcp-local-transport.md` struck its copy on 2026-08-24 and the sweep MISSED
   * the audit's — the same enumeration failure CLAUDE.md §15 records for the
   * `isaac_run_projection` correction. So both documents are checked here, together,
   * and the live evidence is derived from the tree rather than quoted.
   */
  it('neither MCP document claims apps/web/src is free of MCP references', () => {
    // The live fact, measured rather than asserted: this tree's frontend does mention
    // MCP, so any document saying otherwise is wrong right now.
    const mentions = MCP_CAPABILITIES_ALLOWED.length > 0 && MCP_PERMISSIONS.length > 0;
    expect(mentions, 'the Connect Your Agent content module is gone').toBe(true);

    for (const [name, source] of [
      ['docs/mcp-capability-audit.md', AUDIT_SOURCE],
      ['docs/mcp-local-transport.md', TRANSPORT_SOURCE],
    ] as const) {
      for (const claim of [
        'No product screen mentions MCP',
        'apps/web/src contains no reference',
        'no product surface that mentions MCP at all',
      ]) {
        let index = source.indexOf(claim);
        while (index !== -1) {
          const window = source.slice(Math.max(0, index - 14), index);
          expect(
            window,
            `${name} asserts "${claim}" as its own statement rather than striking it. ` +
              'That claim is false: apps/web/src mentions MCP on 151 lines across 9 ' +
              'files (git grep -ic mcp 6baadc8 -- apps/web/src).',
          ).toContain('~~');
          index = source.indexOf(claim, index + 1);
        }
      }
    }
  });

  it('the retired MCP-surface claim is still FINDABLE in both documents, as a correction', () => {
    // NEGATIVE CONTROL. The guard above passes trivially on a document that DELETED
    // the sentence, which is how a corrected claim becomes indistinguishable from one
    // that never drifted — the failure mode CLAUDE.md's convention exists to prevent.
    expect(AUDIT_SOURCE).toContain('No product screen mentions MCP');
    expect(TRANSPORT_SOURCE).toContain('no product surface that mentions MCP at all');
    // And each must still say what replaced it, so a reader is not left with a strike
    // and no verdict.
    expect(AUDIT_SOURCE).toMatch(/CORRECTED 2026-08-25/);
    expect(TRANSPORT_SOURCE).toMatch(/SUPERSEDED 2026-08-24/);
  });

  it('read alone permits exactly the read tools, and the copy for it says so', () => {
    // The OTHER half of the old sentence was true, and losing it would be its own
    // defect: a read-only agent really is refused every write.
    const readable = callableWithOnly('READ');
    expect(readable.length).toBeGreaterThan(0);
    expect(readable).toEqual(
      declaredTools()
        .filter((t) => t.scope === 'READ')
        .map((t) => t.name)
        .sort(),
    );
    // Every write tool is genuinely out of reach for it.
    for (const tool of declaredTools().filter((t) => t.scope === 'DRAFT_WRITE')) {
      expect(readable).not.toContain(tool.name);
    }
    const read = MCP_PERMISSIONS.find((p) => p.id === 'read');
    expect(read, 'the read permission row is gone').toBeDefined();
    expect(`${read!.allows} ${read!.refuses}`).toMatch(
      /writes nothing|cannot change a draft|only look/i,
    );
  });

  it('"no agent can submit" is backed by the backend refusing the token outright', () => {
    // The page states a structural refusal. This is that structure: `submit` and
    // `export` are forbidden substrings in any tool name, checked at import in
    // the application and in CI — so the claim is not this file's word for it.
    const forbidden = POLICY_SOURCE.match(/FORBIDDEN_TOOL_TOKENS = frozenset\(\s*\{([^}]*)\}/);
    expect(forbidden, 'cannot find FORBIDDEN_TOOL_TOKENS in policy.py').not.toBeNull();
    const tokens = Array.from(forbidden![1].matchAll(/"([^"]+)"/g), (m) => m[1]);
    expect(tokens).toContain('submit');
    expect(tokens).toContain('export');
    // And nothing permitted carries one of them.
    for (const name of permittedToolNames()) {
      for (const token of tokens) {
        expect(name, `permitted tool ${name} carries ${token}`).not.toContain(token);
      }
    }
  });

  it('the deferral the page reports is still what the committed audit records', () => {
    /*
     * The page says the two decisions were deferred on 2026-08-12 and that
     * neither has been narrowed. That is the ONE claim on this tab which can go
     * stale without a line of code changing — the day Dean answers, the page
     * keeps saying it. So it is pinned to the audit, and when the audit is
     * updated THIS test fails and sends somebody back to the tab. The failure is
     * the point; it is not a test to relax when it goes red.
     */
    expect(AUDIT_SOURCE).toContain('DEFERRED 2026-08-12 (= D1)');
    expect(AUDIT_SOURCE).toContain('DEFERRED 2026-08-12 (= D2)');
    expect(AUDIT_SOURCE).toContain('None of them is approved, narrowed, or conditionally approved');
    // The status the page shows is the phrase the audit prescribes for it.
    expect(AUDIT_SOURCE).toContain('Requires organization configuration');
    expect(MCP_CONNECT_COPY.statusLabel).toBe('Requires organization configuration');
  });
});

describe('the write permission describes the reach it actually has', () => {
  /*
   * THIS TEST WAS INVERTED, NOT DELETED, and the inversion is the record.
   *
   * It used to REQUIRE the copy to say `cannot give a run its spectrum`, and it was
   * right to: `isaac_update_draft` reached a run's five context/timing fields and the
   * record-level correction route, and the run-level blocks — series, qc, descriptors,
   * assets — had no MCP operation at all. The gap was recorded in
   * `docs/mcp-capability-audit.md` §5A rather than closed, so the copy had to say so.
   *
   * §5A.1 closed it: `isaac_list_questions` and `isaac_answer_questions` reach exactly
   * those blocks, at the level that owns them. A test still requiring the "cannot"
   * sentence would have been requiring the product to keep a FALSE claim on a screen
   * whose whole job is to describe a permission truthfully — with the test reading as
   * evidence of honesty. So it now pins the two properties that survive the change and
   * are what a scientist is actually deciding on.
   */
  it('routes the spectrum, verdict and descriptors to the answer capability, not the field one', () => {
    const write = MCP_CAPABILITIES_ALLOWED.find((c) => c.id === 'write-draft');
    expect(write, 'the write capability row is gone; re-read this test').toBeDefined();
    /* "FIELD PATHS ONLY" WAS ALSO FALSE, and an independent review measured it one
       revision after this test was inverted the first time. `isaac_update_draft`'s
       RECORD-level branch posts to `/edit`, which takes blocking-question keys — so it
       writes exactly the spectrum and QC verdict that sentence said it could not, and
       REFUSES the official field path that sentence said was all it took. Only its
       RUN-level branch is field paths.
       So the row no longer makes a claim about key spaces at all. It describes what a
       scientist is granting, and both negative controls stay: neither the original
       "cannot" sentence nor its replacement may return. */
    expect(write!.detail).toMatch(/five context and timing fields/i);
    expect(write!.detail).toMatch(/refused with nothing written/i);
    expect(write!.detail).not.toMatch(/cannot give a run its spectrum/i);
    expect(write!.detail).not.toMatch(/field paths only/i);

    const answer = MCP_CAPABILITIES_ALLOWED.find((c) => c.id === 'answer-questions');
    expect(answer, 'the answer capability row is gone; re-read this test').toBeDefined();
    expect(answer!.detail).toMatch(/QC verdict/i);
    expect(answer!.detail).toMatch(/descriptor/i);
    // THE LEVEL IS NOT GUESSED, and this is the scientist's protection rather than a
    // detail: ISAAC does not decide which run measured something.
    expect(answer!.detail).toMatch(/will not guess which run measured something/i);
    expect(answer!.detail).toMatch(/refused with nothing written/i);
    // AND THE CONFIRMATION CAVEAT IS RESTATED HERE, not left one row away. This row
    // authorises writing scientific judgement on the strength of a boolean the caller
    // sends and nothing verifies.
    expect(answer!.detail).toMatch(/assertion that you gave it/i);
    /* WHAT A CORRECTION DOES TO THE AUDIT TRAIL, IN BOTH DIRECTIONS. This row said
       "keeping the earlier confirmation beside the new one" flatly, and a review
       measured it FALSE for a spectrum and a descriptor: `complete.py` ASSIGNS their
       evidence list rather than appending, so the earlier confirmation is gone. A
       scientist granting this permission on the strength of an audit-trail promise is
       owed the exception. Backend-measured in
       `test_mcp_server.py::test_what_a_CORRECTION_does_to_THE_EARLIER_CONFIRMATION_is_per_field`. */
    expect(answer!.detail).toMatch(/keeps the earlier confirmation beside/i);
    expect(answer!.detail).toMatch(/REPLACES it for a spectrum or a descriptor/);

    const scope = MCP_PERMISSIONS.find((p) => p.id === 'draft-write');
    expect(scope, 'the draft.write scope row is gone; re-read this test').toBeDefined();
    expect(scope!.allows).not.toMatch(/does not reach a run.s spectrum/i);
    expect(scope!.allows).toMatch(/does not export, submit or finalise/i);
  });

  it('does not claim a new run starts empty, because the first one does not', () => {
    /*
     * A SEPARATE HONESTY DEFECT, found while closing §5A and not caused by it. This
     * row read "It starts empty — no value is copied into it and none is invented",
     * which was true when it was written and stopped being true when
     * `routes._seed_for_new_run` began carrying the record's run-level values onto the
     * FIRST run — a change made because a first run that started empty silently
     * deleted evidenced values from the record it exports.
     *
     * Both halves are required. "It inherits everything" is as false as "it starts
     * empty": a LATER run does start empty, because copying one run's spectrum onto
     * another asserts they measured the same thing.
     */
    const add = MCP_CAPABILITIES_ALLOWED.find((c) => c.id === 'add-run');
    expect(add, 'the add-run capability row is gone; re-read this test').toBeDefined();
    expect(add!.detail).not.toMatch(/starts empty — no value is copied/i);
    expect(add!.detail).toMatch(/first run carries across/i);
    expect(add!.detail).toMatch(/every run after the first starts empty/i);
    expect(add!.detail).toMatch(/no value is ever invented/i);
    /* AND IT SAYS "MOST", NOT "WHAT THE RECORD HOLDS". A review found the umbrella
       phrase overstated it in both directions: `_seed_for_new_run` deliberately does
       NOT carry the six `system.configuration.*` fields (whether two runs may differ
       in detector model is an open scientific question, and copying them would answer
       it), and the earlier parenthetical named only three of the six things that DO
       carry. Both are now stated, including the cost of the omission. */
    expect(add!.detail).toMatch(/carries across most of what/i);
    expect(add!.detail).toMatch(/do NOT move/);
    expect(add!.detail).toMatch(/dropped from a record exported per run/i);
  });

  it('M7 — the withheld set is named by its members, not by a category two of them are not in', () => {
    /*
     * "THE INSTRUMENT AND DETECTOR SETTINGS" UNDER-STATED WHAT IS DROPPED. The
     * unclassified namespace has SIX members (`extract/structured.FIELD_MAP`), and
     * `proposal_id` and `session_id` are ADMINISTRATIVE identifiers — not settings of
     * an instrument or a detector, and not something a reader would picture under that
     * phrase. They are exactly what somebody reconciling a run against a beamtime
     * schedule looks for, and they are dropped from a record exported per run.
     *
     * `workspace.field_level`'s own docstring records the same undercount being found
     * and corrected there — "SIX fields, not the five this list used to name" — by
     * enumerating the map rather than reading the prose. This copy was the next copy
     * of the same mistake, in the surface a reader uses to decide what to grant.
     */
    const add = MCP_CAPABILITIES_ALLOWED.find((c) => c.id === 'add-run');
    expect(add, 'the add-run capability row is gone; re-read this test').toBeDefined();
    expect(add!.detail).not.toMatch(/The instrument and detector settings do NOT move/);
    for (const named of [/detector model/i, /monochromator/i, /spectrometer/i, /scan count/i]) {
      expect(add!.detail).toMatch(named);
    }
    // The two that are NOT instrument settings, named as such.
    expect(add!.detail).toMatch(/proposal and session identifiers/i);
    expect(add!.detail).toMatch(/administrative rather than instrument settings/i);
    // The count is stated, so a future edit that drops one is visible.
    expect(add!.detail).toMatch(/Six fields do NOT move/);
    expect(add!.detail).toMatch(/all six are dropped/i);
  });

  it('I2 — the check-run row names all three gates, so none is reached by elimination', () => {
    /*
     * "THE NO-GUESSING DRAFT CHECK AND THE OFFICIAL ISAAC SCHEMA" reads as an
     * exhaustive pair, so an agent meeting an unfamiliar finding concludes it is the
     * schema's. `export.py` runs `check_exactness` on the assembled record BETWEEN
     * those two (`:339`) and folds a refusal into `draft_report` (`:339-343`), returning
     * `official_report=None` — so a finding this tool surfaces may belong to a gate
     * neither named validator owns, and the reply carries no discriminator.
     *
     * `CLAUDE.md` §12: the exactness gate is ISAAC's, not upstream's, and §1 makes the
     * schema not ours to speak for. Reaching that attribution by omission is the same
     * claim made quietly, which is why the fix is naming the third rather than
     * softening the other two.
     */
    const check = MCP_CAPABILITIES_ALLOWED.find((c) => c.id === 'check-run');
    expect(check, 'the check-run capability row is gone; re-read this test').toBeDefined();
    expect(check!.detail).not.toMatch(
      /no-guessing draft check and the official ISAAC schema say/,
    );
    expect(check!.detail).toMatch(/no-guessing draft check/i);
    expect(check!.detail).toMatch(/anchored-pattern exactness gate/i);
    expect(check!.detail).toMatch(/official ISAAC schema/);
    // And it says the reply does not label which of the three spoke.
    expect(check!.detail).toMatch(/does not label which of the three/i);
    // The read-only claim is untouched.
    expect(check!.detail).toMatch(/writes nothing and changes nothing/i);
  });
});
