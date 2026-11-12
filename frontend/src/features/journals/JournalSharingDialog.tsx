import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../../api/client/api";
import type {
  JournalPermission,
  JournalResponse,
} from "../../api/generated/types.gen";
import { queryKeys } from "../../api/query/keys";
import { AppAdaptiveDialog } from "../../components/journiv/AppAdaptiveDialog";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";

export function JournalSharingDialog({
  journal,
  open,
  onOpenChange,
}: {
  journal: JournalResponse | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [query, setQuery] = useState("");
  const [selectedUserId, setSelectedUserId] = useState<string>();
  const [permission, setPermission] = useState<JournalPermission>("readonly");
  const [submitting, setSubmitting] = useState(false);
  const [failed, setFailed] = useState(false);
  const qc = useQueryClient();
  const journalId = journal?.id;
  const users = useQuery({
    queryKey: ["journal-member-search", query],
    queryFn: () => api.searchUsers(query),
    enabled: open && query.trim().length >= 2,
  });
  const members = useQuery({
    queryKey: ["journal-members", journalId],
    queryFn: () => {
      if (!journalId) throw new Error("A journal is required to load members.");
      return api.journalMembers(journalId);
    },
    enabled: open && journalId !== undefined,
  });

  useEffect(() => {
    if (!open || !journalId) return;
    setQuery("");
    setSelectedUserId(undefined);
    setPermission("readonly");
    setFailed(false);
  }, [open, journalId]);

  const selected = users.data?.find((user) => user.id === selectedUserId);
  async function addMember() {
    if (!journal || !selected || submitting) return;
    setSubmitting(true);
    setFailed(false);
    try {
      await api.addJournalMember(journal.id, {
        user_id: selected.id,
        permission,
      });
      // Membership changes also change which journals appear in the sidebar.
      await qc.invalidateQueries({ queryKey: queryKeys.journals });
      await members.refetch();
      setSelectedUserId(undefined);
      setQuery("");
    } catch {
      setFailed(true);
    } finally {
      setSubmitting(false);
    }
  }
  async function removeMember(userId: string) {
    if (!journal || submitting) return;
    setSubmitting(true);
    setFailed(false);
    try {
      await api.removeJournalMember(journal.id, userId);
      await members.refetch();
      // Keep the owner’s journal list and sharing state in sync.
      await qc.invalidateQueries({ queryKey: queryKeys.journals });
    } catch {
      setFailed(true);
    } finally {
      setSubmitting(false);
    }
  }
  async function changePermission(
    userId: string,
    permission: JournalPermission,
  ) {
    if (!journal || submitting) return;
    setSubmitting(true);
    setFailed(false);
    try {
      await api.updateJournalMember(journal.id, userId, { permission });
      await members.refetch();
    } catch {
      setFailed(true);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppAdaptiveDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Share journal"
      description={
        journal ? `Give someone access to ${journal.title}.` : undefined
      }
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button disabled={!selected || submitting} onClick={addMember}>
            {submitting ? "Adding…" : "Add member"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="space-y-2">
          <p className="text-sm font-medium">Shared with</p>
          {members.isError ? (
            <div className="space-y-2" role="alert">
              <p className="text-sm text-destructive">
                Shared people could not be loaded.
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => members.refetch()}
              >
                Retry
              </Button>
            </div>
          ) : members.data?.length ? (
            <ul className="space-y-1 text-sm text-muted-foreground">
              {members.data.map((member) => (
                <li
                  key={member.user_id}
                  className="flex items-center justify-between gap-2"
                >
                  <span>
                    {member.name} ·{" "}
                    {member.permission === "edit" ? "Can edit" : "Can view"}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={submitting}
                    onClick={() =>
                      changePermission(
                        member.user_id,
                        member.permission === "edit" ? "readonly" : "edit",
                      )
                    }
                  >
                    Make {member.name}{" "}
                    {member.permission === "edit" ? "view-only" : "an editor"}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={submitting}
                    onClick={() => removeMember(member.user_id)}
                  >
                    Remove {member.name}
                  </Button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              No one else has access yet.
            </p>
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor="journal-member-search">Find a person</Label>
          <Input
            id="journal-member-search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Name or email"
          />
          {users.data?.map((user) => (
            <Button
              key={user.id}
              variant={selectedUserId === user.id ? "secondary" : "outline"}
              className="w-full justify-start"
              onClick={() => setSelectedUserId(user.id)}
            >
              {user.name} ({user.email})
            </Button>
          ))}
        </div>
        <div className="space-y-2">
          <Label htmlFor="journal-member-permission">Permission</Label>
          <select
            id="journal-member-permission"
            className="h-9 rounded-md border border-input bg-transparent px-2 text-sm"
            value={permission}
            onChange={(event) =>
              setPermission(event.target.value as JournalPermission)
            }
          >
            <option value="readonly">Can view</option>
            <option value="edit">Can edit</option>
          </select>
        </div>
        {failed && (
          <p className="text-sm text-destructive" role="alert">
            Couldn't update member. Try again.
          </p>
        )}
      </div>
    </AppAdaptiveDialog>
  );
}
