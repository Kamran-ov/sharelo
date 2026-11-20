import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useLocation, useOutletContext } from "react-router-dom";

import { api, ApiError, type CategoryNode, type GroupDetail, type RuleOut } from "../api";
import { Button, ErrorText, Fab, IconTile } from "../components/ui";
import { formatCents } from "../lib/money";
import { describeRule } from "../lib/recurrence";
import { splitText, toRuleLike, type RuleLike } from "../lib/ruleBody";
import RuleSheet from "./RuleSheet";

type SheetState = { kind: "add" } | { kind: "edit"; rule: RuleLike } | null;
type Confirm = { id: number; kind: "skip" | "delete" } | null;

const errorText = (e: unknown) => (e instanceof ApiError ? e.detail || e.code : "Something went wrong");
const small = "min-h-11 rounded-md border border-line bg-card px-3 text-sm font-medium";

export default function Recurring() {
  const group = useOutletContext<GroupDetail>();
  const qc = useQueryClient();
  const { hash } = useLocation();
  const [sheet, setSheet] = useState<SheetState>(null);
  const [confirm, setConfirm] = useState<Confirm>(null);
  const [sheetError, setSheetError] = useState<string | null>(null);
  const [rowError, setRowError] = useState<{ id: number; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const base = `/groups/${group.id}/recurring`;

  const rulesQuery = useQuery({ queryKey: ["rules", group.id], queryFn: () => api<RuleOut[]>("GET", `${base}/`) });
  const tree = useQuery({ queryKey: ["categories"], queryFn: () => api<CategoryNode[]>("GET", "/categories/") });
  const rules = useMemo(() => (rulesQuery.data ?? []).map(toRuleLike), [rulesQuery.data]);

  useEffect(() => {
    if (rules.length > 0 && hash.startsWith("#rule-")) document.getElementById(hash.slice(1))?.scrollIntoView?.({ block: "center" });
  }, [hash, rules.length]);

  const memberName = (id: number) => group.members.find((m) => m.id === id)?.display_name ?? "?";
  const refresh = () => qc.invalidateQueries({ queryKey: ["rules", group.id] });

  const save = async (body: Record<string, unknown>) => {
    setBusy(true);
    setSheetError(null);
    try {
      if (sheet?.kind === "edit") await api("PATCH", `${base}/${sheet.rule.id}/`, body);
      else await api("POST", `${base}/`, body);
      await refresh();
      setSheet(null);
    } catch (e) {
      setSheetError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const act = async (rule: RuleLike, run: () => Promise<unknown>) => {
    setBusy(true);
    setRowError(null);
    setConfirm(null);
    try {
      await run();
      await refresh();
    } catch (e) {
      setRowError({ id: rule.id, text: errorText(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="px-5 pb-4">
      {rulesQuery.isPending && <p className="pt-2 text-muted">Loading…</p>}
      {rulesQuery.isError && <p role="alert" className="pt-2">Could not load recurring expenses.</p>}
      {rulesQuery.isSuccess && rules.length === 0 && <p className="pt-2 text-muted">No recurring expenses yet.</p>}
      <ul className="overflow-hidden rounded-card border border-line bg-card empty:hidden [&>li+li]:border-t [&>li+li]:border-line-subtle">
        {rules.map((rule) => (
          <li
            key={rule.id}
            id={`rule-${rule.id}`}
            data-testid="rule-row"
            data-highlight={hash === `#rule-${rule.id}` ? "true" : "false"}
            className={`space-y-2 px-4 py-3.5 ${hash === `#rule-${rule.id}` ? "bg-highlight-soft" : ""}`}
          >
            <div className="flex items-center gap-3">
              <IconTile name="repeat" />
              <span className="min-w-0 flex-1 break-words font-semibold">
                {rule.description}
                {rule.paused && <span className="ml-2 rounded-pill bg-sunken px-2 py-0.5 text-xs font-medium text-muted">Paused</span>}
              </span>
              <span className="shrink-0 font-heading font-semibold" data-testid="rule-amount">
                {formatCents(rule.amount_cents)}
              </span>
            </div>
            <div className="text-sm text-muted">
              <span className="break-words">{describeRule(rule)}</span> · next <span data-testid="next-date">{rule.next_date}</span>
            </div>
            <div className="break-words text-sm text-muted">
              {memberName(rule.payer)} paid · {splitText(rule, group.members.length)}
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" className={small} onClick={() => { setSheetError(null); setSheet({ kind: "edit", rule }); }}>
                Edit
              </button>
              <button
                type="button"
                className={small}
                disabled={busy}
                onClick={() => act(rule, () => api("POST", `${base}/${rule.id}/${rule.paused ? "resume" : "pause"}`))}
              >
                {rule.paused ? "Resume" : "Pause"}
              </button>
              <button type="button" className={small} onClick={() => { setRowError(null); setConfirm({ id: rule.id, kind: "skip" }); }}>
                Skip next
              </button>
              <button type="button" className={`${small} border-danger text-danger`} onClick={() => { setRowError(null); setConfirm({ id: rule.id, kind: "delete" }); }}>
                Delete
              </button>
            </div>
            {confirm?.id === rule.id && (
              <div role="alertdialog" aria-label={confirm.kind === "skip" ? "Confirm skip" : "Confirm delete"} className="space-y-2 rounded-card border border-line bg-ground p-3">
                <p className="break-words">
                  {confirm.kind === "skip"
                    ? `Skip ${rule.next_date}? No expense is created for that date.`
                    : "Delete this recurring expense? Expenses it already created stay."}
                </p>
                <div className="flex gap-2">
                  <Button className="flex-1" onClick={() => setConfirm(null)}>
                    Keep
                  </Button>
                  <button
                    type="button"
                    className="min-h-11 flex-1 rounded-md bg-primary font-medium text-on-primary"
                    disabled={busy}
                    onClick={() => act(rule, () => (confirm.kind === "skip" ? api("POST", `${base}/${rule.id}/skip`) : api("DELETE", `${base}/${rule.id}/`)))}
                  >
                    {confirm.kind === "skip" ? "Skip it" : "Delete it"}
                  </button>
                </div>
              </div>
            )}
            {rowError?.id === rule.id && (
              <ErrorText>{rowError.text}</ErrorText>
            )}
          </li>
        ))}
      </ul>
      <div className="pointer-events-none sticky bottom-24 flex justify-end pt-4">
        <Fab label="Add recurring expense" disabled={!tree.data} onClick={() => { setSheetError(null); setSheet({ kind: "add" }); }} />
      </div>
      {sheet && tree.data && (
        <RuleSheet
          key={sheet.kind === "edit" ? sheet.rule.id : "add"}
          group={group}
          tree={tree.data}
          editing={sheet.kind === "edit" ? sheet.rule : undefined}
          error={sheetError}
          busy={busy}
          onSubmit={save}
          onClose={() => setSheet(null)}
        />
      )}
    </section>
  );
}
