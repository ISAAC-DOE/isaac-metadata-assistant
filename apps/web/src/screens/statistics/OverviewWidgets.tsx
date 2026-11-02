/**
 * THE OVERVIEW DASHBOARD — one widget per question, each in the form its metric
 * needs (2026-11-02).
 *
 *   Records            part-to-whole  → one stacked bar over the four statuses
 *   Open Questions     distribution   → columns: how many records owe 0, 1, 2 … answers
 *   Activity           trend          → area line, one point per day (per week over a year)
 *   Kinds of Change    ranking        → horizontal bars, busiest kind first
 *   Workflow           ordered steps  → horizontal bars in workflow order
 *   Evidence Support   part-to-whole  → one stacked bar over the six classes
 *   Historical Imports ordered steps  → horizontal bars over the import steps
 *
 * Every figure is read from the API on this page's own reads; nothing is estimated,
 * interpolated or defaulted. A widget with nothing to draw says so in one line and
 * draws no axis — a zero-filled chart would state a measurement that was not made.
 * Each chart still carries its summary sentence and data table (`ChartFrame`), so
 * no value is reachable only by pointer or only by colour.
 */
import { Link } from 'react-router-dom';
import {
  BarChartHorizontal,
  CircleHelp,
  History,
  Inbox,
  LayoutList,
  ShieldCheck,
  Workflow,
} from '../../components/icons';

import { Widget } from '../../components/Widget';
import { BackendDown, LoadingPanel } from '../../components/FetchStates';
import { LABELS, humanizeActivityToken } from '../../lib/labels';
import { ROUTES } from '../../lib/routes';
import type { RuntimeRecord } from '../../lib/crossRecordTriage';
import type { ApiActivitySummary } from '../../lib/types';
import type { FetchState } from '../../lib/useFetch';
import {
  EVIDENCE_CLASSES,
  deriveEvidenceTotals,
  deriveImportSteps,
  deriveOpenQuestionDistribution,
  deriveOpenQuestions,
  deriveWorkflowStages,
  deriveWorkspaceTotals,
} from '../../lib/statisticsModel';
import { HeadlineFigure, UnavailableNote } from './StatsPrimitives';
import {
  ChartEmpty,
  StatsBarChart,
  StatsColumnChart,
  StatsStackedBar,
  StatsTrendChart,
} from './StatsCharts';

type Fetched<T> = FetchState<T> & { reload: () => void };
export type RecordsFetch = Fetched<{ records: RuntimeRecord[]; total: number }>;
export type ActivityFetch = Fetched<ApiActivitySummary>;
export type ImportsFetch = Fetched<unknown>;

function count(n: number): string {
  return n.toLocaleString('en-US');
}

/** A compact failure note with a Retry, for a widget whose read did not answer. */
function WidgetUnavailable({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <UnavailableNote>
      <p>{message}</p>
      <div className="stats-retry">
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          Retry
        </button>
      </div>
    </UnavailableNote>
  );
}

/* ---- Records ------------------------------------------------------------ */

export function RecordsWidget({ records }: { records: RecordsFetch }) {
  const body = records.status === 'data' ? records.data : null;
  const totals = body === null ? null : deriveWorkspaceTotals(body);
  const stale = body === null ? 0 : body.records.filter((r) => r.artifact_state === 'stale').length;
  const rows =
    totals === null
      ? []
      : [
          { key: 'needs_attention', label: LABELS.groupNeedsAttention, value: totals.needsAttention },
          { key: 'in_review', label: LABELS.groupInReview, value: totals.inReview },
          { key: 'ready_to_export', label: LABELS.groupReady, value: totals.readyToExport },
          { key: 'done', label: 'Exported', value: totals.exported },
          ...(totals.unknownStatus > 0
            ? [{ key: 'unknown', label: 'Unrecognized Status', value: totals.unknownStatus }]
            : []),
        ];
  const counted = body?.records.length ?? 0;
  return (
    <Widget
      id="stats-records"
      title="Records"
      icon={<LayoutList size={18} strokeWidth={2} aria-hidden="true" />}
      className="stats-w2"
      info={
        <p>
          {LABELS.groupNeedsAttention} means open questions remain. {LABELS.groupInReview} means no
          question remains but the export dry-run does not pass yet. {LABELS.groupReady} means the
          dry-run passes. Exported means an official record has been written. Status is recomputed
          from the drafts on every read.
        </p>
      }
      lead={
        body !== null && totals !== null && counted !== totals.total ? (
          <UnavailableNote>
            Showing {count(counted)} of {count(totals.total)} records; the breakdown describes
            only the {count(counted)} received.
          </UnavailableNote>
        ) : undefined
      }
      headline={
        totals !== null ? <HeadlineFigure label="Total Records" value={count(totals.total)} /> : null
      }
      footer={<Link to={ROUTES.experiments}>Open My Experiments</Link>}
    >
      {records.status === 'loading' && <LoadingPanel label="Loading the records…" />}
      {records.status === 'error' && <BackendDown error={records.error} onRetry={records.reload} />}
      {totals !== null && counted > 0 && (
        <>
          <ul className="stats-keyed-figures" aria-hidden="true">
            {rows.map((row, i) => (
              <li key={row.key}>
                <span className="stats-keyed-label">
                  <span className="stats-chart-swatch" data-slot={String(i + 1)} />
                  {row.label}
                </span>
                <span className="stats-keyed-value">{count(row.value)}</span>
              </li>
            ))}
          </ul>
          <StatsStackedBar
            caption={`Records by status, out of ${count(counted)}`}
            captionHidden
            hideLegend
            rows={rows}
            total={counted}
            unit="records"
            categoryHeader="Status"
          />
          {stale > 0 && (
            <p className="stats-note">
              {stale === 1
                ? '1 exported record has changed since its export.'
                : `${count(stale)} exported records have changed since their export.`}
            </p>
          )}
        </>
      )}
      {totals !== null && counted === 0 && totals.total === 0 && (
        <p className="stats-note">No records yet.</p>
      )}
    </Widget>
  );
}

/* ---- Open Questions ----------------------------------------------------- */

export function OpenQuestionsWidget({ records }: { records: RecordsFetch }) {
  const list = records.status === 'data' ? records.data.records : null;
  const totals = list !== null && list.length > 0 ? deriveOpenQuestions(list) : null;
  const distribution = list !== null ? deriveOpenQuestionDistribution(list) : [];
  return (
    <Widget
      id="stats-questions"
      title="Open Questions"
      icon={<CircleHelp size={18} strokeWidth={2} aria-hidden="true" />}
      info={
        <p>
          The total counts questions; the chart counts records by how many questions each one is
          still waiting on. One record can owe several answers.
        </p>
      }
      headline={
        totals !== null ? (
          <HeadlineFigure
            label="Total Open Questions"
            value={count(totals.totalOpenQuestions)}
            tone={totals.totalOpenQuestions > 0 ? 'attention' : 'neutral'}
          />
        ) : null
      }
    >
      {records.status === 'loading' && <LoadingPanel label="Loading the open questions…" />}
      {records.status === 'error' && (
        <WidgetUnavailable message="The open questions could not be read." onRetry={records.reload} />
      )}
      {list !== null && list.length === 0 && <p className="stats-note">No records yet.</p>}
      {totals !== null && (
        <>
          <StatsColumnChart
            caption="Records by number of open questions"
            captionHidden
            rows={distribution}
            unit="records"
            total={null}
            categoryHeader="Open Questions"
          />
          {totals.recordsWithUnreadableCount > 0 && (
            <p className="stats-note">
              {totals.recordsWithUnreadableCount === 1
                ? '1 record reported no readable question count and is not charted.'
                : `${count(totals.recordsWithUnreadableCount)} records reported no readable question count and are not charted.`}
            </p>
          )}
        </>
      )}
    </Widget>
  );
}

/* ---- Activity ----------------------------------------------------------- */

export const ACTIVITY_RANGES = [
  { value: '7', label: '7 Days' },
  { value: '30', label: '30 Days' },
  { value: '365', label: '365 Days' },
] as const;

const DAY_FORMAT = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });

function dayLabel(iso: string): string {
  const when = new Date(`${iso}T00:00:00Z`);
  return Number.isFinite(when.getTime()) ? DAY_FORMAT.format(when) : iso;
}

export interface TrendSeries {
  rows: { key: string; label: string; value: number }[];
  axis: { first: string; middle?: string; last: string };
  period: 'day' | 'week';
}

/**
 * The served `by_day` buckets as chart rows: one point per day up to a month, one
 * per seven days beyond it. Weeks are counted back from the LAST day, so the
 * latest point is always a whole week ending today; a partial week at the start
 * is labelled by its own first day, never padded with days the window did not
 * cover.
 */
export function activityTrend(summary: ApiActivitySummary): TrendSeries | null {
  const days = Array.isArray(summary.by_day) ? summary.by_day : null;
  if (days === null || days.length === 0) return null;
  if (days.length <= 31) {
    const rows = days.map((d) => ({ key: d.date, label: dayLabel(d.date), value: d.count }));
    return {
      rows,
      axis: {
        first: rows[0].label,
        middle: rows.length > 7 ? rows[Math.floor(rows.length / 2)].label : undefined,
        last: rows[rows.length - 1].label,
      },
      period: 'day',
    };
  }
  const rows: TrendSeries['rows'] = [];
  for (let end = days.length; end > 0; end -= 7) {
    const slice = days.slice(Math.max(0, end - 7), end);
    rows.unshift({
      key: slice[0].date,
      label: `${dayLabel(slice[0].date)} – ${dayLabel(slice[slice.length - 1].date)}`,
      value: slice.reduce((sum, d) => sum + d.count, 0),
    });
  }
  return {
    rows,
    axis: {
      first: dayLabel(days[0].date),
      middle: dayLabel(days[Math.floor(days.length / 2)].date),
      last: dayLabel(days[days.length - 1].date),
    },
    period: 'week',
  };
}

function rangeLabel(days: number): string {
  return days === 1 ? 'Last Day' : `Last ${count(days)} Days`;
}

export function ActivityWidget({
  activity,
  requestedDays,
  onRequestDays,
}: {
  activity: ActivityFetch;
  requestedDays: number | undefined;
  onRequestDays: (days: number | undefined) => void;
}) {
  const summary = activity.status === 'data' ? activity.data : null;
  const trend = summary !== null ? activityTrend(summary) : null;
  return (
    <Widget
      id="stats-activity"
      title="Activity"
      icon={<History size={18} strokeWidth={2} aria-hidden="true" />}
      className="stats-w2"
      range={{
        label: 'Time Range',
        options: ACTIVITY_RANGES,
        value: String(requestedDays ?? 7),
        onChange: (value) => onRequestDays(value === '7' ? undefined : Number(value)),
      }}
      info={
        <p>
          Every recorded change to a record — an answer, a correction, a run, a proposal, an
          export — counted per UTC day. Open a record&rsquo;s Activity view for the changes
          themselves.
        </p>
      }
      headline={
        summary !== null ? (
          <div className="stats-headline-pair">
            <HeadlineFigure
              label={`Changes, ${rangeLabel(summary.window.days)}`}
              value={count(summary.totals.events_in_window)}
            />
            <HeadlineFigure label="Records Changed" value={count(summary.changed_records.total)} />
          </div>
        ) : null
      }
      footer={
        summary !== null ? (
          <span className="stats-note">
            {summary.scope.truncated
              ? `Covers the ${count(summary.scope.experiments_summarized)} most recently created of ${count(summary.scope.experiments_in_scope)} records. `
              : ''}
            Entries are not attributed to a person.
          </span>
        ) : undefined
      }
    >
      {activity.status === 'loading' && <LoadingPanel label="Loading the activity…" />}
      {activity.status === 'error' && (
        <WidgetUnavailable message="The activity could not be read." onRetry={activity.reload} />
      )}
      {summary !== null && trend !== null && (
        <StatsTrendChart
          caption={`Changes per ${trend.period}, ${rangeLabel(summary.window.days).toLowerCase()}`}
          captionHidden
          rows={trend.rows}
          axisLabels={trend.axis}
          unit="changes"
          periodHeader={trend.period === 'day' ? 'Day (UTC)' : 'Week (UTC)'}
        />
      )}
      {summary !== null && trend === null && (
        <p className="stats-note">No per-day breakdown was returned.</p>
      )}
      {summary !== null && summary.totals.unreadable_entries + summary.totals.events_with_unreadable_timestamp > 0 && (
        <p className="stats-note">
          {count(summary.totals.unreadable_entries + summary.totals.events_with_unreadable_timestamp)}{' '}
          stored entries could not be dated and are not charted.
        </p>
      )}
    </Widget>
  );
}

/* ---- Kinds of Change ---------------------------------------------------- */

const KINDS_SHOWN = 6;

export function ChangeKindsWidget({ activity }: { activity: ActivityFetch }) {
  const summary = activity.status === 'data' ? activity.data : null;
  const ranked = summary?.ranked_actions.slice(0, KINDS_SHOWN) ?? [];
  const more = summary === null ? 0 : summary.actions_with_events - ranked.length;
  return (
    <Widget
      id="stats-change-kinds"
      title="Kinds of Change"
      icon={<BarChartHorizontal size={18} strokeWidth={2} aria-hidden="true" />}
    >
      {activity.status === 'loading' && <LoadingPanel label="Loading the kinds of change…" />}
      {activity.status === 'error' && (
        <WidgetUnavailable message="The activity could not be read." onRetry={activity.reload} />
      )}
      {summary !== null && ranked.length === 0 && (
        <p className="stats-note">{`No changes in the ${rangeLabel(summary.window.days).toLowerCase()}.`}</p>
      )}
      {summary !== null && ranked.length > 0 && (
        <>
          <StatsBarChart
            caption={`Changes by kind, ${rangeLabel(summary.window.days).toLowerCase()}`}
            captionHidden
            rows={ranked.map((entry) => ({
              key: entry.name,
              label: humanizeActivityToken(entry.name),
              value: entry.count,
            }))}
            unit="changes"
            total={null}
            categoryHeader="Kind of Change"
          />
          {more > 0 && (
            <p className="stats-note">{more === 1 ? '1 more kind.' : `${count(more)} more kinds.`}</p>
          )}
        </>
      )}
    </Widget>
  );
}

/* ---- Workflow ----------------------------------------------------------- */

export function WorkflowWidget({ records }: { records: RecordsFetch }) {
  const list = records.status === 'data' ? records.data.records : null;
  return (
    <Widget
      id="stats-workflow"
      title="Workflow"
      icon={<Workflow size={18} strokeWidth={2} aria-hidden="true" />}
      info={<p>Each record is counted once, at its first unfinished step.</p>}
    >
      {records.status === 'loading' && <LoadingPanel label="Loading the workflow…" />}
      {records.status === 'error' && (
        <WidgetUnavailable message="The workflow could not be read." onRetry={records.reload} />
      )}
      {list !== null && list.length === 0 && <p className="stats-note">No records yet.</p>}
      {list !== null && list.length > 0 && (
        <StatsBarChart
          caption={`Records by current workflow step, out of ${count(list.length)}`}
          captionHidden
          rows={deriveWorkflowStages(list).map((stage) => ({
            key: stage.id,
            label: stage.label,
            value: stage.count,
          }))}
          unit="records"
          total={list.length}
          categoryHeader="Workflow Step"
        />
      )}
    </Widget>
  );
}

/* ---- Evidence Support --------------------------------------------------- */

function evidenceClassLabel(key: string): string {
  return key
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

export function EvidenceWidget({ records }: { records: RecordsFetch }) {
  const list = records.status === 'data' ? records.data.records : null;
  const evidence = list !== null && list.length > 0 ? deriveEvidenceTotals(list) : null;
  return (
    <Widget
      id="stats-evidence"
      title="Evidence Support"
      icon={<ShieldCheck size={18} strokeWidth={2} aria-hidden="true" />}
      info={
        <p>
          How each classified field is supported. This counts fields, not records, and is a
          separate signal from schema validation.
        </p>
      }
      headline={
        evidence !== null && evidence.totalFields > 0 ? (
          <HeadlineFigure label="Fields Classified" value={count(evidence.totalFields)} />
        ) : null
      }
    >
      {records.status === 'loading' && <LoadingPanel label="Loading the evidence counts…" />}
      {records.status === 'error' && (
        <WidgetUnavailable message="The evidence counts could not be read." onRetry={records.reload} />
      )}
      {list !== null && list.length === 0 && <p className="stats-note">No records yet.</p>}
      {evidence !== null && evidence.totalFields === 0 && (
        <p className="stats-note">No field has been classified yet.</p>
      )}
      {evidence !== null && evidence.totalFields > 0 && (
        <StatsStackedBar
          caption="Classified fields by evidence-support class"
          captionHidden
          rows={EVIDENCE_CLASSES.map((cls) => ({
            key: cls.key,
            label: evidenceClassLabel(cls.key),
            value: evidence[cls.field],
          }))}
          total={evidence.totalFields}
          unit="fields"
          categoryHeader="Evidence-Support Class"
        />
      )}
    </Widget>
  );
}

/* ---- Historical Imports ------------------------------------------------- */

export function ImportsWidget({ imports }: { imports: ImportsFetch }) {
  const steps = imports.status === 'data' ? deriveImportSteps(imports.data) : null;
  return (
    <Widget
      id="stats-imports"
      title="Historical Imports"
      icon={<Inbox size={18} strokeWidth={2} aria-hidden="true" />}
      info={<p>Each import session is counted once, at the furthest step it has reached.</p>}
      headline={
        steps !== null && steps.sessions !== null && steps.sessions > 0 ? (
          <HeadlineFigure label="Import Sessions" value={count(steps.sessions)} />
        ) : null
      }
      footer={<Link to={ROUTES.imports}>{LABELS.navImports}</Link>}
    >
      {imports.status === 'loading' && <LoadingPanel label="Loading the import sessions…" />}
      {/* Its only reader, so a dead source states itself here as the full alarm. */}
      {imports.status === 'error' && <BackendDown error={imports.error} onRetry={imports.reload} />}
      {steps !== null && steps.received === 0 && <p className="stats-note">No import sessions yet.</p>}
      {steps !== null && steps.received > 0 && (
        <>
          {steps.sessions !== null && steps.sessions !== steps.received && (
            <UnavailableNote>
              Showing {count(steps.received)} of {count(steps.sessions)} sessions.
            </UnavailableNote>
          )}
          <StatsBarChart
            caption={`Import sessions by furthest step, out of ${count(steps.received)}`}
            captionHidden
            rows={steps.rows.filter((row) => row.value > 0)}
            unit="sessions"
            total={steps.received}
            categoryHeader="Furthest Step"
          />
        </>
      )}
    </Widget>
  );
}

/* ---- the whole-workspace empty state ------------------------------------ */

/** Shown in place of the record widgets when the workspace holds no record. */
export function EmptyWorkspaceWidget() {
  return (
    <Widget
      id="stats-records"
      title="Records"
      icon={<LayoutList size={18} strokeWidth={2} aria-hidden="true" />}
      className="stats-w2"
    >
      <ChartEmpty title="No Records Yet">
        Charts appear here once the first experiment is created.
      </ChartEmpty>
      <p className="stats-actions">
        <Link to={ROUTES.experiments}>Go to My Experiments</Link>
      </p>
    </Widget>
  );
}

/* ---- the grid ----------------------------------------------------------- */

/**
 * Three columns on a wide screen, two on a laptop, one on a phone; a `stats-w2`
 * widget spans two. Rows are paired so a wide widget always sits beside a narrow
 * one: Records + Open Questions, Activity + Kinds of Change, then three narrow.
 *
 * An EMPTY workspace collapses the five record-derived widgets into one empty
 * state, because five widgets each saying "no records yet" is noise. Imports stay:
 * a session can exist before any experiment does.
 */
export function OverviewDashboard({
  records,
  activity,
  imports,
  activityDays,
  onActivityDays,
}: {
  records: RecordsFetch;
  activity: ActivityFetch;
  imports: ImportsFetch;
  activityDays: number | undefined;
  onActivityDays: (days: number | undefined) => void;
}) {
  const empty =
    records.status === 'data' && records.data.total === 0 && records.data.records.length === 0;
  return (
    <div className="stats-dashboard">
      {empty ? (
        <>
          <EmptyWorkspaceWidget />
          <ImportsWidget imports={imports} />
        </>
      ) : (
        <>
          <RecordsWidget records={records} />
          <OpenQuestionsWidget records={records} />
          <ActivityWidget
            activity={activity}
            requestedDays={activityDays}
            onRequestDays={onActivityDays}
          />
          <ChangeKindsWidget activity={activity} />
          <WorkflowWidget records={records} />
          <EvidenceWidget records={records} />
          <ImportsWidget imports={imports} />
        </>
      )}
    </div>
  );
}
