import { useInfiniteQuery } from "@tanstack/react-query";
import { Link, useParams, useSearch } from "@tanstack/react-router";
import {
  FileQuestion,
  ImageOff,
  Images,
  Menu,
  Music,
  Play,
  TriangleAlert,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { MediaLibraryItem } from "../../api/generated/types.gen";
import { mediaLibraryQuery } from "../../api/query/options";
import { ListViewSwitch } from "../../components/journiv/ListViewSwitch";
import { PageBar } from "../../components/journiv/PageBar";
import { Button } from "../../components/ui/button";
import { IconButton } from "../../components/ui/icon-button";
import { Skeleton } from "../../components/ui/skeleton";
import { StatusView } from "../../components/journiv/StatusView";
import { cx } from "../../lib/cx";
import { useJournalLookup } from "../../lib/useJournalLookup";
import { usePaneScrollRestoration } from "../../lib/usePaneScrollRestoration";
import { useShell } from "../shell/AppShell";
import { groupMediaByMonth } from "./mediaGroups";
import "./media.css";

const SKELETON_KEYS = Array.from({ length: 12 }, (_, i) => `sk-${i}`);

export function MediaPane() {
  const params = useParams({ strict: false }) as {
    journalId?: string;
    momentId?: string;
  };
  const search = useSearch({ strict: false }) as { q?: string };
  const shell = useShell();
  const journals = useJournalLookup();
  const scopeJournal = journals.get(params.journalId);
  const data = useInfiniteQuery(
    mediaLibraryQuery({ journal_id: params.journalId }),
  );
  const scrollRef = usePaneScrollRestoration<HTMLDivElement>(
    "media",
    data.isLoading,
  );
  const items = data.data?.pages.flatMap((page) => page.items) ?? [];
  const groups = groupMediaByMonth(items);

  // A signed thumbnail can expire between the response and the <img> load, or
  // its file can be gone. The first failure per item forces one refetch to
  // re-sign it; if the item still fails it is marked broken. Never a retry loop,
  // never a dead image on screen.
  //
  // The refetch can hand back the *same* URL (signatures are stamped in whole
  // seconds), and an <img> whose src did not change never fires a second error.
  // So an item is also marked broken once the refetch has settled with its URL
  // unchanged. Broken is remembered per URL: a different URL gets a fresh try.
  const firstFailure = useRef(
    new Map<string, { src: string; loadedAt: number; failures: number }>(),
  );
  const [broken, setBroken] = useState<Record<string, string>>({});
  const markBroken = useCallback((id: string, src: string) => {
    setBroken((current) =>
      current[id] === src ? current : { ...current, [id]: src },
    );
  }, []);
  const { refetch } = data;
  const {
    isFetching,
    dataUpdatedAt: loadedAt,
    errorUpdateCount: failures,
  } = data;
  const onThumbError = useCallback(
    (id: string, src: string) => {
      if (firstFailure.current.get(id)?.src === src) {
        markBroken(id, src);
        return;
      }
      firstFailure.current.set(id, { src, loadedAt, failures });
      void refetch();
    },
    [refetch, loadedAt, failures, markBroken],
  );
  useEffect(() => {
    if (isFetching) return;
    for (const [id, first] of firstFailure.current) {
      // Only once a refetch begun after the failure has settled.
      if (loadedAt === first.loadedAt && failures === first.failures) continue;
      const current = items.find((item) => item.id === id);
      if (current?.signed_thumbnail_url === first.src)
        markBroken(id, first.src);
    }
  }, [isFetching, loadedAt, failures, items, markBroken]);

  return (
    <section className="jv-shell__list" aria-label="Media">
      <PageBar
        className="jv-page-bar--compact-only"
        leading={
          <IconButton label="Open navigation" onClick={shell.openNavigation}>
            <Menu aria-hidden="true" size={19} />
          </IconButton>
        }
        title={
          <span className="jv-label jv-truncate">
            {scopeJournal?.title ?? "All journals"}
          </span>
        }
      />

      <header className="jv-list-header">
        <div className="jv-list-header__row">
          <h1 className="jv-display jv-list-header__title">
            <span className="jv-truncate">Media</span>
          </h1>
          <ListViewSwitch className="jv-list-header__switch" />
        </div>
      </header>

      <div className="jv-media-grid__scroll" ref={scrollRef}>
        {data.isLoading && <MediaGridSkeleton />}

        {data.isError && (
          <StatusView
            role="alert"
            tone="danger"
            icon={<TriangleAlert size={20} />}
            title="Media could not be loaded"
            description="Check your connection and try again."
            action={
              <Button variant="secondary" onClick={() => data.refetch()}>
                Try again
              </Button>
            }
          />
        )}

        {!data.isLoading && !data.isError && !items.length && (
          <StatusView
            icon={<Images size={20} />}
            title="No photos yet"
            description={
              params.journalId
                ? "Photos and videos added to this journal's entries will appear here."
                : "Photos and videos you add to entries will appear here."
            }
          />
        )}

        {groups.map((group) => (
          <div className="jv-media-grid__group" key={group.key}>
            <h2 className="jv-media-grid__month">{group.label}</h2>
            <div className="jv-media-grid__tiles">
              {group.items.map((item) => (
                <MediaTile
                  key={item.id}
                  item={item}
                  journalId={params.journalId}
                  selected={item.moment_id === params.momentId}
                  q={search.q ?? ""}
                  broken={broken[item.id] === item.signed_thumbnail_url}
                  onThumbError={onThumbError}
                />
              ))}
            </div>
          </div>
        ))}

        {data.hasNextPage && (
          <div className="jv-media-grid__more">
            <Button
              variant="secondary"
              onClick={() => data.fetchNextPage()}
              disabled={data.isFetchingNextPage}
            >
              {data.isFetchingNextPage ? "Loading…" : "Load more"}
            </Button>
          </div>
        )}
      </div>
    </section>
  );
}

function MediaTile({
  item,
  journalId,
  selected,
  q,
  broken,
  onThumbError,
}: {
  item: MediaLibraryItem;
  journalId?: string;
  selected: boolean;
  q: string;
  broken: boolean;
  onThumbError: (id: string, src: string) => void;
}) {
  const className = cx("jv-media-tile", selected && "is-selected");
  const linkProps = journalId
    ? {
        to: "/journals/$journalId/$momentId" as const,
        params: { journalId, momentId: item.moment_id },
        search: { q, view: "media" as const },
      }
    : {
        to: "/timeline/$momentId" as const,
        params: { momentId: item.moment_id },
        search: { q, view: "media" as const },
      };

  const label =
    item.media_type === "video"
      ? "Video"
      : item.media_type === "audio"
        ? "Audio clip"
        : item.alt_text || "Photo";

  let inner: React.ReactNode;
  if (item.media_type === "audio") {
    inner = (
      <span className="jv-media-tile__glyph">
        <Music aria-hidden="true" size={20} />
      </span>
    );
  } else if (broken || !item.signed_thumbnail_url) {
    inner = (
      <span className="jv-media-tile__glyph">
        {item.media_type === "image" || item.media_type === "video" ? (
          <ImageOff aria-hidden="true" size={20} />
        ) : (
          <FileQuestion aria-hidden="true" size={20} />
        )}
      </span>
    );
  } else {
    inner = (
      <>
        <img
          src={item.signed_thumbnail_url}
          alt=""
          loading="lazy"
          decoding="async"
          onError={() => onThumbError(item.id, item.signed_thumbnail_url ?? "")}
        />
        {item.media_type === "video" && (
          <span className="jv-media-tile__badge" aria-hidden="true">
            <Play size={14} />
          </span>
        )}
      </>
    );
  }

  return (
    <Link
      {...linkProps}
      className={className}
      aria-label={label}
      aria-current={selected ? "page" : undefined}
    >
      {inner}
    </Link>
  );
}

function MediaGridSkeleton() {
  return (
    <div
      className="jv-media-grid__group"
      role="status"
      aria-label="Loading media"
    >
      <div className="jv-media-grid__month">
        <Skeleton height="0.8rem" width="7rem" />
      </div>
      <div className="jv-media-grid__tiles">
        {SKELETON_KEYS.map((key) => (
          <Skeleton key={key} className="jv-media-tile" />
        ))}
      </div>
    </div>
  );
}
