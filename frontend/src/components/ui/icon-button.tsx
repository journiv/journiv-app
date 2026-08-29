import type { ComponentProps } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Journiv wrapper over the stock base-vega Button for icon-only controls
 * (DESIGN.md §7). Two guarantees shadcn's bare `size="icon"` does not give:
 *
 *  - an accessible name is REQUIRED (`label` → `aria-label` + `title`);
 *  - the touch target is always >= 44px (`--tap-target`) via an invisible
 *    `::after` hit area, even though the visual box is 28-32px.
 */
type IconButtonProps = Omit<
  ComponentProps<typeof Button>,
  "aria-label" | "variant" | "size"
> & {
  /** Required: an icon-only control must always be named for assistive tech. */
  label: string;
  variant?: "ghost" | "secondary";
  /** Visual box size. The touch target is always at least --tap-target. */
  size?: "sm" | "md";
};

export function IconButton({
  label,
  variant = "ghost",
  size = "md",
  className,
  type = "button",
  ...props
}: IconButtonProps) {
  return (
    <Button
      type={type}
      aria-label={label}
      title={label}
      variant={variant === "secondary" ? "outline" : "ghost"}
      size={size === "sm" ? "icon-sm" : "icon"}
      className={cn(
        "relative after:absolute after:top-1/2 after:left-1/2 after:size-11 after:-translate-x-1/2 after:-translate-y-1/2 after:content-['']",
        className,
      )}
      {...props}
    />
  );
}
