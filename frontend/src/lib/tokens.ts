/** Current value of a token from tokens.css (light or dark, whichever applies now) for places that
 *  cannot use var(), such as a canvas. Empty when no stylesheet is loaded (tests). */
export function tokenValue(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
