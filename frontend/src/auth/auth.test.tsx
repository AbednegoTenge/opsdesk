import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { renderApp } from "@/test/render";
import { backend, makeUser } from "@/test/server";

describe("sign-in flow", () => {
  it("sends a visitor without a session to the login page", async () => {
    renderApp("/incidents");
    expect(await screen.findByRole("heading", { name: "Sign in to OpsDesk" })).toBeInTheDocument();
  });

  it("signs in and returns to the page the user asked for", async () => {
    const user = userEvent.setup();
    renderApp("/incidents");

    await user.type(await screen.findByLabelText("Email"), "engineer@opsdesk.test");
    await user.type(screen.getByLabelText("Password"), backend.password);
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Incidents" })).toBeInTheDocument();
    expect(screen.getByText("Test engineer")).toBeInTheDocument();
  });

  it("shows an error for wrong credentials", async () => {
    const user = userEvent.setup();
    renderApp("/login");

    await user.type(await screen.findByLabelText("Email"), "engineer@opsdesk.test");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.");
  });

  it("restores the session from the refresh cookie on reload", async () => {
    backend.refreshUser = makeUser("admin");
    renderApp("/");

    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByText("Admin")).toBeInTheDocument();
  });

  it("offers a retry when the auth service is down instead of signing out", async () => {
    const user = userEvent.setup();
    backend.refreshUser = makeUser("engineer");
    backend.refreshStatus = 503;
    renderApp("/");

    expect(await screen.findByText("Sign-in is temporarily unavailable")).toBeInTheDocument();

    backend.refreshStatus = null;
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
  });

  it("signs out, revokes the refresh token and returns to the login page", async () => {
    const user = userEvent.setup();
    backend.refreshUser = makeUser("engineer");
    renderApp("/");

    await user.click(await screen.findByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("heading", { name: "Sign in to OpsDesk" })).toBeInTheDocument();
    expect(backend.logoutCalls).toBe(1);
    await waitFor(() => expect(backend.refreshUser).toBeNull());
  });
});
