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
import { useCallback, useRef, useState } from "react";
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
  const items = data.data?.pages.flatMap((page) => page.items) ?? [];
  const groups = groupMediaByMonth(items);

  // A signed thumbnail can expire between the response and the <img> load. The
  // first failure per item forces one refetch; a second marks it broken. Same
  // shape as useMomentMedia — never a retry loop, never a dead image on screen.
  const retried = useRef(new Set<string>());
  const [broken, setBroken] = useState<Record<string, true>>({});
  const onThumbError = useCallback(
    (id: string) => {
      if (retried.current.has(id)) {
        setBroken((current) => ({ ...current, [id]: true }));
        return;
      }
      retried.current.add(id);
      void data.refetch();
    },
    [data],
  );

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

      <div className="jv-media-grid__scroll">
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
                  broken={Boolean(broken[item.id])}
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
  onThumbError: (id: string) => void;
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
          onError={() => onThumbError(item.id)}
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
