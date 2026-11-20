// The design guard: finds brand values written anywhere except tokens.css. Lives outside src/
// because its own tests must contain the literals it hunts for.

export type Finding = { file: string; line: number; rule: string; text: string };

// CSS Color Module 4 named colours (148 incl. grey/gray aliases and rebeccapurple).
export const NAMED_COLOURS = (
  "aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet brown " +
  "burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan " +
  "darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid darkred " +
  "darksalmon darkseagreen darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink " +
  "deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite gold " +
  "goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki lavender lavenderblush " +
  "lawngreen lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow lightgray lightgreen lightgrey " +
  "lightpink lightsalmon lightseagreen lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime " +
  "limegreen linen magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen " +
  "mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin " +
  "navajowhite navy oldlace olive olivedrab orange orangered orchid palegoldenrod palegreen paleturquoise " +
  "palevioletred papayawhip peachpuff peru pink plum powderblue purple rebeccapurple red rosybrown royalblue " +
  "saddlebrown salmon sandybrown seagreen seashell sienna silver skyblue slateblue slategray slategrey snow " +
  "springgreen steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow yellowgreen"
).split(" ");

const NAMED = new RegExp(`(^|[^\\w-])(${NAMED_COLOURS.join("|")})(?![\\w-])`, "i");
const PALETTE =
  "slate|gray|zinc|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|white|black";
const PREFIX = "bg|text|border|ring-offset|ring|outline|fill|stroke|from|via|to|divide|placeholder|caret|accent|decoration|shadow";

const RULES: { rule: string; re: RegExp }[] = [
  { rule: "hex colour", re: /(^|[^\w&])#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![\w-])/ },
  { rule: "colour function", re: /\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(/ },
  { rule: "font family", re: /\bInter\b|Space Grotesk|system-ui|sans-serif|\bserif\b|monospace|Helvetica|Arial|Roboto|Segoe/ },
  // A font-family whose value is anything but one var(--token).
  { rule: "font family", re: /font-family\s*:(?!\s*var\(--[\w-]+\)\s*[;}])|fontFamily\s*:(?!\s*["'`]var\(--[\w-]+\)["'`])/ },
  // `neutral` is our token (text-neutral); Tailwind's neutral palette always has a shade.
  { rule: "tailwind palette class", re: new RegExp(`(^|[^\\w-])(?:[\\w-]+:)*(?:${PREFIX})-(?:(?:${PALETTE})(?![\\w-])|(?:${PALETTE}|neutral)-\\d)`) },
  // A Tailwind variant is `dark:` glued to a class; `dark: Record<…>` in a type is not one.
  { rule: "dark: variant", re: /(^|[\s"'`{])dark:[\w[!-]/ },
];

/** Named colours inside a Tailwind arbitrary value, e.g. bg-[white] / text-[red]. */
function namedInBrackets(line: string): boolean {
  for (const m of line.matchAll(/\[([^\]]*)\]/g)) if (NAMED.test(m[1])) return true;
  return false;
}

/** Named colours as the value of a colour property, in TS/JSX (`color: "white"`, `fillStyle = "black"`,
 *  `fill="white"`) or CSS (`color: navy;`). transparent/currentColor/inherit/… are not in the list. */
function namedInColourProperty(line: string): boolean {
  const props = "color|background|backgroundColor|background-color|borderColor|border-color|fill|stroke|fillStyle|strokeStyle|outlineColor|outline-color";
  const quoted = new RegExp(`(?:^|[^\\w-])(?:${props})\\s*[:=]\\s*\\{?\\s*["'\`]([^"'\`]*)["'\`]`, "g");
  for (const m of line.matchAll(quoted)) if (NAMED.test(m[1])) return true;
  const bare = new RegExp(`(?:^|[^\\w-])(?:${props})\\s*:\\s*([^;}"'\`]+)[;}]`, "g");
  for (const m of line.matchAll(bare)) if (NAMED.test(m[1])) return true;
  return false;
}

export function scanText(file: string, text: string): Finding[] {
  const out: Finding[] = [];
  text.split("\n").forEach((line, i) => {
    const hit = new Set(RULES.filter(({ re }) => re.test(line)).map(({ rule }) => rule));
    for (const rule of hit) out.push({ file, line: i + 1, rule, text: line.trim() });
    if (namedInBrackets(line)) out.push({ file, line: i + 1, rule: "named colour in arbitrary value", text: line.trim() });
    if (namedInColourProperty(line)) out.push({ file, line: i + 1, rule: "named colour value", text: line.trim() });
  });
  return out;
}

/** fonts.css may name the families only inside its @font-face declarations; blank those lines
 *  (keeping line numbers) and scan the rest like any other file. */
export function withoutFontFaces(css: string): string {
  return css.replace(/@font-face\s*\{[^}]*\}/g, (block) => block.replace(/[^\n]/g, " "));
}
