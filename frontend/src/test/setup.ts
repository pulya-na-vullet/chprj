import "@testing-library/jest-dom/vitest";

// Mock localStorage for jsdom environment
if (typeof localStorage === "undefined") {
  const store: Record<string, string> = {};
  const localStorageMock = {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = String(value);
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      for (const key in store) {
        delete store[key];
      }
    },
    key: (index: number) => Object.keys(store)[index] || null,
    get length() {
      return Object.keys(store).length;
    },
  };
  Object.defineProperty(window, "localStorage", {
    value: localStorageMock,
  });
}

// jsdom has no matchMedia; core-components' ModalDesktop (responsive context)
// calls it on mount. No-op MediaQueryList is enough for tests.
if (typeof window.matchMedia !== "function") {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}
