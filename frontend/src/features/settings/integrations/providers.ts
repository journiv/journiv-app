import { Image as ImageIcon, type LucideIcon } from "lucide-react";

/**
 * The integration catalogue as data — one entry per provider Journiv can talk
 * to. There is no list-providers endpoint (see DESIGN.md §23), so the frontend
 * owns this registry; `immich` is the only real provider today. Adding one is:
 * a detail route under `/settings/integrations/`, an entry here, a page.
 *
 * `configured` is answered at render time from `GET /instance/config`
 * (`immich_base_url`), not stored here.
 */
export type IntegrationProviderId = "immich";

export type IntegrationProviderMeta = {
  id: IntegrationProviderId;
  name: string;
  /** One line under the name in the catalogue row. */
  blurb: string;
  /** Public setup guide, opened in a new tab from the row's info control. */
  docsUrl: string;
  Icon: LucideIcon;
};

/** The detail route every provider row links to; the `id` fills `$provider`. */
export const INTEGRATION_DETAIL_ROUTE =
  "/settings/integrations/$provider" as const;

export const INTEGRATION_PROVIDERS: IntegrationProviderMeta[] = [
  {
    id: "immich",
    name: "Immich",
    blurb: "Attach photos and videos from your Immich library while writing.",
    docsUrl: "https://www.journiv.com/docs/guides/immich-integration",
    Icon: ImageIcon,
  },
];
