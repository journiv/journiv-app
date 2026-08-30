import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams, useSearch } from "@tanstack/react-router";
import {
  ArrowLeft,
  Images,
  NotebookPen,
  Pencil,
  TriangleAlert,
} from "lucide-react";
import { entryQuery, momentQuery } from "../../api/query/options";
import { EntryHeader } from "../../components/journiv/EntryHeader";
import { JournalBadge } from "../../components/journiv/JournalBadge";
import { MomentChips } from "../../components/journiv/MomentChips";
import { PageBar } from "../../components/journiv/PageBar";
import { Button } from "../../components/ui/button";
import { IconButton } from "../../components/ui/icon-button";
import { Skeleton } from "../../components/ui/skeleton";
import { StatusView } from "../../components/journiv/StatusView";
import { useJournalLookup } from "../../lib/useJournalLookup";
import { momentKind, momentKindLabel, momentTitle } from "../../lib/moment";
import { EMPTY_DELTA } from "../editor/deltaProfile";
import { planReaderContent, QuillReader } from "../editor/QuillReader";
import { EntryMedia } from "./EntryMedia";
import { useMomentMedia } from "./useMomentMedia";
import "./reader.css";

export function ReaderPage() {
  const { momentId, journalId } = useParams({ strict: false }) as {
    momentId: string;
    journalId?: string;
  };
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
  // Carry the list-pane mode back so Back returns to the calendar or grid the
  // reader was opened from, not the plain list.
  const listSearch = { q, ...(view ? { view, month, date } : {}) };
  const journals = useJournalLookup();
  const moment = useQuery(momentQuery(momentId));
  const entry = useQuery({
    ...entryQuery(moment.data?.entry?.id ?? ""),
    enabled: Boolean(moment.data?.entry?.id),
  });
  // One media query for the whole reader: the prose resolves inline embeds from
  // it, and the gallery renders whatever is left over.
  const media = useMomentMedia(momentId, (moment.data?.media_count ?? 0) > 0);

  const goBack = () => {
    if (journalId) {
      void navigate({
        to: "/journals/$journalId",
        params: { journalId },
        search: listSearch,
      });
    } else {
      void navigate({ to: "/timeline", search: listSearch });
    }
  };
  const edit = () => {
    if (journalId) {
      void navigate({
        to: "/journals/$journalId/$momentId/edit",
        params: { journalId, momentId },
        search: { q },
      });
    } else {
      void navigate({
        to: "/timeline/$momentId/edit",
        params: { momentId },
        search: { q },
      });
    }
  };

  if (moment.isLoading) return <ReaderSkeleton />;
  if (moment.isError || !moment.data) {
    return (
      <div className="jv-pane-status">
        <StatusView
          role="alert"
          tone="danger"
          icon={<TriangleAlert size={20} />}
          title="Moment not found"
          description="It may have been deleted, or the link may be out of date."
          action={
            <>
              <Button variant="secondary" onClick={goBack}>
                Back to timeline
              </Button>
              <Button variant="ghost" onClick={() => moment.refetch()}>
                Try again
              </Button>
            </>
          }
        />
      </div>
    );
  }

  const data = moment.data;
  const kind = momentKind(data);
  const title = momentTitle(data);
  const journal = journals.get(data.entry?.journal_id ?? journalId);
  const hasWriting = Boolean(data.entry);
  const content = entry.data?.content_delta ?? EMPTY_DELTA;
  // Media shown inside the prose must not be repeated in the gallery.
  const inlinePaths = hasWriting
    ? planReaderContent(content).inlinePaths
    : undefined;

  return (
    <article className="jv-reader">
      <PageBar
        leading={
          <IconButton label="Back" onClick={goBack}>
            <ArrowLeft aria-hidden="true" size={19} />
          </IconButton>
        }
        title={<JournalBadge journal={journal} />}
        actions={
          <Button variant={hasWriting ? "secondary" : "primary"} onClick={edit}>
            {hasWriting ? (
              <>
                <Pencil aria-hidden="true" size={15} />
                Edit
              </>
            ) : (
              <>
                <NotebookPen aria-hidden="true" size={15} />
                Write
              </>
            )}
          </Button>
        }
      />

      <div className="jv-reader__scroll">
        <div className="jv-reader__column">
          <EntryHeader
            loggedAtUtc={data.logged_at_utc}
            loggedTimezone={data.logged_timezone}
            moment={data}
            journal={journal}
            kindLabel={momentKindLabel(data, kind)}
            title={
              title ? <h1 className="jv-entry-title">{title}</h1> : undefined
            }
          />

          <EntryMedia moment={data} media={media} excludePaths={inlinePaths} />

          {hasWriting && entry.isLoading && <ReaderBodySkeleton />}
          {hasWriting && entry.isError && (
            <StatusView
              role="alert"
              tone="danger"
              icon={<TriangleAlert size={20} />}
              title="Entry content could not be loaded"
              action={
                <Button variant="secondary" onClick={() => entry.refetch()}>
                  Try again
                </Button>
              }
            />
          )}
          {hasWriting && !entry.isLoading && !entry.isError && (
            <QuillReader
              content={content}
              entryId={data.entry?.id ?? momentId}
              plainText={entry.data?.content_plain_text}
              // Inline sources are signed URLs inside the document, so a stale
              // signature is recovered by refetching the entry.
              onMediaError={() => void entry.refetch()}
            />
          )}

          {kind === "note-only" && (
            <div className="jv-reader__note">
              <p className="jv-prose jv-prose-compact">{data.note}</p>
            </div>
          )}

          {!hasWriting && (
            <div className="jv-reader__invitation">
              <StatusView
                icon={
                  kind === "media-only" ? (
                    <Images size={20} />
                  ) : (
                    <NotebookPen size={20} />
                  )
                }
                title={
                  kind === "note-only"
                    ? "This moment is a note"
                    : kind === "media-only"
                      ? "This moment has photos but no writing"
                      : "Nothing written yet"
                }
                description="Add an entry whenever you are ready."
                action={
                  <Button variant="primary" onClick={edit}>
                    Write about this moment
                  </Button>
                }
              />
            </div>
          )}

          <MomentChips moment={data} scopeLinks />
        </div>
      </div>
    </article>
  );
}

function ReaderSkeleton() {
  return (
    <div className="jv-reader" role="status" aria-label="Loading moment">
      <PageBar title={<Skeleton height="0.9rem" width="6rem" />} />
      <div className="jv-reader__scroll">
        <div className="jv-reader__column">
          <div className="jv-entry-header">
            <Skeleton height="0.8rem" width="14rem" />
            <Skeleton height="2.2rem" width="72%" />
            <Skeleton height="0.8rem" width="40%" />
          </div>
          <ReaderBodySkeleton />
        </div>
      </div>
    </div>
  );
}

function ReaderBodySkeleton() {
  return (
    <div className="jv-reader__body-skeleton" aria-hidden="true">
      <Skeleton height="1.05rem" width="100%" />
      <Skeleton height="1.05rem" width="97%" />
      <Skeleton height="1.05rem" width="88%" />
      <Skeleton height="1.05rem" width="45%" />
    </div>
  );
}
