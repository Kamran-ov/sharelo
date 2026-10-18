import { api, ApiError } from "./api";

function mockFetch(...responses: Response[]) {
  const fn = vi.fn();
  responses.forEach((r) => fn.mockResolvedValueOnce(r));
  vi.stubGlobal("fetch", fn);
  return fn;
}
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});
afterEach(() => vi.unstubAllGlobals());

test("post_sends_csrf_header_from_cookie", async () => {
  document.cookie = "csrftoken=abc";
  const fetchMock = mockFetch(json({ ok: true }));
  await api("POST", "/groups/", { name: "x" });
  const init = fetchMock.mock.calls[0][1] as RequestInit;
  expect((init.headers as Record<string, string>)["X-CSRFToken"]).toBe("abc");
});

test("get_sends_no_csrf_header", async () => {
  document.cookie = "csrftoken=abc";
  const fetchMock = mockFetch(json({}));
  await api("GET", "/me");
  const init = fetchMock.mock.calls[0][1] as RequestInit;
  expect(init.headers).not.toHaveProperty("X-CSRFToken");
});

test("missing_csrf_cookie_triggers_me_fetch_once", async () => {
  const fetchMock = vi
    .fn()
    .mockImplementationOnce(async () => {
      document.cookie = "csrftoken=fresh";
      return json({});
    })
    .mockResolvedValueOnce(json({ ok: 1 }));
  vi.stubGlobal("fetch", fetchMock);
  await api("POST", "/auth/login", {});
  expect(fetchMock.mock.calls.map((c) => c[0])).toEqual(["/api/me", "/api/auth/login"]);
  expect(((fetchMock.mock.calls[1][1] as RequestInit).headers as Record<string, string>)["X-CSRFToken"]).toBe("fresh");
});

test("present_csrf_cookie_needs_no_extra_fetch", async () => {
  document.cookie = "csrftoken=abc";
  const fetchMock = mockFetch(json({}));
  await api("POST", "/auth/login", {});
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("error_body_maps_to_typed_api_error", async () => {
  mockFetch(json({ code: "weak_password", detail: "Too short." }, 400));
  await expect(api("GET", "/x")).rejects.toMatchObject({
    status: 400,
    code: "weak_password",
    detail: "Too short.",
  });
  mockFetch(json({ code: "weak_password", detail: "Too short." }, 400));
  await expect(api("GET", "/x")).rejects.toBeInstanceOf(ApiError);
});

test("ok_body_returns_parsed_json", async () => {
  mockFetch(json({ a: 1 }));
  await expect(api("GET", "/x")).resolves.toEqual({ a: 1 });
});

test("non_json_error_maps_to_network_code", async () => {
  mockFetch(new Response("<html>bad gateway</html>", { status: 502 }));
  await expect(api("GET", "/x")).rejects.toMatchObject({ status: 502, code: "network" });
});
