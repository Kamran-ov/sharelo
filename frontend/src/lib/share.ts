export type TextOutcome = "shared" | "cancelled" | "copied" | "manual";
export type ImageOutcome = "shared" | "cancelled" | "downloaded";

const isAbort = (e: unknown) => e instanceof DOMException && e.name === "AbortError";

/**
 * Web Share, then the clipboard, then "manual" (the caller shows the text to copy by hand).
 * Both APIs exist only in secure contexts, so plain-http serving lands on "manual".
 * Must be called inside the tap with no await before it: iOS drops share() after the gesture.
 */
export async function shareText(text: string): Promise<TextOutcome> {
  if (typeof navigator.share === "function") {
    try {
      await navigator.share({ text });
      return "shared";
    } catch (e) {
      if (isAbort(e)) return "cancelled";
    }
  }
  try {
    if (!navigator.clipboard?.writeText) return "manual";
    await navigator.clipboard.writeText(text);
    return "copied";
  } catch {
    return "manual";
  }
}

/** Shares the PNG as a file where the browser can, otherwise downloads it (works without HTTPS). */
export async function shareImage(blob: Blob, filename: string): Promise<ImageOutcome> {
  const file = new File([blob], filename, { type: "image/png" });
  if (typeof navigator.share === "function" && navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file] });
      return "shared";
    } catch (e) {
      if (isAbort(e)) return "cancelled";
    }
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return "downloaded";
}
