import type { ReactNode } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import { BrandMark } from "../../components/journiv/BrandMark";

/** Shared authentication surface for sign-in, sign-up and OIDC completion.
 *  A genuinely detached object, so it is a stock `Card` (DESIGN.md). */
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
      <Card className="jv-auth__card" aria-busy={busy || undefined}>
        <CardHeader className="jv-auth__header">
          <BrandMark size={48} title="Journiv" className="jv-auth__brand" />
          <CardTitle>
            <h1 className="jv-display">{heading}</h1>
          </CardTitle>
          {typeof lede === "string" ? (
            <CardDescription>{lede}</CardDescription>
          ) : (
            lede
          )}
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </main>
  );
}
