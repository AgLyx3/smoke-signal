import { longDate } from "@/lib/format";
import type { ChannelMessage, DemoState, Reaction } from "@/lib/store";
import type { CostType, Stage } from "@/lib/types";
import { AlertCard } from "./AlertCard";
import { ReportMessage } from "./ReportMessage";
import { BotAvatar } from "./slack/BotAvatar";
import { BotMessage, DayDivider, SystemLine } from "./slack/BotMessage";

function EmptyChannel() {
  return (
    <div className="px-5 pb-6 pt-10">
      <div className="mb-3 flex h-16 w-16 items-center justify-center rounded-xl bg-slack-hover text-3xl text-slack-muted">
        #
      </div>
      <h2 className="text-2xl font-black">You&apos;re looking at #spend-signals</h2>
      <p className="mt-1 max-w-xl text-[15px] text-ink-soft">
        This is the very beginning of the channel. Cost Signals posts here when a vendor moves off its own trend, and
        sends a report when the month closes.
      </p>
      <p className="mt-3 text-sm text-slack-muted">Use the presenter bar below to load history.</p>
    </div>
  );
}

function Pending({ label }: { label: string }) {
  return (
    <div className="mt-2 flex gap-3 px-5 py-1">
      <BotAvatar />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-1.5">
          <span className="text-[15px] font-black">Cost Signals</span>
          <span className="rounded bg-[#e8e8e8] px-1 py-px text-[10px] font-bold uppercase text-slack-muted">App</span>
        </div>
        <div className="mt-1 flex items-center gap-2 text-sm text-slack-muted">
          <span className="flex gap-1" aria-hidden>
            <span className="h-2 w-2 animate-bounce rounded-full bg-slack-muted [animation-delay:-0.3s]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-slack-muted [animation-delay:-0.15s]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-slack-muted" />
          </span>
          {label}
        </div>
      </div>
    </div>
  );
}

export function MessageList({
  state,
  busy,
  busyLabel,
  onReact,
  onAnswer,
}: {
  state: DemoState;
  busy: boolean;
  busyLabel: string;
  onReact: (findingId: string, r: Reaction) => void;
  onAnswer: (vendor: string, costType: CostType) => void;
}) {
  const { messages, results, openIssues, reactions, overrides } = state;

  const openSince = new Map<string, string>();
  openIssues.forEach((o) => {
    const end = results[o.stage]?.findings.window_end;
    if (end) openSince.set(o.id, end);
  });

  const renderBody = (m: ChannelMessage) => {
    if (m.kind === "system") return <SystemLine text={m.text} tone={m.tone} />;
    const result = results[m.stage as Stage];
    if (!result) return <SystemLine text="This message's data was cleared." tone="info" />;

    if (m.kind === "report") {
      return <ReportMessage findings={result.findings} report={result.narration.report ?? null} openSince={openSince} />;
    }

    const finding = result.findings.findings.find((f) => f.id === m.findingId);
    if (!finding) {
      return (
        <p className="mt-1 text-sm italic text-slack-muted">
          This finding is no longer produced at the current settings.
        </p>
      );
    }
    return (
      <AlertCard
        finding={finding}
        text={result.narration.alerts.find((a) => a.finding_id === m.findingId)}
        headcount={result.findings.headcount_proxy}
        reaction={reactions[finding.id]}
        override={overrides[finding.vendor]}
        busy={busy}
        demoted={finding.route !== "alert"}
        onReact={(r) => onReact(finding.id, r)}
        onAnswer={(c) => onAnswer(finding.vendor, c)}
      />
    );
  };

  let lastAsOf: string | null = null;
  const rows = messages.map((m, i) => {
    const divider = m.asOf !== lastAsOf;
    lastAsOf = m.asOf;
    const prev = messages[i - 1];
    const continued = !divider && Boolean(prev) && prev.kind !== "system" && m.kind !== "system";
    return (
      <div key={m.id}>
        {divider && <DayDivider label={longDate(m.asOf)} />}
        {m.kind === "system" ? (
          renderBody(m)
        ) : (
          <BotMessage ts={m.ts} continued={continued}>
            {renderBody(m)}
          </BotMessage>
        )}
      </div>
    );
  });

  return (
    <div className="pb-2">
      {messages.length === 0 && !busy ? <EmptyChannel /> : rows}
      {busy && <Pending label={busyLabel} />}
    </div>
  );
}
