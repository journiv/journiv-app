import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import { ApiError } from "../../api/client/errors";
import type {
  JournalResponse,
  MomentResponse,
  PromptResponse,
  UserResponse,
} from "../../api/generated/types.gen";
import { queryKeys } from "../../api/query/keys";
import { createAppQueryClient } from "../../app/queryClient";
import { createAppRouter } from "../../app/router";
import type { DurableDraftDelta } from "./draftCanonical";
import { draftRepository } from "./draftRepository";

vi.mock("../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    journals: vi.fn(),
    moments: vi.fn(),
    moment: vi.fn(),
    momentMedia: vi.fn(),
    entry: vi.fn(),
    createMoment: vi.fn(),
    updateMoment: vi.fn(),
    createDraftEntry: vi.fn(),
    deleteMoment: vi.fn(),
    deleteEntry: vi.fn(),
    mediaFormats: vi.fn(),
    prompt: vi.fn(),
    prompts: vi.fn(),
    dailyPrompt: vi.fn(),
    randomPrompt: vi.fn(),
  },
}));

const now = "2026-09-03T09:00:00Z";
const PROMPT_ID = "11111111-1111-4111-8111-111111111111";

const user: UserResponse = {
  id: "user-1",
  email: "w@example.com",
  name: "Writer",
  role: "user",
  is_active: true,
  created_at: now,
  updated_at: now,
};
const TEMPLATE = "How am I feeling?\nOne win today:";
const journal: JournalResponse = {
  id: "journal-1",
  user_id: user.id,
  title: "Daily notes",
  entry_template: TEMPLATE,
  is_favorite: false,
  is_archived: false,
  entry_count: 0,
  total_words: 0,
  created_at: now,
  updated_at: now,
};
const plainJournal: JournalResponse = {
  ...journal,
  id: "journal-2",
  title: "Scratch",
  entry_template: null,
};
const promptRecord: PromptResponse = {
  id: PROMPT_ID,
  created_at: now,
  updated_at: now,
  text: "Describe someone who made your day recently.",
  category: "gratitude",
  difficulty_level: 1,
  estimated_time_minutes: 5,
  is_active: true,
  usage_count: 0,
  answered_count: 0,
};
const createdMoment = {
  id: "moment-new",
  user_id: user.id,
  logged_at_utc: now,
  logged_date_tz: "2026-09-03",
  logged_timezone: "UTC",
  entry: {
    id: "entry-new",
    journal_id: journal.id,
    moment_id: "moment-new",
    title: "",
    created_at: now,
    updated_at: now,
  },
} as unknown as MomentResponse;

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.adopt({ accessToken: "access", userId: "user-1" });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.journals).mockResolvedValue([journal, plainJournal]);
  vi.mocked(api.moments).mockResolvedValue({ items: [] } as never);
  vi.mocked(api.moment).mockRejectedValue(
    new ApiError("nope", { status: 404 }),
  );
  vi.mocked(api.momentMedia).mockResolvedValue([]);
  vi.mocked(api.mediaFormats).mockResolvedValue({});
  vi.mocked(api.prompt).mockResolvedValue(promptRecord);
  vi.mocked(api.createMoment).mockResolvedValue(createdMoment);
  vi.mocked(api.updateMoment).mockResolvedValue(createdMoment);
});

async function renderRoute(path: string) {
  const history = createMemoryHistory({ initialEntries: [path] });
  const router = createAppRouter(history);
  const queryClient = createAppQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });
  queryClient.setQueryData(queryKeys.me, user);
  render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </StrictMode>,
  );
  await router.load();
}

async function storeRecoveredDraft(
  draftId: string,
  promptId: string | null,
  identity?: { momentId: string; entryId?: string },
) {
  await draftRepository.write({
    key: `user-1:new:${draftId}`,
    userId: user.id,
    localDraftId: draftId,
    journalId: journal.id,
    title: "Recovered prompt writing",
    promptId,
    ...identity,
    contentDelta: {
      ops: [{ insert: "Writing that has not reached the server yet.\n" }],
    } as DurableDraftDelta,
    modifiedAt: now,
    dirty: true,
  });
}

function editorBody(): HTMLElement {
  const body = document.querySelector<HTMLElement>(".ql-editor");
  if (!body) throw new Error("editor body not mounted");
  return body;
}

describe("new entry in a journal with an entry template", () => {
  it("opens with the template and saves it with the writer's answers", async () => {
    const person = userEvent.setup();
    await renderRoute(`/journals/${journal.id}/new`);

    await waitFor(
      () => {
        expect(editorBody().textContent).toContain("How am I feeling?");
        expect(editorBody().textContent).toContain("One win today:");
      },
      { timeout: 10_000 },
    );
    // Untouched template: nothing to save yet, and the prompt offer stays.
    expect(
      screen.getByRole("button", { name: /write from a prompt/i }),
    ).toBeTruthy();

    const title = await screen.findByLabelText("Entry title");
    await person.type(title, "Saturday");
    await person.click(screen.getByRole("button", { name: /^(Done|Retry)$/ }));

    await waitFor(() => expect(api.createMoment).toHaveBeenCalled());
    const sent = JSON.stringify(vi.mocked(api.createMoment).mock.calls[0][0]);
    expect(sent).toContain("How am I feeling?");
    expect(sent).toContain("One win today:");
  });

  it("puts a prompt heading above the template", async () => {
    await renderRoute(`/journals/${journal.id}/new?prompt=${PROMPT_ID}`);
    await waitFor(
      () => {
        const text = editorBody().textContent ?? "";
        expect(text).toContain("How am I feeling?");
        expect(text.indexOf(promptRecord.text)).toBeLessThan(
          text.indexOf("How am I feeling?"),
        );
      },
      { timeout: 10_000 },
    );
  });

  it("puts a prompt picked in the editor above an untouched template", async () => {
    const person = userEvent.setup();
    vi.mocked(api.dailyPrompt).mockResolvedValue(promptRecord);
    vi.mocked(api.prompts).mockResolvedValue({
      items: [promptRecord],
      total: 1,
      next_offset: null,
      category_counts: { gratitude: 1 },
      all_count: 1,
    } as never);
    await renderRoute(`/journals/${journal.id}/new`);
    await waitFor(
      () => expect(editorBody().textContent).toContain("How am I feeling?"),
      { timeout: 10_000 },
    );

    await person.click(
      screen.getByRole("button", { name: /write from a prompt/i }),
    );
    await person.click(
      await screen.findByRole("button", { name: "Insert prompt" }),
    );

    await waitFor(() => {
      const text = editorBody().textContent ?? "";
      expect(text).toContain(promptRecord.text);
      expect(text.indexOf(promptRecord.text)).toBeLessThan(
        text.indexOf("How am I feeling?"),
      );
    });
  });

  it("swaps an untouched template when the journal changes", async () => {
    const person = userEvent.setup();
    await renderRoute(`/journals/${journal.id}/new`);
    await waitFor(
      () => expect(editorBody().textContent).toContain("How am I feeling?"),
      { timeout: 10_000 },
    );

    await person.selectOptions(
      screen.getByRole("combobox", { name: "Journal" }),
      plainJournal.id,
    );
    await waitFor(() =>
      expect(editorBody().textContent).not.toContain("How am I feeling?"),
    );

    await person.selectOptions(
      screen.getByRole("combobox", { name: "Journal" }),
      journal.id,
    );
    await waitFor(() =>
      expect(editorBody().textContent).toContain("How am I feeling?"),
    );
  });

  it("never templates a recovered draft", async () => {
    const person = userEvent.setup();
    const draftId = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
    await storeRecoveredDraft(draftId, null);
    await renderRoute(`/journals/${journal.id}/new?draft=${draftId}`);

    await person.click(await screen.findByRole("button", { name: "Recover" }));
    await waitFor(() =>
      expect(editorBody().textContent).toContain(
        "Writing that has not reached the server yet.",
      ),
    );
    expect(editorBody().textContent).not.toContain("How am I feeling?");
  });
});
