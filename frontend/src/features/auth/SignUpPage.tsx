import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import { ApiError } from "../../api/client/errors";
import { instanceConfigQuery } from "../../api/query/options";
import { Alert, AlertDescription } from "../../components/ui/alert";
import { Button, buttonVariants } from "../../components/ui/button";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "../../components/ui/field";
import { Input } from "../../components/ui/input";
import { Spinner } from "../../components/ui/spinner";
import "./auth.css";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function signUpErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError))
    return "We couldn’t create your account. Try again.";
  if (error.status === 400)
    return "We couldn’t create that account. Check your details or sign in if you already have one.";
  if (error.status === 403)
    return "Account creation isn’t available on this Journiv instance.";
  if (error.status === 422) return "Check your account details and try again.";
  if (error.status === 429)
    return "Too many account creation attempts. Wait a moment and try again.";
  return "We couldn’t create your account. Try again.";
}

/** The shared authentication card. Every SignUpPage state renders through this
 *  so the brand mark, heading and lede stay identical across them (DESIGN §26,
 *  "exactly one spec"). */
function AuthCard({
  heading,
  lede,
  busy,
  children,
}: {
  heading: string;
  lede: React.ReactNode;
  busy?: boolean;
  children?: React.ReactNode;
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

export function SignUpPage() {
  const nameId = useId();
  const emailId = useId();
  const passwordId = useId();
  const confirmId = useId();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [touched, setTouched] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [accountCreated, setAccountCreated] = useState(false);
  const submittingRef = useRef(false);
  const navigate = useNavigate();
  const { returnTo } = useSearch({ from: "/signup" });
  const instanceConfig = useQuery({
    ...instanceConfigQuery(),
    staleTime: 0,
    refetchOnMount: "always",
  });

  const trimmedName = name.trim();
  const trimmedEmail = email.trim().toLowerCase();
  const nameError = trimmedName ? "" : "Enter your name.";
  const emailError = EMAIL_PATTERN.test(trimmedEmail)
    ? ""
    : "Enter a valid email address.";
  const passwordError = password ? "" : "Enter a password.";
  const confirmError = !confirm
    ? "Confirm your password."
    : confirm !== password
      ? "The passwords don’t match."
      : "";
  const invalid = Boolean(
    nameError || emailError || passwordError || confirmError,
  );

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTouched(true);
    setError("");
    // `pending` alone can be stale for a second submit dispatched before React
    // commits it; the ref closes that window so a fast double Enter/click can
    // never fire `api.register` twice.
    if (invalid || pending || submittingRef.current) return;

    submittingRef.current = true;
    setPending(true);
    let registered = false;
    try {
      await api.register({
        name: trimmedName,
        email: trimmedEmail,
        password,
      });
      registered = true;
      const tokens = await api.login(trimmedEmail, password);
      sessionStore.write({
        version: 1,
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
      });
      await navigate({ href: returnTo });
    } catch (caught) {
      if (registered) {
        setPassword("");
        setConfirm("");
        setAccountCreated(true);
      } else {
        setError(signUpErrorMessage(caught));
      }
    } finally {
      submittingRef.current = false;
      setPending(false);
    }
  }

  // Only the very first load blocks the screen; a background refetch (window
  // focus, reconnect) keeps whatever is already rendered so an in-progress
  // form is never torn down under the user.
  if (instanceConfig.isLoading) {
    return (
      <AuthCard
        heading="Checking sign up"
        busy
        lede={
          <p className="jv-auth__lede jv-auth__status" role="status">
            <Spinner aria-hidden />
            Checking whether this instance accepts new accounts…
          </p>
        }
      />
    );
  }

  if (!instanceConfig.data) {
    return (
      <AuthCard
        heading="Sign up unavailable"
        lede="Journiv couldn’t check whether this instance accepts new accounts."
      >
        <Button variant="primary" onClick={() => void instanceConfig.refetch()}>
          Try again
        </Button>
        <p className="jv-auth__alternate jv-caption">
          Already have an account?{" "}
          <Link to="/login" search={{ returnTo }}>
            Sign in
          </Link>
        </p>
      </AuthCard>
    );
  }

  if (instanceConfig.data.disable_signup || instanceConfig.data.oidc_only) {
    return (
      <AuthCard
        heading="Sign up is disabled"
        lede="This Journiv instance is not accepting new accounts. An administrator can enable sign up in the server configuration and restart Journiv."
      >
        <Link
          className={buttonVariants({ variant: "primary" })}
          to="/login"
          search={{ returnTo }}
        >
          Return to sign in
        </Link>
      </AuthCard>
    );
  }

  if (accountCreated) {
    return (
      <AuthCard
        heading="Account created"
        lede="Your account is ready, but we couldn’t sign you in automatically. Sign in to continue to your journal."
      >
        <Link
          className={buttonVariants({ variant: "primary" })}
          to="/login"
          search={{ returnTo }}
        >
          Sign in
        </Link>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      heading="Create your account"
      lede="A private place for the moments you want to remember."
    >
      <form className="jv-auth__form" noValidate onSubmit={submit}>
        <FieldGroup className="jv-auth__fields">
          <Field data-invalid={touched && Boolean(nameError)}>
            <FieldLabel htmlFor={nameId}>Name</FieldLabel>
            <Input
              id={nameId}
              name="name"
              value={name}
              autoComplete="name"
              autoFocus
              aria-invalid={touched && Boolean(nameError)}
              aria-describedby={
                touched && nameError ? `${nameId}-error` : undefined
              }
              onChange={(event) => setName(event.target.value)}
            />
            {touched && nameError && (
              <FieldError id={`${nameId}-error`}>{nameError}</FieldError>
            )}
          </Field>

          <Field data-invalid={touched && Boolean(emailError)}>
            <FieldLabel htmlFor={emailId}>Email</FieldLabel>
            <Input
              id={emailId}
              name="email"
              type="email"
              value={email}
              inputMode="email"
              autoCapitalize="none"
              autoComplete="email"
              spellCheck={false}
              aria-invalid={touched && Boolean(emailError)}
              aria-describedby={
                touched && emailError ? `${emailId}-error` : undefined
              }
              onChange={(event) => setEmail(event.target.value)}
            />
            {touched && emailError && (
              <FieldError id={`${emailId}-error`}>{emailError}</FieldError>
            )}
          </Field>

          <Field data-invalid={touched && Boolean(passwordError)}>
            <FieldLabel htmlFor={passwordId}>Password</FieldLabel>
            <Input
              id={passwordId}
              name="password"
              type="password"
              value={password}
              autoComplete="new-password"
              aria-invalid={touched && Boolean(passwordError)}
              aria-describedby={
                touched && passwordError
                  ? `${passwordId}-description ${passwordId}-error`
                  : `${passwordId}-description`
              }
              onChange={(event) => setPassword(event.target.value)}
            />
            <FieldDescription id={`${passwordId}-description`}>
              Use a unique password you don’t use elsewhere.
            </FieldDescription>
            {touched && passwordError && (
              <FieldError id={`${passwordId}-error`}>
                {passwordError}
              </FieldError>
            )}
          </Field>

          <Field data-invalid={touched && Boolean(confirmError)}>
            <FieldLabel htmlFor={confirmId}>Confirm password</FieldLabel>
            <Input
              id={confirmId}
              name="confirm-password"
              type="password"
              value={confirm}
              autoComplete="new-password"
              aria-invalid={touched && Boolean(confirmError)}
              aria-describedby={
                touched && confirmError ? `${confirmId}-error` : undefined
              }
              onChange={(event) => setConfirm(event.target.value)}
            />
            {touched && confirmError && (
              <FieldError id={`${confirmId}-error`}>{confirmError}</FieldError>
            )}
          </Field>
        </FieldGroup>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <Button type="submit" variant="primary" disabled={pending}>
          {pending && <Spinner data-icon="inline-start" aria-hidden />}
          {pending ? "Creating account…" : "Create account"}
        </Button>
      </form>

      <p className="jv-auth__alternate jv-caption">
        Already have an account?{" "}
        <Link to="/login" search={{ returnTo }}>
          Sign in
        </Link>
      </p>
    </AuthCard>
  );
}
