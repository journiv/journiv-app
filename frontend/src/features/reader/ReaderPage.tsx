import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { useRef, useState } from "react";
import {
  ArrowLeft,
  Download,
  Images,
  NotebookPen,
  Pencil,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { api } from "../../api/client/api";
import { entryQuery, momentQuery, promptQuery } from "../../api/query/options";
import { queryKeys } from "../../api/query/keys";
import { EntryHeader } from "../../components/journiv/EntryHeader";
import {
  AppAdaptiveMenu,
  type AppMenuAction,
} from "../../components/journiv/AppAdaptiveMenu";
import { JournalBadge } from "../../components/journiv/JournalBadge";
import { MomentChips } from "../../components/journiv/MomentChips";
import { PageBar } from "../../components/journiv/PageBar";
import { Button } from "../../components/ui/button";
import { IconButton } from "../../components/ui/icon-button";
import { Skeleton } from "../../components/ui/skeleton";
import { toast } from "../../components/ui/toast";
import { StatusView } from "../../components/journiv/StatusView";
import { useJournalLookup } from "../../lib/useJournalLookup";
import { momentKind, momentKindLabel, momentTitle } from "../../lib/moment";
import { EMPTY_DELTA } from "../editor/deltaProfile";
import { planReaderContent, QuillReader } from "../editor/QuillReader";
import { PromptBanner } from "../prompts/PromptBanner";
import { scopeSearchFrom } from "../timeline/momentScope";
import { DeleteEntryDialog } from "./DeleteEntryDialog";
import { EntryMedia } from "./EntryMedia";
import { useMomentMedia } from "./useMomentMedia";
import "./reader.css";

// One stable id so the pending toast can be resolved (closed) on settle rather
// than lingering next to the outcome.
const PDF_TOAST_ID = "reader-entry-pdf";

export function ReaderPage() {
  const { momentId, journalId } = useParams({ strict: false }) as {
    momentId: string;
    journalId?: string;
  };
  const search = useSearch({ strict: false }) as {
    q?: string;
    view?: "calendar" | "media";
    month?: string;
    date?: string;
    person?: string;
    tag?: string;
    activity?: string;
    mood?: string;
    goal?: string;
  };
  const { q = "", view, month, date } = search;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const isPdfRetryInFlight = useRef(false);
  // Carry the list-pane mode back so Back returns to the calendar or grid the
  // reader was opened from, not the plain list.
  const listSearch = {
    q,
    ...(view ? { view, month, date } : {}),
    ...scopeSearchFrom(search),
  };
  const journals = useJournalLookup();
  const moment = useQuery(momentQuery(momentId));
  const entry = useQuery({
    ...entryQuery(moment.data?.entry?.id ?? ""),
    enabled: Boolean(moment.data?.entry?.id),
  });
  // Prompt attribution is supplementary reading context: a missing or deleted
  // prompt never blocks the Moment itself from rendering.
  const prompt = useQuery({
    ...promptQuery(moment.data?.prompt_id ?? ""),
    enabled: Boolean(moment.data?.prompt_id),
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
  const remove = useMutation({
    mutationFn: async (entryId: string) => {
      await api.deleteEntry(entryId);

      queryClient.removeQueries({ queryKey: queryKeys.entry(entryId) });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.allMoments }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.allMomentCalendars,
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.allMediaLibraries,
        }),
        queryClient.invalidateQueries({ queryKey: queryKeys.journals }),
        queryClient.invalidateQueries({ queryKey: queryKeys.tags }),
        queryClient.invalidateQueries({ queryKey: queryKeys.insights }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.moment(momentId),
          refetchType: "none",
        }),
      ]);

      try {
        await queryClient.fetchQuery({
          ...momentQuery(momentId),
          retry: false,
          staleTime: 0,
        });
        return true;
      } catch {
        queryClient.removeQueries({ queryKey: queryKeys.moment(momentId) });
        return false;
      }
    },
    onSuccess: (momentSurvived) => {
      if (!momentSurvived) goBack();
    },
  });
  const download = useMutation({
    mutationFn: async (entryId: string) => {
      const { blob, filename } = await api.downloadEntryPdf(entryId);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename ?? "entry.pdf";
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    },
    onMutate: () => {
      // The action menu closes on select, so its disabled "Downloading PDF…"
      // item is not on screen while the PDF renders. A pending toast carries
      // that state instead; the browser's own download is the success signal,
      // so success just clears this toast.
      toast.add({
        id: PDF_TOAST_ID,
        type: "loading",
        description: "Preparing your PDF…",
        timeout: 0,
      });
    },
    onSuccess: () => {
      toast.close(PDF_TOAST_ID);
    },
    onSettled: () => {
      isPdfRetryInFlight.current = false;
    },
    onError: (_error, entryId) => {
      toast.close(PDF_TOAST_ID);
      toast.add({
        type: "error",
        priority: "high",
        description: "Couldn’t download PDF. Try again.",
        actionProps: {
          children: "Retry",
          onClick: () => {
            if (isPdfRetryInFlight.current) return;
            isPdfRetryInFlight.current = true;
            download.mutate(entryId);
          },
        },
      });
    },
  });

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
  const entryId = data.entry?.id;
  const kind = momentKind(data);
  const title = momentTitle(data);
  const journal = journals.get(data.entry?.journal_id ?? journalId);
  const hasWriting = Boolean(data.entry);
  const content = entry.data?.content_delta ?? EMPTY_DELTA;
  const entryActions: AppMenuAction[] = entryId
    ? [
        {
          kind: "command",
          id: "download-pdf",
          label: download.isPending ? "Downloading PDF…" : "Download PDF",
          icon: Download,
          disabled: download.isPending,
          onSelect: () => download.mutate(entryId),
        },
        {
          kind: "command",
          id: "delete-entry",
          label: "Delete entry…",
          icon: Trash2,
          destructive: true,
          separatorBefore: true,
          onSelect: () => {
            remove.reset();
            setDeleteOpen(true);
          },
        },
      ]
    : [];
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
          <>
            <Button
              variant={hasWriting ? "secondary" : "default"}
              onClick={edit}
            >
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
            {entryId && (
              <AppAdaptiveMenu label="Entry actions" actions={entryActions} />
            )}
          </>
        }
      />

      {entryId && (
        <DeleteEntryDialog
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          entryTitle={title}
          deleting={remove.isPending}
          failed={remove.isError}
          onConfirm={() => remove.mutate(entryId)}
        />
      )}

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

          {prompt.data && <PromptBanner text={prompt.data.text} readOnly />}

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
                  <Button variant="default" onClick={edit}>
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
