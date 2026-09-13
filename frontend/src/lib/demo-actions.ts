import { useSyncExternalStore } from "react";
import { ask, getDefaultConfig, narrate, runStage } from "./api";
import { longDate } from "./format";
import {
  type ChannelMessage,
  type InflowKind,
  type OpenIssueRecord,
  type StageResult,
  type ThreadTurn,
  getState,
  newId,
  setState,
} from "./store";
import { type Config, type CostType, type Findings, type OpenIssue, type RunRequest, type Stage, STAGES, stageIndex } from "./types";

// Orchestration for the presenter flow. Components call these; the store notifies them.

let busy = false;
const busyListeners = new Set<(b: boolean) => void>();

export function onBusy(l: (b: boolean) => void): () => void {
  busyListeners.add(l);
  return () => busyListeners.delete(l);
}

function setBusy(b: boolean): void {
  busy = b;
  busyListeners.forEach((l) => l(b));
}

export function isBusy(): boolean {
  return busy;
}

function subscribeBusy(cb: () => void): () => void {
  return onBusy(() => cb());
}

export function useBusy(): boolean {
  return useSyncExternalStore(subscribeBusy, isBusy, () => false);
}

export const STAGE_STEP: Record<Stage, { label: string; mode: "alerts" | "report" }> = {
  history: { label: "Load history", mode: "report" },
  "inject-1": { label: "New charges", mode: "alerts" },
  "inject-2": { label: "Month closes", mode: "report" },
};

export function nextStage(): Stage | null {
  const { stage } = getState();
  if (stage === "idle") return "history";
  const i = stageIndex(stage);
  return i + 1 < STAGES.length ? STAGES[i + 1] : null;
}

async function ensureConfig(): Promise<Config> {
  const { config } = getState();
  if (config) return config;
  const fresh = await getDefaultConfig();
  setState({ config: fresh });
  return fresh;
}

function overridesList(): { vendor: string; cost_type: CostType }[] {
  return Object.entries(getState().overrides).map(([vendor, cost_type]) => ({ vendor, cost_type }));
}

/** Open issues raised before `stage`; the stage's own issues must not dedupe its rerun. */
function openIssuesBefore(stage: Stage): OpenIssue[] {
  return getState()
    .openIssues.filter((o) => stageIndex(o.stage) < stageIndex(stage))
    .map(({ id, vendor, kind, impact_monthly }) => ({ id, vendor, kind, impact_monthly }));
}

function inflowOverridesList(): { id: string; kind: InflowKind }[] {
  return Object.entries(getState().inflowOverrides).map(([id, kind]) => ({ id, kind }));
}

async function buildRequest(stage: Stage): Promise<RunRequest> {
  return {
    stage,
    config: await ensureConfig(),
    overrides: overridesList(),
    open_issues: openIssuesBefore(stage),
    inflow_overrides: inflowOverridesList(),
  };
}

/** Answer to "what was this inflow?": only customer payments count as cash in, so net burn and
 *  runway are re-computed for every loaded stage. */
export async function answerInflow(id: string, kind: InflowKind): Promise<void> {
  setState({ inflowOverrides: { ...getState().inflowOverrides, [id]: kind } });
  await rerunAll(null);
}

function appendMessages(msgs: ChannelMessage[]): void {
  setState({ messages: [...getState().messages, ...msgs] });
}

export function postSystem(text: string, tone: "info" | "error" = "info"): void {
  const asOf = currentAsOf();
  appendMessages([{ id: newId(), ts: Date.now(), asOf, kind: "system", text, tone }]);
}

function currentAsOf(): string {
  const { stage, results } = getState();
  if (stage === "idle") return new Date().toISOString().slice(0, 10);
  return results[stage]?.findings.window_end ?? new Date().toISOString().slice(0, 10);
}

function recordOpenIssues(findings: Findings): void {
  const existing = getState().openIssues;
  const fresh: OpenIssueRecord[] = findings.findings
    .filter((f) => f.route === "alert")
    .filter((f) => !existing.some((o) => o.id === f.id))
    .map((f) => ({ id: f.id, vendor: f.vendor, kind: f.kind, impact_monthly: f.impact_monthly, stage: findings.stage }));
  if (fresh.length) setState({ openIssues: [...existing, ...fresh] });
}

function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/** Presenter step: run the stage, narrate it, post to the channel. */
export async function runStep(stage: Stage): Promise<void> {
  if (busy) return;
  setBusy(true);
  try {
    const req = await buildRequest(stage);
    const findings = await runStage(req);
    const narration = await narrate({ findings, mode: STAGE_STEP[stage].mode, open_issues: openIssuesBefore(stage) });
    const result: StageResult = { findings, narration };
    const asOf = findings.window_end;
    const ts = Date.now();

    const msgs: ChannelMessage[] = [];
    if (STAGE_STEP[stage].mode === "alerts") {
      const alerting = findings.findings.filter((f) => f.route === "alert");
      if (alerting.length === 0) {
        msgs.push({ id: newId(), ts, asOf, kind: "system", tone: "info", text: `New charges through ${longDate(asOf)} evaluated: nothing crossed an alert threshold.` });
      }
      alerting.forEach((f, i) => msgs.push({ id: newId(), ts: ts + i, asOf, kind: "alert", stage, findingId: f.id }));
      recordOpenIssues(findings);
    } else {
      msgs.push({ id: newId(), ts, asOf, kind: "report", stage });
    }

    setState({
      stage,
      results: { ...getState().results, [stage]: result },
      messages: [...getState().messages, ...msgs],
    });
  } catch (e) {
    postSystem(`Couldn't run "${STAGE_STEP[stage].label}": ${errorText(e)}`, "error");
  } finally {
    setBusy(false);
  }
}

/** Re-run detection for every loaded stage with the current config and overrides.
 *  Narration text is kept; cards and reports re-derive their facts from the new Findings. */
export async function rerunAll(systemLine: string | null): Promise<void> {
  if (busy) return;
  const loaded = STAGES.filter((s) => getState().results[s]);
  if (loaded.length === 0) {
    if (systemLine) postSystem(systemLine);
    return;
  }
  setBusy(true);
  try {
    for (const stage of loaded) {
      const req = await buildRequest(stage);
      const findings = await runStage(req);
      const prev = getState().results[stage];
      if (!prev) continue;
      setState({ results: { ...getState().results, [stage]: { findings, narration: prev.narration } } });
      if (STAGE_STEP[stage].mode === "alerts") recordOpenIssues(findings);
    }
    if (systemLine) postSystem(systemLine);
  } catch (e) {
    postSystem(`Re-evaluation failed: ${errorText(e)}`, "error");
  } finally {
    setBusy(false);
  }
}

/** Answer to the inline cost-type question on an alert card. */
export async function answerAsk(vendor: string, costType: CostType): Promise<void> {
  setState({ overrides: { ...getState().overrides, [vendor]: costType } });
  await rerunAll(null);
}

export function setReaction(findingId: string, reaction: "expected" | "investigating" | "not_useful"): void {
  const reactions = { ...getState().reactions };
  if (reactions[findingId] === reaction) delete reactions[findingId];
  else reactions[findingId] = reaction;
  setState({ reactions });
}

/** Settings → Save. The channel picks up `pendingRerun` on mount and re-evaluates. */
export function saveSettings(config: Config, overrides: Record<string, CostType>): void {
  setState({ config, overrides, pendingRerun: "Thresholds updated — re-evaluated" });
}

export async function consumePendingRerun(): Promise<void> {
  const { pendingRerun } = getState();
  if (!pendingRerun) return;
  setState({ pendingRerun: null });
  await rerunAll(pendingRerun);
}

export async function loadConfigForSettings(): Promise<Config> {
  return ensureConfig();
}

// --- clarification threads -------------------------------------------------------------------

const threadBusy = new Set<string>();
const threadListeners = new Set<() => void>();

function setThreadBusy(findingId: string, on: boolean): void {
  if (on) threadBusy.add(findingId);
  else threadBusy.delete(findingId);
  threadListeners.forEach((l) => l());
}

function subscribeThreadBusy(cb: () => void): () => void {
  threadListeners.add(cb);
  return () => threadListeners.delete(cb);
}

export function useThreadBusy(findingId: string | null): boolean {
  return useSyncExternalStore(
    subscribeThreadBusy,
    () => (findingId ? threadBusy.has(findingId) : false),
    () => false,
  );
}

function appendTurn(findingId: string, turn: ThreadTurn): void {
  const threads = getState().threads;
  setState({ threads: { ...threads, [findingId]: [...(threads[findingId] ?? []), turn] } });
}

/** Ask a clarifying question under a finding. The answer is grounded in that finding's evidence
 *  pack server-side; on any failure the server returns a template answer, never an error text. */
export async function askInThread(stage: Stage, findingId: string, question: string): Promise<void> {
  const q = question.trim();
  if (!q || threadBusy.has(findingId)) return;
  const history = (getState().threads[findingId] ?? []).map(({ role, text }) => ({ role, text }));
  appendTurn(findingId, { role: "user", text: q, ts: Date.now() });
  setThreadBusy(findingId, true);
  try {
    const res = await ask({
      stage,
      finding_id: findingId,
      question: q,
      thread: history,
      config: await ensureConfig(),
      overrides: overridesList(),
      open_issues: openIssuesBefore(stage),
    });
    appendTurn(findingId, { role: "bot", text: res.answer, ts: Date.now(), source: res.source });
  } catch (e) {
    appendTurn(findingId, { role: "bot", text: `I couldn't answer that right now: ${errorText(e)}`, ts: Date.now(), source: "template" });
  } finally {
    setThreadBusy(findingId, false);
  }
}
