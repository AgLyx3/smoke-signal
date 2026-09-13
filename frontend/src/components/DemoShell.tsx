"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";
import { answerAsk, askInThread, consumePendingRerun, runStep, setReaction, useBusy, useThreadBusy } from "@/lib/demo-actions";
import { useDemoState } from "@/lib/store";
import type { Stage } from "@/lib/types";
import { DmView } from "./DmView";
import { MessageList } from "./MessageList";
import { PresenterBar } from "./PresenterBar";
import { ThreadPanel } from "./ThreadPanel";
import { ChannelHeader } from "./slack/ChannelHeader";
import { Composer } from "./slack/Composer";

type OpenThread = { stage: Stage; findingId: string };

export function DemoShell({ topBar, sidebar }: { topBar: ReactNode; sidebar: ReactNode }) {
  const state = useDemoState();
  const busy = useBusy();
  const [thread, setThread] = useState<OpenThread | null>(null);
  const threadBusy = useThreadBusy(thread?.findingId ?? null);
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

  const threadFinding = thread ? state.results[thread.stage]?.findings.findings.find((f) => f.id === thread.findingId) : undefined;
  if (thread && !threadFinding && !busy) {
    // The finding disappeared (settings changed, demo reset): close the panel rather than show a stale one.
    setThread(null);
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {topBar}
      <div className="flex min-h-0 flex-1">
        {sidebar}
        <main className="flex min-w-0 flex-1 flex-col bg-white">
          {state.view === "dm" ? (
            <DmView state={state} />
          ) : (
            <>
              <ChannelHeader />
              <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
                <MessageList
                  state={state}
                  busy={busy}
                  busyLabel={busyLabel}
                  onReact={setReaction}
                  onAnswer={(vendor, costType) => void answerAsk(vendor, costType)}
                  onOpenThread={(stage, findingId) => setThread({ stage, findingId })}
                  openThreadId={thread?.findingId ?? null}
                />
              </div>
              <Composer />
            </>
          )}
        </main>
        {thread && threadFinding && (
          <ThreadPanel
            finding={threadFinding}
            turns={state.threads[thread.findingId] ?? []}
            busy={threadBusy}
            isAlert={threadFinding.route === "alert"}
            onAsk={(q) => void askInThread(thread.stage, thread.findingId, q)}
            onClose={() => setThread(null)}
          />
        )}
      </div>
      <PresenterBar stage={state.stage} busy={busy} asOf={asOf} onRun={(s) => void runStep(s)} />
    </div>
  );
}
