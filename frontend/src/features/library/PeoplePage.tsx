import { AppAdaptiveMenu } from "../../components/journiv/AppAdaptiveMenu";
import { AppConfirmDialog } from "../../components/journiv/AppConfirmDialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  ChevronDown,
  ChevronRight,
  ImagePlus,
  Menu,
  Pencil,
  Plus,
  Trash2,
  TriangleAlert,
  Users,
  UserPlus,
} from "lucide-react";
import {
  type CSSProperties,
  type ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type {
  PersonCreate,
  PersonGroupCreate,
  PersonGroupUpdate,
  PersonGroupWithPeopleResponse,
  PersonResponse,
  PersonUpdate,
} from "../../api/generated/types.gen";
import { api } from "../../api/client/api";
import { queryKeys } from "../../api/query/keys";
import { peopleQuery, personGroupsQuery } from "../../api/query/options";
import { EntityGlyph } from "../../components/journiv/EntityGlyph";
import { LibraryRow } from "../../components/journiv/LibraryRow";
import { PageBar } from "../../components/journiv/PageBar";
import { Button } from "../../components/ui/button";
import { Dialog, DialogClose } from "../../components/ui/dialog";
import { IconButton } from "../../components/ui/icon-button";
import { Input } from "../../components/ui/input";
import { SearchInput } from "../../components/ui/search-input";
import { Skeleton } from "../../components/ui/skeleton";
import { StatusView } from "../../components/journiv/StatusView";
import { colorFromArgb } from "../../lib/color";
import { cx } from "../../lib/cx";
import { useShell } from "../shell/AppShell";
import { GroupsManagerDialog } from "./GroupsManagerDialog";
import { viewMomentsAction } from "./viewMomentsAction";
import "./library.css";

type PersonFormState =
  | { mode: "create"; groupIds: string[] }
  | { mode: "edit"; person: PersonResponse };

/** What the person form wants done with the profile photo on save. */
type PhotoChange =
  | { kind: "keep" }
  | { kind: "set"; file: File }
  | { kind: "clear" };

type PersonActions = {
  onEdit: () => void;
  onManageGroups: () => void;
  onMerge: () => void;
  onArchive: () => void;
};

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return (
    parts.length > 1
      ? `${parts[0][0]}${parts.at(-1)?.[0]}`
      : (parts[0]?.[0] ?? "?")
  ).toUpperCase();
}

function countLabel(count: number) {
  return `${count} ${count === 1 ? "person" : "people"}`;
}

function personMeta(person: PersonResponse): string | null {
  const moments =
    typeof person.memory_count === "number"
      ? `${person.memory_count} ${person.memory_count === 1 ? "moment" : "moments"}`
      : null;
  return [person.nickname, moments].filter(Boolean).join(" · ") || null;
}

function PersonAvatar({ person }: { person: PersonResponse }) {
  return person.profile_image_url ? (
    <img
      className="jv-library-person__avatar"
      src={person.profile_image_url}
      alt=""
      loading="lazy"
    />
  ) : (
    <span
      className="jv-library-person__avatar jv-library-person__initials"
      aria-hidden="true"
    >
      {initials(person.name)}
    </span>
  );
}

function PersonListItem({
  person,
  actions,
}: {
  person: PersonResponse;
  actions: PersonActions;
}) {
  return (
    <LibraryRow
      leading={<PersonAvatar person={person} />}
      title={person.name}
      meta={personMeta(person)}
      actions={
        <AppAdaptiveMenu
          label={`${person.name} actions`}
          align="end"
          actions={[
            viewMomentsAction({ person: person.id }),
            {
              kind: "command",
              id: "edit",
              label: "Edit person",
              icon: Pencil,
              onSelect: actions.onEdit,
            },
            {
              kind: "command",
              id: "groups",
              label: "Manage groups",
              icon: Users,
              onSelect: actions.onManageGroups,
            },
            // No icon, as before — this action never carried one.
            {
              kind: "command",
              id: "merge",
              label: "Merge duplicate…",
              onSelect: actions.onMerge,
            },
            // Destructive, but archiving is not deleting: it keeps its own
            // Archive glyph (DESIGN.md §17).
            {
              kind: "command",
              id: "archive",
              label: "Archive",
              icon: Archive,
              destructive: true,
              separatorBefore: true,
              onSelect: actions.onArchive,
            },
          ]}
        />
      }
    />
  );
}

/** A directory section: a colour dot, a sentence-case name, a hairline rule, the
 *  server count, then an airy grid of people. Whitespace and one rule carry the
 *  grouping — no boxes, no rail (DESIGN.md §5, §24). */
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

export function PeoplePage() {
  const shell = useShell();
  const qc = useQueryClient();
  const peopleQueryResult = useQuery(peopleQuery());
  const groupsQueryResult = useQuery(personGroupsQuery());
  const people = peopleQueryResult.data ?? [];
  const groups = groupsQueryResult.data ?? [];

  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  // Undefined = follow the default: open when there are no real groups to
  // choose between, collapsed as a fallback bucket when there are.
  const [ungroupedOpen, setUngroupedOpen] = useState<boolean>();
  const [personForm, setPersonForm] = useState<PersonFormState>();
  const [managePerson, setManagePerson] = useState<PersonResponse>();
  const [mergePerson, setMergePerson] = useState<PersonResponse>();
  const [archivePerson, setArchivePerson] = useState<PersonResponse>();
  const [manageGroup, setManageGroup] =
    useState<PersonGroupWithPeopleResponse>();
  const [deleteGroupTarget, setDeleteGroupTarget] =
    useState<PersonGroupWithPeopleResponse>();
  const [groupsManager, setGroupsManager] = useState<{
    initialGroup?: PersonGroupWithPeopleResponse;
  }>();
  const [pendingPhotoUpload, setPendingPhotoUpload] = useState<{
    personId: string;
    file: File;
  }>();

  const refresh = async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: queryKeys.people }),
      qc.invalidateQueries({ queryKey: queryKeys.personGroups }),
    ]);
  };
  const createPerson = useMutation({
    // Media upload needs a person id, so the photo (if any) is attached in a
    // second call once the person exists.
    mutationFn: async ({
      body,
      photo,
    }: {
      body: PersonCreate;
      photo: PhotoChange;
    }) => {
      const created = await api.createPerson(body);
      if (photo.kind === "set") {
        try {
          await api.uploadPersonImage(created.id, photo.file);
        } catch {
          return { created, pendingPhoto: photo.file };
        }
      }
      return { created };
    },
    onSuccess: async ({ created, pendingPhoto }) => {
      setPersonForm(undefined);
      if (pendingPhoto) {
        setPendingPhotoUpload({
          personId: created.id,
          file: pendingPhoto,
        });
      }
      await refresh();
    },
  });
  const retryPhotoUpload = useMutation({
    mutationFn: ({ personId, file }: { personId: string; file: File }) =>
      api.uploadPersonImage(personId, file),
    onSuccess: async () => {
      setPendingPhotoUpload(undefined);
      await refresh();
    },
  });
  const updatePerson = useMutation({
    mutationFn: async ({
      id,
      body,
      photo,
    }: {
      id: string;
      body: PersonUpdate;
      photo?: PhotoChange;
    }) => {
      const updated = await api.updatePerson(id, body);
      if (photo?.kind === "set") {
        await api.uploadPersonImage(id, photo.file);
      } else if (photo?.kind === "clear") {
        await api.removePersonImage(id);
      }
      return updated;
    },
    onSuccess: async () => {
      setPersonForm(undefined);
      setManagePerson(undefined);
      await refresh();
    },
  });
  const archive = useMutation({
    mutationFn: (id: string) => api.archivePerson(id),
    onSuccess: async () => {
      setArchivePerson(undefined);
      await refresh();
    },
  });
  const merge = useMutation({
    mutationFn: ({ source, target }: { source: string; target: string }) =>
      api.mergePeople(source, target),
    onSuccess: async () => {
      setMergePerson(undefined);
      await refresh();
    },
  });
  const createGroup = useMutation({
    mutationFn: (body: PersonGroupCreate) => api.createPersonGroup(body),
    onSuccess: refresh,
  });
  const updateGroup = useMutation({
    mutationFn: ({ id, body }: { id: string; body: PersonGroupUpdate }) =>
      api.updatePersonGroup(id, body),
    onSuccess: refresh,
  });
  const removeGroup = useMutation({
    mutationFn: (id: string) => api.deletePersonGroup(id),
    onSuccess: async () => {
      setDeleteGroupTarget(undefined);
      await refresh();
    },
  });
  const manageMembership = useMutation({
    mutationFn: async ({
      group,
      selected,
    }: {
      group: PersonGroupWithPeopleResponse;
      selected: string[];
    }) => {
      const selectedSet = new Set(selected);
      await Promise.all(
        people.map((person) => {
          const current = (person.groups ?? []).map((item) => item.id);
          const has = current.includes(group.id);
          const wants = selectedSet.has(person.id);
          if (has === wants) return Promise.resolve();
          return api.updatePerson(person.id, {
            group_ids: wants
              ? [...current, group.id]
              : current.filter((id) => id !== group.id),
          });
        }),
      );
    },
    onSuccess: async () => {
      setManageGroup(undefined);
      await refresh();
    },
  });

  const loading = peopleQueryResult.isLoading || groupsQueryResult.isLoading;
  const loadError = peopleQueryResult.isError || groupsQueryResult.isError;
  const normalizedSearch = search.trim().toLowerCase();
  const searching = normalizedSearch.length > 0;

  const matchesPerson = (person: PersonResponse) =>
    !searching ||
    person.name.toLowerCase().includes(normalizedSearch) ||
    (person.nickname?.toLowerCase().includes(normalizedSearch) ?? false);
  const filterPeople = (items: PersonResponse[]) => items.filter(matchesPerson);

  const peopleById = new Map(people.map((person) => [person.id, person]));
  const groupedIds = new Set(
    groups.flatMap((group) => (group.people ?? []).map((person) => person.id)),
  );
  const ungrouped = filterPeople(
    people.filter((person) => !groupedIds.has(person.id)),
  );

  const groupView = groups.map((group) => {
    const members = (group.people ?? []).flatMap(
      (summary) => peopleById.get(summary.id) ?? [],
    );
    const visible = filterPeople(members);
    const nameMatches =
      searching && group.name.toLowerCase().includes(normalizedSearch);
    return { group, visible, nameMatches };
  });

  const nothingMatches =
    searching &&
    !ungrouped.length &&
    groupView.every(
      ({ visible, nameMatches }) => !visible.length && !nameMatches,
    );

  const actionsFor = (person: PersonResponse): PersonActions => ({
    onEdit: () => setPersonForm({ mode: "edit", person }),
    onManageGroups: () => setManagePerson(person),
    onMerge: () => setMergePerson(person),
    onArchive: () => setArchivePerson(person),
  });

  const toggleGroup = (id: string) =>
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <main className="jv-library" aria-label="People">
      <PageBar
        className="jv-page-bar--compact-only"
        leading={
          <IconButton label="Open navigation" onClick={shell.openNavigation}>
            <Menu aria-hidden="true" size={19} />
          </IconButton>
        }
        title={<span className="jv-label jv-truncate">People</span>}
      />
      <header className="jv-library__header">
        <div className="jv-library__headings">
          <h1 className="jv-display jv-library__heading">People</h1>
          <p className="jv-library__intro jv-body">
            Organise the people who appear in your journal.
          </p>
        </div>
        <div className="jv-library__actions">
          <Button onClick={() => setGroupsManager({})}>Manage groups</Button>
          <Button
            variant="primary"
            onClick={() => setPersonForm({ mode: "create", groupIds: [] })}
          >
            <Plus aria-hidden="true" size={16} />
            Add person
          </Button>
        </div>
      </header>

      <div className="jv-library__scroll">
        <div className="jv-library__body">
          <SearchInput
            className="jv-search-wrap"
            label="Search people"
            placeholder="Search people or groups…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onClear={() => setSearch("")}
          />

          {loading && (
            <div
              className="jv-lib-dir"
              role="status"
              aria-label="Loading people"
            >
              {["a", "b"].map((section) => (
                <section className="jv-lib-section" key={section}>
                  <div className="jv-lib-section__head">
                    <span className="jv-lib-section__toggle">
                      <Skeleton height="1rem" width="7rem" />
                      <span className="jv-lib-section__rule" />
                    </span>
                    <Skeleton height="0.85rem" width="3.5rem" />
                    <span className="jv-lib-section__slot" />
                  </div>
                  <ul className="jv-lib-section__grid">
                    {["x", "y", "z"].map((cell) => (
                      <li className="jv-lib-row" key={cell}>
                        <Skeleton height="2.5rem" width="2.5rem" />
                        <span className="jv-lib-row__text">
                          <Skeleton height="0.9rem" width="55%" />
                          <Skeleton height="0.75rem" width="40%" />
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}

          {loadError && (
            <StatusView
              role="alert"
              tone="danger"
              icon={<TriangleAlert size={20} />}
              title="People could not be loaded"
              description="Check your connection and try again."
              action={
                <Button
                  onClick={() => {
                    peopleQueryResult.refetch();
                    groupsQueryResult.refetch();
                  }}
                >
                  Try again
                </Button>
              }
            />
          )}

          {!loading && !loadError && !people.length && !groups.length && (
            <StatusView
              icon={<Users size={20} />}
              title="No people yet"
              description="Add a person or create a group to begin organising your Library."
              action={
                <Button
                  variant="primary"
                  onClick={() =>
                    setPersonForm({ mode: "create", groupIds: [] })
                  }
                >
                  <Plus aria-hidden="true" size={16} />
                  Add person
                </Button>
              }
            />
          )}

          {!loading &&
            !loadError &&
            (people.length > 0 || groups.length > 0) && (
              <div className="jv-lib-dir">
                {groupView.map(({ group, visible, nameMatches }) => {
                  if (searching && !nameMatches && !visible.length) return null;
                  return (
                    <GroupSection
                      key={group.id}
                      title={group.name}
                      colorValue={group.color_value}
                      icon={group.icon}
                      count={group.people?.length ?? 0}
                      open={searching || !collapsed.has(group.id)}
                      onToggle={() => toggleGroup(group.id)}
                      menu={
                        <AppAdaptiveMenu
                          label={`${group.name} group actions`}
                          align="end"
                          actions={[
                            {
                              kind: "command",
                              id: "add-person",
                              label: "Add person to group",
                              icon: UserPlus,
                              onSelect: () =>
                                setPersonForm({
                                  mode: "create",
                                  groupIds: [group.id],
                                }),
                            },
                            {
                              kind: "command",
                              id: "rename-group",
                              label: "Rename group",
                              icon: Pencil,
                              onSelect: () =>
                                setGroupsManager({ initialGroup: group }),
                            },
                            {
                              kind: "command",
                              id: "manage-people",
                              label: "Manage people",
                              icon: Users,
                              onSelect: () => setManageGroup(group),
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
                          {visible.map((person) => (
                            <PersonListItem
                              key={person.id}
                              person={person}
                              actions={actionsFor(person)}
                            />
                          ))}
                        </ul>
                      ) : (
                        <div className="jv-lib-section__empty">
                          {searching ? (
                            <span>No matching people in this group.</span>
                          ) : (
                            <>
                              <span>No one in this group yet.</span>
                              <Button
                                variant="ghost"
                                onClick={() =>
                                  setPersonForm({
                                    mode: "create",
                                    groupIds: [group.id],
                                  })
                                }
                              >
                                <Plus aria-hidden="true" size={15} />
                                Add person
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
                      {ungrouped.map((person) => (
                        <PersonListItem
                          key={person.id}
                          person={person}
                          actions={actionsFor(person)}
                        />
                      ))}
                    </ul>
                  </GroupSection>
                )}

                {nothingMatches && (
                  <div className="jv-lib-dir__nomatch">
                    <StatusView
                      title="No people found"
                      description={`No people or groups match “${search.trim()}”.`}
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

      {pendingPhotoUpload && (
        <p className="jv-library__alert" role="alert">
          The person was added, but their profile photo couldn’t be uploaded.{" "}
          <Button
            variant="ghost"
            size="sm"
            disabled={retryPhotoUpload.isPending}
            onClick={() => retryPhotoUpload.mutate(pendingPhotoUpload)}
          >
            {retryPhotoUpload.isPending ? "Retrying…" : "Retry upload"}
          </Button>
        </p>
      )}

      {personForm && (
        <PersonFormDialog
          state={personForm}
          groups={groups}
          submitting={createPerson.isPending || updatePerson.isPending}
          failed={createPerson.isError || updatePerson.isError}
          onClose={() => setPersonForm(undefined)}
          onSubmit={async (body, photo) => {
            if (personForm.mode === "create")
              await createPerson.mutateAsync({
                body: body as PersonCreate,
                photo,
              });
            else
              await updatePerson.mutateAsync({
                id: personForm.person.id,
                body,
                photo,
              });
          }}
        />
      )}
      {managePerson && (
        <ManagePersonGroupsDialog
          person={managePerson}
          groups={groups}
          submitting={updatePerson.isPending}
          failed={updatePerson.isError}
          onClose={() => setManagePerson(undefined)}
          onSubmit={async (groupIds) => {
            await updatePerson.mutateAsync({
              id: managePerson.id,
              body: { group_ids: groupIds },
            });
          }}
        />
      )}
      {groupsManager && (
        <GroupsManagerDialog
          groups={groups}
          initialGroup={groupsManager.initialGroup}
          busy={
            createGroup.isPending ||
            updateGroup.isPending ||
            removeGroup.isPending
          }
          saveFailed={createGroup.isError || updateGroup.isError}
          deleteFailed={removeGroup.isError}
          onClose={() => setGroupsManager(undefined)}
          onCreate={async (body) => {
            await createGroup.mutateAsync(body);
          }}
          onUpdate={async (id, body) => {
            await updateGroup.mutateAsync({ id, body });
          }}
          onDelete={async (id) => {
            await removeGroup.mutateAsync(id);
          }}
        />
      )}
      {manageGroup && (
        <ManagePeopleDialog
          group={manageGroup}
          people={people}
          submitting={manageMembership.isPending}
          failed={manageMembership.isError}
          onClose={() => setManageGroup(undefined)}
          onSubmit={async (selected) => {
            await manageMembership.mutateAsync({
              group: manageGroup,
              selected,
            });
          }}
        />
      )}
      {mergePerson && (
        <MergeDialog
          person={mergePerson}
          people={people}
          submitting={merge.isPending}
          failed={merge.isError}
          onClose={() => setMergePerson(undefined)}
          onSubmit={async (target) => {
            await merge.mutateAsync({ source: mergePerson.id, target });
          }}
        />
      )}
      {archivePerson && (
        <AppConfirmDialog
          open
          onOpenChange={(open) => !open && setArchivePerson(undefined)}
          title={`Archive ${archivePerson.name}?`}
          description="The person is hidden from active lists. Existing moment references remain."
          confirmLabel={archive.isPending ? "Archiving…" : "Archive"}
          destructive
          pending={archive.isPending}
          onConfirm={() => archive.mutate(archivePerson.id)}
        >
          {archive.isError && (
            <p className="jv-library__alert" role="alert">
              The person could not be archived. Try again.
            </p>
          )}
        </AppConfirmDialog>
      )}
      {deleteGroupTarget && (
        <AppConfirmDialog
          open
          onOpenChange={(open) => !open && setDeleteGroupTarget(undefined)}
          title={`Delete ${deleteGroupTarget.name}?`}
          description="People remain in your Library and are removed only from this group."
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

function GroupChecklist({
  groups,
  selected,
  onChange,
}: {
  groups: PersonGroupWithPeopleResponse[];
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  if (!groups.length) return <p className="jv-caption">No groups yet.</p>;
  return (
    <fieldset className="jv-library-checklist">
      <legend>Groups</legend>
      {groups.map((group) => (
        <label key={group.id}>
          <input
            type="checkbox"
            checked={selected.includes(group.id)}
            onChange={(event) =>
              onChange(
                event.target.checked
                  ? [...selected, group.id]
                  : selected.filter((id) => id !== group.id),
              )
            }
          />
          <span>{group.name}</span>
        </label>
      ))}
    </fieldset>
  );
}

function PersonFormDialog({
  state,
  groups,
  submitting,
  failed,
  onClose,
  onSubmit,
}: {
  state: PersonFormState;
  groups: PersonGroupWithPeopleResponse[];
  submitting: boolean;
  failed: boolean;
  onClose: () => void;
  onSubmit: (
    body: PersonCreate | PersonUpdate,
    photo: PhotoChange,
  ) => Promise<void>;
}) {
  const person = state.mode === "edit" ? state.person : undefined;
  const [name, setName] = useState(person?.name ?? "");
  const [nickname, setNickname] = useState(person?.nickname ?? "");
  const [note, setNote] = useState(person?.note ?? "");
  const [groupIds, setGroupIds] = useState(
    state.mode === "create"
      ? state.groupIds
      : (person?.groups ?? []).map((g) => g.id),
  );
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoCleared, setPhotoCleared] = useState(false);
  const photoInputRef = useRef<HTMLInputElement>(null);
  const previewUrl = useMemo(
    () => (photoFile ? URL.createObjectURL(photoFile) : null),
    [photoFile],
  );
  useEffect(() => {
    if (!previewUrl) return;
    return () => URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);
  const shownImage =
    previewUrl ?? (photoCleared ? null : (person?.profile_image_url ?? null));

  return (
    <Dialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={person ? `Edit ${person.name}` : "Add person"}
    >
      <form
        className="jv-library-form"
        onSubmit={async (event) => {
          event.preventDefault();
          const photo: PhotoChange = photoFile
            ? { kind: "set", file: photoFile }
            : photoCleared
              ? { kind: "clear" }
              : { kind: "keep" };
          try {
            await onSubmit(
              {
                name: name.trim(),
                nickname: nickname.trim() || null,
                note: note.trim() || null,
                group_ids: groupIds,
              },
              photo,
            );
          } catch {
            // Mutation state owns the on-screen failure.
          }
        }}
      >
        <div className="jv-library-form__photo">
          {shownImage ? (
            <img
              className="jv-library-form__photo-preview"
              src={shownImage}
              alt=""
            />
          ) : (
            <span className="jv-library-form__photo-preview" aria-hidden="true">
              {initials(name || person?.name || "")}
            </span>
          )}
          <div className="jv-library-form__photo-actions">
            <input
              ref={photoInputRef}
              className="sr-only"
              type="file"
              accept="image/*"
              aria-label="Profile photo"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) {
                  setPhotoFile(file);
                  setPhotoCleared(false);
                }
                event.target.value = "";
              }}
            />
            <Button size="sm" onClick={() => photoInputRef.current?.click()}>
              <ImagePlus aria-hidden="true" size={15} />
              {shownImage ? "Change photo" : "Add photo"}
            </Button>
            {shownImage && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setPhotoFile(null);
                  setPhotoCleared(true);
                }}
              >
                Remove photo
              </Button>
            )}
          </div>
        </div>
        <label htmlFor="library-person-name">
          <span>Name</span>
          <Input
            id="library-person-name"
            aria-label="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label htmlFor="library-person-nickname">
          <span>
            Nickname <span className="jv-caption">Optional</span>
          </span>
          <Input
            id="library-person-nickname"
            aria-label="Nickname"
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
          />
        </label>
        <label htmlFor="library-person-note">
          <span>
            Note <span className="jv-caption">Optional</span>
          </span>
          <textarea
            id="library-person-note"
            className="jv-field jv-library-form__note"
            aria-label="Note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <GroupChecklist
          groups={groups}
          selected={groupIds}
          onChange={setGroupIds}
        />
        {failed && (
          <p className="jv-library__alert" role="alert">
            The person could not be saved. Your changes are still here.
          </p>
        )}
        <div className="jv-dialog__actions">
          <DialogClose render={<Button>Cancel</Button>} />
          <Button
            type="submit"
            variant="primary"
            disabled={!name.trim() || submitting}
          >
            {submitting ? "Saving…" : person ? "Save" : "Add person"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function ManagePeopleDialog({
  group,
  people,
  submitting,
  failed,
  onClose,
  onSubmit,
}: {
  group: PersonGroupWithPeopleResponse;
  people: PersonResponse[];
  submitting: boolean;
  failed: boolean;
  onClose: () => void;
  onSubmit: (ids: string[]) => Promise<void>;
}) {
  const [selected, setSelected] = useState(
    (group.people ?? []).map((p) => p.id),
  );
  return (
    <Dialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={`Manage ${group.name}`}
      description="People can belong to more than one group."
    >
      <form
        className="jv-library-form"
        onSubmit={async (event) => {
          event.preventDefault();
          try {
            await onSubmit(selected);
          } catch {
            // Mutation state owns the on-screen failure.
          }
        }}
      >
        <fieldset className="jv-library-checklist jv-library-checklist--people">
          <legend>People</legend>
          {people.map((person) => (
            <label key={person.id}>
              <input
                type="checkbox"
                checked={selected.includes(person.id)}
                onChange={(event) =>
                  setSelected(
                    event.target.checked
                      ? [...selected, person.id]
                      : selected.filter((id) => id !== person.id),
                  )
                }
              />
              <span>{person.name}</span>
            </label>
          ))}
        </fieldset>
        {failed && (
          <p className="jv-library__alert" role="alert">
            Group membership could not be saved.
          </p>
        )}
        <div className="jv-dialog__actions">
          <DialogClose render={<Button>Cancel</Button>} />
          <Button type="submit" variant="primary" disabled={submitting}>
            {submitting ? "Saving…" : "Save"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function ManagePersonGroupsDialog({
  person,
  groups,
  submitting,
  failed,
  onClose,
  onSubmit,
}: {
  person: PersonResponse;
  groups: PersonGroupWithPeopleResponse[];
  submitting: boolean;
  failed: boolean;
  onClose: () => void;
  onSubmit: (groupIds: string[]) => Promise<void>;
}) {
  const [selected, setSelected] = useState(
    (person.groups ?? []).map((group) => group.id),
  );
  return (
    <Dialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={`Manage groups for ${person.name}`}
      description="A person can belong to more than one group."
    >
      <form
        className="jv-library-form"
        onSubmit={async (event) => {
          event.preventDefault();
          try {
            await onSubmit(selected);
          } catch {
            // Mutation state owns the on-screen failure.
          }
        }}
      >
        <GroupChecklist
          groups={groups}
          selected={selected}
          onChange={setSelected}
        />
        {failed && (
          <p className="jv-library__alert" role="alert">
            Group membership could not be saved.
          </p>
        )}
        <div className="jv-dialog__actions">
          <DialogClose render={<Button>Cancel</Button>} />
          <Button type="submit" variant="primary" disabled={submitting}>
            {submitting ? "Saving…" : "Save"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function MergeDialog({
  person,
  people,
  submitting,
  failed,
  onClose,
  onSubmit,
}: {
  person: PersonResponse;
  people: PersonResponse[];
  submitting: boolean;
  failed: boolean;
  onClose: () => void;
  onSubmit: (target: string) => Promise<void>;
}) {
  const [target, setTarget] = useState("");
  return (
    <Dialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={`Merge ${person.name}`}
      description="Moments, group memberships and linked identities move to the person you choose. This cannot be undone."
    >
      <form
        className="jv-library-form"
        onSubmit={async (event) => {
          event.preventDefault();
          try {
            await onSubmit(target);
          } catch {
            // Mutation state owns the on-screen failure.
          }
        }}
      >
        <label>
          <span>Merge into</span>
          <select
            className="jv-field"
            aria-label="Merge into"
            value={target}
            onChange={(event) => setTarget(event.target.value)}
          >
            <option value="">Choose a person</option>
            {people
              .filter((item) => item.id !== person.id)
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
          </select>
        </label>
        {failed && (
          <p className="jv-library__alert" role="alert">
            The people could not be merged.
          </p>
        )}
        <div className="jv-dialog__actions">
          <DialogClose render={<Button>Cancel</Button>} />
          <Button
            type="submit"
            variant="danger"
            disabled={!target || submitting}
          >
            {submitting ? "Merging…" : "Merge people"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
