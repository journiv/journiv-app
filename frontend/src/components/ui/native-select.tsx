import { ChevronDownIcon } from "lucide-react";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * A native `<select>` wearing the base-vega `SelectTrigger` treatment.
 *
 * Journiv keeps native selects where the platform control is genuinely better
 * — a touch device's wheel picker beats a custom popup, and some of these
 * lists are long — but there must be exactly one way a select *looks*. This
 * carries the registry `SelectTrigger`'s own class string rather than a
 * parallel stylesheet, so the two cannot drift apart. If you change the
 * appearance here, you are diverging from the registry; change `select.tsx`
 * upstream instead, or don't.
 *
 * Reach for the real `Select` when you need grouping, icons or check marks.
 *
 * `className` styles the control's *wrapper*, not the raw `<select>`. The
 * chevron is an absolutely-positioned sibling whose containing block is that
 * wrapper, so the wrapper must be the box that sizes the control — otherwise a
 * width override (`w-auto`, a scoped width) shrinks the `<select>` while the
 * chevron stays pinned to a full-width wrapper and drifts off to the right.
 * Layout/width classes therefore belong on the wrapper; the `<select>` itself
 * always fills it. This mirrors the registry `SelectTrigger`, where the outer
 * trigger carries the className and the icon is its child.
 */
function NativeSelect({
  className,
  size = "default",
  children,
  ...props
}: Omit<React.ComponentProps<"select">, "size"> & {
  size?: "sm" | "default";
}) {
  return (
    <div className={cn("relative flex w-full items-center", className)}>
      <select
        data-slot="native-select"
        data-size={size}
        className={cn(
          "flex w-full appearance-none items-center justify-between gap-1.5 rounded-md border border-input bg-transparent py-2 pr-8 pl-2.5 text-base whitespace-nowrap shadow-xs transition-[color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 data-[size=default]:h-9 data-[size=sm]:h-8 md:text-sm dark:bg-input/30 dark:hover:bg-input/50 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40",
          // The one native-control adjustment to the registry string above.
          // `SelectTrigger` is a button whose label overflows its box freely,
          // so `py-2` inside the fixed `h-9` is harmless there. A native
          // `<select>` clips to its content box instead, and 36px minus 16px
          // of padding is less than the 24px line box — which cut the
          // descenders off every value. The control centres its own text.
          "py-0",
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDownIcon
        aria-hidden="true"
        className="pointer-events-none absolute right-2.5 size-4 text-muted-foreground"
      />
    </div>
  );
}

export { NativeSelect };
