import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";

import { api, type GroupDetail, type ShareSummary } from "../api";
import Sheet from "../components/Sheet";
import Toast from "../components/Toast";
import { shareImage, shareText, type ImageOutcome, type TextOutcome } from "../lib/share";
import { renderSummaryPng } from "../lib/summaryImage";
import { summaryLines, summaryText } from "../lib/summaryText";

const NOTICE: Partial<Record<TextOutcome | ImageOutcome, string>> = {
  copied: "Copied to clipboard",
  downloaded: "Image downloaded",
  manual: "Could not share — copy the text below",
};

function fileName(groupName: string): string {
  const slug = groupName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return `${slug || "group"}-summary.png`;
}

/**
 * Mounted only while open. Freshness rule: every opening refetches (staleTime 0, gcTime 0,
 * refetchOnMount "always") and the buttons stay disabled while fetching, so whatever changed
 * since the last share is in what gets shared. The PNG is drawn from that fetch's data only.
 */
export default function ShareSheet({ group, onClose }: { group: GroupDetail; onClose: () => void }) {
  const summary = useQuery({
    queryKey: ["summary", group.id],
    queryFn: () => api<ShareSummary>("GET", `/groups/${group.id}/summary/`),
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: "always",
  });
  const [png, setPng] = useState<{ at: number; blob: Blob } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [manualText, setManualText] = useState<string | null>(null);
  const fresh = summary.isSuccess && !summary.isFetching;
  const { data, dataUpdatedAt } = summary;

  useEffect(() => {
    if (!fresh || !data) return;
    let live = true;
    renderSummaryPng(summaryLines(data)).then(
      (blob) => live && setPng({ at: dataUpdatedAt, blob }),
      () => live && setPng(null),
    );
    return () => {
      live = false;
    };
  }, [fresh, data, dataUpdatedAt]);

  const report = (outcome: TextOutcome | ImageOutcome) => setNotice(NOTICE[outcome] ?? null);
  const closeNotice = useCallback(() => setNotice(null), []);

  const onText = () => {
    if (!data) return;
    const text = summaryText(data);
    void shareText(text).then((outcome) => {
      setManualText(outcome === "manual" ? text : null);
      report(outcome);
    });
  };
  const imageReady = fresh && png !== null && png.at === dataUpdatedAt;
  const onImage = () => {
    if (!png) return;
    void shareImage(png.blob, fileName(group.name)).then(report);
  };

  return (
    <Sheet title="Share summary" onClose={onClose}>
      {summary.isError && <p role="alert">Could not load the summary.</p>}
      <div className="flex flex-col gap-3">
        <button type="button" disabled={!fresh} onClick={onText} className="min-h-11 rounded bg-emerald-700 px-3 font-semibold text-white disabled:opacity-50">
          Share as text
        </button>
        <button type="button" disabled={!imageReady} onClick={onImage} className="min-h-11 rounded border border-emerald-700 px-3 font-semibold text-emerald-800 disabled:opacity-50">
          Share as image
        </button>
        {manualText !== null && (
          <textarea
            aria-label="Summary text"
            readOnly
            value={manualText}
            rows={Math.min(14, manualText.split("\n").length + 1)}
            ref={(el) => el?.select()}
            className="w-full rounded border border-slate-300 p-2 font-mono text-sm"
          />
        )}
      </div>
      {notice && <Toast message={notice} onDone={closeNotice} />}
    </Sheet>
  );
}
