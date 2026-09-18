// Cross-cutting global-401 signal. Any protected-resource fetch (client.ts,
// sse.ts) calls `notifyUnauthorized()` when the server answers 401; the auth
// state (`state/AuthContext.tsx`) is the sole subscriber in the running app,
// dropping the session to "session expired" without a page reload. A Set
// (not a single slot) keeps repeated subscribe/unsubscribe cycles — e.g. in
// tests — from clobbering each other.

type Listener = () => void;

const listeners = new Set<Listener>();

export function onUnauthorized(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function notifyUnauthorized(): void {
  for (const listener of listeners) listener();
}
