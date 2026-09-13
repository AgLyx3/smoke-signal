import { cashMode, MIN_RUNWAY_WEEKS } from "@/components/CashCard";
import type { DemoState } from "./store";
import type { Finding, Findings, Stage } from "./types";

// The direct message from the Cost Signals app carries runway detail when Settings routes it
// there (owner-level information goes to the owner, not the channel). Messages are derived from
// the loaded stages, in channel order, so nothing is stored twice.

export type DmMessage =
  | { id: string; ts: number; asOf: string; stage: Stage; kind: "cash"; findings: Findings }
  | { id: string; ts: number; asOf: string; stage: Stage; kind: "runway"; findings: Findings; items: Finding[] };

export function runwayGoesToDm(state: DemoState): boolean {
  return state.connections.runway.enabled && state.connections.runway.delivery === "dm";
}

export function dmMessages(state: DemoState): DmMessage[] {
  if (!runwayGoesToDm(state)) return [];
  const runway = state.connections.runway;
  const out: DmMessage[] = [];
  const seen = new Set<Stage>();
  for (const m of state.messages) {
    if (m.kind === "system" || seen.has(m.stage)) continue;
    seen.add(m.stage);
    const result = state.results[m.stage];
    if (!result) continue;
    const findings = result.findings;
    if (m.kind === "report") {
      if (cashMode(findings, runway)) out.push({ id: `dm-cash-${m.stage}`, ts: m.ts, asOf: m.asOf, stage: m.stage, kind: "cash", findings });
    } else {
      const items = findings.findings.filter(
        (f) => f.route === "alert" && f.runway_weeks_delta != null && Math.abs(f.runway_weeks_delta) >= MIN_RUNWAY_WEEKS,
      );
      if (items.length) out.push({ id: `dm-runway-${m.stage}`, ts: m.ts, asOf: m.asOf, stage: m.stage, kind: "runway", findings, items });
    }
  }
  return out;
}

export function dmUnread(state: DemoState): number {
  return Math.max(dmMessages(state).length - state.dmSeen, 0);
}
