import type { Confidence, CostType, CostTypeSource, Driver, Kind } from "./types";

const MINUS = "−";

/** `$10,000`, `-$1,440`. Whole dollars. */
export function money(n: number): string {
  const abs = Math.round(Math.abs(n)).toLocaleString("en-US");
  return n < 0 ? `-$${abs}` : `$${abs}`;
}

/** `+$10.0K/mo`, `−$1.4K/mo`, `+$660/mo`. `perMonth: false` drops the suffix. */
export function moneyCompact(
  n: number,
  opts: { sign?: boolean; perMonth?: boolean } = {},
): string {
  const { sign = true, perMonth = true } = opts;
  const abs = Math.abs(n);
  const body =
    abs >= 1_000_000
      ? `$${(abs / 1_000_000).toFixed(1)}M`
      : abs >= 1_000
        ? `$${(abs / 1_000).toFixed(1)}K`
        : `$${Math.round(abs)}`;
  const prefix = n < 0 ? MINUS : sign && n > 0 ? "+" : "";
  return `${prefix}${body}${perMonth ? "/mo" : ""}`;
}

/** Fraction → percent string. `pct(0.02)` → `2%`, `pct(0.0199, 1)` → `2.0%`. */
export function pct(frac: number, digits = 0, sign = false): string {
  const v = Math.abs(frac) * 100;
  const rounded = v.toFixed(digits);
  // A real but tiny share reads as "<0.1%", never as "0.0%".
  const tiny = v > 0 && Number(rounded) === 0;
  const body = tiny ? `<${(1 / 10 ** digits).toFixed(digits)}%` : `${rounded}%`;
  const prefix = frac < 0 ? MINUS : sign && frac > 0 && !tiny ? "+" : "";
  return `${prefix}${body}`;
}

/** Finding ids are `<vendor-slug>:<kind>:<as-of date>`; the same problem seen at a later stage
 *  gets a new date, so open issues are matched on the first two segments. */
export function issueKey(findingId: string): string {
  return findingId.split(":").slice(0, 2).join(":");
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function parseISODate(iso: string): { y: number; m: number; d: number } {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return { y, m, d };
}

/** `2026-09-05` → `Sep 5`. */
export function shortDate(iso: string): string {
  const { m, d } = parseISODate(iso);
  return `${MONTHS[m - 1]} ${d}`;
}

/** `2026-09-05` → `Sep 5, 2026`. */
export function longDate(iso: string): string {
  const { y, m, d } = parseISODate(iso);
  return `${MONTHS[m - 1]} ${d}, ${y}`;
}

/** `2026-09-05` → `Sep 2026`. */
export function monthYear(iso: string): string {
  const { y, m } = parseISODate(iso);
  return `${MONTHS[m - 1]} ${y}`;
}

/** Epoch ms → `9:41 AM`. */
export function clockTime(ts: number): string {
  return new Date(ts).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

export const COST_TYPE_LABEL: Record<CostType, string> = {
  usage: "Scales with usage",
  fixed: "Fixed price",
  headcount: "Per seat",
  annual: "Annual",
  payroll: "Payroll",
};

/** Used in the ask sentence: "We're treating X as <phrase>. Right?" */
export const COST_TYPE_PHRASE: Record<CostType, string> = {
  usage: "a cost that scales with usage",
  fixed: "a fixed monthly cost",
  headcount: "a per-seat cost",
  annual: "an annual contract",
  payroll: "payroll",
};

/** Short button labels for the ask: "No, it's fixed". */
export const COST_TYPE_SHORT: Record<CostType, string> = {
  usage: "usage-based",
  fixed: "fixed",
  headcount: "per-seat",
  annual: "annual",
  payroll: "payroll",
};

export const SOURCE_LABEL: Record<CostTypeSource, string> = {
  taxonomy: "Taxonomy",
  llm: "Inferred (LLM)",
  user: "Confirmed by you",
  default: "Unclassified (default)",
};

export const KIND_LABEL: Record<Kind, string> = {
  growth_break: "Off its trend",
  price_change: "Price change",
  new_vendor: "New recurring vendor",
  stopped: "Charge stopped",
  per_head: "Cost per head up",
  renewal: "Renewal coming up",
  spike: "One-off",
};

export const DRIVER_LABEL: Record<Driver, string> = {
  price: "Price",
  volume: "Volume",
  new: "New spend",
  missing: "Missing charge",
  who: "Headcount",
};

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  high: "High",
  medium: "Med",
  low: "Low",
};
