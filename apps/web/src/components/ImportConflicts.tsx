import { useId, useMemo, useState } from 'react';
import { Disclosure } from './Disclosure';
import { SemanticStatus } from './SemanticStatus';
import { api } from '../lib/api';
import { conflictKindLabel } from '../lib/bl15ReviewContent';
import { IMPORT_STAGE_COPY } from '../lib/historicalImportContent';
import {
  CHOOSABLE_ROLES,
  isResolved,
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
      const key = c.kind === 'field' ? '__field__' : c.topic;
      const list = out.get(key);
      if (list) list.push(c);
      else out.set(key, [c]);
    }
    return [...out.entries()];
  }, [conflicts]);

  if (conflicts.length === 0) {
    return <p className="hi-body hi-empty-inline">{COPY.conflicts.none}</p>;
  }

  return (
    <div className="hi-conflict-groups">
      {groups.map(([key, list]) => {
        const explanations = [...new Set(list.map((c) => c.explanation).filter(Boolean))];
        const shared = explanations.length === 1 ? explanations[0] : null;
        const title = key === '__field__' ? COPY.stateLabels.conflict : conflictKindLabel(key);
        return (
          <section className="hi-conflict-group" key={key}>
            <h4 className="hi-conflict-group-title">
              {title}
              <span className="hi-count">{list.length}</span>
            </h4>
            {/* THE SERVER'S EXPLANATION, VERBATIM AND VISIBLE — once per kind when
                every conflict of the kind carries the same sentence, rather than
                repeated under each. */}
            {shared && <p className="hi-conflict-explanation">{shared}</p>}
            <ul className="hi-conflict-list">
              {list.map((conflict) => (
                <ConflictRow
                  key={conflict.key}
                  conflict={conflict}
                  showExplanation={shared === null}
                  sameKindInGroup={
                    conflict.groupToken === null
                      ? 1
                      : list.filter((c) => c.groupToken === conflict.groupToken).length
                  }
                  importId={importId}
                  busy={busy}
                  onAct={onAct}
                  destinations={destinations}
                />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

function ConflictRow({
  conflict,
  showExplanation,
  sameKindInGroup,
  importId,
  busy,
  onAct,
  destinations,
}: {
  conflict: ConflictView;
  showExplanation: boolean;
  sameKindInGroup: number;
  importId: string;
  busy: string | null;
  onAct: ActFn;
  destinations: ProposalDestinations;
}) {
  const resolved = isResolved(conflict);
  const chosen = resolved ? String(conflict.resolution?.chosen_value ?? '') : '';
  return (
    <li className={`hi-conflict${resolved ? ' is-resolved' : ''}`}>
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
        <ul className="hi-conflict-line">
          {conflict.readings.map((reading, index) => (
            <li key={index} className="hi-conflict-reading">
              <span className="hi-conflict-role">{roleLabel(reading.role, reading.sourceType)}</span>{' '}
              <span className="hi-conflict-value">{conflict.distinct?.[index] ?? reading.value}</span>
            </li>
          ))}
        </ul>
        <span className="hi-conflict-state">
          {conflict.forbidden
            ? COPY.resolve.forbidden
            : resolved
              ? `Resolved by a rule you recorded${chosen ? `: ${chosen}` : ''}. Every reading is still kept.`
              : COPY.conflicts.noValue}
        </span>
      </div>
      {showExplanation && conflict.explanation && (
        <p className="hi-conflict-explanation">{conflict.explanation}</p>
      )}
      {/* The file the conflict is ABOUT rides on the review control, so each of a
          long list of `Review Sources` buttons has a name that says which one. */}
      <Disclosure
        className="hi-conflict-review"
        summary={COPY.conflicts.review}
        meta={conflict.subject ? <span className="hi-conflict-subject">{conflict.subject}</span> : undefined}
      >
        <ol className="hi-layers">
          <li className="hi-layer">
            <h5 className="hi-layer-title">{COPY.layers.sourceFact}</h5>
            <ul className="hi-layer-facts">
              {conflict.readings.map((reading, index) => (
                <li key={index}>
                  <span className="hi-conflict-role">{roleLabel(reading.role, reading.sourceType)}</span>{' '}
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
                sameKindInGroup={sameKindInGroup}
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

function ResolveForm({
  conflict,
  sameKindInGroup,
  importId,
  busy,
  onAct,
  destinations,
}: {
  conflict: ConflictView;
  sameKindInGroup: number;
  importId: string;
  busy: string | null;
  onAct: ActFn;
  destinations: ProposalDestinations;
}) {
  const name = useId();
  const [choice, setChoice] = useState<number | null>(null);
  const [scope, setScope] = useState<Scope>('import');
  const [experimentId, setExperimentId] = useState('');
  const [recurring, setRecurring] = useState(false);
  const key = `resolve:${conflict.key}`;
  const chosen = choice === null ? null : conflict.readings[choice];
  const canRecur =
    conflict.kind === 'structural' &&
    sameKindInGroup > 1 &&
    conflict.groupToken !== null &&
    chosen !== null &&
    chosen !== undefined &&
    chosen.role !== null &&
    CHOOSABLE_ROLES.has(chosen.role);
  const needsRecord = scope !== 'import';

  return (
    <form
      className="hi-resolve"
      onSubmit={(event) => {
        event.preventDefault();
        if (chosen === null || chosen === undefined || conflict.target === null) return;
        void onAct(key, async () => {
          const version = needsRecord ? (await api.getExperiment(experimentId)).version : undefined;
          const recur = canRecur && recurring;
          await api.recordImportRule(importId, {
            kind: 'conflict_resolution',
            scope,
            ...(needsRecord ? { experimentId, experimentVersion: version } : {}),
            ...(recur ? { selector: { group_tokens: [conflict.groupToken] } } : {}),
            body: recur
              ? { conflict_kind: conflict.topic, chosen_source_role: chosen.role }
              : { ...conflict.target, chosen_value: chosen.value },
          });
        });
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
              <span className="hi-conflict-role">{roleLabel(reading.role, reading.sourceType)}</span>{' '}
              {reading.value}
            </span>
          </label>
        ))}
      </fieldset>
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
      {needsRecord && (
        <ExperimentPicker value={experimentId} onChange={setExperimentId} destinations={destinations} />
      )}
      {canRecur && (
        <label className="hi-choice">
          <input type="checkbox" checked={recurring} onChange={(e) => setRecurring(e.target.checked)} />
          <span>{COPY.resolve.recurring}</span>
        </label>
      )}
      <button
        type="submit"
        className="btn btn-secondary"
        disabled={busy !== null || chosen === null || (needsRecord && !experimentId)}
      >
        {busy === key ? 'Recording…' : COPY.resolve.submit}
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
