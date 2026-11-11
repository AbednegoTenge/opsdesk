import type { User } from "./types";

/**
 * The signed-in session, held in memory only. The access token never touches
 * localStorage; a page reload restores the session from the httpOnly refresh cookie.
 */
export type Session = { accessToken: string; user: User };

type Listener = (session: Session | null) => void;

let current: Session | null = null;
const listeners = new Set<Listener>();

export const session = {
  get(): Session | null {
    return current;
  },
  set(next: Session | null): void {
    current = next;
    listeners.forEach((listener) => listener(next));
  },
  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};
