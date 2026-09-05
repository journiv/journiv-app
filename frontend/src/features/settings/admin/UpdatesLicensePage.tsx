import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { api } from "../../../api/client/api";
import { ApiError, isNotFound } from "../../../api/client/errors";
import type { LicenseRegisterRequest } from "../../../api/generated/types.gen";
import { queryKeys } from "../../../api/query/keys";
import {
  currentUserQuery,
  licenseInfoQuery,
  versionCheckEnabledQuery,
  versionInfoQuery,
} from "../../../api/query/options";
import { Alert, AlertDescription } from "../../../components/ui/alert";
import { Button } from "../../../components/ui/button";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "../../../components/ui/field";
import { Input } from "../../../components/ui/input";
import { Skeleton } from "../../../components/ui/skeleton";
import { Spinner } from "../../../components/ui/spinner";
import { Switch } from "../../../components/ui/switch";
import { useSettingsDirty } from "../SettingsModal";
import { SettingsRow, SettingsSection } from "../SettingsSection";
import { useCheckCooldown } from "./useCheckCooldown";

const LICENSE_KEY_PATTERN = /^lic_[A-Za-z0-9]{32}$/;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type CheckFeedback = "success" | "failed" | "rate-limited" | undefined;

function dateTime(value: string | null | undefined) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function retryDuration(seconds: number) {
  if (seconds < 60) return `${seconds} ${seconds === 1 ? "second" : "seconds"}`;
  const minutes = Math.ceil(seconds / 60);
  return `${minutes} ${minutes === 1 ? "minute" : "minutes"}`;
}

function VersionManagement() {
  const queryClient = useQueryClient();
  const version = useQuery(versionInfoQuery());
  const enabled = useQuery(versionCheckEnabledQuery());
  const cooldown = useCheckCooldown();
  const [feedback, setFeedback] = useState<CheckFeedback>();

  const check = useMutation({
    mutationFn: () => api.forceVersionCheck(),
    onSuccess: (result) => {
      if (result.version_info)
        queryClient.setQueryData(queryKeys.versionInfo, result.version_info);

      if (result.success) {
        cooldown.clear();
        setFeedback("success");
        return;
      }

      if (result.retry_after_seconds) {
        cooldown.begin(result.retry_after_seconds);
        setFeedback("rate-limited");
        return;
      }

      setFeedback("failed");
    },
    onError: () => setFeedback("failed"),
  });

  const automaticChecks = useMutation({
    mutationFn: (nextEnabled: boolean) =>
      api.updateVersionCheckEnabled({ enabled: nextEnabled }),
    onSuccess: async (result) => {
      queryClient.setQueryData(queryKeys.versionCheckEnabled, result);
      // Enabling performs an immediate check on the backend. Refetch its cached
      // result instead of issuing another manual check from the browser.
      await queryClient.invalidateQueries({ queryKey: queryKeys.versionInfo });
    },
  });

  if (version.isLoading || enabled.isLoading)
    return <Skeleton className="jv-settings__skeleton" />;

  if (version.isError || !version.data || enabled.isError || !enabled.data)
    return (
      <SettingsSection
        title="Version checking"
        intro="Keep this installation informed about Journiv releases."
        footer={
          <Button
            variant="secondary"
            onClick={() => {
              void version.refetch();
              void enabled.refetch();
            }}
          >
            Try again
          </Button>
        }
      >
        <Alert variant="destructive">
          <AlertDescription>
            Version management couldn’t be loaded. Check the connection and try
            again.
          </AlertDescription>
        </Alert>
      </SettingsSection>
    );

  const info = version.data;
  const lastChecked = dateTime(info.last_checked);
  const updateAvailable = Boolean(info.update_available);
  const latestVersion = info.latest_version;
  const versionStatus = updateAvailable
    ? `Update available${latestVersion ? `: ${latestVersion}` : ""}`
    : latestVersion
      ? "Up to date"
      : enabled.data.enabled
        ? "No update information yet"
        : "Automatic checks are off";
  const lastCheckStatus = !lastChecked
    ? "Not checked yet"
    : info.last_check_success === false
      ? `Couldn’t complete ${lastChecked}`
      : `Checked ${lastChecked}`;

  return (
    <SettingsSection
      title="Version checking"
      intro="Manage release checks for this Journiv installation."
      footer={
        <Button
          variant="default"
          disabled={check.isPending || cooldown.seconds > 0}
          onClick={() => {
            setFeedback(undefined);
            check.mutate();
          }}
        >
          {check.isPending ? (
            <Spinner aria-hidden="true" data-icon="inline-start" />
          ) : null}
          {check.isPending
            ? "Checking…"
            : cooldown.seconds > 0
              ? `Try again in ${retryDuration(cooldown.seconds)}`
              : "Check for updates"}
        </Button>
      }
    >
      <SettingsRow label="Installed version">
        <p className="jv-settings-row__readonly">{info.current_version}</p>
      </SettingsRow>
      <SettingsRow label="Update status">
        <p className="jv-settings-row__readonly">{versionStatus}</p>
        {updateAvailable && info.update_url ? (
          <a href={info.update_url} target="_blank" rel="noreferrer">
            View update
          </a>
        ) : null}
        {info.changelog_url ? (
          <a href={info.changelog_url} target="_blank" rel="noreferrer">
            View changelog
          </a>
        ) : null}
      </SettingsRow>
      <SettingsRow label="Last check">
        <p className="jv-settings-row__readonly">{lastCheckStatus}</p>
      </SettingsRow>
      <SettingsRow
        label="Automatic version checking"
        htmlFor="automatic-version-checking"
        description={
          enabled.data.enabled
            ? "Journiv checks for updates automatically."
            : "Automatic checks are off. You can still check manually."
        }
      >
        <Switch
          id="automatic-version-checking"
          checked={enabled.data.enabled}
          disabled={automaticChecks.isPending}
          onCheckedChange={(nextEnabled) => {
            automaticChecks.mutate(nextEnabled);
          }}
        />
        {automaticChecks.isError ? (
          <FieldError>
            Automatic version checking couldn’t be updated. Try again.
          </FieldError>
        ) : null}
      </SettingsRow>
      <SettingsRow
        label="Check now"
        description="Checks the release service immediately. It may be rate limited."
      >
        {feedback === "success" ? (
          <FieldDescription role="status">
            Update check complete.
          </FieldDescription>
        ) : null}
        {feedback === "rate-limited" && cooldown.seconds > 0 ? (
          <FieldDescription role="status">
            The release service is rate limiting this installation. Try again in
            {` ${retryDuration(cooldown.seconds)}.`}
          </FieldDescription>
        ) : null}
        {feedback === "failed" ? (
          <FieldError>
            Journiv couldn’t check for updates. The cached version details are
            still shown above.
          </FieldError>
        ) : null}
      </SettingsRow>
    </SettingsSection>
  );
}

function RegistrationForm({
  defaultEmail,
  onRegistered,
}: {
  defaultEmail: string;
  onRegistered: () => Promise<void>;
}) {
  const licenseId = useId();
  const emailId = useId();
  const discordId = useId();
  const initialEmail = useRef(defaultEmail);
  const emailEdited = useRef(false);
  const [license, setLicense] = useState("");
  const [email, setEmail] = useState(defaultEmail);
  const [discord, setDiscord] = useState("");
  const [touched, setTouched] = useState(false);
  const [succeeded, setSucceeded] = useState(false);
  const [failure, setFailure] = useState<string>();

  // Prefill from the signed-in admin, but only while the field is still
  // pristine. `currentUserQuery` can resolve after this form has mounted with an
  // empty default, and a late fill must never overwrite an address the admin has
  // already begun typing.
  useEffect(() => {
    if (emailEdited.current || email.length > 0 || !defaultEmail) return;
    initialEmail.current = defaultEmail;
    setEmail(defaultEmail);
  }, [defaultEmail, email]);

  const licenseIssue = LICENSE_KEY_PATTERN.test(license.trim())
    ? null
    : "Enter the license key beginning with lic_.";
  const emailIssue = EMAIL_PATTERN.test(email.trim())
    ? null
    : "Enter a valid email address.";
  const valid = !licenseIssue && !emailIssue;
  const dirty =
    !succeeded &&
    (license.length > 0 ||
      email !== initialEmail.current ||
      discord.length > 0);
  useSettingsDirty(dirty);

  const registration = useMutation({
    mutationFn: () => {
      const body: LicenseRegisterRequest = {
        license: license.trim(),
        email: email.trim(),
        ...(discord.trim() ? { discord_id: discord.trim() } : {}),
      };
      return api.registerLicense(body);
    },
    onSuccess: async (result) => {
      if (!result.successful) {
        // `error_message` is the endpoint's user-facing reason (already bound,
        // email mismatch, rate limited, …). Prefer it; fall back to a generic
        // per-case string when the server sent nothing usable.
        const reason = result.error_message?.trim();
        setFailure(
          reason ||
            (result.rate_limited
              ? "License registration is temporarily rate limited. Try again later."
              : "This license couldn’t be registered. Check the key and email, then try again."),
        );
        return;
      }
      setLicense("");
      setDiscord("");
      setTouched(false);
      setSucceeded(true);
      await onRegistered();
    },
    onError: (error) => {
      const clientError = error instanceof ApiError && error.status;
      setFailure(
        clientError && clientError >= 400 && clientError < 500
          ? "This license couldn’t be registered. Check the key and email, then try again."
          : "License registration couldn’t be completed. Check the connection and try again.",
      );
    },
  });

  function update(set: (value: string) => void, value: string) {
    setSucceeded(false);
    setFailure(undefined);
    set(value);
  }

  function submit() {
    setTouched(true);
    setSucceeded(false);
    setFailure(undefined);
    if (!valid || registration.isPending) return;
    registration.mutate();
  }

  return (
    <SettingsSection
      title="Register a license"
      intro="Add a Journiv Plus license to this installation."
      footer={
        <Button
          type="submit"
          form="license-registration"
          disabled={registration.isPending}
        >
          {registration.isPending ? (
            <Spinner aria-hidden="true" data-icon="inline-start" />
          ) : null}
          {registration.isPending ? "Registering…" : "Register license"}
        </Button>
      }
    >
      {succeeded ? (
        <Alert role="status">
          <AlertDescription>
            License registered. Refreshing its installation details…
          </AlertDescription>
        </Alert>
      ) : null}
      {failure ? (
        <Alert variant="destructive">
          <AlertDescription>{failure}</AlertDescription>
        </Alert>
      ) : null}
      <form
        id="license-registration"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <FieldGroup className="jv-settings-form">
          <Field data-invalid={touched && Boolean(licenseIssue)}>
            <FieldLabel htmlFor={licenseId}>License key</FieldLabel>
            <Input
              id={licenseId}
              type="text"
              autoComplete="off"
              spellCheck={false}
              value={license}
              onChange={(event) => update(setLicense, event.target.value)}
              aria-invalid={touched && Boolean(licenseIssue)}
              aria-describedby={
                touched && licenseIssue ? `${licenseId}-error` : undefined
              }
            />
            {touched && licenseIssue ? (
              <FieldError id={`${licenseId}-error`}>{licenseIssue}</FieldError>
            ) : null}
          </Field>
          <Field data-invalid={touched && Boolean(emailIssue)}>
            <FieldLabel htmlFor={emailId}>Admin email</FieldLabel>
            <Input
              id={emailId}
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => {
                emailEdited.current = true;
                update(setEmail, event.target.value);
              }}
              aria-invalid={touched && Boolean(emailIssue)}
              aria-describedby={
                touched && emailIssue ? `${emailId}-error` : undefined
              }
            />
            {touched && emailIssue ? (
              <FieldError id={`${emailId}-error`}>{emailIssue}</FieldError>
            ) : null}
          </Field>
          <Field>
            <FieldLabel htmlFor={discordId}>Discord ID (optional)</FieldLabel>
            <Input
              id={discordId}
              type="text"
              autoComplete="off"
              spellCheck={false}
              value={discord}
              onChange={(event) => update(setDiscord, event.target.value)}
              aria-describedby={`${discordId}-description`}
            />
            <FieldDescription id={`${discordId}-description`}>
              Add the Discord ID associated with your Plus membership, if you
              have one.
            </FieldDescription>
          </Field>
        </FieldGroup>
      </form>
    </SettingsSection>
  );
}

function LicenseManagement() {
  const queryClient = useQueryClient();
  const user = useQuery(currentUserQuery());
  const license = useQuery(licenseInfoQuery());
  const noLicense = license.isError && isNotFound(license.error);

  async function refreshLicense() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.licenseInfo }),
      queryClient.invalidateQueries({ queryKey: queryKeys.instanceConfig }),
    ]);
  }

  if (license.isLoading) return <Skeleton className="jv-settings__skeleton" />;

  if (noLicense)
    return (
      <RegistrationForm
        defaultEmail={user.data?.email ?? ""}
        onRegistered={refreshLicense}
      />
    );

  if (license.isError || !license.data)
    return (
      <SettingsSection
        title="Journiv Plus"
        intro="View the license registered to this installation."
        footer={
          <Button variant="secondary" onClick={() => void license.refetch()}>
            Try again
          </Button>
        }
      >
        <Alert variant="destructive">
          <AlertDescription>
            License details couldn’t be loaded. Check the connection and try
            again.
          </AlertDescription>
        </Alert>
      </SettingsSection>
    );

  const info = license.data;
  const expiresAt = dateTime(info.subscription_expires_at);
  const expired =
    Boolean(info.subscription_expires_at) &&
    new Date(info.subscription_expires_at as string).getTime() < Date.now();
  const status = info.is_active ? "Active" : expired ? "Expired" : "Inactive";

  return (
    <>
      <SettingsSection
        title="Journiv Plus"
        intro="This license is registered to the current installation."
      >
        <SettingsRow label="Status">
          <p className="jv-settings-row__readonly">{status}</p>
        </SettingsRow>
        <SettingsRow label="Tier">
          <p className="jv-settings-row__readonly">
            {info.tier ?? "No tier reported"}
          </p>
        </SettingsRow>
        <SettingsRow label="License type">
          <p className="jv-settings-row__readonly">
            {info.license_type === "lifetime" ? "Lifetime" : "Subscription"}
          </p>
        </SettingsRow>
        {expiresAt ? (
          <SettingsRow label={expired ? "Expired" : "Expires"}>
            <p className="jv-settings-row__readonly">{expiresAt}</p>
          </SettingsRow>
        ) : null}
        {info.registered_email ? (
          <SettingsRow label="Registered email">
            <p className="jv-settings-row__readonly">{info.registered_email}</p>
          </SettingsRow>
        ) : null}
        {info.discord_id ? (
          <SettingsRow label="Discord ID">
            <p className="jv-settings-row__readonly">{info.discord_id}</p>
          </SettingsRow>
        ) : null}
      </SettingsSection>
      {!info.is_active ? (
        <RegistrationForm
          defaultEmail={user.data?.email ?? ""}
          onRegistered={refreshLicense}
        />
      ) : null}
    </>
  );
}

export function UpdatesLicensePage() {
  return (
    <div className="jv-settings__body">
      <VersionManagement />
      <LicenseManagement />
    </div>
  );
}
