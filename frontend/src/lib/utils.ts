import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Class name joiner used by shadcn-registry components (`@/components/ui/*`).
 * Resolves Tailwind class conflicts so a passed `className` can override the
 * component's own utilities. Feature code that is not shadcn keeps using
 * `cx` from `./cx`.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
