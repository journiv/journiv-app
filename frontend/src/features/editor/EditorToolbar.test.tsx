import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EditorToolbar } from "./EditorToolbar";
import type { EditorState, QuillSurfaceHandle } from "./QuillSurface";

const editor = (): QuillSurfaceHandle => ({
  getSelectionIndex: vi.fn(() => 0),
  getIndexFromPoint: vi.fn(() => 0),
  clearHistory: vi.fn(),
  getSelectedMedia: vi.fn(() => null),
  removeSelectedMedia: vi.fn(() => true),
  insertPlaceholder: vi.fn(),
  seedPromptHeading: vi.fn(),
  insertMedia: vi.fn(),
  replacePlaceholder: vi.fn(() => true),
  removePlaceholder: vi.fn(() => true),
  removeEmbedForMediaId: vi.fn(() => null),
  hasPlaceholder: vi.fn(() => false),
  setPlaceholderState: vi.fn(),
  focus: vi.fn(),
  getContents: vi.fn(() => ({ ops: [{ insert: "Selected text\n" }] })),
  getLinkContext: vi.fn(() => ({
    href: "",
    selectedText: "Selected",
    canApply: true,
  })),
  hasFocus: vi.fn(() => true),
  isComposing: vi.fn(() => false),
  redo: vi.fn(),
  setLink: vi.fn(() => true),
  toggleInline: vi.fn(),
  toggleLine: vi.fn(),
  indent: vi.fn(),
  undo: vi.fn(),
});

const state = (formats: Record<string, unknown> = {}): EditorState => ({
  formats,
  focused: true,
  selectionLength: 8,
  wordCount: 2,
  selectedMedia: null,
});

describe("EditorToolbar", () => {
  it("reflects active formats and invokes inline, line, and history commands", async () => {
    const surface = editor();
    render(
      <EditorToolbar
        editor={{ current: surface }}
        state={state({ bold: true, header: 2 })}
      />,
    );

    expect(
      screen.getByRole("button", { name: "Bold" }).getAttribute("aria-pressed"),
    ).toBe("true");
    expect(
      screen
        .getByRole("button", { name: "Heading 2" })
        .getAttribute("aria-pressed"),
    ).toBe("true");
    await userEvent.click(screen.getByRole("button", { name: "Italic" }));
    await userEvent.click(screen.getByRole("button", { name: "Bullet list" }));
    await userEvent.click(screen.getByRole("button", { name: "Blockquote" }));
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    await userEvent.click(screen.getByRole("button", { name: "Redo" }));

    expect(surface.toggleInline).toHaveBeenCalledWith("italic");
    expect(surface.toggleLine).toHaveBeenCalledWith("list", "bullet");
    expect(surface.toggleLine).toHaveBeenCalledWith("blockquote", true);
    expect(surface.undo).toHaveBeenCalledOnce();
    expect(surface.redo).toHaveBeenCalledOnce();
    // The word count is no longer a toolbar control — it lives below the prose
    // (see EntryEditorPage.datetime.test.tsx).
    expect(screen.queryByText(/\d+ words?/)).toBeNull();
  });

  it("marks the checklist control active for either task state", () => {
    const { rerender } = render(
      <EditorToolbar
        editor={{ current: editor() }}
        state={state({ list: "unchecked" })}
      />,
    );
    expect(
      screen
        .getByRole("button", { name: "Checklist" })
        .getAttribute("aria-pressed"),
    ).toBe("true");
    rerender(
      <EditorToolbar
        editor={{ current: editor() }}
        state={state({ list: "checked" })}
      />,
    );
    expect(
      screen
        .getByRole("button", { name: "Checklist" })
        .getAttribute("aria-pressed"),
    ).toBe("true");
  });

  it("shows list indent controls only on a list line and honours the bounds", async () => {
    const surface = editor();
    const { rerender } = render(
      <EditorToolbar editor={{ current: surface }} state={state({})} />,
    );
    expect(
      screen.queryByRole("button", { name: "Indent list item" }),
    ).toBeNull();

    rerender(
      <EditorToolbar
        editor={{ current: surface }}
        state={state({ list: "bullet" })}
      />,
    );
    expect(
      screen
        .getByRole("button", { name: "Outdent list item" })
        .hasAttribute("disabled"),
    ).toBe(true);
    await userEvent.click(
      screen.getByRole("button", { name: "Indent list item" }),
    );
    expect(surface.indent).toHaveBeenCalledWith(1);

    rerender(
      <EditorToolbar
        editor={{ current: surface }}
        state={state({ list: "bullet", indent: 5 })}
      />,
    );
    expect(
      screen
        .getByRole("button", { name: "Indent list item" })
        .hasAttribute("disabled"),
    ).toBe(true);
    await userEvent.click(
      screen.getByRole("button", { name: "Outdent list item" }),
    );
    expect(surface.indent).toHaveBeenCalledWith(-1);
  });

  it("preserves the editor selection on pointer interaction", () => {
    render(<EditorToolbar editor={{ current: editor() }} state={state()} />);
    const eventResult = fireEvent.pointerDown(
      screen.getByRole("button", { name: "Bold" }),
    );
    expect(eventResult).toBe(false);
  });

  it("adds a safe link and rejects unsafe links without changing content", async () => {
    const surface = editor();
    render(<EditorToolbar editor={{ current: surface }} state={state()} />);
    await userEvent.click(screen.getByRole("button", { name: "Add link" }));
    const input = screen.getByLabelText("Link URL");
    await userEvent.clear(input);
    await userEvent.type(input, "javascript:alert(1)");
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(screen.getByRole("alert").textContent).toContain("http");
    expect(surface.setLink).not.toHaveBeenCalled();

    await userEvent.clear(input);
    await userEvent.type(input, "https://journiv.com/docs");
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(surface.setLink).toHaveBeenCalledWith("https://journiv.com/docs");
  });

  it("cancels without altering the selection and removes an active link", async () => {
    const surface = editor();
    vi.mocked(surface.getLinkContext).mockReturnValue({
      href: "https://journiv.com",
      selectedText: "Selected",
      canApply: true,
    });
    render(
      <EditorToolbar
        editor={{ current: surface }}
        state={state({ link: "https://journiv.com" })}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Edit link" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(surface.setLink).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Edit link" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(surface.setLink).toHaveBeenCalledWith(false);
  });

  it("offers the prompt affordance only when onPickPrompt is passed", async () => {
    const onPickPrompt = vi.fn();
    const { rerender } = render(
      <EditorToolbar editor={{ current: editor() }} state={state()} />,
    );
    expect(
      screen.queryByRole("button", { name: "Write from a prompt" }),
    ).toBeNull();

    rerender(
      <EditorToolbar
        editor={{ current: editor() }}
        state={state()}
        onPickPrompt={onPickPrompt}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Write from a prompt" }),
    );
    expect(onPickPrompt).toHaveBeenCalledOnce();
  });

  it("opens the markdown shortcuts reference", async () => {
    render(<EditorToolbar editor={{ current: editor() }} state={state()} />);
    const help = screen.getByRole("button", { name: "Markdown shortcuts" });
    expect(help.getAttribute("aria-pressed")).toBeNull();

    await userEvent.click(help);
    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).toContain("**bold**");
    expect(dialog.textContent).toContain("Numbered list");
  });
});
