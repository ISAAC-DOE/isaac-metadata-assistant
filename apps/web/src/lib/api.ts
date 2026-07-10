/*
 * Typed client signatures for the ISAAC UI.
 *
 * THIS TASK: every method returns committed synthetic mock data (lib/mock.ts),
 * synchronously — the frontend is a static skeleton. A later task rewires these
 * bodies to `fetch` the FastAPI backend (apps/api) and makes them async; the
 * return TYPES already mirror the Task 1 serializations, so callers barely change.
 *
 * The client holds NO validation/coverage/warning logic — those are read from
 * the core via the API (thin-client principle, react-build-notes.md).
 */

import type {
  Artifact,
  CompletionAnswer,
  EvidenceTrailEntry,
  ExperimentDetail,
  GraphStatus,
  PendingBlocker,
  QueueGroup,
  RunnerStage,
  Signals,
  SourcePreview,
} from './types';
import * as mock from './mock';

export const api = {
  // S1
  listExperiments(): QueueGroup[] {
    return mock.getQueueGroups();
  },

  // record surfaces
  getExperiment(id: string): ExperimentDetail {
    return mock.getExperimentDetail(id);
  },

  // S4
  getPending(): PendingBlocker[] {
    return mock.getPendingBlockers();
  },
  getCompletionAnswers(): CompletionAnswer[] {
    return mock.getCompletionAnswers();
  },

  // S5
  getEvidenceTrail(): EvidenceTrailEntry[] {
    return mock.getEvidenceTrail();
  },
  getSourcePreview(): SourcePreview {
    return mock.getSourcePreview();
  },

  // S6
  getSignals(): Signals {
    return mock.getSignals();
  },
  getArtifacts(): Artifact[] {
    return mock.getArtifacts();
  },

  // S2
  getRunnerStages(): RunnerStage[] {
    return mock.getRunnerStages();
  },

  // memory (advisory only; never gates)
  getGraphStatus(): GraphStatus {
    return mock.getGraphStatus();
  },
} as const;

export type IsaacApi = typeof api;
