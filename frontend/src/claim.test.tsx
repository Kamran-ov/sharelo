import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";

import GroupShell from "./pages/GroupShell";
import Groups from "./pages/Groups";
import Join from "./pages/Join";
import Settings from "./pages/Settings";

afterEach(() => vi.unstubAllGlobals());

type Call = { method: string; url: string; body: unknown };
type Reply = { status?: number; body: unknown };

/** Route table keyed by "METHOD /path"; every request is recorded. */
function mockApi(routes: Record<string, Reply | ((call: Call) => Reply)>): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = init.method ?? "GET";
      const call = { method, url, body: init.body ? JSON.parse(String(init.body)) : undefined };
      calls.push(call);
      const path = url.replace(/^\/api/, "");
      const route = routes[`${method} ${path}`];
      const reply = typeof route === "function" ? route(call) : route;
      if (!reply) return new Response(JSON.stringify({ code: "not_found", detail: "" }), { status: 404 });
      return new Response(JSON.stringify(reply.body), { status: reply.status ?? 200 });
    }),
  );
  document.cookie = "csrftoken=t";
  return calls;
}

const guestMe = { authenticated: false, profile: null, guest_memberships: [11], guest_refused: [], google_enabled: false };
const userMe = {
  authenticated: true,
  profile: { id: 1, display_name: "Ann", email: "a@example.com", main_group_id: 1 },
  guest_memberships: [],
  guest_refused: [],
  google_enabled: false,
};

const member = (id: number, display_name: string, status: "joined" | "guest" | "unclaimed") => ({
  id,
  display_name,
  profile_id: status === "joined" ? id : null,
  is_guest: status !== "joined",
  status,
});

const flat = {
  id: 5,
  name: "Flat",
  currency: "EUR",
  is_main: false,
  link_active: null,
  share_token: "tok",
  members: [member(10, "Ann", "joined"), member(11, "Janet", "guest"), member(12, "Cami", "unclaimed")],
  my_member_id: 10,
};

function renderAt(path: string, routes: JSX.Element) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          {routes}
          <Route path="/g/:id/expenses" element={<p>expenses page</p>} />
          <Route path="/login" element={<p>login page</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const preview = (unclaimed: { id: number; display_name: string }[]) => ({
  group_name: "Flat",
  currency: "EUR",
  member_names: ["Ann", "Janet", "Cami"],
  unclaimed_members: unclaimed,
});

test("test_join_lists_unclaimed_names_and_claims_on_tap", async () => {
  const calls = mockApi({
    "GET /me": { body: guestMe },
    "GET /join/tok/": { body: preview([{ id: 11, display_name: "Janet" }, { id: 12, display_name: "Cami" }]) },
    "POST /join/tok/claim": { body: { group_id: 5, member_id: 11 } },
  });
  renderAt("/join/tok", <Route path="/join/:token" element={<Join />} />);
  expect(await screen.findByRole("heading", { name: "Are you one of these?" })).toBeInTheDocument();
  expect(screen.getByLabelText("Your name")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Janet" }));
  expect(await screen.findByText("expenses page")).toBeInTheDocument();
  const post = calls.find((c) => c.method === "POST");
  expect(post).toMatchObject({ url: "/api/join/tok/claim", body: { member_id: 11 } });
});

test("test_join_claim_conflict_shows_inline_error_and_refetches", async () => {
  let previews = 0;
  mockApi({
    "GET /me": { body: guestMe },
    "GET /join/tok/": () => {
      previews += 1;
      return { body: preview(previews === 1 ? [{ id: 11, display_name: "Janet" }] : []) };
    },
    "POST /join/tok/claim": { status: 400, body: { code: "member_already_claimed", detail: "member 11 is taken" } },
  });
  renderAt("/join/tok", <Route path="/join/:token" element={<Join />} />);
  fireEvent.click(await screen.findByRole("button", { name: "Janet" }));
  await waitFor(() => expect(previews).toBe(2));
  expect(screen.queryByRole("button", { name: "Janet" })).not.toBeInTheDocument();
  expect(screen.queryByText("expenses page")).not.toBeInTheDocument();
});

test("test_join_claim_conflict_message_is_the_server_detail", async () => {
  mockApi({
    "GET /me": { body: guestMe },
    "GET /join/tok/": { body: preview([{ id: 11, display_name: "Janet" }, { id: 12, display_name: "Cami" }]) },
    "POST /join/tok/claim": { status: 400, body: { code: "member_already_claimed", detail: "member 11 is taken" } },
  });
  renderAt("/join/tok", <Route path="/join/:token" element={<Join />} />);
  fireEvent.click(await screen.findByRole("button", { name: "Janet" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("member 11 is taken");
});

function SettingsRoute() {
  return <Outlet context={flat} />;
}

test("test_settings_member_status_labels", async () => {
  mockApi({ "GET /groups/5/recurring/status/": { body: { last_run_at: null } }, "GET /groups/5/category-defaults/": { body: {} }, "GET /categories/": { body: [] } });
  renderAt(
    "/g/5/settings",
    <Route element={<SettingsRoute />}>
      <Route path="/g/:id/settings" element={<Settings />} />
    </Route>,
  );
  expect(await screen.findByTestId("member-10")).toHaveTextContent("Ann (you) · joined");
  expect(screen.getByTestId("member-11")).toHaveTextContent("Janet · guest");
  expect(screen.getByTestId("member-12")).toHaveTextContent("Cami · not joined yet");
});

test("test_settings_add_person_posts_name_and_shows_name_taken", async () => {
  const calls = mockApi({
    "GET /groups/5/recurring/status/": { body: { last_run_at: null } },
    "GET /groups/5/category-defaults/": { body: {} },
    "GET /categories/": { body: [] },
    "POST /groups/5/members/": { status: 400, body: { code: "name_taken", detail: "'Janet' is already in group 5" } },
  });
  renderAt(
    "/g/5/settings",
    <Route element={<SettingsRoute />}>
      <Route path="/g/:id/settings" element={<Settings />} />
    </Route>,
  );
  fireEvent.change(await screen.findByLabelText("Add person"), { target: { value: "Janet" } });
  fireEvent.click(screen.getByRole("button", { name: "Add" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("'Janet' is already in group 5");
  expect(calls.find((c) => c.method === "POST")).toMatchObject({ url: "/api/groups/5/members/", body: { display_name: "Janet" } });
});

function shellRoutes() {
  return (
    <Route path="/g/:id" element={<GroupShell />}>
      <Route path="settings" element={<p>settings tab</p>} />
    </Route>
  );
}

test("test_guest_banner_shown_only_for_guest_session", async () => {
  mockApi({ "GET /me": { body: guestMe }, "GET /groups/5/": { body: { ...flat, my_member_id: 11 } } });
  renderAt("/g/5/settings", shellRoutes());
  expect(await screen.findByText("You're a guest. Create an account to keep access on any device.")).toBeInTheDocument();
});

test("test_guest_banner_absent_for_signed_in_user", async () => {
  mockApi({ "GET /me": { body: userMe }, "GET /groups/5/": { body: flat } });
  renderAt("/g/5/settings", shellRoutes());
  expect(await screen.findByText("settings tab")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByText(/You're a guest/)).not.toBeInTheDocument());
});

test("test_guest_sign_out_asks_for_confirmation", async () => {
  const calls = mockApi({
    "GET /me": { body: guestMe },
    "GET /groups/": { body: [{ id: 5, name: "Flat", currency: "EUR", is_main: false, link_active: null }] },
    "GET /groups/5/": { body: { ...flat, my_member_id: 11 } },
    "POST /auth/logout": { body: guestMe },
  });
  renderAt("/groups", <Route path="/groups" element={<Groups />} />);
  await screen.findByText("Flat");
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  const dialog = await screen.findByRole("dialog", { name: "Sign out" });
  expect(dialog).toHaveTextContent("You will lose access on this device. Save the group link or create an account first.");
  expect(await within(dialog).findByRole("button", { name: "Copy link" })).toBeInTheDocument();
  expect(calls.some((c) => c.method === "POST")).toBe(false);
  fireEvent.click(within(dialog).getByRole("button", { name: "Sign out anyway" }));
  expect(await screen.findByText("login page")).toBeInTheDocument();
});

test("test_signed_in_sign_out_does_not_ask", async () => {
  const calls = mockApi({
    "GET /me": { body: userMe },
    "GET /groups/": { body: [] },
    "POST /auth/logout": { body: guestMe },
  });
  renderAt("/groups", <Route path="/groups" element={<Groups />} />);
  await waitFor(() => expect(calls.some((c) => c.url === "/api/me")).toBe(true));
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  expect(await screen.findByText("login page")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
