import { describe, expect, it } from "vitest";

import { bridgeAuthorized } from "../src/auth.js";

describe("bridge route authentication", () => {
  it("requires the configured bearer token and fails closed when unset", () => {
    const request = (token?: string) => new Request("http://127.0.0.1/forecast/discover", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    expect(bridgeAuthorized(request("bridge-token"), "bridge-token")).toBe(true);
    expect(bridgeAuthorized(request("wrong"), "bridge-token")).toBe(false);
    expect(bridgeAuthorized(request(), "bridge-token")).toBe(false);
    expect(bridgeAuthorized(request("bridge-token"), undefined)).toBe(false);
  });
});
