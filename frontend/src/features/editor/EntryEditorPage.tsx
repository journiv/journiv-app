import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useBlocker,
  useNavigate,
  useParams,
  useSearch,
} from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client/api";
import type {
  JournalResponse,
  MomentCreate,
  MomentResponse,
  MomentUpdate,
  QuillDelta,
} from "../../api/generated/types.gen";
import { queryKeys } from "../../api/query/keys";
import {
  entryQuery,
  journalsQuery,
  momentQuery,
} from "../../api/query/options";
import { Button } from "../../components/ui/button";
import { Skeleton } from "../../components/ui/skeleton";
import { EMPTY_DELTA, isQuillDocumentDelta } from "./deltaProfile";
import { EditorToolbar } from "./EditorToolbar";
import { QuillSurface, type QuillSurfaceHandle } from "./QuillSurface";
import { isExplicitSaveShortcut } from "./shortcuts";

export function EntryEditorPage() {
  const { momentId, journalId } = useParams({ strict: false }) as {
    momentId?: string;
    journalId?: string;
  };
  const moment = useQuery({
    ...momentQuery(momentId ?? ""),
    enabled: Boolean(momentId),
  });
  const entry = useQuery({
    ...entryQuery(moment.data?.entry?.id ?? ""),
    enabled: Boolean(moment.data?.entry?.id),
  });
  const journals = useQuery(journalsQuery());

  if (momentId && moment.isLoading) return <EditorSkeleton />;
  if (momentId && (moment.isError || !moment.data))
    return <EditorLoadError retry={() => moment.refetch()} />;
  if (moment.data?.entry && entry.isLoading) return <EditorSkeleton />;
  if (moment.data?.entry && (entry.isError || !entry.data))
    return <EditorLoadError retry={() => entry.refetch()} />;
  if (journals.isLoading) return <EditorSkeleton />;
  if (journals.isError || !journals.data)
    return <EditorLoadError retry={() => journals.refetch()} />;

  const initialContent = entry.data?.content_delta ?? EMPTY_DELTA;
  if (!isQuillDocumentDelta(initialContent)) {
    return (
      <UnsupportedEditor
        momentId={moment.data?.id ?? momentId ?? ""}
        routeJournalId={journalId}
      />
    );
  }

  return (
    <EntryEditorForm
      key={momentId ?? `new-${journalId ?? "timeline"}`}
      initialContent={initialContent}
      initialJournalId={entry.data?.journal_id ?? journalId ?? ""}
      initialTitle={entry.data?.title ?? ""}
      journals={journals.data}
      moment={moment.data}
      routeJournalId={journalId}
    />
  );
}

function EntryEditorForm({
  initialContent,
  initialJournalId,
  initialTitle,
  journals,
  moment,
  routeJournalId,
}: {
  initialContent: QuillDelta;
  initialJournalId: string;
  initialTitle: string;
  journals: JournalResponse[];
  moment?: MomentResponse;
  routeJournalId?: string;
}) {
  const { q = "" } = useSearch({ strict: false }) as { q?: string };
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const surfaceRef = useRef<QuillSurfaceHandle>(null);
  const allowNavigationRef = useRef(false);
  const [title, setTitle] = useState(initialTitle);
  const [journalId, setJournalId] = useState(initialJournalId);
  const [bodyDirty, setBodyDirty] = useState(false);
  const [error, setError] = useState("");
  const [editorState, setEditorState] = useState({
    formats: {} as Record<string, unknown>,
    focused: false,
    selectionLength: 0,
    wordCount: 0,
  });
  const titleDirty = title !== initialTitle;
  const journalDirty = journalId !== initialJournalId;
  const dirty = titleDirty || journalDirty || bodyDirty;
  const activeJournals = journals.filter((journal) => !journal.is_archived);
  const needsJournalSelector =
    !moment ||
    activeJournals.length > 1 ||
    !activeJournals.some((journal) => journal.id === initialJournalId);

  const shouldBlock = useCallback(
    () =>
      !allowNavigationRef.current &&
      dirty &&
      !window.confirm("Discard your unsaved changes?"),
    [dirty],
  );
  useBlocker({
    shouldBlockFn: shouldBlock,
    enableBeforeUnload: dirty,
    disabled: !dirty,
  });

  const mutation = useMutation({
    mutationFn: async () => {
      setError("");
      const contentDelta = surfaceRef.current?.getContents();
      if (!contentDelta) throw new Error("Editor is not ready");
      if (!journalId) throw new Error("Choose a Journal before saving");
      if (!activeJournals.some((journal) => journal.id === journalId))
        throw new Error("Choose an active Journal before saving");
      const entryPayload = {
        title: title.trim() || null,
        content_delta: contentDelta,
        journal_id: journalId,
      };
      if (!moment) {
        const body: MomentCreate = {
          entry: entryPayload,
          logged_at_utc: new Date().toISOString(),
          logged_timezone:
            Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
        };
        return api.createMoment(body);
      }
      const body: MomentUpdate = moment.entry
        ? { entry_update: entryPayload }
        : { entry_create: entryPayload };
      return api.updateMoment(moment.id, body);
    },
    onSuccess: async (savedMoment) => {
      allowNavigationRef.current = true;
      queryClient.setQueryData(queryKeys.moment(savedMoment.id), savedMoment);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.allMoments }),
        queryClient.invalidateQueries({ queryKey: queryKeys.journals }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.moment(savedMoment.id),
        }),
        ...(savedMoment.entry?.id
          ? [
              queryClient.invalidateQueries({
                queryKey: queryKeys.entry(savedMoment.entry.id),
              }),
            ]
          : []),
      ]);
      await goToReader(
        savedMoment.id,
        savedMoment.entry?.journal_id ?? journalId,
      );
    },
    onError: (caught) => {
      setError(
        caught instanceof Error && caught.message
          ? caught.message
          : "Entry could not be saved. Your text is still here; try again.",
      );
    },
  });

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (
        !isExplicitSaveShortcut(event) ||
        mutation.isPending ||
        surfaceRef.current?.isComposing()
      )
        return;
      event.preventDefault();
      mutation.mutate();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [mutation]);

  async function goToReader(momentId: string, savedJournalId?: string) {
    if (routeJournalId) {
      await navigate({
        to: "/journals/$journalId/$momentId",
        params: { journalId: savedJournalId ?? routeJournalId, momentId },
        search: { q },
      });
    } else {
      await navigate({
        to: "/timeline/$momentId",
        params: { momentId },
        search: { q },
      });
    }
  }

  const cancel = () => {
    if (dirty && !window.confirm("Discard your unsaved changes?")) return;
    allowNavigationRef.current = true;
    if (moment) void goToReader(moment.id);
    else if (routeJournalId)
      void navigate({
        to: "/journals/$journalId",
        params: { journalId: routeJournalId },
        search: { q },
      });
    else void navigate({ to: "/timeline", search: { q } });
  };

  return (
    <div className="selected-view editor-page">
      <header className="editor-header">
        <Button
          className="back-button"
          onClick={cancel}
          disabled={mutation.isPending}
        >
          <ArrowLeft aria-hidden="true" size={17} />
          Cancel
        </Button>
        <div className="editor-actions">
          <Button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Saving…" : error ? "Retry" : "Done"}
          </Button>
        </div>
      </header>
      <main className="editor-document">
        <p className="muted editor-draft-warning" role="note">
          No autosave or draft recovery yet. Press Done before leaving this
          page.
        </p>
        {needsJournalSelector && (
          <label className="editor-journal" htmlFor="entry-journal">
            Journal
            <select
              id="entry-journal"
              value={journalId}
              onChange={(event) => setJournalId(event.target.value)}
              disabled={mutation.isPending}
              required
            >
              <option value="">Choose a Journal</option>
              {activeJournals.map((journal) => (
                <option key={journal.id} value={journal.id}>
                  {journal.title}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="sr-only" htmlFor="entry-title">
          Entry title
        </label>
        <input
          className="editor-title"
          id="entry-title"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Untitled moment"
          disabled={mutation.isPending}
          maxLength={300}
        />
        <EditorToolbar
          editor={surfaceRef.current}
          state={editorState}
          disabled={mutation.isPending}
        />
        <QuillSurface
          ref={surfaceRef}
          editorId={moment?.entry?.id ?? moment?.id ?? "new-entry"}
          initialContent={initialContent}
          onUserChange={() => setBodyDirty(true)}
          onStateChange={setEditorState}
          placeholder="Write about this moment…"
          readOnly={mutation.isPending}
        />
        {error && (
          <p className="editor-error" role="alert">
            {error}
          </p>
        )}
      </main>
    </div>
  );
}

function EditorSkeleton() {
  return (
    <div
      className="selected-view reader-state"
      role="status"
      aria-label="Loading editor"
    >
      <Skeleton className="skeleton-title" />
      <Skeleton />
      <Skeleton />
    </div>
  );
}

function EditorLoadError({ retry }: { retry: () => unknown }) {
  return (
    <div className="selected-view reader-state" role="alert">
      <p>The editor could not be loaded.</p>
      <Button onClick={() => retry()}>Try again</Button>
    </div>
  );
}

function UnsupportedEditor({
  momentId,
  routeJournalId,
}: {
  momentId: string;
  routeJournalId?: string;
}) {
  const { q = "" } = useSearch({ strict: false }) as { q?: string };
  const navigate = useNavigate();
  const back = () => {
    if (routeJournalId) {
      void navigate({
        to: "/journals/$journalId/$momentId",
        params: { journalId: routeJournalId, momentId },
        search: { q },
      });
    } else {
      void navigate({
        to: "/timeline/$momentId",
        params: { momentId },
        search: { q },
      });
    }
  };

  return (
    <div className="selected-view reader-state" role="alert">
      <p>
        This entry contains formatting or media that this prototype cannot edit
        without data loss. Editing and saving are disabled.
      </p>
      <Button onClick={back}>Back without changes</Button>
    </div>
  );
}
