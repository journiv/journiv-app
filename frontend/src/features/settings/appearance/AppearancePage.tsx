import { Button } from "../../../components/ui/button";
import { Skeleton } from "../../../components/ui/skeleton";
import { StatusView } from "../../../components/journiv/StatusView";
import { useSettingsDirty } from "../SettingsModal";
import { SettingsRow, SettingsSection } from "../SettingsSection";
import { PersonalizeSection } from "./PersonalizeSection";
import { useAppearanceForm } from "./useAppearanceForm";

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
        action={<Button onClick={() => form.query.refetch()}>Try again</Button>}
      />
    );
  return (
    <div className="jv-settings__body">
      <SettingsSection
        title="Appearance"
        intro="These are account defaults. The sidebar theme control remains a per-device override."
      >
        <SettingsRow label="Account theme" htmlFor="account-theme">
          <select
            id="account-theme"
            className="jv-field"
            value={form.theme}
            onChange={(event) => form.setTheme(event.target.value)}
          >
            <option value="system">System</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </SettingsRow>
        <SettingsRow label="Time format" htmlFor="time-format">
          <select
            id="time-format"
            className="jv-field"
            value={form.timeFormat}
            onChange={(event) => form.setTimeFormat(event.target.value)}
          >
            <option value="system">System</option>
            <option value="twelve_hour">12-hour</option>
            <option value="twenty_four_hour">24-hour</option>
          </select>
        </SettingsRow>
        <SettingsRow label="Week starts on" htmlFor="week-start">
          <select
            id="week-start"
            className="jv-field"
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
          </select>
        </SettingsRow>
      </SettingsSection>
      {form.mutation.isError && (
        <p className="jv-settings__alert" role="alert">
          Appearance settings couldn’t be saved. Your changes are still here.
        </p>
      )}
      {form.mutation.isSuccess && !form.dirty && (
        <p className="jv-settings__success">Appearance saved.</p>
      )}
      <div className="jv-settings__actions">
        <Button
          variant="primary"
          disabled={!form.dirty || form.mutation.isPending}
          onClick={() => form.mutation.mutate()}
        >
          {form.mutation.isPending ? "Saving…" : "Save changes"}
        </Button>
      </div>

      <PersonalizeSection />
    </div>
  );
}
