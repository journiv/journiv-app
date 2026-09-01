import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import type { IntegrationAssetResponse } from "../../../api/generated/types.gen";
import { immichAssetsInfiniteQuery } from "../../../api/query/options";
import type {
  AssetGridItem,
  AssetGridSource,
} from "../../media/assetGrid.types";
import { isPickableImmichAsset } from "./useImmichAttachments";

function toGridItem(asset: IntegrationAssetResponse): AssetGridItem {
  return {
    id: asset.id,
    thumbUrl: asset.thumb_url,
    label: asset.title ?? "Immich item",
    badge: asset.type === "VIDEO" ? "video" : null,
    // Duration isn't in the normalized asset yet (gap G2). A video badge with
    // no time is still a useful "this is a clip" marker.
    durationSec: null,
  };
}

/**
 * The editor picker's Immich data source, plus a resolver from selected ids
 * back to the full asset records the import call needs.
 *
 * Both this and {@link AssetGridPicker} read the same infinite query key, so
 * React Query serves one cache entry — no double fetch.
 */
export function useImmichAssetSource(enabled = true): {
  source: AssetGridSource;
  resolve: (ids: string[]) => IntegrationAssetResponse[];
} {
  const query = useInfiniteQuery({
    ...immichAssetsInfiniteQuery(),
    enabled,
  });

  const assets = useMemo(
    () => (query.data?.pages ?? []).flatMap((page) => page.assets),
    [query.data],
  );
  const byId = useMemo(() => {
    const map = new Map<string, IntegrationAssetResponse>();
    for (const asset of assets) map.set(asset.id, asset);
    return map;
  }, [assets]);
  const items = useMemo(
    () => assets.filter(isPickableImmichAsset).map(toGridItem),
    [assets],
  );

  const source = useMemo<AssetGridSource>(
    () => ({
      useItems: () => ({
        items,
        isLoading: query.isLoading,
        isFetchingNextPage: query.isFetchingNextPage,
        hasNextPage: query.hasNextPage,
        fetchNextPage: () => {
          void query.fetchNextPage();
        },
        isError: query.isError,
        refetch: () => {
          void query.refetch();
        },
      }),
      empty: {
        title: "Nothing in your Immich library yet",
        description: "Add photos or videos in Immich and they’ll show up here.",
      },
      error: {
        title: "Can’t reach Immich",
        description:
          "The connection may need reconnecting in Settings → Integrations.",
        retryLabel: "Retry",
      },
    }),
    [
      items,
      query.isLoading,
      query.isFetchingNextPage,
      query.hasNextPage,
      query.isError,
      query.fetchNextPage,
      query.refetch,
    ],
  );

  return {
    source,
    resolve: (ids) =>
      ids
        .map((id) => byId.get(id))
        .filter((asset): asset is IntegrationAssetResponse => Boolean(asset)),
  };
}
