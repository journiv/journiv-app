export type AuthSession = {
  version: 1;
  accessToken: string;
};

type SessionListener = (session: AuthSession | null) => void;

const key = "journiv.session.v1";
const listeners = new Set<SessionListener>();

function notify(session: AuthSession | null) {
  for (const listener of listeners) listener(session);
}

export const sessionStore = {
  read: (): AuthSession | null => {
    try {
      const value: unknown = JSON.parse(sessionStorage.getItem(key) ?? "null");
      if (!value || typeof value !== "object") return null;
      const session = value as AuthSession;
      if (
        session.version !== 1 ||
        typeof session.accessToken !== "string" ||
        session.accessToken.length === 0
      )
        return null;
      const sanitized = {
        version: 1,
        accessToken: session.accessToken,
      } as const;
      if ("refreshToken" in value)
        sessionStorage.setItem(key, JSON.stringify(sanitized));
      return sanitized;
    } catch {
      return null;
    }
  },
  write: (session: AuthSession) => {
    sessionStorage.setItem(key, JSON.stringify(session));
    notify(session);
  },
  clear: () => {
    sessionStorage.removeItem(key);
    notify(null);
  },
  subscribe: (listener: SessionListener) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
};
