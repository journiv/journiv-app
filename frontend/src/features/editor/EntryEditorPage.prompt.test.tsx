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
const journal: JournalResponse = {
  id: "journal-1",
  user_id: user.id,
  title: "Daily notes",
  is_favorite: false,
  is_archived: false,
  entry_count: 0,
  total_words: 0,
  created_at: now,
  updated_at: now,
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
  sessionStore.write({
    version: 1,
    accessToken: "access",
    refreshToken: "refresh",
  });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.journals).mockResolvedValue([journal]);
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

describe("new entry from a prompt", () => {
  it("seeds the heading, shows the banner and links prompt_id on save", async () => {
    const person = userEvent.setup();
    await renderRoute(`/timeline/new?prompt=${PROMPT_ID}`);

    // Banner: the prompt is named above the body.
    const banner = await screen.findByRole(
      "complementary",
      { name: "Writing from a prompt" },
      { timeout: 10_000 },
    );
    expect(
      banner.textContent?.includes(
        "Describe someone who made your day recently.",
      ),
    ).toBe(true);

    // Body: the prompt is seeded as a heading (so it appears a second time).
    await waitFor(() =>
      expect(
        screen.getAllByText("Describe someone who made your day recently.")
          .length,
      ).toBeGreaterThanOrEqual(2),
    );

    const title = await screen.findByLabelText("Entry title");
    await person.type(title, "For Sam");

    await person.click(screen.getByRole("button", { name: /^(Done|Retry)$/ }));

    await waitFor(() => expect(api.createMoment).toHaveBeenCalled());
    expect(api.createMoment).toHaveBeenCalledWith(
      expect.objectContaining({ prompt_id: PROMPT_ID }),
    );
  });

  it("drops the link when the prompt banner is removed", async () => {
    const person = userEvent.setup();
    await renderRoute(`/timeline/new?prompt=${PROMPT_ID}`);

    await screen.findByRole(
      "complementary",
      { name: "Writing from a prompt" },
      { timeout: 10_000 },
    );
    await person.click(screen.getByRole("button", { name: "Remove prompt" }));

    const title = await screen.findByLabelText("Entry title");
    await person.type(title, "No prompt");
    await person.click(screen.getByRole("button", { name: /^(Done|Retry)$/ }));

    await waitFor(() => expect(api.createMoment).toHaveBeenCalled());
    const body = vi.mocked(api.createMoment).mock.calls[0][0] as {
      prompt_id?: string;
    };
    expect(body.prompt_id).toBeUndefined();
  });

  it("restores a selected prompt link from a recovered local draft", async () => {
    const person = userEvent.setup();
    const draftId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    await storeRecoveredDraft(draftId, PROMPT_ID);
    await renderRoute(`/timeline/new?draft=${draftId}`);

    await person.click(await screen.findByRole("button", { name: "Recover" }));
    expect(
      await screen.findByRole("complementary", {
        name: "Writing from a prompt",
      }),
    ).toBeTruthy();

    await person.click(screen.getByRole("button", { name: /^(Done|Retry)$/ }));
    await waitFor(() => expect(api.createMoment).toHaveBeenCalled());
    expect(api.createMoment).toHaveBeenCalledWith(
      expect.objectContaining({ prompt_id: PROMPT_ID }),
    );
  });

  it("restores a removed prompt as an explicit unlinked state", async () => {
    const person = userEvent.setup();
    const draftId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
    await storeRecoveredDraft(draftId, null);
    await renderRoute(`/timeline/new?draft=${draftId}`);

    await person.click(await screen.findByRole("button", { name: "Recover" }));
    expect(
      screen.queryByRole("complementary", { name: "Writing from a prompt" }),
    ).toBeNull();

    await person.click(screen.getByRole("button", { name: /^(Done|Retry)$/ }));
    await waitFor(() => expect(api.createMoment).toHaveBeenCalled());
    const body = vi.mocked(api.createMoment).mock.calls[0][0] as {
      prompt_id?: string;
    };
    expect(body.prompt_id).toBeUndefined();
  });

  it("links the initial prompt when finalising a recovered draft Moment", async () => {
    const person = userEvent.setup();
    const draftId = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
    const draftMomentId = "draft-moment";
    await storeRecoveredDraft(draftId, PROMPT_ID, { momentId: draftMomentId });
    vi.mocked(api.moment).mockResolvedValue({
      ...createdMoment,
      id: draftMomentId,
      entry: undefined,
    });
    await renderRoute(`/timeline/new?draft=${draftId}`);

    await person.click(await screen.findByRole("button", { name: "Recover" }));
    await person.click(screen.getByRole("button", { name: /^(Done|Retry)$/ }));

    await waitFor(() => expect(api.updateMoment).toHaveBeenCalled());
    expect(api.updateMoment).toHaveBeenCalledWith(
      draftMomentId,
      expect.objectContaining({ prompt_id: PROMPT_ID }),
    );
  });
});
