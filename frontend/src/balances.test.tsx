import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";

import type { GroupDetail } from "./api";
import { UNDO_MS } from "./components/Toast";
import { moveBadge, moveToHomeLines, topCardText } from "./lib/balances";
import { parseAmountForSubmit } from "./lib/money";
import Balances from "./pages/Balances";

vi.mock("./lib/summaryImage", () => ({ renderSummaryPng: vi.fn(async () => new Blob(["png"], { type: "image/png" })) }));

const group = {
  id: 7,
  name: "Rome trip",
  currency: "EUR",
  is_main: false,
  link_active: true,
  share_token: "tok",
  my_member_id: 2,
  members: [
    { id: 1, display_name: "Alice" },
    { id: 2, display_name: "Bea" },
  ],
} as unknown as GroupDetail;

interface Call {
  method: string;
  path: string;
  body: Record<string, unknown> | null;
}

function mockApi(routes: Record<string, (call: Call) => { status?: number; json?: unknown }>) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = url.replace(/^\/api/, "");
      const call: Call = { method: init?.method ?? "GET", path, body: init?.body ? JSON.parse(init.body as string) : null };
      calls.push(call);
      const key = Object.keys(routes).find((k) => `${call.method} ${path}`.startsWith(k));
      const res = key ? routes[key](call) : { status: 404, json: { code: "not_found", detail: "no route" } };
      const status = res.status ?? 200;
      return new Response(status === 204 ? null : JSON.stringify(res.json ?? {}), { status });
    }),
  );
  return calls;
}

const balances = (canMove: boolean) => ({
  currency: "EUR",
  nets: { "1": 20000, "2": -20000 },
  transfers: [{ from_member: 2, to_member: 1, amount_cents: 20000, can_move_to_home: canMove, to_profile: 11 }],
  members: [
    { member_id: 1, paid: 0, owed_share: 0, net: 20000 },
    { member_id: 2, paid: 0, owed_share: 0, net: -20000 },
  ],
});

const routes = (canMove = false, extra: Parameters<typeof mockApi>[0] = {}) => ({
  "GET /me": () => ({ json: {} }),
  "GET /groups/7/balances/": () => ({ json: balances(canMove) }),
  "GET /groups/7/settlements/": () => ({ json: [] }),
  ...extra,
});

function renderPage(client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  document.cookie = "csrftoken=tok";
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/g/7/balances"]}>
        <Routes>
          <Route path="/g/7" element={<Outlet context={group} />}>
            <Route path="balances" element={<Balances />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const navProps: string[] = [];
function setNavigator(props: Record<string, unknown>) {
  for (const [key, value] of Object.entries(props)) {
    Object.defineProperty(navigator, key, { value, configurable: true, writable: true });
    navProps.push(key);
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  for (const key of navProps.splice(0)) delete (navigator as unknown as Record<string, unknown>)[key];
});

test("test_top_card_wording_positive_negative_zero", () => {
  expect(topCardText(8420)).toEqual({ tone: "owed", text: "you are owed 84.20" });
  expect(topCardText(-1200)).toEqual({ tone: "owe", text: "you owe 12.00" });
  expect(topCardText(0)).toEqual({ tone: "settled", text: "all settled" });
  expect(topCardText(5).text).toBe("you are owed 0.05");
});

test("test_settle_parse_accepts_zero_rejects_junk", () => {
  expect(["0", "0.00", "0,0", "12,50", "21.05"].map(parseAmountForSubmit)).toEqual([0, 0, 0, 1250, 2105]);
  expect(["", "abc", "12.345", "-3", "1,234.50"].map(parseAmountForSubmit)).toEqual([null, null, null, null, null]);
});

test("test_move_to_home_preview_names_the_transfer_debtor_on_both_lines", () => {
  const lines = moveToHomeLines("Rome trip", "Bea", "Alice", 20000);
  expect(lines.trip).toBe("In Rome trip: Bea pays Alice 200.00 — settles the trip");
  expect(lines.home).toBe("In Home: Bea owes Alice 200.00");
});

test("test_history_badge_reads_trip_name_moved_to_home_on_each_side", () => {
  expect(moveBadge({ twin: 9, twin_group_name: "Home", is_home_side: false }, "Rome trip")).toBe("Rome trip: moved to Home");
  expect(moveBadge({ twin: 9, twin_group_name: "Rome trip", is_home_side: true }, "Home")).toBe("Rome trip: moved to Home");
  expect(moveBadge({ twin: null, twin_group_name: null, is_home_side: false }, "Home")).toBeNull();
});

test("test_move_to_home_button_follows_can_move_to_home_flag", async () => {
  mockApi(routes(true));
  const { unmount } = renderPage();
  expect(await screen.findByRole("button", { name: "Move to Home" })).toBeInTheDocument();
  unmount();
  mockApi(routes(false));
  renderPage();
  await screen.findByRole("button", { name: "Settle" });
  expect(screen.queryByRole("button", { name: "Move to Home" })).toBeNull();
});

test("test_settle_sheet_prefills_transfer_and_sends_integer_amount", async () => {
  const calls = mockApi(routes(false, { "POST /groups/7/settlements/": () => ({ status: 201, json: { id: 40 } }) }));
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: "Settle" }));
  const amount = screen.getByLabelText(/Amount/) as HTMLInputElement;
  expect(amount.value).toBe("200.00");
  fireEvent.click(within(screen.getByRole("dialog", { name: "Settle up" })).getByRole("button", { name: "Settle" }));
  await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
  const post = calls.find((c) => c.method === "POST")!;
  expect(post.body).toMatchObject({ from_member: 2, to_member: 1, amount_cents: 20000 });
  expect(Number.isInteger(post.body!.amount_cents)).toBe(true);
});

test("test_settle_zero_shows_server_error_inline", async () => {
  const calls = mockApi(
    routes(false, { "POST /groups/7/settlements/": () => ({ status: 400, json: { code: "amount_not_positive", detail: "amount_cents=0" } }) }),
  );
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: "Settle" }));
  fireEvent.change(screen.getByLabelText(/Amount/), { target: { value: "0.00" } });
  const dialog = screen.getByRole("dialog", { name: "Settle up" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Settle" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("amount_cents=0");
  expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({ amount_cents: 0 });
  expect(calls.filter((c) => c.path === "/groups/7/balances/")).toHaveLength(1);
});

async function settleFully() {
  const calls = mockApi(
    routes(false, {
      "POST /groups/7/settlements/": () => ({ status: 201, json: { id: 40 } }),
      "DELETE /groups/7/settlements/40/": () => ({ status: 204 }),
    }),
  );
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: "Settle" }));
  const dialog = screen.getByRole("dialog", { name: "Settle up" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Settle" }));
  await screen.findByRole("status");
  return calls;
}

test("test_undo_deletes_the_server_id_within_five_seconds", async () => {
  const calls = await settleFully();
  fireEvent.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  expect(calls.find((c) => c.method === "DELETE")!.path).toBe("/groups/7/settlements/40/");
});

test("test_toast_goes_away_without_delete", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const calls = await settleFully();
  act(() => {
    vi.advanceTimersByTime(UNDO_MS + 100);
  });
  expect(screen.queryByRole("status")).toBeNull();
  expect(calls.some((c) => c.method === "DELETE")).toBe(false);
});

// ---- 018: share the summary ----

const summary = (total: number) => ({
  group: { id: 7, name: "Rome trip" },
  currency: "EUR",
  total_spent_cents: total,
  per_member: [
    { member_id: 1, display_name: "Alice", paid: total, owed_share: total / 2, net: total / 2 },
    { member_id: 2, display_name: "Bea", paid: 0, owed_share: total / 2, net: -total / 2 },
  ],
  transfers: [{ from_member: 2, to_member: 1, amount_cents: total / 2 }],
  recent_expenses: [{ id: 1, date: "2026-11-12", description: "Dinner", amount_cents: total, paid_by: [1] }],
});
const TEXT_4000 = "Rome trip — total 40.00 EUR\n\nBea pays Alice 20.00\n\nLast expenses:\n12 Nov Dinner 40.00 (Alice)";

async function openShare() {
  fireEvent.click(await screen.findByRole("button", { name: "Share" }));
  const sheet = await screen.findByRole("dialog", { name: "Share summary" });
  const text = within(sheet).getByRole("button", { name: "Share as text" });
  await waitFor(() => expect(text).toBeEnabled());
  return sheet;
}

test("test_share_uses_web_share_when_available", async () => {
  mockApi(routes(false, { "GET /groups/7/summary/": () => ({ json: summary(4000) }) }));
  const share = vi.fn(async () => undefined);
  setNavigator({ share });
  renderPage();
  const sheet = await openShare();
  fireEvent.click(within(sheet).getByRole("button", { name: "Share as text" }));
  await waitFor(() => expect(share).toHaveBeenCalledWith({ text: TEXT_4000 }));
  expect(screen.queryByRole("status")).toBeNull();
});

test("test_share_falls_back_to_clipboard_and_toasts", async () => {
  mockApi(routes(false, { "GET /groups/7/summary/": () => ({ json: summary(4000) }) }));
  const writeText = vi.fn(async () => undefined);
  setNavigator({ clipboard: { writeText } });
  renderPage();
  const sheet = await openShare();
  fireEvent.click(within(sheet).getByRole("button", { name: "Share as text" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Copied to clipboard");
  expect(writeText).toHaveBeenCalledWith(TEXT_4000);
  expect(screen.queryByRole("textbox", { name: "Summary text" })).toBeNull();
});

test("test_share_cancel_shows_no_toast", async () => {
  mockApi(routes(false, { "GET /groups/7/summary/": () => ({ json: summary(4000) }) }));
  const share = vi.fn(async () => {
    throw new DOMException("cancelled", "AbortError");
  });
  const writeText = vi.fn(async () => undefined);
  setNavigator({ share, clipboard: { writeText } });
  renderPage();
  const sheet = await openShare();
  fireEvent.click(within(sheet).getByRole("button", { name: "Share as text" }));
  await waitFor(() => expect(share).toHaveBeenCalled());
  await act(async () => {});
  expect(writeText).not.toHaveBeenCalled();
  expect(screen.queryByRole("status")).toBeNull();
});

test("test_share_without_share_or_clipboard_shows_text_to_copy", async () => {
  mockApi(routes(false, { "GET /groups/7/summary/": () => ({ json: summary(4000) }) }));
  setNavigator({ share: undefined, clipboard: undefined });
  renderPage();
  const sheet = await openShare();
  fireEvent.click(within(sheet).getByRole("button", { name: "Share as text" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Could not share — copy the text below");
  expect(within(sheet).getByRole("textbox", { name: "Summary text" })).toHaveValue(TEXT_4000);
});

test("test_share_clipboard_rejection_shows_text_to_copy", async () => {
  mockApi(routes(false, { "GET /groups/7/summary/": () => ({ json: summary(4000) }) }));
  setNavigator({ clipboard: { writeText: vi.fn(async () => Promise.reject(new Error("denied"))) } });
  renderPage();
  const sheet = await openShare();
  fireEvent.click(within(sheet).getByRole("button", { name: "Share as text" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Could not share — copy the text below");
  expect(within(sheet).getByRole("textbox", { name: "Summary text" })).toHaveValue(TEXT_4000);
});

test("test_share_buttons_disabled_while_summary_refetches", async () => {
  // The cache is seeded with an old summary, as if a previous opening had left it there.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["summary", 7], summary(4000));
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  mockApi(routes(false));
  const fetchMock = vi.mocked(fetch);
  const routed = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation(async (url, init) => {
    if (String(url).endsWith("/groups/7/summary/")) {
      await held;
      return new Response(JSON.stringify(summary(6000)), { status: 200 });
    }
    return routed(url as string, init);
  });
  const share = vi.fn(async () => undefined);
  setNavigator({ share });
  renderPage(client);
  fireEvent.click(await screen.findByRole("button", { name: "Share" }));
  const sheet = await screen.findByRole("dialog", { name: "Share summary" });
  const textButton = within(sheet).getByRole("button", { name: "Share as text" });
  const imageButton = within(sheet).getByRole("button", { name: "Share as image" });
  expect(client.getQueryData(["summary", 7])).toEqual(summary(4000));
  expect(textButton).toBeDisabled();
  expect(imageButton).toBeDisabled();
  fireEvent.click(textButton);
  expect(share).not.toHaveBeenCalled();
  release();
  await waitFor(() => expect(textButton).toBeEnabled());
  await waitFor(() => expect(imageButton).toBeEnabled());
  fireEvent.click(textButton);
  await waitFor(() => expect(share).toHaveBeenCalledTimes(1));
  expect(share).toHaveBeenCalledWith({
    text: "Rome trip — total 60.00 EUR\n\nBea pays Alice 30.00\n\nLast expenses:\n12 Nov Dinner 60.00 (Alice)",
  });
});

test("test_share_image_downloads_when_file_sharing_unsupported", async () => {
  mockApi(routes(false, { "GET /groups/7/summary/": () => ({ json: summary(4000) }) }));
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() }));
  const clicked: string[] = [];
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    clicked.push(this.download);
  });
  renderPage();
  const sheet = await openShare();
  const imageButton = within(sheet).getByRole("button", { name: "Share as image" });
  await waitFor(() => expect(imageButton).toBeEnabled());
  fireEvent.click(imageButton);
  expect(await screen.findByRole("status")).toHaveTextContent("Image downloaded");
  expect(clicked).toEqual(["rome-trip-summary.png"]);
  click.mockRestore();
});
