export function ChannelHeader() {
  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-slack-border px-5">
      <div className="min-w-0">
        <div className="flex items-center gap-1 text-[17px] font-black">
          <span aria-hidden className="text-slack-muted">#</span>
          spend-signals
          <span aria-hidden className="ml-1 text-xs text-slack-muted">
            ▾
          </span>
        </div>
      </div>
      <div className="flex items-center gap-3 text-[13px] text-slack-muted">
        <span className="hidden truncate lg:inline">Cost changes worth knowing, from Rho</span>
        <span className="flex items-center gap-1 rounded border border-slack-border px-2 py-[2px]">
          <span aria-hidden className="flex -space-x-1">
            <span className="h-4 w-4 rounded-sm bg-emerald-500" />
            <span className="h-4 w-4 rounded-sm bg-sky-500" />
            <span className="h-4 w-4 rounded-sm bg-amber-500" />
          </span>
          6
        </span>
      </div>
    </header>
  );
}
