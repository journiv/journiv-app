import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Pencil,
  Trash2,
  UserCheck,
  UserPlus,
  UsersRound,
  UserX,
} from "lucide-react";
import { useMemo, useState } from "react";
import { sessionStore } from "../../../api/auth/session";
import { api } from "../../../api/client/api";
import { ApiError } from "../../../api/client/errors";
import type {
  AdminUserCreate,
  AdminUserListResponse,
  AdminUserUpdate,
} from "../../../api/generated/types.gen";
import { queryKeys } from "../../../api/query/keys";
import { adminUsersQuery, currentUserQuery } from "../../../api/query/options";
import {
  AppAdaptiveMenu,
  type AppMenuAction,
} from "../../../components/journiv/AppAdaptiveMenu";
import { StatusView } from "../../../components/journiv/StatusView";
import { Alert, AlertDescription } from "../../../components/ui/alert";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "../../../components/ui/empty";
import { SearchInput } from "../../../components/ui/search-input";
import { Skeleton } from "../../../components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../../components/ui/table";
import { useSettingsDirty } from "../SettingsModal";
import { SettingsSection } from "../SettingsSection";
import { DeleteUserDialog } from "./DeleteUserDialog";
import { UserForm, type UserFormValues } from "./UserForm";
import "./users.css";

const PAGE_SIZE = 10;

/**
 * The backend returns a precise `detail` for the rules an admin can hit
 * (last administrator, duplicate email, password policy). Show it verbatim for
 * client errors; fall back to a written line for 5xx / no-response.
 */
function writeReason(error: unknown, fallback: string) {
  if (
    error instanceof ApiError &&
    typeof error.status === "number" &&
    error.status >= 400 &&
    error.status < 500 &&
    error.message
  )
    return error.message;
  return fallback;
}

function signOutAndReload() {
  sessionStore.clear();
  window.location.assign("/login");
}

type Editor =
  | { kind: "create" }
  | { kind: "edit"; user: AdminUserListResponse };

function initials(name: string, email: string) {
  const parts = (name.trim() || email.trim()).split(/\s+/).filter(Boolean);
  if (!parts.length) return "";
  return (
    parts.length > 1
      ? `${parts[0][0]}${parts[parts.length - 1][0]}`
      : parts[0].slice(0, 2)
  ).toUpperCase();
}

function accountDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(
    date,
  );
}

function authLabel(user: AdminUserListResponse) {
  if (user.login_type === "local") return "Password";
  if (user.login_type === "oidc") return "OIDC";
  return user.login_type;
}

function providerLabel(provider: string) {
  try {
    return new URL(provider).hostname;
  } catch {
    return provider;
  }
}

function UsersSkeleton() {
  return (
    <div
      className="jv-users__skeleton"
      role="status"
      aria-label="Loading users"
    >
      <Skeleton height="2.25rem" />
      {[0, 1, 2, 3].map((row) => (
        <div className="jv-users__skeleton-row" key={row}>
          <Skeleton width="2.25rem" height="2.25rem" className="rounded-full" />
          <div>
            <Skeleton width="9rem" height="0.85rem" />
            <Skeleton width="13rem" height="0.7rem" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function UsersPage() {
  const queryClient = useQueryClient();
  const usersQuery = useQuery(adminUsersQuery());
  const currentUser = useQuery(currentUserQuery());
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [editor, setEditor] = useState<Editor>();
  const [formDirty, setFormDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formFailure, setFormFailure] = useState<string>();
  const [statusUserId, setStatusUserId] = useState<string>();
  const [actionFailure, setActionFailure] = useState<string>();
  const [deleteTarget, setDeleteTarget] = useState<AdminUserListResponse>();
  const [deleting, setDeleting] = useState(false);
  const [deleteFailure, setDeleteFailure] = useState<string>();
  useSettingsDirty(formDirty);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return usersQuery.data ?? [];
    return (usersQuery.data ?? []).filter((user) =>
      [
        user.name,
        user.email,
        user.role,
        user.is_active ? "active" : "inactive",
        user.login_type,
        ...(user.linked_providers ?? []),
      ].some((value) => value.toLowerCase().includes(needle)),
    );
  }, [search, usersQuery.data]);

  const activeAdminCount = useMemo(
    () =>
      (usersQuery.data ?? []).filter(
        (candidate) => candidate.role === "admin" && candidate.is_active,
      ).length,
    [usersQuery.data],
  );

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const visibleUsers = filtered.slice(
    safePage * PAGE_SIZE,
    (safePage + 1) * PAGE_SIZE,
  );

  async function refreshUsers(userId?: string) {
    const jobs: Promise<unknown>[] = [
      queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers }),
    ];
    if (userId === currentUser.data?.id)
      jobs.push(queryClient.invalidateQueries({ queryKey: queryKeys.me }));
    await Promise.all(jobs);
  }

  async function saveUser(values: UserFormValues) {
    if (!editor) return;
    setSaving(true);
    setFormFailure(undefined);
    try {
      if (editor.kind === "create") {
        await api.createAdminUser(values as AdminUserCreate);
        setPage(0);
        await refreshUsers();
      } else {
        await api.updateAdminUser(editor.user.id, values as AdminUserUpdate);
        await refreshUsers(editor.user.id);
      }
      setFormDirty(false);
      setEditor(undefined);
    } catch (error) {
      setFormFailure(
        writeReason(
          error,
          editor.kind === "create"
            ? "This account couldn’t be created. The email may already be in use."
            : "These changes couldn’t be saved. Try again.",
        ),
      );
    } finally {
      setSaving(false);
    }
  }

  async function setActive(user: AdminUserListResponse) {
    const nextActive = !user.is_active;
    setStatusUserId(user.id);
    setActionFailure(undefined);
    try {
      await api.updateAdminUser(user.id, { is_active: nextActive });
      if (user.id === currentUser.data?.id && !nextActive) {
        signOutAndReload();
        return;
      }
      await refreshUsers(user.id);
    } catch (error) {
      setActionFailure(
        writeReason(
          error,
          `${user.name} couldn’t be ${nextActive ? "activated" : "deactivated"}. Try again.`,
        ),
      );
    } finally {
      setStatusUserId(undefined);
    }
  }

  async function deleteUser() {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteFailure(undefined);
    try {
      await api.deleteAdminUser(deleteTarget.id);
      if (deleteTarget.id === currentUser.data?.id) {
        signOutAndReload();
        return;
      }
      await refreshUsers();
      setDeleteTarget(undefined);
    } catch (error) {
      setDeleteFailure(
        writeReason(error, "This account couldn’t be deleted. Try again."),
      );
    } finally {
      setDeleting(false);
    }
  }

  if (editor)
    return (
      <UserForm
        user={editor.kind === "edit" ? editor.user : undefined}
        saving={saving}
        failedMessage={formFailure}
        onDirtyChange={setFormDirty}
        onCancel={() => {
          setFormFailure(undefined);
          setEditor(undefined);
        }}
        onSubmit={saveUser}
      />
    );

  return (
    // `jv-users` is the query container for the table's column budget, and the
    // wide measure is because this is a data table rather than a form
    // (DESIGN.md §9, §23).
    <div className="jv-settings__body jv-settings__body--wide jv-users">
      <SettingsSection
        title="Users"
        titleId="users-title"
        intro="Create accounts and manage access to this Journiv instance."
        action={
          <Button
            type="button"
            variant="default"
            onClick={() => {
              setFormFailure(undefined);
              setEditor({ kind: "create" });
            }}
          >
            <UserPlus data-icon="inline-start" />
            Add user
          </Button>
        }
      >
        {usersQuery.isLoading ? (
          <UsersSkeleton />
        ) : usersQuery.isError ? (
          <StatusView
            tone="danger"
            role="alert"
            title="We couldn’t load users"
            description="Something went wrong reaching the server."
            action={
              <Button
                variant="secondary"
                onClick={() => void usersQuery.refetch()}
              >
                Try again
              </Button>
            }
          />
        ) : (
          <>
            <div className="jv-users__toolbar">
              <SearchInput
                label="Search users"
                placeholder="Search by name, email, role or provider…"
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setPage(0);
                }}
                onClear={() => {
                  setSearch("");
                  setPage(0);
                }}
              />
              <p className="jv-users__count jv-meta">
                {filtered.length}{" "}
                {filtered.length === 1 ? "account" : "accounts"}
              </p>
            </div>

            {actionFailure && (
              <Alert variant="destructive">
                <AlertDescription>{actionFailure}</AlertDescription>
              </Alert>
            )}

            {visibleUsers.length ? (
              <>
                <Table className="jv-users-table">
                  <TableCaption className="sr-only">
                    Accounts with their role, status and last activity; each row
                    also carries the account's email and sign-in method
                  </TableCaption>
                  <TableHeader>
                    <TableRow>
                      <TableHead>User</TableHead>
                      <TableHead className="jv-users-table__role">
                        Role
                      </TableHead>
                      <TableHead className="jv-users-table__status">
                        Status
                      </TableHead>
                      <TableHead className="jv-users-table__last">
                        Last active
                      </TableHead>
                      <TableHead className="jv-users-table__actions">
                        <span className="sr-only">Actions</span>
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {visibleUsers.map((user) => {
                      const isCurrent = user.id === currentUser.data?.id;
                      const isLastActiveAdmin =
                        user.role === "admin" &&
                        user.is_active &&
                        activeAdminCount <= 1;
                      return (
                        <TableRow key={user.id}>
                          <TableCell className="jv-users-table__user">
                            <span className="jv-users-table__user-content">
                              <span
                                className="jv-users__avatar jv-caption"
                                aria-hidden="true"
                              >
                                {initials(user.name, user.email)}
                              </span>
                              <span className="jv-users__identity">
                                <span className="jv-users__name">
                                  {user.name}
                                  {isCurrent && (
                                    <Badge variant="ghost">You</Badge>
                                  )}
                                </span>
                                <span className="jv-users__email">
                                  {user.email}
                                </span>
                                {/* Authentication lives here rather than in a
                                    column of its own: the settings modal never
                                    gives this table more than about 1000px, and
                                    six columns want ~950px of that, so the
                                    column could only ever have existed in a
                                    sliver of widths (users.css). */}
                                <span className="jv-users__auth jv-caption">
                                  {authLabel(user)}
                                  {user.linked_providers?.length ? (
                                    <>
                                      {" · "}
                                      <span
                                        className="jv-users__providers"
                                        title={user.linked_providers.join(", ")}
                                      >
                                        {user.linked_providers
                                          .map(providerLabel)
                                          .join(", ")}
                                      </span>
                                    </>
                                  ) : null}
                                </span>
                                {/* The Last active column's content, shown only
                                    at the widths where that column is dropped.
                                    `display: none` keeps the duplicate out of
                                    the accessibility tree. */}
                                <span className="jv-users__last-fallback jv-caption">
                                  {user.last_login_at
                                    ? `Last active ${accountDate(user.last_login_at)}`
                                    : "Never signed in"}
                                </span>
                              </span>
                            </span>
                          </TableCell>
                          <TableCell className="jv-users-table__role">
                            <Badge
                              variant={
                                user.role === "admin" ? "outline" : "secondary"
                              }
                            >
                              {user.role === "admin" ? "Administrator" : "User"}
                            </Badge>
                          </TableCell>
                          <TableCell className="jv-users-table__status">
                            <Badge
                              variant={user.is_active ? "secondary" : "outline"}
                            >
                              {user.is_active ? "Active" : "Inactive"}
                            </Badge>
                          </TableCell>
                          <TableCell className="jv-users-table__last">
                            <span className="jv-users-table__cell-stack">
                              {user.last_login_at ? (
                                <time dateTime={user.last_login_at}>
                                  {accountDate(user.last_login_at)}
                                </time>
                              ) : (
                                <span>Never</span>
                              )}
                              <span className="jv-users__created jv-caption">
                                Created {accountDate(user.created_at)}
                              </span>
                            </span>
                          </TableCell>
                          <TableCell className="jv-users-table__actions">
                            <AppAdaptiveMenu
                              label={`${user.name} actions`}
                              align="end"
                              actions={[
                                {
                                  kind: "command",
                                  id: "edit",
                                  label: "Edit",
                                  icon: Pencil,
                                  onSelect: () => {
                                    setFormFailure(undefined);
                                    setEditor({ kind: "edit", user });
                                  },
                                },
                                // Your own account cannot be deactivated or
                                // deleted from this row.
                                ...(isCurrent
                                  ? []
                                  : ([
                                      {
                                        kind: "command",
                                        id: "active",
                                        label: user.is_active
                                          ? "Deactivate"
                                          : "Activate",
                                        icon: user.is_active
                                          ? UserX
                                          : UserCheck,
                                        disabled:
                                          statusUserId === user.id ||
                                          isLastActiveAdmin,
                                        onSelect: () => void setActive(user),
                                      },
                                      {
                                        kind: "command",
                                        id: "delete",
                                        label: "Delete",
                                        icon: Trash2,
                                        destructive: true,
                                        separatorBefore: true,
                                        disabled: isLastActiveAdmin,
                                        onSelect: () => {
                                          setDeleteFailure(undefined);
                                          setDeleteTarget(user);
                                        },
                                      },
                                    ] satisfies AppMenuAction[])),
                              ]}
                            />
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>

                {filtered.length > PAGE_SIZE && (
                  <div className="jv-users__pagination">
                    <p className="jv-meta">
                      {safePage * PAGE_SIZE + 1}–
                      {Math.min((safePage + 1) * PAGE_SIZE, filtered.length)} of{" "}
                      {filtered.length}
                    </p>
                    <div>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={safePage === 0}
                        onClick={() =>
                          setPage((current) => Math.max(0, current - 1))
                        }
                      >
                        Previous
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={safePage + 1 >= pageCount}
                        onClick={() => setPage((current) => current + 1)}
                      >
                        Next
                      </Button>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <Empty>
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <UsersRound aria-hidden="true" />
                  </EmptyMedia>
                  <EmptyTitle>
                    {search ? "No matching users" : "No users"}
                  </EmptyTitle>
                  <EmptyDescription>
                    {search
                      ? "Try another name, email, role or provider."
                      : "Create the first account for this instance."}
                  </EmptyDescription>
                </EmptyHeader>
                {search && (
                  <EmptyContent>
                    <Button variant="secondary" onClick={() => setSearch("")}>
                      Clear search
                    </Button>
                  </EmptyContent>
                )}
              </Empty>
            )}
          </>
        )}
      </SettingsSection>

      {deleteTarget && (
        <DeleteUserDialog
          user={deleteTarget}
          currentUserId={currentUser.data?.id}
          deleting={deleting}
          failure={deleteFailure}
          onOpenChange={(open) => {
            if (!open && !deleting) setDeleteTarget(undefined);
          }}
          onConfirm={deleteUser}
        />
      )}
    </div>
  );
}
