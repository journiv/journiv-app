import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../../api/client/api";
import type {
  ImportJobListResponse,
  ImportJobStatusResponse,
  InstanceConfigResponse,
} from "../../../api/generated/types.gen";
import { setTestViewportWidth } from "../../../test/viewport";
import { ImportPage } from "./ImportPage";

vi.mock("../../../api/client/api", () => ({
  api: {
    cancelImport: vi.fn(),
    uploadImport: vi.fn(),
    importStatus: vi.fn(),
    listImports: vi.fn(),
    deleteImport: vi.fn(),
    instanceConfig: vi.fn(),
  },
}));

const NOW = "2026-09-06T09:00:00Z";

const CONFIG = {
  import_export_max_file_size_mb: 100,
  max_file_size_mb: 50,
  disable_signup: false,
  oidc_enabled: false,
  oidc_only: false,
  plus: { available: false, tier: "member", upgrade_url: "" },
} as InstanceConfigResponse;

function job(
  over: Partial<ImportJobStatusResponse> = {},
): ImportJobStatusResponse {
  return {
    id: "i1",
    status: "pending",
    progress: 0,
    total_items: 0,
    processed_items: 0,
    created_at: NOW,
    source_type: "journiv",
    ...over,
  };
}

function page(
  items: ImportJobStatusResponse[],
  next: string | null = null,
): ImportJobListResponse {
  return {
    items,
    next_cursor_created_at: next,
    next_cursor_id: next,
  };
}

function zip(name = "export.zip") {
  return new File([new Uint8Array(16)], name, { type: "application/zip" });
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
  vi.mocked(api.listImports).mockResolvedValue(page([]));
  vi.mocked(api.instanceConfig).mockResolvedValue(CONFIG);
});

describe("Settings · Import", () => {
  it("changes the guidance line with the selected source", async () => {
    const user = userEvent.setup({ applyAccept: false });
    renderPage(<ImportPage />);

    expect(await screen.findByText(/containing data\.json/)).toBeTruthy();

    await user.selectOptions(screen.getByLabelText("Source"), "dayone");
    expect(screen.getByText(/Export JSON/)).toBeTruthy();
  });

  it("rejects a non-zip file inline and keeps the action disabled", async () => {
    const user = userEvent.setup({ applyAccept: false });
    renderPage(<ImportPage />);

    await user.upload(
      await screen.findByLabelText("Import archive"),
      new File(["hello"], "notes.txt", { type: "text/plain" }),
    );

    expect(await screen.findByText(/Choose a \.zip archive/)).toBeTruthy();
    expect(
      (
        screen.getByRole("button", {
          name: "Start import",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });

  it("rejects a file over the instance size limit", async () => {
    const user = userEvent.setup({ applyAccept: false });
    renderPage(<ImportPage />);

    const big = zip("huge.zip");
    Object.defineProperty(big, "size", { value: 200 * 1024 * 1024 });
    await user.upload(await screen.findByLabelText("Import archive"), big);

    expect(await screen.findByText(/maximum is 100 MB/)).toBeTruthy();
  });

  it("uploads the archive and shows the created/skipped breakdown and warnings", async () => {
    const user = userEvent.setup({ applyAccept: false });
    vi.mocked(api.uploadImport).mockResolvedValue(job({ status: "pending" }));
    vi.mocked(api.importStatus).mockResolvedValue(
      job({
        status: "completed",
        progress: 100,
        processed_items: 130,
        total_items: 132,
        warnings: ["Colour value ignored", "Unknown mood skipped"],
        result_data: {
          entries_created: 128,
          journals_created: 3,
          media_files_imported: 84,
          entries_skipped: 4,
          warning_categories: { "Skipped due to size": 2 },
        },
      }),
    );

    renderPage(<ImportPage />);
    await user.upload(await screen.findByLabelText("Import archive"), zip());
    await user.click(screen.getByRole("button", { name: "Start import" }));

    await waitFor(() =>
      expect(api.uploadImport).toHaveBeenCalledWith(
        expect.any(File),
        "journiv",
      ),
    );

    expect(await screen.findByText("128 entries")).toBeTruthy();
    expect(screen.getByText(/4 entries skipped/)).toBeTruthy();

    await user.click(screen.getByText(/View 2 warnings/));
    expect(screen.getByText("Colour value ignored")).toBeTruthy();
    expect(screen.getByText(/Skipped due to size — 2/)).toBeTruthy();
  });

  it("lists recent import jobs", async () => {
    vi.mocked(api.listImports).mockResolvedValue(
      page([
        job({
          id: "i7",
          status: "partial",
          source_type: "dayone",
          result_data: { entries_created: 12 },
        }),
      ]),
    );

    renderPage(<ImportPage />);

    expect(await screen.findByText("Partial")).toBeTruthy();
    expect(screen.getByRole("cell", { name: "Day One" })).toBeTruthy();
    expect(screen.getByText("12 entries")).toBeTruthy();
  });

  it.each([
    ["dialog", 1440],
    ["bottom sheet", 390],
  ])(
    "shows a previous import's details in the responsive %s",
    async (_name, width) => {
      const user = userEvent.setup();
      setTestViewportWidth(width);
      vi.mocked(api.listImports).mockResolvedValue(
        page([
          job({
            id: "i-details",
            status: "completed",
            progress: 100,
            processed_items: 9,
            total_items: 9,
            source_type: "dayone",
            completed_at: "2026-09-06T09:01:00Z",
            result_data: {
              journals_created: 2,
              entries_created: 9,
              media_files_imported: 4,
              entries_skipped: 1,
              warning_categories: { "Skipped due to size": 2 },
            },
          }),
        ]),
      );

      renderPage(<ImportPage />);

      await user.click(
        await screen.findByRole("button", { name: "View import details" }),
      );

      const details = await screen.findByRole("dialog", {
        name: "Import details",
      });
      expect(within(details).getByText("Day One")).toBeTruthy();
      expect(within(details).getByText("2 journals")).toBeTruthy();
      expect(within(details).getByText("9 entries")).toBeTruthy();
      expect(within(details).getByText("4 media files")).toBeTruthy();
      expect(within(details).getByText("1 entry skipped")).toBeTruthy();
      expect(within(details).getByText(/Skipped due to size — 2/)).toBeTruthy();
    },
  );

  it("cancels a running import from the history after confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(api.listImports).mockResolvedValue(
      page([job({ id: "i9", status: "running", progress: 40 })]),
    );
    vi.mocked(api.importStatus).mockResolvedValue(
      job({ id: "i9", status: "running", progress: 40 }),
    );
    vi.mocked(api.cancelImport).mockResolvedValue(
      job({ id: "i9", status: "cancelled", progress: 40 }),
    );

    renderPage(<ImportPage />);

    await user.click(
      await screen.findByRole("button", { name: "Cancel import" }),
    );
    await user.click(await screen.findByRole("button", { name: "Cancel job" }));

    await waitFor(() => expect(api.cancelImport).toHaveBeenCalledWith("i9"));
  });

  it("confirms before cancelling the in-progress import from its panel", async () => {
    const user = userEvent.setup();
    vi.mocked(api.listImports).mockResolvedValue(
      page([job({ id: "i9", status: "running", progress: 40 })]),
    );
    vi.mocked(api.importStatus)
      .mockResolvedValueOnce(job({ id: "i9", status: "running", progress: 40 }))
      .mockResolvedValue(job({ id: "i9", status: "cancelled", progress: 40 }));
    vi.mocked(api.cancelImport).mockResolvedValue(
      job({ id: "i9", status: "cancelled", progress: 40 }),
    );

    renderPage(<ImportPage />);

    await user.click(await screen.findByRole("button", { name: "Cancel" }));
    await user.click(await screen.findByRole("button", { name: "Cancel job" }));

    await waitFor(() => expect(api.cancelImport).toHaveBeenCalledWith("i9"));
    expect(await screen.findByText(/Import cancelled/)).toBeTruthy();
  });
});
