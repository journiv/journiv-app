import { lazy, Suspense } from "react";
import type { MediaViewerProps } from "./MediaViewerImpl";

export type { MediaViewerProps } from "./MediaViewerImpl";
export {
  type MediaViewerItem,
  libraryMediaToViewerItems,
  momentMediaToViewerItems,
} from "./mediaViewerItem";

const MediaViewerImpl = lazy(async () => ({
  default: (await import("./MediaViewerImpl")).MediaViewerImpl,
}));

/**
 * Full-screen media viewer.
 *
 * Thin lazy boundary around `MediaViewerImpl` so `yet-another-react-lightbox`
 * and its plugins load only when a viewer is actually opened, not with the
 * route. `MediaViewerImpl` is the only importer of the library; returning
 * before it is rendered means `React.lazy` never runs the dynamic import, so
 * the chunk is not even requested on a normal Reader load — a separate build
 * chunk alone would not guarantee that. There is no fallback: nothing shows
 * until the closed → open transition.
 */
export function MediaViewer(props: MediaViewerProps) {
  if (props.activeId == null) return null;
  return (
    <Suspense fallback={null}>
      <MediaViewerImpl {...props} />
    </Suspense>
  );
}
