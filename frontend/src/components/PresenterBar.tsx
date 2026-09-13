import Link from "next/link";
import { STAGE_STEP } from "@/lib/demo-actions";
import { longDate } from "@/lib/format";
import type { DemoStage } from "@/lib/store";
import { STAGES, type Stage, stageIndex } from "@/lib/types";

export function PresenterBar({
  stage,
  busy,
  asOf,
  onRun,
}: {
  stage: DemoStage;
  busy: boolean;
  asOf: string | null;
  onRun: (stage: Stage) => void;
}) {
  const doneUpTo = stage === "idle" ? -1 : stageIndex(stage);

  return (
    <div className="flex h-12 shrink-0 items-center gap-3 border-t border-slate-700 bg-slate-900 px-4 text-slate-100">
      <span className="rounded bg-slate-700 px-1.5 py-0.5 text-[10px] font-bold tracking-wider">PRESENTER</span>
      <span className="hidden text-xs text-slate-400 md:inline">Demo controls, not part of Slack</span>

      <div className="ml-2 flex items-center gap-2">
        {STAGES.map((s, i) => {
          const done = i <= doneUpTo;
          const next = i === doneUpTo + 1;
          const running = busy && next;
          return (
            <button
              key={s}
              type="button"
              disabled={!next || busy}
              onClick={() => onRun(s)}
              className={`flex items-center gap-2 rounded-md border px-3 py-1 text-sm font-medium transition ${
                done
                  ? "border-slate-700 bg-slate-800 text-slate-400"
                  : next
                    ? "border-indigo-400 bg-indigo-500 text-white hover:bg-indigo-400 disabled:opacity-80"
                    : "border-slate-800 bg-slate-900 text-slate-600"
              }`}
            >
              <span
                className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-bold ${
                  done ? "bg-emerald-600 text-white" : next ? "bg-white/20" : "bg-slate-800"
                }`}
              >
                {done ? "✓" : i + 1}
              </span>
              {running ? (
                <>
                  <span
                    aria-hidden
                    className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white"
                  />
                  Running…
                </>
              ) : (
                STAGE_STEP[s].label
              )}
            </button>
          );
        })}
      </div>

      <div className="ml-auto flex items-center gap-4 text-xs text-slate-400">
        {asOf && <span className="tabular-nums">As of {longDate(asOf)}</span>}
        <Link href="/transaction-records" className="flex items-center gap-1 rounded px-2 py-1 text-slate-200 hover:bg-slate-800">
          <span aria-hidden>▤</span> Records
        </Link>
        <Link href="/settings" className="flex items-center gap-1 rounded px-2 py-1 text-slate-200 hover:bg-slate-800">
          <span aria-hidden>⚙</span> Settings
        </Link>
      </div>
    </div>
  );
}
