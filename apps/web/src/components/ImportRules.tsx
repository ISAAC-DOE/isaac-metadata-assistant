import { useId, useState } from 'react';
import { HelpTip } from './HelpTip';
import { SemanticStatus } from './SemanticStatus';
import { ExperimentPicker } from './ImportConflicts';
import { api } from '../lib/api';
import { IMPORT_STAGE_COPY } from '../lib/historicalImportContent';
import {
  liveChannels,
  RULE_KIND_LABELS,
  RULE_SCOPE_LABELS,
  shortConventionName,
} from '../lib/importStages';
import type { ProposalDestinations } from '../lib/importDestinations';
import type {
  ApiConventionRule,
  ApiImportProfile,
  ApiImportRulesView,
  ApiImportSignalSelection,
  ApiImportUnitRow,
} from '../lib/types';

type ActFn = (name: string, run: () => Promise<unknown>) => Promise<void>;
type Scope = 'import' | 'experiment' | 'profile';
const COPY = IMPORT_STAGE_COPY;

/**
 * READING RULES — "LEARNING", WITHOUT SILENT PROMOTION (owner QA H1, 2026-09-22).
 *
 * A rule records HOW TO READ sources: which naming convention applies to which runs,
 * which of two disagreeing readings a scientist chose, which channel belongs to which
 * element. It never records a value. Each one says where it applies — only this
 * import, an experiment, or a convention — and who confirmed it: `Unattributed` in
 * every deployment of this build, because no trusted sign-in boundary exists, and
 * saying so honestly is the point.
 *
 * A rule confirmed on ANOTHER experiment is shown as a suggestion with what it would
 * match here, and it applies only when a scientist adopts it for this experiment.
 */
export function ImportRules({
  rules,
  profiles,
  importId,
  busy,
  onAct,
  destinations,
}: {
  rules: ApiImportRulesView | undefined;
  profiles: ApiImportProfile[];
  importId: string;
  busy: string | null;
  onAct: ActFn;
  destinations: ProposalDestinations;
}) {
  const recorded = [...(rules?.import ?? []), ...(rules?.experiment ?? [])];
  const suggestions = rules?.reusable_from_other_experiments ?? [];
  const nameOf = (id: string | null) => {
    const p = profiles.find((profile) => profile.profile_id === id);
    return p ? shortConventionName(p.display_name) : id ?? '';
  };

  return (
    <div className="hi-rules">
      <div className="hi-stage-sub-head">
        <h4 className="hi-block-title">{COPY.rulesTitle}</h4>
        <HelpTip subject={COPY.rulesTitle}>{COPY.rulesHelp}</HelpTip>
      </div>
      {recorded.length === 0 ? (
        <p className="hi-sub">{COPY.rulesNone}</p>
      ) : (
        <ul className="hi-rule-list">
          {recorded.map((rule) => (
            <RuleRow key={rule.rule_id} rule={rule} conventionName={nameOf(rule.profile_id)} />
          ))}
        </ul>
      )}

      {suggestions.length > 0 && (
        <>
          <h5 className="hi-block-subtitle">{COPY.suggestionsTitle}</h5>
          <ul className="hi-rule-list">
            {suggestions.map((row) => (
              <li key={row.rule.rule_id} className="hi-rule">
                <RuleSummary rule={row.rule} conventionName={nameOf(row.rule.profile_id)} />
                <p className="hi-sub">
                  From {row.from_experiment_title} · would match {row.matches?.units ?? 0} measurement
                  {(row.matches?.units ?? 0) === 1 ? '' : 's'} here
                  {row.difference_count ? `, changing ${row.difference_count}` : ''}.
                  {row.version_is_current === false ? ' Its convention version has changed since.' : ''}
                </p>
                <AdoptForm
                  rule={row.rule}
                  importId={importId}
                  busy={busy}
                  onAct={onAct}
                  destinations={destinations}
                  target={rules?.target_experiment_id ?? null}
                />
              </li>
            ))}
          </ul>
        </>
      )}

      <BindingForm
        profiles={profiles}
        importId={importId}
        busy={busy}
        onAct={onAct}
        destinations={destinations}
      />
    </div>
  );
}

/**
 * Which sources a rule applies to, in words. THE SERVER'S OWN SENTENCE FIRST
 * (`selector.description`); otherwise read from the selector — and an EMPTY list is not
 * a selector (2026-09-23: `Array.isArray([])` is true, so an every-source rule read
 * "sample group ·").
 */
export function selectorText(selector: Record<string, unknown>): string {
  if (typeof selector.description === 'string' && selector.description.trim()) {
    return selector.description;
  }
  const list = (value: unknown): string[] =>
    Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string' && v.length > 0) : [];
  const range = Array.isArray(selector.legacy_range) && selector.legacy_range.length === 2
    ? (selector.legacy_range as number[])
    : null;
  const groups = list(selector.group_tokens);
  const paths = list(selector.source_paths);
  if (range) return range[0] === range[1] ? `legacy number ${range[0]}` : `legacy numbers ${range[0]}–${range[1]}`;
  if (groups.length > 0) return `sample group ${groups.join(', ')}`;
  if (paths.length > 0) return `${paths.length} named source${paths.length === 1 ? '' : 's'}`;
  return 'every source';
}

function RuleSummary({ rule, conventionName }: { rule: ApiConventionRule; conventionName: string }) {
  const where = selectorText(rule.selector ?? {});
  const what =
    rule.kind === 'profile_binding'
      ? `${conventionName || String(rule.body.profile_id ?? '')}`
      : rule.kind === 'signal_assignment'
        ? ((rule.body.assignments as { channel: string; element: string; edge?: string | null }[] | undefined) ?? [])
            .map((a) => `${a.channel} → ${a.element}${a.edge ? ` ${a.edge}` : ''}`)
            .join(', ')
        : String(rule.body.chosen_value ?? rule.body.chosen_source_role ?? '');
  return (
    <p className="hi-rule-summary">
      <span className="hi-rule-kind">{RULE_KIND_LABELS[rule.kind] ?? rule.kind}</span>
      <span className="hi-rule-what">{what}</span>
      <span className="hi-sub">
        {where} · {RULE_SCOPE_LABELS[rule.scope] ?? rule.scope} · version {rule.version}
      </span>
    </p>
  );
}

function RuleRow({ rule, conventionName }: { rule: ApiConventionRule; conventionName: string }) {
  return (
    <li className="hi-rule">
      <RuleSummary rule={rule} conventionName={conventionName} />
      <p className="hi-sub">
        {COPY.confirmedBy}{' '}
        {rule.confirmed_by === 'unattributed' ? COPY.unattributed : rule.confirmed_by}
        {rule.version_is_current === false ? ' · its convention version has changed, so it no longer applies' : ''}
      </p>
    </li>
  );
}

function AdoptForm({
  rule,
  importId,
  busy,
  onAct,
  destinations,
  target,
}: {
  rule: ApiConventionRule;
  importId: string;
  busy: string | null;
  onAct: ActFn;
  destinations: ProposalDestinations;
  target: string | null;
}) {
  const [experimentId, setExperimentId] = useState(target ?? '');
  const key = `adopt:${rule.rule_id}`;
  return (
    <form
      className="hi-rule-adopt"
      onSubmit={(event) => {
        event.preventDefault();
        void onAct(key, async () => {
          const version = (await api.getExperiment(experimentId)).version;
          await api.recordImportRule(importId, {
            kind: rule.kind,
            scope: 'experiment',
            experimentId,
            experimentVersion: version,
            selector: rule.selector,
            body: rule.body,
            derivedFrom: rule.rule_id,
          });
        });
      }}
    >
      <ExperimentPicker value={experimentId} onChange={setExperimentId} destinations={destinations} />
      <button type="submit" className="btn btn-secondary" disabled={busy !== null || !experimentId}>
        {busy === key ? 'Adopting…' : COPY.adopt}
      </button>
    </form>
  );
}

/** Scope choice shared by every rule form: only here, an experiment, or a convention. */
function ScopeChoice({
  scope,
  setScope,
  experimentId,
  setExperimentId,
  destinations,
}: {
  scope: Scope;
  setScope: (s: Scope) => void;
  experimentId: string;
  setExperimentId: (id: string) => void;
  destinations: ProposalDestinations;
}) {
  const name = useId();
  return (
    <>
      <fieldset className="hi-resolve-group">
        <legend className="hi-field-label">{COPY.resolve.scope}</legend>
        {(['import', 'experiment', 'profile'] as Scope[]).map((option) => (
          <label key={option} className="hi-choice">
            <input type="radio" name={name} checked={scope === option} onChange={() => setScope(option)} />
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

/**
 * Read some runs under a different convention. Offered only when a second convention
 * is registered: with one, there is nothing to choose, and the surface says so.
 */
function BindingForm({
  profiles,
  importId,
  busy,
  onAct,
  destinations,
}: {
  profiles: ApiImportProfile[];
  importId: string;
  busy: string | null;
  onAct: ActFn;
  destinations: ProposalDestinations;
}) {
  const [profileId, setProfileId] = useState(profiles.find((p) => !p.is_default)?.profile_id ?? '');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [scope, setScope] = useState<Scope>('import');
  const [experimentId, setExperimentId] = useState('');
  const key = 'rule:binding';
  if (profiles.length < 2) {
    return <p className="hi-sub">{COPY.bindingOne}</p>;
  }
  const profile = profiles.find((p) => p.profile_id === profileId);
  const low = Number.parseInt(from, 10);
  const high = Number.parseInt(to, 10);
  const valid = profile !== undefined && Number.isFinite(low) && Number.isFinite(high) && low <= high;
  return (
    <form
      className="hi-resolve"
      onSubmit={(event) => {
        event.preventDefault();
        if (!valid || profile === undefined) return;
        void onAct(key, async () => {
          const version = scope !== 'import' ? (await api.getExperiment(experimentId)).version : undefined;
          await api.recordImportRule(importId, {
            kind: 'profile_binding',
            scope,
            ...(scope !== 'import' ? { experimentId, experimentVersion: version } : {}),
            selector: { legacy_range: [low, high] },
            body: { profile_id: profile.profile_id, profile_version: profile.profile_version },
          });
        });
      }}
    >
      <h5 className="hi-block-subtitle">{COPY.bindingTitle}</h5>
      <label className="hi-field">
        <span className="hi-field-label">{COPY.fields.convention}</span>
        <select className="hi-input" value={profileId} onChange={(e) => setProfileId(e.target.value)}>
          {profiles.map((p) => (
            <option key={p.profile_id} value={p.profile_id}>
              {shortConventionName(p.display_name)}
            </option>
          ))}
        </select>
      </label>
      <div className="hi-inline-fields">
        <label className="hi-field">
          <span className="hi-field-label">{COPY.fields.fromRun}</span>
          <input className="hi-input" inputMode="numeric" value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="hi-field">
          <span className="hi-field-label">{COPY.fields.toRun}</span>
          <input className="hi-input" inputMode="numeric" value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
      </div>
      <ScopeChoice
        scope={scope}
        setScope={setScope}
        experimentId={experimentId}
        setExperimentId={setExperimentId}
        destinations={destinations}
      />
      <button
        type="submit"
        className="btn btn-secondary"
        disabled={busy !== null || !valid || (scope !== 'import' && !experimentId)}
      >
        {busy === key ? 'Recording…' : COPY.bindingSubmit}
      </button>
    </form>
  );
}

const EDGES = ['', 'K', 'L1', 'L2', 'L3', 'M1', 'M2', 'M3', 'M4', 'M5'];

/**
 * THE HERFD SIGNAL FOR ONE RUN — a suggestion, a reason, and a way to confirm it.
 *
 * `proposed` is shown as Suggested, never as decided. A run whose several channels
 * carry signal (a dual-element measurement) shows each live channel and lets a
 * scientist say which element each belongs to; nothing picks one for them.
 */
export function SignalSelection({
  unit,
  selection,
  importId,
  busy,
  onAct,
  destinations,
  state,
}: {
  unit: ApiImportUnitRow;
  selection: ApiImportSignalSelection;
  importId: string;
  busy: string | null;
  onAct: ActFn;
  destinations: ProposalDestinations;
  state: { state: Parameters<typeof SemanticStatus>[0]['state']; label: string };
}) {
  const live = liveChannels(selection);
  const established = selection.elements[0];
  const [assign, setAssign] = useState<Record<string, { element: string; edge: string }>>(() =>
    Object.fromEntries(
      (selection.assignments.length > 0 ? selection.assignments.map((a) => a.channel) : live).map((channel) => {
        const a = selection.assignments.find((x) => x.channel === channel);
        return [channel, { element: a?.element ?? established?.element ?? '', edge: a?.edge ?? established?.edge ?? '' }];
      }),
    ),
  );
  const [scope, setScope] = useState<Scope>('import');
  const [experimentId, setExperimentId] = useState('');
  const key = `signal:${unit.stem}`;
  const channels = Object.keys(assign);
  const valid = channels.length > 0 && channels.every((c) => /^[A-Z][a-z]?$/.test(assign[c]?.element ?? ''));
  const canConfirm = selection.status !== 'confirmed' && channels.length > 0;

  return (
    <div className="hi-signal">
      <p className="hi-signal-line">
        <SemanticStatus state={state.state} label={state.label} size="sm" />{' '}
        {selection.assignments.length > 0
          ? selection.assignments
              .map((a) => `${a.channel} → ${a.element}${a.edge ? ` ${a.edge}` : ''}`)
              .join(' · ')
          : live.length > 0
            ? `${live.length} live channel${live.length === 1 ? '' : 's'}: ${live.join(', ')}`
            : 'No live channel'}
      </p>
      <p className="hi-sub">{selection.reason}</p>
      {canConfirm && (
        <form
          className="hi-resolve"
          onSubmit={(event) => {
            event.preventDefault();
            if (!valid) return;
            void onAct(key, async () => {
              const version = scope !== 'import' ? (await api.getExperiment(experimentId)).version : undefined;
              await api.recordImportRule(importId, {
                kind: 'signal_assignment',
                scope,
                ...(scope !== 'import' ? { experimentId, experimentVersion: version } : {}),
                selector: { source_paths: [unit.acquisition_path] },
                body: {
                  assignments: channels.map((channel) => ({
                    channel,
                    element: assign[channel]?.element,
                    ...(assign[channel]?.edge ? { edge: assign[channel]?.edge } : {}),
                  })),
                },
              });
            });
          }}
        >
          {channels.map((channel) => (
            <div className="hi-inline-fields" key={channel}>
              <span className="hi-signal-channel">{channel}</span>
              <label className="hi-field">
                <span className="hi-field-label">{COPY.fields.element}</span>
                <input
                  className="hi-input hi-input-short"
                  value={assign[channel]?.element ?? ''}
                  maxLength={2}
                  onChange={(e) =>
                    setAssign((prev) => ({ ...prev, [channel]: { element: e.target.value, edge: prev[channel]?.edge ?? '' } }))
                  }
                />
              </label>
              <label className="hi-field">
                <span className="hi-field-label">{COPY.fields.edge}</span>
                <select
                  className="hi-input hi-input-short"
                  value={assign[channel]?.edge ?? ''}
                  onChange={(e) =>
                    setAssign((prev) => ({ ...prev, [channel]: { element: prev[channel]?.element ?? '', edge: e.target.value } }))
                  }
                >
                  {EDGES.map((edge) => (
                    <option key={edge} value={edge}>
                      {edge || '—'}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          ))}
          <ScopeChoice
            scope={scope}
            setScope={setScope}
            experimentId={experimentId}
            setExperimentId={setExperimentId}
            destinations={destinations}
          />
          <button
            type="submit"
            className="btn btn-secondary"
            disabled={busy !== null || !valid || (scope !== 'import' && !experimentId)}
          >
            {busy === key
              ? 'Recording…'
              : selection.status === 'proposed'
                ? COPY.signalConfirm
                : COPY.signalAssign}
          </button>
        </form>
      )}
    </div>
  );
}
