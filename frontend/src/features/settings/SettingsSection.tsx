import type { ReactNode } from "react";
import { cx } from "../../lib/cx";

/**
 * A titled group of settings. "Section title, then setting / description /
 * control" — not a card per setting (DESIGN.md §5, §23).
 */
export function SettingsSection({
  title,
  intro,
  divider = true,
  children,
}: {
  title: string;
  intro?: ReactNode;
  /** The hairline under the title. Off for a section that is only a notice. */
  divider?: boolean;
  children: ReactNode;
}) {
  return (
    <section className="jv-settings-section">
      <h3 className="jv-settings-section__title jv-section-title">{title}</h3>
      {intro && <p className="jv-settings-section__intro jv-body">{intro}</p>}
      {divider && !intro && <div className="jv-settings-section__divider" />}
      {children}
    </section>
  );
}

/**
 * One setting: a label and optional description on the left, its control on the
 * right (stacked below the breakpoint).
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
    <div className={cx("jv-settings-row", className)}>
      {htmlFor ? (
        <label className="jv-settings-row__label jv-label" htmlFor={htmlFor}>
          {label}
        </label>
      ) : (
        <p className="jv-settings-row__label jv-label">{label}</p>
      )}
      {description && (
        <p className="jv-settings-row__description jv-caption">{description}</p>
      )}
      <div className="jv-settings-row__control">{children}</div>
    </div>
  );
}
