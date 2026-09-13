"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";
import { KIND_LABEL, moneyCompact, pct } from "@/lib/format";
import type { ThreadTurn } from "@/lib/store";
import type { Finding } from "@/lib/types";
import { BotAvatar } from "./slack/BotAvatar";

// Slack-style thread under one alert or report item. Questions go to /api/ask, which answers
// from that finding's evidence pack only; chips cover the questions a founder asks first.

const ALERT_CHIPS = ["Show me the charges", "Which cardholders?", "Why now and not last month?", "What don't you know here?"];
const REPORT_CHIPS = ["Show me the charges", "Why isn't this an alert?", "Which cardholders?", "What don't you know here?"];

function Turn({ t }: { t: ThreadTurn }) {
  if (t.role === "user") {
    return (
      <div className="flex gap-2">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-[#1264a3] text-[11px] font-bold text-white">DK</div>
        <div className="min-w-0">
          <div className="text-[13px] font-black">Dana K.</div>
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{t.text}</p>
        </div>
      </div>
    );
  }
  return (
    <div className="flex gap-2" data-testid="thread-bot-turn">
      <BotAvatar />
      <div className="min-w-0">
        <div className="flex items-baseline gap-1.5">
          <span className="text-[13px] font-black">Cost Signals</span>
          <span className="rounded bg-[#e8e8e8] px-1 py-px text-[10px] font-bold uppercase text-slack-muted">App</span>
          {t.source && (
            <span className="text-[10px] text-slack-muted" title="How this answer was produced">
              {t.source === "claude" ? "via Claude, grounded in this vendor's data" : "template answer"}
            </span>
          )}
        </div>
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink">{t.text}</p>
      </div>
    </div>
  );
}

export function ThreadPanel({
  finding,
  turns,
  busy,
  isAlert,
  onAsk,
  onClose,
}: {
  finding: Finding;
  turns: ThreadTurn[];
  busy: boolean;
  isAlert: boolean;
  onAsk: (question: string) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [turns.length, busy]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!draft.trim() || busy) return;
    onAsk(draft);
    setDraft("");
  };

  const chips = isAlert ? ALERT_CHIPS : REPORT_CHIPS;

  return (
    <aside className="flex w-[420px] shrink-0 flex-col border-l border-slack-border bg-white" aria-label="Thread">
      <div className="flex items-center justify-between border-b border-slack-border px-4 py-2.5">
        <div className="min-w-0">
          <div className="text-[15px] font-black">Thread</div>
          <div className="truncate text-xs text-slack-muted">#spend-signals</div>
        </div>
        <button type="button" onClick={onClose} aria-label="Close thread" className="rounded p-1 text-lg leading-none text-slack-muted hover:bg-slack-hover">
          ×
        </button>
      </div>

      <div className="border-b border-slack-border px-4 py-3">
        <div className="flex gap-2">
          <BotAvatar />
          <div className="min-w-0">
            <div className="text-[13px] font-black">Cost Signals</div>
            <div className="text-sm">
              <span className="font-bold">{finding.vendor}</span> · {KIND_LABEL[finding.kind]} ·{" "}
              <span className="tabular-nums">{moneyCompact(finding.impact_monthly)}</span>
              <span className="text-slack-muted"> · {pct(finding.impact_pct_of_spend, 1)} of spend</span>
            </div>
            <p className="mt-0.5 text-xs text-slack-muted">
              Ask about this {isAlert ? "alert" : "item"}. Answers come only from {finding.vendor}&apos;s Rho transactions
              and the numbers on the card.
            </p>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-3">
        {turns.length === 0 && (
          <p className="text-sm text-slack-muted">
            {turns.length === 0 ? "No replies yet. Try one of the questions below." : null}
          </p>
        )}
        {turns.map((t) => (
          <Turn key={t.ts + t.role} t={t} />
        ))}
        {busy && (
          <div className="flex items-center gap-2 text-sm text-slack-muted" data-testid="thread-pending">
            <span className="flex gap-1" aria-hidden>
              <span className="h-2 w-2 animate-bounce rounded-full bg-slack-muted [animation-delay:-0.3s]" />
              <span className="h-2 w-2 animate-bounce rounded-full bg-slack-muted [animation-delay:-0.15s]" />
              <span className="h-2 w-2 animate-bounce rounded-full bg-slack-muted" />
            </span>
            Checking {finding.vendor}&apos;s charges…
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="border-t border-slack-border px-4 py-3">
        <div className="mb-2 flex flex-wrap gap-1.5">
          {chips.map((c) => (
            <button
              key={c}
              type="button"
              disabled={busy}
              onClick={() => onAsk(c)}
              className="rounded-full border border-slack-border bg-slack-hover px-2.5 py-0.5 text-xs text-ink-soft hover:border-[#bbb] disabled:opacity-50"
            >
              {c}
            </button>
          ))}
        </div>
        <form onSubmit={submit} className="flex items-end gap-2 rounded-lg border border-[#bbb] px-3 py-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={`Reply about ${finding.vendor}…`}
            aria-label="Reply in thread"
            className="min-w-0 flex-1 bg-transparent text-sm outline-none"
          />
          <button
            type="submit"
            disabled={busy || !draft.trim()}
            className="rounded bg-slack-green px-2.5 py-1 text-xs font-bold text-white disabled:opacity-40"
            aria-label="Send"
          >
            ➤
          </button>
        </form>
      </div>
    </aside>
  );
}
