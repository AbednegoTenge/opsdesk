import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Role } from "@/api/types";
import { renderApp } from "@/test/render";
import { HttpResponse, http } from "msw";

import { page } from "@/test/fixtures";
import { API, backend, makeUser, server } from "@/test/server";

async function navLabels(role: Role) {
  backend.refreshUser = makeUser(role);
  renderApp("/");
  const nav = await screen.findByRole("navigation", { name: "Main" });
  return within(nav)
    .getAllByRole("link")
    .map((link) => link.textContent);
}

describe("role-aware navigation", () => {
  it("shows a viewer only the read-only pages", async () => {
    expect(await navLabels("viewer")).toEqual(["Dashboard", "Incidents"]);
  });

  it("adds reports for an engineer", async () => {
    expect(await navLabels("engineer")).toEqual(["Dashboard", "Incidents", "Reports"]);
  });

  it("shows an admin everything", async () => {
    expect(await navLabels("admin")).toEqual([
      "Dashboard",
      "Incidents",
      "Reports",
      "Users",
      "SLA policies",
    ]);
  });

  it.each([
    ["viewer", "/reports"],
    ["viewer", "/users"],
    ["engineer", "/users"],
    ["engineer", "/settings/sla"],
  ] as const)("blocks a %s from %s", async (role, path) => {
    backend.refreshUser = makeUser(role);
    renderApp(path);
    expect(
      await screen.findByRole("heading", { name: "You don't have access to this page" }),
    ).toBeInTheDocument();
  });

  it("lets an admin open admin pages", async () => {
    backend.refreshUser = makeUser("admin");
    server.use(http.get(`${API}/users/`, () => HttpResponse.json(page([]))));
    renderApp("/users");
    expect(await screen.findByRole("heading", { name: "Users" })).toBeInTheDocument();
  });

  it("shows a not-found page for unknown paths", async () => {
    backend.refreshUser = makeUser("viewer");
    renderApp("/nope");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});
