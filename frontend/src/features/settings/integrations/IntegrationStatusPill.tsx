import type { IntegrationStatusResponse } from "../../../api/generated/types.gen";
import { cx } from "../../../lib/cx";
import { Badge } from "../../../components/ui/badge";
import { immichConnectionState } from "./immichStatus";

type Tone = "ok" | "warn" | "muted";

/**
 * The at-a-glance connection state for a catalogue row. A dot **plus** a label
 * — never colour alone (DESIGN.md). Derives from the same pure
 * `immichConnectionState` the detail form uses.
 */
export function IntegrationStatusPill({
  configured,
  status,
  unavailable = false,
}: {
  /** The instance exposes this provider at all (`immich_base_url` present). */
  configured: boolean;
  status: IntegrationStatusResponse | undefined;
  /** The status request itself failed — we cannot say connected or not. */
  unavailable?: boolean;
}) {
  const { label, tone } = unavailable
    ? { label: "Status unavailable", tone: "muted" as Tone }
    : resolve(configured, status);
  return (
    <Badge variant="outline" className="jv-status-pill">
      <span
        className={cx("jv-status-pill__dot", `jv-status-pill__dot--${tone}`)}
        aria-hidden="true"
      />
      {label}
    </Badge>
  );
}

function resolve(
  configured: boolean,
  status: IntegrationStatusResponse | undefined,
): { label: string; tone: Tone } {
  if (!configured) return { label: "Not available", tone: "muted" };
  const state = immichConnectionState(status);
  if (!state.connected) return { label: "Not connected", tone: "muted" };
  if (state.hasError) return { label: "Attention needed", tone: "warn" };
  if (!state.active) return { label: "Paused", tone: "muted" };
  return { label: "Connected", tone: "ok" };
}
