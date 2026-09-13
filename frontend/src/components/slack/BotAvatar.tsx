export function BotAvatar({ size = 36 }: { size?: number }) {
  return (
    <span
      aria-hidden
      style={{ width: size, height: size }}
      className="flex shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 text-white"
    >
      <svg width={size * 0.55} height={size * 0.55} viewBox="0 0 20 20" fill="currentColor">
        <rect x="2" y="11" width="4" height="7" rx="1" />
        <rect x="8" y="7" width="4" height="11" rx="1" />
        <rect x="14" y="2" width="4" height="16" rx="1" />
      </svg>
    </span>
  );
}
