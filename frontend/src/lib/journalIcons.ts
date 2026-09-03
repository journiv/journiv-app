import {
  Anchor,
  Baby,
  Bike,
  BookMarked,
  BookOpen,
  Brain,
  Briefcase,
  CalendarHeart,
  Camera,
  Cat,
  Coffee,
  Compass,
  Dog,
  Dumbbell,
  Feather,
  Flower,
  Footprints,
  Globe,
  GraduationCap,
  Heart,
  HeartPulse,
  House,
  Leaf,
  Lightbulb,
  type LucideIcon,
  MapPin,
  Moon,
  Mountain,
  Music,
  NotebookPen,
  Palette,
  PenLine,
  Plane,
  Sparkles,
  Sprout,
  Star,
  Sun,
  Target,
  Tent,
  TreePine,
  Users,
  Utensils,
  Waves,
} from "lucide-react";

/**
 * A journal may carry an icon, rendered tinted with the journal's own colour by
 * `JournalDot`. The stored value is one of these keys — a small curated subset
 * of the Lucide set the app already bundles, never an arbitrary lookup.
 *
 * The Flutter client stores Material Symbols names in the same backend field, so
 * a value written there will not match a key here. That is expected: an
 * unrecognised value falls back to the plain colour dot on both clients. See
 * DESIGN.md.
 */
export const JOURNAL_ICONS: ReadonlyArray<{
  key: string;
  label: string;
  Icon: LucideIcon;
}> = [
  { key: "book-open", label: "Open book", Icon: BookOpen },
  { key: "book-marked", label: "Bookmarked book", Icon: BookMarked },
  { key: "pen-line", label: "Pen", Icon: PenLine },
  { key: "notebook-pen", label: "Notebook", Icon: NotebookPen },
  { key: "feather", label: "Feather", Icon: Feather },
  { key: "heart", label: "Heart", Icon: Heart },
  { key: "heart-pulse", label: "Heartbeat", Icon: HeartPulse },
  { key: "calendar-heart", label: "Calendar heart", Icon: CalendarHeart },
  { key: "sparkles", label: "Sparkles", Icon: Sparkles },
  { key: "star", label: "Star", Icon: Star },
  { key: "sun", label: "Sun", Icon: Sun },
  { key: "moon", label: "Moon", Icon: Moon },
  { key: "brain", label: "Brain", Icon: Brain },
  { key: "lightbulb", label: "Lightbulb", Icon: Lightbulb },
  { key: "target", label: "Target", Icon: Target },
  { key: "briefcase", label: "Briefcase", Icon: Briefcase },
  { key: "graduation-cap", label: "Graduation cap", Icon: GraduationCap },
  { key: "house", label: "House", Icon: House },
  { key: "users", label: "People", Icon: Users },
  { key: "baby", label: "Baby", Icon: Baby },
  { key: "dog", label: "Dog", Icon: Dog },
  { key: "cat", label: "Cat", Icon: Cat },
  { key: "plane", label: "Plane", Icon: Plane },
  { key: "compass", label: "Compass", Icon: Compass },
  { key: "globe", label: "Globe", Icon: Globe },
  { key: "map-pin", label: "Map pin", Icon: MapPin },
  { key: "mountain", label: "Mountain", Icon: Mountain },
  { key: "tent", label: "Tent", Icon: Tent },
  { key: "tree-pine", label: "Pine tree", Icon: TreePine },
  { key: "leaf", label: "Leaf", Icon: Leaf },
  { key: "sprout", label: "Sprout", Icon: Sprout },
  { key: "flower", label: "Flower", Icon: Flower },
  { key: "waves", label: "Waves", Icon: Waves },
  { key: "anchor", label: "Anchor", Icon: Anchor },
  { key: "dumbbell", label: "Dumbbell", Icon: Dumbbell },
  { key: "bike", label: "Bicycle", Icon: Bike },
  { key: "footprints", label: "Footprints", Icon: Footprints },
  { key: "camera", label: "Camera", Icon: Camera },
  { key: "music", label: "Music note", Icon: Music },
  { key: "palette", label: "Palette", Icon: Palette },
  { key: "coffee", label: "Coffee", Icon: Coffee },
  { key: "utensils", label: "Utensils", Icon: Utensils },
];

const BY_KEY = new Map(JOURNAL_ICONS.map((entry) => [entry.key, entry.Icon]));

/**
 * Resolve a stored icon value to a renderable component, or `null` when it is
 * empty or not one of our keys (e.g. a Material Symbols name from Flutter).
 */
export function resolveJournalIcon(value?: string | null): LucideIcon | null {
  if (!value) return null;
  return BY_KEY.get(value) ?? null;
}
