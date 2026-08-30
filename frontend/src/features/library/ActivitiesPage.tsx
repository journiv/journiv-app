import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  Menu,
  MoreHorizontal,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { type CSSProperties, type ReactNode, useId, useState } from "react";
import type {
  ActivityCreate,
  ActivityGroupCreate,
  ActivityGroupUpdate,
  ActivityGroupWithActivitiesResponse,
  ActivityResponse,
  ActivityUpdate,
} from "../../api/generated/types.gen";
import { api } from "../../api/client/api";
import { queryKeys } from "../../api/query/keys";
import { activitiesQuery, activityGroupsQuery } from "../../api/query/options";
import { EntityGlyph } from "../../components/journiv/EntityGlyph";
import { LibraryRow } from "../../components/journiv/LibraryRow";
import { PageBar } from "../../components/journiv/PageBar";
import { StatusView } from "../../components/journiv/StatusView";
import { Button } from "../../components/ui/button";
import { Dialog, DialogClose } from "../../components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { IconButton } from "../../components/ui/icon-button";
import { Input } from "../../components/ui/input";
import { SearchInput } from "../../components/ui/search-input";
import { Skeleton } from "../../components/ui/skeleton";
import { colorFromArgb, ENTITY_COLOR_PRESETS } from "../../lib/color";
import { cx } from "../../lib/cx";
import { JOURNAL_ICONS } from "../../lib/journalIcons";
import { useShell } from "../shell/AppShell";
import { GroupsManagerDialog } from "./GroupsManagerDialog";
import { ViewMomentsMenuItem } from "./ViewMomentsMenuItem";
import "./library.css";

type ActivityFormState =
  | { mode: "create"; groupId: string | null }
  | { mode: "edit"; activity: ActivityResponse };

function countLabel(count: number) {
  return `${count} ${count === 1 ? "activity" : "activities"}`;
}

function GroupSection({
  title,
  quiet,
  colorValue,
  icon,
  count,
  open,
  onToggle,
  menu,
  children,
}: {
  title: string;
  quiet?: boolean;
  colorValue?: number | null;
  icon?: string | null;
  count: number;
  open: boolean;
  onToggle: () => void;
  menu?: ReactNode;
  children: ReactNode;
}) {
  const hex = colorFromArgb(colorValue);
  return (
    <section
      className={cx("jv-lib-section", quiet && "jv-lib-section--quiet")}
      style={hex ? ({ "--entity-accent": hex } as CSSProperties) : undefined}
    >
      <div className="jv-lib-section__head">
        <button
          type="button"
          className="jv-lib-section__toggle"
          aria-expanded={open}
          aria-label={`${title}, ${countLabel(count)}`}
          onClick={onToggle}
        >
          {open ? (
            <ChevronDown
              className="jv-lib-section__chevron"
              aria-hidden="true"
              size={16}
            />
          ) : (
            <ChevronRight
              className="jv-lib-section__chevron"
              aria-hidden="true"
              size={16}
            />
          )}
          {!quiet && (
            <EntityGlyph colorValue={colorValue} icon={icon} size={13} />
          )}
          <span className="jv-lib-section__name jv-section-title jv-truncate">
            {title}
          </span>
          <span className="jv-lib-section__rule" aria-hidden="true" />
        </button>
        <span className="jv-lib-section__count jv-meta">
          {countLabel(count)}
        </span>
        {menu ?? <span className="jv-lib-section__slot" aria-hidden="true" />}
      </div>
      {open && children}
    </section>
  );
}

function ActivityListItem({
  activity,
  onEdit,
  onDelete,
}: {
  activity: ActivityResponse;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <LibraryRow
      leading={
        <EntityGlyph color={activity.color} icon={activity.icon} size={16} />
      }
      title={activity.name}
      actions={
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <IconButton label={`${activity.name} actions`}>
                <MoreHorizontal aria-hidden="true" size={17} />
              </IconButton>
            }
          />
          <DropdownMenuContent align="end">
            <ViewMomentsMenuItem scope={{ activity: activity.id }} />
            <DropdownMenuItem onClick={onEdit}>
              <Pencil aria-hidden="true" size={15} />
              Edit activity
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onClick={onDelete}>
              <Trash2 aria-hidden="true" size={15} />
              Delete activity…
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      }
    />
  );
}

export function ActivitiesPage() {
  const shell = useShell();
  const qc = useQueryClient();
  const activitiesResult = useQuery(activitiesQuery());
  const groupsResult = useQuery(activityGroupsQuery());
  const activities = activitiesResult.data ?? [];
  const groups = groupsResult.data ?? [];

  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [ungroupedOpen, setUngroupedOpen] = useState<boolean>();
  const [activityForm, setActivityForm] = useState<ActivityFormState>();
  const [deleteActivityTarget, setDeleteActivityTarget] =
    useState<ActivityResponse>();
  const [deleteGroupTarget, setDeleteGroupTarget] =
    useState<ActivityGroupWithActivitiesResponse>();
  const [groupsManager, setGroupsManager] = useState<{
    initialGroup?: ActivityGroupWithActivitiesResponse;
  }>();

  const refresh = async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: queryKeys.activities }),
      qc.invalidateQueries({ queryKey: queryKeys.activityGroups }),
    ]);
  };
  const createActivity = useMutation({
    mutationFn: (body: ActivityCreate) => api.createActivity(body),
    onSuccess: async () => {
      setActivityForm(undefined);
      await refresh();
    },
  });
  const updateActivity = useMutation({
    mutationFn: ({ id, body }: { id: string; body: ActivityUpdate }) =>
      api.updateActivity(id, body),
    onSuccess: async () => {
      setActivityForm(undefined);
      await refresh();
    },
  });
  const removeActivity = useMutation({
    mutationFn: (id: string) => api.deleteActivity(id),
    onSuccess: async () => {
      setDeleteActivityTarget(undefined);
      await refresh();
    },
  });
  const createGroup = useMutation({
    mutationFn: (body: ActivityGroupCreate) => api.createActivityGroup(body),
    onSuccess: refresh,
  });
  const updateGroup = useMutation({
    mutationFn: ({ id, body }: { id: string; body: ActivityGroupUpdate }) =>
      api.updateActivityGroup(id, body),
    onSuccess: refresh,
  });
  const removeGroup = useMutation({
    mutationFn: (id: string) => api.deleteActivityGroup(id),
    onSuccess: async () => {
      setDeleteGroupTarget(undefined);
      await refresh();
    },
  });

  const loading = activitiesResult.isLoading || groupsResult.isLoading;
  const loadError = activitiesResult.isError || groupsResult.isError;
  const normalizedSearch = search.trim().toLowerCase();
  const searching = normalizedSearch.length > 0;
  const matchesActivity = (activity: ActivityResponse) =>
    !searching || activity.name.toLowerCase().includes(normalizedSearch);

  const groupView = groups.map((group) => {
    const members = activities
      .filter((activity) => activity.group_id === group.id)
      .sort(comparePositionThenName);
    return {
      group,
      members,
      visible: members.filter(matchesActivity),
      nameMatches:
        searching && group.name.toLowerCase().includes(normalizedSearch),
    };
  });
  const ungrouped = activities
    .filter((activity) => !activity.group_id)
    .sort(comparePositionThenName)
    .filter(matchesActivity);
  const nothingMatches =
    searching &&
    !ungrouped.length &&
    groupView.every(
      ({ visible, nameMatches }) => !visible.length && !nameMatches,
    );

  const toggleGroup = (id: string) =>
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <main className="jv-library" aria-label="Activities">
      <PageBar
        className="jv-page-bar--compact-only"
        leading={
          <IconButton label="Open navigation" onClick={shell.openNavigation}>
            <Menu aria-hidden="true" size={19} />
          </IconButton>
        }
        title={<span className="jv-label jv-truncate">Activities</span>}
      />
      <header className="jv-library__header">
        <div className="jv-library__headings">
          <h1 className="jv-display jv-library__heading">Activities</h1>
          <p className="jv-library__intro jv-body">
            Organise the activities you record in your journal.
          </p>
        </div>
        <div className="jv-library__actions">
          <Button onClick={() => setGroupsManager({})}>Manage groups</Button>
          <Button
            variant="primary"
            onClick={() => setActivityForm({ mode: "create", groupId: null })}
          >
            <Plus aria-hidden="true" size={16} />
            Add activity
          </Button>
        </div>
      </header>

      <div className="jv-library__scroll">
        <div className="jv-library__body">
          <SearchInput
            className="jv-search-wrap"
            label="Search activities"
            placeholder="Search activities or groups…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onClear={() => setSearch("")}
          />

          {loading && <ActivitiesSkeleton />}
          {loadError && (
            <StatusView
              role="alert"
              tone="danger"
              icon={<TriangleAlert size={20} />}
              title="Activities could not be loaded"
              description="Check your connection and try again."
              action={
                <Button
                  onClick={() => {
                    activitiesResult.refetch();
                    groupsResult.refetch();
                  }}
                >
                  Try again
                </Button>
              }
            />
          )}
          {!loading && !loadError && !activities.length && !groups.length && (
            <StatusView
              icon={<Sparkles size={20} />}
              title="No activities yet"
              description="Add an activity or create a group to begin organising your Library."
              action={
                <Button
                  variant="primary"
                  onClick={() =>
                    setActivityForm({ mode: "create", groupId: null })
                  }
                >
                  <Plus aria-hidden="true" size={16} />
                  Add activity
                </Button>
              }
            />
          )}
          {!loading &&
            !loadError &&
            (activities.length > 0 || groups.length > 0) && (
              <div className="jv-lib-dir">
                {groupView.map(({ group, members, visible, nameMatches }) => {
                  if (searching && !nameMatches && !visible.length) return null;
                  return (
                    <GroupSection
                      key={group.id}
                      title={group.name}
                      colorValue={group.color_value}
                      icon={group.icon}
                      count={group.activities?.length ?? members.length}
                      open={searching || !collapsed.has(group.id)}
                      onToggle={() => toggleGroup(group.id)}
                      menu={
                        <DropdownMenu>
                          <DropdownMenuTrigger
                            render={
                              <IconButton label={`${group.name} group actions`}>
                                <MoreHorizontal aria-hidden="true" size={17} />
                              </IconButton>
                            }
                          />
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() =>
                                setActivityForm({
                                  mode: "create",
                                  groupId: group.id,
                                })
                              }
                            >
                              <Plus aria-hidden="true" size={15} />
                              Add activity to group
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() =>
                                setGroupsManager({ initialGroup: group })
                              }
                            >
                              <Pencil aria-hidden="true" size={15} />
                              Edit group
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              variant="destructive"
                              onClick={() => setDeleteGroupTarget(group)}
                            >
                              <Trash2 aria-hidden="true" size={15} />
                              Delete group…
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      }
                    >
                      {visible.length ? (
                        <ul className="jv-lib-section__grid">
                          {visible.map((activity) => (
                            <ActivityListItem
                              key={activity.id}
                              activity={activity}
                              onEdit={() =>
                                setActivityForm({
                                  mode: "edit",
                                  activity,
                                })
                              }
                              onDelete={() => setDeleteActivityTarget(activity)}
                            />
                          ))}
                        </ul>
                      ) : (
                        <div className="jv-lib-section__empty">
                          {searching ? (
                            <span>No matching activities in this group.</span>
                          ) : (
                            <>
                              <span>No activities in this group yet.</span>
                              <Button
                                variant="ghost"
                                onClick={() =>
                                  setActivityForm({
                                    mode: "create",
                                    groupId: group.id,
                                  })
                                }
                              >
                                <Plus aria-hidden="true" size={15} />
                                Add activity
                              </Button>
                            </>
                          )}
                        </div>
                      )}
                    </GroupSection>
                  );
                })}

                {ungrouped.length > 0 && (
                  <GroupSection
                    quiet
                    title="Without a group"
                    count={ungrouped.length}
                    open={searching || (ungroupedOpen ?? groups.length === 0)}
                    onToggle={() =>
                      setUngroupedOpen((open) => !(open ?? groups.length === 0))
                    }
                  >
                    <ul className="jv-lib-section__grid">
                      {ungrouped.map((activity) => (
                        <ActivityListItem
                          key={activity.id}
                          activity={activity}
                          onEdit={() =>
                            setActivityForm({ mode: "edit", activity })
                          }
                          onDelete={() => setDeleteActivityTarget(activity)}
                        />
                      ))}
                    </ul>
                  </GroupSection>
                )}

                {nothingMatches && (
                  <div className="jv-lib-dir__nomatch">
                    <StatusView
                      title="No activities found"
                      description={`No activities or groups match “${search.trim()}”.`}
                      action={
                        <Button onClick={() => setSearch("")}>
                          Clear search
                        </Button>
                      }
                    />
                  </div>
                )}
              </div>
            )}
        </div>
      </div>

      {activityForm && (
        <ActivityFormDialog
          state={activityForm}
          groups={groups}
          submitting={createActivity.isPending || updateActivity.isPending}
          failed={createActivity.isError || updateActivity.isError}
          onClose={() => setActivityForm(undefined)}
          onSubmit={async (body) => {
            if (activityForm.mode === "create")
              await createActivity.mutateAsync(body as ActivityCreate);
            else
              await updateActivity.mutateAsync({
                id: activityForm.activity.id,
                body,
              });
          }}
        />
      )}
      {groupsManager && (
        <GroupsManagerDialog
          groups={groups}
          initialGroup={groupsManager.initialGroup}
          itemNoun={{ singular: "activity", plural: "activities" }}
          itemCount={(group) =>
            (group as ActivityGroupWithActivitiesResponse).activities?.length ??
            0
          }
          busy={
            createGroup.isPending ||
            updateGroup.isPending ||
            removeGroup.isPending
          }
          saveFailed={createGroup.isError || updateGroup.isError}
          deleteFailed={removeGroup.isError}
          onClose={() => setGroupsManager(undefined)}
          onCreate={async (body) => {
            await createGroup.mutateAsync({ ...body, position: groups.length });
          }}
          onUpdate={async (id, body) => {
            await updateGroup.mutateAsync({ id, body });
          }}
          onDelete={async (id) => {
            await removeGroup.mutateAsync(id);
          }}
        />
      )}
      {deleteActivityTarget && (
        <Dialog
          open
          onOpenChange={(open) => !open && setDeleteActivityTarget(undefined)}
          title={`Delete ${deleteActivityTarget.name}?`}
          description="The activity is hidden from active lists. Existing moment references remain."
        >
          {removeActivity.isError && (
            <p className="jv-library__alert" role="alert">
              The activity could not be deleted. Try again.
            </p>
          )}
          <div className="jv-dialog__actions">
            <DialogClose render={<Button>Cancel</Button>} />
            <Button
              variant="danger"
              disabled={removeActivity.isPending}
              onClick={() => removeActivity.mutate(deleteActivityTarget.id)}
            >
              {removeActivity.isPending ? "Deleting…" : "Delete activity"}
            </Button>
          </div>
        </Dialog>
      )}
      {deleteGroupTarget && (
        <Dialog
          open
          onOpenChange={(open) => !open && setDeleteGroupTarget(undefined)}
          title={`Delete ${deleteGroupTarget.name}?`}
          description="Activities remain in your Library and move to Without a group."
        >
          {removeGroup.isError && (
            <p className="jv-library__alert" role="alert">
              The group could not be deleted. Try again.
            </p>
          )}
          <div className="jv-dialog__actions">
            <DialogClose render={<Button>Cancel</Button>} />
            <Button
              variant="danger"
              disabled={removeGroup.isPending}
              onClick={() => removeGroup.mutate(deleteGroupTarget.id)}
            >
              {removeGroup.isPending ? "Deleting…" : "Delete group"}
            </Button>
          </div>
        </Dialog>
      )}
    </main>
  );
}

function comparePositionThenName(a: ActivityResponse, b: ActivityResponse) {
  const position = (a.position ?? 0) - (b.position ?? 0);
  return position || a.name.localeCompare(b.name);
}

function ActivitiesSkeleton() {
  return (
    <div className="jv-lib-dir" role="status" aria-label="Loading activities">
      {["a", "b"].map((section) => (
        <section className="jv-lib-section" key={section}>
          <div className="jv-lib-section__head">
            <span className="jv-lib-section__toggle">
              <Skeleton height="1rem" width="7rem" />
              <span className="jv-lib-section__rule" />
            </span>
            <Skeleton height="0.85rem" width="4.5rem" />
            <span className="jv-lib-section__slot" />
          </div>
          <ul className="jv-lib-section__grid">
            {["x", "y", "z"].map((cell) => (
              <li className="jv-lib-row" key={cell}>
                <Skeleton height="1rem" width="1rem" />
                <span className="jv-lib-row__text">
                  <Skeleton height="0.9rem" width="55%" />
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function ActivityFormDialog({
  state,
  groups,
  submitting,
  failed,
  onClose,
  onSubmit,
}: {
  state: ActivityFormState;
  groups: ActivityGroupWithActivitiesResponse[];
  submitting: boolean;
  failed: boolean;
  onClose: () => void;
  onSubmit: (body: ActivityCreate | ActivityUpdate) => Promise<void>;
}) {
  const activity = state.mode === "edit" ? state.activity : undefined;
  const nameId = useId();
  const groupSelectId = useId();
  const colorName = useId();
  const iconName = useId();
  const initialName = activity?.name ?? "";
  const initialGroup =
    state.mode === "create"
      ? (state.groupId ?? "")
      : (state.activity.group_id ?? "");
  const initialColor = activity?.color ?? "";
  const initialIcon = activity?.icon ?? "";
  const [name, setName] = useState(initialName);
  const [selectedGroup, setSelectedGroup] = useState(initialGroup);
  const [color, setColor] = useState(initialColor);
  const [icon, setIcon] = useState(initialIcon);
  const trimmed = name.trim();
  const dirty = activity
    ? trimmed !== initialName ||
      selectedGroup !== initialGroup ||
      color !== initialColor ||
      icon !== initialIcon
    : Boolean(trimmed);
  const tint = (hex: string): CSSProperties =>
    ({ "--entity-accent": hex }) as CSSProperties;

  return (
    <Dialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={activity ? `Edit ${activity.name}` : "Add activity"}
      description="Choose how this activity appears when you record a moment."
    >
      <form
        className="jv-library-form"
        onSubmit={async (event) => {
          event.preventDefault();
          if (!trimmed || submitting) return;
          try {
            await onSubmit({
              name: trimmed,
              group_id: selectedGroup || null,
              color: color || null,
              icon: icon || null,
            });
          } catch {
            // The mutation state renders the human failure message and the
            // controlled fields intentionally remain untouched.
          }
        }}
      >
        <label htmlFor={nameId}>
          <span>Activity name</span>
          <Input
            id={nameId}
            aria-label="Activity name"
            value={name}
            autoFocus
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label htmlFor={groupSelectId}>
          <span>Group</span>
          <select
            id={groupSelectId}
            className="jv-field"
            value={selectedGroup}
            onChange={(event) => setSelectedGroup(event.target.value)}
          >
            <option value="">Without a group</option>
            {groups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="jv-groups-form__group">
          <legend>Colour</legend>
          <div className="jv-groups-form__swatches">
            <label className="jv-groups-form__swatch jv-groups-form__swatch--none">
              <input
                type="radio"
                name={colorName}
                className="sr-only"
                checked={!color}
                onChange={() => setColor("")}
              />
              <span className="sr-only">No colour</span>
            </label>
            {ENTITY_COLOR_PRESETS.map((preset) => (
              <label
                key={preset.hex}
                className="jv-groups-form__swatch"
                style={tint(preset.hex)}
              >
                <input
                  type="radio"
                  name={colorName}
                  className="sr-only"
                  checked={color.toLowerCase() === preset.hex.toLowerCase()}
                  onChange={() => setColor(preset.hex)}
                />
                <span className="sr-only">{preset.label}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset className="jv-groups-form__group">
          <legend>Icon</legend>
          <div className="jv-groups-form__icons">
            <label className="jv-groups-form__icon jv-groups-form__icon--none">
              <input
                type="radio"
                name={iconName}
                className="sr-only"
                checked={!icon}
                onChange={() => setIcon("")}
              />
              None
            </label>
            {JOURNAL_ICONS.map(({ key, label, Icon }) => (
              <label
                key={key}
                className="jv-groups-form__icon"
                style={color ? tint(color) : undefined}
              >
                <input
                  type="radio"
                  name={iconName}
                  className="sr-only"
                  checked={icon === key}
                  onChange={() => setIcon(key)}
                />
                <span className="sr-only">{label}</span>
                <Icon size={17} aria-hidden="true" />
              </label>
            ))}
          </div>
        </fieldset>
        {failed && (
          <p className="jv-library__alert" role="alert">
            The activity could not be saved. Your changes are still here.
          </p>
        )}
        <div className="jv-dialog__actions">
          <DialogClose render={<Button>Cancel</Button>} />
          <Button
            type="submit"
            variant="primary"
            disabled={!trimmed || !dirty || submitting}
          >
            {submitting ? "Saving…" : activity ? "Save" : "Add activity"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
