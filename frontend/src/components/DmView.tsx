"use client";

import { useEffect } from "react";
import { type DmMessage, dmMessages } from "@/lib/dm";
import { KIND_LABEL, longDate, moneyCompact, pct } from "@/lib/format";
import { type DemoState, setState } from "@/lib/store";
import { CashCard, weeksOfRunway } from "./CashCard";
import { BotAvatar } from "./slack/BotAvatar";
import { BotMessage, DayDivider } from "./slack/BotMessage";
import { Composer } from "./slack/Composer";

// The founder's direct message with the Cost Signals app: where runway detail goes when Settings
// routes it there. The channel keeps the dollars; this keeps the weeks.

function RunwayLines({ m }: { m: Extract<DmMessage, { kind: "runway" }> }) {
  const c = m.findings.cash;
  return (
    <div className="mt-1 max-w-3xl rounded-lg border border-slack-border border-l-4 border-l-[#b45309] bg-white px-4 py-3" data-testid="dm-runway">
      <div className="text-[13px] font-bold uppercase tracking-wide text-ink">Runway impact of today&apos;s alerts</div>
      {c?.runway_months != null && (
        <p className="mt-0.5 text-xs text-slack-muted">
          Runway {c.runway_months.toFixed(1)} months on {moneyCompact(c.total_cash, { sign: false, perMonth: false })} total cash at{" "}
          {moneyCompact(c.net_burn_monthly, { sign: false })} net burn. Weeks below assume the new rate holds.
        </p>
      )}
      <ul className="mt-2 space-y-1.5">
        {m.items.map((f) => (
          <li key={f.id} className="flex flex-wrap items-baseline gap-x-2 text-sm">
            <span className="font-semibold text-[#b45309]" data-testid="runway-weeks">
              {weeksOfRunway(f.runway_weeks_delta as number)}
            </span>
            <span className="font-bold">{f.vendor}</span>
            <span className="text-slack-muted">
              · {KIND_LABEL[f.kind]} · {moneyCompact(f.impact_monthly)} · {pct(f.impact_pct_of_spend, 1)} of spend
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11px] text-slack-muted">Sent here because runway is owner-level information (Settings → Runway framing).</p>
    </div>
  );
}

export function DmView({ state }: { state: DemoState }) {
  const messages = dmMessages(state);
  const count = messages.length;

  useEffect(() => {
    if (state.dmSeen !== count) setState({ dmSeen: count });
  }, [count, state.dmSeen]);

  let lastAsOf: string | null = null;
  return (
    <>
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-slack-border px-5">
        <div className="flex items-center gap-2 text-[17px] font-black">
          <BotAvatar />
          Cost Signals
          <span className="rounded bg-[#e8e8e8] px-1 py-px text-[10px] font-bold uppercase text-slack-muted">App</span>
        </div>
        <span className="text-[13px] text-slack-muted">Direct message · runway detail for {state.connections.runway.recipient}</span>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden pb-2">
        {count === 0 ? (
          <div className="px-5 pb-6 pt-10">
            <h2 className="text-xl font-black">Cost Signals</h2>
            <p className="mt-1 max-w-xl text-[15px] text-ink-soft">
              Runway detail lands here when Settings routes it to a direct message. Nothing yet: turn on Runway
              framing, keep &ldquo;Direct message to the founder&rdquo;, and load history.
            </p>
          </div>
        ) : (
          messages.map((m) => {
            const divider = m.asOf !== lastAsOf;
            lastAsOf = m.asOf;
            return (
              <div key={m.id}>
                {divider && <DayDivider label={longDate(m.asOf)} />}
                <BotMessage ts={m.ts} continued={false}>
                  {m.kind === "cash" ? (
                    <div className="mt-1 max-w-3xl rounded-lg border border-slack-border bg-white">
                      <CashCard findings={m.findings} runway={state.connections.runway} />
                    </div>
                  ) : (
                    <RunwayLines m={m} />
                  )}
                </BotMessage>
              </div>
            );
          })
        )}
      </div>
      <Composer />
    </>
  );
}
