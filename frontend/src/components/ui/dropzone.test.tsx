import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Dropzone } from "./dropzone";

function Harness({ onChange }: { onChange?: (f: File | null) => void }) {
  const [file, setFile] = useState<File | null>(null);
  return (
    <Dropzone
      label="Archive"
      value={file}
      onValueChange={(next) => {
        setFile(next);
        onChange?.(next);
      }}
      accept=".zip"
    />
  );
}

describe("Dropzone", () => {
  it("reports the picked file and shows it as a removable chip", async () => {
    const user = userEvent.setup({ applyAccept: false });
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);

    const file = new File(["x"], "backup.zip", { type: "application/zip" });
    await user.upload(screen.getByLabelText("Archive"), file);

    expect(onChange).toHaveBeenCalledWith(file);
    expect(screen.getByText("backup.zip")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Remove file" }));
    expect(onChange).toHaveBeenLastCalledWith(null);
    expect(screen.queryByText("backup.zip")).toBeNull();
  });

  it("passes through the accessible name and reports validation to the caller", async () => {
    const user = userEvent.setup({ applyAccept: false });
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);

    // A mismatched type is still reported — the caller owns the type/size rule.
    const txt = new File(["x"], "notes.txt", { type: "text/plain" });
    await user.upload(screen.getByLabelText("Archive"), txt);
    expect(onChange).toHaveBeenCalledWith(txt);
  });
});
