import { useState } from "react";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { api } from "../../api/client/api";
import { sessionStore } from "../../api/auth/session";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import "./auth.css";

export function LoginPage() {
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const navigate = useNavigate();
  const { returnTo } = useSearch({ from: "/login" });

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
      await navigate({ to: returnTo });
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
          <label className="jv-auth__label" htmlFor="email">
            Email
            <Input
              id="email"
              required
              name="email"
              type="email"
              autoComplete="email"
            />
          </label>
          <label className="jv-auth__label" htmlFor="password">
            Password
            <Input
              id="password"
              required
              name="password"
              type="password"
              autoComplete="current-password"
            />
          </label>
          {error && (
            <p className="jv-auth__error" role="alert">
              {error}
            </p>
          )}
          <Button type="submit" variant="primary" disabled={pending}>
            {pending ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </div>
    </main>
  );
}
