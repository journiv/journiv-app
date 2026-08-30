import { ChevronLeft, Pencil, Plus, Trash2 } from "lucide-react";
import { type CSSProperties, useId, useState } from "react";
import { EntityGlyph } from "../../components/journiv/EntityGlyph";
import { Button } from "../../components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";
import { IconButton } from "../../components/ui/icon-button";
import { Input } from "../../components/ui/input";
import {
  argbFromHex,
  colorFromArgb,
  ENTITY_COLOR_PRESETS,
} from "../../lib/color";
import { JOURNAL_ICONS } from "../../lib/journalIcons";

/** The subset of any Library group response this dialog needs. People,
 *  Activities, Goals and Moods all pass a shape wider than this. */
export type LibraryGroup = {
  id: string;
  name: string;
  color_value?: number | null;
  icon?: string | null;
};

/** The appearance-only body every Library group create/update accepts. */
export type LibraryGroupCreateInput = {
  name: string;
  color_value: number | null;
  icon: string | null;
};

type View =
  | { kind: "list" }
  | { kind: "form"; group?: LibraryGroup }
  | { kind: "delete"; group: LibraryGroup };

function countLabel(count: number, singular: string, plural: string) {
  return `${count} ${count === 1 ? singular : plural}`;
}

/**
 * One dialog, three views: the group list (rename / recolour / delete each,
 * plus New group), the appearance form, and a delete confirmation. Views swap
 * in place — no stacked large modals (DESIGN.md §22). Entity assignment is not
 * edited here: People owns many-to-many membership on each person, while an
 * Activity / Goal / Mood chooses its single optional group in its own form.
 */
export function GroupsManagerDialog({
  groups,
  initialGroup,
  busy,
  saveFailed,
  deleteFailed,
  onClose,
  onCreate,
  onUpdate,
  onDelete,
  itemNoun = { singular: "person", plural: "people" },
  itemCount = (group) =>
    ((group as LibraryGroup & { people?: unknown[] }).people ?? []).length,
}: {
  groups: LibraryGroup[];
  initialGroup?: LibraryGroup;
  busy: boolean;
  saveFailed: boolean;
  deleteFailed: boolean;
  onClose: () => void;
  onCreate: (body: LibraryGroupCreateInput) => Promise<void>;
  onUpdate: (id: string, body: LibraryGroupCreateInput) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  itemNoun?: { singular: string; plural: string };
  itemCount?: (group: LibraryGroup) => number;
}) {
  const [view, setView] = useState<View>(
    initialGroup ? { kind: "form", group: initialGroup } : { kind: "list" },
  );
  const { plural } = itemNoun;
  const pluralCap = `${plural[0].toUpperCase()}${plural.slice(1)}`;

  if (view.kind === "form") {
    return (
      <GroupForm
        group={view.group}
        busy={busy}
        failed={saveFailed}
        itemPlural={plural}
        onCancel={() => setView({ kind: "list" })}
        onClose={onClose}
        onSubmit={async (body) => {
          try {
            if (view.group) await onUpdate(view.group.id, body);
            else await onCreate(body);
            setView({ kind: "list" });
          } catch {
            // Mutation state owns the on-screen failure. Stay on the form so
            // the user's name, colour and icon selections survive.
          }
        }}
      />
    );
  }

  if (view.kind === "delete") {
    const group = view.group;
    return (
      <Dialog open onOpenChange={(open) => !open && onClose()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{`Delete ${group.name}?`}</DialogTitle>
            <DialogDescription>
              {`${pluralCap} stay in your Library and are removed only from this group.`}
            </DialogDescription>
          </DialogHeader>
          {deleteFailed && (
            <p className="jv-library__alert" role="alert">
              The group could not be deleted. Try again.
            </p>
          )}
          <div className="jv-dialog__actions">
            <Button variant="ghost" onClick={() => setView({ kind: "list" })}>
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={busy}
              onClick={async () => {
                try {
                  await onDelete(group.id);
                  setView({ kind: "list" });
                } catch {
                  // Keep the confirmation visible with its failure message.
                }
              }}
            >
              {busy ? "Deleting…" : "Delete group"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Manage groups</DialogTitle>
          <DialogDescription>
            {`Rename, recolour or remove a group. Deleting a group never removes its ${plural}.`}
          </DialogDescription>
        </DialogHeader>
        <div className="jv-groups-manager">
          {groups.length ? (
            <ul className="jv-groups-manager__list">
              {groups.map((group) => (
                <li key={group.id} className="jv-groups-manager__row">
                  <EntityGlyph
                    colorValue={group.color_value}
                    icon={group.icon}
                    size={13}
                  />
                  <span className="jv-groups-manager__name jv-truncate">
                    {group.name}
                  </span>
                  <span className="jv-groups-manager__count">
                    {countLabel(
                      itemCount(group),
                      itemNoun.singular,
                      itemNoun.plural,
                    )}
                  </span>
                  <span className="jv-groups-manager__row-actions">
                    <IconButton
                      label={`Edit ${group.name}`}
                      onClick={() => setView({ kind: "form", group })}
                    >
                      <Pencil aria-hidden="true" size={15} />
                    </IconButton>
                    <IconButton
                      label={`Delete ${group.name}`}
                      onClick={() => setView({ kind: "delete", group })}
                    >
                      <Trash2 aria-hidden="true" size={15} />
                    </IconButton>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="jv-groups-manager__empty">
              {`No groups yet. Create one to organise your ${plural}.`}
            </p>
          )}
          <Button
            variant="ghost"
            className="jv-groups-manager__add"
            onClick={() => setView({ kind: "form" })}
          >
            <Plus aria-hidden="true" size={16} />
            New group
          </Button>
        </div>
        <div className="jv-dialog__actions">
          <DialogClose render={<Button variant="secondary">Done</Button>} />
        </div>
      </DialogContent>
    </Dialog>
  );
}

function GroupForm({
  group,
  busy,
  failed,
  itemPlural,
  onCancel,
  onClose,
  onSubmit,
}: {
  group?: LibraryGroup;
  busy: boolean;
  failed: boolean;
  itemPlural: string;
  onCancel: () => void;
  onClose: () => void;
  onSubmit: (body: LibraryGroupCreateInput) => Promise<void>;
}) {
  const editing = Boolean(group);
  const nameId = useId();
  const colorName = useId();
  const iconName = useId();
  const initialColor = colorFromArgb(group?.color_value) ?? "";
  const [name, setName] = useState(group?.name ?? "");
  const [colorHex, setColorHex] = useState(initialColor);
  const [icon, setIcon] = useState(group?.icon ?? "");
  const trimmed = name.trim();
  const dirty = group
    ? trimmed !== group.name ||
      colorHex !== initialColor ||
      icon !== (group.icon ?? "")
    : Boolean(trimmed);
  const tint = (hex: string): CSSProperties =>
    ({ "--entity-accent": hex }) as CSSProperties;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {editing ? `Edit ${group?.name}` : "New group"}
          </DialogTitle>
          <DialogDescription>
            {`A group is a way to file the ${itemPlural} in your journal together.`}
          </DialogDescription>
        </DialogHeader>
        <Button
          variant="ghost"
          className="jv-groups-manager__back"
          onClick={onCancel}
        >
          <ChevronLeft aria-hidden="true" size={16} />
          All groups
        </Button>
        <form
          className="jv-library-form"
          onSubmit={async (event) => {
            event.preventDefault();
            if (!trimmed || busy) return;
            await onSubmit({
              name: trimmed,
              color_value: colorHex ? argbFromHex(colorHex) : null,
              icon: icon || null,
            });
          }}
        >
          <label htmlFor={nameId}>
            <span>Group name</span>
            <Input
              id={nameId}
              aria-label="Group name"
              value={name}
              maxLength={100}
              autoFocus
              onChange={(event) => setName(event.target.value)}
            />
          </label>

          <fieldset className="jv-groups-form__group">
            <legend>Colour</legend>
            <div className="jv-groups-form__swatches">
              <label className="jv-groups-form__swatch jv-groups-form__swatch--none">
                <input
                  type="radio"
                  name={colorName}
                  className="sr-only"
                  checked={!colorHex}
                  onChange={() => setColorHex("")}
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
                    checked={
                      colorHex.toLowerCase() === preset.hex.toLowerCase()
                    }
                    onChange={() => setColorHex(preset.hex)}
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
                  style={colorHex ? tint(colorHex) : undefined}
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
              The group could not be saved. Your changes are still here.
            </p>
          )}
          <div className="jv-dialog__actions">
            <Button variant="ghost" type="button" onClick={onCancel}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={!trimmed || !dirty || busy}
            >
              {busy ? "Saving…" : editing ? "Save" : "Create group"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
