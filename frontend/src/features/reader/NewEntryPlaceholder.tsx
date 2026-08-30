import { useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { Button } from "../../components/ui/button";

export function NewEntryPlaceholder() {
  const { journalId } = useParams({ strict: false }) as { journalId?: string };
  const {
    q = "",
    view,
    month,
    date,
  } = useSearch({ strict: false }) as {
    q?: string;
    view?: "calendar" | "media";
    month?: string;
    date?: string;
  };
  const navigate = useNavigate();
  const cancel = () => {
    if (journalId) {
      void navigate({
        to: "/journals/$journalId",
        params: { journalId },
        search: { q, ...(view ? { view, month, date } : {}) },
      });
    } else {
      void navigate({
        to: "/timeline",
        search: { q, ...(view ? { view, month, date } : {}) },
      });
    }
  };

  return (
    <div className="selected-view">
      <div className="reader-copy">
        <Button className="back-button" onClick={cancel}>
          <ArrowLeft aria-hidden="true" size={17} />
          Cancel
        </Button>
        <p className="eyebrow">Prototype route</p>
        <h1>New entry</h1>
        <p className="muted">
          The editor arrives in Phase C. This first-class route validates the
          browser and mobile navigation state without creating server data.
        </p>
        {journalId && (
          <p className="muted">The selected journal context is preserved.</p>
        )}
      </div>
    </div>
  );
}
