import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client/api";
import { ApiError } from "../../api/client/errors";
import type {
  PromptPageResponse,
  PromptResponse,
} from "../../api/generated/types.gen";
import { createAppQueryClient } from "../../app/queryClient";
import { PromptBrowser } from "./PromptBrowser";

vi.mock("../../api/client/api", () => ({
  api: {
    prompts: vi.fn(),
    dailyPrompt: vi.fn(),
    randomPrompt: vi.fn(),
    promptAnalytics: vi.fn(),
  },
}));

const prompt = (overrides: Partial<PromptResponse>): PromptResponse => ({
  id: "p",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  text: "text",
  category: "gratitude",
  difficulty_level: 1,
  estimated_time_minutes: 5,
  is_active: true,
  usage_count: 0,
  answered_count: 0,
  ...overrides,
});

const libraryPrompts: PromptResponse[] = [
  prompt({
    id: "g1",
    text: "What are you grateful for today?",
    category: "gratitude",
  }),
  prompt({
    id: "g2",
    text: "Name a small kindness you noticed.",
    category: "gratitude",
  }),
  prompt({
    id: "r1",
    text: "What did today teach you?",
    category: "reflection",
    difficulty_level: 2,
    estimated_time_minutes: 15,
  }),
  prompt({
    id: "r2",
    text: "Which belief have you outgrown?",
    category: "reflection",
    difficulty_level: 3,
    estimated_time_minutes: 20,
  }),
];

const daily = prompt({
  id: "d1",
  text: "Describe someone who made your day.",
  category: "gratitude",
});

const promptPage = (
  items: PromptResponse[],
  overrides: Partial<PromptPageResponse> = {},
): PromptPageResponse => ({
  items,
  total: items.length,
  next_offset: null,
  category_counts: items.reduce<Record<string, number>>((counts, item) => {
    const category = item.category ?? "";
    counts[category] = (counts[category] ?? 0) + 1;
    return counts;
  }, {}),
  all_count: items.length,
  ...overrides,
});

function browsePage(query: {
  category?: string | null;
  q?: string | null;
  min_minutes?: number | null;
  max_minutes?: number | null;
}): PromptPageResponse {
  const q = query.q?.toLowerCase();
  const items = libraryPrompts.filter((item) => {
    const matchesText =
      !q ||
      item.text.toLowerCase().includes(q) ||
      (item.category ?? "").toLowerCase().includes(q);
    const minutes = item.estimated_time_minutes;
    return (
      matchesText &&
      (!query.category || item.category === query.category) &&
      (query.min_minutes == null ||
        (typeof minutes === "number" && minutes >= query.min_minutes)) &&
      (query.max_minutes == null ||
        (typeof minutes === "number" && minutes <= query.max_minutes))
    );
  });
  return promptPage(items);
}

function renderBrowser(onSelect = vi.fn()) {
  const client = createAppQueryClient();
  client.setDefaultOptions({ queries: { retry: false, retryDelay: 0 } });
  render(
    <QueryClientProvider client={client}>
      <PromptBrowser
        variant="page"
        selectActionLabel="Write"
        dailyActionLabel="Write with this prompt"
        onSelectPrompt={onSelect}
      />
    </QueryClientProvider>,
  );
  return { onSelect };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.prompts).mockImplementation((query) =>
    Promise.resolve(browsePage(query)),
  );
  vi.mocked(api.dailyPrompt).mockResolvedValue(daily);
  vi.mocked(api.randomPrompt).mockResolvedValue(
    prompt({ id: "rand", text: "A random spark." }),
  );
  vi.mocked(api.promptAnalytics).mockResolvedValue({
    prompts_answered: 2,
    total_answers: 3,
    current_streak: 2,
    favorite_categories: [
      { category: "gratitude", answered_count: 2 },
      { category: "reflection", answered_count: 1 },
    ],
    completion_trend: [{ week_start: "2026-09-01", answered_count: 3 }],
    most_used_prompt: {
      id: "g1",
      text: "What are you grateful for today?",
      answered_count: 2,
    },
  });
});

describe("PromptBrowser", () => {
  it("mounts the Insights query only after switching tabs", async () => {
    renderBrowser();
    await screen.findByRole("list", { name: "Prompts" });
    expect(api.promptAnalytics).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("tab", { name: "Insights" }));

    expect(await screen.findByText("Prompts answered")).toBeTruthy();
    expect(api.promptAnalytics).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("list", { name: "Prompts" })).toBeNull();
  });

  it("shows the daily hero and starts an entry from it", async () => {
    const { onSelect } = renderBrowser();
    const hero = await screen.findByRole("region", {
      name: "Prompt of the day",
    });
    expect(
      within(hero).getByText("Describe someone who made your day."),
    ).toBeTruthy();

    await userEvent.click(
      within(hero).getByRole("button", { name: "Write with this prompt" }),
    );
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ id: "d1" }),
    );
  });

  it("lists the library and narrows by category", async () => {
    renderBrowser();
    const list = await screen.findByRole("list", { name: "Prompts" });
    expect(
      within(list).getByText("What are you grateful for today?"),
    ).toBeTruthy();
    expect(within(list).getByText("What did today teach you?")).toBeTruthy();

    vi.mocked(api.prompts).mockResolvedValueOnce(
      promptPage(
        libraryPrompts.filter((item) => item.category === "reflection"),
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: /^Reflection/ }));

    await waitFor(() => {
      expect(vi.mocked(api.prompts)).toHaveBeenCalledTimes(2);
      expect(vi.mocked(api.prompts)).toHaveBeenLastCalledWith(
        expect.objectContaining({ category: "reflection" }),
      );
      expect(screen.queryByText("What are you grateful for today?")).toBeNull();
    });
    expect(screen.getByText("What did today teach you?")).toBeTruthy();
  });

  it("always offers every supported difficulty level", async () => {
    renderBrowser();
    await screen.findByRole("list", { name: "Prompts" });

    const levels = Array.from(
      (screen.getByLabelText("Level") as HTMLSelectElement).options,
      (option) => option.value,
    );
    expect(levels).toEqual(expect.arrayContaining(["1", "2", "3", "4", "5"]));
  });

  it("narrows by search text", async () => {
    renderBrowser();
    await screen.findByRole("list", { name: "Prompts" });

    await userEvent.type(
      screen.getByRole("textbox", { name: "Search prompts" }),
      "kindness",
    );

    await waitFor(() => {
      expect(vi.mocked(api.prompts)).toHaveBeenLastCalledWith(
        expect.objectContaining({ q: "kindness" }),
      );
      expect(
        screen.getByText("Name a small kindness you noticed."),
      ).toBeTruthy();
    });
    expect(screen.queryByText("What did today teach you?")).toBeNull();
  });

  it("sends the duration bucket bounds to the library endpoint", async () => {
    renderBrowser();
    await screen.findByRole("list", { name: "Prompts" });

    await userEvent.selectOptions(screen.getByLabelText("Duration"), "long");

    await waitFor(() => {
      expect(vi.mocked(api.prompts)).toHaveBeenLastCalledWith(
        expect.objectContaining({ min_minutes: 11, max_minutes: 15 }),
      );
      expect(screen.getByText("What did today teach you?")).toBeTruthy();
      expect(screen.queryByText("What are you grateful for today?")).toBeNull();
    });
  });

  it("selects a prompt from a card", async () => {
    const { onSelect } = renderBrowser();
    const list = await screen.findByRole("list", { name: "Prompts" });

    await userEvent.click(
      within(list).getByRole("button", {
        name: "Write: Which belief have you outgrown?",
      }),
    );
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ id: "r2" }),
    );
  });

  it("shows the signed-in writer's answer count", async () => {
    vi.mocked(api.prompts).mockResolvedValue(
      promptPage([
        prompt({
          id: "written",
          text: "What stayed with you today?",
          answered_count: 3,
        }),
      ]),
    );
    renderBrowser();

    expect(await screen.findByText("Written 3 times")).toBeTruthy();
  });

  it("loads the next offset page", async () => {
    vi.mocked(api.prompts)
      .mockResolvedValueOnce(
        promptPage([libraryPrompts[0]], {
          total: 2,
          next_offset: 1,
          all_count: 2,
        }),
      )
      .mockResolvedValueOnce(
        promptPage([libraryPrompts[1]], { total: 2, all_count: 2 }),
      );
    renderBrowser();

    const list = await screen.findByRole("list", { name: "Prompts" });
    await userEvent.click(
      screen.getByRole("button", { name: "Load more prompts" }),
    );

    expect(
      await within(list).findByText("Name a small kindness you noticed."),
    ).toBeTruthy();
  });

  it("handles an already-answered daily prompt and shuffles", async () => {
    vi.mocked(api.dailyPrompt).mockResolvedValue(null);
    renderBrowser();

    const hero = await screen.findByRole("region", {
      name: "Prompt of the day",
    });
    expect(
      within(hero).getByText(/started an entry from today’s prompt/i),
    ).toBeTruthy();

    await userEvent.click(
      within(hero).getByRole("button", { name: "Try another prompt" }),
    );
    expect(await within(hero).findByText("A random spark.")).toBeTruthy();
  });

  it("does not claim a daily entry was started when no active prompts exist", async () => {
    const person = userEvent.setup();
    vi.mocked(api.dailyPrompt).mockResolvedValue(null);
    vi.mocked(api.randomPrompt).mockRejectedValue(
      new ApiError("No prompts available", { status: 404 }),
    );
    renderBrowser();

    const hero = await screen.findByRole("region", {
      name: "Prompt of the day",
    });
    await person.click(
      within(hero).getByRole("button", { name: "Try another prompt" }),
    );

    expect(
      await within(hero).findByText(/There are no active prompts right now/i),
    ).toBeTruthy();
    expect(
      within(hero).queryByText(/started an entry from today’s prompt/i),
    ).toBeNull();
  });

  it("shows a retryable error when the library fails", async () => {
    vi.mocked(api.prompts).mockRejectedValue(
      new ApiError("boom", { status: 500 }),
    );
    renderBrowser();

    expect(await screen.findByText("Prompts could not be loaded")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });
});
