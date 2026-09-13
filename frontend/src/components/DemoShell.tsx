"use client";

import { type ReactNode, useEffect, useRef } from "react";
import { answerAsk, consumePendingRerun, runStep, setReaction, useBusy } from "@/lib/demo-actions";
import { useDemoState } from "@/lib/store";
import { MessageList } from "./MessageList";
import { PresenterBar } from "./PresenterBar";
import { ChannelHeader } from "./slack/ChannelHeader";
import { Composer } from "./slack/Composer";

export function DemoShell({ topBar, sidebar }: { topBar: ReactNode; sidebar: ReactNode }) {
  const state = useDemoState();
  const busy = useBusy();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void consumePendingRerun();
  }, []);

  const messageCount = state.messages.length;
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messageCount, busy]);

  const asOf = state.stage === "idle" ? null : (state.results[state.stage]?.findings.window_end ?? null);
  const busyLabel = state.stage === "idle" || messageCount === 0 ? "Reading twelve months of transactions…" : "Evaluating…";

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {topBar}
      <div className="flex min-h-0 flex-1">
        {sidebar}
        <main className="flex min-w-0 flex-1 flex-col bg-white">
          <ChannelHeader />
          <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
            <MessageList
              state={state}
              busy={busy}
              busyLabel={busyLabel}
              onReact={setReaction}
              onAnswer={(vendor, costType) => void answerAsk(vendor, costType)}
            />
          </div>
          <Composer />
        </main>
      </div>
      <PresenterBar stage={state.stage} busy={busy} asOf={asOf} onRun={(s) => void runStep(s)} />
    </div>
  );
}
