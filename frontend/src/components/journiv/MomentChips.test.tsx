import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { MomentResponse } from "../../api/generated/types.gen";
import { MomentChips } from "./MomentChips";

const moment = (over: Partial<MomentResponse>): MomentResponse =>
  ({
    id: "m1",
    user_id: "u1",
    logged_at_utc: "2026-08-26T10:00:00Z",
    logged_date_tz: "2026-08-26",
    logged_timezone: "UTC",
    tags: [],
    people: [],
    ...over,
  }) as MomentResponse;

describe("MomentChips", () => {
  it("renders nothing when there are no people or tags", () => {
    const { container } = render(<MomentChips moment={moment({})} />);
    expect(container.innerHTML).toBe("");
  });

  it("renders people and tags in their own labelled sections", () => {
    render(
      <MomentChips
        moment={moment({
          people: [{ id: "p1", name: "Sam" }],
          tags: [
            { id: "t1", name: "travel" } as never,
            { id: "t2", name: "family" } as never,
          ],
        })}
      />,
    );

    expect(
      screen.getByRole("region", { name: "People" }).textContent,
    ).toContain("Sam");
    const tags = screen.getByRole("region", { name: "Tags" });
    expect(tags.textContent).toContain("travel");
    expect(tags.textContent).toContain("family");
  });

  it("omits a section that has no items", () => {
    render(
      <MomentChips
        moment={moment({ tags: [{ id: "t1", name: "solo" } as never] })}
      />,
    );
    expect(screen.queryByRole("region", { name: "People" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Tags" })).not.toBeNull();
  });
});
