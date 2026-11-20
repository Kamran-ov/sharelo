// 2 px stroke line icons, round caps, drawn in currentColor (docs/design/README.md "Icons").
const PATHS = {
  plus: "M12 5v14M5 12h14",
  chevronDown: "M6 9l6 6 6-6",
  chevronLeft: "M15 6l-6 6 6 6",
  close: "M6 6l12 12M18 6L6 18",
  list: "M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01",
  scale: "M12 4v16M5 8h14M5 8l-3 6a3 3 0 006 0zM19 8l-3 6a3 3 0 006 0zM8 20h8",
  repeat: "M17 2l4 4-4 4M3 11V9a3 3 0 013-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 01-3 3H3",
  settings: "M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z",
  cart: "M3 4h2l2.4 11h11l2-8H6.2M9 20h.01M18 20h.01",
  food: "M4 3v8a3 3 0 003 3v7M7 3v8M10 3v8a3 3 0 01-3 3M17 3c-2 0-3 2-3 5s1 4 3 4v9",
  home: "M3 11l9-7 9 7M5 10v10h14V10",
  car: "M5 16l1.5-5h11l1.5 5M4 16h16v3H4zM7 19v2M17 19v2",
  bolt: "M13 2L4 14h7l-1 8 9-12h-7z",
  ticket: "M3 8a2 2 0 002-2h14a2 2 0 002 2v2a2 2 0 000 4v2a2 2 0 00-2 2H5a2 2 0 00-2-2v-2a2 2 0 000-4z",
  heart: "M12 20s-7-4.4-7-10a4 4 0 017-2.6A4 4 0 0119 10c0 5.6-7 10-7 10z",
  tag: "M3 12V4h8l10 10-8 8zM7.5 7.5h.01",
  share: "M4 12v7a1 1 0 001 1h14a1 1 0 001-1v-7M16 6l-4-4-4 4M12 2v13",
  upload: "M4 17v2a1 1 0 001 1h14a1 1 0 001-1v-2M7 9l5-5 5 5M12 4v12",
} as const;

export type IconName = keyof typeof PATHS;

export default function Icon({ name, size = 20, strokeWidth = 2 }: { name: IconName; size?: number; strokeWidth?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  );
}

/** Category tile icon from the Splitwise parent category name; anything unknown is a tag. */
export function categoryIcon(parentName: string | undefined): IconName {
  switch (parentName) {
    case "Food and drink":
      return "food";
    case "Home":
      return "home";
    case "Transportation":
      return "car";
    case "Utilities":
      return "bolt";
    case "Entertainment":
      return "ticket";
    case "Life":
      return "heart";
    default:
      return "tag";
  }
}
