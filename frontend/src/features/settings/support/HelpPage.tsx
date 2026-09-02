import { ExternalLink } from "lucide-react";
import { SettingsSection } from "../SettingsSection";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemGroup,
  ItemSeparator,
  ItemTitle,
} from "../../../components/ui/item";

export function HelpPage() {
  return (
    <div className="jv-settings__body">
      <SettingsSection
        title="Help & feedback"
        intro="Find guidance or report a problem to the Journiv project."
      >
        <ItemGroup>
          <Item
            size="sm"
            render={
              <a
                href="https://github.com/journiv/journiv-app"
                target="_blank"
                rel="noreferrer"
              />
            }
          >
            <ItemContent>
              <ItemTitle>Journiv project</ItemTitle>
            </ItemContent>
            <ItemActions>
              <ExternalLink aria-hidden="true" />
            </ItemActions>
          </Item>
          <ItemSeparator />
          <Item
            size="sm"
            render={
              <a
                href="https://github.com/journiv/journiv-app/issues"
                target="_blank"
                rel="noreferrer"
              />
            }
          >
            <ItemContent>
              <ItemTitle>Report an issue</ItemTitle>
            </ItemContent>
            <ItemActions>
              <ExternalLink aria-hidden="true" />
            </ItemActions>
          </Item>
        </ItemGroup>
      </SettingsSection>
    </div>
  );
}
