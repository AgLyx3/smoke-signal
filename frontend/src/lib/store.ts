import { useSyncExternalStore } from "react";
import type { Config, CostType, Findings, NarrateResponse, OpenIssue, Stage } from "./types";

// Client state lives in localStorage under `smoke-signal:*` so a reload keeps the transcript.
// Every localStorage access is wrapped; a blocked or full store degrades to in-memory state.

const PREFIX = "smoke-signal:";

export type DemoStage = "idle" | Stage;
export type Reaction = "expected" | "investigating" | "not_useful";

export type ChannelMessage =
  | { id: string; ts: number; asOf: string; kind: "system"; text: string; tone: "info" | "error" }
  | { id: string; ts: number; asOf: string; kind: "alert"; stage: Stage; findingId: string }
  | { id: string; ts: number; asOf: string; kind: "report"; stage: Stage };

export type StageResult = { findings: Findings; narration: NarrateResponse };

/** An open issue plus the stage that raised it, so reruns of that same stage do not dedupe against it. */
export type OpenIssueRecord = OpenIssue & { stage: Stage };

export type ProviderId = "anthropic" | "openai";

/** Opt-in connections from Settings. Only a masked label is ever kept: the key itself is never
 *  written to storage (in production it would be encrypted server-side, read-only scope). */
export type ProviderConnection = { connected: boolean; label: string | null; connectedAt: string | null };

export type RunwayDelivery = "dm" | "channel";

export type Connections = {
  providers: Record<ProviderId, ProviderConnection>;
  runway: {
    enabled: boolean;
    delivery: RunwayDelivery;
    recipient: string;
    /** Months of net burn to keep in operating checking (assumption, editable). */
    bufferMonths: number;
    /** Assumed Rho Treasury yield (assumption, editable). */
    treasuryApy: number;
  };
};

export const DEFAULT_CONNECTIONS: Connections = {
  providers: {
    anthropic: { connected: false, label: null, connectedAt: null },
    openai: { connected: false, label: null, connectedAt: null },
  },
  // Runway is owner-level information, so the default destination is a DM to the founder.
  runway: { enabled: false, delivery: "dm", recipient: "Dana K.", bufferMonths: 3, treasuryApy: 0.038 },
};

/** One turn in the clarification thread under a finding. */
export type ThreadTurn = { role: "user" | "bot"; text: string; ts: number; source?: "claude" | "template" };

export type DemoState = {
  stage: DemoStage;
  config: Config | null;
  overrides: Record<string, CostType>;
  openIssues: OpenIssueRecord[];
  reactions: Record<string, Reaction>;
  messages: ChannelMessage[];
  results: Partial<Record<Stage, StageResult>>;
  pendingRerun: string | null;
  connections: Connections;
  threads: Record<string, ThreadTurn[]>;
  /** Which Slack surface is open: the channel, or the direct message with the Smoke Signal app. */
  view: "channel" | "dm";
  /** How many DM messages the founder has seen; the sidebar badge is the rest. */
  dmSeen: number;
  /** Answers to "what was this inflow?" by transaction id; only customer payments count as cash in. */
  inflowOverrides: Record<string, InflowKind>;
};

export type InflowKind = "customer" | "funding" | "refund" | "transfer" | "other";

const KEYS: Record<keyof DemoState, string> = {
  stage: `${PREFIX}stage`,
  config: `${PREFIX}config`,
  overrides: `${PREFIX}overrides`,
  openIssues: `${PREFIX}openIssues`,
  reactions: `${PREFIX}reactions`,
  messages: `${PREFIX}messages`,
  results: `${PREFIX}results`,
  pendingRerun: `${PREFIX}pendingRerun`,
  connections: `${PREFIX}connections`,
  threads: `${PREFIX}threads`,
  view: `${PREFIX}view`,
  dmSeen: `${PREFIX}dmSeen`,
  inflowOverrides: `${PREFIX}inflowOverrides`,
};

export const DEFAULT_STATE: DemoState = {
  stage: "idle",
  config: null,
  overrides: {},
  openIssues: [],
  reactions: {},
  messages: [],
  results: {},
  pendingRerun: null,
  connections: DEFAULT_CONNECTIONS,
  threads: {},
  view: "channel",
  dmSeen: 0,
  inflowOverrides: {},
};

function readKey<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

function writeKey(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage blocked or full: keep going in memory.
  }
}

function removeKey(key: string): void {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

function load(): DemoState {
  const state = { ...DEFAULT_STATE };
  (Object.keys(KEYS) as (keyof DemoState)[]).forEach((k) => {
    (state as Record<string, unknown>)[k] = readKey(KEYS[k], DEFAULT_STATE[k]);
  });
  return state;
}

let state: DemoState | null = null;
const listeners = new Set<() => void>();

export function getState(): DemoState {
  if (state === null) state = typeof window === "undefined" ? DEFAULT_STATE : load();
  return state;
}

export function setState(patch: Partial<DemoState>): void {
  const prev = getState();
  state = { ...prev, ...patch };
  (Object.keys(patch) as (keyof DemoState)[]).forEach((k) => writeKey(KEYS[k], state![k]));
  listeners.forEach((l) => l());
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getServerSnapshot(): DemoState {
  return DEFAULT_STATE;
}

export function useDemoState(): DemoState {
  return useSyncExternalStore(subscribe, getState, getServerSnapshot);
}

export function resetDemo(): void {
  Object.values(KEYS).forEach(removeKey);
  state = { ...DEFAULT_STATE };
  listeners.forEach((l) => l());
}

export function newId(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }
}
