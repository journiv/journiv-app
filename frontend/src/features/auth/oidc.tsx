import { apiBaseUrl } from "../../api/client/config";
import { buttonVariants } from "../../components/ui/button";
import { cx } from "../../lib/cx";
import { safeReturnTo } from "./returnTo";

const returnToKey = "journiv.auth.oidc-return-to.v1";

export const oidcReturnToStore = {
  read: () => {
    try {
      return safeReturnTo(sessionStorage.getItem(returnToKey));
    } catch {
      return safeReturnTo(undefined);
    }
  },
  write: (returnTo: string) => {
    sessionStorage.setItem(returnToKey, safeReturnTo(returnTo));
  },
  clear: () => {
    sessionStorage.removeItem(returnToKey);
  },
};

export function oidcLoginHref() {
  return `${apiBaseUrl().replace(/\/$/, "")}/api/v1/auth/oidc/login`;
}

export function oidcLogoutHref() {
  return `${apiBaseUrl().replace(/\/$/, "")}/api/v1/auth/oidc/logout`;
}

export function startOidcLogout(
  navigate: (href: string) => void = (href) => window.location.assign(href),
) {
  navigate(oidcLogoutHref());
}

export function OidcAction({
  returnTo,
  primary = false,
}: {
  returnTo: string;
  primary?: boolean;
}) {
  return (
    <a
      className={cx(
        buttonVariants({ variant: primary ? "default" : "outline" }),
        "jv-auth__oidc",
      )}
      href={oidcLoginHref()}
      onClick={() => oidcReturnToStore.write(returnTo)}
    >
      Continue with single sign-on
    </a>
  );
}
