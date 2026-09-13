export function TopBar() {
  return (
    <div className="flex h-10 shrink-0 items-center bg-slack-top px-3 text-white">
      <div className="flex w-56 items-center gap-2 text-slack-sidebar-text">
        <span aria-hidden className="text-sm">‹</span>
        <span aria-hidden className="text-sm">›</span>
        <span aria-hidden className="ml-1 text-sm">🕘</span>
      </div>
      <div className="mx-auto flex h-6 w-full max-w-xl items-center rounded-md bg-white/20 px-2 text-[13px] text-white/85">
        <span aria-hidden className="mr-2 text-xs">🔍</span>
        Search Lumen Labs
      </div>
      <div className="flex w-56 items-center justify-end gap-3">
        <span aria-hidden className="text-sm text-slack-sidebar-text">?</span>
        <span className="flex h-6 w-6 items-center justify-center rounded bg-emerald-600 text-[11px] font-bold">
          DK
        </span>
      </div>
    </div>
  );
}
