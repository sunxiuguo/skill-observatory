import type { Job, ObservatoryState, Review, Run, Skill } from "./types.ts";

export function byCreatedDesc<T extends { created_at?: string }>(a: T, b: T): number {
  return (b.created_at ?? "").localeCompare(a.created_at ?? "");
}

export function reviewsByRun(state: ObservatoryState): Map<string, Review> {
  const map = new Map<string, Review>();
  for (const r of [...state.reviews].sort(byCreatedDesc)) map.set(r.run_id, r);
  return map;
}

export function jobsByRun(state: ObservatoryState): Map<string, Job> {
  const map = new Map<string, Job>();
  for (const j of state.jobs) {
    if (j.run_id) map.set(j.run_id, j);
  }
  return map;
}

export function skillById(state: ObservatoryState): Map<string, Skill> {
  return new Map(state.skills.map((s) => [s.id, s]));
}

export type RunBucket = "ready" | "running" | "held" | "reviewed";

export function runBucket(run: Run, review: Review | undefined, job: Job | undefined): RunBucket {
  if (job?.status === "hold" || (review?.decision ?? "").toUpperCase() === "HOLD") return "held";
  if (review?.status==='reviewed') return 'reviewed';
  if (job && ["running", "queued", "waiting"].includes(job.status)) return "running";
  if (run.status === "ready") return "ready";
  if (["dev_evaluating", "final_evaluating"].includes(run.status)) return "running";
  if (run.status === "evidence_pending") return "held";
  // Triaged with no terminal review is a waiting queue item → ready for a human.
  if (run.status === "triaged") return "ready";
  return "ready";
}

export function isTerminalRun(run: Run, review: Review | undefined): boolean {
  return run.status === "reviewed" || (review !== undefined && review.status === "reviewed");
}

export function sortRuns(runs: Run[]): Run[] {
  return [...runs].sort(byCreatedDesc);
}

export function matchesQuery(haystacks: (string | null | undefined)[], q: string): boolean {
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  return haystacks.some((h) => h?.toLowerCase().includes(needle));
}
