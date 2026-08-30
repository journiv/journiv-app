import { browserTimeZone } from "@/lib/datetime";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EntryDateControl } from "./EntryDateControl";

// 20:00 on 15 January 2026 in Vienna (UTC+1 in winter).
const VIENNA_UTC = "2026-01-15T19:00:00.000Z";

function setup(
  props: Partial<React.ComponentProps<typeof EntryDateControl>> = {},
) {
  const onChange = vi.fn();
  render(
    <EntryDateControl
      loggedAtUtc={VIENNA_UTC}
      loggedTimezone="Europe/Vienna"
      onChange={onChange}
      {...props}
    />,
  );
  return { onChange, user: userEvent.setup() };
}

const trigger = () =>
  screen.getByRole("button", { name: /change entry date and time/i });

async function open(user: ReturnType<typeof userEvent.setup>) {
  await user.click(trigger());
  // The calendar is lazy-loaded on open.
  await screen.findByRole("grid");
}

describe("EntryDateControl", () => {
  it("shows the date and time in the entry's own zone on the trigger", () => {
    setup();
    // The 15th in Vienna — not the 16th (19:00 UTC) or the test machine's day.
    expect(trigger().textContent).toContain("January 15, 2026");
    expect(trigger().textContent).toMatch(/8:00\s?PM/i);
  });

  it("converts a picked day using the entry's zone, keeping the time", async () => {
    const { onChange, user } = setup();
    await open(user);

    const twentieth = screen
      .getAllByRole("button")
      .find((button) => button.textContent?.trim() === "20");
    expect(twentieth).toBeDefined();
    await user.click(twentieth as HTMLElement);

    expect(onChange).toHaveBeenCalledWith({
      utc: "2026-01-20T19:00:00.000Z",
      timezone: "Europe/Vienna",
    });
  });

  it("offers month and year dropdowns reflecting the entry's date", async () => {
    const { user } = setup();
    await open(user);

    const month = screen.getByRole("combobox", {
      name: /choose the month/i,
    }) as HTMLSelectElement;
    const year = screen.getByRole("combobox", {
      name: /choose the year/i,
    }) as HTMLSelectElement;
    // January 2026 in Vienna.
    expect(month.value).toBe("0");
    expect(year.value).toBe("2026");
  });

  it("jumps to a year picked from the dropdown, then commits that day", async () => {
    const { onChange, user } = setup();
    await open(user);

    await user.selectOptions(
      screen.getByRole("combobox", { name: /choose the year/i }),
      "2024",
    );
    const twentieth = screen
      .getAllByRole("button")
      .find((button) => button.textContent?.trim() === "20");
    await user.click(twentieth as HTMLElement);

    expect(onChange).toHaveBeenCalledWith({
      utc: "2024-01-20T19:00:00.000Z",
      timezone: "Europe/Vienna",
    });
  });

  it("converts a picked time using the entry's zone", async () => {
    const { onChange, user } = setup();
    await open(user);

    fireEvent.change(screen.getByLabelText("Time"), {
      target: { value: "09:30" },
    });

    expect(onChange).toHaveBeenLastCalledWith({
      utc: "2026-01-15T08:30:00.000Z",
      timezone: "Europe/Vienna",
    });
  });

  it("shows the effective zone when it differs from the browser's", async () => {
    const { user } = setup();
    await open(user);
    expect(screen.getByText(/· Europe\/Vienna/)).toBeTruthy();
  });

  it("hides the effective zone when it matches the browser's", async () => {
    const { user } = setup({
      loggedAtUtc: new Date().toISOString(),
      loggedTimezone: browserTimeZone(),
    });
    await open(user);
    expect(screen.queryByText(new RegExp(`· ${browserTimeZone()}`))).toBeNull();
  });

  it("resets to now in the browser's zone", async () => {
    const { onChange, user } = setup();
    await open(user);
    await user.click(screen.getByRole("button", { name: /reset to now/i }));

    const call = onChange.mock.calls.at(-1)?.[0];
    expect(call.timezone).toBe(browserTimeZone());
    expect(Date.now() - Date.parse(call.utc)).toBeLessThan(5000);
  });
});
