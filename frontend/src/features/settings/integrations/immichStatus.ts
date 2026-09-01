import type {
  ImportMode,
  IntegrationStatusResponse,
} from "../../../api/generated/types.gen";

/**
 * The connection facts the Integrations form renders, derived from the raw
 * status response. Pure so it can be unit-tested without React.
 */
export type ImmichConnectionState = {
  connected: boolean;
  /** `is_active` — a connection can exist but be paused server-side. */
  active: boolean;
  /** The provider last reported a problem; the key almost always needs
   *  re-entering. */
  hasError: boolean;
  mode: ImportMode;
  /**
   * Changes only when the server-side connection identity changes. The form
   * re-seeds its local mode from the server on this key, so a background status
   * refetch never clobbers an in-progress edit.
   */
  identity: string;
};

export function immichConnectionState(
  status: IntegrationStatusResponse | undefined,
): ImmichConnectionState {
  return {
    connected: status?.status === "connected",
    active: status?.is_active ?? false,
    hasError: Boolean(status?.last_error),
    mode: status?.import_mode ?? "link_only",
    identity: status
      ? [
          status.provider,
          status.status,
          status.external_user_id ?? "",
          status.connected_at ?? "",
        ].join(":")
      : "none",
  };
}
