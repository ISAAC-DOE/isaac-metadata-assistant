/**
 * Settings → API → Documentation → Connect an Agent (P36V PR3 slice C).
 *
 * Eight short sections, collapsed behind one disclosure so the Documentation
 * sub-tab stays a reference surface rather than becoming a single-page manual.
 * The disclosure's `<summary>` carries the section's real `<h3>` (heading content
 * is permitted there), so collapsing it does not remove it from the outline.
 *
 * Every claim below is either (a) derived from the generated contract and passed
 * in as {@link ConnectAnAgentFacts}, or (b) a boundary this repository's own code
 * enforces. Deliberately NOT stated, because none of it exists: SDKs, agent
 * frameworks, rate limits, scopes, streaming, webhooks, OAuth, or any key
 * functionality.
 *
 * On hosted access: the caveat is stated provider-neutrally on purpose. Naming
 * the identity layer in front of a deployment would disclose infrastructure
 * topology, which `settings-page.test.tsx` forbids on every Settings tab (the
 * same substring list the backend withholds from `GET /api/about`). The
 * SUBSTANCE — a browser session is not a headless credential — is stated in
 * full.
 */
import { SAMPLE_BASE_ENV, SAMPLE_CREDENTIAL_ENV } from '../../lib/apiDocsModel';

export interface ConnectAnAgentFacts {
  /** Request media types the contract declares, from the document. */
  requestMediaTypes: string[];
  /** Every failure status the contract documents, ascending. */
  errorCodes: string[];
  /** Operations whose contract documents a `401`, out of the total. */
  authRequiredCount: number;
  operationCount: number;
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
}: {
  facts: ConnectAnAgentFacts;
  /** Controlled so Quick Start's link can open it and move focus here. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  summaryId: string;
}) {
  const sections: { heading: string; body: string }[] = [
    {
      heading: 'Choose an Endpoint',
      body: "Start in the Endpoint Explorer above. Each operation there carries its purpose, its declared parameters, its request body when it has one, and every response the contract documents — all generated from this app's own contract, so an agent never has to work from a guess about what exists.",
    },
    {
      heading: 'Set the Base URL',
      body: `Call the paths exactly as the Explorer lists them; each one is already complete. The samples write the origin as $${SAMPLE_BASE_ENV} and never hard-code one, because the correct origin is wherever this page is being served from — the caller's to supply, not this screen's to publish.`,
    },
    {
      heading: 'Configure Authentication',
      body: `When a deployment enables authentication, every call carries an "Authorization: Bearer" header holding that deployment's credential; the liveness check is the one operation that stays reachable without it. ${facts.authRequiredCount} of ${facts.operationCount} operations document a 401, which is how the Explorer marks them. Signing in through a deployment's identity layer with a browser is not the same thing as headless authentication: that gives a person an interactive session, not a credential a program can present on its own. And API keys are unavailable here — see API Keys — because this API has no operation that issues one.`,
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
        supports.
      </p>
      <div className="api-connect-body">
        {sections.map((section) => (
          <section className="api-connect-section" key={section.heading}>
            <h4 className="api-connect-heading">{section.heading}</h4>
            <p>{section.body}</p>
          </section>
        ))}
      </div>
    </details>
  );
}
