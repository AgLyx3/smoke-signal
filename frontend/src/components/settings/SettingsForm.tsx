"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { loadConfigForSettings, saveSettings } from "@/lib/demo-actions";
import { COST_TYPE_LABEL, SOURCE_LABEL, money, pct } from "@/lib/format";
import { getState, resetDemo, useDemoState } from "@/lib/store";
import { COST_TYPES, type Config, type CostType, type Stage, STAGES } from "@/lib/types";
import { ConnectionsSection } from "./ConnectionsSection";

type Draft = { config: Config; overrides: Record<string, CostType> };

const TYPE_NOTE: Record<CostType, string> = {
  usage: "Log-linear trend; alerts on a break from the vendor's own growth.",
  fixed: "Last price; alerts on a material price change.",
  headcount: "Cost per head; alerts when it leaves its own range.",
  annual: "Renewal notices only. Off by default.",
  payroll: "Context in reports. Off by default.",
};

function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={() => onChange(!on)}
      className={`relative h-6 w-11 rounded-full transition ${on ? "bg-slack-green" : "bg-gray-300"}`}
    >
      <span
        className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${on ? "left-[22px]" : "left-0.5"}`}
      />
    </button>
  );
}

export function SettingsForm() {
  const router = useRouter();
  const state = useDemoState();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);

  useEffect(() => {
    let cancelled = false;
    loadConfigForSettings()
      .then((config) => {
        if (!cancelled) setDraft({ config: structuredClone(config), overrides: { ...getState().overrides } });
      })
      .catch((e: unknown) => {
        if (!cancelled) setLoadError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const latestStage: Stage | undefined =
    state.stage !== "idle" ? state.stage : [...STAGES].reverse().find((s) => state.results[s]);
  const latest = latestStage ? state.results[latestStage] : undefined;
  const trailing = latest?.findings.trailing_monthly_spend ?? null;
  const vendors = latest?.findings.vendors ?? [];

  const setThreshold = (t: CostType, patch: Partial<Config["thresholds"][string]>) => {
    if (!draft) return;
    const cur = draft.config.thresholds[t] ?? { alert_pct: 0.01, alerts: true };
    setDraft({ ...draft, config: { ...draft.config, thresholds: { ...draft.config.thresholds, [t]: { ...cur, ...patch } } } });
  };

  const setOverride = (vendor: string, ct: CostType | null) => {
    if (!draft) return;
    const overrides = { ...draft.overrides };
    if (ct === null) delete overrides[vendor];
    else overrides[vendor] = ct;
    setDraft({ ...draft, overrides });
  };

  const onSave = () => {
    if (!draft) return;
    saveSettings(draft.config, draft.overrides);
    router.push("/");
  };

  const onReset = () => {
    resetDemo();
    router.push("/");
  };

  return (
    <div className="min-h-full bg-[#f6f6f6] text-ink">
      <header className="border-b border-slack-border bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-slack-muted">Cost Signals</div>
            <h1 className="text-xl font-bold">Settings</h1>
          </div>
          <Link href="/" className="text-sm text-slack-link hover:underline">
            ← Back to #spend-signals
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-8 px-6 py-8">
        {loadError && (
          <div role="alert" className="rounded border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800">
            Couldn&apos;t load the default thresholds: {loadError}
          </div>
        )}

        <section className="rounded-lg border border-slack-border bg-white">
          <div className="border-b border-slack-border px-5 py-3">
            <h2 className="font-bold">Alert thresholds</h2>
            <p className="text-sm text-slack-muted">
              A finding alerts when its monthly impact reaches this share of trailing monthly spend
              {trailing ? ` (currently ${money(trailing)}/mo)` : ""}. Everything below the line goes to the report.
              {!trailing && " Load history to see dollar equivalents."}
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-slack-muted">
                <tr>
                  <th className="px-5 py-2 font-semibold">Cost type</th>
                  <th className="px-3 py-2 font-semibold">Alert at</th>
                  <th className="px-3 py-2 font-semibold">Dollar equivalent</th>
                  <th className="px-3 py-2 font-semibold">Alerts</th>
                  <th className="px-5 py-2 font-semibold">Baseline</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slack-border/70">
                {COST_TYPES.map((t) => {
                  const th = draft?.config.thresholds[t];
                  return (
                    <tr key={t}>
                      <td className="px-5 py-2.5 font-medium">{COST_TYPE_LABEL[t]}</td>
                      <td className="px-3 py-2.5">
                        <label className="flex items-center gap-1">
                          <input
                            type="number"
                            min={0}
                            max={100}
                            step={0.1}
                            disabled={!th}
                            value={th ? Number((th.alert_pct * 100).toFixed(2)) : ""}
                            onChange={(e) => {
                              const v = Number(e.target.value);
                              if (Number.isFinite(v)) setThreshold(t, { alert_pct: Math.max(0, v) / 100 });
                            }}
                            className="w-20 rounded border border-[#bbb] px-2 py-1 text-right tabular-nums disabled:bg-gray-100"
                            aria-label={`${COST_TYPE_LABEL[t]} alert percent`}
                          />
                          <span className="text-slack-muted">%</span>
                        </label>
                      </td>
                      <td className="px-3 py-2.5 tabular-nums text-ink-soft">
                        {th && trailing ? `≈ ${money(th.alert_pct * trailing)}/mo` : "—"}
                      </td>
                      <td className="px-3 py-2.5">
                        {th && (
                          <Toggle on={th.alerts} onChange={(v) => setThreshold(t, { alerts: v })} label={`${COST_TYPE_LABEL[t]} alerts`} />
                        )}
                      </td>
                      <td className="px-5 py-2.5 text-xs text-slack-muted">{TYPE_NOTE[t]}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section className="rounded-lg border border-slack-border bg-white">
          <div className="border-b border-slack-border px-5 py-3">
            <h2 className="font-bold">Vendor classifications</h2>
            <p className="text-sm text-slack-muted">
              How each vendor is expected to behave. Taxonomy matches are fixed rules; inferred ones came from the
              classifier. Changing a value writes an override that wins over both.
              {vendors.length === 0 && " Load history to see vendors."}
            </p>
          </div>
          {vendors.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase tracking-wide text-slack-muted">
                  <tr>
                    <th className="px-5 py-2 font-semibold">Vendor</th>
                    <th className="px-3 py-2 font-semibold">Category</th>
                    <th className="px-3 py-2 font-semibold">Cadence</th>
                    <th className="px-3 py-2 text-right font-semibold">Monthly</th>
                    <th className="px-3 py-2 text-right font-semibold">Growth</th>
                    <th className="px-3 py-2 font-semibold">Cost type</th>
                    <th className="px-5 py-2 font-semibold">Source</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slack-border/70">
                  {vendors.map((v) => {
                    const override = draft?.overrides[v.vendor];
                    const value = override ?? v.cost_type;
                    return (
                      <tr key={v.vendor}>
                        <td className="px-5 py-2 font-medium">{v.vendor}</td>
                        <td className="px-3 py-2 text-ink-soft">{v.category}</td>
                        <td className="px-3 py-2 text-ink-soft">{v.cadence}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{money(v.monthly_spend)}</td>
                        <td className="px-3 py-2 text-right tabular-nums text-ink-soft">
                          {v.growth_pct != null ? `${pct(v.growth_pct, 0, true)}/mo` : "—"}
                        </td>
                        <td className="px-3 py-2">
                          <select
                            value={value}
                            disabled={!draft}
                            onChange={(e) => setOverride(v.vendor, e.target.value as CostType)}
                            aria-label={`${v.vendor} cost type`}
                            className="rounded border border-[#bbb] bg-white px-2 py-1"
                          >
                            {COST_TYPES.map((t) => (
                              <option key={t} value={t}>
                                {COST_TYPE_LABEL[t]}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="px-5 py-2 text-xs">
                          {override ? (
                            <span className="inline-flex items-center gap-2">
                              <span className="rounded bg-emerald-100 px-1.5 py-px font-medium text-emerald-900">
                                Override
                              </span>
                              <button
                                type="button"
                                onClick={() => setOverride(v.vendor, null)}
                                className="text-slack-link hover:underline"
                              >
                                clear
                              </button>
                            </span>
                          ) : (
                            <span
                              className={`rounded px-1.5 py-px font-medium ${
                                v.cost_type_source === "llm" ? "bg-amber-100 text-amber-900" : "bg-gray-100 text-gray-700"
                              }`}
                            >
                              {SOURCE_LABEL[v.cost_type_source]}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <ConnectionsSection />

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {confirmReset ? (
              <>
                <span className="text-sm text-ink-soft">Clears the transcript, thresholds, overrides, reactions and connections.</span>
                <button
                  type="button"
                  onClick={onReset}
                  className="rounded border border-red-300 bg-red-50 px-3 py-1.5 text-sm font-semibold text-red-800 hover:bg-red-100"
                >
                  Yes, reset demo
                </button>
                <button type="button" onClick={() => setConfirmReset(false)} className="text-sm text-slack-muted hover:underline">
                  Cancel
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmReset(true)}
                className="rounded border border-[#bbb] bg-white px-3 py-1.5 text-sm font-semibold hover:bg-slack-hover"
              >
                Reset demo
              </button>
            )}
          </div>
          <div className="flex items-center gap-3">
            <Link href="/" className="text-sm text-slack-muted hover:underline">
              Cancel
            </Link>
            <button
              type="button"
              disabled={!draft}
              onClick={onSave}
              className="rounded bg-slack-green px-4 py-1.5 text-sm font-bold text-white hover:bg-[#148567] disabled:opacity-50"
            >
              Save
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
