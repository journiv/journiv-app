import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useBlocker,
  useNavigate,
  useParams,
  useSearch,
} from "@tanstack/react-router";
import { TriangleAlert } from "lucide-react";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
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
  mediaFormatsQuery,
  momentQuery,
} from "../../api/query/options";
import { EntryHeader } from "../../components/journiv/EntryHeader";
import { PageBar } from "../../components/journiv/PageBar";
import { Button } from "../../components/ui/button";
import { Skeleton } from "../../components/ui/skeleton";
import { StatusView } from "../../components/journiv/StatusView";
import {
  EMPTY_DELTA,
  INLINE_MEDIA_KINDS,
  isEditableDocumentDelta,
  JOURNIV_DELTA_FORMATS,
} from "./deltaProfile";
import { parseSupportedFormats } from "./mediaUpload";
import { UPLOAD_BLOT_NAME } from "./uploadPlaceholder";
import { useEntryDraft } from "./useEntryDraft";
import { useMediaAttachments } from "./useMediaAttachments";
import { EditorToolbar } from "./EditorToolbar";
import {
  type EditorState,
  QuillSurface,
  type QuillSurfaceHandle,
} from "./QuillSurface";
import { isExplicitSaveShortcut } from "./shortcuts";
import "./editor.css";

/**
 * What the editor can hold: Gate-1 text, inline media, and the client-only
 * upload placeholder. The placeholder is stripped by `getContents()`, so it can
 * never be saved.
 */
/**
 * Builds the picker filter from the backend's own list, so the frontend can
 * never accept something the server will reject — or hide something it allows.
 * Falls back to broad wildcards while the list is loading: a picker that opens
 * is better than one that filters everything out.
 */
export function acceptAttribute(value: unknown): string {
  const formats = parseSupportedFormats(value);
  const extensions = formats
    ? [...formats.images, ...formats.videos, ...formats.audio]
    : [];
  if (!extensions.length) return "image/*,video/*,audio/*";
  // Extensions plus wildcards: iOS offers a far better picker when the broad
  // types are present, while the extensions keep desktop dialogs precise.
  return [...extensions, "image/*", "video/*", "audio/*"].join(",");
}

export const EDITOR_FORMATS = [
  ...JOURNIV_DELTA_FORMATS,
  // Every media kind the guard admits must be here too, or Quill throws
  // "Unable to create <kind> blot" when it loads such a document.
  ...INLINE_MEDIA_KINDS,
  UPLOAD_BLOT_NAME,
] as const;

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
  const formats = useQuery(mediaFormatsQuery());

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
  if (!isEditableDocumentDelta(initialContent)) {
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
      acceptedMedia={formats.data}
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
  acceptedMedia,
  moment,
  routeJournalId,
}: {
  initialContent: QuillDelta;
  initialJournalId: string;
  initialTitle: string;
  journals: JournalResponse[];
  acceptedMedia?: unknown;
  moment?: MomentResponse;
  routeJournalId?: string;
}) {
  const { q = "" } = useSearch({ strict: false }) as { q?: string };
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const surfaceRef = useRef<QuillSurfaceHandle>(null);
  const titleRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Media uploaded during THIS session, so cancel can clean up only what it
  // introduced and never pre-existing Moment media.
  const sessionMediaRef = useRef<string[]>([]);
  const allowNavigationRef = useRef(false);
  // A new entry has no Moment yet; it will be logged now, in this timezone.
  const draftAtRef = useRef({
    utc: new Date().toISOString(),
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  });
  const draftLoggedAt = draftAtRef.current.utc;
  const draftTimezone = draftAtRef.current.timezone;
  const draft = useEntryDraft({
    moment,
    loggedAtUtc: draftLoggedAt,
    loggedTimezone: draftTimezone,
  });
  const [title, setTitle] = useState(initialTitle);
  const [journalId, setJournalId] = useState(initialJournalId);
  const [bodyDirty, setBodyDirty] = useState(false);
  const [error, setError] = useState("");
  const [editorState, setEditorState] = useState<EditorState>({
    formats: {},
    focused: false,
    selectionLength: 0,
    wordCount: 0,
    selectedMedia: null,
  });
  const titleDirty = title !== initialTitle;
  const journalDirty = journalId !== initialJournalId;
  const dirty = titleDirty || journalDirty || bodyDirty;
  const activeJournals = journals.filter((journal) => !journal.is_archived);
  const needsJournalSelector =
    !moment ||
    activeJournals.length > 1 ||
    !activeJournals.some((journal) => journal.id === initialJournalId);

  const media = useMediaAttachments({
    surfaceRef,
    ensureDraft: useCallback(async () => {
      if (!journalId) {
        setError("Choose a Journal before adding media");
        return null;
      }
      try {
        return await draft.ensure(journalId);
      } catch {
        setError("Could not prepare this entry for media. Try again.");
        return null;
      }
    }, [draft, journalId]),
    onDirty: () => setBodyDirty(true),
    onMediaAdded: (mediaId) => sessionMediaRef.current.push(mediaId),
  });

  const openMediaPicker = useCallback(() => {
    setError("");
    fileInputRef.current?.click();
  }, []);

  /**
   * Removes the media under the cursor from the writing. The file is not
   * deleted here: the backend removes media a save dropped from the document
   * (`delete_orphaned_media_for_delta`), so until Done this is undoable.
   */
  const removeSelectedMedia = useCallback(() => {
    if (surfaceRef.current?.removeSelectedMedia()) setBodyDirty(true);
  }, []);

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

  // The title textarea grows with its content so long titles never clip.
  const resizeTitle = useCallback(() => {
    const node = titleRef.current;
    if (!node) return;
    node.style.height = "auto";
    node.style.height = `${node.scrollHeight}px`;
  }, []);
  useLayoutEffect(resizeTitle, [resizeTitle]);

  const mutation = useMutation({
    mutationFn: async () => {
      setError("");
      const contentDelta = surfaceRef.current?.getContents();
      if (!contentDelta) throw new Error("Editor is not ready");
      if (!journalId) throw new Error("Choose a Journal before saving");
      if (!activeJournals.some((journal) => journal.id === journalId))
        throw new Error("Choose an active Journal before saving");
      if (media.pending > 0)
        throw new Error("Wait for uploads to finish before saving");
      const entryPayload = {
        title: title.trim() || null,
        content_delta: contentDelta,
        journal_id: journalId,
      };
      if (!moment && !draft.draft) {
        const body: MomentCreate = {
          entry: entryPayload,
          logged_at_utc: draftLoggedAt,
          logged_timezone: draftTimezone,
        };
        return api.createMoment(body);
      }
      // A draft Moment was created to own uploaded media. Finalise through it,
      // clearing `is_draft` so the entry leaves the drafts pile and appears in
      // the Timeline.
      const targetId = moment?.id ?? draft.draft?.momentId ?? "";
      const hasEntry = Boolean(moment?.entry ?? draft.draft?.entryId);
      const body: MomentUpdate = hasEntry
        ? { entry_update: { ...entryPayload, is_draft: false } }
        : { entry_create: entryPayload };
      return api.updateMoment(targetId, body);
    },
    onSuccess: async (savedMoment) => {
      allowNavigationRef.current = true;
      // The draft is now a real entry; cancel must not delete it.
      draft.adopt();
      sessionMediaRef.current = [];
      // The backend deletes media this save removed from the document, so undo
      // must not be able to restore a reference to a file that is now gone.
      surfaceRef.current?.clearHistory();
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
    const keptMedia = sessionMediaRef.current.length;
    const question = keptMedia
      ? `Discard your unsaved changes? The ${keptMedia === 1 ? "file" : `${keptMedia} files`} you added will stay on this moment.`
      : "Discard your unsaved changes?";
    if (dirty && !window.confirm(question)) return;
    allowNavigationRef.current = true;
    // Abort anything still uploading before leaving.
    for (const item of media.attachments) media.cancel(item.uploadId);
    // A draft created for this session is cleaned up. Media the user actually
    // attached is KEPT: the Moment survives as a media-only Moment rather than
    // silently deleting photographs someone just took.
    void draft.discard(sessionMediaRef.current.length > 0);
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
    <div className="jv-editor">
      {/* One Cancel control at every width. Two controls with the same
          accessible name — even if one is display:none — is a trap. */}
      <PageBar
        title={
          needsJournalSelector ? (
            <label
              className="jv-editor__journal jv-meta"
              htmlFor="entry-journal"
            >
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
          ) : (
            <span className="jv-editor__status">
              {mutation.isPending
                ? "Saving…"
                : dirty
                  ? "Unsaved changes"
                  : "No changes"}
            </span>
          )
        }
        actions={
          <>
            {needsJournalSelector && (
              <span className="jv-editor__status jv-desktop-only">
                {mutation.isPending
                  ? "Saving…"
                  : dirty
                    ? "Unsaved changes"
                    : "No changes"}
              </span>
            )}
            <Button
              variant="ghost"
              onClick={cancel}
              disabled={mutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending}
            >
              {mutation.isPending ? "Saving…" : error ? "Retry" : "Done"}
            </Button>
          </>
        }
      />

      <div className="jv-editor__scroll">
        <div className="jv-editor__column">
          <EntryHeader
            loggedAtUtc={moment?.logged_at_utc ?? draftLoggedAt}
            loggedTimezone={moment?.logged_timezone ?? draftTimezone}
            moment={moment}
            journal={activeJournals.find((item) => item.id === journalId)}
            title={
              <>
                <label className="sr-only" htmlFor="entry-title">
                  Entry title
                </label>
                <textarea
                  className="jv-editor__title jv-entry-title"
                  id="entry-title"
                  ref={titleRef}
                  rows={1}
                  value={title}
                  onChange={(event) => {
                    setTitle(event.target.value);
                    resizeTitle();
                  }}
                  placeholder="Give this a title (optional)"
                  disabled={mutation.isPending}
                  maxLength={300}
                />
              </>
            }
          />

          <p className="jv-caption jv-editor__notice" role="note">
            Journiv does not autosave yet — press Done before leaving this page.
          </p>

          <EditorToolbar
            editor={surfaceRef.current}
            state={editorState}
            disabled={mutation.isPending}
            onAddMedia={openMediaPicker}
            onRemoveMedia={removeSelectedMedia}
          />
          <input
            ref={fileInputRef}
            className="sr-only"
            type="file"
            accept={acceptAttribute(acceptedMedia)}
            multiple
            tabIndex={-1}
            aria-hidden="true"
            onChange={(event) => {
              const files = [...(event.target.files ?? [])];
              // Reset so choosing the same file twice still fires a change.
              event.target.value = "";
              if (files.length) void media.attach(files);
            }}
          />
          {(media.error || media.failed.length > 0) && (
            <div className="jv-editor__upload-errors" role="alert">
              {media.error && (
                <p className="jv-editor__upload-error">{media.error}</p>
              )}
              {media.failed.map((item) => (
                <p key={item.uploadId} className="jv-editor__upload-error">
                  <span>{item.message}</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => media.retry(item.uploadId)}
                  >
                    Retry
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => media.cancel(item.uploadId)}
                  >
                    Remove
                  </Button>
                </p>
              ))}
            </div>
          )}
          <QuillSurface
            ref={surfaceRef}
            editorId={moment?.entry?.id ?? moment?.id ?? "new-entry"}
            initialContent={initialContent}
            formats={EDITOR_FORMATS}
            onUserChange={() => setBodyDirty(true)}
            onStateChange={setEditorState}
            placeholder="Write about this moment…"
            readOnly={mutation.isPending}
          />
          {error && (
            <p className="jv-editor__error" role="alert">
              {error}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function EditorSkeleton() {
  return (
    <div className="jv-editor" role="status" aria-label="Loading editor">
      <PageBar title={<Skeleton height="0.9rem" width="6rem" />} />
      <div className="jv-editor__scroll">
        <div className="jv-editor__column">
          <div className="jv-entry-header">
            <Skeleton height="0.8rem" width="13rem" />
            <Skeleton height="2.2rem" width="68%" />
          </div>
          <Skeleton height="1.05rem" width="100%" />
        </div>
      </div>
    </div>
  );
}

function EditorLoadError({ retry }: { retry: () => unknown }) {
  return (
    <div className="jv-pane-status">
      <StatusView
        role="alert"
        tone="danger"
        icon={<TriangleAlert size={20} />}
        title="The editor could not be loaded"
        action={
          <Button variant="secondary" onClick={() => retry()}>
            Try again
          </Button>
        }
      />
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
    <div className="jv-pane-status">
      <StatusView
        role="alert"
        icon={<TriangleAlert size={20} />}
        title="This entry cannot be edited here yet"
        description="It contains formatting or media this prototype cannot edit without losing data, so editing and saving are disabled."
        action={
          <Button variant="secondary" onClick={back}>
            Back without changes
          </Button>
        }
      />
    </div>
  );
}
