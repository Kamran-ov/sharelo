import type { components } from "./api/types";

export type Schemas = components["schemas"];
export type Me = Schemas["Me"];
export type GroupSummary = Schemas["GroupSummary"];
export type GroupDetail = Schemas["GroupDetail"];
export type JoinPreview = Schemas["JoinPreview"];
export type JoinResult = Schemas["JoinResult"];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly detail: string,
  ) {
    super(detail || code);
  }
}

function csrfToken(): string | null {
  const match = document.cookie.split("; ").find((c) => c.startsWith("csrftoken="));
  return match ? decodeURIComponent(match.slice("csrftoken=".length)) : null;
}

async function send(method: string, path: string, body: unknown, token: string | null) {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && token) headers["X-CSRFToken"] = token;
  try {
    return await fetch(`/api${path}`, {
      method,
      headers,
      credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network", "Cannot reach the server");
  }
}

export async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  let token = csrfToken();
  if (method !== "GET" && token === null) {
    // GET /api/me is what sets the csrftoken cookie.
    await send("GET", "/me", undefined, null);
    token = csrfToken();
  }
  const res = await send(method, path, body, token);
  if (res.ok) return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
  let code = "network";
  let detail = res.statusText;
  try {
    const err = (await res.json()) as { code?: string; detail?: string };
    code = err.code ?? code;
    detail = err.detail ?? detail;
  } catch {
    // non-JSON error body (proxy error page): keep the generic network code
  }
  throw new ApiError(res.status, code, detail);
}
