const CHANNELS = ["general", "engineering", "finance", "spend-signals", "random"];
const SELECTED = "spend-signals";
const DMS: { name: string; online: boolean }[] = [
  { name: "Dana K.", online: true },
  { name: "Sam O.", online: true },
  { name: "Priya N.", online: false },
];

function SectionTitle({ children }: { children: string }) {
  return (
    <div className="mt-4 flex items-center gap-1 px-4 text-[15px] text-slack-sidebar-text">
      <span aria-hidden className="text-[10px]">▾</span>
      {children}
    </div>
  );
}

export function Sidebar() {
  return (
    <nav className="flex w-64 shrink-0 flex-col bg-slack-sidebar text-slack-sidebar-text">
      <div className="flex h-12 items-center justify-between border-b border-white/10 px-4">
        <div className="flex items-center gap-1 text-[17px] font-black text-white">
          Lumen Labs
          <span aria-hidden className="text-xs">▾</span>
        </div>
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white text-slack-sidebar" aria-hidden>
          ✎
        </span>
      </div>

      <div className="flex-1 overflow-y-auto pb-4 text-[15px]">
        <ul className="mt-3">
          {["Threads", "Mentions & reactions", "Drafts & sent"].map((item) => (
            <li key={item} className="px-4 py-[3px]">
              {item}
            </li>
          ))}
        </ul>

        <SectionTitle>Channels</SectionTitle>
        <ul>
          {CHANNELS.map((c) => {
            const selected = c === SELECTED;
            return (
              <li
                key={c}
                aria-current={selected ? "page" : undefined}
                className={`mx-2 flex items-center gap-2 rounded px-2 py-[3px] ${
                  selected ? "bg-slack-selected font-medium text-white" : "hover:bg-white/10"
                }`}
              >
                <span aria-hidden className="w-3 text-center opacity-70">
                  #
                </span>
                {c}
              </li>
            );
          })}
          <li className="mx-2 flex items-center gap-2 rounded px-2 py-[3px] opacity-80">
            <span aria-hidden className="w-3 text-center">
              +
            </span>
            Add channels
          </li>
        </ul>

        <SectionTitle>Direct messages</SectionTitle>
        <ul>
          {DMS.map((d) => (
            <li key={d.name} className="mx-2 flex items-center gap-2 rounded px-2 py-[3px] hover:bg-white/10">
              <span
                aria-hidden
                className={`h-2 w-2 rounded-full ${d.online ? "bg-emerald-400" : "border border-slack-sidebar-text"}`}
              />
              {d.name}
            </li>
          ))}
        </ul>

        <SectionTitle>Apps</SectionTitle>
        <ul>
          <li className="mx-2 flex items-center gap-2 rounded px-2 py-[3px] hover:bg-white/10">
            <span aria-hidden className="h-4 w-4 rounded-sm bg-gradient-to-br from-indigo-500 to-violet-600" />
            Cost Signals
          </li>
        </ul>
      </div>
    </nav>
  );
}
