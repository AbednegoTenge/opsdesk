import { afterEach, describe, expect, it } from "vitest";

import { apiBaseUrl } from "./config";

describe("apiBaseUrl", () => {
  afterEach(() => {
    delete window.__OPSDESK_CONFIG__;
  });

  it("uses the build-time value by default", () => {
    expect(apiBaseUrl()).toBe("http://localhost:3000/api/v1");
  });

  it("prefers runtime config and trims trailing slashes", () => {
    window.__OPSDESK_CONFIG__ = { apiBaseUrl: "https://api.example.com/api/v1/" };
    expect(apiBaseUrl()).toBe("https://api.example.com/api/v1");
  });
});
