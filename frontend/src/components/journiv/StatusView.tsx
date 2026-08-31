import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

type StatusTone = "neutral" | "danger";

/**
 * Journiv's single pattern for empty, error and "nothing selected" states
 * (DESIGN.md §16). Every one gets a short title and, where an action is
 * possible, exactly one action. Bare sentences floating in a pane are not an
 * acceptable state. A product component — shadcn has no equivalent.
 */
export function StatusView({
  icon,
  title,
  description,
  action,
  tone = "neutral",
  role,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  tone?: StatusTone;
  role?: "status" | "alert";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mx-auto flex max-w-[30rem] flex-col items-center gap-2 px-6 py-8 text-center",
        className,
      )}
      role={role}
    >
      {icon && (
        <span
          className={cn(
            "mb-1 inline-flex size-11 items-center justify-center rounded-lg",
            tone === "danger"
              ? "bg-destructive/10 text-destructive"
              : "bg-muted text-muted-foreground",
          )}
          aria-hidden="true"
        >
          {icon}
        </span>
      )}
      <p className="jv-section-title text-balance text-foreground">{title}</p>
      {description && (
        <p className="text-sm leading-normal text-pretty text-muted-foreground">
          {description}
        </p>
      )}
      {action && (
        <div className="mt-3 flex flex-wrap justify-center gap-2">{action}</div>
      )}
    </div>
  );
}
