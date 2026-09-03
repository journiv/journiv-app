import { useQuery } from "@tanstack/react-query";
import { instanceConfigQuery } from "../../api/query/options";

/**
 * This instance's Journiv Plus capability, read from `GET /instance/config`
 * (the same query the capability-aware Settings pages use). It lets a Plus-only
 * surface decide what to render WITHOUT calling a protected endpoint and
 * interpreting its 403/503 — see docs/features/library.md "Tags".
 *
 * Three outcomes matter:
 *  - `isSupporter`  → render the Plus feature.
 *  - `available && !isSupporter` → an upsell (there is a licence to buy).
 *  - `!available`   → "not included in this build" (a self-hoster must swap the
 *    image; no call-to-action).
 */
export type PlusCapabilityState = {
  loading: boolean;
  /** Plus code is deployable here (binary loaded, or proxy configured). */
  available: boolean;
  /** Resolved licence tier; "member" is the unlicensed / free state. */
  tier: string;
  /** A paid tier ("supporter" or "believer") is active. */
  isSupporter: boolean;
  /** Where to learn about / buy Journiv Plus. */
  upgradeUrl: string;
};

const SUPPORTER_TIERS = new Set(["supporter", "believer"]);
const FALLBACK_UPGRADE_URL = "https://journiv.com/plus";

export function usePlusCapability(): PlusCapabilityState {
  const { data, isLoading } = useQuery(instanceConfigQuery());
  const plus = data?.plus;
  const tier = plus?.tier ?? "member";
  return {
    loading: isLoading,
    available: plus?.available ?? false,
    tier,
    isSupporter: SUPPORTER_TIERS.has(tier),
    upgradeUrl: plus?.upgrade_url ?? FALLBACK_UPGRADE_URL,
  };
}
