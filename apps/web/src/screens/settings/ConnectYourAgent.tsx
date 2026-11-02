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
 * ── ONE STATE LINE AND ONE DISCLOSURE SINCE 2026-11-02 ───────────────────────
 *
 * The owner retired standing disclaimers. The widget now shows its state as one
 * plain line and holds every reference section — what an agent can and cannot do,
 * its permissions, the setup steps and the Claude companion — in sequence inside
 * one disclosure, instead of four view buttons and an "Endpoint, Activity and
 * Access" drawer. The absences above still hold and are still pinned.
 *
 * ── ONE WIDGET SINCE 2026-10-12 ────────────────────────────────────────────
 *
 * This was a whole tab — a banner, a two-column grid of four sections, a
 * headline boundary and four drawers — measured at 3,502 words explaining one
 * absent capability. It is now the Connect Your Agent widget on the
 * Integrations tab, and every claim in it is KEPT; what moved is where each one
 * sits:
 *
 *   · VISIBLE: the state (headline + one reason line, in a live region), and the
 *     one boundary a reader who takes nothing else must take — no agent can
 *     submit a record.
 *   · IN PLACE, ONE CLICK AWAY: the four reference bodies (what an agent will be
 *     able to do, its permissions, setting it up, the companion artifact) as
 *     views of the widget, switched by a toggle group. Nothing is open until a
 *     reader asks; every panel stays mounted (`hidden`), so the claim-parity
 *     guards still read it.
 *   · IN DETAILS: the endpoint, activity, revocation and direction answers.
 *   · IN INFO: who owns the two decisions that would change the state.
 *
 * THE REASON LINE READS THE DEPLOYMENT'S OWN POSTURE (`/api/health` →
 * `mcp.posture`), the same source the voice-capture view reads, so the two
 * cannot disagree about why nothing can connect. The HEADLINE does not need to:
 * with no published address (`MCP_ENDPOINT` is `null`) no remote agent can be
 * pointed here in any posture this build can report, so "not available" is true
 * before the read settles and after it. There is still no "connected" state,
 * and no member of any type here to hold one.
 *
 * HEADINGS: the widget title is the `h2`; the state, the boundary and each
 * section inside a view or Details are `h3`; the companion's own sub-sections
 * are `h4`. The outline never skips a level, which `settings-page.test.tsx`
 * asserts across every Settings surface.
 */
import { Widget } from '../../components/Widget';
import { Network } from '../../components/icons';
import {
  MCP_CAPABILITIES_ALLOWED,
  MCP_CAPABILITIES_REFUSED,
  MCP_CONNECT_COPY,
  MCP_ENDPOINT,
  MCP_PERMISSIONS,
  MCP_SETUP_STEPS,
  MCP_WIDGET_COPY,
  mcpDeploymentState,
} from '../../lib/mcpConnectContent';
import { AssistantCompanionSection } from './AssistantCompanion';

export const AGENT_WIDGET_HEADING_ID = 'settings-agent-heading';

export function ConnectYourAgentPanel({
  endpoint = MCP_ENDPOINT,
  withCompanion = true,
}: {
  endpoint?: string | null;
  withCompanion?: boolean;
}) {
  const unconfigured = mcpDeploymentState(endpoint) === 'requires-configuration';

  return (
    <Widget
      id={AGENT_WIDGET_HEADING_ID}
      title={MCP_WIDGET_COPY.title}
      icon={<Network size={18} strokeWidth={2} />}
      headline={
        /* The state, as one sentence in a polite live region. No dot, no pill, no
           colour — the text is the entire signal. Both branches are derived from
           the same `endpoint`, so they cannot disagree. */
        <div className="settings-agent-state" role="status">
          {unconfigured ? (
            <p className="settings-state-line">{MCP_CONNECT_COPY.stateLine}</p>
          ) : (
            <>
              <p className="settings-state-line">{MCP_CONNECT_COPY.stateLinePublished}</p>
              {/* An address the deployment supplied, shown as inert text — not a
                  link and not a claim that anything is reachable there. */}
              <p className="mono settings-agent-endpoint">{endpoint}</p>
            </>
          )}
        </div>
      }
      details={{
        summary: MCP_WIDGET_COPY.detailsSummary,
        content: (
          <div className="settings-sequence">
            <section className="settings-sequence-item">
              <h3 className="settings-view-heading">{MCP_CONNECT_COPY.neverSubmitHeading}</h3>
              <p className="settings-view-lead">{MCP_CONNECT_COPY.neverSubmitDetail}</p>
            </section>
            <section className="settings-sequence-item">
              <h3 className="settings-view-heading">{MCP_CONNECT_COPY.canDoHeading}</h3>
              <dl className="settings-defs">
                {MCP_CAPABILITIES_ALLOWED.map((capability) => (
                  <div className="settings-def" key={capability.id}>
                    <dt>{capability.action}</dt>
                    <dd>{capability.detail}</dd>
                  </div>
                ))}
              </dl>
            </section>
            <section className="settings-sequence-item">
              <h3 className="settings-view-heading">{MCP_WIDGET_COPY.refusedHeading}</h3>
              <dl className="settings-defs">
                {MCP_CAPABILITIES_REFUSED.map((capability) => (
                  <div className="settings-def" key={capability.id}>
                    <dt>{capability.action}</dt>
                    <dd>{capability.detail}</dd>
                  </div>
                ))}
              </dl>
            </section>
            <section className="settings-sequence-item">
              <h3 className="settings-view-heading">{MCP_CONNECT_COPY.permissionsHeading}</h3>
              <p className="settings-view-lead">{MCP_CONNECT_COPY.permissionsDetail}</p>
              <dl className="settings-defs">
                {MCP_PERMISSIONS.map((permission) => (
                  <div className="settings-def" key={permission.id}>
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
            <section className="settings-sequence-item">
              <h3 className="settings-view-heading">{MCP_CONNECT_COPY.setupHeading}</h3>
              <ol className="settings-steps">
                {MCP_SETUP_STEPS.map((step) => (
                  <li key={step.id}>
                    <strong>{step.title}.</strong> {step.detail}
                    {step.command && (
                      <>
                        {' '}
                        {/* Inert text with an angle-bracket placeholder, so it cannot
                            be pasted as though it were a published address. */}
                        <code className="mono">{step.command}</code>
                      </>
                    )}
                  </li>
                ))}
              </ol>
            </section>
            {withCompanion && (
              <section className="settings-sequence-item">
                <AssistantCompanionSection bare />
              </section>
            )}
          </div>
        ),
      }}
    />
  );
}
