import { KIND_LABEL, issueKey, longDate, money, moneyCompact, monthYear, pct, shortDate } from "@/lib/format";
import type { Finding, Findings, ReportText } from "@/lib/types";

const COLLAPSE_OVER = 5;

function byAbsImpactDesc(a: Finding, b: Finding): number {
  return Math.abs(b.impact_monthly) - Math.abs(a.impact_monthly);
}

function impactLabel(f: Finding): string {
  if (f.kind === "renewal") return moneyCompact(f.impact_monthly, { sign: false, perMonth: false });
  if (f.kind === "spike") return moneyCompact(f.impact_monthly, { perMonth: false });
  return moneyCompact(f.impact_monthly);
}

function fallbackText(f: Finding): string {
  return `${KIND_LABEL[f.kind]}: ${money(f.actual_monthly)} against ${money(f.baseline.expected_monthly)} expected.`;
}

function reportTitle(findings: Findings): string {
  const start = findings.window_start.slice(0, 7);
  const end = findings.window_end.slice(0, 7);
  if (start === end) return `Monthly report · ${monthYear(findings.window_end)}`;
  return `Report · ${monthYear(findings.window_start)} – ${monthYear(findings.window_end)}`;
}

function Item({ f, text, openSince }: { f: Finding; text: string; openSince: string | undefined }) {
  const decrease = f.impact_monthly < 0;
  return (
    <li className="flex gap-3 py-2">
      <div className={`w-24 shrink-0 text-right text-sm font-semibold tabular-nums ${decrease ? "text-emerald-700" : "text-ink"}`}>
        {impactLabel(f)}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-bold">{f.vendor}</span>
          <span className="text-xs text-slack-muted">
            {KIND_LABEL[f.kind]} · {pct(f.impact_pct_of_spend, 1, true)} of spend
          </span>
          {openSince && (
            <span className="rounded bg-amber-50 px-1.5 py-px text-[11px] font-medium text-amber-900">
              Open since {shortDate(openSince)}
            </span>
          )}
          {f.escalation_of && (
            <span className="rounded bg-amber-100 px-1.5 py-px text-[11px] font-medium text-amber-900">Escalated</span>
          )}
        </div>
        <p className="text-sm leading-relaxed text-ink-soft">{text}</p>
      </div>
    </li>
  );
}

export function ReportMessage({
  findings,
  report,
  openSince,
}: {
  findings: Findings;
  report: ReportText | null;
  /** finding id → window_end of the stage that first alerted on it */
  openSince: Map<string, string>;
}) {
  const textById = new Map<string, string>();
  if (report) {
    report.needs_attention.forEach((t) => textById.set(t.finding_id, t.text));
    Object.values(report.worth_knowing)
      .flat()
      .forEach((t) => textById.set(t.finding_id, t.text));
  }

  const items = findings.findings.filter((f) => f.route !== "ignore");
  const narratedAttention = new Set((report?.needs_attention ?? []).map((t) => t.finding_id));
  const isAttention = (f: Finding) =>
    f.route === "alert" || Boolean(f.escalation_of) || openSince.has(issueKey(f.id)) || narratedAttention.has(f.id);
  const attention = items.filter(isAttention).sort(byAbsImpactDesc);

  const groups = new Map<string, Finding[]>();
  items
    .filter((f) => !isAttention(f))
    .forEach((f) => {
      const list = groups.get(f.category) ?? [];
      list.push(f);
      groups.set(f.category, list);
    });
  const orderedGroups = [...groups.entries()]
    .map(([category, list]) => [category, list.sort(byAbsImpactDesc)] as const)
    .sort((a, b) => Math.abs(b[1][0].impact_monthly) - Math.abs(a[1][0].impact_monthly));

  return (
    <div className="mt-1 max-w-3xl overflow-hidden rounded-lg border border-slack-border bg-white">
      <div className="px-4 py-3">
        <div className="text-base font-bold">{reportTitle(findings)}</div>
        <div className="text-xs text-slack-muted">
          {longDate(findings.window_start)} – {longDate(findings.window_end)} · trailing spend{" "}
          {money(findings.trailing_monthly_spend)}/mo · {findings.headcount_proxy} cardholders
        </div>
        {report && <p className="mt-2 text-[15px] leading-snug">{report.intro}</p>}
      </div>

      <div className="border-t border-slack-border px-4 py-3">
        <h4 className="text-[13px] font-bold uppercase tracking-wide text-ink">Needs attention</h4>
        {attention.length === 0 ? (
          <p className="mt-1 text-sm text-slack-muted">Nothing needs attention.</p>
        ) : (
          <ul className="mt-1 divide-y divide-slack-border/60">
            {attention.map((f) => (
              <Item key={f.id} f={f} text={textById.get(f.id) ?? fallbackText(f)} openSince={openSince.get(issueKey(f.id))} />
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-slack-border px-4 py-3">
        <h4 className="text-[13px] font-bold uppercase tracking-wide text-ink">Worth knowing</h4>
        {orderedGroups.length === 0 ? (
          <p className="mt-1 text-sm text-slack-muted">Nothing else moved outside its normal range.</p>
        ) : (
          orderedGroups.map(([category, list]) => {
            const heading = (
              <span className="text-sm font-semibold text-ink-soft">
                {category}
                <span className="ml-1 font-normal text-slack-muted">
                  · {list.length} item{list.length === 1 ? "" : "s"}
                </span>
              </span>
            );
            const body = (
              <ul className="divide-y divide-slack-border/60">
                {list.map((f) => (
                  <Item key={f.id} f={f} text={textById.get(f.id) ?? fallbackText(f)} openSince={undefined} />
                ))}
              </ul>
            );
            return list.length > COLLAPSE_OVER ? (
              <details key={category} className="mt-2">
                <summary className="cursor-pointer select-none">{heading}</summary>
                {body}
              </details>
            ) : (
              <div key={category} className="mt-2">
                {heading}
                {body}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
