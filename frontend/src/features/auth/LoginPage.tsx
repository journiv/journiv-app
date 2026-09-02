import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useRef, useState } from "react";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import { instanceConfigQuery } from "../../api/query/options";
import { Alert, AlertDescription } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import { Field, FieldGroup, FieldLabel } from "../../components/ui/field";
import { Input } from "../../components/ui/input";
import { Separator } from "../../components/ui/separator";
import { Spinner } from "../../components/ui/spinner";
import { AuthCard } from "./AuthCard";
import { OidcAction } from "./oidc";
import "./auth.css";

export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const submitting = useRef(false);
  const navigate = useNavigate();
  const { returnTo } = useSearch({ from: "/login" });
  const instanceConfig = useQuery({
    ...instanceConfigQuery(),
    staleTime: 0,
    refetchOnMount: "always",
  });

  async function submit(form: FormData) {
    if (submitting.current) return;

    submitting.current = true;
    setError("");
    setPending(true);
    try {
      const tokens = await api.login(
        String(form.get("email")),
        String(form.get("password")),
      );
      sessionStore.write({
        version: 1,
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
      });
      await navigate({ href: returnTo });
    } catch {
      setError("Sign in failed. Check your email and password.");
    } finally {
      submitting.current = false;
      setPending(false);
    }
  }

  if (instanceConfig.isLoading) {
    return (
      <AuthCard
        heading="Checking sign-in options"
        busy
        lede={
          <p className="jv-auth__lede jv-auth__status" role="status">
            <Spinner aria-hidden />
            Checking how this Journiv instance accepts sign-ins…
          </p>
        }
      />
    );
  }

  if (!instanceConfig.data) {
    return (
      <AuthCard
        heading="Sign in unavailable"
        lede="Journiv couldn’t check the sign-in methods available on this instance."
      >
        <Button variant="default" onClick={() => void instanceConfig.refetch()}>
          Try again
        </Button>
      </AuthCard>
    );
  }

  const { disable_signup, oidc_enabled, oidc_only } = instanceConfig.data;

  if (oidc_only) {
    return (
      <AuthCard
        heading="Welcome back"
        lede="This Journiv instance uses single sign-on. Continue with your identity provider to access your journal."
      >
        <OidcAction returnTo={returnTo} primary />
      </AuthCard>
    );
  }

  return (
    <AuthCard
      heading="Welcome back"
      lede="Sign in to continue to your journal."
    >
      <form className="jv-auth__form" action={submit}>
        <FieldGroup className="jv-auth__fields">
          <Field>
            <FieldLabel htmlFor="email">Email</FieldLabel>
            <Input
              id="email"
              required
              name="email"
              type="email"
              autoComplete="email"
              autoFocus
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="password">Password</FieldLabel>
            <Input
              id="password"
              required
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>
        </FieldGroup>
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <Button type="submit" variant="default" disabled={pending}>
          {pending && <Spinner data-icon="inline-start" aria-hidden />}
          {pending ? "Signing in…" : "Sign in"}
        </Button>
      </form>

      {oidc_enabled && (
        <>
          <div className="jv-auth__divider">
            <Separator aria-hidden="true" />
            <span className="jv-caption">or</span>
            <Separator aria-hidden="true" />
          </div>
          <OidcAction returnTo={returnTo} />
        </>
      )}

      {!disable_signup && (
        <p className="jv-auth__alternate jv-caption">
          New to Journiv?{" "}
          <Link to="/signup" search={{ returnTo }}>
            Create an account
          </Link>
        </p>
      )}
    </AuthCard>
  );
}
