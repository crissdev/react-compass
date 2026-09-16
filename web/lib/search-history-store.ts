'use client';

import { useSyncExternalStore } from 'react';
import {
  parseSearchHistory,
  SEARCH_HISTORY_STORAGE_KEY,
  type SearchHistoryItem,
} from '@/lib/search-history';

const HISTORY_EVENT = 'docchat-search-history-change';
const EMPTY_HISTORY: SearchHistoryItem[] = [];

let cachedValue: string | null | undefined;
let cachedHistory: SearchHistoryItem[] = EMPTY_HISTORY;

function readStoredValue(): string | null {
  try {
    return window.localStorage.getItem(SEARCH_HISTORY_STORAGE_KEY);
  } catch {
    return null;
  }
}

function getSnapshot(): SearchHistoryItem[] {
  const value = readStoredValue();
  if (value !== cachedValue) {
    cachedValue = value;
    cachedHistory = parseSearchHistory(value);
  }
  return cachedHistory;
}

function subscribe(onStoreChange: () => void): () => void {
  const handleStorage = (event: StorageEvent) => {
    if (event.key && event.key !== SEARCH_HISTORY_STORAGE_KEY) return;
    cachedValue = undefined;
    onStoreChange();
  };

  window.addEventListener('storage', handleStorage);
  window.addEventListener(HISTORY_EVENT, onStoreChange);
  return () => {
    window.removeEventListener('storage', handleStorage);
    window.removeEventListener(HISTORY_EVENT, onStoreChange);
  };
}

export function useSearchHistory(): SearchHistoryItem[] {
  return useSyncExternalStore(subscribe, getSnapshot, () => EMPTY_HISTORY);
}

export function saveSearchHistory(items: SearchHistoryItem[]): void {
  const value = JSON.stringify(items);
  cachedValue = value;
  cachedHistory = items;

  try {
    window.localStorage.setItem(SEARCH_HISTORY_STORAGE_KEY, value);
  } catch {
    // The in-memory history still works when storage is unavailable.
  }

  window.dispatchEvent(new Event(HISTORY_EVENT));
}
