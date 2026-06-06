interface CatCompanionProps {
  /** Visual mood. Purely decorative; never the sole carrier of meaning. */
  variant?: "idle" | "sleepy" | "curious";
  /** Square render size in px. */
  size?: number;
  className?: string;
}

/**
 * Decorative SVG cat — hand-built, zero dependency (no Lottie, no remote asset).
 * All motion is CSS-only and fully disabled under `prefers-reduced-motion` (see
 * `.cat` rules in styles.css). Marked `aria-hidden` because it is ornamental;
 * any place it accompanies a real state (e.g. the empty Recent Sessions list)
 * keeps its own visible text.
 */
export function CatCompanion({ variant = "idle", size = 64, className }: CatCompanionProps) {
  const sleepy = variant === "sleepy";
  return (
    <span
      className={`cat cat--${variant}${className ? ` ${className}` : ""}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <svg viewBox="0 0 64 64" width={size} height={size} role="presentation" focusable="false">
        {/* tail */}
        <path className="cat__tail" d="M43 51 C57 52 58 34 48 31" />

        <g className="cat__body-grp">
          {/* body */}
          <path className="cat__body" d="M18 53 C17 39 24 34 32 34 C40 34 47 39 46 53 Z" />
        </g>

        <g className="cat__head">
          {/* ears */}
          <path className="cat__ear cat__ear--l" d="M21 17 L18 5 L31 13 Z" />
          <path className="cat__ear cat__ear--r" d="M43 17 L46 5 L33 13 Z" />
          <path className="cat__ear-inner" d="M22 15 L21 9 L27 13 Z" />
          <path className="cat__ear-inner" d="M42 15 L43 9 L37 13 Z" />
          {/* face */}
          <circle className="cat__face" cx="32" cy="27" r="13" />

          {sleepy ? (
            <>
              <path className="cat__eye--closed" d="M24.5 28 q2.5 2 5 0" />
              <path className="cat__eye--closed" d="M34.5 28 q2.5 2 5 0" />
            </>
          ) : (
            <>
              <ellipse className="cat__eye" cx="27" cy="27" rx="1.8" ry="2.6" />
              <ellipse className="cat__eye" cx="37" cy="27" rx="1.8" ry="2.6" />
            </>
          )}

          <path className="cat__nose" d="M30.4 31 L33.6 31 L32 33 Z" />
          <path className="cat__mouth" d="M32 33 q-2 2.2 -4.4 .8" />
          <path className="cat__mouth" d="M32 33 q2 2.2 4.4 .8" />

          <g className="cat__whiskers">
            <path className="cat__whisker" d="M22 29 L14 28" />
            <path className="cat__whisker" d="M22 31 L15 33" />
            <path className="cat__whisker" d="M42 29 L50 28" />
            <path className="cat__whisker" d="M42 31 L49 33" />
          </g>
        </g>

        {sleepy && (
          <g className="cat__zzz">
            <text className="cat__z cat__z--1" x="45" y="20">z</text>
            <text className="cat__z cat__z--2" x="51" y="13">z</text>
          </g>
        )}
      </svg>
    </span>
  );
}
