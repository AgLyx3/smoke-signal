"use client";

import { useState } from "react";
import { type Connections, type ProviderId, type RunwayDelivery, setState, useDemoState } from "@/lib/store";

// Opt-in connections, each one a named capability with a stated reason (PRD: progressive
// disclosure of asks). These persist immediately; they are not part of the threshold draft.
// Provider keys are recorded only; runway framing changes what the cards and reports show.

const PROVIDERS: { id: ProviderId; name: string; prefix: string; placeholder: string }[] = [
  { id: "anthropic", name: "Anthropic", prefix: "sk-ant-", placeholder: "sk-ant-admin… (read-only)" },
  { id: "openai", name: "OpenAI", prefix: "sk-", placeholder: "sk-admin… (read-only)" },
];

const PEOPLE = ["Dana K.", "Sam O.", "Priya N."];

function maskKey(key: string): string {
  return `••••${key.slice(-4)}`;
}

function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={() => onChange(!on)}
      className={`relative h-6 w-11 shrink-0 rounded-full transition ${on ? "bg-slack-green" : "bg-gray-300"}`}
    >
      <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${on ? "left-[22px]" : "left-0.5"}`} />
    </button>
  );
}

function ProviderRow({ id, name, prefix, placeholder, connections }: (typeof PROVIDERS)[number] & { connections: Connections }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const conn = connections.providers[id];

  const connect = () => {
    const key = value.trim();
    if (!key.startsWith(prefix) || key.length < 20) {
      setError(`Expected a read-only admin key starting with ${prefix}`);
      return;
    }
    // Only the masked tail is kept. The key never reaches storage or the network in this build.
    setState({
      connections: {
        ...connections,
        providers: { ...connections.providers, [id]: { connected: true, label: maskKey(key), connectedAt: new Date().toISOString() } },
      },
    });
    setValue("");
    setError(null);
  };

  const disconnect = () => {
    setState({
      connections: { ...connections, providers: { ...connections.providers, [id]: { connected: false, label: null, connectedAt: null } } },
    });
  };

  return (
    <div className="flex flex-wrap items-center gap-3 px-5 py-3">
      <div className="w-24 font-medium">{name}</div>
      {conn.connected ? (
        <>
          <span className="rounded bg-emerald-100 px-1.5 py-px text-xs font-medium text-emerald-900">Connected</span>
          <span className="font-mono text-xs text-ink-soft">{conn.label}</span>
          <span className="text-xs text-slack-muted">per-model and per-key breakdown enabled for {name} alerts</span>
          <button type="button" onClick={disconnect} className="ml-auto text-xs text-slack-link hover:underline">
            Disconnect
          </button>
        </>
      ) : (
        <>
          <span className="rounded bg-gray-100 px-1.5 py-px text-xs font-medium text-gray-700">Not connected</span>
          <input
            type="password"
            autoComplete="off"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={placeholder}
            aria-label={`${name} admin key`}
            className="w-64 rounded border border-[#bbb] px-2 py-1 font-mono text-xs"
          />
          <button
            type="button"
            onClick={connect}
            className="rounded border border-[#bbb] bg-white px-3 py-1 text-sm font-semibold hover:bg-slack-hover"
          >
            Connect
          </button>
          {error && (
            <span role="alert" className="text-xs text-red-700">
              {error}
            </span>
          )}
        </>
      )}
    </div>
  );
}

export function ConnectionsSection() {
  const { connections } = useDemoState();
  const runway = connections.runway;

  const setRunway = (patch: Partial<Connections["runway"]>) =>
    setState({ connections: { ...connections, runway: { ...runway, ...patch } } });

  return (
    <section className="rounded-lg border border-slack-border bg-white">
      <div className="border-b border-slack-border px-5 py-3">
        <h2 className="font-bold">Connections</h2>
        <p className="text-sm text-slack-muted">
          Everything above works with Rho data alone. Each connection here is optional and unlocks one named
          capability. Nothing is asked for up front.
        </p>
      </div>

      <div className="border-b border-slack-border">
        <div className="px-5 pt-3">
          <h3 className="text-sm font-semibold">Provider usage keys</h3>
          <p className="text-xs text-slack-muted">
            A read-only admin key lets an alert on that vendor break down by model and by API key, so &ldquo;Anthropic is
            60% above trend&rdquo; can say which model or key did it. We keep only the last four characters here; in
            production the key is encrypted server-side with read scope only. It can never move money or change limits.
          </p>
        </div>
        <div className="divide-y divide-slack-border/70">
          {PROVIDERS.map((p) => (
            <ProviderRow key={p.id} {...p} connections={connections} />
          ))}
        </div>
      </div>

      <div className="px-5 py-3">
        <div className="flex items-start gap-3">
          <Toggle on={runway.enabled} onChange={(v) => setRunway({ enabled: v })} label="Runway framing" />
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold">Runway framing</h3>
            <p className="text-xs text-slack-muted">
              State each alert&apos;s consequence in weeks of runway, computed from the operating account balance and
              trailing net burn. Rho already holds both, so this needs no extra data. Runway is owner-level
              information, which is why it has its own destination.
            </p>
            {runway.enabled && (
              <fieldset className="mt-3 space-y-2 text-sm">
                <legend className="text-xs font-semibold uppercase tracking-wide text-slack-muted">
                  Where runway detail goes
                </legend>
                {(
                  [
                    ["dm", "Direct message to the founder (recommended)"],
                    ["channel", "The #spend-signals channel, visible to everyone in it"],
                  ] as [RunwayDelivery, string][]
                ).map(([value, label]) => (
                  <label key={value} className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="runway-delivery"
                      value={value}
                      checked={runway.delivery === value}
                      onChange={() => setRunway({ delivery: value })}
                    />
                    <span>{label}</span>
                  </label>
                ))}
                {runway.delivery === "dm" && (
                  <label className="flex items-center gap-2 pl-6">
                    <span className="text-xs text-slack-muted">Recipient</span>
                    <select
                      value={runway.recipient}
                      onChange={(e) => setRunway({ recipient: e.target.value })}
                      aria-label="Runway recipient"
                      className="rounded border border-[#bbb] bg-white px-2 py-1 text-sm"
                    >
                      {PEOPLE.map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <div className="flex flex-wrap items-center gap-4 pt-1">
                  <label className="flex items-center gap-2">
                    <span className="text-xs text-slack-muted">Keep in operating</span>
                    <input
                      type="number"
                      min={0}
                      max={24}
                      step={0.5}
                      value={runway.bufferMonths}
                      onChange={(e) => setRunway({ bufferMonths: Math.max(0, Number(e.target.value) || 0) })}
                      aria-label="Buffer months"
                      className="w-16 rounded border border-[#bbb] px-2 py-1 text-right tabular-nums"
                    />
                    <span className="text-xs text-slack-muted">months of net burn</span>
                  </label>
                  <label className="flex items-center gap-2">
                    <span className="text-xs text-slack-muted">Treasury yield</span>
                    <input
                      type="number"
                      min={0}
                      max={20}
                      step={0.1}
                      value={Number((runway.treasuryApy * 100).toFixed(2))}
                      onChange={(e) => setRunway({ treasuryApy: Math.max(0, Number(e.target.value) || 0) / 100 })}
                      aria-label="Treasury APY percent"
                      className="w-16 rounded border border-[#bbb] px-2 py-1 text-right tabular-nums"
                    />
                    <span className="text-xs text-slack-muted">% APY (assumption)</span>
                  </label>
                </div>
                <p className="text-xs text-slack-muted">
                  When on, alerts say what a change costs in weeks of runway, and reports carry the cash position: total
                  cash across both Rho accounts, net burn, runway, and what the operating balance above the buffer could
                  earn in Rho Treasury.
                </p>
              </fieldset>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
