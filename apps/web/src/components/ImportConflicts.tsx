import { useId, useMemo, useState } from 'react';
import { Disclosure } from './Disclosure';
import { HelpTip } from './HelpTip';
import { SemanticStatus } from './SemanticStatus';
import { api } from '../lib/api';
import { conflictKindLabel } from '../lib/bl15ReviewContent';
import { IMPORT_STAGE_COPY } from '../lib/historicalImportContent';
import {
  CHOOSABLE_ROLES,
  isResolved,
  readingLabel,
  roleLabel,
  type ConflictView,
} from '../lib/importStages';
import type { ProposalDestinations } from '../lib/importDestinations';

type ActFn = (name: string, run: () => Promise<unknown>) => Promise<void>;

const COPY = IMPORT_STAGE_COPY;

/**
 * CONFLICTS, SOURCE BY SOURCE (owner QA H1, 2026-09-22).
 *
 * The brief's own example is the shape of every row here:
 *
 *   `× Sources Conflict · Filename after1400Cycling · Beamtime notes
 *    after1500Cycling · No value has been selected. [Review Sources]`
 *
 * — the state as icon and word, each source named by the KIND of claim it makes and
 * the one token that differs, and a plain statement that nothing was chosen. Opening
 * `Review Sources` shows the four layers the server keeps apart, each labelled:
 *
 *   Source Facts · Normalized Reading · Suggested Resolution (not authoritative) ·
 *   Scientist-Confirmed Resolution
 *
 * WHAT STAYS VISIBLE, AND WHY. A conflict is one of the things a `HelpTip` or a
 * collapsed disclosure must never hold (DEC-35), so the conflict itself — its
 * state, every source's reading, and the server's explanation of what KIND of
 * disagreement it is — is on the surface. Only the per-source locators, the
 * evidence behind a suggestion and the resolve form sit behind `Review Sources`.
 *
 * A recorded resolution goes to `POST /imports/{id}/rules`: it chooses BETWEEN
 * stated readings, keeps every one of them, and for a record field still reaches a
 * record only as a proposal. Two acquisitions sharing one legacy number are never
 * resolved — the server forbids it and this surface offers no control for it.
 */
/** How many conflicts of one kind show before `Show N more`. */
export const CONFLICTS_SHOWN_PER_KIND = 5;

export function ImportConflicts({
  conflicts,
  importId,
  busy,
  onAct,
  destinations,
}: {
  conflicts: ConflictView[];
  importId: string;
  busy: string | null;
  onAct: ActFn;
  destinations: ProposalDestinations;
}) {
  const groups = useMemo(() => {
    const out = new Map<string, ConflictView[]>();
    for (const c of conflicts) {
      const key = c.kind === 'field' ? FIELD_KIND : c.topic;
      const list = out.get(key);
      if (list) list.push(c);
      else out.set(key, [c]);
    }
    return [...out.entries()];
  }, [conflicts]);
  /* ONE polite announcement region for the whole stage, permanently mounted, so a
     `Show N more` press is announced without a live region per kind. */
  const [announcement, setAnnouncement] = useState('');

  if (conflicts.length === 0) {
    return <p className="hi-body hi-empty-inline">{COPY.conflicts.none}</p>;
  }

  return (
    <div className="hi-conflict-groups">
      {groups.map(([key, list]) => (
        <ConflictKind
          key={key}
          kind={key}
          list={list}
          importId={importId}
          busy={busy}
          onAct={onAct}
          destinations={destinations}
          announce={setAnnouncement}
        />
      ))}
      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>
    </div>
  );
}

const FIELD_KIND = '__field__';

/**
 * ONE KIND OF CONFLICT (orchestrator decision, 2026-09-22, for a 53-conflict import).
 *
 * The header is ALWAYS visible and carries what a reader must not miss: what kind of
 * disagreement this is, HOW MANY there are, and what it means — the server's own
 * explanation, verbatim (a field disagreement has none, so its meaning is this
 * surface's one sentence). The first five conflicts follow; the rest are one press
 * away behind `Show N more`, a real button whose name carries the count. Every
 * conflict stays in the DOM and counted: hiding a ROW is not hiding the uncertainty,
 * because the header has already stated it. The action that resolves a whole sample
 * group at once lives here, at the kind, because that is what it acts on.
 */
function ConflictKind({
  kind,
  list,
  importId,
  busy,
  onAct,
  destinations,
  announce,
}: {
  kind: string;
  list: ConflictView[];
  importId: string;
  busy: string | null;
  onAct: ActFn;
  destinations: ProposalDestinations;
  announce: (text: string) => void;
}) {
  const [all, setAll] = useState(false);
  const titleId = useId();
  const listId = useId();
  const explanations = [...new Set(list.map((c) => c.explanation).filter(Boolean))] as string[];
  const shared = explanations.length === 1 ? explanations[0] : null;
  const title = kind === FIELD_KIND ? COPY.conflicts.fieldKindTitle : conflictKindLabel(kind);
  const meaning = kind === FIELD_KIND ? COPY.conflicts.fieldKindMeaning : shared;
  /* ONE LINE ON THE SURFACE, THE REST ONE PRESS AWAY (independent review, 2026-09-23):
     the first sentence of the server's own explanation stays visible, verbatim; the
     remainder is behind the `?`, still in the DOM. */
  const [lead, rest] = splitFirstSentence(meaning ?? '');
  const extra = list.length - CONFLICTS_SHOWN_PER_KIND;
  const open = list.filter((c) => !isResolved(c)).length;
  const forbidden = list.every((c) => c.forbidden);
  const groupable = kind !== FIELD_KIND && groupRuleChoices(list) !== null;
  /* OPEN FIRST, resolved after — so the first five rows are the ones still waiting. */
  const ordered = [...list.filter((c) => !isResolved(c)), ...list.filter((c) => isResolved(c))];

  return (
    <section className="hi-conflict-group" aria-labelledby={titleId}>
      <div className="hi-conflict-group-head">
        <h4 className="hi-conflict-group-title" id={titleId}>
          {title}
          <span className="hi-count">{list.length}</span>
          {open !== list.length && (
            <span className="hi-sub">
              {open} open · {list.length - open} resolved
            </span>
          )}
        </h4>
        {/* THE MEANING, VERBATIM — its first sentence always visible, once per kind. */}
        {lead && (
          <p className="hi-conflict-explanation">
            {lead}
            {rest && (
              <>
                {' '}
                <HelpTip subject={`this kind of conflict: ${title}`}>{rest}</HelpTip>
              </>
            )}
          </p>
        )}
        {/* WHAT HAS BEEN CHOSEN, said once for the kind rather than on every row. */}
        {open > 0 && (
          <p className="hi-conflict-kind-state">
            {forbidden
              ? COPY.resolve.forbidden
              : `${open} open — ${COPY.conflicts.noValue.replace(/\.$/, '')} for ${open === 1 ? 'it' : 'any of them'}.`}
          </p>
        )}
        {groupable && (
          <Disclosure className="hi-conflict-review hi-group-rule" summary={COPY.resolve.groupTitle}>
            <GroupRuleForm
              kind={kind}
              list={list}
              importId={importId}
              busy={busy}
              onAct={onAct}
              destinations={destinations}
            />
          </Disclosure>
        )}
      </div>
      <ul className="hi-conflict-list" id={listId}>
        {ordered.map((conflict, index) => (
          <ConflictRow
            key={conflict.key}
            conflict={conflict}
            hidden={!all && index >= CONFLICTS_SHOWN_PER_KIND}
            showExplanation={kind !== FIELD_KIND && shared === null}
            importId={importId}
            busy={busy}
            onAct={onAct}
            destinations={destinations}
          />
        ))}
      </ul>
      {extra > 0 && (
        <button
          type="button"
          className="btn btn-ghost hi-show-more"
          aria-expanded={all}
          aria-controls={listId}
          aria-describedby={titleId}
          onClick={() => {
            const next = !all;
            setAll(next);
            announce(
              next
                ? `${extra} more shown — all ${list.length} of this kind.`
                : `Showing the first ${CONFLICTS_SHOWN_PER_KIND} of ${list.length}.`,
            );
          }}
        >
          {all ? `Show the first ${CONFLICTS_SHOWN_PER_KIND} only` : `Show ${extra} more`}
        </button>
      )}
    </section>
  );
}

function ConflictRow({
  conflict,
  hidden,
  showExplanation,
  importId,
  busy,
  onAct,
  destinations,
}: {
  conflict: ConflictView;
  hidden: boolean;
  showExplanation: boolean;
  importId: string;
  busy: string | null;
  onAct: ActFn;
  destinations: ProposalDestinations;
}) {
  const resolved = isResolved(conflict);
  const chosen = resolved ? String(conflict.resolution?.chosen_value ?? '') : '';
  return (
    <li className={`hi-conflict${resolved ? ' is-resolved' : ''}`} hidden={hidden}>
      {/* ONE LINE, AS THE BRIEF WROTE IT: the state, each source's reading, and what
          was chosen — `× Sources Conflict · Filename … · Header … · No value has been
          selected.` Every reading stays on the surface; only the locators, the
          evidence behind a suggestion and the resolve form sit behind the review. */}
      <div className="hi-conflict-main">
        {resolved ? (
          <SemanticStatus state="complete" label={COPY.stateLabels.resolved} size="sm" />
        ) : (
          <SemanticStatus state="conflict" label={COPY.stateLabels.conflict} size="sm" />
        )}
        {/* A field disagreement names WHICH field, since one kind holds them all. */}
        {conflict.kind === 'field' && <span className="hi-conflict-topic">{conflict.topic}</span>}
        <ul className="hi-conflict-line">
          {conflict.readings.map((reading, index) => (
            <li key={index} className="hi-conflict-reading">
              <span className="hi-conflict-role">{readingLabel(reading)}</span>{' '}
              <span className="hi-conflict-value">{conflict.distinct?.[index] ?? reading.value}</span>
            </li>
          ))}
        </ul>
        {/* The open state is said once, on the kind; a row says so only when it differs. */}
        {resolved && (
          <span className="hi-conflict-state">
            {`Resolved by a rule you recorded${chosen ? `: ${chosen}` : ''}. Every reading is still kept.`}
          </span>
        )}
        {/* Which acquisition, so a long list of rows can be told apart. */}
        {conflict.subject && <span className="hi-conflict-subject">{conflict.subject}</span>}
      </div>
      {showExplanation && conflict.explanation && (
        <p className="hi-conflict-explanation">{conflict.explanation}</p>
      )}
      <Disclosure
        className="hi-conflict-review"
        summary={
          <>
            {COPY.conflicts.review}
            {/* Each "Review Sources" names WHICH conflict for a screen reader, since a
                list holds many; the visible words stay the start of the name. */}
            {conflict.subject && <span className="sr-only"> — {conflict.subject}</span>}
          </>
        }
      >
        <ol className="hi-layers">
          <li className="hi-layer">
            <h5 className="hi-layer-title">{COPY.layers.sourceFact}</h5>
            <ul className="hi-layer-facts">
              {conflict.readings.map((reading, index) => (
                <li key={index}>
                  <span className="hi-conflict-role">{readingLabel(reading)}</span>{' '}
                  <span className="hi-layer-value">{reading.value}</span>
                  <span className="hi-sub">
                    {reading.sources.map((s) => `${s.path} · ${s.locator}`).join('; ')}
                  </span>
                  {reading.roleMeaning && <span className="hi-sub">{reading.roleMeaning}</span>}
                </li>
              ))}
            </ul>
          </li>
          <li className="hi-layer">
            <h5 className="hi-layer-title">{COPY.layers.normalized}</h5>
            <p className="hi-sub">
              {conflict.kind === 'field'
                ? 'Each reading above is already the normalized value where a named rule produced one.'
                : COPY.layers.normalizedNone}
            </p>
          </li>
          <li className="hi-layer hi-layer-suggested">
            <h5 className="hi-layer-title">
              {COPY.layers.suggested}
              <span className="hi-layer-flag">{COPY.layers.nonAuthoritative}</span>
            </h5>
            <Suggestion conflict={conflict} />
          </li>
          <li className="hi-layer">
            <h5 className="hi-layer-title">{COPY.layers.confirmed}</h5>
            {resolved ? (
              <p className="hi-sub">
                {chosen ? `${chosen} — ` : ''}recorded as a reading rule. {COPY.confirmedBy}{' '}
                {COPY.unattributed}.
              </p>
            ) : conflict.forbidden ? (
              <p className="hi-sub">{COPY.resolve.forbidden}</p>
            ) : !conflict.resolvable || conflict.target === null ? (
              <p className="hi-sub">{COPY.resolve.fixtureOnly}</p>
            ) : (
              <ResolveForm
                conflict={conflict}
                importId={importId}
                busy={busy}
                onAct={onAct}
                destinations={destinations}
              />
            )}
          </li>
        </ol>
      </Disclosure>
    </li>
  );
}

function Suggestion({ conflict }: { conflict: ConflictView }) {
  const rec = conflict.recommendation;
  if (!rec) return <p className="hi-sub">{COPY.layers.noSuggestion}</p>;
  return (
    <>
      <p className="hi-sub">
        {rec.status === 'suggested' && rec.value ? (
          <>
            Suggests <span className="hi-layer-value">{rec.value}</span>.{' '}
          </>
        ) : null}
        {rec.why}
      </p>
      {rec.supports.length > 0 && (
        <ul className="hi-layer-supports">
          {rec.supports.map((support, index) => (
            <li key={index} className={support.counts ? undefined : 'is-not-counted'}>
              {support.sentence}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

type Scope = 'import' | 'experiment' | 'profile';

/** The three scopes, in the owner's words, and the record picker a stored rule needs. */
function ScopeFields({
  name,
  scope,
  setScope,
  experimentId,
  setExperimentId,
  destinations,
}: {
  name: string;
  scope: Scope;
  setScope: (scope: Scope) => void;
  experimentId: string;
  setExperimentId: (id: string) => void;
  destinations: ProposalDestinations;
}) {
  return (
    <>
      <fieldset className="hi-resolve-group">
        <legend className="hi-field-label">{COPY.resolve.scope}</legend>
        {(['import', 'experiment', 'profile'] as Scope[]).map((option) => (
          <label key={option} className="hi-choice">
            <input
              type="radio"
              name={`${name}-scope`}
              checked={scope === option}
              onChange={() => setScope(option)}
            />
            <span>{COPY.scopeOptions[option]}</span>
          </label>
        ))}
      </fieldset>
      {scope !== 'import' && (
        <ExperimentPicker value={experimentId} onChange={setExperimentId} destinations={destinations} />
      )}
    </>
  );
}

/** Record a rule: read the record's version first when it is stored on one. */
async function recordConflictRule(
  importId: string,
  scope: Scope,
  experimentId: string,
  rule: { selector?: Record<string, unknown>; body: Record<string, unknown> },
) {
  const stored = scope !== 'import';
  const version = stored ? (await api.getExperiment(experimentId)).version : undefined;
  await api.recordImportRule(importId, {
    kind: 'conflict_resolution',
    scope,
    ...(stored ? { experimentId, experimentVersion: version } : {}),
    ...(rule.selector ? { selector: rule.selector } : {}),
    body: rule.body,
  });
}

function ResolveForm({
  conflict,
  importId,
  busy,
  onAct,
  destinations,
}: {
  conflict: ConflictView;
  importId: string;
  busy: string | null;
  onAct: ActFn;
  destinations: ProposalDestinations;
}) {
  const name = useId();
  const [choice, setChoice] = useState<number | null>(null);
  const [scope, setScope] = useState<Scope>('import');
  const [experimentId, setExperimentId] = useState('');
  const key = `resolve:${conflict.key}`;
  const chosen = choice === null ? null : conflict.readings[choice];

  return (
    <form
      className="hi-resolve"
      onSubmit={(event) => {
        event.preventDefault();
        if (chosen === null || chosen === undefined || conflict.target === null) return;
        const target = conflict.target;
        void onAct(key, () =>
          recordConflictRule(importId, scope, experimentId, {
            body: { ...target, chosen_value: chosen.value },
          }),
        );
      }}
    >
      <fieldset className="hi-resolve-group">
        <legend className="hi-field-label">{COPY.resolve.choose}</legend>
        {conflict.readings.map((reading, index) => (
          <label key={index} className="hi-choice">
            <input
              type="radio"
              name={`${name}-reading`}
              checked={choice === index}
              onChange={() => setChoice(index)}
            />
            <span>
              <span className="hi-conflict-role">{readingLabel(reading)}</span>{' '}
              {reading.value}
            </span>
          </label>
        ))}
      </fieldset>
      <ScopeFields
        name={name}
        scope={scope}
        setScope={setScope}
        experimentId={experimentId}
        setExperimentId={setExperimentId}
        destinations={destinations}
      />
      <button
        type="submit"
        className="btn btn-secondary"
        disabled={busy !== null || chosen === null || (scope !== 'import' && !experimentId)}
      >
        {busy === key ? 'Recording…' : COPY.resolve.submit}
      </button>
    </form>
  );
}

/**
 * What a whole-sample-group resolution can choose between, derived from the kind's
 * own conflicts: the source KINDS (roles) that appear among their readings and that
 * the server accepts as a choice, and the sample groups holding MORE THAN ONE
 * conflict of this kind that can be resolved. `null` when there is nothing to choose
 * — a single conflict is resolved on its own row, and two acquisitions sharing a
 * legacy number are never resolved at all.
 */
/** `[first sentence, the rest]` of a server explanation, split at the first ". ". */
export function splitFirstSentence(text: string): [string, string] {
  const trimmed = text.trim();
  const at = trimmed.search(/[.!?](\s|$)/);
  if (at < 0 || at === trimmed.length - 1) return [trimmed, ''];
  return [trimmed.slice(0, at + 1), trimmed.slice(at + 1).trim()];
}

export function groupRuleChoices(
  list: readonly ConflictView[],
): { roles: string[]; groups: { token: string; count: number }[] } | null {
  const eligible = list.filter(
    (c) => c.kind === 'structural' && c.resolvable && !c.forbidden && !isResolved(c) && c.groupToken !== null,
  );
  const counts = new Map<string, number>();
  for (const c of eligible) counts.set(c.groupToken as string, (counts.get(c.groupToken as string) ?? 0) + 1);
  const groups = [...counts.entries()]
    .filter(([, count]) => count > 1)
    .map(([token, count]) => ({ token, count }))
    .sort((a, b) => a.token.localeCompare(b.token));
  const roles = [
    ...new Set(
      eligible.flatMap((c) => c.readings.map((r) => r.role)).filter((r): r is string => r !== null && CHOOSABLE_ROLES.has(r)),
    ),
  ];
  if (groups.length === 0 || roles.length < 2) return null;
  return { roles, groups };
}

/**
 * RESOLVE EVERY CONFLICT OF THIS KIND IN ONE SAMPLE GROUP — by the KIND of source
 * that is right ("for sample 03, the file's name is the correction"), never by a
 * value. The server applies it only where exactly one reading has that role, and
 * keeps every reading.
 */
function GroupRuleForm({
  kind,
  list,
  importId,
  busy,
  onAct,
  destinations,
}: {
  kind: string;
  list: ConflictView[];
  importId: string;
  busy: string | null;
  onAct: ActFn;
  destinations: ProposalDestinations;
}) {
  const choices = groupRuleChoices(list);
  const name = useId();
  const [role, setRole] = useState<string | null>(null);
  const [group, setGroup] = useState(choices?.groups[0]?.token ?? '');
  const [scope, setScope] = useState<Scope>('import');
  const [experimentId, setExperimentId] = useState('');
  const key = `resolve-group:${kind}`;
  if (choices === null) return null;
  return (
    <form
      className="hi-resolve"
      onSubmit={(event) => {
        event.preventDefault();
        if (role === null || !group) return;
        void onAct(key, () =>
          recordConflictRule(importId, scope, experimentId, {
            selector: { group_tokens: [group] },
            body: { conflict_kind: kind, chosen_source_role: role },
          }),
        );
      }}
    >
      <p className="hi-sub">{COPY.resolve.groupLead}</p>
      <label className="hi-field">
        <span className="hi-field-label">{COPY.resolve.groupWhich}</span>
        <select className="hi-input" value={group} onChange={(e) => setGroup(e.target.value)}>
          {choices.groups.map((g) => (
            <option key={g.token} value={g.token}>
              Sample {g.token} ({g.count} conflicts)
            </option>
          ))}
        </select>
      </label>
      <fieldset className="hi-resolve-group">
        <legend className="hi-field-label">{COPY.resolve.groupRole}</legend>
        {choices.roles.map((r) => (
          <label key={r} className="hi-choice">
            <input type="radio" name={`${name}-role`} checked={role === r} onChange={() => setRole(r)} />
            <span>{roleLabel(r, null)}</span>
          </label>
        ))}
      </fieldset>
      <ScopeFields
        name={name}
        scope={scope}
        setScope={setScope}
        experimentId={experimentId}
        setExperimentId={setExperimentId}
        destinations={destinations}
      />
      <button
        type="submit"
        className="btn btn-secondary"
        disabled={busy !== null || role === null || !group || (scope !== 'import' && !experimentId)}
      >
        {busy === key ? 'Recording…' : COPY.resolve.groupSubmit}
      </button>
    </form>
  );
}

/** A record picker for a rule stored on an experiment. The same list every picker uses. */
export function ExperimentPicker({
  value,
  onChange,
  destinations,
}: {
  value: string;
  onChange: (id: string) => void;
  destinations: ProposalDestinations;
}) {
  return (
    <label className="hi-field">
      <span className="hi-field-label">{COPY.whichExperiment}</span>
      {destinations.failed ? (
        <>
          <input
            className="hi-input"
            type="text"
            required
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder="the record's id"
          />
          <span className="hi-note">
            The list of records could not be read, so this asks for the id instead.
          </span>
        </>
      ) : destinations.rows === null ? (
        <span className="hi-note">Reading your records…</span>
      ) : destinations.rows.length === 0 ? (
        <span className="hi-note">This workspace holds no records yet.</span>
      ) : (
        <select
          className="hi-input"
          required
          value={value}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">Choose a record…</option>
          {destinations.rows.map((row) => (
            <option key={row.id} value={row.id}>
              {row.title}
            </option>
          ))}
        </select>
      )}
    </label>
  );
}
