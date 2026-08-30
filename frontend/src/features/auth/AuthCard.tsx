import type { ReactNode } from "react";

/** Shared authentication surface for sign-in, sign-up and OIDC completion. */
export function AuthCard({
  heading,
  lede,
  busy,
  children,
}: {
  heading: string;
  lede: ReactNode;
  busy?: boolean;
  children?: ReactNode;
}) {
  return (
    <main className="jv-auth">
      <div className="jv-auth__card" aria-busy={busy || undefined}>
        <p className="jv-auth__brand">Journiv</p>
        <h1 className="jv-display">{heading}</h1>
        {typeof lede === "string" ? (
          <p className="jv-auth__lede">{lede}</p>
        ) : (
          lede
        )}
        {children}
      </div>
    </main>
  );
}
