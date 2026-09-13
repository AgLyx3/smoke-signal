export function Composer() {
  return (
    <div className="shrink-0 px-5 pb-5 pt-2">
      <div
        aria-disabled="true"
        className="rounded-lg border border-[#8d8d8d] bg-white opacity-80"
        title="Composer is disabled in this demo"
      >
        <div className="flex items-center gap-3 border-b border-slack-border px-3 py-1.5 text-[13px] text-slack-muted">
          <span className="font-bold">B</span>
          <span className="italic">I</span>
          <span className="line-through">S</span>
          <span aria-hidden>⛓</span>
          <span aria-hidden>≡</span>
          <span aria-hidden>{"<>"}</span>
        </div>
        <input
          type="text"
          disabled
          placeholder="Message #spend-signals"
          className="w-full bg-transparent px-3 py-2 text-[15px] placeholder:text-slack-muted"
        />
        <div className="flex items-center justify-between px-3 py-1.5 text-slack-muted">
          <div className="flex items-center gap-3 text-sm">
            <span aria-hidden>+</span>
            <span aria-hidden>Aa</span>
            <span aria-hidden>☺</span>
            <span aria-hidden>@</span>
          </div>
          <span
            aria-hidden
            className="flex h-7 w-8 items-center justify-center rounded bg-[#e0e0e0] text-xs text-white"
          >
            ➤
          </span>
        </div>
      </div>
    </div>
  );
}
