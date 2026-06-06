/** Single-weight line icons, ported from the Claude Design prototype. */
interface IconProps {
  size?: number;
  stroke?: string;
  sw?: number;
  children: React.ReactNode;
}

function Icon({ size = 18, stroke = "currentColor", sw = 1.7, children }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={stroke}
      strokeWidth={sw}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

type P = { size?: number; stroke?: string };

export const MicIcon = (p: P) => (
  <Icon {...p}>
    <rect x="9" y="2" width="6" height="12" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </Icon>
);
export const MicOffIcon = (p: P) => (
  <Icon {...p}>
    <path d="M9 5a3 3 0 0 1 6 0v5M15 13.5A3 3 0 0 1 9 11M5 11a7 7 0 0 0 11.5 5.4M12 18v3M3 3l18 18" />
  </Icon>
);
export const GearIcon = (p: P) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1l2.1-2.1M17 7l2.1-2.1" />
  </Icon>
);
export const HistoryIcon = (p: P) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </Icon>
);
export const CloseIcon = (p: P) => (
  <Icon {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Icon>
);
export const BackIcon = (p: P) => (
  <Icon {...p}>
    <path d="M15 5l-7 7 7 7" />
  </Icon>
);
export const InterruptIcon = (p: P) => (
  <Icon {...p}>
    <path d="M9 7l-5 5 5 5M4 12h11a5 5 0 0 0 5-5V5" />
  </Icon>
);
export const PowerIcon = (p: P) => (
  <Icon {...p} sw={2.2}>
    <path d="M12 3.5v8" />
    <path d="M6.8 7.2a7.5 7.5 0 1 0 10.4 0" />
  </Icon>
);
