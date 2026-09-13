"use client";

import Link from "next/link";
import { Fragment, useEffect, useState } from "react";
import type { components } from "@/lib/api-types";
import { useDemoState } from "@/lib/store";
import type { Stage } from "@/lib/types";

// Bare view of the raw transactions the pipeline reads: Rho's /transactions shape, one row per
// record, the raw JSON a click away. It follows the presenter's beat: the stage defaults to what
// the channel has loaded, every row is tagged with the beat that added it, and "only what this
// beat added" shows the delta between Load history, New charges and Month closes.

type TransactionsResponse = components["schemas"]["TransactionsResponse"];
type AccountsResponse = components["schemas"]["AccountsResponse"];
type Row = Record<string, unknown>;

const STAGE_LABEL: Record<Stage, string> = {
  history: "Load history · Sep 2025 – Aug 31, 2026",
  "inject-1": "New charges · through Sep 5, 2026",
  "inject-2": "Month closes · through Sep 30, 2026",
};
const BEAT_LABEL: Record<string, string> = { history: "history", "inject-1": "new charges", "inject-2": "month" };

const TYPES = [
  "card_debit",
  "ach_debit",
  "wire_out",
  "check_payment",
  "card_refund",
  "wire_fee",
  "ach_credit",
  "wire_in",
  "credit_repayment",
  "internal_transfer",
  "treasury_deposit",
  "rewards_accrual",
];

const PAGE = 100;

function str(v: unknown): string {
  return v == null ? "" : String(v);
}

function dollars(minor: unknown): { text: string; negative: boolean } {
  const n = Number(minor ?? 0) / 100;
  const text = `${n < 0 ? "−" : ""}$${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return { text, negative: n < 0 };
}

function amount(row: Row) {
  const a = row.amount as { amount?: number } | undefined;
  return dollars(a?.amount);
}

function when(row: Row): string {
  const iso = str(row.initiated_at);
  return iso ? iso.replace("T", " ").replace("Z", " UTC") : "";
}

export function TransactionRecords() {
  const demo = useDemoState();
  const demoStage: Stage = demo.stage === "idle" ? "history" : demo.stage;
  const [stage, setStage] = useState<Stage | null>(null);
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [account, setAccount] = useState("");
  const [onlyBeat, setOnlyBeat] = useState(false);
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<TransactionsResponse | null>(null);
  const [accounts, setAccounts] = useState<AccountsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const effective: Stage = stage ?? demoStage;

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams({ stage: effective, limit: String(PAGE), offset: String(offset) });
    if (q.trim()) params.set("q", q.trim());
    if (type) params.set("type", type);
    if (account) params.set("account", account);
    if (onlyBeat) params.set("beat", effective);
    Promise.all([
      fetch(`/api/transactions?${params.toString()}`).then(async (r) => {
        if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
        return (await r.json()) as TransactionsResponse;
      }),
      fetch(`/api/accounts?stage=${effective}`).then(async (r) => (r.ok ? ((await r.json()) as AccountsResponse) : null)),
    ])
      .then(([d, a]) => {
        if (!cancelled) {
          setData(d);
          setAccounts(a);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [effective, q, type, account, onlyBeat, offset]);

  const rows = (data?.transactions ?? []) as Row[];
  const matched = data?.matched ?? 0;
  const from = matched === 0 ? 0 : offset + 1;
  const to = Math.min(offset + rows.length, matched);
  const addedHere = data?.by_beat?.[effective] ?? 0;

  return (
    <div className="min-h-full bg-[#f6f6f6] text-ink">
      <header className="border-b border-slack-border bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-slack-muted">Cost Signals</div>
            <h1 className="text-xl font-bold">Transaction records</h1>
            <p className="mt-0.5 text-sm text-slack-muted">
              What the pipeline reads: synthetic rows in Rho&apos;s <code>/transactions</code> and <code>/accounts</code> shape.
              Amounts are signed minor units in the raw JSON (debits negative); click a row to see it.
            </p>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <Link href="/settings" className="text-slack-link hover:underline">
              Settings
            </Link>
            <Link href="/" className="text-slack-link hover:underline">
              ← Back to #spend-signals
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-6">
        {accounts && (
          <section className="mb-4 rounded-lg border border-slack-border bg-white px-4 py-3" data-testid="accounts-strip">
            <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 text-sm">
              <span className="text-xs font-semibold uppercase tracking-wide text-slack-muted">Accounts · as of {accounts.as_of}</span>
              {accounts.accounts.map((a) => {
                const acct = a as Row;
                const bal = dollars((acct.balance as { amount?: number } | undefined)?.amount);
                const selected = account === str(acct.account_type);
                return (
                  <button
                    key={str(acct.id)}
                    type="button"
                    onClick={() => {
                      setAccount(selected ? "" : str(acct.account_type));
                      setOffset(0);
                    }}
                    aria-pressed={selected}
                    className={`rounded px-2 py-0.5 text-left hover:bg-slack-hover ${selected ? "bg-[#e8f5fa] ring-1 ring-slack-link" : ""}`}
                    title="Filter the rows to this account"
                  >
                    <span className="font-medium">{str(acct.name)}</span>{" "}
                    <span className="text-xs text-slack-muted">{str(acct.account_type)}</span>{" "}
                    <span className={`font-mono tabular-nums ${bal.negative ? "text-red-700" : ""}`}>{bal.text}</span>
                  </button>
                );
              })}
              <span className="ml-auto text-xs text-slack-muted">Click an account to filter its rows</span>
            </div>
          </section>
        )}

        <div className="mb-3 flex flex-wrap items-end gap-3 text-sm">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slack-muted">Beat {stage === null ? "(following the channel)" : ""}</span>
            <select
              value={effective}
              onChange={(e) => {
                setStage(e.target.value as Stage);
                setOffset(0);
              }}
              aria-label="Stage"
              className="rounded border border-[#bbb] bg-white px-2 py-1"
            >
              {(Object.keys(STAGE_LABEL) as Stage[]).map((s) => (
                <option key={s} value={s}>
                  {STAGE_LABEL[s]}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 self-center pt-4">
            <input
              type="checkbox"
              checked={onlyBeat}
              onChange={(e) => {
                setOnlyBeat(e.target.checked);
                setOffset(0);
              }}
            />
            <span>
              Only what this beat added{data ? ` (${addedHere.toLocaleString()} rows)` : ""}
            </span>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slack-muted">Type</span>
            <select
              value={type}
              onChange={(e) => {
                setType(e.target.value);
                setOffset(0);
              }}
              aria-label="Transaction type"
              className="rounded border border-[#bbb] bg-white px-2 py-1"
            >
              <option value="">all types</option>
              {TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-1 flex-col gap-1">
            <span className="text-xs text-slack-muted">Search counterparty, memo, cardholder</span>
            <input
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setOffset(0);
              }}
              placeholder="e.g. anthropic, pinecone, gusto"
              aria-label="Search"
              className="w-full max-w-md rounded border border-[#bbb] px-2 py-1"
            />
          </label>
          <div className="ml-auto text-xs text-slack-muted" data-testid="records-count">
            {data ? (
              <>
                {from.toLocaleString()}–{to.toLocaleString()} of {matched.toLocaleString()} matching · {data.total.toLocaleString()} rows
                in this beat ·{" "}
                {Object.entries(data.by_beat)
                  .map(([b, n]) => `${BEAT_LABEL[b] ?? b} +${n.toLocaleString()}`)
                  .join(" · ")}
              </>
            ) : error ? (
              <span className="text-red-700">{error}</span>
            ) : (
              "Loading…"
            )}
          </div>
        </div>

        <div className="overflow-x-auto rounded-lg border border-slack-border bg-white">
          <table className="w-full text-left text-[13px]">
            <thead className="bg-[#fafafa] text-xs uppercase tracking-wide text-slack-muted">
              <tr>
                <th className="px-3 py-2 font-semibold">Beat</th>
                <th className="px-3 py-2 font-semibold">Initiated</th>
                <th className="px-3 py-2 font-semibold">Type</th>
                <th className="px-3 py-2 font-semibold">Status</th>
                <th className="px-3 py-2 font-semibold">Counterparty</th>
                <th className="px-3 py-2 text-right font-semibold">Amount</th>
                <th className="px-3 py-2 font-semibold">Account</th>
                <th className="px-3 py-2 font-semibold">Cardholder</th>
                <th className="px-3 py-2 font-semibold">Card</th>
                <th className="px-3 py-2 font-semibold">Memo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slack-border/70">
              {rows.map((r) => {
                const id = str(r.id);
                const a = amount(r);
                const beat = str(r._beat);
                const fresh = beat === effective && effective !== "history";
                const isOpen = open === id;
                return (
                  <Fragment key={id}>
                    <tr
                      onClick={() => setOpen(isOpen ? null : id)}
                      className={`cursor-pointer align-top hover:bg-slack-hover ${fresh ? "bg-amber-50" : ""}`}
                      data-testid="record-row"
                      data-beat={beat}
                    >
                      <td className="whitespace-nowrap px-3 py-1.5 text-xs">
                        <span className={`rounded px-1.5 py-px ${fresh ? "bg-amber-200 font-semibold text-amber-900" : "bg-gray-100 text-gray-600"}`}>
                          {BEAT_LABEL[beat] ?? beat}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-3 py-1.5 font-mono text-xs">{when(r)}</td>
                      <td className="whitespace-nowrap px-3 py-1.5 font-mono text-xs">{str(r.transaction_type)}</td>
                      <td className="px-3 py-1.5">{str(r.status)}</td>
                      <td className="px-3 py-1.5">{str(r.counterparty_name)}</td>
                      <td className={`whitespace-nowrap px-3 py-1.5 text-right font-mono tabular-nums ${a.negative ? "" : "text-emerald-700"}`}>
                        {a.text}
                      </td>
                      <td className="px-3 py-1.5 text-slack-muted">{str(r.account_name)}</td>
                      <td className="px-3 py-1.5">{str(r.user_full_name)}</td>
                      <td className="px-3 py-1.5 text-slack-muted">{str(r.card_name)}</td>
                      <td className="max-w-xs truncate px-3 py-1.5 text-slack-muted">{str(r.memo)}</td>
                    </tr>
                    {isOpen && (
                      <tr>
                        <td colSpan={10} className="bg-[#fafafa] px-3 py-2">
                          <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-[11px] leading-snug">
                            {JSON.stringify(Object.fromEntries(Object.entries(r).filter(([k]) => k !== "_beat")), null, 2)}
                          </pre>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
              {data && rows.length === 0 && (
                <tr>
                  <td colSpan={10} className="px-3 py-6 text-center text-slack-muted">
                    No rows match.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="mt-3 flex items-center justify-between text-sm">
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE))}
            className="rounded border border-[#bbb] bg-white px-3 py-1 disabled:opacity-40"
          >
            ← Previous {PAGE}
          </button>
          <button
            type="button"
            disabled={!data || offset + PAGE >= matched}
            onClick={() => setOffset(offset + PAGE)}
            className="rounded border border-[#bbb] bg-white px-3 py-1 disabled:opacity-40"
          >
            Next {PAGE} →
          </button>
        </div>
      </main>
    </div>
  );
}
