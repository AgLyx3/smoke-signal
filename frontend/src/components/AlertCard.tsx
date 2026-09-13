import Link from "next/link";
import type { ReactNode } from "react";
import {
  CONFIDENCE_LABEL,
  COST_TYPE_LABEL,
  COST_TYPE_PHRASE,
  COST_TYPE_SHORT,
  DRIVER_LABEL,
  KIND_LABEL,
  SOURCE_LABEL,
  money,
  moneyCompact,
  pct,
} from "@/lib/format";
import type { Reaction } from "@/lib/store";
import type { AlertText, Confidence, CostType, Finding } from "@/lib/types";

const CONFIDENCE_STYLE: Record<Confidence, string> = {
  high: "border-emerald-200 bg-emerald-50 text-emerald-800",
  medium: "border-amber-200 bg-amber-50 text-amber-800",
  low: "border-gray-300 bg-gray-50 text-gray-700",
};

const REACTIONS: { key: Reaction; emoji: string; label: string }[] = [
  { key: "expected", emoji: "👀", label: "expected" },
  { key: "investigating", emoji: "🔍", label: "investigating" },
  { key: "not_useful", emoji: "👎", label: "not useful" },
];

const ASKABLE: CostType[] = ["usage", "fixed", "headcount"];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="border-t border-slack-border px-4 py-3">
      <div className="mb-1 text-[11px] font-bold uppercase tracking-wide text-slack-muted">{title}</div>
      {children}
    </div>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] text-slack-muted">{label}</dt>
      <dd className="text-sm font-medium tabular-nums">{children}</dd>
    </div>
  );
}

function movementFacts(f: Finding, headcount: number): { label: string; value: string }[] {
  const b = f.baseline;
  const facts: { label: string; value: string }[] = [];
  if (f.kind === "new_vendor") {
    facts.push({ label: "Actual vs expected", value: `${money(f.actual_monthly)} vs no baseline` });
    facts.push({ label: "Observations", value: `${b.n_obs} charges` });
  } else {
    facts.push({ label: "Actual vs expected", value: `${money(f.actual_monthly)} vs ${money(b.expected_monthly)}` });
  }
  if (f.kind === "growth_break" && b.growth_pct != null && b.expected_monthly > 0) {
    const now = (1 + b.growth_pct) * (f.actual_monthly / b.expected_monthly) - 1;
    facts.push({ label: "Growth", value: `was ${pct(b.growth_pct)}/mo → now ${pct(now, 0, true)} this month` });
  }
  if (f.kind === "price_change" && b.last_price != null && b.last_price > 0) {
    facts.push({
      label: "Price",
      value: `${money(b.last_price)} → ${money(f.actual_monthly)} (${pct(f.actual_monthly / b.last_price - 1, 0, true)})`,
    });
  }
  if (f.kind === "per_head" && b.cost_per_head != null && headcount > 0) {
    facts.push({ label: "Per head", value: `${money(b.cost_per_head)} → ${money(f.actual_monthly / headcount)}` });
  }
  return facts;
}

export function AlertCard({
  finding,
  text,
  headcount,
  reaction,
  override,
  busy,
  demoted,
  onReact,
  onAnswer,
}: {
  finding: Finding;
  text: AlertText | undefined;
  headcount: number;
  reaction: Reaction | undefined;
  override: CostType | undefined;
  busy: boolean;
  demoted: boolean;
  onReact: (r: Reaction) => void;
  onAnswer: (costType: CostType) => void;
}) {
  const f = finding;
  const inferred = f.cost_type_source === "llm";
  const askOpen = f.ask_cost_type && !override;
  const others = ASKABLE.filter((c) => c !== f.cost_type);

  return (
    <div className="mt-1 max-w-3xl overflow-hidden rounded-lg border border-slack-border border-l-4 border-l-amber-500 bg-white">
      {demoted && (
        <div className="bg-amber-50 px-4 py-1.5 text-xs text-amber-900">
          No longer meets the alert threshold at the current settings; it will appear in the report instead.
        </div>
      )}

      <div className="px-4 py-3">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-base font-bold">{f.vendor}</span>
          <span className="text-base font-bold tabular-nums">{moneyCompact(f.impact_monthly)}</span>
          <span className="text-sm text-slack-muted">· {pct(f.impact_pct_of_spend, 1)} of monthly spend</span>
        </div>
        {text && <p className="mt-1 text-[15px] leading-snug">{text.headline}</p>}
      </div>

      <Section title="What moved">
        {text && <p className="text-sm leading-relaxed text-ink-soft">{text.what_moved}</p>}
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 md:grid-cols-4">
          <Fact label="Vendor">
            {f.vendor} <span className="font-normal text-slack-muted">· {f.category}</span>
          </Fact>
          <Fact label="Kind">{KIND_LABEL[f.kind]}</Fact>
          {movementFacts(f, headcount).map((m) => (
            <Fact key={m.label} label={m.label}>
              {m.value}
            </Fact>
          ))}
        </dl>
      </Section>

      <Section title="Why">
        {text && <p className="text-sm leading-relaxed text-ink-soft">{text.why}</p>}
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {f.drivers.map((d) => (
            <span
              key={d.driver}
              className="rounded-full border border-slack-border bg-slack-hover px-2 py-0.5 text-xs font-medium"
            >
              {DRIVER_LABEL[d.driver]} {pct(d.share)}
            </span>
          ))}
          <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${CONFIDENCE_STYLE[f.confidence]}`}>
            {CONFIDENCE_LABEL[f.confidence]} confidence
          </span>
        </div>
      </Section>

      <div className="flex flex-wrap items-center gap-2 border-t border-slack-border px-4 py-2 text-xs">
        <span className="inline-flex items-center gap-1 rounded border border-slack-border px-2 py-0.5 font-medium">
          {COST_TYPE_LABEL[f.cost_type]}
          {f.cost_type_source !== "taxonomy" && (
            <span className="group/tip relative inline-flex">
              <span
                tabIndex={0}
                title={`cost_type_source: ${f.cost_type_source}`}
                className={`ml-1 cursor-help rounded px-1 text-[10px] font-bold uppercase ${
                  inferred ? "bg-amber-100 text-amber-900" : "bg-emerald-100 text-emerald-900"
                }`}
              >
                {inferred ? "inferred" : "confirmed"}
              </span>
              <span
                role="tooltip"
                className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden -translate-x-1/2 whitespace-nowrap rounded bg-ink px-2 py-1 font-mono text-[11px] text-white group-hover/tip:block group-focus-within/tip:block"
              >
                cost_type_source: {f.cost_type_source} · {SOURCE_LABEL[f.cost_type_source]}
              </span>
            </span>
          )}
        </span>
        {f.cardholders.length > 0 && (
          <span className="text-slack-muted">
            Cardholder{f.cardholders.length > 1 ? "s" : ""}: {f.cardholders.join(", ")}
          </span>
        )}
      </div>

      {askOpen && (
        <div className="mx-4 mb-3 rounded-md border border-slack-border bg-slack-hover px-3 py-2">
          <p className="text-sm font-medium">
            We&apos;re treating {f.vendor} as {COST_TYPE_PHRASE[f.cost_type]}. Right?
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => onAnswer(f.cost_type)}
              className="rounded bg-slack-green px-3 py-1 text-sm font-bold text-white hover:bg-[#148567] disabled:opacity-60"
            >
              Yes
            </button>
            {others.map((c) => (
              <button
                key={c}
                type="button"
                disabled={busy}
                onClick={() => onAnswer(c)}
                className="rounded border border-[#bbb] bg-white px-3 py-1 text-sm font-bold hover:bg-[#f0f0f0] disabled:opacity-60"
              >
                No, it&apos;s {COST_TYPE_SHORT[c]}
              </button>
            ))}
            {busy && <span className="self-center text-xs text-slack-muted">Re-evaluating…</span>}
          </div>
        </div>
      )}

      {override && (
        <div className="mx-4 mb-3 flex items-center gap-2 text-xs text-emerald-800">
          <span aria-hidden>✓</span>
          Got it. {f.vendor} is treated as {COST_TYPE_SHORT[override]}; detection re-ran with that classification.
          <Link href="/settings" className="text-slack-link underline-offset-2 hover:underline">
            Change
          </Link>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-1.5 border-t border-slack-border px-4 py-2">
        {REACTIONS.map((r) => {
          const active = reaction === r.key;
          return (
            <button
              key={r.key}
              type="button"
              aria-pressed={active}
              onClick={() => onReact(r.key)}
              className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${
                active
                  ? "border-slack-link bg-[#e8f5fa] font-semibold text-slack-link"
                  : "border-slack-border bg-slack-hover text-ink-soft hover:border-[#bbb]"
              }`}
            >
              <span aria-hidden>{r.emoji}</span>
              {r.label}
              {active && <span className="ml-0.5 tabular-nums">1</span>}
            </button>
          );
        })}
        <a
          href="#"
          onClick={(e) => e.preventDefault()}
          className="ml-auto rounded border border-[#bbb] px-3 py-1 text-xs font-bold hover:bg-slack-hover"
        >
          View in Rho ↗
        </a>
      </div>
    </div>
  );
}
