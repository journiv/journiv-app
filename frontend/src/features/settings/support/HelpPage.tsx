import { ExternalLink } from "lucide-react";
import { SettingsSection } from "../SettingsSection";

export function HelpPage() {
  return (
    <div className="jv-settings__body">
      <SettingsSection
        title="Help & feedback"
        intro="Find guidance or report a problem to the Journiv project."
      >
        <ul className="jv-settings-link-list">
          <li>
            <a
              href="https://github.com/journiv/journiv-app"
              target="_blank"
              rel="noreferrer"
            >
              Journiv project <ExternalLink size={14} aria-hidden="true" />
            </a>
          </li>
          <li>
            <a
              href="https://github.com/journiv/journiv-app/issues"
              target="_blank"
              rel="noreferrer"
            >
              Report an issue <ExternalLink size={14} aria-hidden="true" />
            </a>
          </li>
        </ul>
      </SettingsSection>
    </div>
  );
}
