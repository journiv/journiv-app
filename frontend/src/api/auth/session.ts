export type AuthSession = {
  version: 1;
  accessToken: string;
  refreshToken: string;
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
      return session.version === 1 &&
        typeof session.accessToken === "string" &&
        session.accessToken.length > 0 &&
        typeof session.refreshToken === "string" &&
        session.refreshToken.length > 0
        ? session
        : null;
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
