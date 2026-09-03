import type { CSSProperties } from "react";

import { cn } from "@/lib/utils";

/**
 * shadcn base-vega Skeleton. Journiv keeps two conveniences over upstream: a
 * decorative `<span aria-hidden>` (valid inside headings / inline flow) and
 * optional `width` / `height` for shape-matching without an arbitrary class at
 * every call site (DESIGN.md).
 */
function Skeleton({
  className,
  width,
  height,
  style,
}: {
  className?: string;
  width?: string;
  height?: string;
  style?: CSSProperties;
}) {
  return (
    <span
      aria-hidden="true"
      data-slot="skeleton"
      className={cn("block animate-pulse rounded-md bg-muted", className)}
      style={{ width, height, ...style }}
    />
  );
}

export { Skeleton };
