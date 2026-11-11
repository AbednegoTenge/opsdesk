import { describe, expect, it } from "vitest";

import { describeEvent, formatDuration, formatMinutes, formatRelative, TRANSITIONS } from "./format";

describe("formatDuration", () => {
  it.each([
    [null, "—"],
    [45, "45s"],
    [60, "1m"],
    [5400, "1h 30m"],
    [7200, "2h"],
    [86_400, "1d"],
    [200_000, "2d 7h"],
  ])("%s -> %s", (seconds, expected) => {
    expect(formatDuration(seconds)).toBe(expected);
  });

  it("formats SLA minutes", () => {
    expect(formatMinutes(1440)).toBe("1d");
    expect(formatMinutes(null)).toBe("—");
  });
});

describe("formatRelative", () => {
  const now = Date.parse("2026-11-11T12:00:00Z");
  it("describes past and future times", () => {
    expect(formatRelative("2026-11-11T11:55:00Z", now)).toBe("5 minutes ago");
    expect(formatRelative("2026-11-11T15:00:00Z", now)).toBe("in 3 hours");
    expect(formatRelative("2026-11-11T12:00:20Z", now)).toBe("now");
    expect(formatRelative(null, now)).toBe("—");
  });
});

describe("describeEvent", () => {
  it.each([
    ["status_changed", { from: "open", to: "in_progress", note: "" }, "moved from Open to In progress"],
    ["status_changed", { from: "in_progress", to: "resolved", note: "Fixed" }, "moved from In progress to Resolved: “Fixed”"],
    ["priority_changed", { from: "low", to: "critical" }, "changed priority from Low to Critical"],
    ["assigned", { from: null, to: { id: 1, email: "a@x.test" } }, "assigned to a@x.test"],
    ["unassigned", { from: { id: 1, email: "a@x.test" }, to: null }, "unassigned a@x.test"],
    ["updated", { fields: { title: {}, description: { changed: true } } }, "updated the title and description"],
    ["sla_breached", { target: "response" }, "breached the response SLA"],
  ] as const)("%s", (type, data, expected) => {
    expect(describeEvent(type, data as Record<string, unknown>)).toBe(expected);
  });
});

describe("TRANSITIONS", () => {
  it("never offers a no-op move", () => {
    for (const [from, targets] of Object.entries(TRANSITIONS)) {
      expect(targets).not.toContain(from);
    }
  });
});
