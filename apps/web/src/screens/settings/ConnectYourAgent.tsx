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
import { useHealthState } from '../../lib/useHealth';
import { Widget } from '../../components/Widget';
import {
  ChevronRight,
  Compass,
  LayoutList,
  Lock,
  Network,
  Shield,
  SlidersHorizontal,
} from '../../components/icons';
import {
  MCP_AUDIT_DOC,
  MCP_CAPABILITIES_ALLOWED,
  MCP_CAPABILITIES_REFUSED,
  MCP_CONNECT_COPY,
  MCP_ENDPOINT,
  MCP_PERMISSIONS,
  MCP_SETUP_STEPS,
  MCP_WIDGET_COPY,
  mcpDeploymentState,
  mcpReasonLine,
} from '../../lib/mcpConnectContent';
import { AssistantCompanionSection } from './AssistantCompanion';

/** The widget heading's id — also the region's accessible name. */
export const AGENT_WIDGET_HEADING_ID = 'settings-agent-heading';

export function ConnectYourAgentPanel({
  /**
   * The published endpoint address, or `null`. Defaults to the module
   * constant, which is `null` — the page passes nothing, and the parameter
   * exists so the "an endpoint exists" branch is reachable from a test rather
   * than being unexercised code waiting for the day the decision lands.
   */
  endpoint = MCP_ENDPOINT,
  /** Opens the Endpoint Explorer — the surface that lets a reader check the
   *  "no agent interface is published here" claim against the real contract. */
  onOpenExplorer,
  /** Render the companion-artifact view. The page does; a test of the panel
   *  alone may leave it out, because it issues a read of its own. */
  withCompanion = true,
}: {
  endpoint?: string | null;
  onOpenExplorer: () => void;
  withCompanion?: boolean;
}) {
  const state = mcpDeploymentState(endpoint);
  const unconfigured = state === 'requires-configuration';
  const { settled, health } = useHealthState();
  /* The banner reports the state it is IN. Rendering the unconfigured sentences
     unconditionally put "There is no endpoint address to connect to" directly
     above a published address — the page contradicting itself on its one
     subject. Both branches are derived from the same `state`, so they cannot
     disagree. The posture only ever chooses WHICH unconfigured reason is given;
     it cannot turn the unconfigured state into anything else. */
  const statusLabel = unconfigured
    ? MCP_CONNECT_COPY.statusLabel
    : MCP_CONNECT_COPY.statusLabelPublished;
  const statusDetail = unconfigured
    ? mcpReasonLine(settled ? health?.mcp?.posture ?? null : null)
    : MCP_CONNECT_COPY.statusDetailPublished;

  /* The four reference views — `Widget`'s toggle-button switcher, collapsed until
     a reader opens one, so a page that refuses a second tablist never gains one. */
  const views = [
    {
      id: 'can-do',
      label: MCP_WIDGET_COPY.viewCanDo,
      icon: <LayoutList size={14} strokeWidth={2} />,
      content: (
        <>
          <p className="settings-view-lead">{MCP_CONNECT_COPY.neverSubmitDetail}</p>
          <p className="settings-view-note">{MCP_CONNECT_COPY.neverSubmitEnforcement}</p>
          {/* The provenance qualifier sits HERE, immediately above the
              material it qualifies, because a reader who skims to the
              capability list is exactly the reader who needs to know it
              describes a defined interface rather than a running one. */}
          <p className="settings-view-note">{MCP_CONNECT_COPY.provenanceNote}</p>
          <dl className="settings-defs">
            {MCP_CAPABILITIES_ALLOWED.map((capability) => (
              <div className="settings-def" key={capability.id}>
                <dt>{capability.action}</dt>
                <dd>{capability.detail}</dd>
              </div>
            ))}
          </dl>
          <h3 className="settings-view-heading">{MCP_WIDGET_COPY.refusedHeading}</h3>
          <dl className="settings-defs">
            {MCP_CAPABILITIES_REFUSED.map((capability) => (
              <div className="settings-def" key={capability.id}>
                <dt>{capability.action}</dt>
                <dd>{capability.detail}</dd>
              </div>
            ))}
          </dl>
          <p className="settings-view-note">
            The boundary above is settled in <code className="mono">{MCP_AUDIT_DOC}</code>,
            committed to this repository.
          </p>
        </>
      ),
    },
    {
      id: 'permissions',
      label: MCP_WIDGET_COPY.viewPermissions,
      icon: <Lock size={14} strokeWidth={2} />,
      content: (
        <>
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
        </>
      ),
    },
    {
      id: 'setup',
      label: MCP_WIDGET_COPY.viewSetup,
      icon: <SlidersHorizontal size={14} strokeWidth={2} />,
      content: (
        <>
          {/* THE PRECONDITION, above the steps rather than inside one of
              them. A procedure a reader cannot start has to say so before
              the reader starts it. */}
          <p className="api-connect-prerequisite">{MCP_CONNECT_COPY.setupPrerequisite}</p>
          <ol className="settings-steps">
            {MCP_SETUP_STEPS.map((step) => (
              <li key={step.id}>
                <strong>{step.title}.</strong> {step.detail}
                {step.command && (
                  <>
                    {' '}
                    {/* Inert text. The address is an angle-bracket placeholder,
                        so the line cannot be pasted as though it were an
                        address this deployment published. */}
                    <code className="mono">{step.command}</code>
                  </>
                )}
              </li>
            ))}
          </ol>
          <p className="settings-view-note">{MCP_CONNECT_COPY.setupBilling}</p>
        </>
      ),
    },
    ...(withCompanion
      ? [
          {
            id: 'claude',
            label: MCP_WIDGET_COPY.viewClaude,
            icon: <Compass size={14} strokeWidth={2} />,
            /* THE COMPANION ARTIFACT, in a view of its own and still its own
               component with its own contract and tests. It is a DIFFERENT
               DIRECTION — an optional page a scientist opens in Claude, which
               this website neither hosts nor depends on — and it is here
               because its stated prerequisite is the same connector the Setup
               view describes, so a reader meets both claims or neither. */
            content: <AssistantCompanionSection bare onOpenExplorer={onOpenExplorer} />,
          },
        ]
      : []),
  ];

  return (
    <Widget
      id={AGENT_WIDGET_HEADING_ID}
      title={MCP_WIDGET_COPY.title}
      icon={<Network size={18} strokeWidth={2} />}
      sub={MCP_WIDGET_COPY.sub}
      /* WHO OWNS THE DECISIONS, rendered only while they are the reason nothing
         works. Once an address exists, "both were deferred and neither has been
         narrowed" is no longer this page's to assert. Provenance, not state:
         the state is the headline. */
      info={
        <>
          <p>{MCP_CONNECT_COPY.cardSub}</p>
          {unconfigured && <p>{MCP_CONNECT_COPY.statusOwner}</p>}
        </>
      }
      headline={
        /* THE STATE, said once, as a sentence. `role="status"` makes it a polite
           live region: the reason arrives from a read, so when it replaces the
           first one it is announced rather than silently swapped. No dot, no
           pill, no colour — the text is the entire signal. */
        <div className="settings-agent-state" role="status">
          <h3 className="widget-state settings-state-heading">{statusLabel}</h3>
          <p className="settings-state-line">{statusDetail}</p>
        </div>
      }
      details={{
        summary: MCP_WIDGET_COPY.detailsSummary,
        content: (
          <div className="settings-qa">
            <section className="settings-qa-item">
              <h3 className="settings-qa-heading">{MCP_CONNECT_COPY.endpointHeading}</h3>
              {unconfigured ? (
                <>
                  <p>{MCP_CONNECT_COPY.endpointNone}</p>
                  <p>{MCP_CONNECT_COPY.endpointVerify}</p>
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
                  <p>{MCP_CONNECT_COPY.endpointPublishedNote}</p>
                </>
              )}
              {/* THE OTHER MECHANISM. Outside the branch on purpose: "no endpoint
                  here" and "the HTTP API is a different thing with a different
                  answer" are both worth a reader in either state. */}
              <p>{MCP_CONNECT_COPY.restApiPointer}</p>
            </section>
            <section className="settings-qa-item">
              <h3 className="settings-qa-heading">{MCP_CONNECT_COPY.activityHeading}</h3>
              <p>{MCP_CONNECT_COPY.activityNone}</p>
            </section>
            <section className="settings-qa-item">
              <h3 className="settings-qa-heading">{MCP_CONNECT_COPY.revocationHeading}</h3>
              <p>{MCP_CONNECT_COPY.revocationNone}</p>
              <p>{MCP_CONNECT_COPY.revocationFuture}</p>
            </section>
            <section className="settings-qa-item">
              <h3 className="settings-qa-heading">{MCP_CONNECT_COPY.oneWayHeading}</h3>
              <p>{MCP_CONNECT_COPY.oneWayDetail}</p>
            </section>
          </div>
        ),
      }}
      viewSwitcher="buttons"
      collapsible
      defaultView={null}
      views={views}
    >
      {/* THE HEADLINE BOUNDARY, visible. It is the single most useful thing a
          scientist can be told about letting an agent near their drafts, and a
          reader who takes nothing else from this widget should take this. Its
          explanation is the first thing in the Can Do view. */}
      <div className="settings-boundary">
        <Shield size={15} strokeWidth={2} aria-hidden="true" className="settings-boundary-icon" />
        <h3 className="settings-boundary-heading">{MCP_CONNECT_COPY.neverSubmitHeading}</h3>
      </div>

    </Widget>
  );
}
