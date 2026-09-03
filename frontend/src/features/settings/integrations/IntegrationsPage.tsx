import { useQueries } from "@tanstack/react-query";
import { Link, useMatchRoute } from "@tanstack/react-router";
import { ChevronLeft } from "lucide-react";
import {
  instanceConfigQuery,
  integrationStatusQuery,
} from "../../../api/query/options";
import { Button } from "../../../components/ui/button";
import { Skeleton } from "../../../components/ui/skeleton";
import { StatusView } from "../../../components/journiv/StatusView";
import { ImmichConnectForm } from "./ImmichConnectForm";
import { IntegrationsCatalogue } from "./IntegrationsCatalogue";
import "./integrations.css";

/**
 * `/settings/integrations` is the provider catalogue;
 * `/settings/integrations/immich` is the Immich detail. Both carry
 * `staticData.settings: "integrations"`, so the modal chrome and the "Providers"
 * nav item are unchanged across the drill-down — only this pane swaps
 * (docs/features/settings.md). An unknown provider sub-route is redirected to the catalogue
 * by the router, so anything that reaches here that is not the Immich detail is
 * the catalogue.
 */
export function IntegrationsPage() {
  const matchRoute = useMatchRoute();
  if (matchRoute({ to: "/settings/integrations/$provider" }))
    return <ImmichIntegrationDetail />;
  return <IntegrationsCatalogue />;
}

function ImmichIntegrationDetail() {
  const [config, status] = useQueries({
    queries: [instanceConfigQuery(), integrationStatusQuery()],
  });

  const back = (
    <Link
      to="/settings/integrations"
      search={{ q: "" }}
      state={(prev) => prev}
      className="jv-integrations__back jv-desktop-only jv-caption"
    >
      <ChevronLeft aria-hidden="true" size={15} />
      Back to integrations
    </Link>
  );

  if (config.isLoading || status.isLoading)
    return (
      <>
        {back}
        <Skeleton className="jv-settings__skeleton" />
      </>
    );

  if (config.isError)
    return (
      <>
        {back}
        <StatusView
          title="Integrations couldn’t be loaded"
          description="Instance capabilities are unavailable."
          action={
            <Button variant="secondary" onClick={() => config.refetch()}>
              Try again
            </Button>
          }
        />
      </>
    );

  if (status.isError || !status.data)
    return (
      <>
        {back}
        <StatusView
          title="Integration status couldn’t be loaded"
          description="Check your connection and try again."
          action={
            <Button variant="secondary" onClick={() => status.refetch()}>
              Try again
            </Button>
          }
        />
      </>
    );

  if (!config.data?.immich_base_url)
    return (
      <>
        {back}
        <StatusView
          title="Immich isn’t enabled on this instance"
          description="An administrator has not configured an Immich server."
        />
      </>
    );

  return (
    <>
      {back}
      <ImmichConnectForm
        baseUrl={config.data.immich_base_url}
        status={status.data}
      />
    </>
  );
}
