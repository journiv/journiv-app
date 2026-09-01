import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Pencil, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { setTestViewportWidth } from "../../test/viewport";
import { AppAdaptiveMenu, type AppMenuAction } from "./AppAdaptiveMenu";

const COMPACT = 390;
const REGULAR = 1440;

/** The link actions need a real router; the rest of the suite does not care. */
function renderWithRouter(ui: ReactNode) {
  const rootRoute = createRootRoute({ component: Outlet });
  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/",
    component: () => <>{ui}</>,
  });
  const timelineRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/timeline",
    component: () => <p>Timeline</p>,
  });
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute, timelineRoute]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  // biome-ignore lint/suspicious/noExplicitAny: a throwaway router for one test
  render(<RouterProvider router={router as any} />);
  return router;
}

function actions(over: Partial<Record<string, unknown>> = {}) {
  const onEdit = vi.fn();
  const onDelete = vi.fn();
  const list: AppMenuAction[] = [
    {
      kind: "link",
      id: "view",
      label: "View moments",
      link: { to: "/timeline" },
    },
    {
      kind: "command",
      id: "edit",
      label: "Rename",
      icon: Pencil,
      onSelect: onEdit,
    },
    {
      kind: "command",
      id: "delete",
      label: "Delete…",
      icon: Trash2,
      destructive: true,
      separatorBefore: true,
      onSelect: onDelete,
      ...over,
    },
  ];
  return { list, onEdit, onDelete };
}

describe("AppAdaptiveMenu", () => {
  it.each([
    ["regular", REGULAR],
    ["compact", COMPACT],
  ])("the trigger carries the accessible label (%s)", async (_n, width) => {
    setTestViewportWidth(width);
    const { list } = actions();
    renderWithRouter(<AppAdaptiveMenu label="Trips actions" actions={list} />);
    expect(
      await screen.findByRole("button", { name: "Trips actions" }),
    ).toBeTruthy();
  });

  it("renders nothing when there are no actions", () => {
    setTestViewportWidth(REGULAR);
    renderWithRouter(<AppAdaptiveMenu label="Trips actions" actions={[]} />);
    expect(screen.queryByRole("button", { name: "Trips actions" })).toBeNull();
  });

  it("exposes menu semantics in the regular presentation", async () => {
    setTestViewportWidth(REGULAR);
    const { list } = actions();
    renderWithRouter(<AppAdaptiveMenu label="Trips actions" actions={list} />);

    await userEvent.click(
      await screen.findByRole("button", { name: "Trips actions" }),
    );

    expect(await screen.findByRole("menu")).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Rename" })).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("exposes an action sheet, not a menu, in the compact presentation", async () => {
    setTestViewportWidth(COMPACT);
    const { list } = actions();
    renderWithRouter(<AppAdaptiveMenu label="Trips actions" actions={list} />);

    await userEvent.click(
      await screen.findByRole("button", { name: "Trips actions" }),
    );

    // A Drawer is not a menu container, so the rows are buttons and links in a
    // dialog named by the trigger's own label.
    expect(
      await screen.findByRole("dialog", { name: "Trips actions" }),
    ).toBeTruthy();
    expect(screen.queryByRole("menu")).toBeNull();
    expect(screen.getByRole("button", { name: "Rename" })).toBeTruthy();
  });

  it.each([
    ["regular", REGULAR],
    ["compact", COMPACT],
  ])("selecting an action invokes it exactly once (%s)", async (_n, width) => {
    setTestViewportWidth(width);
    const { list, onEdit } = actions();
    renderWithRouter(<AppAdaptiveMenu label="Trips actions" actions={list} />);

    await userEvent.click(
      await screen.findByRole("button", { name: "Trips actions" }),
    );
    await userEvent.click(await screen.findByText("Rename"));

    expect(onEdit).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["regular", REGULAR],
    ["compact", COMPACT],
  ])("a disabled action does not invoke onSelect (%s)", async (_n, width) => {
    setTestViewportWidth(width);
    const { list, onDelete } = actions({ disabled: true });
    renderWithRouter(<AppAdaptiveMenu label="Trips actions" actions={list} />);

    await userEvent.click(
      await screen.findByRole("button", { name: "Trips actions" }),
    );
    await userEvent.click(await screen.findByText("Delete…"), {
      pointerEventsCheck: 0,
    });

    expect(onDelete).not.toHaveBeenCalled();
  });

  it.each([
    ["regular", REGULAR],
    ["compact", COMPACT],
  ])("a destructive action keeps its own icon (%s)", async (_n, width) => {
    setTestViewportWidth(width);
    const { list } = actions();
    renderWithRouter(<AppAdaptiveMenu label="Trips actions" actions={list} />);

    await userEvent.click(
      await screen.findByRole("button", { name: "Trips actions" }),
    );
    const row = (await screen.findByText("Delete…")).closest(
      "[data-variant], button, a",
    );

    // Destructive is a treatment, not an icon override: the row still carries
    // the Trash2 glyph the caller supplied, and it is marked destructive by
    // more than colour alone.
    expect(row?.querySelector("svg")).toBeTruthy();
    expect(
      row?.getAttribute("data-variant") === "destructive" ||
        row?.className.includes("jv-sheet-action--destructive"),
    ).toBe(true);
  });

  it("navigates for a link action in the compact presentation", async () => {
    setTestViewportWidth(COMPACT);
    const { list } = actions();
    const router = renderWithRouter(
      <AppAdaptiveMenu label="Trips actions" actions={list} />,
    );

    await userEvent.click(
      await screen.findByRole("button", { name: "Trips actions" }),
    );
    await userEvent.click(await screen.findByText("View moments"));

    expect(await screen.findByText("Timeline")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/timeline");
  });

  it("navigates for a link action in the regular presentation", async () => {
    setTestViewportWidth(REGULAR);
    const { list } = actions();
    const router = renderWithRouter(
      <AppAdaptiveMenu label="Trips actions" actions={list} />,
    );

    await userEvent.click(
      await screen.findByRole("button", { name: "Trips actions" }),
    );
    await userEvent.click(await screen.findByText("View moments"));

    expect(await screen.findByText("Timeline")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/timeline");
  });
});
