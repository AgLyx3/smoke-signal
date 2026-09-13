import { longDate, money, moneyCompact, pct } from "@/lib/format";
import type { Connections } from "@/lib/store";
import type { Findings } from "@/lib/types";

// The CFO line the bank can say without asking anyone: runway from both Rho accounts, and what
// the operating balance allows. Arithmetic only; the buffer and yield are stated assumptions
// the founder can change in Settings.

export type RunwayPrefs = Connections["runway"];

export function runwayDeliveryLabel(r: RunwayPrefs): string {
  return r.delivery === "dm" ? `Runway detail → DM to ${r.recipient}` : "Runway detail → #spend-signals";
}

export function weeksOfRunway(delta: number): string {
  const abs = Math.abs(delta);
  const w = abs < 10 ? abs.toFixed(1) : Math.round(abs).toString();
  return delta >= 0 ? `≈ ${w} week${w === "1.0" ? "" : "s"} of runway` : `≈ ${w} week${w === "1.0" ? "" : "s"} of runway back`;
}

/** Runway framing on an alert only when it is at least this many weeks; smaller deltas stay
 *  dollars-only so the phrase keeps its weight. */
export const MIN_RUNWAY_WEEKS = 1.0;

/** The treasury paragraph repeats only when there is news: a buffer shortfall, or idle cash above
 *  the buffer worth at least this many months of net burn. Otherwise a report carries one line. */
export const TREASURY_NEWS_MONTHS = 2.0;

export type CashMode = "full" | "status";

export function cashMode(findings: Findings, runway: RunwayPrefs): CashMode | null {
  const c = findings.cash;
  if (!c || c.runway_months == null || c.net_burn_monthly <= 0) return null;
  if (findings.period?.kind === "first_run") return "full"; // orientation, once
  const buffer = runway.bufferMonths ?? c.buffer_months;
  const recommended = buffer * c.net_burn_monthly;
  const sweep = Math.max(c.operating_balance - recommended, 0);
  const shortfall = Math.max(recommended - c.operating_balance, 0);
  if (shortfall > 0 || sweep / c.net_burn_monthly >= TREASURY_NEWS_MONTHS) return "full";
  return "status";
}

export function CashCard({ findings, runway }: { findings: Findings; runway: RunwayPrefs }) {
  const c = findings.cash;
  const mode = cashMode(findings, runway);
  if (!c || c.runway_months == null || !mode) return null;
  const buffer = runway.bufferMonths ?? c.buffer_months;
  const apy = runway.treasuryApy ?? c.treasury_apy;
  const recommended = buffer * c.net_burn_monthly;
  const sweep = Math.max(c.operating_balance - recommended, 0);
  const shortfall = Math.max(recommended - c.operating_balance, 0);
  const upside = (sweep * apy) / 12;

  if (mode === "status") {
    return (
      <div className="border-t border-slack-border px-4 py-2 text-sm" data-testid="cash-position">
        <span className="text-[11px] font-bold uppercase tracking-wide text-ink">Runway</span>{" "}
        <span className="font-bold tabular-nums">{c.runway_months.toFixed(1)} months</span>
        <span className="text-slack-muted">
          {" "}
          · total cash {moneyCompact(c.total_cash, { sign: false, perMonth: false })} · net burn{" "}
          {moneyCompact(c.net_burn_monthly, { sign: false })} · operating covers{" "}
          {(c.operating_balance / c.net_burn_monthly).toFixed(1)} months, within the {buffer}-month buffer plan ·{" "}
          {runwayDeliveryLabel(runway)}
        </span>
      </div>
    );
  }

  return (
    <div className="border-t border-slack-border px-4 py-3" data-testid="cash-position">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <h4 className="text-[13px] font-bold uppercase tracking-wide text-ink">Cash position</h4>
        <span className="text-[11px] text-slack-muted">
          as of {longDate(c.as_of)} · {runwayDeliveryLabel(runway)}
        </span>
      </div>
      <div className="mt-1 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm">
        <span>
          <span className="text-[11px] text-slack-muted">Runway</span>{" "}
          <span className="text-base font-bold tabular-nums">{c.runway_months.toFixed(1)} months</span>
        </span>
        <span className="tabular-nums">
          <span className="text-[11px] text-slack-muted">Total cash</span> {moneyCompact(c.total_cash, { sign: false, perMonth: false })}
          <span className="text-slack-muted">
            {" "}
            = operating {moneyCompact(c.operating_balance, { sign: false, perMonth: false })} + treasury{" "}
            {moneyCompact(c.treasury_balance, { sign: false, perMonth: false })}
          </span>
        </span>
        <span className="tabular-nums">
          <span className="text-[11px] text-slack-muted">Net burn</span> {moneyCompact(c.net_burn_monthly, { sign: false })}
          <span className="text-slack-muted">
            {" "}
            (spend {moneyCompact(findings.trailing_monthly_spend, { sign: false })} − inflows{" "}
            {moneyCompact(c.monthly_inflows, { sign: false })})
          </span>
        </span>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-ink-soft">
        Operating checking covers <span className="font-medium text-ink">{(c.operating_balance / c.net_burn_monthly).toFixed(1)} months</span> of
        net burn.{" "}
        {sweep > 0 ? (
          <>
            Keeping a {buffer}-month buffer ({money(recommended)}), about{" "}
            <span className="font-medium text-ink">{moneyCompact(sweep, { sign: false, perMonth: false })}</span> could sit in Rho Treasury
            instead and earn <span className="font-medium text-ink">≈ {money(Math.round(upside))}/mo</span> at {pct(apy, 1)} APY, with a
            reverse sweep covering payroll days.
          </>
        ) : shortfall > 0 ? (
          <>
            A {buffer}-month buffer is {money(recommended)}; a{" "}
            <span className="font-medium text-ink">{moneyCompact(shortfall, { sign: false, perMonth: false })}</span> top-up from treasury would restore it.
          </>
        ) : (
          <>That matches the {buffer}-month buffer.</>
        )}
      </p>
      <p className="mt-1 text-[11px] text-slack-muted">
        Balances from Rho accounts; inflows are the trailing 3-month average of settled credits. Buffer and yield are assumptions,
        editable in Settings.
      </p>
    </div>
  );
}
