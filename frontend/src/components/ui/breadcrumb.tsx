import { ChevronRight, MoreHorizontal } from "lucide-react";
import type * as React from "react";
import { useRender } from "@base-ui/react/use-render";

import { cn } from "@/lib/utils";

/**
 * shadcn base-vega Breadcrumb, kept close to upstream. One reconciliation:
 * upstream's `asChild` + radix `Slot` on `BreadcrumbLink` is replaced with the
 * base-ui `render` prop (this repo has no radix), so a router `<Link>` can be
 * passed: `<BreadcrumbLink render={<Link to="/library/tags" />}>Tags</BreadcrumbLink>`.
 */

function Breadcrumb({ ...props }: React.ComponentProps<"nav">) {
  return <nav aria-label="breadcrumb" data-slot="breadcrumb" {...props} />;
}

function BreadcrumbList({ className, ...props }: React.ComponentProps<"ol">) {
  return (
    <ol
      data-slot="breadcrumb-list"
      className={cn(
        "flex flex-wrap items-center gap-1.5 text-sm break-words text-muted-foreground sm:gap-2.5",
        className,
      )}
      {...props}
    />
  );
}

function BreadcrumbItem({ className, ...props }: React.ComponentProps<"li">) {
  return (
    <li
      data-slot="breadcrumb-item"
      className={cn("inline-flex items-center gap-1.5", className)}
      {...props}
    />
  );
}

function BreadcrumbLink({
  className,
  render,
  ...props
}: React.ComponentProps<"a"> & { render?: React.ReactElement }) {
  // `defaultTagName` gives an `<a>` when no `render` is supplied — no literal
  // empty `<a/>` for the a11y lint to flag.
  return useRender({
    render,
    defaultTagName: "a",
    props: {
      "data-slot": "breadcrumb-link",
      className: cn("transition-colors hover:text-foreground", className),
      ...props,
    },
  });
}

// Reconciled from upstream: dropped `role="link"` + `aria-disabled` (a
// non-focusable `role="link"` fails the a11y lint). `aria-current="page"` on
// the span already tells assistive tech this is the current location.
function BreadcrumbPage({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      data-slot="breadcrumb-page"
      aria-current="page"
      className={cn("font-normal text-foreground", className)}
      {...props}
    />
  );
}

function BreadcrumbSeparator({
  children,
  className,
  ...props
}: React.ComponentProps<"li">) {
  return (
    <li
      data-slot="breadcrumb-separator"
      role="presentation"
      aria-hidden="true"
      className={cn("[&>svg]:size-3.5", className)}
      {...props}
    >
      {children ?? <ChevronRight />}
    </li>
  );
}

function BreadcrumbEllipsis({
  className,
  ...props
}: React.ComponentProps<"span">) {
  return (
    <span
      data-slot="breadcrumb-ellipsis"
      role="presentation"
      aria-hidden="true"
      className={cn("flex size-9 items-center justify-center", className)}
      {...props}
    >
      <MoreHorizontal className="size-4" />
      <span className="sr-only">More</span>
    </span>
  );
}

export {
  Breadcrumb,
  BreadcrumbList,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbPage,
  BreadcrumbSeparator,
  BreadcrumbEllipsis,
};
