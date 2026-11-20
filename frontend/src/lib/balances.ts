import type { SettlementRow } from "../api";
import { formatCents } from "./money";

export type Tone = "owed" | "owe" | "settled";

/** The top card for "me" in parts (words, then figure): `net` is the server's number for my
 *  member, never recomputed here. */
export function topCardParts(net: number): { tone: Tone; label: string; figure: string | null } {
  if (net > 0) return { tone: "owed", label: "you are owed", figure: formatCents(net) };
  if (net < 0) return { tone: "owe", label: "you owe", figure: formatCents(-net) };
  return { tone: "settled", label: "all settled", figure: null };
}

export function topCardText(net: number): { tone: Tone; text: string } {
  const { tone, label, figure } = topCardParts(net);
  return { tone, text: figure === null ? label : `${label} ${figure}` };
}

/** Both lines name the transfer's debtor as the one who owes: the twin row runs the other way. */
export function moveToHomeLines(tripName: string, debtor: string, creditor: string, cents: number) {
  const amount = formatCents(cents);
  return {
    trip: `In ${tripName}: ${debtor} pays ${creditor} ${amount} — settles the trip`,
    home: `In Home: ${debtor} owes ${creditor} ${amount}`,
  };
}

/** "Rome trip: moved to Home" on both sides; the Home row learns the trip's name from its twin. */
export function moveBadge(row: Pick<SettlementRow, "twin" | "twin_group_name" | "is_home_side">, ownGroupName: string): string | null {
  if (row.twin === null || row.twin === undefined) return null;
  const trip = row.is_home_side ? row.twin_group_name : ownGroupName;
  return `${trip}: moved to Home`;
}
