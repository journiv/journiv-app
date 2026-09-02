import { Button } from "../../../components/ui/button";
import { Skeleton } from "../../../components/ui/skeleton";
import { StatusView } from "../../../components/journiv/StatusView";
import { useSettingsDirty } from "../SettingsModal";
import { SettingsRow, SettingsSection } from "../SettingsSection";
import { PersonalizeSection } from "./PersonalizeSection";
import { useAppearanceForm } from "./useAppearanceForm";
import { NativeSelect } from "../../../components/ui/native-select";
import { Alert, AlertDescription } from "../../../components/ui/alert";

export function AppearancePage() {
  const form = useAppearanceForm();
  useSettingsDirty(form.dirty);
  if (form.query.isLoading)
    return <Skeleton className="jv-settings__skeleton" />;
  if (form.query.isError)
    return (
      <StatusView
        title="Appearance couldn’t be loaded"
        description="Check your connection and try again."
        action={
          <Button variant="secondary" onClick={() => form.query.refetch()}>
            Try again
          </Button>
        }
      />
    );
  return (
    <div className="jv-settings__body">
      <SettingsSection
        title="Appearance"
        intro="These are account defaults. The sidebar theme control remains a per-device override."
        footer={
          <Button
            variant="default"
            disabled={!form.dirty || form.mutation.isPending}
            onClick={() => form.mutation.mutate()}
          >
            {form.mutation.isPending ? "Saving…" : "Save changes"}
          </Button>
        }
      >
        <SettingsRow label="Account theme" htmlFor="account-theme">
          <NativeSelect
            id="account-theme"
            value={form.theme}
            onChange={(event) => form.setTheme(event.target.value)}
          >
            <option value="system">System</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </NativeSelect>
        </SettingsRow>
        <SettingsRow label="Time format" htmlFor="time-format">
          <NativeSelect
            id="time-format"
            value={form.timeFormat}
            onChange={(event) => form.setTimeFormat(event.target.value)}
          >
            <option value="system">System</option>
            <option value="twelve_hour">12-hour</option>
            <option value="twenty_four_hour">24-hour</option>
          </NativeSelect>
        </SettingsRow>
        <SettingsRow label="Week starts on" htmlFor="week-start">
          <NativeSelect
            id="week-start"
            value={form.weekStart}
            onChange={(event) => form.setWeekStart(Number(event.target.value))}
          >
            <option value={0}>Monday</option>
            <option value={1}>Tuesday</option>
            <option value={2}>Wednesday</option>
            <option value={3}>Thursday</option>
            <option value={4}>Friday</option>
            <option value={5}>Saturday</option>
            <option value={6}>Sunday</option>
          </NativeSelect>
        </SettingsRow>
      </SettingsSection>
      {form.mutation.isError && (
        <p className="jv-settings__alert" role="alert">
          Appearance settings couldn’t be saved. Your changes are still here.
        </p>
      )}
      {form.mutation.isSuccess && !form.dirty && (
        <Alert role="status">
          <AlertDescription>Appearance saved.</AlertDescription>
        </Alert>
      )}
      <PersonalizeSection />
      {/* UiExperimentSection is intentionally unmounted — the UI-feel A/B
          framework (src/features/theme/uiExperiment.ts) is kept wired at boot
          for future use but hidden from Settings. Re-add <UiExperimentSection />
          here to run another round. */}
    </div>
  );
}
