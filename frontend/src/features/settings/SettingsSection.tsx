import type { ReactNode } from "react";
import {
  Field,
  FieldDescription,
  FieldLabel,
  FieldTitle,
} from "../../components/ui/field";
import { Item, ItemContent, ItemActions } from "../../components/ui/item";
import { cx } from "../../lib/cx";

/**
 * A titled group of settings on the shared Settings surface
 * (DESIGN.md "Settings and management surfaces", docs/features/settings.md).
 *
 * Settings is application chrome, but it is not a dashboard: a section is a
 * heading, an optional one-line intro, and its controls sitting directly on
 * the pane. Grouping is carried by the heading, the vertical rhythm, and a
 * hairline between adjacent sections — not by a raised card. Do not wrap a
 * section in `Card`; do not add a per-section surface, shadow, or radius.
 */
export function SettingsSection({
  title,
  titleId,
  intro,
  action,
  footer,
  children,
}: {
  title: string;
  /** Set when a caller labels its own region with the section heading. */
  titleId?: string;
  intro?: ReactNode;
  /** A single header-level action (Add user, Add person), placed opposite the
   *  title. This is a section action, not the page's primary Save — that lives
   *  in the modal action bar via `useSettingsForm` (SettingsModal). */
  action?: ReactNode;
  /** The section's own settled actions (Connect, Start import, Register…).
   *  Rendered in a hairline-topped row under the section. Not for the page's
   *  primary Save. */
  footer?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="jv-settings-section">
      <div className="jv-settings-section__head">
        <div className="jv-settings-section__heading">
          <h3 className="jv-settings-section__title" id={titleId}>
            {title}
          </h3>
          {intro && <p className="jv-settings-section__intro">{intro}</p>}
        </div>
        {action && <div className="jv-settings-section__action">{action}</div>}
      </div>
      <div className="jv-settings-section__body">{children}</div>
      {footer && <div className="jv-settings-section__footer">{footer}</div>}
    </section>
  );
}

/**
 * One setting. The label and optional help stack above the control by default
 * (DESIGN.md "Settings rows") — the control is left-anchored and bounded, never
 * pinned to the far edge. Pass `inline` for a compact control (a Switch, a
 * short segmented toggle) that reads better beside its label than beneath it.
 *
 * A stock `Item` carrying a `Field`: the label/help/control triple is what
 * `Field` describes, the row is what `Item` describes.
 */
export function SettingsRow({
  label,
  htmlFor,
  description,
  inline = false,
  children,
  className,
}: {
  label: ReactNode;
  /** When the control is a single labellable field, associate them. */
  htmlFor?: string;
  description?: ReactNode;
  /** Label left, control right, vertically centred. For toggles and short
   *  segmented controls only — inputs, selects and comboboxes stay stacked. */
  inline?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Item
      size="sm"
      className={cx(
        "jv-settings-row",
        inline && "jv-settings-row--inline",
        className,
      )}
      render={<div />}
    >
      <ItemContent className="min-w-0">
        <Field>
          {htmlFor ? (
            <FieldLabel htmlFor={htmlFor}>{label}</FieldLabel>
          ) : (
            <FieldTitle>{label}</FieldTitle>
          )}
          {description && <FieldDescription>{description}</FieldDescription>}
        </Field>
      </ItemContent>
      <ItemActions className="jv-settings-row__control">{children}</ItemActions>
    </Item>
  );
}
