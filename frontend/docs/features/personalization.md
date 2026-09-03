# Personalization feature contract

Personalization is device-local theming over the existing shadcn tokens. It is
not the global visual contract; read DESIGN.md for that.

UserTheme stores versioned light/dark partial semantic colour maps plus optional
system/editor fonts and prose scale in localStorage. Radius and arbitrary font
variables are deliberately excluded. The structured map is the expected shape
for a future account-settings sync field.

Apply only parsed, allowlisted CSS declarations through the single user-theme
style element. The importer is lenient about CSS structure but strict about
allowed names and safe colour-function values; reject URLs, imports, unsafe
functions, unbalanced values, and font declarations. Export is the inverse and
keeps fonts as a comment.

Accent is a light/dark brand plus brand-foreground pair, not one colour. The
picker clamps each theme to a contrast-safe band and rejects values it cannot
measure. Imported themes retain their own authored pairs. Curated presets are
tested against background, card, and foreground in both modes.

System and editor font pickers are independent and use bundled fonts. Prose
scale changes prose only, never root rem sizing. The dormant UI-feel experiment
layer has no mounted control; keep it isolated until deliberately removed.

## Known gaps

- Personalization does not sync across devices.
- The picker keeps a fixed brand foreground for some pale custom accents; full
  theme import is the supported escape hatch.

