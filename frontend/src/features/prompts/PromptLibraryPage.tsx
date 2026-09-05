import { useNavigate, useSearch } from "@tanstack/react-router";
import type { PromptResponse } from "../../api/generated/types.gen";
import { LibraryWorkspace } from "../library/LibraryWorkspace";
import { PromptBrowser, type PromptBrowserTab } from "./PromptBrowser";

/**
 * `/library/prompts` — the prompt library (docs/features/prompts.md). It reuses
 * the Library workspace shell (wide span-2 canvas, compact PageBar, one scroll
 * owner) like every other Library section and Insights; the browsing UI is the
 * shared `PromptBrowser`, the same component the editor's prompt picker mounts.
 *
 * Choosing a prompt here opens a new entry with `?prompt=`, so the editor seeds
 * the heading, shows the banner, and links `prompt_id` on save.
 */
export function PromptLibraryPage() {
  const navigate = useNavigate({ from: "/library/prompts" });
  const { tab } = useSearch({ strict: false }) as { tab: PromptBrowserTab };

  const openEditorWithPrompt = (prompt: PromptResponse) => {
    void navigate({
      to: "/timeline/new",
      search: { q: "", prompt: prompt.id },
    });
  };

  return (
    <LibraryWorkspace
      title="Prompts"
      intro="A library of journaling prompts for when you want a place to start."
    >
      <PromptBrowser
        variant="page"
        selectActionLabel="Write"
        dailyActionLabel="Write with this prompt"
        onSelectPrompt={openEditorWithPrompt}
        tab={tab}
        onTabChange={(next) => navigate({ search: { tab: next } })}
      />
    </LibraryWorkspace>
  );
}
