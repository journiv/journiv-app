import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../../api/client/api";
import type {
  ExportJobListResponse,
  ExportJobStatusResponse,
  JournalResponse,
} from "../../../api/generated/types.gen";
import { setTestViewportWidth } from "../../../test/viewport";
import { ExportPage } from "./ExportPage";

vi.mock("../../../api/client/api", () => ({
  api: {
    cancelExport: vi.fn(),
    createExport: vi.fn(),
    exportStatus: vi.fn(),
    signExportUrl: vi.fn(),
    listExports: vi.fn(),
    deleteExport: vi.fn(),
    journals: vi.fn(),
  },
}));

const NOW = "2026-09-06T09:00:00Z";

function job(
  over: Partial<ExportJobStatusResponse> = {},
): ExportJobStatusResponse {
  return {
    id: "e1",
    status: "pending",
    progress: 0,
    total_items: 0,
    processed_items: 0,
    created_at: NOW,
    export_type: "full",
    include_media: true,
    ...over,
  };
}

function page(
  items: ExportJobStatusResponse[],
  next: string | null = null,
): ExportJobListResponse {
  return {
    items,
    next_cursor_created_at: next,
    next_cursor_id: next,
  };
}

function journal(over: Partial<JournalResponse> = {}): JournalResponse {
  return {
    id: "j1",
    title: "Journal",
    created_at: NOW,
    updated_at: NOW,
    user_id: "u1",
    is_favorite: false,
    is_archived: false,
    entry_count: 0,
    total_words: 0,
    ...over,
  };
}

function renderPage(node: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{node}</QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  setTestViewportWidth(1440);
  vi.mocked(api.listExports).mockResolvedValue(page([]));
  vi.mocked(api.journals).mockResolvedValue([]);
});

describe("Settings · Export", () => {
  it("reveals a journal checklist for a scoped export and posts the chosen ids", async () => {
    const user = userEvent.setup();
    vi.mocked(api.journals).mockResolvedValue([
      journal({ id: "j1", title: "Work" }),
      journal({ id: "j2", title: "Old diary", is_archived: true }),
    ]);
    vi.mocked(api.createExport).mockResolvedValue(job({ status: "pending" }));
    vi.mocked(api.exportStatus).mockResolvedValue(
      job({ status: "running", progress: 5 }),
    );

    renderPage(<ExportPage />);

    await user.click(
      await screen.findByRole("radio", { name: /Choose journals/ }),
    );
    // Archived journals are offered too, marked as such.
    expect(
      await screen.findByRole("checkbox", { name: /Old diary/ }),
    ).toBeTruthy();
    expect(screen.getByText(/Archived/)).toBeTruthy();

    await user.click(screen.getByRole("checkbox", { name: /Work/ }));
    await user.click(screen.getByRole("button", { name: "Create export" }));

    await waitFor(() =>
      expect(api.createExport).toHaveBeenCalledWith({
        export_type: "journal",
        include_media: true,
        journal_ids: ["j1"],
      }),
    );
  });

  it("shows the result stats and a download action once the export completes", async () => {
    const user = userEvent.setup();
    vi.mocked(api.createExport).mockResolvedValue(job({ status: "pending" }));
    vi.mocked(api.exportStatus).mockResolvedValue(
      job({
        status: "completed",
        progress: 100,
        processed_items: 10,
        total_items: 10,
        file_size: 2560,
        result_data: {
          journal_count: 2,
          entry_count: 10,
          media_count: 4,
          missing_media_count: 1,
        },
      }),
    );
    vi.mocked(api.signExportUrl).mockResolvedValue({
      signed_url: "https://example.test/download",
      expires_at: 0,
    });

    renderPage(<ExportPage />);
    await user.click(screen.getByRole("button", { name: "Create export" }));

    expect(await screen.findByText("10 entries")).toBeTruthy();
    expect(screen.getByText("1 media missing")).toBeTruthy();
    const link = await screen.findByRole("button", {
      name: "Download archive",
    });
    expect(link.getAttribute("href")).toBe("https://example.test/download");
  });

  it("blocks a new export while one is still running", async () => {
    vi.mocked(api.listExports).mockResolvedValue(
      page([job({ id: "e9", status: "running", progress: 40 })]),
    );
    vi.mocked(api.exportStatus).mockResolvedValue(
      job({ id: "e9", status: "running", progress: 40 }),
    );

    renderPage(<ExportPage />);

    await waitFor(() =>
      expect(
        (
          screen.getByRole("button", {
            name: "Create export",
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(true),
    );
  });

  it("cancels a running export from the history after confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(api.listExports).mockResolvedValue(
      page([job({ id: "e9", status: "running", progress: 40 })]),
    );
    vi.mocked(api.exportStatus).mockResolvedValue(
      job({ id: "e9", status: "running", progress: 40 }),
    );
    vi.mocked(api.cancelExport).mockResolvedValue(
      job({ id: "e9", status: "cancelled", progress: 40 }),
    );

    renderPage(<ExportPage />);

    await user.click(
      await screen.findByRole("button", { name: "Cancel export" }),
    );
    await user.click(await screen.findByRole("button", { name: "Cancel job" }));

    await waitFor(() => expect(api.cancelExport).toHaveBeenCalledWith("e9"));
  });

  it("confirms before cancelling the in-progress export from its panel", async () => {
    const user = userEvent.setup();
    vi.mocked(api.listExports).mockResolvedValue(
      page([job({ id: "e9", status: "running", progress: 40 })]),
    );
    vi.mocked(api.exportStatus)
      .mockResolvedValueOnce(job({ id: "e9", status: "running", progress: 40 }))
      .mockResolvedValue(job({ id: "e9", status: "cancelled", progress: 40 }));
    vi.mocked(api.cancelExport).mockResolvedValue(
      job({ id: "e9", status: "cancelled", progress: 40 }),
    );

    renderPage(<ExportPage />);

    // The panel's own control, not the history row's icon button.
    await user.click(await screen.findByRole("button", { name: "Cancel" }));
    await user.click(await screen.findByRole("button", { name: "Cancel job" }));

    await waitFor(() => expect(api.cancelExport).toHaveBeenCalledWith("e9"));
    // The job is adopted so the neutral cancelled notice is shown.
    expect(await screen.findByText(/Export cancelled/)).toBeTruthy();
  });

  it("removes an export from the history after a confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(api.listExports).mockResolvedValue(
      page([job({ id: "e1", status: "completed", file_size: 1024 })]),
    );
    vi.mocked(api.deleteExport).mockResolvedValue(undefined);

    renderPage(<ExportPage />);

    await user.click(
      await screen.findByRole("button", { name: "Delete export" }),
    );
    await user.click(await screen.findByRole("button", { name: "Delete" }));

    await waitFor(() => expect(api.deleteExport).toHaveBeenCalledWith("e1"));
  });

  it.each([
    ["dialog", 1440],
    ["bottom sheet", 390],
  ])(
    "shows a previous export's details in the responsive %s",
    async (_name, width) => {
      const user = userEvent.setup();
      setTestViewportWidth(width);
      vi.mocked(api.listExports).mockResolvedValue(
        page([
          job({
            id: "e-details",
            status: "completed",
            progress: 100,
            processed_items: 9,
            total_items: 9,
            completed_at: "2026-09-06T09:01:00Z",
            file_size: 7168,
            result_data: {
              journal_count: 5,
              entry_count: 9,
              media_count: 4,
              missing_media_count: 1,
            },
          }),
        ]),
      );

      renderPage(<ExportPage />);

      await user.click(
        await screen.findByRole("button", { name: "View export details" }),
      );

      const details = await screen.findByRole("dialog", {
        name: "Export details",
      });
      expect(within(details).getByText("5 journals")).toBeTruthy();
      expect(within(details).getByText("9 entries")).toBeTruthy();
      expect(within(details).getByText("4 media files")).toBeTruthy();
      expect(within(details).getByText("1 media file missing")).toBeTruthy();
      expect(within(details).getByText("7 KB")).toBeTruthy();
    },
  );

  it("loads an older page of export jobs", async () => {
    const user = userEvent.setup();
    const cursor = "2026-01-01T00:00:00Z";
    vi.mocked(api.listExports)
      .mockResolvedValueOnce(
        page([job({ id: "e1", status: "failed" })], cursor),
      )
      .mockResolvedValueOnce(page([job({ id: "e2", status: "partial" })]));

    renderPage(<ExportPage />);

    await user.click(
      await screen.findByRole("button", { name: "Load older jobs" }),
    );

    await waitFor(() =>
      expect(api.listExports).toHaveBeenCalledWith({
        cursor_created_at: cursor,
        cursor_id: cursor,
      }),
    );
    expect(await screen.findByText("Partial")).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Load older jobs" }),
    ).toBeNull();
  });
});
