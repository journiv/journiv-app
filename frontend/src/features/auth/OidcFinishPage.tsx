import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client/api";
import { sessionStore } from "../../api/auth/session";
import { Alert, AlertDescription } from "../../components/ui/alert";
import { buttonVariants } from "../../components/ui/button";
import { Spinner } from "../../components/ui/spinner";
import { cx } from "../../lib/cx";
import { AuthCard } from "./AuthCard";
import { oidcReturnToStore } from "./oidc";
import "./auth.css";

const completionError =
  "We couldn’t complete single sign-on. The link may have expired or already been used.";

export function OidcFinishPage() {
  const { ticket } = useSearch({ from: "/oidc-finish" });
  const navigate = useNavigate();
  const started = useRef(false);
  const [error, setError] = useState(ticket ? "" : completionError);
  const returnTo = oidcReturnToStore.read();

  useEffect(() => {
    if (!ticket || started.current) return;
    // The ticket is single-use. This ref is load-bearing under React StrictMode,
    // whose development effect replay must never send a second exchange.
    started.current = true;
    void api
      .oidcExchange(ticket)
      .then(async (tokens) => {
        sessionStore.write({
          version: 1,
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
        });
        oidcReturnToStore.clear();
        await navigate({ href: returnTo, replace: true });
      })
      .catch(() => setError(completionError));
  }, [navigate, returnTo, ticket]);

  if (error) {
    return (
      <AuthCard
        heading="Sign in wasn’t completed"
        lede="Return to sign in to start a new, secure connection with your identity provider."
      >
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
        <Link
          className={cx(
            buttonVariants({ variant: "primary" }),
            "jv-auth__oidc",
          )}
          to="/login"
          search={{ returnTo }}
        >
          Return to sign in
        </Link>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      heading="Completing sign in"
      busy
      lede={
        <p className="jv-auth__lede jv-auth__status" role="status">
          <Spinner aria-hidden />
          Establishing your Journiv session…
        </p>
      }
    />
  );
}
