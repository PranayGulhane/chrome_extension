// Minimal pub-sub so the module-level chrome.runtime.onMessage listener (outside React) and the
// Esc-key listener can both toggle the panel's visibility, and the App component can subscribe to
// it via useSyncExternalStore. Not reaching for a state library for one boolean.
type Listener = () => void;

let visible = false;
const listeners = new Set<Listener>();

function emit(): void {
  for (const listener of listeners) listener();
}

export const panelStore = {
  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  getSnapshot(): boolean {
    return visible;
  },
  toggle(): void {
    visible = !visible;
    emit();
  },
  close(): void {
    if (!visible) return;
    visible = false;
    emit();
  },
};
