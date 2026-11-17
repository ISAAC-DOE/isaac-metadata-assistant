/**
 * DEVELOPER TOOLS FLAG (2026-11-16, owner direction: the scientist UI keeps only what a
 * scientist uses).
 *
 * Project Memory (`/memory`, a graph of this repository's own docs), Statistics → Build &
 * Verification and Settings → Advanced (the Endpoint Explorer and its related-tools links)
 * are developer surfaces. They are not deleted: a build started with
 * `VITE_ISAAC_DEV_TOOLS=1` shows them exactly as before. Without the flag, which is every
 * hosted build, they are not offered, and their old addresses land somewhere sensible
 * (`/memory` → My Experiments, `?tab=build` → Overview, `?tab=advanced|explorer` → Overview).
 *
 * Read at call time, not at module load, so a test can turn it on with
 * `vi.stubEnv('VITE_ISAAC_DEV_TOOLS', '1')`.
 */
export const DEV_TOOLS_ENV = 'VITE_ISAAC_DEV_TOOLS';

export function devToolsEnabled(): boolean {
  return (import.meta.env.VITE_ISAAC_DEV_TOOLS as string | undefined) === '1';
}
