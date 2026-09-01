import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  Menu,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { type CSSProperties, type ReactNode, useId, useState } from "react";
import { api } from "../../api/client/api";
import type {
  MoodCreate,
  MoodGroupCreate,
  MoodGroupUpdate,
  MoodGroupWithMoodsResponse,
  MoodResponse,
  MoodUpdate,
} from "../../api/generated/types.gen";
import { queryKeys } from "../../api/query/keys";
import { moodGroupsQuery, moodsQuery } from "../../api/query/options";
import { EntityGlyph } from "../../components/journiv/EntityGlyph";
import { LibraryRow } from "../../components/journiv/LibraryRow";
import { PageBar } from "../../components/journiv/PageBar";
import { StatusView } from "../../components/journiv/StatusView";
import { Button } from "../../components/ui/button";
import { Dialog, DialogClose } from "../../components/ui/dialog";
import { AppAdaptiveMenu } from "../../components/journiv/AppAdaptiveMenu";
import { AppConfirmDialog } from "../../components/journiv/AppConfirmDialog";
import { IconButton } from "../../components/ui/icon-button";
import { Input } from "../../components/ui/input";
import { SearchInput } from "../../components/ui/search-input";
import { Skeleton } from "../../components/ui/skeleton";
import {
  argbFromHex,
  colorFromArgb,
  ENTITY_COLOR_PRESETS,
} from "../../lib/color";
import { cx } from "../../lib/cx";
import { useShell } from "../shell/AppShell";
import { GroupsManagerDialog } from "./GroupsManagerDialog";
import { viewMomentsAction } from "./viewMomentsAction";
import "./library.css";

type MoodFormState = { mode: "create" } | { mode: "edit"; mood: MoodResponse };

function countLabel(count: number) {
  return `${count} ${count === 1 ? "mood" : "moods"}`;
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

function moodMeta(mood: MoodResponse) {
  const category =
    mood.category.charAt(0).toUpperCase() + mood.category.slice(1);
  return `${category} · ${mood.score} out of 5`;
}

function MoodListItem({
  mood,
  onEdit,
  onDelete,
}: {
  mood: MoodResponse;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <LibraryRow
      leading={<EntityGlyph colorValue={mood.color_value} size={16} />}
      title={mood.name}
      meta={moodMeta(mood)}
      actions={
        <AppAdaptiveMenu
          label={`${mood.name} actions`}
          align="end"
          actions={[
            viewMomentsAction({ mood: mood.id }),
            {
              kind: "command",
              id: "edit",
              label: "Edit mood",
              icon: Pencil,
              onSelect: onEdit,
            },
            {
              kind: "command",
              id: "delete",
              label: "Delete mood…",
              icon: Trash2,
              destructive: true,
              separatorBefore: true,
              onSelect: onDelete,
            },
          ]}
        />
      }
    />
  );
}

export function MoodsPage() {
  const shell = useShell();
  const qc = useQueryClient();
  const moodsResult = useQuery(moodsQuery());
  const groupsResult = useQuery(moodGroupsQuery());
  const moods = moodsResult.data ?? [];
  const groups = groupsResult.data ?? [];

  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [ungroupedOpen, setUngroupedOpen] = useState<boolean>();
  const [moodForm, setMoodForm] = useState<MoodFormState>();
  const [deleteMoodTarget, setDeleteMoodTarget] = useState<MoodResponse>();
  const [deleteGroupTarget, setDeleteGroupTarget] =
    useState<MoodGroupWithMoodsResponse>();
  const [groupsManager, setGroupsManager] = useState<{
    initialGroup?: MoodGroupWithMoodsResponse;
  }>();

  const refresh = async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: queryKeys.moods }),
      qc.invalidateQueries({ queryKey: queryKeys.moodGroups }),
    ]);
  };
  const createMood = useMutation({
    mutationFn: (body: MoodCreate) => api.createMood(body),
    onSuccess: async () => {
      setMoodForm(undefined);
      await refresh();
    },
  });
  const updateMood = useMutation({
    mutationFn: ({ id, body }: { id: string; body: MoodUpdate }) =>
      api.updateMood(id, body),
    onSuccess: async () => {
      setMoodForm(undefined);
      await refresh();
    },
  });
  const removeMood = useMutation({
    mutationFn: (id: string) => api.deleteMood(id),
    onSuccess: async () => {
      setDeleteMoodTarget(undefined);
      await refresh();
    },
  });
  const createGroup = useMutation({
    mutationFn: (body: MoodGroupCreate) => api.createMoodGroup(body),
    onSuccess: refresh,
  });
  const updateGroup = useMutation({
    mutationFn: ({ id, body }: { id: string; body: MoodGroupUpdate }) =>
      api.updateMoodGroup(id, body),
    onSuccess: refresh,
  });
  const removeGroup = useMutation({
    mutationFn: (id: string) => api.deleteMoodGroup(id),
    onSuccess: async () => {
      setDeleteGroupTarget(undefined);
      await refresh();
    },
  });

  const loading = moodsResult.isLoading || groupsResult.isLoading;
  const loadError = moodsResult.isError || groupsResult.isError;
  const normalizedSearch = search.trim().toLowerCase();
  const searching = normalizedSearch.length > 0;
  const matchesMood = (mood: MoodResponse) =>
    !searching ||
    mood.name.toLowerCase().includes(normalizedSearch) ||
    mood.category.toLowerCase().includes(normalizedSearch);
  const groupView = groups.map((group) => ({
    group,
    members: [...(group.moods ?? [])].sort(comparePositionThenName),
    visible: [...(group.moods ?? [])]
      .sort(comparePositionThenName)
      .filter(matchesMood),
    nameMatches:
      searching && group.name.toLowerCase().includes(normalizedSearch),
  }));
  const groupedMoodIds = new Set(
    groups.flatMap((group) => (group.moods ?? []).map((mood) => mood.id)),
  );
  const ungrouped = moods
    .filter((mood) => !groupedMoodIds.has(mood.id))
    .sort(comparePositionThenName)
    .filter(matchesMood);
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
    <main className="jv-library" aria-label="Moods">
      <PageBar
        className="jv-page-bar--compact-only"
        leading={
          <IconButton label="Open navigation" onClick={shell.openNavigation}>
            <Menu aria-hidden="true" size={19} />
          </IconButton>
        }
        title={<span className="jv-label jv-truncate">Moods</span>}
      />
      <header className="jv-library__header">
        <div className="jv-library__headings">
          <h1 className="jv-display jv-library__heading">Moods</h1>
          <p className="jv-library__intro jv-body">
            Shape the mood scale you use when recording your day.
          </p>
        </div>
        <div className="jv-library__actions">
          <Button onClick={() => setGroupsManager({})}>Manage groups</Button>
          <Button
            variant="primary"
            onClick={() => setMoodForm({ mode: "create" })}
          >
            <Plus aria-hidden="true" size={16} />
            Add mood
          </Button>
        </div>
      </header>

      <div className="jv-library__scroll">
        <div className="jv-library__body">
          <SearchInput
            className="jv-search-wrap"
            label="Search moods"
            placeholder="Search moods or groups…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onClear={() => setSearch("")}
          />
          {loading && <MoodsSkeleton />}
          {loadError && (
            <StatusView
              role="alert"
              tone="danger"
              icon={<TriangleAlert size={20} />}
              title="Moods could not be loaded"
              description="Check your connection and try again."
              action={
                <Button
                  onClick={() => {
                    moodsResult.refetch();
                    groupsResult.refetch();
                  }}
                >
                  Try again
                </Button>
              }
            />
          )}
          {!loading && !loadError && !moods.length && !groups.length && (
            <StatusView
              icon={<Sparkles size={20} />}
              title="No moods yet"
              description="Add a mood or create a group to begin shaping your mood scale."
              action={
                <Button
                  variant="primary"
                  onClick={() => setMoodForm({ mode: "create" })}
                >
                  <Plus aria-hidden="true" size={16} />
                  Add mood
                </Button>
              }
            />
          )}
          {!loading &&
            !loadError &&
            (moods.length > 0 || groups.length > 0) && (
              <div className="jv-lib-dir">
                {groupView.map(({ group, members, visible, nameMatches }) => {
                  if (searching && !nameMatches && !visible.length) return null;
                  return (
                    <GroupSection
                      key={group.id}
                      title={group.name}
                      colorValue={group.color_value}
                      icon={group.icon}
                      count={members.length}
                      open={searching || !collapsed.has(group.id)}
                      onToggle={() => toggleGroup(group.id)}
                      menu={
                        <AppAdaptiveMenu
                          label={`${group.name} group actions`}
                          align="end"
                          actions={[
                            {
                              kind: "command",
                              id: "edit-group",
                              label: "Edit group",
                              icon: Pencil,
                              onSelect: () =>
                                setGroupsManager({ initialGroup: group }),
                            },
                            {
                              kind: "command",
                              id: "delete-group",
                              label: "Delete group…",
                              icon: Trash2,
                              destructive: true,
                              separatorBefore: true,
                              onSelect: () => setDeleteGroupTarget(group),
                            },
                          ]}
                        />
                      }
                    >
                      {visible.length ? (
                        <ul className="jv-lib-section__grid">
                          {visible.map((mood) => (
                            <MoodListItem
                              key={mood.id}
                              mood={mood}
                              onEdit={() => setMoodForm({ mode: "edit", mood })}
                              onDelete={() => setDeleteMoodTarget(mood)}
                            />
                          ))}
                        </ul>
                      ) : (
                        <div className="jv-lib-section__empty">
                          <span>
                            {searching
                              ? "No matching moods in this group."
                              : "No moods in this group yet."}
                          </span>
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
                      {ungrouped.map((mood) => (
                        <MoodListItem
                          key={mood.id}
                          mood={mood}
                          onEdit={() => setMoodForm({ mode: "edit", mood })}
                          onDelete={() => setDeleteMoodTarget(mood)}
                        />
                      ))}
                    </ul>
                  </GroupSection>
                )}
                {nothingMatches && (
                  <div className="jv-lib-dir__nomatch">
                    <StatusView
                      title="No moods found"
                      description={`No moods or groups match “${search.trim()}”.`}
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

      {moodForm && (
        <MoodFormDialog
          state={moodForm}
          submitting={createMood.isPending || updateMood.isPending}
          failed={createMood.isError || updateMood.isError}
          onClose={() => setMoodForm(undefined)}
          onSubmit={async (body) => {
            if (moodForm.mode === "create")
              await createMood.mutateAsync(body as MoodCreate);
            else await updateMood.mutateAsync({ id: moodForm.mood.id, body });
          }}
        />
      )}
      {groupsManager && (
        <GroupsManagerDialog
          groups={groups}
          initialGroup={groupsManager.initialGroup}
          itemNoun={{ singular: "mood", plural: "moods" }}
          itemCount={(group) =>
            (group as MoodGroupWithMoodsResponse).moods?.length ?? 0
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
      {deleteMoodTarget && (
        <AppConfirmDialog
          open
          onOpenChange={(open) => !open && setDeleteMoodTarget(undefined)}
          title={`Delete ${deleteMoodTarget.name}?`}
          description="The mood is hidden from active lists. Existing moment references remain."
          confirmLabel={removeMood.isPending ? "Deleting…" : "Delete mood"}
          destructive
          pending={removeMood.isPending}
          onConfirm={() => removeMood.mutate(deleteMoodTarget.id)}
        >
          {removeMood.isError && (
            <p className="jv-library__alert" role="alert">
              The mood could not be deleted. Try again.
            </p>
          )}
        </AppConfirmDialog>
      )}
      {deleteGroupTarget && (
        <AppConfirmDialog
          open
          onOpenChange={(open) => !open && setDeleteGroupTarget(undefined)}
          title={`Delete ${deleteGroupTarget.name}?`}
          description="Moods remain in your Library and are removed only from this group."
          confirmLabel={removeGroup.isPending ? "Deleting…" : "Delete group"}
          destructive
          pending={removeGroup.isPending}
          onConfirm={() => removeGroup.mutate(deleteGroupTarget.id)}
        >
          {removeGroup.isError && (
            <p className="jv-library__alert" role="alert">
              The group could not be deleted. Try again.
            </p>
          )}
        </AppConfirmDialog>
      )}
    </main>
  );
}

function comparePositionThenName(a: MoodResponse, b: MoodResponse) {
  const position = (a.position ?? 0) - (b.position ?? 0);
  return position || a.name.localeCompare(b.name);
}

function MoodsSkeleton() {
  return (
    <div className="jv-lib-dir" role="status" aria-label="Loading moods">
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

function MoodFormDialog({
  state,
  submitting,
  failed,
  onClose,
  onSubmit,
}: {
  state: MoodFormState;
  submitting: boolean;
  failed: boolean;
  onClose: () => void;
  onSubmit: (body: MoodCreate | MoodUpdate) => Promise<void>;
}) {
  const mood = state.mode === "edit" ? state.mood : undefined;
  const nameId = useId();
  const scoreId = useId();
  const colorName = useId();
  const initialName = mood?.name ?? "";
  const initialScore = mood?.score ?? 3;
  const initialColor = colorFromArgb(mood?.color_value) ?? "";
  const [name, setName] = useState(initialName);
  const [score, setScore] = useState(initialScore);
  const [color, setColor] = useState(initialColor);
  const trimmed = name.trim();
  const dirty = mood
    ? trimmed !== initialName ||
      score !== initialScore ||
      color !== initialColor
    : Boolean(trimmed);
  const tint = (hex: string): CSSProperties =>
    ({ "--entity-accent": hex }) as CSSProperties;

  return (
    <Dialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={mood ? `Edit ${mood.name}` : "Add mood"}
      description="Choose the name, feeling score and colour used in your journal."
    >
      <form
        className="jv-library-form"
        onSubmit={async (event) => {
          event.preventDefault();
          if (!trimmed || submitting) return;
          try {
            await onSubmit({
              name: trimmed,
              score,
              color_value: color ? argbFromHex(color) : null,
              ...(!mood ? { icon: null } : {}),
            });
          } catch {
            // Mutation state owns the failure message; controlled values stay.
          }
        }}
      >
        <label htmlFor={nameId}>
          <span>Mood name</span>
          <Input
            id={nameId}
            aria-label="Mood name"
            value={name}
            maxLength={100}
            autoFocus
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label htmlFor={scoreId}>
          <span>Feeling score</span>
          <select
            id={scoreId}
            className="jv-field"
            aria-label="Feeling score"
            value={score}
            onChange={(event) => setScore(Number(event.target.value))}
          >
            <option value={5}>5 — Very positive</option>
            <option value={4}>4 — Positive</option>
            <option value={3}>3 — Neutral</option>
            <option value={2}>2 — Negative</option>
            <option value={1}>1 — Very negative</option>
          </select>
          <small className="jv-library-form__hint">
            The score determines whether Journiv categorises this mood as
            positive, neutral or negative.
          </small>
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
        {failed && (
          <p className="jv-library__alert" role="alert">
            The mood could not be saved. Your changes are still here.
          </p>
        )}
        <div className="jv-dialog__actions">
          <DialogClose render={<Button>Cancel</Button>} />
          <Button
            type="submit"
            variant="primary"
            disabled={!trimmed || !dirty || submitting}
          >
            {submitting ? "Saving…" : mood ? "Save" : "Add mood"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
