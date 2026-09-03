import type { ReactNode } from "react";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "../ui/empty";
import { cn } from "../../lib/utils";

type StatusTone = "neutral" | "danger";

/**
 * Journiv's single pattern for empty, error and "nothing selected" states
 * (DESIGN.md). Built on the stock `Empty`; what this adds is the product
 * contract around it — every state gets a short title and, where an action is
 * possible, exactly one action. Bare sentences floating in a pane are not an
 * acceptable state.
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
    <Empty
      className={cn("mx-auto max-w-[30rem] border-0 p-6", className)}
      role={role}
    >
      <EmptyHeader>
        {icon && (
          <EmptyMedia
            variant="icon"
            className={
              tone === "danger" ? "bg-destructive/10 text-destructive" : ""
            }
          >
            {icon}
          </EmptyMedia>
        )}
        <EmptyTitle className="text-balance">{title}</EmptyTitle>
        {description && (
          <EmptyDescription className="text-pretty">
            {description}
          </EmptyDescription>
        )}
      </EmptyHeader>
      {action && (
        <EmptyContent className="flex-row flex-wrap justify-center">
          {action}
        </EmptyContent>
      )}
    </Empty>
  );
}
