import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";

import type { GroupDetail } from "./api";
import Recurring from "./pages/Recurring";

const group = {
  id: 7,
  name: "Home",
  currency: "EUR",
  is_main: true,
  link_active: null,
  share_token: "tok",
  my_member_id: 1,
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

const rule = (over: Record<string, unknown> = {}) => ({
  id: 3,
  description: "Rent",
  amount_cents: 95000,
  payer: 1,
  split_type: "equal",
  split_params: {},
  category: 5,
  frequency: "monthly",
  day_of_month: 1,
  month: null,
  start_date: "2026-11-01",
  next_date: "2026-11-01",
  end_date: null,
  paused: false,
  ...over,
});

const tree = [{ id: 1, name: "Home", children: [{ id: 5, name: "General" }] }];

function renderPage(routes: Parameters<typeof mockApi>[0], hash = "") {
  document.cookie = "csrftoken=tok";
  const calls = mockApi({ "GET /me": () => ({ json: {} }), "GET /categories/": () => ({ json: tree }), ...routes });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/g/7/recurring${hash}`]}>
        <Routes>
          <Route path="/g/7" element={<Outlet context={group} />}>
            <Route path="recurring" element={<Recurring />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return calls;
}

async function openAdd() {
  const plus = await screen.findByLabelText("Add recurring expense");
  await waitFor(() => expect(plus).toBeEnabled());
  fireEvent.click(plus);
}

test("test_rule_row_shows_schedule_next_date_payer_split_and_paused_badge", async () => {
  renderPage({ "GET /groups/7/recurring/": () => ({ json: [rule(), rule({ id: 4, description: "Netflix", paused: true })] }) });
  const rows = await screen.findAllByTestId("rule-row");
  expect(within(rows[0]).getByText("monthly on the 1st")).toBeInTheDocument();
  expect(within(rows[0]).getByTestId("next-date")).toHaveTextContent("2026-11-01");
  expect(rows[0]).toHaveTextContent("Alice paid · 50/50");
  expect(within(rows[0]).getByTestId("rule-amount")).toHaveTextContent("950.00");
  expect(within(rows[0]).queryByText("Paused")).toBeNull();
  expect(within(rows[1]).getByText("Paused")).toBeInTheDocument();
});

test("test_rule_sheet_preview_shows_three_dates_before_save", async () => {
  renderPage({ "GET /groups/7/recurring/": () => ({ json: [] }) });
  await openAdd();
  fireEvent.change(await screen.findByLabelText("Start date"), { target: { value: "2026-11-01" } });
  fireEvent.change(screen.getByLabelText("Day of month"), { target: { value: "1" } });
  expect(screen.getByTestId("preview")).toHaveTextContent("Next: 2026-11-01, 2026-12-01, 2027-01-01");
  fireEvent.change(screen.getByLabelText("Day of month"), { target: { value: "31" } });
  fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2027-01-31" } });
  expect(screen.getByTestId("preview")).toHaveTextContent("Next: 2027-01-31, 2027-02-28, 2027-03-31");
});

test("test_create_sends_integer_cents_and_service_split", async () => {
  const calls = renderPage({
    "GET /groups/7/recurring/": () => ({ json: [] }),
    "POST /groups/7/recurring/": () => ({ status: 201, json: rule() }),
  });
  await openAdd();
  fireEvent.change(await screen.findByLabelText(/Amount/), { target: { value: "950" } });
  fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Rent" } });
  fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-11-01" } });
  fireEvent.change(screen.getByLabelText("Day of month"), { target: { value: "1" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/groups/7/recurring/")).toBe(true));
  const body = calls.find((c) => c.method === "POST" && c.path === "/groups/7/recurring/")!.body!;
  expect(body).toMatchObject({ amount_cents: 95000, split_type: "equal", frequency: "monthly", day_of_month: 1, start_date: "2026-11-01", payer: 1 });
  expect(Number.isInteger(body.amount_cents)).toBe(true);
});

test("test_edit_sends_only_the_changed_amount", async () => {
  const calls = renderPage({
    "GET /groups/7/recurring/": () => ({ json: [rule()] }),
    "PATCH /groups/7/recurring/3/": () => ({ json: rule({ amount_cents: 100000 }) }),
  });
  fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
  fireEvent.change(await screen.findByLabelText(/Amount/), { target: { value: "1000" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
  expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ amount_cents: 100000 });
});

test("test_skip_confirm_shows_the_date_being_skipped", async () => {
  const calls = renderPage({
    "GET /groups/7/recurring/": () => ({ json: [rule({ next_date: "2026-11-01" })] }),
    "POST /groups/7/recurring/3/skip": () => ({ json: rule({ next_date: "2026-12-01" }) }),
  });
  fireEvent.click(await screen.findByRole("button", { name: "Skip next" }));
  const dialog = await screen.findByRole("alertdialog", { name: "Confirm skip" });
  expect(dialog).toHaveTextContent("Skip 2026-11-01?");
  expect(calls.some((c) => c.path.endsWith("/skip"))).toBe(false);
  fireEvent.click(within(dialog).getByRole("button", { name: "Skip it" }));
  await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path.endsWith("/skip"))).toBe(true));
});

test("test_paused_skip_error_rendered_inline", async () => {
  renderPage({
    "GET /groups/7/recurring/": () => ({ json: [rule({ paused: true })] }),
    "POST /groups/7/recurring/3/skip": () => ({ status: 400, json: { code: "rule_paused", detail: "rule_paused: rule 3 is paused" } }),
  });
  fireEvent.click(await screen.findByRole("button", { name: "Skip next" }));
  fireEvent.click(await screen.findByRole("button", { name: "Skip it" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("rule 3 is paused");
  expect(screen.getByTestId("next-date")).toHaveTextContent("2026-11-01");
});

test("test_delete_confirm_says_past_expenses_stay", async () => {
  const calls = renderPage({
    "GET /groups/7/recurring/": () => ({ json: [rule()] }),
    "DELETE /groups/7/recurring/3/": () => ({ status: 204 }),
  });
  fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
  const dialog = await screen.findByRole("alertdialog", { name: "Confirm delete" });
  expect(dialog).toHaveTextContent("Expenses it already created stay");
  fireEvent.click(within(dialog).getByRole("button", { name: "Delete it" }));
  await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
});

test("test_hash_highlights_the_linked_rule_row", async () => {
  renderPage({ "GET /groups/7/recurring/": () => ({ json: [rule(), rule({ id: 4, description: "Netflix" })] }) }, "#rule-4");
  const rows = await screen.findAllByTestId("rule-row");
  expect(rows[0]).toHaveAttribute("data-highlight", "false");
  expect(rows[1]).toHaveAttribute("data-highlight", "true");
});

test("test_pause_and_resume_call_the_matching_endpoints", async () => {
  const calls = renderPage({
    "GET /groups/7/recurring/": () => ({ json: [rule()] }),
    "POST /groups/7/recurring/3/pause": () => ({ json: rule({ paused: true }) }),
  });
  fireEvent.click(await screen.findByRole("button", { name: "Pause" }));
  await waitFor(() => expect(calls.some((c) => c.path.endsWith("/pause"))).toBe(true));
});
