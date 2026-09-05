import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import type {
  PromptPageResponse,
  PromptResponse,
  UserResponse,
} from "../../api/generated/types.gen";
import { createAppQueryClient } from "../../app/queryClient";
import { createAppRouter } from "../../app/router";

vi.mock("../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    journals: vi.fn(),
    prompts: vi.fn(),
    dailyPrompt: vi.fn(),
    randomPrompt: vi.fn(),
    promptAnalytics: vi.fn(),
  },
}));

const now = "2026-09-03T09:00:00Z";
const user: UserResponse = {
  id: "user-1",
  email: "w@example.com",
  name: "Writer",
  role: "user",
  is_active: true,
  created_at: now,
  updated_at: now,
};
const p = (over: Partial<PromptResponse>): PromptResponse => ({
  id: "p1",
  created_at: now,
  updated_at: now,
  text: "What are you grateful for today?",
  category: "gratitude",
  difficulty_level: 1,
  estimated_time_minutes: 5,
  is_active: true,
  usage_count: 0,
  answered_count: 0,
  ...over,
});

const promptPage = (items: PromptResponse[]): PromptPageResponse => ({
  items,
  total: items.length,
  next_offset: null,
  category_counts: { gratitude: items.length },
  all_count: items.length,
});

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({
    version: 1,
    accessToken: "a",
    refreshToken: "r",
  });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.journals).mockResolvedValue([]);
  vi.mocked(api.prompts).mockResolvedValue(promptPage([p({})]));
  vi.mocked(api.dailyPrompt).mockResolvedValue(null);
  vi.mocked(api.randomPrompt).mockResolvedValue(p({ id: "rand" }));
  vi.mocked(api.promptAnalytics).mockResolvedValue({
    prompts_answered: 0,
    total_answers: 0,
    current_streak: 0,
    favorite_categories: [],
    completion_trend: [],
  });
});

async function renderRoute(path: string) {
  const history = createMemoryHistory({ initialEntries: [path] });
  const router = createAppRouter(history);
  const queryClient = createAppQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await router.load();
  return router;
}

describe("/library/prompts", () => {
  it("renders the prompt library inside the Library workspace", async () => {
    await renderRoute("/library/prompts");

    expect(
      await screen.findByRole("heading", { name: "Prompts", level: 1 }),
    ).toBeTruthy();
    expect(
      await screen.findByText("What are you grateful for today?"),
    ).toBeTruthy();
  });

  it("restores the Insights tab from the URL", async () => {
    await renderRoute("/library/prompts?tab=insights");

    expect(await screen.findByText("No prompt entries yet")).toBeTruthy();
    expect(api.promptAnalytics).toHaveBeenCalledTimes(1);
  });
});
