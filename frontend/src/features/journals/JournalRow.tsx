import { Link } from "@tanstack/react-router";
import {
  ArchiveRestore,
  ArrowDown,
  ArrowUp,
  Archive as ArchiveIcon,
  Palette,
  Pencil,
  Star,
  Trash2,
} from "lucide-react";
import type { JournalResponse } from "../../api/generated/types.gen";
import { JournalDot } from "../../components/journiv/JournalBadge";
import {
  AppAdaptiveMenu,
  type AppMenuAction,
} from "../../components/journiv/AppAdaptiveMenu";
import { IconButton } from "../../components/ui/icon-button";
import { formatDateMedium } from "../../lib/datetime";

const nf = new Intl.NumberFormat();

function countsLine(journal: JournalResponse): string {
  if (journal.entry_count <= 0) return "No entries yet";
  return [
    `${nf.format(journal.entry_count)} ${journal.entry_count === 1 ? "entry" : "entries"}`,
    `${nf.format(journal.total_words)} words`,
  ].join(" · ");
}

export function JournalRow({
  journal,
  search,
  canMoveUp,
  canMoveDown,
  onRename,
  onEditAppearance,
  onDelete,
  onToggleFavorite,
  onSetArchived,
  onMove,
}: {
  journal: JournalResponse;
  search: string;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onRename: (journal: JournalResponse) => void;
  onEditAppearance: (journal: JournalResponse) => void;
  onDelete: (journal: JournalResponse) => void;
  onToggleFavorite: (journal: JournalResponse) => void;
  onSetArchived: (id: string, archived: boolean) => void;
  onMove: (id: string, direction: "up" | "down") => void;
}) {
  const archived = journal.is_archived;
  const menuActions: AppMenuAction[] = [
    {
      kind: "command",
      id: "rename",
      label: "Rename",
      icon: Pencil,
      onSelect: () => onRename(journal),
    },
    {
      kind: "command",
      id: "appearance",
      label: "Edit appearance",
      icon: Palette,
      onSelect: () => onEditAppearance(journal),
    },
    // Ordering and archiving are meaningless for an already-archived journal.
    ...(archived
      ? []
      : ([
          {
            kind: "command",
            id: "move-up",
            label: "Move up",
            icon: ArrowUp,
            disabled: !canMoveUp,
            onSelect: () => onMove(journal.id, "up"),
          },
          {
            kind: "command",
            id: "move-down",
            label: "Move down",
            icon: ArrowDown,
            disabled: !canMoveDown,
            onSelect: () => onMove(journal.id, "down"),
          },
          {
            kind: "command",
            id: "archive",
            label: "Archive",
            icon: ArchiveIcon,
            onSelect: () => onSetArchived(journal.id, true),
          },
        ] satisfies AppMenuAction[])),
    {
      kind: "command",
      id: "delete",
      label: "Delete…",
      icon: Trash2,
      destructive: true,
      separatorBefore: true,
      onSelect: () => onDelete(journal),
    },
  ];

  return (
    <li className="jv-jrow">
      <Link
        to="/journals/$journalId"
        params={{ journalId: journal.id }}
        search={{ q: search }}
        className="jv-jrow__link"
      >
        <JournalDot journal={journal} size={16} className="jv-jrow__glyph" />
        <span className="jv-jrow__text">
          <span className="jv-jrow__title jv-truncate">{journal.title}</span>
          {journal.description && (
            <span className="jv-jrow__desc jv-truncate">
              {journal.description}
            </span>
          )}
          <span className="jv-jrow__stats jv-meta">
            <span className="jv-truncate">{countsLine(journal)}</span>
            {journal.last_entry_at && (
              <span className="jv-jrow__last jv-truncate">
                Last entry {formatDateMedium(journal.last_entry_at)}
              </span>
            )}
          </span>
        </span>
      </Link>

      <div className="jv-jrow__actions">
        {archived ? (
          <IconButton
            label={`Unarchive ${journal.title}`}
            onClick={() => onSetArchived(journal.id, false)}
          >
            <ArchiveRestore aria-hidden="true" size={16} />
          </IconButton>
        ) : (
          <IconButton
            label={
              journal.is_favorite
                ? `Remove ${journal.title} from favourites`
                : `Add ${journal.title} to favourites`
            }
            aria-pressed={journal.is_favorite}
            className={journal.is_favorite ? "is-active" : undefined}
            onClick={() => onToggleFavorite(journal)}
          >
            <Star
              aria-hidden="true"
              size={16}
              fill={journal.is_favorite ? "currentColor" : "none"}
            />
          </IconButton>
        )}

        <AppAdaptiveMenu
          label={`${journal.title} actions`}
          align="end"
          actions={menuActions}
        />
      </div>
    </li>
  );
}
