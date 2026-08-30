import { useQuery } from "@tanstack/react-query";
import {
  currentUserQuery,
  instanceConfigQuery,
  licenseInfoQuery,
  versionInfoQuery,
} from "../../../api/query/options";
import { Button } from "../../../components/ui/button";
import { Skeleton } from "../../../components/ui/skeleton";
import { StatusView } from "../../../components/journiv/StatusView";
import { SettingsRow, SettingsSection } from "../SettingsSection";

export function AboutPage() {
  const config = useQuery(instanceConfigQuery());
  const user = useQuery(currentUserQuery());
  const isAdmin = user.data?.role === "admin";
  // `/instance/version/info` and `/instance/license/info` are admin-only on the
  // backend (403 otherwise). Ask for them only when they can succeed, so a
  // normal user sees the capability rows rather than an empty value or an error.
  const version = useQuery({ ...versionInfoQuery(), enabled: isAdmin });
  const license = useQuery({ ...licenseInfoQuery(), enabled: isAdmin });

  if (config.isLoading || user.isLoading || (isAdmin && version.isLoading))
    return <Skeleton className="jv-settings__skeleton" />;
  // The public instance config is the only required payload here.
  if (config.isError || !config.data)
    return (
      <StatusView
        title="About couldn’t be loaded"
        description="Check your connection and try again."
        action={
          <Button
            onClick={() => {
              void config.refetch();
              if (isAdmin) void version.refetch();
            }}
          >
            Try again
          </Button>
        }
      />
    );

  return (
    <div className="jv-settings__body">
      <SettingsSection
        title="About Journiv"
        intro="What this Journiv instance reports about itself."
      >
        {version.data && (
          <>
            <SettingsRow label="Current version">
              <p className="jv-settings-row__readonly">
                {version.data.current_version}
              </p>
            </SettingsRow>
            {version.data.latest_version && (
              <SettingsRow label="Latest version">
                <p className="jv-settings-row__readonly">
                  {version.data.latest_version}
                  {version.data.update_available ? " · update available" : ""}
                </p>
                {version.data.update_url && (
                  <a
                    href={version.data.update_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    View update
                  </a>
                )}
              </SettingsRow>
            )}
          </>
        )}
        <SettingsRow label="Import limit">
          <p className="jv-settings-row__readonly">
            {config.data.import_export_max_file_size_mb} MB
          </p>
        </SettingsRow>
        <SettingsRow label="Sign-up">
          <p className="jv-settings-row__readonly">
            {config.data.disable_signup ? "Disabled" : "Enabled"}
          </p>
        </SettingsRow>
        {config.data.oidc_enabled && (
          <SettingsRow label="Single sign-on">
            <p className="jv-settings-row__readonly">Enabled</p>
          </SettingsRow>
        )}
        {license.data && (
          <SettingsRow label="Plus license">
            <p className="jv-settings-row__readonly">
              {license.data.is_active
                ? (license.data.tier ?? "Active")
                : "Inactive"}
            </p>
          </SettingsRow>
        )}
      </SettingsSection>
    </div>
  );
}
