import { describe, expect, it, vi } from "vitest";
import { onUnauthorized, notifyUnauthorized } from "../api/authEvents";

describe("authEvents", () => {
  it("calls every subscribed listener on notify", () => {
    const a = vi.fn();
    const b = vi.fn();
    const offA = onUnauthorized(a);
    const offB = onUnauthorized(b);
    notifyUnauthorized();
    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(1);
    offA();
    offB();
  });

  it("stops calling a listener after it unsubscribes", () => {
    const a = vi.fn();
    const off = onUnauthorized(a);
    off();
    notifyUnauthorized();
    expect(a).not.toHaveBeenCalled();
  });

  it("a second subscribe/unsubscribe cycle doesn't affect other listeners", () => {
    const a = vi.fn();
    const b = vi.fn();
    const offA = onUnauthorized(a);
    onUnauthorized(b);
    offA();
    offA(); // idempotent
    notifyUnauthorized();
    expect(a).not.toHaveBeenCalled();
    expect(b).toHaveBeenCalledTimes(1);
  });
});
