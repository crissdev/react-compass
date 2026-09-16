'use client';

import { useSyncExternalStore } from 'react';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'docchat-theme';
const THEME_EVENT = 'docchat-theme-change';

function readTheme(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
}

function subscribe(onStoreChange: () => void): () => void {
  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
  const handleSystemThemeChange = (event: MediaQueryListEvent) => {
    if (localStorage.getItem(STORAGE_KEY)) return;
    document.documentElement.dataset.theme = event.matches ? 'dark' : 'light';
    onStoreChange();
  };

  window.addEventListener(THEME_EVENT, onStoreChange);
  mediaQuery.addEventListener('change', handleSystemThemeChange);

  return () => {
    window.removeEventListener(THEME_EVENT, onStoreChange);
    mediaQuery.removeEventListener('change', handleSystemThemeChange);
  };
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, readTheme, () => 'light');
}

export function setTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(STORAGE_KEY, theme);
  window.dispatchEvent(new Event(THEME_EVENT));
}
