import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { api } from "../../api/client/api";
import { instanceConfigQuery } from "../../api/query/options";
import { sessionStore } from "../../api/auth/session";
import { Alert, AlertDescription } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import { Field, FieldGroup, FieldLabel } from "../../components/ui/field";
import { Input } from "../../components/ui/input";
import { Spinner } from "../../components/ui/spinner";
import "./auth.css";

export function LoginPage() {
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const navigate = useNavigate();
  const { returnTo } = useSearch({ from: "/login" });
  const instanceConfig = useQuery({
    ...instanceConfigQuery(),
    staleTime: 0,
    refetchOnMount: "always",
  });

  async function submit(form: FormData) {
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
      setPending(false);
    }
  }

  return (
    <main className="jv-auth">
      <div className="jv-auth__card">
        <p className="jv-auth__brand">Journiv</p>
        <h1 className="jv-display">Welcome back</h1>
        <p className="jv-auth__lede">Sign in to continue to your journal.</p>
        <form action={submit} className="jv-auth__form">
          <FieldGroup className="jv-auth__fields">
            <Field>
              <FieldLabel htmlFor="email">Email</FieldLabel>
              <Input
                id="email"
                required
                name="email"
                type="email"
                autoComplete="email"
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
              />
            </Field>
          </FieldGroup>
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" variant="primary" disabled={pending}>
            {pending && <Spinner data-icon="inline-start" aria-hidden />}
            {pending ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        {instanceConfig.isSuccess &&
          !instanceConfig.isFetching &&
          !instanceConfig.data.disable_signup && (
            <p className="jv-auth__alternate jv-caption">
              New to Journiv?{" "}
              <Link to="/signup" search={{ returnTo }}>
                Create an account
              </Link>
            </p>
          )}
      </div>
    </main>
  );
}
