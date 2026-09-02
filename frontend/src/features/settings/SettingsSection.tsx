import type { ReactNode } from "react";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import {
  Field,
  FieldDescription,
  FieldLabel,
  FieldTitle,
} from "../../components/ui/field";
import { Item, ItemContent, ItemActions } from "../../components/ui/item";
import { cx } from "../../lib/cx";

/**
 * A titled group of settings, as a stock `Card` (DESIGN.md §5, §23). Settings
 * is application chrome, not reading content: a group of controls is a real
 * object and gets the standard Vega card — a raised `--card` panel on the
 * `--muted` settings canvas. The no-card rule applies to entries and the
 * reader, never here.
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
  /** A single header-level action (Add user, Add person). `CardAction` places
   *  it opposite the title without a hand-built heading row. */
  action?: ReactNode;
  /** The section's own actions. They belong to the card, not to the canvas. */
  footer?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card className="jv-settings-section">
      <CardHeader>
        <CardTitle>
          <h3 className="jv-settings-section__title" id={titleId}>
            {title}
          </h3>
        </CardTitle>
        {intro && <CardDescription>{intro}</CardDescription>}
        {action && <CardAction>{action}</CardAction>}
      </CardHeader>
      <CardContent>{children}</CardContent>
      {footer && (
        <CardFooter className="justify-end gap-3 border-t">{footer}</CardFooter>
      )}
    </Card>
  );
}

/**
 * One setting: a label and optional description on the left, its control on the
 * right (stacked below the row's own reflow width). A stock `Item` carrying a
 * `Field` — the label/description/control triple is exactly what `Field`
 * describes, and the row is exactly what `Item` describes.
 */
export function SettingsRow({
  label,
  htmlFor,
  description,
  children,
  className,
}: {
  label: ReactNode;
  /** When the control is a single labellable field, associate them. */
  htmlFor?: string;
  description?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Item
      size="sm"
      className={cx("jv-settings-row", className)}
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
