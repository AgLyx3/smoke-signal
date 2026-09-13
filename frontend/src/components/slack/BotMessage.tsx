import type { ReactNode } from "react";
import { clockTime } from "@/lib/format";
import { BotAvatar } from "./BotAvatar";

export function BotMessage({
  ts,
  continued,
  children,
}: {
  ts: number;
  continued: boolean;
  children: ReactNode;
}) {
  return (
    <div className={`group relative flex gap-3 px-5 hover:bg-slack-hover ${continued ? "py-0.5" : "mt-2 py-1"}`}>
      <div className="flex w-9 shrink-0 justify-end">
        {continued ? (
          <span className="relative w-full">
            <span aria-hidden className="absolute bottom-0 left-[17px] top-0 w-px bg-slack-border" />
            <span className="absolute right-0 top-1 hidden text-[11px] text-slack-muted group-hover:inline">
              {clockTime(ts)}
            </span>
          </span>
        ) : (
          <BotAvatar />
        )}
      </div>
      <div className="min-w-0 flex-1">
        {!continued && (
          <div className="flex items-baseline gap-1.5">
            <span className="text-[15px] font-black">Smoke Signal</span>
            <span className="rounded bg-[#e8e8e8] px-1 py-px text-[10px] font-bold uppercase text-slack-muted">App</span>
            <span className="text-xs text-slack-muted">{clockTime(ts)}</span>
          </div>
        )}
        {children}
      </div>
    </div>
  );
}

export function DayDivider({ label }: { label: string }) {
  return (
    <div className="relative my-3 flex items-center justify-center">
      <span aria-hidden className="absolute inset-x-0 top-1/2 h-px bg-slack-border" />
      <span className="relative rounded-full border border-slack-border bg-white px-3 py-1 text-[13px] font-bold">
        {label}
      </span>
    </div>
  );
}

export function SystemLine({ text, tone }: { text: string; tone: "info" | "error" }) {
  return (
    <div
      role={tone === "error" ? "alert" : undefined}
      className={`mx-5 my-1 rounded px-3 py-1.5 text-[13px] ${
        tone === "error" ? "bg-red-50 text-red-800" : "text-slack-muted"
      }`}
    >
      {tone === "error" ? "⚠ " : ""}
      {text}
    </div>
  );
}
