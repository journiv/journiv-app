import { useQueries } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Info } from "lucide-react";
import {
  instanceConfigQuery,
  integrationStatusQuery,
} from "../../../api/query/options";
import { Button } from "../../../components/ui/button";
import { Skeleton } from "../../../components/ui/skeleton";
import { StatusView } from "../../../components/journiv/StatusView";
import { LibraryRow } from "../../../components/journiv/LibraryRow";
import { SettingsSection } from "../SettingsSection";
import { IntegrationStatusPill } from "./IntegrationStatusPill";
import { INTEGRATION_DETAIL_ROUTE, INTEGRATION_PROVIDERS } from "./providers";
import "./integrations.css";

/**
 * The provider catalogue — one `LibraryRow` per known integration, each linking
 * to its detail route (DESIGN.md §23). A provider the instance has not enabled
 * stays listed but unlinked, with a "Not available" pill. A trailing muted row
 * sets the expectation that more providers are coming.
 *
 * There is no list-providers endpoint; the set is the frontend registry in
 * `providers.ts`. Only Immich is real, so the one status query is enough.
 */
export function IntegrationsCatalogue() {
  const [config, status] = useQueries({
    queries: [instanceConfigQuery(), integrationStatusQuery()],
  });

  if (config.isLoading) return <Skeleton className="jv-settings__skeleton" />;

  if (config.isError)
    return (
      <StatusView
        title="Integrations couldn’t be loaded"
        description="Instance capabilities are unavailable."
        action={
          <Button variant="secondary" onClick={() => config.refetch()}>
            Try again
          </Button>
        }
      />
    );

  const immichConfigured = Boolean(config.data?.immich_base_url);

  return (
    <div className="jv-settings__body">
      <SettingsSection
        title="Integrations"
        intro="Connect Journiv to services you already run. Photos and videos you attach from a connected provider are handled by its import mode."
      >
        <ul className="jv-integrations-list">
          {INTEGRATION_PROVIDERS.map((provider) => {
            const configured =
              provider.id === "immich" ? immichConfigured : false;
            return (
              <LibraryRow
                key={provider.id}
                className="jv-integrations-row"
                leading={
                  <span
                    className="jv-integrations-row__tile"
                    aria-hidden="true"
                  >
                    <provider.Icon size={18} />
                  </span>
                }
                title={provider.name}
                meta={
                  configured ? provider.blurb : "Not enabled on this instance."
                }
                rowLink={
                  configured ? (
                    <Link
                      to={INTEGRATION_DETAIL_ROUTE}
                      params={{ provider: provider.id }}
                      search={{ q: "" }}
                      state={(prev) => prev}
                    />
                  ) : undefined
                }
                actions={
                  <>
                    <IntegrationStatusPill
                      configured={configured}
                      status={status.data}
                      unavailable={configured && status.isError}
                    />
                    <a
                      className="jv-integrations-row__guide"
                      href={provider.docsUrl}
                      target="_blank"
                      rel="noreferrer noopener"
                      aria-label={`${provider.name} setup guide`}
                      title={`${provider.name} setup guide`}
                      onClick={(event) => event.stopPropagation()}
                    >
                      <Info aria-hidden="true" size={15} />
                    </a>
                  </>
                }
              />
            );
          })}

          <LibraryRow
            className="jv-integrations-row jv-integrations-row--soon"
            title="More integrations"
            meta="Additional providers are on the way."
          />
        </ul>
      </SettingsSection>
    </div>
  );
}
