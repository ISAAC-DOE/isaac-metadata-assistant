/**
 * Settings → Connect Your Agent — the panel body.
 *
 * All copy comes from `lib/mcpConnectContent.ts`, which carries the reasoning
 * for every claim. This file is layout, semantics and the one branch that
 * matters: whether an endpoint exists.
 *
 * WHAT THIS COMPONENT DELIBERATELY DOES NOT RENDER, and each absence is pinned
 * by `__tests__/connect-your-agent.test.tsx`:
 *
 *   · the bare word `connected`, in any casing, in any state. The guard is a
 *     flat substring ratchet rather than a "not preceded by a negation" rule,
 *     which is why even honest negations ("no agent is connected") are written
 *     another way here — a guard a future author can satisfy by adding the word
 *     "not" is not a guard;
 *   · any status conveyed by colour — the state is a sentence inside a
 *     `role="status"` region, so a screen reader and a monochrome display get
 *     the same information as a sighted one;
 *   · an endpoint URL when none is supplied;
 *   · a last-activity value, ever. There is no prop for one, because there is
 *     no source for one — a prop would be a place to put a plausible date;
 *   · a Revoke or Disconnect control;
 *   · any `input`, `textarea`, `select`, or other field. Nothing on this tab
 *     accepts typing, so nothing on it can be shaped like a credential prompt.
 *
 * LAYOUT reuses the API Access tab's existing chrome (`.api-access*`,
 * `.api-keys*`, `.api-connect*`) rather than introducing a sixth arrangement of
 * the same boxes: a full-width status banner, a two-column grid that keeps
 * prose at a readable measure inside the 1200px card, and full-width sections
 * for the material that is a list. No new CSS is added by this slice.
 *
 * HEADINGS start at `h3`. The tab's card supplies the `h2`, so `h3` for a
 * section and `h4` inside one keeps the outline from skipping a level — a
 * property `settings-page.test.tsx` asserts across every Settings surface.
 *
 * LANDMARKS: the `<section>` elements carry no accessible name on purpose, so
 * they are sectioning containers rather than landmarks. The tab already sits
 * inside one named region (the card); six more would make a landmark list
 * useless for navigation. Their headings still structure the outline, which is
 * how a screen-reader user moves within the panel.
 */
import { Lock, ChevronRight } from '../../components/icons';
import {
  MCP_AUDIT_DOC,
  MCP_CAPABILITIES_ALLOWED,
  MCP_CAPABILITIES_REFUSED,
  MCP_CONNECT_COPY,
  MCP_ENDPOINT,
  MCP_PERMISSIONS,
  MCP_SETUP_STEPS,
  mcpDeploymentState,
} from '../../lib/mcpConnectContent';

export function ConnectYourAgentPanel({
  /**
   * The published endpoint address, or `null`. Defaults to the module
   * constant, which is `null` — the page passes nothing, and the parameter
   * exists so the "an endpoint exists" branch is reachable from a test rather
   * than being unexercised code waiting for the day the decision lands.
   */
  endpoint = MCP_ENDPOINT,
  /** Selects the Endpoint Explorer tab — the tab that lets a reader check the
   *  "no agent interface is published here" claim against the real contract. */
  onOpenExplorer,
}: {
  endpoint?: string | null;
  onOpenExplorer: () => void;
}) {
  const state = mcpDeploymentState(endpoint);
  const unconfigured = state === 'requires-configuration';
  /* The banner reports the state it is IN. Rendering the unconfigured sentences
     unconditionally put "There is no endpoint address to connect to" directly
     above a published address — the page contradicting itself on its one
     subject. Both branches are derived from the same `state`, so they cannot
     disagree. */
  const statusLabel = unconfigured
    ? MCP_CONNECT_COPY.statusLabel
    : MCP_CONNECT_COPY.statusLabelPublished;
  const statusDetail = unconfigured
    ? MCP_CONNECT_COPY.statusDetail
    : MCP_CONNECT_COPY.statusDetailPublished;

  return (
    <div className="api-access">
      {/* THE STATE, said once, at the top, as a sentence.
          `role="status"` makes it a polite live region: the state is derived,
          so if it ever changes under the reader it is announced rather than
          silently replaced. It is not decorated with a dot, a pill, or a
          colour — the text is the entire signal. */}
      <section className="api-access-banner" role="status">
        <Lock size={16} strokeWidth={2} aria-hidden="true" className="api-access-banner-icon" />
        <div className="api-access-banner-body">
          <h3 className="api-keys-heading">{statusLabel}</h3>
          <p className="api-keys-lead">{statusDetail}</p>
          {/* WHO OWNS THE DECISIONS is rendered only while they are the reason
              nothing works. Once an address exists, "both were deferred and
              neither has been narrowed" is no longer this page's to assert. */}
          {unconfigured && <p className="api-keys-note">{MCP_CONNECT_COPY.statusOwner}</p>}
        </div>
      </section>

      <div className="api-access-grid">
        <section className="api-access-col">
          <h3 className="api-keys-heading">{MCP_CONNECT_COPY.endpointHeading}</h3>
          {state === 'requires-configuration' ? (
            <>
              <p className="api-keys-note">{MCP_CONNECT_COPY.endpointNone}</p>
              <p className="api-keys-note">{MCP_CONNECT_COPY.endpointVerify}</p>
              <button type="button" className="settings-jump-btn" onClick={onOpenExplorer}>
                Endpoint Explorer
                <ChevronRight size={13} strokeWidth={2.2} aria-hidden="true" />
              </button>
            </>
          ) : (
            <>
              {/* An address the deployment supplied, shown as inert text. Not a
                  link, not a copy affordance, and explicitly not a claim that
                  anything is connected to it. */}
              <p className="mono">{endpoint}</p>
              <p className="api-keys-note">{MCP_CONNECT_COPY.endpointPublishedNote}</p>
            </>
          )}

          <h3 className="api-keys-heading">{MCP_CONNECT_COPY.activityHeading}</h3>
          <p className="api-keys-note">{MCP_CONNECT_COPY.activityNone}</p>
        </section>

        <section className="api-access-col">
          <h3 className="api-keys-heading">{MCP_CONNECT_COPY.revocationHeading}</h3>
          <p className="api-keys-note">{MCP_CONNECT_COPY.revocationNone}</p>
          <p className="api-keys-note">{MCP_CONNECT_COPY.revocationFuture}</p>

          <h3 className="api-keys-heading">{MCP_CONNECT_COPY.oneWayHeading}</h3>
          <p className="api-keys-note">{MCP_CONNECT_COPY.oneWayDetail}</p>
        </section>
      </div>

      {/* THE HEADLINE BOUNDARY, on its own rather than as row one of a list.
          It is the single most useful thing a scientist can be told about
          letting an agent near their drafts, and a reader who takes nothing
          else from this tab should take this. */}
      <section className="api-access-full">
        <h3 className="api-keys-heading">{MCP_CONNECT_COPY.neverSubmitHeading}</h3>
        <p className="api-keys-lead">{MCP_CONNECT_COPY.neverSubmitDetail}</p>
        <p className="api-keys-note">{MCP_CONNECT_COPY.neverSubmitEnforcement}</p>
      </section>

      <section className="api-access-full">
        <h3 className="api-keys-heading">What an Agent Will Be Able to Do</h3>
        {/* The provenance qualifier sits HERE, immediately above the material
            it qualifies, because a reader who skims to the capability list is
            exactly the reader who needs to know it describes a defined
            interface rather than a running one. */}
        <p className="api-keys-note">{MCP_CONNECT_COPY.provenanceNote}</p>
        <dl className="api-keys-rows">
          {MCP_CAPABILITIES_ALLOWED.map((capability) => (
            <div className="api-keys-row" key={capability.id}>
              <dt>{capability.action}</dt>
              <dd>{capability.detail}</dd>
            </div>
          ))}
        </dl>

        <h4 className="api-connect-heading">And What It Will Not</h4>
        <dl className="api-keys-rows">
          {MCP_CAPABILITIES_REFUSED.map((capability) => (
            <div className="api-keys-row" key={capability.id}>
              <dt>{capability.action}</dt>
              <dd>{capability.detail}</dd>
            </div>
          ))}
        </dl>
        <p className="api-keys-note">
          The boundary above is settled in <code className="mono">{MCP_AUDIT_DOC}</code>, committed
          to this repository.
        </p>
      </section>

      <section className="api-access-full">
        <h3 className="api-keys-heading">{MCP_CONNECT_COPY.permissionsHeading}</h3>
        <p className="api-keys-note">{MCP_CONNECT_COPY.permissionsDetail}</p>
        <dl className="api-keys-rows">
          {MCP_PERMISSIONS.map((permission) => (
            <div className="api-keys-row" key={permission.id}>
              <dt>
                <code className="mono">{permission.name}</code>
              </dt>
              <dd>
                {permission.allows} {permission.refuses}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="api-access-full">
        <h3 className="api-keys-heading">{MCP_CONNECT_COPY.setupHeading}</h3>
        {/* THE PRECONDITION, above the steps rather than inside one of them.
            A procedure a reader cannot start has to say so before the reader
            starts it. */}
        <p className="api-connect-prerequisite">{MCP_CONNECT_COPY.setupPrerequisite}</p>
        <ol className="api-keys-requirements">
          {MCP_SETUP_STEPS.map((step) => (
            <li key={step.id}>
              <strong>{step.title}.</strong> {step.detail}
              {step.command && (
                <>
                  {' '}
                  {/* Inert text. The address is an angle-bracket placeholder, so
                      the line cannot be pasted as though it were an address this
                      deployment published. */}
                  <code className="mono">{step.command}</code>
                </>
              )}
            </li>
          ))}
        </ol>
        <p className="api-keys-note">{MCP_CONNECT_COPY.setupBilling}</p>
      </section>

    </div>
  );
}
