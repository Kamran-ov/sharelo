import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { RequireAccess } from "./auth";
import GoogleButton from "./components/GoogleButton";
import { NewGroupSheet } from "./pages/Groups";

afterEach(() => vi.unstubAllGlobals());

const me = (over: object) => ({
  authenticated: false,
  profile: null,
  guest_memberships: [],
  google_enabled: false,
  ...over,
});

function mockMe(body: object) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })),
  );
}

function renderGuard() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/groups"]}>
        <Routes>
          <Route path="/login" element={<p>login page</p>} />
          <Route element={<RequireAccess />}>
            <Route path="/groups" element={<p>groups page</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("google_button_renders_only_when_enabled", () => {
  const { rerender } = render(<GoogleButton enabled onCredential={() => {}} />);
  expect(screen.getByTestId("google-button")).toBeInTheDocument();
  rerender(<GoogleButton enabled={false} onCredential={() => {}} />);
  expect(screen.queryByTestId("google-button")).not.toBeInTheDocument();
});

test("guard_redirects_anonymous_to_login", async () => {
  mockMe(me({}));
  renderGuard();
  expect(await screen.findByText("login page")).toBeInTheDocument();
});

test("guard_lets_guest_with_membership_through", async () => {
  mockMe(me({ guest_memberships: [7] }));
  renderGuard();
  expect(await screen.findByText("groups page")).toBeInTheDocument();
});

test("new_group_main_checkbox_disabled_when_profile_has_main_group", () => {
  const wrap = (hasMain: boolean) => (
    <QueryClientProvider client={new QueryClient()}>
      <NewGroupSheet hasMainGroup={hasMain} onClose={() => {}} />
    </QueryClientProvider>
  );
  const { unmount } = render(wrap(true));
  const boxed = screen.getByLabelText("Make this my main group") as HTMLInputElement;
  expect(boxed.disabled).toBe(true);
  expect(boxed.checked).toBe(false);
  unmount();
  render(wrap(false));
  const open = screen.getByLabelText("Make this my main group") as HTMLInputElement;
  expect(open.disabled).toBe(false);
  expect(open.checked).toBe(true);
});
