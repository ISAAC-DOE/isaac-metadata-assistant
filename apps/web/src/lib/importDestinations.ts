import { useCallback, useEffect, useState } from 'react';
import { api } from './api';
import { stripLifecycleSuffix } from './adapt';

/**
 * THE RECORDS AN IMPORT CAN BE SENT TO — one list, shared by every picker on the
 * Historical Import screen (the batch send, a single candidate, and a rule stored on
 * an experiment).
 *
 * Moved out of `HistoricalImport.tsx` on 2026-09-22 so the stage components can use
 * it without importing the screen. Its behaviour is unchanged: it LISTS the
 * workspace's experiments so one can be chosen instead of a typed ULID, and a failed
 * read is reported as `failed` rather than as an empty list — an empty picker with no
 * explanation would read as "you have no experiments", which is a different claim.
 */
export function useProposalDestinations() {
  const [rows, setRows] = useState<{ id: string; title: string }[] | null>(null);
  const [failed, setFailed] = useState(false);

  const reload = useCallback(async () => {
    try {
      const list = await api.listExperiments();
      setRows(
        (list.experiments ?? []).map((e) => ({
          id: e.id,
          title: stripLifecycleSuffix(e.title) || e.id,
        })),
      );
      setFailed(false);
    } catch {
      setRows(null);
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { rows, failed, reload };
}

export type ProposalDestinations = ReturnType<typeof useProposalDestinations>;
