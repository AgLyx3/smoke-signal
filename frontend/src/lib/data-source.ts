// Integration flips this to `false` once the FastAPI service is wired up behind `/api`.
// While `true`, `api.ts` serves `mock.ts` with an artificial delay so loading states are visible.
export const USE_MOCK = true;

export const MOCK_DELAY_MS = 400;
