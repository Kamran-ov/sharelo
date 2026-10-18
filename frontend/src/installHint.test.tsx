import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import InstallHint from "./components/InstallHint";

const IOS = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1";
const DESKTOP = "Mozilla/5.0 (X11; Linux x86_64) Chrome/120";

afterEach(() => localStorage.clear());

describe("install hint", () => {
  it("test_install_hint_ios_shows_share_instructions", () => {
    render(<InstallHint userAgent={IOS} standalone={false} />);
    expect(screen.getByText(/Add to Home Screen/)).toBeInTheDocument();
  });

  it("test_install_hint_hidden_when_standalone", () => {
    render(<InstallHint userAgent={IOS} standalone />);
    expect(screen.queryByRole("region", { name: "Install Sharelo" })).toBeNull();
  });

  it("test_install_hint_absent_without_ios_or_prompt", () => {
    render(<InstallHint userAgent={DESKTOP} standalone={false} />);
    expect(screen.queryByRole("region", { name: "Install Sharelo" })).toBeNull();
  });

  it("test_install_hint_android_uses_captured_beforeinstallprompt", () => {
    render(<InstallHint userAgent={DESKTOP} standalone={false} />);
    const event = Object.assign(new Event("beforeinstallprompt", { cancelable: true }), { prompt: vi.fn() });
    fireEvent(window, event);
    fireEvent.click(screen.getByRole("button", { name: "Install Sharelo" }));
    expect(event.prompt).toHaveBeenCalledOnce();
    expect(event.defaultPrevented).toBe(true);
  });

  it("test_install_hint_dismissal_is_remembered_and_survives_blocked_storage", () => {
    const first = render(<InstallHint userAgent={IOS} standalone={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    first.unmount();
    render(<InstallHint userAgent={IOS} standalone={false} />);
    expect(screen.queryByRole("region", { name: "Install Sharelo" })).toBeNull();

    localStorage.clear();
    const blocked = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    render(<InstallHint userAgent={IOS} standalone={false} />);
    fireEvent.click(screen.getAllByRole("button", { name: "Dismiss" })[0]);
    expect(blocked).toHaveBeenCalled();
    vi.restoreAllMocks();
  });
});
