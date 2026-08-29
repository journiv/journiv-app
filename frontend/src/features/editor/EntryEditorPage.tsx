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
  currentUserQuery,
  entryQuery,
  journalsQuery,
  mediaFormatsQuery,
  momentQuery,
} from "../../api/query/options";
import { defaultJournalId } from "../../lib/journalOrder";
import { uuid } from "../../lib/uuid";
import { EntryHeader } from "../../components/journiv/EntryHeader";
import { MomentChips } from "../../components/journiv/MomentChips";
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
import {
  DraftMediaUnreachable,
  DraftRecoveryPrompt,
  LocalDraftStatus,
} from "./DraftRecovery";
import { draftKeyFor } from "./draftRepository";
import { parseSupportedFormats } from "./mediaUpload";
import { UPLOAD_BLOT_NAME } from "./uploadPlaceholder";
import { useDraftRecovery } from "./useDraftRecovery";
import { type DraftIdentity, useEntryDraft } from "./useEntryDraft";
import { useLocalDraft } from "./useLocalDraft";
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

/**
 * Leaving the editor with writing that never reached the server.
 *
 * The old wording — "Discard your unsaved changes?" — is no longer true: the
 * writing is kept on this device and offered back next time. Say so, so nobody
 * abandons work they think is about to vanish. (This is the in-app prompt only;
 * the browser writes its own text for a reload or a closed tab.)
 */
const LEAVE_CONFIRMATION =
  "Leave without saving to your journal? Your writing is kept on this device.";

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
  const { draft: draftParam, q = "" } = useSearch({ strict: false }) as {
    draft?: string;
    q?: string;
  };
  const navigate = useNavigate();
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
  // Drafts are scoped to the signed-in account. Without an id there is nothing
  // safe to key a record on, so nothing is stored at all.
  const currentUser = useQuery(currentUserQuery());

  /**
   * The id a NEW entry's draft is filed under, held steady for this editing
   * session and carried in `?draft=` so a reload finds the same record. An
   * existing entry keys on its own id and needs none of this.
   */
  const localDraftIdRef = useRef(draftParam ?? uuid());
  const localDraftId = momentId ? undefined : localDraftIdRef.current;

  const draftKey = draftKeyFor({
    userId: currentUser.data?.id,
    entryId: moment.data?.entry?.id,
    momentId,
    localDraftId,
  });

  const serverContent = entry.data?.content_delta ?? undefined;
  const recovery = useDraftRecovery({
    key: draftKey,
    momentId,
    serverContent,
    serverTitle: entry.data?.title ?? "",
    serverJournalId: entry.data?.journal_id,
    serverUpdatedAt: entry.data?.updated_at,
    serverLoaded: !momentId || Boolean(moment.data),
    // A document the editor cannot represent is never opened, so it can never
    // have produced a draft either.
    enabled: !serverContent || isEditableDocumentDelta(serverContent),
  });

  /** Which document the editor will open with, once the reader has chosen. */
  const [choice, setChoice] = useState<"server" | "draft" | null>(null);

  /**
   * Puts the local draft id in the URL, once something has actually been
   * stored. Replace, not push: recovering a draft is not a step in the reader's
   * history. The blocker ignores this navigation (see `shouldBlock`).
   */
  const rememberDraftInUrl = useCallback(() => {
    if (!localDraftId || draftParam === localDraftId) return;
    // Named routes, because only the two "new" routes carry `draft` in their
    // search schema — the type system enforces that the parameter cannot be
    // pushed onto a route that would silently drop it.
    void (journalId
      ? navigate({
          to: "/journals/$journalId/new",
          params: { journalId },
          search: { q, draft: localDraftId },
          replace: true,
        })
      : navigate({
          to: "/timeline/new",
          search: { q, draft: localDraftId },
          replace: true,
        }));
  }, [draftParam, journalId, localDraftId, navigate, q]);

  /**
   * Once the editor is open it stays open.
   *
   * The draft decision resolves asynchronously — the signed-in user, the local
   * record, the Moment's media — and any of those settling later must not
   * replace a mounted editor with a gate. That would tear down `QuillSurface`
   * and take the reader's typing with it.
   */
  const opened = useRef(false);

  // Drafts are scoped to the signed-in user, so the decision cannot even be
  // framed until that id is known. Waiting here costs a moment; deciding twice
  // would cost the editor's state.
  if (currentUser.isLoading && !opened.current) return <EditorSkeleton />;
  if (momentId && moment.isLoading) return <EditorSkeleton />;
  if (momentId && (moment.isError || !moment.data))
    return (
      <EditorLoadError
        retry={() => moment.refetch()}
        draftIsSafe={recovery.state.phase !== "clear"}
      />
    );
  if (moment.data?.entry && entry.isLoading) return <EditorSkeleton />;
  if (moment.data?.entry && (entry.isError || !entry.data))
    return (
      <EditorLoadError
        retry={() => entry.refetch()}
        draftIsSafe={recovery.state.phase !== "clear"}
      />
    );
  if (journals.isLoading) return <EditorSkeleton />;
  if (journals.isError || !journals.data)
    return (
      <EditorLoadError
        retry={() => journals.refetch()}
        draftIsSafe={recovery.state.phase !== "clear"}
      />
    );

  const serverInitialContent = serverContent ?? EMPTY_DELTA;
  if (!isEditableDocumentDelta(serverInitialContent)) {
    return (
      <UnsupportedEditor
        momentId={moment.data?.id ?? momentId ?? ""}
        routeJournalId={journalId}
      />
    );
  }

  // Everything about the local draft is settled BEFORE the form mounts:
  // `QuillSurface` takes its document once and cannot be reseeded.
  if (choice === null && !opened.current) {
    if (
      recovery.state.phase === "checking" ||
      recovery.state.phase === "resolving"
    ) {
      return <EditorSkeleton />;
    }
    if (recovery.state.phase === "unreachable-media") {
      const unreachable = recovery.state;
      return (
        <DraftMediaUnreachable
          draft={unreachable.draft}
          onRetry={unreachable.retry}
          onDiscard={() => {
            void recovery.discard();
            setChoice("server");
          }}
        />
      );
    }
    if (recovery.state.phase === "offer") {
      const offer = recovery.state;
      return (
        <DraftRecoveryPrompt
          draft={offer.draft}
          serverChanged={offer.serverChanged}
          unresolvedMediaCount={offer.unresolvedMediaCount}
          isNewEntry={!momentId}
          onRecover={() => setChoice("draft")}
          onDiscard={() => {
            void recovery.discard();
            setChoice("server");
          }}
        />
      );
    }
  }

  const recovered =
    choice === "draft" && recovery.state.phase === "offer"
      ? recovery.state
      : null;
  opened.current = true;

  return (
    <EntryEditorForm
      key={momentId ?? `new-${journalId ?? "timeline"}`}
      initialContent={recovered?.content ?? serverInitialContent}
      initialJournalId={
        recovered?.draft.journalId ??
        entry.data?.journal_id ??
        journalId ??
        defaultJournalId(journals.data) ??
        ""
      }
      initialTitle={recovered?.draft.title ?? entry.data?.title ?? ""}
      journals={journals.data}
      acceptedMedia={formats.data}
      moment={moment.data}
      routeJournalId={journalId}
      draftKey={draftKey}
      draftUserId={currentUser.data?.id}
      localDraftId={localDraftId}
      serverUpdatedAt={entry.data?.updated_at}
      // A recovered draft brings its server Moment back with it, so Done
      // finalises the Moment that already owns the recovered media instead of
      // creating a second one. Only for a NEW entry: on an existing one the
      // recorded Moment is the reader's own saved entry, not a draft.
      recoveredIdentity={
        !momentId && recovered?.draft.momentId
          ? {
              momentId: recovered.draft.momentId,
              entryId: recovered.draft.entryId ?? null,
            }
          : null
      }
      // Attachments the recovered draft still has. They belong to the draft
      // Moment, so cancelling must keep them — the same thing it does for a
      // session that never reloaded.
      recoveredMediaIds={
        (!momentId && recovered?.resolvedMediaIds) || undefined
      }
      // Content the reader chose to bring back is unsaved by definition.
      startsDirty={choice === "draft"}
      onDraftStored={rememberDraftInUrl}
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
  draftKey,
  draftUserId,
  localDraftId,
  serverUpdatedAt,
  recoveredIdentity,
  recoveredMediaIds,
  startsDirty,
  onDraftStored,
}: {
  initialContent: QuillDelta;
  initialJournalId: string;
  initialTitle: string;
  journals: JournalResponse[];
  acceptedMedia?: unknown;
  moment?: MomentResponse;
  routeJournalId?: string;
  /** Where this session's local draft lives; null when none can be kept. */
  draftKey: string | null;
  draftUserId?: string;
  localDraftId?: string;
  serverUpdatedAt?: string;
  recoveredIdentity: DraftIdentity | null;
  recoveredMediaIds?: string[];
  startsDirty: boolean;
  onDraftStored: () => void;
}) {
  const { q = "" } = useSearch({ strict: false }) as { q?: string };
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const surfaceRef = useRef<QuillSurfaceHandle>(null);
  const titleRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Media uploaded during THIS session, so cancel can clean up only what it
  // introduced and never pre-existing Moment media. A recovered draft's
  // attachments start here too: they were uploaded by an earlier run of this
  // same unfinished entry, and a reload must not turn Cancel from "keep the
  // photographs" into "delete them".
  const sessionMediaRef = useRef<string[]>([...(recoveredMediaIds ?? [])]);
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
    initialIdentity: recoveredIdentity,
  });
  const [title, setTitle] = useState(initialTitle);
  const [journalId, setJournalId] = useState(initialJournalId);
  const [bodyDirty, setBodyDirty] = useState(startsDirty);
  const [metaDirty, setMetaDirty] = useState(false);
  const [error, setError] = useState("");

  // The Moment that owns this entry's metadata. For an existing Moment that is
  // `moment` (the parent refetches it on invalidation, so it stays current). A
  // new entry has none until the Details popover — or media — creates the draft;
  // then we query that draft so the header meta and foot chips can update.
  const draftMomentId = moment ? null : (draft.draft?.momentId ?? null);
  const liveDraftMoment = useQuery({
    ...momentQuery(draftMomentId ?? ""),
    enabled: Boolean(draftMomentId),
  });
  const momentForDisplay = moment ?? liveDraftMoment.data;
  const [editorState, setEditorState] = useState<EditorState>({
    formats: {},
    focused: false,
    selectionLength: 0,
    wordCount: 0,
    selectedMedia: null,
  });
  const titleDirty = title !== initialTitle;
  const journalDirty = journalId !== initialJournalId;
  const dirty = titleDirty || journalDirty || bodyDirty || metaDirty;

  /**
   * The local safety net. Not autosave: Done is still the only thing that puts
   * writing in a journal. This only means a reload does not take it away.
   */
  const localDraft = useLocalDraft({
    key: draftKey,
    identity: draftUserId
      ? {
          userId: draftUserId,
          ...((moment?.entry?.id ?? draft.draft?.entryId)
            ? {
                entryId: moment?.entry?.id ?? draft.draft?.entryId ?? undefined,
              }
            : {}),
          ...((moment?.id ?? draft.draft?.momentId)
            ? { momentId: moment?.id ?? draft.draft?.momentId }
            : {}),
          ...(localDraftId ? { localDraftId } : {}),
        }
      : null,
    journalId,
    title,
    baseUpdatedAt: serverUpdatedAt,
    dirty,
    // `getContents()` strips in-flight upload placeholders, so a document that
    // is mid-upload still yields something safe to keep.
    getDocument: useCallback(
      () => surfaceRef.current?.getContents() ?? null,
      [],
    ),
    onFirstStore: onDraftStored,
  });

  /**
   * Restarts the local debounce. Called from every handler that changes
   * something worth keeping — deliberately explicit rather than an effect
   * watching state, so it is obvious at each call site what is being protected.
   * The server is never called from this path.
   */
  const keepLocally = localDraft.schedule;
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
    onDirty: () => {
      setBodyDirty(true);
      keepLocally();
    },
    onMediaAdded: (mediaId) => sessionMediaRef.current.push(mediaId),
  });

  const openMediaPicker = useCallback(() => {
    setError("");
    fileInputRef.current?.click();
  }, []);

  // Metadata editing needs a server Moment id. Reuse the lazy-draft path so a
  // new entry only creates a row once the user actually sets something.
  const ensureMomentId = useCallback(async (): Promise<string | null> => {
    if (moment) return moment.id;
    if (!journalId) {
      setError("Choose a Journal before adding details");
      return null;
    }
    try {
      const identity = await draft.ensure(journalId);
      return identity.momentId;
    } catch {
      setError("Could not prepare this entry for details. Try again.");
      return null;
    }
  }, [moment, draft, journalId]);

  const onDetailsSaved = useCallback(
    (savedMomentId: string) => {
      setError("");
      // Only a draft we created this session is at risk on Cancel; an existing
      // Moment's metadata is already persisted and must not look "unsaved".
      if (!moment) {
        setMetaDirty(true);
        keepLocally();
      }
      void queryClient.invalidateQueries({
        queryKey: queryKeys.moment(savedMomentId),
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.allMoments });
    },
    [keepLocally, moment, queryClient],
  );

  /**
   * Removes the media under the cursor from the writing. The file is not
   * deleted here: the backend removes media a save dropped from the document
   * (`delete_orphaned_media_for_delta`), so until Done this is undoable.
   */
  const removeSelectedMedia = useCallback(() => {
    if (!surfaceRef.current?.removeSelectedMedia()) return;
    setBodyDirty(true);
    keepLocally();
  }, [keepLocally]);

  const shouldBlock = useCallback(
    ({
      current,
      next,
    }: {
      current: { pathname: string };
      next: { pathname: string };
    }) => {
      // The editor navigates to ITSELF to record the local draft id in
      // `?draft=`. Prompting there would pop a discard dialog on the first
      // keystroke of every new entry.
      if (next.pathname === current.pathname) return false;
      return (
        !allowNavigationRef.current &&
        dirty &&
        !window.confirm(LEAVE_CONFIRMATION)
      );
    },
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
      // The writing is on the server now, so the local copy has done its job.
      // This is the ONLY place a save removes it — every failure below keeps it.
      await localDraft.remove();
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
      ? `${LEAVE_CONFIRMATION} The ${keptMedia === 1 ? "file" : `${keptMedia} files`} you added will stay on this moment.`
      : LEAVE_CONFIRMATION;
    if (dirty && !window.confirm(question)) return;
    allowNavigationRef.current = true;
    // An explicit discard is one of only two things that may remove the local
    // copy. The other is a confirmed server save.
    void localDraft.remove();
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
                onChange={(event) => {
                  setJournalId(event.target.value);
                  keepLocally();
                }}
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
            moment={momentForDisplay}
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
                    keepLocally();
                  }}
                  placeholder="Give this a title (optional)"
                  disabled={mutation.isPending}
                  maxLength={300}
                />
              </>
            }
          />

          <LocalDraftStatus
            status={localDraft.status}
            omittedTransientUploads={localDraft.omittedTransientUploads}
          />

          <EditorToolbar
            editor={surfaceRef.current}
            state={editorState}
            disabled={mutation.isPending}
            onAddMedia={openMediaPicker}
            onRemoveMedia={removeSelectedMedia}
            details={{
              moment: momentForDisplay,
              ensureMomentId,
              onSaved: onDetailsSaved,
              loggedAtUtc: moment?.logged_at_utc ?? draftLoggedAt,
              loggedTimezone: moment?.logged_timezone ?? draftTimezone,
            }}
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
            onFiles={(files, index) => void media.attach(files, index)}
            onUserChange={() => {
              setBodyDirty(true);
              keepLocally();
            }}
            onStateChange={setEditorState}
            placeholder="Write about this moment…"
            readOnly={mutation.isPending}
          />
          {error && (
            <p className="jv-editor__error" role="alert">
              {error}
            </p>
          )}

          {/* Same metadata, same rendering as the reader (DESIGN.md §11). */}
          <MomentChips moment={momentForDisplay} />
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

function EditorLoadError({
  retry,
  draftIsSafe,
}: {
  retry: () => unknown;
  /** There is unsaved writing on this device for this entry. */
  draftIsSafe?: boolean;
}) {
  return (
    <div className="jv-pane-status">
      <StatusView
        role="alert"
        tone="danger"
        icon={<TriangleAlert size={20} />}
        title="The editor could not be loaded"
        // The editor needs the server's own copy before it can offer a local
        // draft against it, so it stays closed. Saying the writing is still
        // here is the difference between a wait and a loss.
        description={
          draftIsSafe
            ? "Your unsaved writing for this entry is still stored on this device and will be offered back once Journiv can be reached."
            : undefined
        }
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
