import { useId } from "react";

/** The CodeTortoise mascot: a tortoise seen from above in a dark tile (also public/logo.svg, the tab icon). */
export default function Logo({ size = 28, title }: { size?: number; title?: string }) {
  const id = useId().replace(/:/g, "");
  const [shell, tile, amber] = [`${id}s`, `${id}t`, `${id}a`];
  return (
    <svg width={size} height={size} viewBox="0 0 80 80" role={title ? "img" : undefined} aria-hidden={title ? undefined : true}
         aria-label={title}>
      <defs>
        <linearGradient id={shell} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#8f75ff" /><stop offset="1" stopColor="#3b2a9e" /></linearGradient>
        <linearGradient id={tile} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#151a2d" /><stop offset="1" stopColor="#2a2466" /></linearGradient>
        <linearGradient id={amber} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#ffd36b" /><stop offset="1" stopColor="#ffab1f" /></linearGradient>
      </defs>
      <rect x="2" y="2" width="76" height="76" rx="18" fill={`url(#${tile})`} />
      <g fill={`url(#${amber})`}>
        <ellipse cx="40" cy="15" rx="7" ry="8" />
        <ellipse cx="20" cy="27" rx="7" ry="5" transform="rotate(-35 20 27)" />
        <ellipse cx="60" cy="27" rx="7" ry="5" transform="rotate(35 60 27)" />
        <ellipse cx="21" cy="57" rx="7" ry="5" transform="rotate(35 21 57)" />
        <ellipse cx="59" cy="57" rx="7" ry="5" transform="rotate(-35 59 57)" />
        <path d="M40 66 L36 72 L44 72 Z" />
      </g>
      <circle cx="37" cy="12.5" r="1.4" fill="#2b1a00" />
      <circle cx="43" cy="12.5" r="1.4" fill="#2b1a00" />
      <ellipse cx="40" cy="42" rx="20" ry="23" fill={`url(#${shell})`} />
      <g fill="none" stroke="#d4caff" strokeWidth="1.5" strokeLinejoin="round">
        <polygon points="40,33 47,37 47,46 40,50 33,46 33,37" />
        <path d="M40 19 V33 M47 37 L57 31 M47 46 L58 52 M40 50 V65 M33 46 L22 52 M33 37 L23 31" />
      </g>
    </svg>
  );
}
