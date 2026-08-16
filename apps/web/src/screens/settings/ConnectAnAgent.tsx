/**
 * Settings → API Access → Connect an Agent (P36V PR3 slice C; P36V-1 slice 13).
 *
 * Eight short sections, collapsed behind one disclosure so the API Access tab
 * stays a reference surface rather than becoming a single-page manual. The
 * disclosure's `<summary>` carries the section's real `<h3>` (heading content is
 * permitted there), so collapsing it does not remove it from the outline.
 *
 * Every claim below is either (a) derived from the generated contract and passed
 * in as {@link ConnectAnAgentFacts}, or (b) a boundary this repository's own code
 * enforces. Deliberately NOT stated, because none of it exists: SDKs, agent
 * frameworks, rate limits, scopes, streaming, webhooks, OAuth, or any key
 * functionality.
 *
 * P36V-1 slice 12 moved the endpoint browser to its own top-level tab, so the
 * two references to the Endpoint Explorer "above" became false. They now name
 * the TAB, and "Choose an Endpoint" carries a real control that goes there.
 *
 * P36V-1 slice 13 also removed three claims this guide was restating from
 * elsewhere on the same tab — the key-unavailable reason (the status banner's),
 * the browser-session / headless-credential boundary (an access row's) and the
 * 401 count (Quick Start's, which derives it from the contract). This guide
 * points at them instead of authoring a second copy, which is why
 * {@link ConnectAnAgentFacts} no longer carries the two count fields: it renders
 * no count.
 *
 * ONE claim came BACK in 2026-08-08, and the reversal is deliberate. Slice 13's
 * de-duplication was right for claims this guide merely restated, and wrong for
 * the one that is a PRECONDITION of the whole procedure: on a deployment that
 * answers only browser sessions, no agent can connect at all, and this guide is
 * a `<details>` a reader can open without ever seeing the sibling that said so.
 * See `API_ACCESS_COPY.connectPrerequisite` — still authored once, still counted
 * once, but rendered here rather than pointed at from here.
 *
 * On hosted access: that boundary is stated provider-neutrally wherever it
 * appears. Naming the identity layer in front of a deployment would disclose
 * infrastructure topology, which `settings-page.test.tsx` forbids on every
 * Settings tab (the same substring list the backend withholds from
 * `GET /api/about`).
 */
import { SAMPLE_BASE_ENV, SAMPLE_CREDENTIAL_ENV } from '../../lib/apiDocsModel';
import { API_ACCESS_COPY } from '../../lib/settingsContent';

export interface ConnectAnAgentFacts {
  /** Request media types the contract declares, from the document. */
  requestMediaTypes: string[];
  /** Every failure status the contract documents, ascending. */
  errorCodes: string[];
}

function mediaTypeSentence(mediaTypes: string[]): string {
  if (mediaTypes.length === 0) {
    return 'No operation in this contract declares a request-body media type, so nothing here expects one.';
  }
  // P36V — the trailing clause used to read "a key it does not name is dropped
  // rather than interpreted". That was FALSE for a mutating operation and
  // contradicted this app's own contract two sections above on this same screen:
  // `DemoResetRequest` sets `extra="forbid"`, so POST /api/demo/reset REJECTS an
  // unnamed key with 422 (verified live), and its own generated description says
  // "Any other field is rejected." Only the assistant-query models ignore extras.
  // Since the document carries no per-operation signal a caller could read off,
  // this sentence now states the safe rule and routes the reader to the operation
  // that does say — rather than generalising from one model to all of them.
  return `Operations that declare a request body declare ${mediaTypes.join(', ')}. Send only the fields the contract names for that operation: some reject an unnamed key outright and others ignore it, so each operation's own description in the Endpoint Explorer is the authority on which.`;
}

export function ConnectAnAgent({
  facts,
  open,
  onOpenChange,
  summaryId,
  onOpenExplorer,
}: {
  facts: ConnectAnAgentFacts;
  /** Controlled so Quick Start's link can open it and move focus here. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  summaryId: string;
  /** Selects the Endpoint Explorer tab — the guide's first step is there. */
  onOpenExplorer: () => void;
}) {
  const sections: { heading: string; body: string; action?: string }[] = [
    {
      heading: 'Choose an Endpoint',
      body: "Start on the Endpoint Explorer tab. Each operation there carries its purpose, its declared parameters, its request body when it has one, and every response the contract documents — all generated from this app's own contract, so an agent never has to work from a guess about what exists.",
      action: 'Open the Endpoint Explorer',
    },
    {
      heading: 'Set the Base URL',
      body: `Call the paths exactly as the Endpoint Explorer tab lists them; each one is already complete. The samples write the origin as $${SAMPLE_BASE_ENV} and never hard-code one, because the correct origin is wherever this page is being served from — the caller's to supply, not this screen's to publish.`,
    },
    {
      heading: 'Configure Authentication',
      body: `When a deployment enables authentication, every call carries an "Authorization: Bearer" header holding that deployment's credential; the liveness check is the one operation that stays reachable without it. Quick Start on this tab reports how many operations document a 401, the access rows at the top of this tab say what that one credential is and is not, and the Endpoint Explorer marks each operation.`,
    },
    {
      heading: 'Send Structured Requests',
      body: mediaTypeSentence(facts.requestMediaTypes),
    },
    {
      heading: 'Respect Read and Write Boundaries',
      body: "Read operations are safe to repeat. Writes change a record and require explicit user intent — an agent should never write on someone's behalf unless that person asked for that specific change. Several writes also require the record's current ETag, so a blind overwrite is refused rather than applied, and file upload is refused outright.",
    },
    {
      heading: 'Validate Responses',
      body: 'The official ISAAC schema and the deterministic validators are the only authority on whether a record is valid or exportable. Assistant operations are advisory: they answer from a fixed catalog and refuse what falls outside it. Project Memory returns leads to confirm against the cited files, and is not record truth. Treat both as input to a check, never as the check itself.',
    },
    {
      heading: 'Handle Errors',
      body: `Read the status before the body. This contract documents ${facts.errorCodes.join(', ')}, and every one of them is listed with the operation that can return it, in its own words. A refusal is a decision, not a transient fault: retrying it produces the same answer.`,
    },
    {
      heading: 'Protect Credentials',
      body: `Keep the credential in the environment the agent runs in and read it from there — that is what the samples do with $${SAMPLE_CREDENTIAL_ENV}. Never place it in a prompt, in source control, in a log line, or in a screenshot, and never echo it back in output. This app never displays a credential, and this screen has none to give.`,
    },
  ];

  return (
    <details
      className="api-connect"
      open={open}
      onToggle={(e) => onOpenChange((e.currentTarget as HTMLDetailsElement).open)}
    >
      <summary className="api-connect-summary" id={summaryId}>
        <h3 className="api-connect-title">Connect an Agent</h3>
      </summary>
      <p className="api-connect-lead">
        What a program calling this API has to get right — short, and only what this build actually
        supports.{' '}
        {/* The cross-reference to the OTHER agent surface, appended to the lead
            rather than given a paragraph of its own: this guide and the Connect
            Your Agent tab describe different protocols under near-identical
            names and make auth claims that do not reconcile unless a reader
            knows which path each is about. Authored in `API_ACCESS_COPY` — see
            the note on `connectMcpPointer` for the pair. */}
        {API_ACCESS_COPY.connectMcpPointer}
      </p>
      {/* FINDING B — the precondition, stated INSIDE the guide.
          Slice 13 (see the note at the top of this file) moved the tab's shared
          boundaries out to the access rows, which was right for claims this
          guide merely restated. It was wrong for this one: a reader can open
          this disclosure on its own and follow eight steps to an integration
          that cannot be made on the deployment serving the page, with the
          disqualifying fact one component away. A precondition has to sit with
          the procedure it disqualifies.
          Authored once, in `API_ACCESS_COPY`, so the duplication guard counts
          it like every other canonical string on this tab. */}
      <p className="api-connect-prerequisite">{API_ACCESS_COPY.connectPrerequisite}</p>
      <div className="api-connect-body">
        {sections.map((section) => (
          <section className="api-connect-section" key={section.heading}>
            <h4 className="api-connect-heading">{section.heading}</h4>
            <p>{section.body}</p>
            {section.action && (
              <button type="button" className="settings-jump-btn" onClick={onOpenExplorer}>
                {section.action}
              </button>
            )}
          </section>
        ))}
      </div>
    </details>
  );
}
