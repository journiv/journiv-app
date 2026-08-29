import { Loader2Icon } from "lucide-react";
import { cn } from "@/lib/utils";

function Spinner({ className, ...props }: React.ComponentProps<"svg">) {
  // Decorative when the caller hides it (e.g. beside "Saving…" text); a
  // standalone spinner keeps the status role so it is announced.
  const decorative =
    props["aria-hidden"] === true || props["aria-hidden"] === "true";
  return (
    <Loader2Icon
      data-slot="spinner"
      role={decorative ? undefined : "status"}
      aria-label={decorative ? undefined : "Loading"}
      className={cn("size-4 animate-spin", className)}
      {...props}
    />
  );
}

export { Spinner };
