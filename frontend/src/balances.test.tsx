import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";

import type { GroupDetail } from "./api";
import { UNDO_MS } from "./components/Toast";
import { moveBadge, moveToHomeLines, topCardText } from "./lib/balances";
import { parseAmountForSubmit } from "./lib/money";
import Balances from "./pages/Balances";

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

function renderPage() {
  document.cookie = "csrftoken=tok";
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
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
