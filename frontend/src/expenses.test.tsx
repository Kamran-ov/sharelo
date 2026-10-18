import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";

import type { ExpenseRow, GroupDetail } from "./api";
import CategoryPicker from "./components/CategoryPicker";
import Toast from "./components/Toast";
import Expenses from "./pages/Expenses";
import Settings from "./pages/Settings";

const group = {
  id: 1,
  name: "Home",
  currency: "EUR",
  is_main: true,
  link_active: null,
  share_token: "tok",
  my_member_id: 1,
  members: [
    { id: 1, display_name: "Ann", profile_id: 1, is_guest: false },
    { id: 2, display_name: "Bea", profile_id: 2, is_guest: false },
  ],
} as unknown as GroupDetail;

const tree = [
  { id: 10, name: "Food and drink", children: [{ id: 11, name: "Dining out" }, { id: 12, name: "Groceries" }] },
  { id: 20, name: "Uncategorized", children: [{ id: 21, name: "General" }] },
];

const row = (over: Partial<ExpenseRow> = {}): ExpenseRow =>
  ({
    id: 5,
    description: "Rent",
    amount_cents: 4210,
    currency: "EUR",
    original_amount_cents: null,
    original_currency: null,
    rate_used: "1.00000000",
    date: "2026-10-01",
    category: 12,
    split_type: "equal",
    source: "manual",
    notes: "",
    payers: [{ member: 1, paid_cents: 4210 }],
    splits: [{ member: 1, owed_cents: 2105 }, { member: 2, owed_cents: 2105 }],
    created_at: "",
    ...over,
  }) as ExpenseRow;

interface Call {
  method: string;
  path: string;
  body: Record<string, unknown> | null;
}

/** Routes `/api/...` to canned JSON; records every call. */
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

function baseRoutes(rows: ExpenseRow[] = [], extra: Parameters<typeof mockApi>[0] = {}) {
  return {
    "GET /me": () => ({ json: {} }),
    "GET /categories/": () => ({ json: tree }),
    "GET /groups/1/category-defaults/": () => ({ json: {} }),
    "GET /groups/1/expenses/": () => ({ json: { count: rows.length, page: 1, month_totals: { "2026-10": 4210 }, results: rows } }),
    ...extra,
  };
}

function renderPage(page: "expenses" | "settings" = "expenses") {
  document.cookie = "csrftoken=tok";
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/g/1/" + page]}>
        <Routes>
          <Route path="/g/1" element={<Outlet context={group} />}>
            <Route path="expenses" element={<Expenses />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function openAdd() {
  const plus = await screen.findByLabelText("Add expense");
  await waitFor(() => expect(plus).toBeEnabled());
  fireEvent.click(plus);
  return screen.findByRole("dialog", { name: "New expense" });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

test("test_amount_sent_to_api_is_an_integer_from_the_sheet", async () => {
  const calls = mockApi(baseRoutes([], { "POST /groups/1/expenses/": () => ({ status: 201, json: row({ id: 77 }) }) }));
  renderPage();
  await openAdd();
  fireEvent.change(screen.getByLabelText(/Amount/), { target: { value: "42,10" } });
  fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Pizza" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
  const post = calls.find((c) => c.method === "POST")!;
  expect(post.body).toMatchObject({ amount_cents: 4210, preset: "half", category: 21, payer_member: 1, description: "Pizza" });
  expect(Number.isInteger(post.body!.amount_cents)).toBe(true);
});

test("test_undo_sends_delete_within_five_seconds", async () => {
  const calls = mockApi(
    baseRoutes([], {
      "POST /groups/1/expenses/": () => ({ status: 201, json: row({ id: 77 }) }),
      "DELETE /groups/1/expenses/77/": () => ({ status: 204 }),
    }),
  );
  renderPage();
  await openAdd();
  fireEvent.change(screen.getByLabelText(/Amount/), { target: { value: "5" } });
  fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Tea" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  fireEvent.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  expect(calls.find((c) => c.method === "DELETE")!.path).toBe("/groups/1/expenses/77/");
  expect(calls.some((c) => c.path.includes("/-"))).toBe(false);
});

test("test_pending_row_is_not_tappable_and_toast_waits_for_server_id", async () => {
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  const calls = mockApi(baseRoutes([], { "POST /groups/1/expenses/": () => ({ status: 201, json: row({ id: 77 }) }) }));
  const real = globalThis.fetch;
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    if (init?.method === "POST" && url.endsWith("/expenses/")) await gate;
    return real(url, init);
  });
  renderPage();
  await openAdd();
  fireEvent.change(screen.getByLabelText(/Amount/), { target: { value: "5" } });
  fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Tea" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  const pending = await screen.findByText("saving…");
  expect(pending.closest("li")).toHaveAttribute("aria-busy", "true");
  expect(within(pending.closest("li")!).queryByRole("button")).toBeNull();
  expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
  await act(async () => release());
  expect(await screen.findByRole("button", { name: "Undo" })).toBeInTheDocument();
  expect(calls.filter((c) => c.method === "POST")).toHaveLength(1);
});

test("test_toast_goes_away_after_five_seconds_without_delete", () => {
  vi.useFakeTimers();
  const onUndo = vi.fn();
  const onDone = vi.fn();
  render(<Toast message="Saved" onUndo={onUndo} onDone={onDone} />);
  act(() => void vi.advanceTimersByTime(4999));
  expect(onDone).not.toHaveBeenCalled();
  act(() => void vi.advanceTimersByTime(2));
  expect(onDone).toHaveBeenCalledTimes(1);
  expect(onUndo).not.toHaveBeenCalled();
});

test("test_save_disabled_without_rate_until_manual_rate_typed", async () => {
  mockApi(
    baseRoutes([], {
      "GET /groups/1/rate/": () => ({ status: 400, json: { code: "no_rate", detail: "GBP" } }),
    }),
  );
  renderPage();
  await openAdd();
  fireEvent.change(screen.getByLabelText(/Amount/), { target: { value: "10" } });
  fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Tea" } });
  fireEvent.click(screen.getByText("Advanced"));
  fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "GBP" } });
  expect(await screen.findByRole("alert")).toHaveTextContent("No rate for GBP");
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Manual rate"), { target: { value: "1,17" } });
  expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  expect(screen.getByTestId("converted")).toHaveTextContent("≈ 11.70 EUR");
});

test("test_save_enabled_with_rate_shows_converted_preview", async () => {
  mockApi(baseRoutes([], { "GET /groups/1/rate/": () => ({ json: { currency: "USD", date: "x", rate: "0.90909091" } }) }));
  renderPage();
  await openAdd();
  fireEvent.change(screen.getByLabelText(/Amount/), { target: { value: "100" } });
  fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Tea" } });
  fireEvent.click(screen.getByText("Advanced"));
  fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "USD" } });
  expect(await screen.findByText("≈ 90.91 EUR")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
});

test("test_row_with_two_payers_opens_read_only_and_sends_no_patch", async () => {
  const multi = row({ payers: [{ member: 1, paid_cents: 2000 }, { member: 2, paid_cents: 2210 }] });
  const calls = mockApi(baseRoutes([multi]));
  renderPage();
  fireEvent.click(await screen.findByText("Rent"));
  expect(await screen.findByText("multiple payers — edit not supported yet")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
  expect(calls.some((c) => c.method === "PATCH")).toBe(false);
});

test("test_single_payer_row_edit_sends_the_patch", async () => {
  const calls = mockApi(baseRoutes([row()], { "PATCH /groups/1/expenses/5/": () => ({ json: row() }) }));
  renderPage();
  fireEvent.click(await screen.findByText("Rent"));
  const dialog = await screen.findByRole("dialog", { name: "Edit expense" });
  fireEvent.change(within(dialog).getByLabelText("Description"), { target: { value: "Rent!" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
  expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ description: "Rent!", date: "2026-10-01", category: 12 });
});

test("test_description_suggestion_fills_its_category_and_default_split", async () => {
  mockApi(
    baseRoutes([row({ description: "Weekly shop", category: 12 })], {
      "GET /groups/1/category-defaults/": () => ({ json: { "12": { preset: "personal", params: {} } } }),
    }),
  );
  renderPage();
  await screen.findByText("Weekly shop");
  const dialog = within(await openAdd());
  fireEvent.click(dialog.getByRole("button", { name: "Weekly shop" }));
  expect(dialog.getByLabelText("Description")).toHaveValue("Weekly shop");
  expect(dialog.getByRole("button", { name: /Food and drink › Groceries/ })).toBeInTheDocument();
  expect(dialog.getByRole("button", { name: "Only me" })).toHaveAttribute("aria-pressed", "true");
});

test("test_category_picker_orders_children_by_use_then_seed_order", () => {
  const onPick = vi.fn();
  render(<CategoryPicker tree={tree} counts={new Map([[12, 3]])} current={12} onPick={onPick} />);
  const options = screen.getAllByRole("option").map((o) => o.textContent);
  expect(options).toEqual(["Groceries", "Dining out"]);
  expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Food and drink", "Uncategorized"]);
  fireEvent.click(screen.getByRole("option", { name: "Dining out" }));
  expect(onPick).toHaveBeenCalledWith(11);
});

test("test_settings_percent_default_roundtrips_percent_payer", async () => {
  const calls = mockApi({
    "GET /categories/": () => ({ json: tree }),
    "GET /groups/1/category-defaults/": () => ({ json: {} }),
    "PUT /groups/1/category-defaults/": () => ({ json: {} }),
  });
  renderPage("settings");
  const select = await screen.findByLabelText("Default split for Food and drink › Groceries");
  fireEvent.change(select, { target: { value: "custom" } });
  await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
  expect(calls.find((c) => c.method === "PUT")!.body).toEqual({ "12": { preset: "percentage", params: { percent_payer: 50 } } });
});

test("test_settings_unmapped_default_is_preserved_in_put", async () => {
  const exact = { preset: "exact", params: { cents: { "1": 100 } } };
  const calls = mockApi({
    "GET /categories/": () => ({ json: tree }),
    "GET /groups/1/category-defaults/": () => ({ json: { "11": exact } }),
    "PUT /groups/1/category-defaults/": () => ({ json: {} }),
  });
  renderPage("settings");
  expect(await screen.findByRole("option", { name: "Other (kept)" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Default split for Food and drink › Groceries"), { target: { value: "personal" } });
  await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
  expect(calls.find((c) => c.method === "PUT")!.body).toEqual({ "11": exact, "12": { preset: "personal", params: {} } });
});

test("test_month_total_comes_from_the_api_not_the_loaded_rows", async () => {
  mockApi(baseRoutes([row({ amount_cents: 100 })]));
  renderPage();
  expect(await screen.findByTestId("month-total-2026-10")).toHaveTextContent("42.10 EUR");
});

test("test_default_chip_is_general_in_a_group_without_expenses", async () => {
  mockApi(baseRoutes([]));
  renderPage();
  await openAdd();
  expect(screen.getByRole("button", { name: /Uncategorized › General/ })).toBeInTheDocument();
});
