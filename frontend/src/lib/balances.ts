import type { SettlementRow } from "../api";
import { formatCents } from "./money";

export type Tone = "owed" | "owe" | "settled";

/** The top card for "me": `net` is the server's number for my member, never recomputed here. */
export function topCardText(net: number): { tone: Tone; text: string } {
  if (net > 0) return { tone: "owed", text: `you are owed ${formatCents(net)}` };
  if (net < 0) return { tone: "owe", text: `you owe ${formatCents(-net)}` };
  return { tone: "settled", text: "all settled" };
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
