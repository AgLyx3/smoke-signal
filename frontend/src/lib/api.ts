import { MOCK_DELAY_MS, USE_MOCK } from "./data-source";
import { MOCK_DEFAULT_CONFIG, mockNarrate, mockRun } from "./mock";
import type { components } from "./api-types";
import type { Config, Findings, NarrateRequest, NarrateResponse, RunRequest } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${init?.method ?? "GET"} ${path} → ${res.status}: ${body || res.statusText}`);
  }
  return (await res.json()) as T;
}

function post<TReq, TRes>(path: string, body: TReq): Promise<TRes> {
  return request<TRes>(path, { method: "POST", body: JSON.stringify(body) });
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function runStage(req: RunRequest): Promise<Findings> {
  if (USE_MOCK) {
    await delay(MOCK_DELAY_MS);
    return mockRun(req);
  }
  return post<RunRequest, Findings>("/api/run", req);
}

export async function narrate(req: NarrateRequest): Promise<NarrateResponse> {
  if (USE_MOCK) {
    await delay(MOCK_DELAY_MS);
    return mockNarrate(req);
  }
  return post<NarrateRequest, NarrateResponse>("/api/narrate", req);
}

export type AskRequest = components["schemas"]["AskRequest"];
export type AskResponse = components["schemas"]["AskResponse"];

export async function ask(req: AskRequest): Promise<AskResponse> {
  if (USE_MOCK) {
    await delay(MOCK_DELAY_MS);
    return { answer: `Mock answer to "${req.question}".`, source: "template", evidence_used: [] };
  }
  return post<AskRequest, AskResponse>("/api/ask", req);
}

export async function getDefaultConfig(): Promise<Config> {
  if (USE_MOCK) {
    await delay(MOCK_DELAY_MS / 4);
    return structuredClone(MOCK_DEFAULT_CONFIG);
  }
  return request<Config>("/api/config/default");
}
