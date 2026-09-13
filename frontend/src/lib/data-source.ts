// `false`: the FastAPI service behind `/api` (run with `vercel dev -L` locally).
// `true`: `api.ts` serves `mock.ts` with an artificial delay, for UI work without the backend.
export const USE_MOCK = false;

export const MOCK_DELAY_MS = 400;
