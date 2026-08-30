import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  History,
  Menu,
  MoreHorizontal,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { type CSSProperties, type ReactNode, useId, useState } from "react";
import { api } from "../../api/client/api";
import type {
  ActivityResponse,
  GoalCategoryCreate,
  GoalCategoryResponse,
  GoalCategoryUpdate,
  GoalCreate,
  GoalFrequency,
  GoalType,
  GoalUpdate,
  GoalWithProgressResponse,
} from "../../api/generated/types.gen";
import { queryKeys } from "../../api/query/keys";
import {
  activitiesQuery,
  goalCategoriesQuery,
  goalsQuery,
} from "../../api/query/options";
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
import {
  argbFromHex,
  colorFromArgb,
  ENTITY_COLOR_PRESETS,
} from "../../lib/color";
import { cx } from "../../lib/cx";
import { JOURNAL_ICONS } from "../../lib/journalIcons";
import { useShell } from "../shell/AppShell";
import { GoalHistoryDialog } from "./GoalHistoryDialog";
import { GroupsManagerDialog } from "./GroupsManagerDialog";
import { ViewMomentsMenuItem } from "./ViewMomentsMenuItem";
import "./library.css";

type GoalFormState =
  | { mode: "create"; categoryId: string | null }
  | { mode: "edit"; goal: GoalWithProgressResponse };

function countLabel(count: number) {
  return `${count} ${count === 1 ? "goal" : "goals"}`;
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

function goalMeta(goal: GoalWithProgressResponse, activity?: ActivityResponse) {
  const cadence = frequencyLabel(goal.frequency_type ?? "daily");
  const direction = goal.goal_type === "avoid" ? "Avoid" : "Achieve";
  const progress = `${goal.current_period_completed ?? 0}/${goal.target_count ?? 1} this period`;
  return [
    cadence,
    direction,
    progress,
    activity?.name,
    goal.is_paused && "Paused",
  ]
    .filter(Boolean)
    .join(" · ");
}

function GoalListItem({
  goal,
  activity,
  onHistory,
  onEdit,
  onDelete,
}: {
  goal: GoalWithProgressResponse;
  activity?: ActivityResponse;
  onHistory: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <LibraryRow
      leading={
        <EntityGlyph colorValue={goal.color_value} icon={goal.icon} size={16} />
      }
      title={goal.title}
      meta={goalMeta(goal, activity)}
      actions={
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <IconButton label={`${goal.title} actions`}>
                <MoreHorizontal aria-hidden="true" size={17} />
              </IconButton>
            }
          />
          <DropdownMenuContent align="end">
            <ViewMomentsMenuItem scope={{ goal: goal.id }} />
            <DropdownMenuItem onClick={onHistory}>
              <History aria-hidden="true" size={15} />
              View history
            </DropdownMenuItem>
            <DropdownMenuItem onClick={onEdit}>
              <Pencil aria-hidden="true" size={15} />
              Edit goal
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onClick={onDelete}>
              <Trash2 aria-hidden="true" size={15} />
              Delete goal…
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      }
    />
  );
}

export function GoalsPage() {
  const shell = useShell();
  const qc = useQueryClient();
  const goalsResult = useQuery(goalsQuery());
  const categoriesResult = useQuery(goalCategoriesQuery());
  const activitiesResult = useQuery(activitiesQuery());
  const goals = goalsResult.data ?? [];
  const categories = categoriesResult.data ?? [];
  const activities = activitiesResult.data ?? [];

  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [ungroupedOpen, setUngroupedOpen] = useState<boolean>();
  const [goalForm, setGoalForm] = useState<GoalFormState>();
  const [historyTarget, setHistoryTarget] =
    useState<GoalWithProgressResponse>();
  const [deleteGoalTarget, setDeleteGoalTarget] =
    useState<GoalWithProgressResponse>();
  const [deleteCategoryTarget, setDeleteCategoryTarget] =
    useState<GoalCategoryResponse>();
  const [groupsManager, setGroupsManager] = useState<{
    initialGroup?: GoalCategoryResponse;
  }>();

  const refresh = async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: queryKeys.goals }),
      qc.invalidateQueries({ queryKey: queryKeys.goalCategories }),
    ]);
  };
  const createGoal = useMutation({
    mutationFn: (body: GoalCreate) => api.createGoal(body),
    onSuccess: async () => {
      setGoalForm(undefined);
      await refresh();
    },
  });
  const updateGoal = useMutation({
    mutationFn: ({ id, body }: { id: string; body: GoalUpdate }) =>
      api.updateGoal(id, body),
    onSuccess: async () => {
      setGoalForm(undefined);
      await refresh();
    },
  });
  const removeGoal = useMutation({
    mutationFn: (id: string) => api.deleteGoal(id),
    onSuccess: async () => {
      setDeleteGoalTarget(undefined);
      await refresh();
    },
  });
  const createCategory = useMutation({
    mutationFn: (body: GoalCategoryCreate) => api.createGoalCategory(body),
    onSuccess: refresh,
  });
  const updateCategory = useMutation({
    mutationFn: ({ id, body }: { id: string; body: GoalCategoryUpdate }) =>
      api.updateGoalCategory(id, body),
    onSuccess: refresh,
  });
  const removeCategory = useMutation({
    mutationFn: (id: string) => api.deleteGoalCategory(id),
    onSuccess: async () => {
      setDeleteCategoryTarget(undefined);
      await refresh();
    },
  });

  const loading =
    goalsResult.isLoading ||
    categoriesResult.isLoading ||
    activitiesResult.isLoading;
  const loadError =
    goalsResult.isError || categoriesResult.isError || activitiesResult.isError;
  const normalizedSearch = search.trim().toLowerCase();
  const searching = normalizedSearch.length > 0;
  const matchesGoal = (goal: GoalWithProgressResponse) =>
    !searching || goal.title.toLowerCase().includes(normalizedSearch);
  const categoryView = categories.map((category) => {
    const members = goals
      .filter((goal) => goal.category_id === category.id)
      .sort(comparePositionThenTitle);
    return {
      category,
      members,
      visible: members.filter(matchesGoal),
      nameMatches:
        searching && category.name.toLowerCase().includes(normalizedSearch),
    };
  });
  const ungrouped = goals
    .filter((goal) => !goal.category_id)
    .sort(comparePositionThenTitle)
    .filter(matchesGoal);
  const nothingMatches =
    searching &&
    !ungrouped.length &&
    categoryView.every(
      ({ visible, nameMatches }) => !visible.length && !nameMatches,
    );
  const activityById = new Map(
    activities.map((activity) => [activity.id, activity]),
  );

  const toggleCategory = (id: string) =>
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <main className="jv-library" aria-label="Goals">
      <PageBar
        className="jv-page-bar--compact-only"
        leading={
          <IconButton label="Open navigation" onClick={shell.openNavigation}>
            <Menu aria-hidden="true" size={19} />
          </IconButton>
        }
        title={<span className="jv-label jv-truncate">Goals</span>}
      />
      <header className="jv-library__header">
        <div className="jv-library__headings">
          <h1 className="jv-display jv-library__heading">Goals</h1>
          <p className="jv-library__intro jv-body">
            Track the habits and targets that matter to you.
          </p>
        </div>
        <div className="jv-library__actions">
          <Button onClick={() => setGroupsManager({})}>Manage groups</Button>
          <Button
            variant="primary"
            onClick={() => setGoalForm({ mode: "create", categoryId: null })}
          >
            <Plus aria-hidden="true" size={16} />
            Add goal
          </Button>
        </div>
      </header>

      <div className="jv-library__scroll">
        <div className="jv-library__body">
          <SearchInput
            className="jv-search-wrap"
            label="Search goals"
            placeholder="Search goals or groups…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onClear={() => setSearch("")}
          />

          {loading && <GoalsSkeleton />}
          {loadError && (
            <StatusView
              role="alert"
              tone="danger"
              icon={<TriangleAlert size={20} />}
              title="Goals could not be loaded"
              description="Check your connection and try again."
              action={
                <Button
                  onClick={() => {
                    goalsResult.refetch();
                    categoriesResult.refetch();
                    activitiesResult.refetch();
                  }}
                >
                  Try again
                </Button>
              }
            />
          )}
          {!loading && !loadError && !goals.length && !categories.length && (
            <StatusView
              icon={<Sparkles size={20} />}
              title="No goals yet"
              description="Add a goal or create a group to begin tracking what matters."
              action={
                <Button
                  variant="primary"
                  onClick={() =>
                    setGoalForm({ mode: "create", categoryId: null })
                  }
                >
                  <Plus aria-hidden="true" size={16} />
                  Add goal
                </Button>
              }
            />
          )}
          {!loading &&
            !loadError &&
            (goals.length > 0 || categories.length > 0) && (
              <div className="jv-lib-dir">
                {categoryView.map(
                  ({ category, members, visible, nameMatches }) => {
                    if (searching && !nameMatches && !visible.length)
                      return null;
                    return (
                      <GroupSection
                        key={category.id}
                        title={category.name}
                        colorValue={category.color_value}
                        icon={category.icon}
                        count={members.length}
                        open={searching || !collapsed.has(category.id)}
                        onToggle={() => toggleCategory(category.id)}
                        menu={
                          <DropdownMenu>
                            <DropdownMenuTrigger
                              render={
                                <IconButton
                                  label={`${category.name} group actions`}
                                >
                                  <MoreHorizontal
                                    aria-hidden="true"
                                    size={17}
                                  />
                                </IconButton>
                              }
                            />
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem
                                onClick={() =>
                                  setGoalForm({
                                    mode: "create",
                                    categoryId: category.id,
                                  })
                                }
                              >
                                <Plus aria-hidden="true" size={15} />
                                Add goal to group
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                onClick={() =>
                                  setGroupsManager({
                                    initialGroup: category,
                                  })
                                }
                              >
                                <Pencil aria-hidden="true" size={15} />
                                Edit group
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                variant="destructive"
                                onClick={() =>
                                  setDeleteCategoryTarget(category)
                                }
                              >
                                <Trash2 aria-hidden="true" size={15} />
                                Delete group…
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        }
                      >
                        {visible.length ? (
                          <ul className="jv-lib-section__grid jv-lib-section__grid--goals">
                            {visible.map((goal) => (
                              <GoalListItem
                                key={goal.id}
                                goal={goal}
                                activity={
                                  goal.activity_id
                                    ? activityById.get(goal.activity_id)
                                    : undefined
                                }
                                onHistory={() => setHistoryTarget(goal)}
                                onEdit={() =>
                                  setGoalForm({ mode: "edit", goal })
                                }
                                onDelete={() => setDeleteGoalTarget(goal)}
                              />
                            ))}
                          </ul>
                        ) : (
                          <div className="jv-lib-section__empty">
                            {searching ? (
                              <span>No matching goals in this group.</span>
                            ) : (
                              <>
                                <span>No goals in this group yet.</span>
                                <Button
                                  variant="ghost"
                                  onClick={() =>
                                    setGoalForm({
                                      mode: "create",
                                      categoryId: category.id,
                                    })
                                  }
                                >
                                  <Plus aria-hidden="true" size={15} />
                                  Add goal
                                </Button>
                              </>
                            )}
                          </div>
                        )}
                      </GroupSection>
                    );
                  },
                )}

                {ungrouped.length > 0 && (
                  <GroupSection
                    quiet
                    title="Without a group"
                    count={ungrouped.length}
                    open={
                      searching || (ungroupedOpen ?? categories.length === 0)
                    }
                    onToggle={() =>
                      setUngroupedOpen(
                        (open) => !(open ?? categories.length === 0),
                      )
                    }
                  >
                    <ul className="jv-lib-section__grid jv-lib-section__grid--goals">
                      {ungrouped.map((goal) => (
                        <GoalListItem
                          key={goal.id}
                          goal={goal}
                          activity={
                            goal.activity_id
                              ? activityById.get(goal.activity_id)
                              : undefined
                          }
                          onHistory={() => setHistoryTarget(goal)}
                          onEdit={() => setGoalForm({ mode: "edit", goal })}
                          onDelete={() => setDeleteGoalTarget(goal)}
                        />
                      ))}
                    </ul>
                  </GroupSection>
                )}

                {nothingMatches && (
                  <div className="jv-lib-dir__nomatch">
                    <StatusView
                      title="No goals found"
                      description={`No goals or groups match “${search.trim()}”.`}
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

      {goalForm && (
        <GoalFormDialog
          state={goalForm}
          categories={categories}
          activities={activities}
          submitting={createGoal.isPending || updateGoal.isPending}
          failed={createGoal.isError || updateGoal.isError}
          onClose={() => setGoalForm(undefined)}
          onSubmit={async (body) => {
            if (goalForm.mode === "create")
              await createGoal.mutateAsync({
                ...(body as GoalCreate),
                position:
                  goals.reduce(
                    (highest, goal) => Math.max(highest, goal.position ?? 0),
                    0,
                  ) + 10,
              });
            else
              await updateGoal.mutateAsync({
                id: goalForm.goal.id,
                body,
              });
          }}
        />
      )}
      {historyTarget && (
        <GoalHistoryDialog
          goal={historyTarget}
          onClose={() => setHistoryTarget(undefined)}
        />
      )}
      {groupsManager && (
        <GroupsManagerDialog
          groups={categories}
          initialGroup={groupsManager.initialGroup}
          itemNoun={{ singular: "goal", plural: "goals" }}
          itemCount={(group) =>
            goals.filter((goal) => goal.category_id === group.id).length
          }
          busy={
            createCategory.isPending ||
            updateCategory.isPending ||
            removeCategory.isPending
          }
          saveFailed={createCategory.isError || updateCategory.isError}
          deleteFailed={removeCategory.isError}
          onClose={() => setGroupsManager(undefined)}
          onCreate={async (body) => {
            await createCategory.mutateAsync({
              ...body,
              position: categories.length,
            });
          }}
          onUpdate={async (id, body) => {
            await updateCategory.mutateAsync({ id, body });
          }}
          onDelete={async (id) => {
            await removeCategory.mutateAsync(id);
          }}
        />
      )}
      {deleteGoalTarget && (
        <Dialog
          open
          onOpenChange={(open) => !open && setDeleteGoalTarget(undefined)}
          title={`Delete ${deleteGoalTarget.title}?`}
          description="This permanently removes the goal and its completion history. This cannot be undone."
        >
          {removeGoal.isError && (
            <p className="jv-library__alert" role="alert">
              The goal could not be deleted. Try again.
            </p>
          )}
          <div className="jv-dialog__actions">
            <DialogClose render={<Button>Cancel</Button>} />
            <Button
              variant="danger"
              disabled={removeGoal.isPending}
              onClick={() => removeGoal.mutate(deleteGoalTarget.id)}
            >
              {removeGoal.isPending ? "Deleting…" : "Delete goal"}
            </Button>
          </div>
        </Dialog>
      )}
      {deleteCategoryTarget && (
        <Dialog
          open
          onOpenChange={(open) => !open && setDeleteCategoryTarget(undefined)}
          title={`Delete ${deleteCategoryTarget.name}?`}
          description="Goals remain in your Library and move to Without a group."
        >
          {removeCategory.isError && (
            <p className="jv-library__alert" role="alert">
              The group could not be deleted. Try again.
            </p>
          )}
          <div className="jv-dialog__actions">
            <DialogClose render={<Button>Cancel</Button>} />
            <Button
              variant="danger"
              disabled={removeCategory.isPending}
              onClick={() => removeCategory.mutate(deleteCategoryTarget.id)}
            >
              {removeCategory.isPending ? "Deleting…" : "Delete group"}
            </Button>
          </div>
        </Dialog>
      )}
    </main>
  );
}

function comparePositionThenTitle(
  a: GoalWithProgressResponse,
  b: GoalWithProgressResponse,
) {
  const position = (a.position ?? 0) - (b.position ?? 0);
  return position || a.title.localeCompare(b.title);
}

function frequencyLabel(value: GoalFrequency) {
  return `${value[0].toUpperCase()}${value.slice(1)}`;
}

function GoalsSkeleton() {
  return (
    <div className="jv-lib-dir" role="status" aria-label="Loading goals">
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
                  <Skeleton height="0.75rem" width="80%" />
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function GoalFormDialog({
  state,
  categories,
  activities,
  submitting,
  failed,
  onClose,
  onSubmit,
}: {
  state: GoalFormState;
  categories: GoalCategoryResponse[];
  activities: ActivityResponse[];
  submitting: boolean;
  failed: boolean;
  onClose: () => void;
  onSubmit: (body: GoalCreate | GoalUpdate) => Promise<void>;
}) {
  const goal = state.mode === "edit" ? state.goal : undefined;
  const titleId = useId();
  const categorySelectId = useId();
  const activitySelectId = useId();
  const typeId = useId();
  const frequencyId = useId();
  const targetId = useId();
  const reminderId = useId();
  const pausedId = useId();
  const colorName = useId();
  const iconName = useId();
  const initial = {
    title: goal?.title ?? "",
    category:
      state.mode === "create"
        ? (state.categoryId ?? "")
        : (state.goal.category_id ?? ""),
    activity: goal?.activity_id ?? "",
    type: goal?.goal_type ?? ("achieve" as GoalType),
    frequency: goal?.frequency_type ?? ("daily" as GoalFrequency),
    target: String(goal?.target_count ?? 1),
    reminder: goal?.reminder_time ?? "",
    paused: goal?.is_paused ?? false,
    color: colorFromArgb(goal?.color_value) ?? "",
    icon: goal?.icon ?? "",
  };
  const [title, setTitle] = useState(initial.title);
  const [selectedCategory, setSelectedCategory] = useState(initial.category);
  const [selectedActivity, setSelectedActivity] = useState(initial.activity);
  const [goalType, setGoalType] = useState<GoalType>(initial.type);
  const [frequency, setFrequency] = useState<GoalFrequency>(initial.frequency);
  const [target, setTarget] = useState(initial.target);
  const [reminder, setReminder] = useState(initial.reminder);
  const [paused, setPaused] = useState(initial.paused);
  const [color, setColor] = useState(initial.color);
  const [icon, setIcon] = useState(initial.icon);
  const trimmed = title.trim();
  const targetCount = Number(target);
  const validTarget = Number.isInteger(targetCount) && targetCount >= 1;
  const dirty = goal
    ? trimmed !== initial.title ||
      selectedCategory !== initial.category ||
      selectedActivity !== initial.activity ||
      goalType !== initial.type ||
      frequency !== initial.frequency ||
      target !== initial.target ||
      reminder !== initial.reminder ||
      paused !== initial.paused ||
      color !== initial.color ||
      icon !== initial.icon
    : Boolean(trimmed);
  const tint = (hex: string): CSSProperties =>
    ({ "--entity-accent": hex }) as CSSProperties;

  return (
    <Dialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={goal ? `Edit ${goal.title}` : "Add goal"}
      description="Define what to track and how this goal appears in your Library."
      className="sm:max-w-2xl"
    >
      <form
        className="jv-library-form"
        onSubmit={async (event) => {
          event.preventDefault();
          if (!trimmed || !validTarget || submitting) return;
          try {
            await onSubmit({
              title: trimmed,
              category_id: selectedCategory || null,
              activity_id: selectedActivity || null,
              goal_type: goalType,
              frequency_type: frequency,
              target_count: targetCount,
              reminder_time: reminder || null,
              is_paused: paused,
              color_value: color ? argbFromHex(color) : null,
              icon: icon || null,
            });
          } catch {
            // Mutation state owns the human failure message and all controlled
            // values intentionally remain in place for another attempt.
          }
        }}
      >
        <label htmlFor={titleId}>
          <span>Goal title</span>
          <Input
            id={titleId}
            aria-label="Goal title"
            value={title}
            maxLength={200}
            autoFocus
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <div className="jv-library-form__columns">
          <label htmlFor={categorySelectId}>
            <span>Group</span>
            <select
              id={categorySelectId}
              className="jv-field"
              value={selectedCategory}
              onChange={(event) => setSelectedCategory(event.target.value)}
            >
              <option value="">Without a group</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor={activitySelectId}>
            <span>Linked activity</span>
            <select
              id={activitySelectId}
              className="jv-field"
              value={selectedActivity}
              onChange={(event) => setSelectedActivity(event.target.value)}
            >
              <option value="">Manual progress</option>
              {activities.map((activity) => (
                <option key={activity.id} value={activity.id}>
                  {activity.name}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor={typeId}>
            <span>Direction</span>
            <select
              id={typeId}
              className="jv-field"
              value={goalType}
              onChange={(event) => setGoalType(event.target.value as GoalType)}
            >
              <option value="achieve">Achieve</option>
              <option value="avoid">Avoid</option>
            </select>
          </label>
          <label htmlFor={frequencyId}>
            <span>Frequency</span>
            <select
              id={frequencyId}
              className="jv-field"
              value={frequency}
              onChange={(event) =>
                setFrequency(event.target.value as GoalFrequency)
              }
            >
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </label>
          <label htmlFor={targetId}>
            <span>Target count</span>
            <Input
              id={targetId}
              aria-label="Target count"
              type="number"
              min={1}
              step={1}
              value={target}
              aria-invalid={!validTarget}
              onChange={(event) => setTarget(event.target.value)}
            />
            {!validTarget && (
              <span className="jv-library-form__error" role="alert">
                Enter a whole number of at least 1.
              </span>
            )}
          </label>
          <label htmlFor={reminderId}>
            <span>Reminder time</span>
            <Input
              id={reminderId}
              aria-label="Reminder time"
              type="time"
              value={reminder}
              onChange={(event) => setReminder(event.target.value)}
            />
          </label>
        </div>
        <label className="jv-library-form__check" htmlFor={pausedId}>
          <input
            id={pausedId}
            type="checkbox"
            checked={paused}
            onChange={(event) => setPaused(event.target.checked)}
          />
          <span>
            <strong>Pause this goal</strong>
            <small>Keep it in your Library without tracking progress.</small>
          </span>
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
            The goal could not be saved. Your changes are still here.
          </p>
        )}
        <div className="jv-dialog__actions">
          <DialogClose render={<Button>Cancel</Button>} />
          <Button
            type="submit"
            variant="primary"
            disabled={!trimmed || !validTarget || !dirty || submitting}
          >
            {submitting ? "Saving…" : goal ? "Save" : "Add goal"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
