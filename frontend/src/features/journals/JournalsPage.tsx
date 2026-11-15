import { Menu, NotebookText, Plus, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { useSearch } from "@tanstack/react-router";
import type { JournalResponse } from "../../api/generated/types.gen";
import { PageBar } from "../../components/journiv/PageBar";
import { Button } from "../../components/ui/button";
import { IconButton } from "../../components/ui/icon-button";
import { Skeleton } from "../../components/ui/skeleton";
import { StatusView } from "../../components/journiv/StatusView";
import { groupJournals, reorderWithinGroup } from "../../lib/journalOrder";
import { useJournalLookup } from "../../lib/useJournalLookup";
import { usePaneScrollRestoration } from "../../lib/usePaneScrollRestoration";
import { useShell } from "../shell/AppShell";
import { DeleteJournalDialog } from "./DeleteJournalDialog";
import { JournalFormDialog, type JournalFormValues } from "./JournalFormDialog";
import { JournalRow } from "./JournalRow";
import { JournalSharingDialog } from "./JournalSharingDialog";
import { useJournalMutations } from "./useJournalMutations";
import { canManageJournal, isSharedJournal } from "../../lib/journalAccess";
import "./journals.css";

export function JournalsPage() {
  const shell = useShell();
  const { q = "" } = useSearch({ strict: false }) as { q?: string };
  const { journals, isLoading, isError, refetch } = useJournalLookup();
  const { create, update, toggleFavorite, setArchived, reorder, remove } =
    useJournalMutations();
  const scrollRef = usePaneScrollRestoration<HTMLDivElement>(
    "journals",
    isLoading,
  );

  const [formOpen, setFormOpen] = useState(false);
  const [formJournal, setFormJournal] = useState<JournalResponse | undefined>();
  const [deleteTarget, setDeleteTarget] = useState<JournalResponse | null>(
    null,
  );
  const [sharingJournal, setSharingJournal] = useState<JournalResponse | null>(
    null,
  );

  const { active, archived } = groupJournals(journals);
  // Received journals have the owner's ordering, not the viewer's personal order.
  const ownedActive = active.filter((journal) => !isSharedJournal(journal));
  const sharedActive = active.filter(isSharedJournal);
  const favs = ownedActive.filter((j) => j.is_favorite);
  const rest = ownedActive.filter((j) => !j.is_favorite);

  function openCreate() {
    create.reset();
    update.reset();
    setFormJournal(undefined);
    setFormOpen(true);
  }
  function openEdit(journal: JournalResponse) {
    create.reset();
    update.reset();
    setFormJournal(journal);
    setFormOpen(true);
  }
  async function submitForm(values: JournalFormValues) {
    if (formJournal) {
      await update.mutateAsync({ id: formJournal.id, body: values });
    } else {
      await create.mutateAsync(values);
    }
    setFormOpen(false);
  }
  function openDelete(journal: JournalResponse) {
    remove.reset();
    setDeleteTarget(journal);
  }
  async function confirmDelete() {
    if (!deleteTarget) return;
    await remove.mutateAsync(deleteTarget.id);
    setDeleteTarget(null);
  }
  function move(id: string, direction: "up" | "down") {
    // Shared journals are visible here but cannot be reordered by this user.
    const updates = reorderWithinGroup(ownedActive, id, direction);
    if (updates) reorder.mutate({ updates });
  }

  function renderRow(journal: JournalResponse, peers: JournalResponse[]) {
    return (
      <JournalRow
        key={journal.id}
        journal={journal}
        search={q}
        canMoveUp={canManageJournal(journal) && peers[0]?.id !== journal.id}
        canMoveDown={
          canManageJournal(journal) &&
          peers[peers.length - 1]?.id !== journal.id
        }
        onRename={openEdit}
        onEditAppearance={openEdit}
        onDelete={openDelete}
        onToggleFavorite={(j) => toggleFavorite.mutate(j)}
        onSetArchived={(id, archived) => setArchived.mutate({ id, archived })}
        onMove={move}
        onShare={setSharingJournal}
      />
    );
  }

  return (
    <section className="jv-shell__list" aria-label="Journals">
      <PageBar
        className="jv-page-bar--compact-only"
        leading={
          <IconButton label="Open navigation" onClick={shell.openNavigation}>
            <Menu aria-hidden="true" size={19} />
          </IconButton>
        }
        title={<span className="jv-label jv-truncate">Journals</span>}
      />

      <header className="jv-journals__header">
        <h1 className="jv-display jv-journals__heading">Journals</h1>
        <Button variant="default" onClick={openCreate}>
          <Plus aria-hidden="true" size={16} />
          New journal
        </Button>
      </header>

      <div className="jv-journals__scroll" ref={scrollRef}>
        {isLoading && (
          <ul className="jv-jlist" role="status" aria-label="Loading journals">
            {["a", "b", "c", "d"].map((k) => (
              <li className="jv-jrow jv-jrow--skeleton" key={k}>
                <Skeleton height="1rem" width="1rem" />
                <span className="jv-jrow__text">
                  <Skeleton height="0.95rem" width="42%" />
                  <Skeleton height="0.8rem" width="70%" />
                  <Skeleton height="0.8rem" width="55%" />
                </span>
              </li>
            ))}
          </ul>
        )}

        {isError && (
          <StatusView
            role="alert"
            tone="danger"
            icon={<TriangleAlert size={20} />}
            title="Journals could not be loaded"
            description="Check your connection and try again."
            action={
              <Button variant="secondary" onClick={() => refetch()}>
                Try again
              </Button>
            }
          />
        )}

        {!isLoading && !isError && !journals.length && (
          <StatusView
            icon={<NotebookText size={20} />}
            title="No journals yet"
            description="Create a journal to group the moments you write."
            action={
              <Button variant="default" onClick={openCreate}>
                <Plus aria-hidden="true" size={16} />
                New journal
              </Button>
            }
          />
        )}

        {!isLoading && !isError && active.length > 0 && (
          <ul className="jv-jlist">
            {favs.map((j) => renderRow(j, favs))}
            {rest.map((j) => renderRow(j, rest))}
          </ul>
        )}

        {!isLoading && !isError && sharedActive.length > 0 && (
          <section aria-label="Shared with me">
            <h2 className="jv-label">Shared with me</h2>
            <ul className="jv-jlist">
              {sharedActive.map((j) => renderRow(j, []))}
            </ul>
          </section>
        )}

        {!isLoading && !isError && archived.length > 0 && (
          <details className="jv-journals__archived">
            <summary className="jv-journals__archived-summary">
              Archived ({archived.length})
            </summary>
            <ul className="jv-jlist">
              {archived.map((j) => renderRow(j, []))}
            </ul>
          </details>
        )}
      </div>

      <JournalFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        journal={formJournal}
        onSubmit={submitForm}
        submitting={create.isPending || update.isPending}
        failed={create.isError || update.isError}
      />
      {deleteTarget && (
        <DeleteJournalDialog
          open
          onOpenChange={(open) => !open && setDeleteTarget(null)}
          journal={deleteTarget}
          onConfirm={confirmDelete}
          onArchiveInstead={() => {
            setArchived.mutate({ id: deleteTarget.id, archived: true });
            setDeleteTarget(null);
          }}
          deleting={remove.isPending}
          failed={remove.isError}
        />
      )}
      <JournalSharingDialog
        journal={sharingJournal}
        open={sharingJournal !== null}
        onOpenChange={(open) => !open && setSharingJournal(null)}
      />
    </section>
  );
}
