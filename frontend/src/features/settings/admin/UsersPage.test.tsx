import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../../api/client/api";
import { ApiError } from "../../../api/client/errors";
import type {
  AdminUserListResponse,
  UserResponse,
} from "../../../api/generated/types.gen";
import { UsersPage } from "./UsersPage";

vi.mock("../../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    adminUsers: vi.fn(),
    createAdminUser: vi.fn(),
    updateAdminUser: vi.fn(),
    deleteAdminUser: vi.fn(),
  },
}));

const now = "2026-08-24T08:30:00Z";
const currentUser: UserResponse = {
  id: "admin-1",
  email: "admin@journiv.test",
  name: "Ada Admin",
  role: "admin",
  is_active: true,
  created_at: now,
  updated_at: now,
};
const localUser: AdminUserListResponse = {
  id: currentUser.id,
  email: currentUser.email,
  name: currentUser.name ?? "Ada Admin",
  role: "admin",
  is_active: true,
  last_login_at: now,
  created_at: now,
  login_type: "local",
};
const oidcUser: AdminUserListResponse = {
  id: "user-2",
  email: "robin@example.com",
  name: "Robin Reader",
  role: "user",
  is_active: false,
  last_login_at: null,
  created_at: now,
  login_type: "oidc",
  linked_providers: ["https://login.example.com/realms/journiv"],
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <UsersPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.me).mockResolvedValue(currentUser);
  vi.mocked(api.adminUsers).mockResolvedValue([localUser, oidcUser]);
  vi.mocked(api.createAdminUser).mockResolvedValue(currentUser);
  vi.mocked(api.updateAdminUser).mockResolvedValue(currentUser);
  vi.mocked(api.deleteAdminUser).mockResolvedValue({});
});

describe("Administration users", () => {
  it("renders backend account metadata and filters the complete list locally", async () => {
    renderPage();

    expect(await screen.findByText("Ada Admin")).toBeTruthy();
    expect(screen.getByText("robin@example.com")).toBeTruthy();
    expect(screen.getByText("login.example.com")).toBeTruthy();
    expect(screen.getByText("Never")).toBeTruthy();
    expect(screen.getByText("2 accounts")).toBeTruthy();

    await userEvent.type(
      screen.getByRole("textbox", { name: "Search users" }),
      "OIDC",
    );
    expect(screen.queryByText("Ada Admin")).toBeNull();
    expect(screen.getByText("Robin Reader")).toBeTruthy();
    expect(screen.getByText("1 account")).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: "Clear search" }));
    expect(screen.getByText("Ada Admin")).toBeTruthy();
  });

  it("validates a new local account before creating it and refreshes the list", async () => {
    renderPage();
    await screen.findByText("Ada Admin");
    await userEvent.click(screen.getByRole("button", { name: "Add user" }));
    await userEvent.click(screen.getByRole("button", { name: "Create user" }));

    expect(screen.getByText("Enter a display name.")).toBeTruthy();
    expect(screen.getByText("Enter a valid email address.")).toBeTruthy();
    expect(screen.getByText("Enter a temporary password.")).toBeTruthy();
    expect(api.createAdminUser).not.toHaveBeenCalled();

    await userEvent.type(
      screen.getByLabelText("Display name"),
      "  New Writer  ",
    );
    await userEvent.type(screen.getByLabelText("Email"), "WRITER@example.com");
    await userEvent.type(
      screen.getByLabelText("Temporary password"),
      "journal8pass",
    );
    await userEvent.click(screen.getByRole("button", { name: "Create user" }));

    await waitFor(() =>
      expect(api.createAdminUser).toHaveBeenCalledWith({
        name: "New Writer",
        email: "writer@example.com",
        password: "journal8pass",
        role: "user",
      }),
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Add user" })).toBeTruthy(),
    );
    expect(api.adminUsers).toHaveBeenCalledTimes(2);
  });

  it("edits OIDC account fields without offering ambiguous password conversion", async () => {
    renderPage();
    await screen.findByText("Robin Reader");
    await userEvent.click(
      screen.getByRole("button", { name: "Robin Reader actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Edit" }),
    );

    expect(screen.getByText(/signs in through OIDC/)).toBeTruthy();
    expect(screen.queryByLabelText("New password")).toBeNull();

    const name = screen.getByLabelText("Display name");
    await userEvent.clear(name);
    await userEvent.type(name, "Robin Updated");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(api.updateAdminUser).toHaveBeenCalledWith(oidcUser.id, {
        name: "Robin Updated",
      }),
    );
  });

  it("updates active status from the row action and reports a refused write", async () => {
    vi.mocked(api.updateAdminUser).mockRejectedValueOnce(new Error("offline"));
    renderPage();
    await screen.findByText("Robin Reader");
    await userEvent.click(
      screen.getByRole("button", { name: "Robin Reader actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Activate" }),
    );

    await waitFor(() =>
      expect(api.updateAdminUser).toHaveBeenCalledWith(oidcUser.id, {
        is_active: true,
      }),
    );
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Robin Reader couldn’t be activated",
    );
  });

  it("requires the exact email before permanently deleting an account", async () => {
    renderPage();
    await screen.findByText("Robin Reader");
    await userEvent.click(
      screen.getByRole("button", { name: "Robin Reader actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Delete" }),
    );

    const dialog = await screen.findByRole("dialog", {
      name: "Delete Robin Reader?",
    });
    const confirm = within(dialog).getByLabelText(/Type .* to confirm/);
    const remove = within(dialog).getByRole("button", { name: "Delete user" });
    expect((remove as HTMLButtonElement).disabled).toBe(true);

    await userEvent.type(confirm, "wrong@example.com");
    expect((remove as HTMLButtonElement).disabled).toBe(true);
    expect(api.deleteAdminUser).not.toHaveBeenCalled();

    await userEvent.clear(confirm);
    await userEvent.type(confirm, oidcUser.email);
    expect((remove as HTMLButtonElement).disabled).toBe(false);
    await userEvent.click(remove);

    await waitFor(() =>
      expect(api.deleteAdminUser).toHaveBeenCalledWith(oidcUser.id),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("hides deactivate and delete on the signed-in admin's own row", async () => {
    // Default fixtures: the signed-in admin is also the only active admin.
    renderPage();
    await screen.findByText("Ada Admin");
    await userEvent.click(
      screen.getByRole("button", { name: "Ada Admin actions" }),
    );

    expect(await screen.findByRole("menuitem", { name: "Edit" })).toBeTruthy();
    expect(screen.queryByRole("menuitem", { name: /deactivate/i })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: /delete/i })).toBeNull();
  });

  it("surfaces the backend's reason when a write is refused", async () => {
    const secondAdmin: AdminUserListResponse = {
      ...localUser,
      id: "admin-2",
      email: "bee@journiv.test",
      name: "Bee Admin",
    };
    vi.mocked(api.adminUsers).mockResolvedValue([localUser, secondAdmin]);
    vi.mocked(api.updateAdminUser).mockRejectedValueOnce(
      new ApiError(
        "Cannot deactivate the last admin user. At least one active admin must exist.",
        { status: 400 },
      ),
    );
    renderPage();
    await screen.findByText("Bee Admin");
    await userEvent.click(
      screen.getByRole("button", { name: "Bee Admin actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Deactivate" }),
    );

    expect((await screen.findByRole("alert")).textContent).toContain(
      "At least one active admin must exist",
    );
  });
});
