import { Menu } from "lucide-react";
import type { ReactNode } from "react";
import { PageBar } from "../../components/journiv/PageBar";
import { IconButton } from "../../components/ui/icon-button";
import { useShell } from "../shell/AppShell";
import "./library.css";

/**
 * The shared Library list shell (DESIGN.md §24). Every Library section — People,
 * Tags, Moods, Activities, Goals — is a wide workspace spanning the shell's two
 * content columns: a compact `PageBar` for navigation, a header carrying the
 * title and the surface's one primary action above the single scroll owner,
 * then the section's own content (search, grid, dialogs). Opening one item
 * pushes to `LibraryDetailView` on the same route area.
 */
export function LibraryWorkspace({
  title,
  intro,
  actions,
  children,
}: {
  title: string;
  intro?: string;
  /** The header's right-side cluster: the one primary plus any secondaries. */
  actions?: ReactNode;
  children: ReactNode;
}) {
  const shell = useShell();
  return (
    <main className="jv-library" aria-label={title}>
      <PageBar
        className="jv-page-bar--compact-only"
        leading={
          <IconButton label="Open navigation" onClick={shell.openNavigation}>
            <Menu aria-hidden="true" size={19} />
          </IconButton>
        }
        title={<span className="jv-label jv-truncate">{title}</span>}
      />
      <header className="jv-library__header">
        <div className="jv-library__headings">
          <h1 className="jv-display jv-library__heading">{title}</h1>
          {intro && <p className="jv-library__intro jv-body">{intro}</p>}
        </div>
        {actions && <div className="jv-library__actions">{actions}</div>}
      </header>
      <div className="jv-library__scroll">
        <div className="jv-library__body">{children}</div>
      </div>
    </main>
  );
}
